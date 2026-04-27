"""Markup-native Figma renderer — Option B walker.

This module replaces `dd.renderers.figma.generate_figma_script` at M6
cutover per `docs/decisions/v0.3-option-b-cutover.md`. Until then it
coexists with the dict-IR renderer in CI; an A/B harness
(`tests/test_option_b_parity.py`) asserts the two paths produce
scripts at parity.

Current scope (M1d):

- ``render_figma_preamble`` emits the pre-Phase-1 region byte-identical
  to baseline (M1b).
- ``render_figma`` walks the L3 AST in BFS order and emits a full
  three-phase Figma script (M1c + M1d):

  * Phase 1 — materialize nodes via Mode 1 ``createInstance`` (with
    fallback chain + wireframe placeholder) or per-type
    ``createFrame`` / ``createRectangle`` / ``createEllipse`` /
    ``createLine`` / ``createVector`` / ``createBooleanOperation`` /
    ``createText``; intrinsic properties via a transitional
    ``_spec_elements`` shim into baseline ``_emit_visual`` /
    ``_emit_layout`` / ``_emit_text_props`` / ``_emit_vector_paths``.
  * Phase 2 — wire tree via ``appendChild`` (with leaf-parent guard),
    emit text characters, emit per-node ``layoutSizingHorizontal`` /
    ``layoutSizingVertical`` when parent is auto-layout.
  * Phase 3 — ``resize`` for non-auto-layout children, position,
    constraints, and any override-tree-deferred ops.
  * End wrapper — outer try/catch that captures render-thrown
    exceptions into ``__errors`` and returns ``M``.

Pipeline-health gate on 3 reference fixtures (181/222/237): no crash,
non-empty, landmarks present, script-size ratio ≥ 0.90 (actual
0.938–0.940). Tight byte-parity is M2 scope; the ``_spec_elements``
shim and the baseline-helper imports below are removed at M2/M6 per
the decision record.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any, Optional

from dd.markup_l3 import L3Document, Node, PathOverride
from dd.renderers.figma import (
    MISSING_COMPONENT_PLACEHOLDER_BLOCK,
    _CONSTRAINT_MAP,
    _SIZING_MAP,
    _build_text_finder,
    _collect_swap_targets_from_tree,
    _emit_layout,
    _emit_override_tree,
    _emit_text_props,
    _emit_vector_paths,
    _emit_visual,
    _escape_js,
    _guarded_op,
    _resolve_layout_sizing,
    _walk_elements,
)
from dd.visual import build_visual_from_db


# Baseline createText defaults when the AST carries no typography
# (the current M0 compressor output). These match
# `dd.renderers.figma.generate_figma_script` emission for a bare text
# element with empty `style` — byte-parity on M1c depends on using the
# exact same fallback values.
_DEFAULT_TEXT_FONT_FAMILY = "Inter"
_DEFAULT_TEXT_FONT_STYLE = "Regular"


_TEXT_TYPES = frozenset({"text", "heading", "link"})


_LEAF_TYPES = frozenset({
    "text", "heading", "link",
    "rectangle", "ellipse", "line", "vector", "boolean_operation",
})


# AST types that map to Figma native types for createCalls. Unsupported
# types (instance, group) or unknown types fall through to
# `figma.createFrame()` — matches baseline line 1273 fallback.
_TYPE_TO_CREATE_CALL: dict[str, str] = {
    "frame": "figma.createFrame()",
    "rectangle": "figma.createRectangle()",
    "ellipse": "figma.createEllipse()",
    "line": "figma.createLine()",
    "vector": "figma.createVector()",
    "boolean_operation": "figma.createBooleanOperation()",
    "text": "figma.createText()",
    "heading": "figma.createText()",
    "link": "figma.createText()",
}


def render_figma_preamble(
    doc: L3Document,
    conn: sqlite3.Connection,
    nid_map: dict[str, int],
    *,
    fonts: list[tuple[str, str]],
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    ckr_built: bool = True,
    uses_placeholder: bool = False,
) -> str:
    """Emit the pre-Phase-1 preamble region of a Figma render script.

    The output is byte-identical to the range of
    `generate_figma_script(...)`'s return string from the start up to
    (but not including) the `// Phase 1:` marker. That identity is
    enforced by `tests/test_option_b_parity.py::TestM1bPreambleByteParity`.

    `fonts` is the deduplicated (family, style) manifest for every
    font the render will reference. The caller supplies it — a screen's
    manifest includes fonts used by CompRef descendants (which come from
    master components at render time and are NOT in `doc.top_level`'s
    walk). Producing that manifest AST-natively (walking CompRef masters
    from the DB) is an M1c+ concern; for M1b, callers supply
    `dd.renderers.figma.collect_fonts(spec, db_visuals)` as the bridge.

    `uses_placeholder` signals that at least one Phase 1 node in the
    render will call `_missingComponentPlaceholder` (Mode 1 fallback).
    Baseline determines this post-walk and back-fills the reserved
    preamble slot; Option B takes it as an input because M1b's scope
    is preamble emission, not node-creation walking. The full M1d
    walker computes this during its Phase 1 pass.

    `conn` is accepted but not currently read — reserved for M1c+
    lookups. The preamble is a pure function of (fonts, db_visuals,
    ckr_built, uses_placeholder).

    `doc` and `nid_map` are likewise accepted in the M1b signature so
    the caller shape matches the full `render_figma` at M1d onwards;
    they aren't consulted by the preamble itself.
    """
    del doc, conn, nid_map  # reserved for M1c+

    preamble: list[str] = []
    preamble.append("const __errors = [];")
    # Per-stage timing instrumentation (2026-04-24). Diagnostic only;
    # cost is microseconds. Each `__mark(name)` records a delta from
    # the prior marker so a partial run (e.g. PROXY_EXECUTE timeout
    # mid-script) leaves __perf populated up to the last reached
    # stage. M["__perf"] = __perf is appended in _emit_end_wrapper.
    # Callers that iterate M (walk_ref.js / execute_ref.js) filter
    # "__perf" alongside "__errors" / "__canary".
    preamble.append("const __perf = { stages: {}, t0: Date.now() };")
    preamble.append("let __t_last = __perf.t0;")
    preamble.append(
        "const __mark = (name) => { const now = Date.now(); "
        "__perf.stages[name] = now - __t_last; __t_last = now; };"
    )
    # Phase 1 perf (2026-04-22): make document traversal faster by
    # skipping invisible instance children. Figma docs flag this as
    # the default in Dev Mode and "significantly speeds up"
    # findOne / findAll / tree walks. Our extraction path computes
    # effective visibility upstream so the skipped children aren't
    # needed at render time. Set BEFORE any figma.* call so every
    # subsequent operation benefits.
    preamble.append("figma.skipInvisibleInstanceChildren = true;")

    # Phase 1 perf (2026-04-22): batch font loads via a single
    # Promise.all instead of N sequential awaits. Figma's docs call
    # this out as the canonical pattern (`working-with-text`), and
    # font loads are internally cached so no benefit from serialisation.
    # Each font still keeps its own .catch() so one failure doesn't
    # abort the batch — errors are pushed into __errors per-font, same
    # shape as before. Screen 241 went from 28 serial awaits to 1.
    all_fonts = [("Inter", "Regular")] + [
        f for f in fonts if f != ("Inter", "Regular")
    ]
    if all_fonts:
        font_entries: list[str] = []
        for family, style in all_fonts:
            family_js = _escape_js(family)
            style_js = _escape_js(style)
            font_entries.append(
                f"figma.loadFontAsync({{family: \"{family_js}\", style: \"{style_js}\"}})"
                f".catch(__e => __errors.push({{"
                f"kind:\"font_load_failed\", "
                f"family:\"{family_js}\", style:\"{style_js}\", "
                f"error: String(__e && __e.message || __e)"
                f"}}))"
            )
        preamble.append(
            "await Promise.all([\n  "
            + ",\n  ".join(font_entries)
            + "\n]);"
        )
    preamble.append('__mark("preamble_done");')

    preamble.append("const M = {};")
    if not ckr_built:
        preamble.append(
            '__errors.push({kind:"ckr_unbuilt", '
            'error:"component_key_registry empty or missing — '
            'Mode 1 will degrade to Mode 2 for every INSTANCE node"});'
        )
    preamble.append("const _rootPage = figma.currentPage;")
    if uses_placeholder:
        preamble.append(MISSING_COMPONENT_PLACEHOLDER_BLOCK)
    else:
        preamble.append("")

    needed_node_ids = _collect_prefetch_ids(db_visuals)

    if needed_node_ids:
        preamble.append(
            "// Pre-fetch component nodes (deduplicated, null-safe)"
        )
        for i, fid in enumerate(sorted(needed_node_ids)):
            var_name = f"_p{i}"
            id_lit = _escape_js(fid)
            preamble.append(
                f'const {var_name} = await (async () => {{ '
                f'try {{ return await figma.getNodeByIdAsync("{id_lit}"); }} '
                f'catch (__e) {{ __errors.push({{kind:"prefetch_failed", '
                f'id:"{id_lit}", error: String(__e && __e.message || __e)}}); '
                f'return null; }} '
                f'}})();'
            )
    preamble.append(
        '__perf.prefetch_count = ' + str(len(needed_node_ids)) + ';'
    )
    preamble.append('__mark("prefetch_done");')

    preamble.append("")
    # Baseline wraps Phases 1-3 in a single `try { ... } catch` block to
    # capture script-level throws into `__errors`. The opener lives in
    # the preamble region because it appears before the `// Phase 1:`
    # marker; matching baseline byte-for-byte requires emitting it here.
    preamble.append("")
    preamble.append("try {")
    return "\n".join(preamble) + "\n"


def render_figma(
    doc: L3Document,
    conn: Optional[sqlite3.Connection],
    nid_map: dict[int, int],
    *,
    fonts: list[tuple[str, str]],
    spec_key_map: dict[int, str],
    original_name_map: Optional[dict[int, str]] = None,
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    ckr_built: bool = True,
    page_name: Optional[str] = None,
    canvas_position: Optional[tuple[float, float]] = None,
    _spec_elements: Optional[dict[str, dict[str, Any]]] = None,
    _spec_tokens: Optional[dict[str, Any]] = None,
    descendant_visibility_resolver: Optional[
        dict[str, dict[str, str]]
    ] = None,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Full markup-native Figma render-script walker.

    Walks `doc` in pre-order, dispatches per `Node.head.type_or_path`
    (for type-keyword heads) or per Mode-1 comp-ref resolution (for
    comp-ref heads). Emits a three-phase Figma JS script with the
    same shape baseline `generate_figma_script` produces for dict-IR
    input.

    `spec_key_map` and `original_name_map` and `nid_map` are keyed
    on ``id(Node)`` — grammar §2.3.1 only scopes eid uniqueness to
    siblings, so cousin subtrees can share an eid. Object identity
    is the only unambiguous per-Node lookup key within one
    compressor run. Produced by
    ``dd.compress_l3.compress_to_l3_with_maps``.

    `spec_key_map[id(node)]` resolves to the CompositionSpec element
    key (``"screen-1"``, ``"button-3"``); the baseline renderer emits
    ``M["<spec_key>"] = nN.id;`` and the verifier reads that M dict
    to walk the rendered tree. `original_name_map[id(node)]` is the
    raw Figma layer name (``"iPhone 13 Pro Max – 119"``) before
    grammar sanitization. When absent, falls back to the AST eid.

    ``_spec_elements`` and ``_spec_tokens`` are transitional M1d
    shims: the ``spec["elements"]`` and ``spec["tokens"]`` dicts
    from the baseline ``generate_ir`` output. When supplied, Phase 1
    delegates per-node visual / layout / text property emission to
    baseline helpers (``_emit_visual`` / ``_emit_layout`` /
    ``_emit_text_props``) on a per-node shadow element — getting us
    to ratio ≥ 0.95 against baseline output without re-implementing
    those emitters AST-natively yet. Native re-implementation is
    tracked for M2 byte-parity + M5 upstream migration. When absent
    (M1c-minimal fixtures, early M1d tests), Phase 1 falls back to
    the cheap-emission path (name + fills=[] + fontName default
    only).
    """
    original_name_map = original_name_map or {}
    spec_elements = _spec_elements or {}
    spec_tokens = _spec_tokens or {}
    walk = list(_walk_ast(doc))

    # Baseline assigns `n{idx}` where `idx` is the position in the full
    # BFS walk of `spec["elements"]` — including Mode-1-absorbed
    # descendants whose idx slot is "burned" but produces no
    # var_map entry. My AST walk naturally excludes absorbed nodes, so
    # a dense counter would diverge from baseline's gappy numbering.
    # Match baseline by keying var names on the spec-walk index when
    # the shim supplies `_spec_elements`; otherwise fall back to dense
    # numbering (M1c synthetic fixtures only).
    #
    # Key on `id(node)` (Python object identity) rather than
    # `node.head.eid` — grammar §2.3.1 only requires eid uniqueness
    # within a Block, so cousin subtrees can collide on eid and clobber
    # each other's var_map entries. Using object identity makes each
    # Node's var lookup unambiguous regardless of eid collisions.
    if spec_elements and doc.top_level:
        root_spec_key = spec_key_map.get(id(doc.top_level[0]), "")
        baseline_walk_idx = _baseline_walk_indices(
            spec_elements, root_spec_key,
        )
        # Slot children synthesised post-compressor (plan-type-role-
        # split Option 2) aren't in the dict-IR walk the baseline
        # builds indices from, so their fallback mustn't collide with
        # any existing baseline_idx. Start fallback above the
        # baseline's max; two Option-2 slot kids on the same screen
        # get distinct n{N} assignments, no "invalid redefinition of
        # lexical identifier" in the emitted script.
        _fallback_idx = max(baseline_walk_idx.values(), default=-1) + 1
        var_map: dict[int, str] = {}
        for _idx, (node, _p) in enumerate(walk):
            spec_key = spec_key_map.get(id(node), node.head.eid)
            baseline_idx = baseline_walk_idx.get(spec_key)
            if baseline_idx is None:
                baseline_idx = _fallback_idx
                _fallback_idx += 1
            var_map[id(node)] = f"n{baseline_idx}"
    else:
        var_map = {
            id(node): f"n{idx}" for idx, (node, _p) in enumerate(walk)
        }

    node_id_vars = _prefetch_var_map(db_visuals)
    # F13c: deferred_groups is populated by Phase 1 (every GROUP
    # encountered registers here, skipping Phase 1 emission).
    # Phase 2 reads it to emit `figma.group(...)` bottom-up after
    # all descendants are created. Phase 3 reads it to emit
    # group position-only ops (no resize / no layoutSizing).
    deferred_groups: dict[int, dict[str, Any]] = {}
    # Phase E #3 (2026-04-26): same pattern for BOOLEAN_OPERATION
    # nodes. Plugin API requires children to exist before
    # `figma.union/subtract/intersect/exclude([children], parent)`
    # can wrap them. Phase 1 registers the bool_op + its operation
    # type; Phase 2 walks bottom-up after the appendChild loop and
    # emits the materialization call. Phase 3 then applies regular
    # resize/position/constraints (post-materialization the bool
    # node IS extensible — verified empirically against the live
    # bridge: name/fills/strokes/x/y/rotation/opacity/visible all
    # accept writes). See test_boolean_operation_fidelity_debt.py
    # for the contract this implementation satisfies.
    deferred_bool_ops: dict[int, dict[str, Any]] = {}
    (
        phase1, uses_placeholder, phase1_refs,
        override_deferred, absorbed_node_ids,
    ) = _emit_phase1(
        walk, var_map, spec_key_map, original_name_map,
        nid_map=nid_map, db_visuals=db_visuals,
        spec_elements=spec_elements, spec_tokens=spec_tokens,
        node_id_vars=node_id_vars,
        descendant_visibility_resolver=descendant_visibility_resolver,
        deferred_groups=deferred_groups,
        deferred_bool_ops=deferred_bool_ops,
    )
    preamble = render_figma_preamble(
        doc, conn, nid_map,
        fonts=fonts, db_visuals=db_visuals, ckr_built=ckr_built,
        uses_placeholder=uses_placeholder,
    )
    text_chars = _collect_text_chars(walk, var_map)
    phase2 = _emit_phase2(
        walk, var_map, text_chars, spec_key_map, doc, page_name,
        canvas_position=canvas_position,
        nid_map=nid_map, db_visuals=db_visuals,
        spec_elements=spec_elements,
        spec_tokens=spec_tokens,
        deferred_groups=deferred_groups,
        deferred_bool_ops=deferred_bool_ops,
        absorbed_node_ids=absorbed_node_ids,
    )
    phase3 = _emit_phase3(
        walk, var_map, spec_key_map,
        nid_map=nid_map, db_visuals=db_visuals,
        spec_elements=spec_elements,
        override_deferred=override_deferred,
        deferred_groups=deferred_groups,
        absorbed_node_ids=absorbed_node_ids,
    )

    end = _emit_end_wrapper()

    body_lines = phase1 + phase2 + phase3 + end
    script = preamble + "\n".join(body_lines)
    return script, phase1_refs


def _collect_prefetch_ids(
    db_visuals: Optional[dict[int, dict[str, Any]]],
) -> set[str]:
    """Build the set of Figma node IDs the preamble prefetches.

    Matches baseline `generate_figma_script` line ~914: iterate every
    `db_visuals[nid]`, collect `component_figma_id` plus every swap
    target reachable through the override tree. Sorted at emission
    time so `_p0`, `_p1`, ... assignments are deterministic.
    """
    needed: set[str] = set()
    if db_visuals is None:
        return needed
    for _nid, vis in db_visuals.items():
        figma_id = vis.get("component_figma_id")
        if figma_id:
            needed.add(figma_id)
        _collect_swap_targets_from_tree(
            vis.get("override_tree"), needed,
        )
    return needed


def _prefetch_var_map(
    db_visuals: Optional[dict[int, dict[str, Any]]],
) -> dict[str, str]:
    """Return `{figma_node_id: _pN}` matching the preamble's prefetch
    variable assignments. `_emit_override_tree` looks up `instance_swap`
    targets here and emits the prefetched local instead of re-issuing
    `getNodeByIdAsync`.
    """
    needed = _collect_prefetch_ids(db_visuals)
    return {
        fid: f"_p{i}"
        for i, fid in enumerate(sorted(needed))
    }


def _ast_prop_is_false(node: Node, key: str) -> bool:
    """Return True iff the AST node's head has a property ``key`` whose
    value is a boolean literal ``false``.

    Reads straight from ``node.head.properties`` rather than the
    dict-IR shim's ``element.get(key)``. Canonical multi-backend-ready
    pattern: every backend walker consumes the same L3 AST property
    and emits its native representation.

    Skips non-PropAssign entries (PathOverride carries a `.path` not
    a `.key` — those address descendants, not the head-node's own
    properties).
    """
    for prop in node.head.properties:
        if not hasattr(prop, "key"):
            continue
        if prop.key == key:
            val = getattr(prop.value, "py", None)
            return val is False
    return False


def _ast_prop_py(node: Node, key: str) -> Any:
    """Return the Python value of AST property ``key`` on the node's
    head, or ``None`` when absent. Companion to
    ``_ast_prop_is_false`` — same canonical read path, different
    return contract (scalar vs boolean-false-probe).

    Skips non-PropAssign entries (PathOverride carries a `.path` not
    a `.key` — those address descendants, not the head-node's own
    properties).
    """
    for prop in node.head.properties:
        if not hasattr(prop, "key"):
            continue
        if prop.key == key:
            return getattr(prop.value, "py", None)
    return None


def _reconstruct_relative_transform(
    x: float,
    y: float,
    rotation_deg: float,
    mirror_axis: Optional[str],
) -> list[list[float]]:
    """Reconstruct a Figma 2×3 ``relativeTransform`` from L3 primitives.

    Inverse of ``dd.compress_l3._decompose_rt``:

    - No mirror: rotation matrix ``[[cos, -sin, tx], [sin, cos, ty]]``.
    - ``mirror="horizontal"``: negate the first column of that rotation
      matrix (the decomposer builds ``u`` by negating column 0 and
      requires ``u`` to be a pure rotation; we undo that).
    - ``mirror="vertical"``: negate the second column.

    Multi-backend-neutral L3 intent: Figma reconstructs the matrix;
    React/SwiftUI/Flutter use native ``transform: rotate() scaleX()``,
    ``.rotationEffect().scaleEffect(x:-1)``, ``Transform.rotate`` +
    scale negation respectively. Every backend consumes the same two
    AST primitives.
    """
    rot_rad = math.radians(rotation_deg)
    c = math.cos(rot_rad)
    s = math.sin(rot_rad)
    m00, m01 = c, -s
    m10, m11 = s, c
    if mirror_axis == "horizontal":
        m00 = -m00
        m10 = -m10
    elif mirror_axis == "vertical":
        m01 = -m01
        m11 = -m11
    return [[m00, m01, x], [m10, m11, y]]


def _matrix_cell(v: float) -> str:
    """Format a matrix cell with enough precision for round-trip
    parity while keeping trig-epsilon values readable. Mirrors the
    baseline renderer's inline formatting.
    """
    if abs(v) < 1e-12:
        return "0"
    rounded = round(v, 9)
    if rounded == int(rounded):
        return f"{int(rounded)}"
    return f"{rounded}"


def _baseline_walk_indices(
    spec_elements: dict[str, dict[str, Any]],
    root_spec_key: str,
) -> dict[str, int]:
    """Return `{spec_element_key: baseline_walk_idx}` matching the
    position assignment baseline's ``n{idx}`` counter produces.

    Baseline `_walk_elements` is BFS from the root; the `idx` used for
    variable naming is ``enumerate(walk_order)``, so Mode-1-absorbed
    descendants consume an idx slot and leave a gap in the emitted
    variable sequence. Using this map via ``spec_key_map`` lets the
    Option B walker inherit baseline's variable-name assignment
    without walking the dict-IR at render time.

    M2 shim: removed alongside `_spec_elements` when the verifier
    migrates to AST eids (M5).
    """
    spec = {"elements": spec_elements, "root": root_spec_key}
    walk = _walk_elements(spec)
    return {eid: idx for idx, (eid, _elem, _parent) in enumerate(walk)}


def _walk_ast(doc: L3Document) -> list[tuple[Node, Optional[Node]]]:
    """BFS walk yielding (node, parent_or_None) pairs.

    Parent is `None` for top-level nodes. BFS matches baseline
    `dd.renderers.figma._walk_elements` — variable names (`n0`, `n1`,
    `n2`, ...) and `appendChild` emission order depend on walk order,
    so any divergence here breaks byte-parity on branching trees.
    """
    out: list[tuple[Node, Optional[Node]]] = []
    queue: list[tuple[Node, Optional[Node]]] = [
        (top, None) for top in doc.top_level
    ]
    while queue:
        node, parent = queue.pop(0)
        out.append((node, parent))
        if node.block is not None:
            for stmt in node.block.statements:
                if isinstance(stmt, Node):
                    queue.append((stmt, node))
    return out


def _guard_naked_prop_lines(
    lines: list[str], eid: str, kind: str,
) -> list[str]:
    """Post-process a list of JS lines and wrap any naked per-prop
    write (``{var}.{prop} = {value};``) in ``_guarded_op``.

    Preserves lines that are already guarded (start with ``try``),
    comments, and anything not shaped like a prop assignment. This
    lets helpers that emit a mix of guarded + naked lines (e.g.
    ``_emit_text_props``, ``_emit_visual``'s registry path,
    ``_emit_vector_paths``) be post-processed by the Phase 1 caller
    uniformly.

    Rationale: Phase 1 ops are wrapped in a single outer try/catch
    (``_emit_end_wrapper``). Without per-op guards, one throw
    cascades through every remaining Phase 1 op AND Phase 2's
    ``_page.appendChild(root_var)`` — the root attach — stranding
    the already-created nodes on ``figma.currentPage`` as orphans.
    Twin of the Phase 2 F3 follow-up at lines 1212-1219.
    """
    out: list[str] = []
    for raw in lines:
        stripped = raw.lstrip()
        # Already guarded, a comment, or an empty line.
        if (
            not stripped
            or stripped.startswith("try ")
            or stripped.startswith("try{")
            or stripped.startswith("//")
        ):
            out.append(raw)
            continue
        # Skip bookkeeping writes on the M dict and diagnostic writes.
        if stripped.startswith("M[") or stripped.startswith("__"):
            out.append(raw)
            continue
        # Skip const/let/var declarations (the creation lines are
        # load-bearing; nothing to guard at the variable-declaration
        # boundary).
        if (
            stripped.startswith("const ")
            or stripped.startswith("let ")
            or stripped.startswith("var ")
        ):
            out.append(raw)
            continue
        # Skip JS control-flow block openers. These have ``=`` (from
        # ``=>`` arrows or inline assignments in ``for`` headers) and
        # ``.`` (from ``obj.findAll`` calls in ``for`` headers) and
        # would otherwise match the shape check below, producing
        # syntactically broken output (e.g.
        # ``try { for (...) { } catch ...`` with a dangling brace).
        # Twin of the ``M[`` / ``__`` / ``const`` skips — structural
        # lines are load-bearing, not per-op writes.
        control_prefixes = (
            "for ", "for(",
            "if ", "if(",
            "else ", "else{", "else {",
            "while ", "while(",
            "do ", "do{", "do {",
            "switch ", "switch(",
            "return ", "return;", "return}",
            "throw ",
            "function ", "function(",
            "async ", "await ",  # bare await/async at statement start
            "}", "{",  # brace-only lines (block close/open)
        )
        if stripped.startswith(control_prefixes):
            out.append(raw)
            continue
        # Shape check: ``<var>.<prop>...`` with an ``=`` in the LHS
        # portion before the first ``=``. That covers both simple
        # assignments and method calls like ``.resize(...)``.
        if "=" in stripped and "." in stripped.split("=", 1)[0]:
            out.append(_guarded_op(stripped, eid, kind))
            continue
        # Method calls without assignment (e.g. ``{var}.resize(w, h);``).
        # They still throw on leaf node types and cascade the same way.
        if stripped.startswith(tuple("abcdefghijklmnopqrstuvwxyz_")) and \
                "(" in stripped and "." in stripped.split("(", 1)[0]:
            out.append(_guarded_op(stripped, eid, kind))
            continue
        out.append(raw)
    return out


def _emit_phase1(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[int, str],
    spec_key_map: dict[int, str],
    original_name_map: dict[int, str],
    *,
    nid_map: dict[int, int],
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    spec_elements: Optional[dict[str, dict[str, Any]]] = None,
    spec_tokens: Optional[dict[str, Any]] = None,
    node_id_vars: Optional[dict[str, str]] = None,
    descendant_visibility_resolver: Optional[
        dict[str, dict[str, str]]
    ] = None,
    deferred_groups: Optional[dict[int, dict[str, Any]]] = None,
    deferred_bool_ops: Optional[dict[int, dict[str, Any]]] = None,
) -> tuple[list[str], bool, list[tuple[str, str, str]], list[str], set[int]]:
    """Phase 1 — materialize nodes + set intrinsic properties.

    Returns `(lines, uses_placeholder, token_refs, override_deferred,
    absorbed_node_ids)` where:

    - `uses_placeholder` — at least one node emitted a Mode 1
      createInstance that may fall back to
      `_missingComponentPlaceholder`. The preamble uses this to
      decide whether to inject the placeholder helper block.
    - `token_refs` — `(eid, property, token_name)` triples for Phase B
      rebind.
    - `override_deferred` — JS lines from `_emit_override_tree` that
      must execute after `appendChild` (e.g. ``layoutSizing`` on swap
      targets; see `_emit_override_op` for the list). Forwarded into
      Phase 3 by the caller.
    - `absorbed_node_ids` — P3a (N1 fix): `id(node)` for every node
      that lives inside a Mode-1 instance subtree, INCLUDING the
      Mode-1 head itself. Phase 2 + Phase 3 must skip nodes whose
      PARENT is in this set — i.e. descendants of Mode-1 heads.
      Figma's Plugin API rejects appendChild and most property
      writes on nodes inside an INSTANCE subtree ("Cannot move node
      into INSTANCE" / "object is not extensible"). The Mode-1 head
      ITSELF still needs Phase 2 appendChild (into its own parent —
      the screen frame) and Phase 3 resize/position (top-level
      instances carry explicit IR layout); Phase 1's `mode1_node_ids`
      contains the head only so it acts as the absorption-root marker
      for the parent-in-set check downstream. The OLD path
      (dd/renderers/figma.py:1757) used parent-in-set with the same
      semantics; Phase E §7 screen 24 surfaced 130+ append_child_failed
      errors when the AST renderer port lost the skip-set entirely
      (P3a addressed that), and the Phase E re-run regression
      (2026-04-26) caught a follow-up where Phase 2/3 was checking
      `id(node)` instead of `id(parent)`, dropping the head's own
      ops. The contract is now: `mode1_node_ids` + `skipped_node_ids`
      together identify every node inside an instance subtree; the
      union is exposed as `absorbed_node_ids`; Phase 2/3 skip when
      the PARENT is in that set.

    F13c: `deferred_groups` (caller-supplied dict) is populated with
    {id(group_node): {"spec_key", "element", "var"}} for every GROUP
    node encountered. Phase 1 skips creation/prop emission for these;
    Phase 2 calls `figma.group([direct_children_vars], grandparent_var)`
    bottom-up; Phase 3 sets position. The deferral exists because
    Figma's Plugin API has no `createGroup()` — groups can only be
    constructed by wrapping existing nodes via `figma.group()`, which
    requires the children to exist FIRST. Without this path, the
    AST renderer silently coerced GROUP→FRAME via _TYPE_TO_CREATE_CALL
    fallback, and the children's stored x/y (in group-PARENT space per
    Plugin API convention) got reinterpreted as group-local-space,
    offsetting them by the group's own (x, y). User-visible: HGB
    Customer Complete Info Tablet's logo (Group 4746) rendered with
    its vector children at +19px outside the parent Top Nav frame.
    """
    spec_elements = spec_elements or {}
    spec_tokens = spec_tokens or {}
    node_id_vars = node_id_vars or {}
    if deferred_groups is None:
        deferred_groups = {}
    if deferred_bool_ops is None:
        deferred_bool_ops = {}
    lines: list[str] = []
    lines.append(
        "// Phase 1: Materialize — create nodes, set intrinsic properties"
    )
    uses_placeholder = False
    token_refs: list[tuple[str, str, str]] = []
    override_deferred: list[str] = []
    # P3a (N1 fix): Mode-1 instance descendants must be SKIPPED in
    # Phase 1 (no createX) and Phase 2 (no appendChild — Figma's
    # Plugin API rejects "Cannot move node into INSTANCE") and
    # Phase 3 (no resize / no position). The OLD path
    # (dd/renderers/figma.py:1267, 1306, 1479, 1757) had this
    # contract — the AST renderer port lost it. Phase E §7 screen 24
    # produced 130+ append_child_failed errors as a result.
    #
    # Codex (2026-04-25): key on `id(node)` per the AST renderer's
    # identity contract. Two sets so we can distinguish "this IS a
    # Mode-1 instance" (still emitted) from "this is absorbed by a
    # Mode-1 ancestor" (skipped). Combined `absorbed_node_ids`
    # threaded into Phase 2 + Phase 3 by the caller via the Phase 1
    # return tuple.
    #
    # Caveat (Codex sharpest catch): `mode1_ok` from
    # `_emit_mode1_create` means "Mode-1 IIFE was emitted" not
    # "real createInstance succeeded." The IIFE may degrade to
    # `_missingComponentPlaceholder()` at runtime if the source/master
    # is unavailable. Skipping descendants matches OLD-path behavior:
    # placeholder render gets no children. Alternative (conditionally
    # append children at runtime when var is the placeholder) is a
    # bigger design choice deferred to a future cycle.
    mode1_node_ids: set[int] = set()
    skipped_node_ids: set[int] = set()

    for node, parent in walk:
        eid = node.head.eid
        # P3a: skip descendants of any node already absorbed by Mode-1.
        # `parent` may be None for the root; parent's id-in-set is the
        # transitive descend signal.
        if parent is not None and (
            id(parent) in mode1_node_ids
            or id(parent) in skipped_node_ids
        ):
            skipped_node_ids.add(id(node))
            continue
        var = var_map[id(node)]
        head_kind = node.head.head_kind
        etype = node.head.type_or_path if head_kind == "type" else ""
        # Phase E residual #1 fix (2026-04-26): L3 markup uses
        # hyphenated type names (`boolean-operation`); the renderer's
        # dict lookups (`_TYPE_TO_CREATE_CALL`, `_FIGMA_NODE_TYPE`)
        # use underscore form. Without this normalization, etype
        # `boolean-operation` falls through `_TYPE_TO_CREATE_CALL.get`
        # to `figma.createFrame()`, then `n.booleanOperation = "UNION"`
        # prop write fails on the frame fallback. Codex 2026-04-26
        # (gpt-5.5) traced the path: ir.py emits underscore →
        # compress_l3.py:846 hyphenates for L3 grammar →
        # render_figma_ast lookups expect underscore. Sonnet
        # subagent verified all etype consumers expect underscore
        # form and the fix is single-entry / no double-replace risk.
        # `boolean-operation` is the only hyphenated L3 type today
        # (markup_l3.py grammar §2.7); future hyphenated types are
        # auto-handled.
        etype = etype.replace("-", "_") if isinstance(etype, str) else ""

        raw_visual: dict[str, Any] = {}
        if db_visuals is not None:
            nid = nid_map.get(id(node))
            if nid is not None:
                raw_visual = db_visuals.get(nid, {}) or {}

        spec_key = spec_key_map.get(id(node), eid)
        # Path 1 demo fix: merge AST-head properties onto the spec-based
        # element so (a) new nodes from append/insert/replace get emitted
        # with their layout/padding/fill/etc. — they have no spec entry
        # OR nid_map entry — and (b) set-on-original nodes pick up
        # head-overlaid properties too (e.g. `set @existing-btn fill=...`
        # would have been silently dropped previously). Precedence:
        # head.properties → spec["elements"][key] → defaults. db_visuals
        # stays untouched on its own path at lines 648-651 (the
        # build_visual_from_db render-tree shape is richer than the
        # sparse IR visual and must not be replaced). See
        # dd/ast_to_element.py for the resolver.
        from dd.ast_to_element import resolve_element
        element = resolve_element(
            node=node,
            spec_elements=spec_elements if spec_elements else {},
            spec_key=spec_key,
            db_visuals={},
            nid=None,
            nid_map={},
        )

        component_key = raw_visual.get("component_key")
        component_figma_id = raw_visual.get("component_figma_id")
        instance_figma_node_id = raw_visual.get("figma_node_id")
        is_db_instance = raw_visual.get("node_type") == "INSTANCE"
        is_text = etype in _TEXT_TYPES

        use_mode1 = (
            head_kind == "comp-ref"
            or (
                (component_key or component_figma_id
                 or (is_db_instance and instance_figma_node_id))
                and not is_text
            )
        )

        # P5 (forensic-audit-2 finding 1): when use_mode1 is True but
        # the inner identifier gate fails, we silently fall through to
        # createFrame. The is_db_instance branch below covers part of
        # this case via degraded_to_mode2, but only when is_db_instance
        # is True. The case where head_kind=="comp-ref" AND
        # is_db_instance=False AND identifiers are missing was a fully
        # silent fall-through pre-fix — no __errors push, no
        # diagnostic, verifier blind.
        #
        # Codex 2026-04-26 (gpt-5.5 high reasoning): keep
        # degraded_to_mode2 for intentional fallback (is_db_instance
        # path); use mode1_dispatch_failed for the precondition-
        # failure variant where comp-ref markup expected Mode 1 but
        # couldn't get there because of missing identity data.
        if (
            use_mode1
            and not (
                component_figma_id or instance_figma_node_id or component_key
            )
            and not is_db_instance
        ):
            err_eid = spec_key_map.get(id(node), eid)
            eid_lit = _escape_js(err_eid)
            reason_parts = []
            if head_kind == "comp-ref":
                reason_parts.append("head=comp-ref")
            if not component_key:
                reason_parts.append("no component_key")
            if not component_figma_id:
                reason_parts.append("no component_figma_id")
            if not instance_figma_node_id:
                reason_parts.append("no instance_figma_node_id")
            reason = _escape_js(", ".join(reason_parts) or "unknown")
            lines.append(
                f'__errors.push({{eid:"{eid_lit}", '
                f'kind:"mode1_dispatch_failed", reason:"{reason}"}});'
            )

        if use_mode1 and (
            component_figma_id or instance_figma_node_id or component_key
        ):
            emitted, mode1_ok = _emit_mode1_create(
                var, node, spec_key_map, original_name_map,
                component_figma_id, instance_figma_node_id,
                raw_visual, element,
                deferred_lines=override_deferred,
                node_id_vars=node_id_vars,
                descendant_visibility_resolver=(
                    descendant_visibility_resolver
                ),
                component_key=component_key,
            )
            if mode1_ok:
                # Guard Mode 1 post-create prop writes. The first
                # emitted line is the async-IIFE create (``const
                # {var} = await (async () => {{...}})();``) — that
                # stays naked because the variable declaration is
                # load-bearing, and its internal try/catch already
                # routes missing-component failures into ``__errors``.
                # Every subsequent ``{var}.name = ...`` / rotation /
                # opacity / visible write is what this guard covers —
                # before, a throw there cascaded into the outer
                # end-wrapper ``render_thrown`` and skipped the root
                # page-attach. Twin of the Mode 2 guard below.
                mode1_err_eid = spec_key_map.get(id(node), eid)
                if emitted:
                    lines.append(emitted[0])
                    lines.extend(_guard_naked_prop_lines(
                        emitted[1:], mode1_err_eid, "phase1_mode1_prop_failed",
                    ))
                uses_placeholder = True
                m_key = spec_key_map.get(id(node), eid)
                lines.append(
                    f'M["{_escape_js(m_key)}"] = {var}.id;'
                )
                lines.append("")
                # P3a: mark this node as a Mode-1 absorber. Descendants
                # encountered later in the walk will be skipped via
                # the parent-check at the top of the loop. Phase 2
                # appendChild and Phase 3 prop-writes also skip them.
                mode1_node_ids.add(id(node))
                continue

        if is_db_instance:
            err_eid = spec_key_map.get(id(node), eid)
            eid_lit = _escape_js(err_eid)
            reason_parts: list[str] = []
            if not component_key:
                reason_parts.append("no component_key")
            if not component_figma_id:
                reason_parts.append("no component_figma_id")
            if not instance_figma_node_id:
                reason_parts.append("no instance_figma_node_id")
            reason = _escape_js(", ".join(reason_parts) or "unknown")
            lines.append(
                f'__errors.push({{eid:"{eid_lit}", '
                f'kind:"degraded_to_mode2", reason:"{reason}"}});'
            )

        # F13c: GROUP nodes are deferred. Skip Phase 1 entirely (no
        # create call, no name, no visual, no layout, no M assign).
        # Phase 2 calls `figma.group([direct_children_vars],
        # grandparent_var)` AFTER all descendants are created, then
        # emits name + M assign. Phase 3 sets x, y. The
        # deferred_groups dict is the cross-phase carrier.
        # Per Codex F13c spec: do NOT replicate the OLD path's
        # "register descendant in EVERY ancestor's children_vars" —
        # that's suspicious for nested groups. Use direct-AST-children
        # only; bottom-up processing in Phase 2 ensures inner groups
        # exist as vars by the time outer groups call figma.group().
        if etype == "group":
            deferred_groups[id(node)] = {
                "spec_key": spec_key_map.get(id(node), eid),
                "element": element,
                "var": var,
                "node": node,
                "original_name": original_name_map.get(id(node)) or eid,
            }
            continue

        # Phase E #3 (2026-04-26): BOOLEAN_OPERATION nodes use the
        # F13c deferred pattern. Plugin API requires children to
        # exist BEFORE figma.union/subtract/intersect/exclude can
        # wrap them — so Phase 1 skips emission entirely (no create
        # call, no name, no visual, no M assign). The bool_op's
        # children still emit normally in Phase 1 as their own
        # primitives. Phase 2 walks deferred_bool_ops bottom-up
        # AFTER appendChild loop, calling figma.<op>(children, parent)
        # which creates the bool node + auto-adopts the children.
        # Phase 3 then applies regular resize/position/constraints
        # (post-materialization the bool node IS extensible —
        # verified empirically, see test_boolean_operation_dispatch.py).
        # Codex 2026-04-26 (gpt-5.5 high reasoning) review: 9
        # specific concerns addressed in this implementation —
        # symbolic var names (already true), z-order preservation
        # via insertChild (mirror F13c), whitelist operation mapping
        # (no .lower()), consistent fallback metadata, etc.
        if etype == "boolean_operation":
            # Read the operation type from raw_visual (db_visuals).
            # Whitelist mapping per Codex critique — silent fallback
            # to .lower() makes corrupted IR hard to diagnose.
            raw_op = raw_visual.get("boolean_operation") if raw_visual else None
            op_map = {
                "UNION": "union",
                "SUBTRACT": "subtract",
                "INTERSECT": "intersect",
                "EXCLUDE": "exclude",
            }
            operation_js = op_map.get(raw_op, "union")
            deferred_bool_ops[id(node)] = {
                "spec_key": spec_key_map.get(id(node), eid),
                "element": element,
                "var": var,
                "node": node,
                "original_name": original_name_map.get(id(node)) or eid,
                "operation_js": operation_js,
                "raw_op": raw_op,
                "raw_visual": raw_visual,
            }
            continue

        # Non-deferred path: emit the create call and per-node
        # prop writes. (Bool ops took the deferred path above and
        # already `continue`d; groups did the same higher up.)
        create_call = _TYPE_TO_CREATE_CALL.get(etype, "figma.createFrame()")
        lines.append(f"const {var} = {create_call};")

        # Mode 2 post-create prop-write boundary. Every naked
        # ``{var}.foo = ...`` assignment emitted below goes into
        # ``node_ops`` instead of ``lines``; at the end of the
        # per-node block we pass ``node_ops`` through
        # ``_guard_naked_prop_lines`` and extend ``lines``. Without
        # this, one throw inside a Phase 1 prop write cascaded
        # through the rest of Phase 1 AND Phase 2's root
        # ``_page.appendChild(root_var)`` — stranding the created
        # nodes as orphans on ``figma.currentPage``. Twin of the
        # Phase 2 per-op guard at lines 1283-1289.
        node_ops: list[str] = []

        original_name = original_name_map.get(id(node)) or eid
        name_js = _escape_js(original_name)
        node_ops.append(f'{var}.name = "{name_js}";')

        if element:
            # Build visual from raw DB data — matches baseline Phase 1
            # line ~1314. `element.get("visual")` is the sparse IR
            # visual that build_composition_spec produces; the DB
            # `raw_visual` (from query_screen_visuals) carries the
            # full rendered-tree shape that baseline consumes via
            # build_visual_from_db. Using the sparse IR visual at
            # this call site was the root of my strokeWeight /
            # cornerRadius / effects ratio gap.
            if raw_visual:
                visual = build_visual_from_db(raw_visual)
            else:
                visual = dict(element.get("visual") or {})
            layout = element.get("layout") or {}
            style = element.get("style") or {}
            spec_key_for_emit = spec_key_map.get(id(node), eid)

            # Overlay IR-style fill / stroke / cornerRadius when
            # `visual` is empty (synthetic IR elements without DB
            # node_ids). Matches baseline figma.py:1327–1343.
            ir_fill_ref = style.get("fill")
            if ir_fill_ref and not visual.get("fills"):
                visual["fills"] = [{"type": "solid", "color": ir_fill_ref}]
            if not is_text:
                ir_stroke_ref = style.get("stroke")
                if ir_stroke_ref and not visual.get("strokes"):
                    visual["strokes"] = [
                        {"type": "solid", "color": ir_stroke_ref},
                    ]
                ir_radius_ref = style.get("radius")
                if (
                    ir_radius_ref is not None
                    and "cornerRadius" not in visual
                    and isinstance(ir_radius_ref, (int, float))
                ):
                    visual["cornerRadius"] = ir_radius_ref

            if visual:
                visual_lines, visual_refs = _emit_visual(
                    var, spec_key_for_emit, visual, spec_tokens,
                    node_type=_FIGMA_NODE_TYPE.get(etype),
                )
                node_ops.extend(visual_lines)
                # `_emit_visual` returns pre-built ``(eid, prop,
                # token_name)`` 3-tuples keyed on the eid it received
                # (== ``spec_key_for_emit``). Pass through — rebuilding
                # here was a shape-mismatch bug that happened to be
                # dormant on the Dank corpus (DB-extracted specs have
                # empty ``_token_refs`` maps) and only surfaced on the
                # synthetic compose.py path.
                token_refs.extend(visual_refs)
            elif etype == "frame":
                node_ops.append(f"{var}.fills = [];")
                node_ops.append(f"{var}.clipsContent = false;")
            elif etype in ("rectangle", "ellipse", "vector", "boolean_operation"):
                node_ops.append(f"{var}.fills = [];")

            text_auto_resize = None
            if is_text:
                text_auto_resize = raw_visual.get("text_auto_resize")

            if layout and not is_text:
                layout_lines, layout_refs = _emit_layout(
                    var, spec_key_for_emit, layout, spec_tokens,
                    text_auto_resize=text_auto_resize, etype=etype,
                )
                node_ops.extend(layout_lines)
                token_refs.extend(layout_refs)

            if is_text:
                db_font = raw_visual.get("font") or raw_visual
                _emit_text_props(
                    var, element, style, spec_tokens, node_ops,
                    db_font=db_font, eid=spec_key_for_emit,
                )
            if etype in ("vector", "boolean_operation") and raw_visual:
                _emit_vector_paths(var, raw_visual, node_ops)

            # Clear default fills on non-text nodes when the DB row
            # has no fills — matches baseline figma.py:1401–1402. Any
            # `figma.createRectangle / createVector / createFrame`
            # ships with a default white fill, which has to be cleared
            # explicitly when the DB says the node is unfilled.
            if not is_text and not visual.get("fills"):
                node_ops.append(f"{var}.fills = [];")

            # Clear default stroke on vector / line — `createVector()`
            # and `createLine()` ship with a 1px black stroke that
            # must be cleared when the DB row has no strokes. Matches
            # baseline figma.py:1404–1413.
            if etype in ("vector", "line") and not visual.get("strokes"):
                node_ops.append(f"{var}.strokes = [];")

            # Clear default `clipsContent=true` on frames when the DB
            # value is NULL / falsy. Matches baseline
            # figma.py:1424–1428 — `createFrame()` ships with
            # clipsContent=true and that value clobbers overflow visual
            # when the DB intends no clipping.
            if (
                etype == "frame"
                and not visual.get("clipsContent")
            ):
                node_ops.append(f"{var}.clipsContent = false;")
        else:
            if etype == "frame":
                node_ops.append(f"{var}.fills = [];")
                node_ops.append(f"{var}.clipsContent = false;")
            elif etype in ("rectangle", "ellipse", "vector", "boolean_operation"):
                node_ops.append(f"{var}.fills = [];")
            elif etype in _TEXT_TYPES:
                font_js = (
                    f'{{family: "{_DEFAULT_TEXT_FONT_FAMILY}", '
                    f'style: "{_DEFAULT_TEXT_FONT_STYLE}"}}'
                )
                err_eid = spec_key_map.get(id(node), eid)
                err_eid_js = _escape_js(err_eid)
                node_ops.append(
                    f"try {{ {var}.fontName = {font_js}; }} "
                    f"catch (__e) {{ __errors.push({{eid:\"{err_eid_js}\", "
                    f"kind:\"text_set_failed\", "
                    f"error: String(__e && __e.message || __e)}}); }}"
                )

        # AST-property-driven `visible=false` emission — the first
        # element-level property to migrate off the transitional
        # `_spec_elements` shim onto direct AST reads. Read from the
        # L3 AST, not the dict-IR shim, so every backend walker
        # (Figma, React, SwiftUI, Flutter) consumes the same property
        # and emits its native "hidden" form: Figma
        # `node.visible = false`; React `style={{display: 'none'}}`;
        # SwiftUI `.isHidden(true)`; Flutter
        # `Visibility(visible: false)`. Missing this emission was the
        # root cause of the visual-artifact cluster (Issues #1, #3,
        # #4, #6, #7) where hidden overlays / modals / conditional
        # content rendered on top of visible content across ~every
        # Dank screen — a 85-node-per-screen gap on ipad-12.9-69.
        # Applies to both shim and no-shim paths (reads AST only).
        if _ast_prop_is_false(node, "visible"):
            node_ops.append(f"{var}.visible = false;")

        # Guard every Mode 2 per-op prop write accumulated in this
        # iteration, then splice into `lines`. See the ``node_ops``
        # declaration above for the rationale (Phase 2 root-attach
        # cascade).
        guard_err_eid = spec_key_map.get(id(node), eid)
        lines.extend(_guard_naked_prop_lines(
            node_ops, guard_err_eid, "phase1_mode2_prop_failed",
        ))

        m_key = spec_key_map.get(id(node), eid)
        lines.append(f'M["{_escape_js(m_key)}"] = {var}.id;')
        lines.append("")

    lines.append(f"__perf.phase1_node_count = {len(walk)};")
    lines.append('__mark("phase1_done");')

    # P3a: combined "this node is inside a Mode-1 subtree" set.
    # Phase 2/3 use this to skip appendChild + property writes on
    # nodes the instance subtree has absorbed.
    absorbed_node_ids = mode1_node_ids | skipped_node_ids
    return lines, uses_placeholder, token_refs, override_deferred, absorbed_node_ids


_FIGMA_NODE_TYPE: dict[str, str] = {
    "frame": "FRAME",
    "rectangle": "RECTANGLE",
    "ellipse": "ELLIPSE",
    "line": "LINE",
    "vector": "VECTOR",
    "boolean_operation": "BOOLEAN_OPERATION",
    "text": "TEXT",
    "heading": "TEXT",
    "link": "TEXT",
}


def _emit_mode1_create(
    var: str,
    node: Node,
    spec_key_map: dict[int, str],
    original_name_map: dict[int, str],
    component_figma_id: Optional[str],
    instance_figma_node_id: Optional[str],
    raw_visual: dict[str, Any],
    element: dict[str, Any],
    *,
    deferred_lines: list[str],
    node_id_vars: Optional[dict[str, str]] = None,
    descendant_visibility_resolver: Optional[
        dict[str, dict[str, str]]
    ] = None,
    component_key: Optional[str] = None,
) -> tuple[list[str], bool]:
    """Emit the Mode 1 createInstance block for one node.

    Returns `(lines, ok)`. `ok=False` means no usable source
    identifier — caller falls through to Mode 2 (createFrame).

    Mirrors `generate_figma_script` lines ~1112–1161: the async IIFE
    wraps getNodeByIdAsync (or getMainComponentAsync for instance
    refs) and calls createInstance, with a
    `_missingComponentPlaceholder` fallback on any failure mode.

    `element` is the shim-provided CompositionSpec element dict (may
    be empty when called outside the shim path). When present, its
    `layout.sizing.widthPixels`/`heightPixels` supply the placeholder
    dimensions — matching baseline lines 1123–1127.

    `deferred_lines` accumulates override-tree ops that need to run
    after Phase 2 appendChild (e.g. ``layoutSizing`` on swap targets).
    Caller threads these into Phase 3.

    Resolution precedence — preserves the existing fallback chain
    (which the renderer's gate already mirrors) and adds the
    component-key path that was previously missing:

      1. ``component_figma_id`` → ``getNodeByIdAsync`` → ``createInstance``
      2. ``instance_figma_node_id`` → ``getNodeByIdAsync`` →
         ``getMainComponentAsync`` → ``createInstance`` (handles
         unpublished/local components and INSTANCE rows whose master
         id we don't have cached)
      3. ``component_key`` (F1) → ``importComponentByKeyAsync`` →
         ``createInstance``. Required for Mode-3 prompt composition
         where ``build_template_visuals`` resolves a real component_key
         from ``component_templates`` but ``component_key_registry``
         hasn't yet been populated with figma_node_ids (fresh DBs).
         Without this branch, every Mode-3 element with a key but
         no resolved figma_id silently fell through to ``createFrame``.
    """
    lines: list[str] = []
    eid = node.head.eid
    err_eid = spec_key_map.get(id(node), eid)
    eid_lit = _escape_js(err_eid)

    name_for_placeholder = original_name_map.get(id(node)) or eid
    name_lit = _escape_js(name_for_placeholder)
    sizing = (element.get("layout") or {}).get("sizing") or {}
    pw = sizing.get("widthPixels") or sizing.get("width")
    ph = sizing.get("heightPixels") or sizing.get("height")
    pw_js = pw if isinstance(pw, (int, float)) else 24
    ph_js = ph if isinstance(ph, (int, float)) else 24
    fallback_js = (
        f'_missingComponentPlaceholder("{name_lit}", '
        f'{pw_js}, {ph_js}, "{eid_lit}")'
    )

    node_id_vars = node_id_vars or {}

    if component_figma_id:
        id_lit = _escape_js(component_figma_id)
        node_expr = node_id_vars.get(
            component_figma_id,
            f'await figma.getNodeByIdAsync("{id_lit}")',
        )
        lines.append(
            f'const {var} = await (async () => {{ '
            f'const __src = {node_expr}; '
            f'if (!__src) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"missing_component_node", id:"{id_lit}"}}); '
            f'return {fallback_js}; }} '
            f'try {{ return __src.createInstance(); }} '
            f'catch (__e) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"create_instance_failed", id:"{id_lit}", '
            f'error: String(__e && __e.message || __e)}}); '
            f'return {fallback_js}; }} '
            f'}})();'
        )
    elif instance_figma_node_id:
        id_lit = _escape_js(instance_figma_node_id)
        lines.append(
            f'const {var} = await (async () => {{ '
            f'const __src = await figma.getNodeByIdAsync("{id_lit}"); '
            f'if (!__src) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"missing_instance_node", id:"{id_lit}"}}); '
            f'return {fallback_js}; }} '
            f'if (typeof __src.getMainComponentAsync !== "function") '
            f'{{ __errors.push({{eid:"{eid_lit}", kind:"not_an_instance", '
            f'id:"{id_lit}"}}); return {fallback_js}; }} '
            f'const __master = await __src.getMainComponentAsync(); '
            f'if (!__master) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"no_main_component", id:"{id_lit}"}}); '
            f'return {fallback_js}; }} '
            f'try {{ return __master.createInstance(); }} '
            f'catch (__e) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"create_instance_failed", id:"{id_lit}", '
            f'error: String(__e && __e.message || __e)}}); '
            f'return {fallback_js}; }} '
            f'}})();'
        )
    elif component_key:
        # F1: component-key-only path. Used by Mode-3 prompt
        # composition when build_template_visuals resolves a real
        # component_key from component_templates but the CKR row's
        # figma_node_id is empty (fresh DBs). Same null-safety
        # contract as the other branches: a missing key surfaces in
        # __errors and degrades to the wireframe placeholder instead
        # of throwing or silently rendering as a generic frame.
        # `_emit_composition_children` already uses this exact API
        # (`importComponentByKeyAsync`) for keyed children — adding it
        # here makes the main element emission consistent.
        id_lit = _escape_js(component_key)
        lines.append(
            f'const {var} = await (async () => {{ '
            f'try {{ '
            f'const __master = await figma.importComponentByKeyAsync("{id_lit}"); '
            f'if (!__master) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"missing_component_key", id:"{id_lit}"}}); '
            f'return {fallback_js}; }} '
            f'return __master.createInstance(); '
            f'}} catch (__e) {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"import_component_failed", id:"{id_lit}", '
            f'error: String(__e && __e.message || __e)}}); '
            f'return {fallback_js}; }} '
            f'}})();'
        )
    else:
        return [], False

    original_name = original_name_map.get(id(node)) or eid
    lines.append(f'{var}.name = "{_escape_js(original_name)}";')

    props = element.get("props") or {}
    text_override = props.get("text", "")
    if text_override:
        text_target = props.get("text_target")
        find_expr = _build_text_finder(var, text_target)
        # F11.1: try/catch around the load+write pair (see
        # dd/renderers/figma.py characters branch for context). When the
        # text node's current fontName is unavailable in this Figma
        # session (paid commercial font, library-imported font), the
        # load rejects and the next-line write throws — without the
        # catch the throw aborts Phase 1.
        # F12: include node_id + name on the catch so per-eid
        # attribution survives.
        lines.append(
            f'{{ const _t = {find_expr}; '
            f'if (_t) {{ try {{ '
            f'await figma.loadFontAsync(_t.fontName); '
            f'_t.characters = "{_escape_js(text_override)}"; '
            f'}} catch (__e) {{ '
            f'__errors.push({{kind:"text_set_failed", '
            f'property:"text", '
            f'node_id:_t.id, name:_t.name, '
            f'error: String(__e && __e.message || __e)}}); '
            f'}} }} }}'
        )

    subtitle_override = props.get("subtitle", "")
    if subtitle_override:
        sub_find = _build_text_finder(var, None, subtitle=True)
        # F11.1 + F12: same guard + per-eid attribution for subtitle.
        lines.append(
            f'{{ const _t = {sub_find}; '
            f'if (_t) {{ try {{ '
            f'await figma.loadFontAsync(_t.fontName); '
            f'_t.characters = "{_escape_js(subtitle_override)}"; '
            f'}} catch (__e) {{ '
            f'__errors.push({{kind:"text_set_failed", '
            f'property:"subtitle", '
            f'node_id:_t.id, name:_t.name, '
            f'error: String(__e && __e.message || __e)}}); '
            f'}} }} }}'
        )

    # PR-1: the legacy `hidden_children` name-based emitter was
    # deleted here. Backend-neutral `.visible=bool` PathOverrides on
    # the CompRef head (populated by the unified resolver in
    # compress_l3._fetch_descendant_visibility_overrides) supply the
    # same descendant hides via the Stage-4 id-based path below.

    override_tree = raw_visual.get("override_tree")
    if override_tree:
        _emit_override_tree(
            override_tree, var, node_id_vars, lines,
            deferred_lines=deferred_lines,
        )

    # PR-2 Stage 4: markup-native descendant visibility PathOverrides.
    # The Figma renderer reads the `descendant_visibility_resolver`
    # side-car map (built by the compressor) to translate each
    # `<eid>.visible` PathOverride into a stable `id.endsWith(";<fig_id>")`
    # findOne call — which sidesteps the name-ambiguity bug that
    # `findOne(name)` runs into on masters with multiple same-name
    # descendants. The markup path itself never carries the Figma id;
    # the resolver IS the Figma adapter. An HTML / SwiftUI renderer
    # would ignore this map and consume its own backend-appropriate
    # resolver (slot-schema lookup, null-slot emission, etc).
    #
    # Resolver keys match the compressor's `eid_key` (CompositionSpec
    # element key, e.g. `button-22`) — the AST node's own
    # `node.head.eid` is the sanitized original-name form (e.g.
    # `button-white`). Look up via `spec_key_map[id(node)]` so the
    # compressor and renderer agree on the per-instance bucket.
    if descendant_visibility_resolver is not None:
        _emit_visibility_path_overrides(
            node=node,
            var=var,
            spec_key_map=spec_key_map,
            descendant_visibility_resolver=descendant_visibility_resolver,
            lines=lines,
        )

    # Scalar rotation only when AST carries no transform primitives
    # (``rotation`` / ``mirror``). When either is present, Phase 3
    # emits a full ``relativeTransform`` matrix that subsumes both
    # rotation and translation; emitting scalar ``rotation`` here
    # would race the matrix and leave an ambiguous pivot.
    #
    # A1.2 (Codex 5.5): rotation NOT gated on _overrides — it has
    # its own AST-transform-conflict guard and isn't in
    # _INSTANCE_OVERRIDE_TO_FIGMA_NAME. Keep current heuristic.
    ast_rotation = _ast_prop_py(node, "rotation")
    ast_mirror = _ast_prop_py(node, "mirror")
    has_ast_transform = (
        isinstance(ast_rotation, (int, float)) and ast_rotation != 0
    ) or isinstance(ast_mirror, str)
    if not has_ast_transform:
        inst_rotation = raw_visual.get("rotation")
        if isinstance(inst_rotation, (int, float)) and inst_rotation != 0:
            lines.append(
                f"{var}.rotation = {-math.degrees(inst_rotation)};"
            )

    # A1.2 (Backlog #1, provenance plan): per-property emission
    # gating for visual props on Mode-1 INSTANCE heads. Pre-A1.2
    # the renderer "delegated to master" for fills/strokes/etc. AND
    # used a heuristic gate for opacity (`< 1.0` — the silent
    # default leak the audit flagged). With _overrides on the IR
    # (A1.1), per-prop emission is now correctly driven by
    # extraction-time provenance.
    #
    # Codex 5.5 (gpt-5.5 high reasoning, 2026-04-26):
    # "Mode 1 delegates to the master only for non-overridden
    # props. If _overrides contains fills, strokes, strokeWeight,
    # cornerRadius, blendMode, clipsContent, etc., Mode 1 should
    # emit those onto the instance head after createInstance().
    # Build a sparse override visual and pass through _emit_visual."
    overrides_list = element.get("_overrides")
    if overrides_list:
        # Build sparse visual: only the props in _overrides, sourced
        # from raw_visual via build_visual_from_db. The
        # default-skip in build_visual_from_db can drop overridden
        # props that happen to match the default (e.g. opacity=1.0
        # explicitly overridden), so we patch those back below.
        from dd.visual import build_visual_from_db

        full_visual = build_visual_from_db(raw_visual)
        # A1.2 gating set: visual props that get emitted on Mode-1
        # only when in _overrides. Excludes:
        # - rotation (own AST-conflict guard above)
        # - visible (PathOverride path; not in this set)
        sparse_visual: dict[str, Any] = {}
        for prop_name in overrides_list:
            if prop_name in {"rotation", "visible"}:
                continue
            if prop_name in full_visual:
                sparse_visual[prop_name] = full_visual[prop_name]
            elif prop_name == "opacity":
                # Codex 5.5 caveat: opacity=1.0 explicit override
                # gets dropped by build_visual_from_db's default-skip.
                # Patch back from raw_visual.
                inst_opacity = raw_visual.get("opacity")
                if isinstance(inst_opacity, (int, float)):
                    sparse_visual["opacity"] = inst_opacity

        if sparse_visual:
            visual_lines, visual_refs = _emit_visual(
                var, err_eid, sparse_visual, {},
                node_type="INSTANCE",
            )
            for vl in visual_lines:
                # Wrap each in try/catch — Mode-1 instance prop
                # writes can be rejected by Figma for various
                # reasons (read-only on certain instance subtrees,
                # type mismatch, etc.). Same kind as the existing
                # phase1_mode1_prop_failed family.
                lines.append(_guarded_op(
                    vl, err_eid, "phase1_mode1_prop_failed",
                ))
    elif overrides_list is None:
        # A1.2: legacy IR (no _overrides field at all) preserves
        # the historical opacity heuristic so un-migrated specs
        # don't silently regress emission. Codex 5.5 framing:
        # "Missing provenance defaults to snapshot" applies on the
        # VERIFIER side (under-flag is safe). On the RENDERER side,
        # missing provenance means "use the prior heuristic" because
        # not emitting at all could remove a previously-rendered
        # opacity value. New specs should always carry _overrides.
        inst_opacity = raw_visual.get("opacity")
        if (
            isinstance(inst_opacity, (int, float))
            and inst_opacity < 1.0
        ):
            lines.append(f"{var}.opacity = {inst_opacity};")
    # else: overrides_list == [] (explicit empty) → emit nothing,
    # snapshot semantics. The Mode-1 master defaults stand.

    if element.get("visible") is False:
        lines.append(f"{var}.visible = false;")

    return lines, True


def _emit_visibility_path_overrides(
    *,
    node: Node,
    var: str,
    spec_key_map: dict[int, str],
    descendant_visibility_resolver: dict[str, dict[str, str]],
    lines: list[str],
) -> None:
    """Emit ``.visible`` flips for descendant PathOverrides on this
    instance head as a single batched lookup.

    Codex Option B (2026-04-24): collect all ``.visible`` overrides for
    THIS instance into one lookup pass. Open ONE
    ``skipInvisibleInstanceChildren = false`` toggle window, do ONE
    ``findAll`` walk that populates a ``Set``-keyed ``Map`` from
    ``fig_id`` → node, then K straight-line ``map.get(...).visible =
    ...`` assignments, then restore the flag in ``finally``. This
    replaces the previous shape that opened a fresh toggle + ran a
    fresh ``findOne`` subtree walk per override — measured at
    ~59s/instance for heavy masters (e.g. ``button/large/translucent``)
    and the root cause of the 300s render timeout on demo-2's
    screen-333 brief.

    The toggle is still scoped per instance head (not per render run)
    so the global perf flag is back on as soon as this instance's
    overrides are applied. The walk itself is synchronous (no
    ``await``) — required because ``skipInvisibleInstanceChildren`` is
    global state and any awaited boundary inside the try would let
    other code observe the flipped flag.

    Without the toggle the global perf flag set in the preamble (line
    148) silently makes ``findAll`` skip every hidden subtree, the
    unhide never runs, and the rendered instance shows only the master
    defaults — confirmed by the screen-333 visual gap investigation
    2026-04-23.

    See ``tests/test_override_toggle_skipinvisible.py`` for the
    contract (single-toggle batching + try/finally restore).
    """
    spec_key_for_resolver = spec_key_map.get(
        id(node), node.head.eid,
    )
    resolver_bucket = descendant_visibility_resolver.get(
        spec_key_for_resolver, {},
    )

    # Collect all (fig_id, js_bool) pairs for this instance head.
    # Skip non-PathOverride props, non-`.visible` paths, missing
    # resolver entries, and non-bool values — same filter as before.
    targets: list[tuple[str, str, str]] = []  # (fig_id, js_bool, path)
    head_eid = node.head.eid
    for prop in node.head.properties:
        if not isinstance(prop, PathOverride):
            continue
        if not prop.path.endswith(".visible"):
            continue
        fig_child_id = resolver_bucket.get(prop.path)
        if not fig_child_id:
            # P5 (forensic-audit-2 finding 5): silent no-op pre-fix.
            # The PathOverride exists but the resolver has no fig_id
            # for the path — usually because the resolver was built
            # from stale CKR data, the master's child names changed,
            # or the override's path is malformed. Either way the
            # override is silently dropped; surface it via __errors
            # so the verifier can attribute the missing visibility.
            eid_lit = _escape_js(head_eid)
            path_lit = _escape_js(prop.path)
            lines.append(
                f'__errors.push({{eid:"{eid_lit}", '
                f'kind:"override_target_missing", '
                f'path:"{path_lit}", '
                f'reason:"resolver has no entry"}});'
            )
            continue
        bool_py = getattr(prop.value, "py", None)
        if not isinstance(bool_py, bool):
            continue
        js_bool = "true" if bool_py else "false"
        targets.append((fig_child_id, js_bool, prop.path))

    # No `.visible` overrides for this head — emit nothing. The toggle
    # cost is non-trivial; skipping it when there's nothing to do
    # matters for instances that carry only non-`.visible` overrides.
    if not targets:
        return

    # Build the JS Set literal of fig_ids to look up. Duplicates here
    # would be defensively idempotent on the JS side (Map.set last
    # wins), but the input shape rarely has them.
    js_id_literals = ", ".join(
        f'"{_escape_js(fid)}"' for fid, _, _ in targets
    )

    eid_lit = _escape_js(head_eid)

    # Single toggle window + single walk + K straight-line assigns.
    # The findAll callback splits on ";" and compares the LAST segment
    # — that's the same id-suffix convention findOne(endsWith) used,
    # but we evaluate it once per node instead of once per override.
    lines.append("figma.skipInvisibleInstanceChildren = false;")
    lines.append("try {")
    lines.append(f"  const _ids = new Set([{js_id_literals}]);")
    lines.append("  const _targets = new Map();")
    lines.append(
        f"  for (const _n of {var}.findAll(n => "
        '_ids.has(n.id.split(";").pop()))) {'
    )
    lines.append('    _targets.set(_n.id.split(";").pop(), _n);')
    lines.append("  }")
    lines.append("  let _t;")
    for fid, js_bool, path in targets:
        esc_fid = _escape_js(fid)
        esc_path = _escape_js(path)
        # P5 (forensic-audit-2 finding 5): runtime no-op site. Pre-fix
        # `if (_t) _t.visible = X;` silently skipped when findAll
        # didn't surface the cached id (resolver claimed the id
        # existed at compile time, but the live tree disagrees —
        # usually means the master's structure changed since the
        # resolver was built). Push override_target_missing instead
        # of failing silent.
        lines.append(
            f'  _t = _targets.get("{esc_fid}"); '
            f"if (_t) {{ _t.visible = {js_bool}; }} "
            f'else {{ __errors.push({{eid:"{eid_lit}", '
            f'kind:"override_target_missing", '
            f'path:"{esc_path}", '
            f'reason:"findAll did not surface fig_id"}}); }}'
        )
    lines.append("} finally {")
    lines.append("  figma.skipInvisibleInstanceChildren = true;")
    lines.append("}")


def _collect_text_chars(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[int, str],
) -> dict[int, tuple[str, str]]:
    """Map node-object-id → (var, escaped_text) for every text-typed
    node with a positional literal value. Baseline emits these in
    Phase 2 after each node's `appendChild`.

    Keyed on `id(node)` rather than eid because grammar §2.3.1 allows
    eid collisions across scopes (cousin subtrees can share an eid);
    see var_map keying in `render_figma`.
    """
    out: dict[int, tuple[str, str]] = {}
    for node, _parent in walk:
        if node.head.type_or_path not in _TEXT_TYPES:
            continue
        pos = node.head.positional
        if pos is None:
            continue
        py_value = getattr(pos, "py", None)
        if not isinstance(py_value, str) or not py_value:
            continue
        out[id(node)] = (var_map[id(node)], _escape_js(py_value))
    return out


def _emit_phase2(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[int, str],
    text_chars: dict[int, tuple[str, str]],
    spec_key_map: dict[int, str],
    doc: L3Document,
    page_name: Optional[str],
    *,
    canvas_position: Optional[tuple[float, float]] = None,
    nid_map: Optional[dict[int, int]] = None,
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    spec_elements: Optional[dict[str, dict[str, Any]]] = None,
    spec_tokens: Optional[dict[str, Any]] = None,
    deferred_groups: Optional[dict[int, dict[str, Any]]] = None,
    deferred_bool_ops: Optional[dict[int, dict[str, Any]]] = None,
    absorbed_node_ids: Optional[set[int]] = None,
) -> list[str]:
    """Phase 2 — wire tree via appendChild; emit text characters +
    per-node layoutSizing when parent is auto-layout.

    Guards against the LEAF_TYPE_APPEND defect (baseline lines
    1499–1524): leaf-type AST parents (text / line / rectangle /
    etc.) cannot accept children; emitting `parent.appendChild(...)`
    then throws at runtime and orphans the subtree. Skip silently
    and push a structured diagnostic.

    F13c: when `deferred_groups` is provided (every entry keyed on
    id(group_node)), Phase 2:
    - Skips groups in the appendChild loop (they don't exist yet).
    - For non-group children whose parent is in `deferred_groups`,
      walks UP the deferral chain to the nearest non-deferred
      ancestor and appends THERE temporarily. Records the child's
      var in the immediate-parent group's `direct_children`.
    - After the appendChild loop, walks deferred groups bottom-up
      by AST depth (innermost first) and emits
      `figma.group([direct_children_vars], grandparent_var)` for
      each, then `name + M[spec_key]` assigns. Outer groups'
      direct_children includes inner groups' vars (registered
      during the appendChild loop walk-up).
    """
    nid_map = nid_map or {}
    spec_elements = spec_elements or {}
    spec_tokens = spec_tokens or {}
    if deferred_groups is None:
        deferred_groups = {}
    if deferred_bool_ops is None:
        deferred_bool_ops = {}
    if absorbed_node_ids is None:
        absorbed_node_ids = set()
    lines: list[str] = []
    lines.append("")
    lines.append("// Phase 2: Compose — wire tree, set layoutSizing")
    lines.append("await new Promise(r => setTimeout(r, 0));")
    lines.append("")

    # F13c: build a parent map + direct-children registry for groups.
    parent_by_node_id: dict[int, Optional[Node]] = {
        id(n): p for n, p in walk
    }
    # Per-group direct_children — populated as we walk children below.
    # `direct_children` preserves insertion order = AST walk order.
    for ginfo in deferred_groups.values():
        ginfo.setdefault("direct_children", [])
    # Phase E #3: same registry for bool_ops.
    for binfo in deferred_bool_ops.values():
        binfo.setdefault("direct_children", [])

    def _resolve_nondeferred_ancestor(start_parent: Optional[Node]) -> Optional[Node]:
        """Walk up the parent chain until we find a non-deferred
        ancestor (or None at the top). Used to redirect appendChild
        when the immediate parent is a deferred group OR bool_op
        (which don't exist as Figma nodes yet)."""
        cur = start_parent
        while cur is not None and (
            id(cur) in deferred_groups or id(cur) in deferred_bool_ops
        ):
            cur = parent_by_node_id.get(id(cur))
        return cur

    def _is_group(node: Optional[Node]) -> bool:
        return node is not None and id(node) in deferred_groups

    def _is_bool_op(node: Optional[Node]) -> bool:
        return node is not None and id(node) in deferred_bool_ops

    def _is_deferred(node: Optional[Node]) -> bool:
        return _is_group(node) or _is_bool_op(node)

    for node, parent in walk:
        if parent is None:
            continue
        # P3a (N1 fix) — Phase E re-run regression fix (2026-04-26):
        # skip Phase 2 appendChild ONLY when the node's PARENT is
        # absorbed (Mode-1 head or descendant), not when the node
        # itself is absorbed. The Mode-1 head NODE is in
        # `mode1_node_ids` (Phase 1 line 836) but it still needs to
        # be appended to its own parent (e.g. a top-level INSTANCE
        # under screen-1). Pre-fix the original guard checked
        # `id(node) in absorbed_node_ids` and the Mode-1 head
        # silently lost its own appendChild, becoming a page-level
        # orphan; the verifier reported `missing_child` for every
        # top-level instance. Phase 1's `skipped_node_ids` is
        # populated transitively via the parent-in-set check at
        # lines 741-746, so parent-in-set here correctly catches
        # both direct children of Mode-1 heads AND grandchildren
        # (whose parent is in skipped_node_ids).
        # Must run BEFORE leaf-type and group-deferral checks
        # because Mode-1 absorption takes precedence over both.
        if id(parent) in absorbed_node_ids:
            continue
        eid = node.head.eid
        if id(node) not in var_map:
            continue
        parent_eid = parent.head.eid
        if id(parent) not in var_map:
            continue
        parent_head_kind = parent.head.head_kind
        parent_etype = (
            parent.head.type_or_path
            if parent_head_kind == "type"
            else ""
        )
        if parent_etype in _LEAF_TYPES:
            lines.append(
                f'// leaf_type_append skipped: parent={parent_eid!r} '
                f'({parent_etype!r}) cannot accept child {eid!r}'
            )
            lines.append(
                f'__errors.push({{kind:"leaf_type_append_skipped", '
                f'parent_eid:"{_escape_js(parent_eid)}", '
                f'parent_type:"{parent_etype}", '
                f'child_eid:"{_escape_js(eid)}"}});'
            )
            continue
        # F13c + Phase E #3: skip GROUP and BOOL_OP nodes here —
        # they don't exist as Figma nodes yet. The post-loop
        # bottom-up block creates them via figma.group(...) /
        # figma.<op>(...) AFTER all descendants are wired into the
        # temporary grandparent.
        if _is_deferred(node):
            # Register this deferred node's var in any outer
            # deferred parent's direct_children so the outer's
            # bottom-up block knows what to wrap. The var name is
            # reserved in var_map; the materialization call (group
            # or bool_op) will bind it via `const <var> = figma...`.
            if parent is not None:
                if _is_group(parent):
                    deferred_groups[id(parent)]["direct_children"].append(
                        var_map[id(node)]
                    )
                elif _is_bool_op(parent):
                    deferred_bool_ops[id(parent)]["direct_children"].append(
                        var_map[id(node)]
                    )
            continue
        child_var = var_map[id(node)]
        # F13c + Phase E #3: when the immediate parent is a
        # deferred group OR bool_op, the parent doesn't exist yet —
        # append to the nearest non-deferred ancestor (typically the
        # grandparent) so the descendant has a real parent to live
        # on temporarily. figma.group()/figma.<op>() later will move
        # it into the new node as a side effect of being passed in
        # the children-array. Also record this child's var in the
        # immediate-parent's direct_children so the bottom-up block
        # knows what to wrap.
        effective_parent = parent
        if _is_deferred(parent):
            if _is_group(parent):
                deferred_groups[id(parent)]["direct_children"].append(child_var)
            else:  # _is_bool_op(parent)
                deferred_bool_ops[id(parent)]["direct_children"].append(child_var)
            resolved_anc = _resolve_nondeferred_ancestor(parent)
            if resolved_anc is not None and id(resolved_anc) in var_map:
                effective_parent = resolved_anc
            else:
                # No non-deferred ancestor found — child still gets
                # default-parented to currentPage by createFrame/etc.
                # The bottom-up block will pick it up via
                # direct_children. Skip the appendChild.
                continue
        parent_var = var_map[id(effective_parent)]
        # Per-op guard (Tier E follow-up to F3): without this, a
        # single throw here aborts the rest of Phase 2 AND the
        # final _rootPage.appendChild — orphaning the entire
        # subtree from the page. User-visible symptom: "no
        # nesting hierarchy" because Figma auto-parents every
        # created node to currentPage, so un-re-parented nodes
        # end up flat at page root. Canonical guard shape matches
        # `dd/renderers/figma.py::_guarded_op` for byte parity.
        err_eid_child = _escape_js(spec_key_map.get(id(node), eid))
        lines.append(
            f'try {{ {parent_var}.appendChild({child_var}); }} '
            f'catch (__e) {{ __errors.push({{eid:"{err_eid_child}", '
            f'kind:"append_child_failed", '
            f'error: String(__e && __e.message || __e)}}); }}'
        )
        if id(node) in text_chars:
            var, escaped = text_chars[id(node)]
            err_eid = spec_key_map.get(id(node), eid)
            err_eid_js = _escape_js(err_eid)
            lines.append(
                f'try {{ {var}.characters = "{escaped}"; }} '
                f'catch (__e) {{ __errors.push({{eid:"{err_eid_js}", '
                f'kind:"text_set_failed", '
                f'error: String(__e && __e.message || __e)}}); }}'
            )

        etype = node.head.type_or_path if node.head.head_kind == "type" else ""
        is_text = etype in _TEXT_TYPES
        spec_key = spec_key_map.get(id(node), eid)
        parent_spec_key = spec_key_map.get(id(parent), parent_eid)
        parent_element = spec_elements.get(parent_spec_key, {})
        parent_direction = (
            parent_element.get("layout", {}).get("direction", "")
        )
        parent_is_autolayout = parent_direction in ("horizontal", "vertical")

        if parent_is_autolayout:
            element = spec_elements.get(spec_key, {})
            elem_sizing = element.get("layout", {}).get("sizing", {})
            db_sizing_h = nv_sh = None
            db_sizing_v = nv_sv = None
            text_auto_resize = None
            nid = nid_map.get(id(node))
            if db_visuals is not None and nid is not None:
                nv = db_visuals.get(nid, {}) or {}
                db_sizing_h = nv.get("layout_sizing_h")
                db_sizing_v = nv.get("layout_sizing_v")
                text_auto_resize = nv.get("text_auto_resize")
            # Item 1 of the 13-item burn-down: thread auto-layout
            # context so _resolve_one_axis can validate stale DB
            # HUG/FILL values (Codex round-13).
            elem_layout_dir = element.get("layout", {}).get("direction", "")
            node_is_autolayout_frame = elem_layout_dir in ("horizontal", "vertical")
            sizing_h, sizing_v = _resolve_layout_sizing(
                elem_sizing, db_sizing_h, db_sizing_v,
                text_auto_resize, is_text, etype,
                parent_is_autolayout=parent_is_autolayout,
                node_is_autolayout_frame=node_is_autolayout_frame,
            )
            # Per-op guards — layoutSizing ops are ordering-sensitive
            # (feedback_text_layout_invariants.md) and can throw on
            # Mode-1 placeholder frames subbed for missing INSTANCEs.
            # Without guards they cascade (Tier E F3 follow-up).
            err_eid_layout = _escape_js(spec_key_map.get(id(node), eid))
            if sizing_h:
                figma_h = _SIZING_MAP.get(sizing_h, sizing_h.upper())
                lines.append(
                    f'try {{ {child_var}.layoutSizingHorizontal = "{figma_h}"; }} '
                    f'catch (__e) {{ __errors.push({{eid:"{err_eid_layout}", '
                    f'kind:"layout_sizing_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
            if sizing_v:
                figma_v = _SIZING_MAP.get(sizing_v, sizing_v.upper())
                lines.append(
                    f'try {{ {child_var}.layoutSizingVertical = "{figma_v}"; }} '
                    f'catch (__e) {{ __errors.push({{eid:"{err_eid_layout}", '
                    f'kind:"layout_sizing_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
            # F13b: for text in autolayout parents, lock textAutoResize
            # AFTER layoutSizing has resolved the width. Mirrors the
            # OLD path's `text_autoresize_deferred` intent
            # (dd/renderers/figma.py:1855). Codex F13b spec: only emit
            # when NOT WIDTH_AND_HEIGHT — that mode is the default and
            # re-emitting it after layoutSizing re-enables natural-
            # width behavior, undoing the lock. Same authority as
            # `text_auto_resize` already read at line 1453.
            if is_text and text_auto_resize and text_auto_resize != "WIDTH_AND_HEIGHT":
                lines.append(
                    f'try {{ {child_var}.textAutoResize = "{text_auto_resize}"; }} '
                    f'catch (__e) {{ __errors.push({{eid:"{err_eid_layout}", '
                    f'kind:"text_auto_resize_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )

    # F13c + Phase E #3: bottom-up creation of deferred GROUPs and
    # BOOL_OPs. Innermost first so each outer deferred-node's
    # `direct_children` already contains its inner-deferred vars
    # (Plugin API requires children to exist before figma.group() /
    # figma.<op>() can wrap them). Groups and bool_ops are
    # materialized in one merged pass sorted by depth so a
    # bool_op-inside-group emits BEFORE the wrapping group, and
    # vice-versa.
    #
    # AST depth approximates DOM depth: a node's depth is the
    # length of its parent chain. Sort descending = deepest first.
    def _depth(n: Node) -> int:
        d = 0
        cur = parent_by_node_id.get(id(n))
        while cur is not None:
            d += 1
            cur = parent_by_node_id.get(id(cur))
        return d

    # Merge groups + bool_ops into one bottom-up pass so a bool_op
    # nested inside a group materializes BEFORE the group call
    # references it (and vice-versa).
    deferred_all: list[tuple[str, dict[str, Any]]] = []
    for ginfo in deferred_groups.values():
        deferred_all.append(("group", ginfo))
    for binfo in deferred_bool_ops.values():
        deferred_all.append(("bool_op", binfo))

    if deferred_all:
        deferred_all.sort(key=lambda item: -_depth(item[1]["node"]))

        for kind, info in deferred_all:
            dvar = info["var"]
            spec_key = info["spec_key"]
            err_d = _escape_js(spec_key)
            original_name = info["original_name"]
            name_js = _escape_js(original_name)
            direct_children = info["direct_children"]
            d_node = info["node"]
            # Find grandparent (nearest non-deferred ancestor). For
            # top-level deferred nodes this is the doc root or the
            # screen frame.
            grandparent_node = _resolve_nondeferred_ancestor(
                parent_by_node_id.get(id(d_node))
            )
            if grandparent_node is None:
                grandparent_var = "_rootPage"
            elif id(grandparent_node) not in var_map:
                grandparent_var = "_rootPage"
            else:
                grandparent_var = var_map[id(grandparent_node)]

            # Materialization shape varies by kind.
            if kind == "group":
                # F13c: figma.group(children, parent)
                empty_kind = "group_empty_append_failed"
                fail_kind = "group_create_failed"
                name_fail_kind = "group_name_failed"
                insert_fail_kind = "group_insert_failed"
                if not direct_children:
                    lines.append(
                        f'// F13c: group {spec_key!r} had no direct '
                        f'children — creating empty FRAME placeholder.'
                    )
                    lines.append(f'const {dvar} = figma.createFrame();')
                    lines.append(
                        f'try {{ {grandparent_var}.appendChild({dvar}); }} '
                        f'catch (__e) {{ __errors.push({{eid:"{err_d}", '
                        f'kind:"{empty_kind}", '
                        f'error: String(__e && __e.message || __e)}}); }}'
                    )
                else:
                    children_array = ", ".join(direct_children)
                    lines.append(
                        f'const {dvar} = (function() {{ '
                        f'try {{ '
                        f'return figma.group([{children_array}], '
                        f'{grandparent_var}); '
                        f'}} catch (__e) {{ '
                        f'__errors.push({{eid:"{err_d}", '
                        f'kind:"{fail_kind}", '
                        f'error: String(__e && __e.message || __e)}}); '
                        f'return figma.createFrame(); '
                        f'}} '
                        f'}})();'
                    )
            else:  # kind == "bool_op"
                # Phase E #3: figma.<op>(children, parent)
                operation_js = info["operation_js"]
                empty_kind = "bool_op_empty_failed"
                fail_kind = "bool_op_create_failed"
                name_fail_kind = "bool_op_name_failed"
                insert_fail_kind = "bool_op_insert_failed"
                if not direct_children:
                    # Empty bool_op — Plugin API rejects
                    # figma.<op>([], ...). Substitute a frame
                    # placeholder so var_map / M[...] mapping survives
                    # and downstream prop writes have a real target.
                    lines.append(
                        f'// Phase E #3: bool_op {spec_key!r} had no '
                        f'direct children (op={operation_js!r}) — '
                        f'creating empty FRAME placeholder.'
                    )
                    lines.append(f'const {dvar} = figma.createFrame();')
                    lines.append(
                        f'try {{ {grandparent_var}.appendChild({dvar}); }} '
                        f'catch (__e) {{ __errors.push({{eid:"{err_d}", '
                        f'kind:"{empty_kind}", '
                        f'error: String(__e && __e.message || __e)}}); }}'
                    )
                else:
                    children_array = ", ".join(direct_children)
                    # Specific catch metadata per Codex review #6:
                    # eid + operation + childCount so failures are
                    # diagnostic. Fallback to figma.createFrame()
                    # so subsequent prop writes have a target.
                    n_children = len(direct_children)
                    lines.append(
                        f'const {dvar} = (function() {{ '
                        f'try {{ '
                        f'return figma.{operation_js}([{children_array}], '
                        f'{grandparent_var}); '
                        f'}} catch (__e) {{ '
                        f'__errors.push({{eid:"{err_d}", '
                        f'kind:"{fail_kind}", '
                        f'operation:"{operation_js}", '
                        f'childCount:{n_children}, '
                        f'error: String(__e && __e.message || __e)}}); '
                        f'return figma.createFrame(); '
                        f'}} '
                        f'}})();'
                    )

            lines.append(
                f'try {{ {dvar}.name = "{name_js}"; }} catch (__e) {{ '
                f'__errors.push({{eid:"{err_d}", '
                f'kind:"{name_fail_kind}", '
                f'error: String(__e && __e.message || __e)}}); }}'
            )
            lines.append(f'M["{_escape_js(spec_key)}"] = {dvar}.id;')

            # P2 (forensic-audit-2 finding 2): bool-op visual replay.
            # Pre-fix the deferred materialization only emitted name +
            # M[] + z-order; visual props (fills, strokes, effects,
            # opacity, rotation, etc.) were never replayed because the
            # main loop's `if etype == "boolean_operation": continue`
            # had skipped _emit_visual entirely. Result: bool_ops
            # rendered as #D9D9D9 (Figma's default placeholder grey)
            # where IR specified the actual color. Surfaced as 10
            # DRIFT screens on the post-rextract Nouns sweep.
            #
            # Groups don't need this — their visual props are
            # inherited from the wrapping behavior (figma.group does
            # not set fills/strokes; the children carry them).
            if kind == "bool_op":
                bool_raw_visual = info.get("raw_visual")
                if bool_raw_visual:
                    bool_visual = build_visual_from_db(bool_raw_visual)
                    if bool_visual:
                        bool_visual_lines, _bool_visual_refs = _emit_visual(
                            dvar, err_d, bool_visual, spec_tokens,
                            node_type="BOOLEAN_OPERATION",
                        )
                        # Each visual line is `dvar.prop = ...;` —
                        # guard with try/catch in case the
                        # post-materialization bool node rejects a
                        # specific prop write (matches the
                        # phase1_mode2_prop_failed pattern used
                        # elsewhere).
                        for vl in bool_visual_lines:
                            lines.append(
                                f"try {{ {vl} }} catch (__e) {{ "
                                f'__errors.push({{eid:"{err_d}", '
                                f'kind:"phase1_mode2_prop_failed", '
                                f"error: String(__e && __e.message || __e)}}); }}"
                            )

            # Z-order: figma.group()/figma.<op>() always appends the
            # new node at the END of grandparent's children. For
            # nodes that aren't the last sibling in source order,
            # this puts them on top of subsequent siblings. Use
            # insertChild at the correct sort_order to fix.
            if grandparent_node is not None:
                gp_children_in_walk = [
                    c for c, p in walk
                    if p is grandparent_node
                ]
                try:
                    target_idx = gp_children_in_walk.index(d_node)
                except ValueError:
                    target_idx = -1
                if target_idx >= 0:
                    lines.append(
                        f'try {{ {grandparent_var}.insertChild({target_idx}, {dvar}); }} '
                        f'catch (__e) {{ __errors.push({{eid:"{err_d}", '
                        f'kind:"{insert_fail_kind}", '
                        f'error: String(__e && __e.message || __e)}}); }}'
                    )

    lines.append('__mark("phase2_done");')

    if doc.top_level:
        root_node = doc.top_level[0]
        root_var = var_map.get(id(root_node))
        if root_var is not None:
            # CRITICAL guard: this is the line that parents the
            # whole rendered tree onto the page. If it throws and
            # we're in the old naked-op regime, nothing ever
            # reaches the page — user sees "flat hierarchy"
            # because Figma's createFrame/etc. auto-parents to
            # currentPage, and whatever appendChild never re-
            # parented stays at the page root. Per-op guard keeps
            # the diagnostic structured.
            root_eid = spec_key_map.get(id(root_node), root_node.head.eid or "")
            root_eid_js = _escape_js(root_eid)
            if page_name:
                esc_name = _escape_js(page_name)
                lines.append(
                    f'let _page = figma.root.children.find(p => '
                    f'p.type === "PAGE" && p.name === "{esc_name}");'
                )
                lines.append(
                    f'if (!_page) {{ _page = figma.createPage(); '
                    f'_page.name = "{esc_name}"; }}'
                )
                lines.append(
                    f'try {{ _page.appendChild({root_var}); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{root_eid_js}", '
                    f'kind:"root_append_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
                lines.append("await figma.setCurrentPageAsync(_page);")
            else:
                lines.append(
                    f'try {{ _rootPage.appendChild({root_var}); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{root_eid_js}", '
                    f'kind:"root_append_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )

            if canvas_position is not None:
                cx, cy = canvas_position
                lines.append(
                    f'try {{ {root_var}.x = {cx}; }} '
                    f'catch (__e) {{ __errors.push({{eid:"{root_eid_js}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
                lines.append(
                    f'try {{ {root_var}.y = {cy}; }} '
                    f'catch (__e) {{ __errors.push({{eid:"{root_eid_js}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )

    lines.append('__mark("root_attach_done");')

    return lines


def _emit_phase3(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[int, str],
    spec_key_map: dict[int, str],
    *,
    nid_map: dict[int, int],
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    spec_elements: Optional[dict[str, dict[str, Any]]] = None,
    override_deferred: Optional[list[str]] = None,
    deferred_groups: Optional[dict[int, dict[str, Any]]] = None,
    absorbed_node_ids: Optional[set[int]] = None,
) -> list[str]:
    """Phase 3 — resize (for non-auto-layout children), position,
    constraints, and override-tree-deferred ops. Baseline emits the
    Phase 3 comment only when there are hydrate_ops; preserving that
    behaviour keeps non-positioned screens free of a stray Phase 3
    header.

    F13c: GROUP nodes (in `deferred_groups`) get position-only
    treatment. Figma `GroupNode` has no fills/strokes/cornerRadius
    and no autolayout; emitting those would throw "object is not
    extensible". Position (`x`, `y`) is moved AFTER `figma.group()`
    runs in Phase 2 — the group's auto-fit bbox at creation time
    matches the union of children's positions, so setting `g.x`
    here re-anchors the whole subtree at the source's intended
    position.
    """
    spec_elements = spec_elements or {}
    override_deferred = override_deferred or []
    deferred_groups = deferred_groups or {}
    if absorbed_node_ids is None:
        absorbed_node_ids = set()
    ops: list[str] = list(override_deferred)
    parent_by_node_id: dict[int, Optional[Node]] = {
        id(n): p for n, p in walk
    }

    # F13b: lazy import — resolve_element merges AST head + spec
    # element + db_visuals into the canonical element shape. Phase 3
    # was reading spec_elements directly, which misses both the AST
    # head's overrides AND the F13a deep-merge resolution. Reading
    # the resolved shape here aligns Phase 3 with Phase 1's locus
    # (line 694) and is what makes the text resize / textAutoResize
    # block work for non-autolayout-parent text nodes (Bug B).
    from dd.ast_to_element import resolve_element

    for node, parent in walk:
        # P3a (N1 fix) — Phase E re-run regression fix (2026-04-26):
        # skip Phase 3 props ONLY when the node's PARENT is absorbed
        # (i.e. the node is inside a Mode-1 INSTANCE subtree, not the
        # head itself). The Mode-1 head NODE is in absorbed_node_ids
        # but it still needs its own resize/position/constraints
        # applied (top-level instances carry explicit IR layout that
        # the verifier expects to match). Pre-fix the original guard
        # checked `id(node) in absorbed_node_ids`, which silently
        # dropped the head's own Phase 3 ops and left the instance
        # at default size/position; the verifier reported
        # `bounds_mismatch` cascade on top of the missing_child from
        # Phase 2. Phase 1's `skipped_node_ids` is populated
        # transitively at lines 741-746, so parent-in-set catches
        # both direct children of Mode-1 heads AND grandchildren.
        if parent is not None and id(parent) in absorbed_node_ids:
            continue
        eid = node.head.eid
        if id(node) not in var_map:
            continue
        var = var_map[id(node)]
        spec_key = spec_key_map.get(id(node), eid)
        err_eid = _escape_js(spec_key)

        # F13c: GROUPs get position-only treatment. Figma `GroupNode`
        # has no fills/strokes/cornerRadius/autolayout — emitting any
        # of those throws "object is not extensible". The figma.group()
        # call in Phase 2 already auto-fits the group's bbox to its
        # children's union; setting g.x / g.y here re-anchors the
        # whole subtree at the source's intended position (children's
        # local coords inside the group recompute automatically per
        # Plugin API). Skip the rest of the per-node Phase 3 block
        # (resize / textAutoResize / constraints) for groups.
        if id(node) in deferred_groups:
            ginfo = deferred_groups[id(node)]
            position = (
                ginfo.get("element", {}).get("layout", {}).get("position")
            )
            if position:
                x_val = position.get("x", 0)
                y_val = position.get("y", 0)
                ops.append(
                    f'try {{ {var}.x = {x_val}; }} catch (__e) {{ '
                    f'__errors.push({{eid:"{err_eid}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
                ops.append(
                    f'try {{ {var}.y = {y_val}; }} catch (__e) {{ '
                    f'__errors.push({{eid:"{err_eid}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
            # Visibility — the AST may have `visible=false` on a
            # group head; preserve it. Figma GroupNode has .visible.
            if _ast_prop_is_false(node, "visible"):
                ops.append(
                    f'try {{ {var}.visible = false; }} catch (__e) {{ '
                    f'__errors.push({{eid:"{err_eid}", '
                    f'kind:"visibility_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
            continue

        # F13b: read the RESOLVED element (AST head + spec + db_visuals
        # merged) so Phase 3 sees the same shape Phase 1 emits against.
        # Without this, Phase 3 missed both the AST head's overrides
        # and the AST-supplied widthPixels/heightPixels for nodes whose
        # IR `width`/`height` were already literal numerics. Codex spec
        # 2026-04-25.
        nid = nid_map.get(id(node))
        element = resolve_element(
            node=node,
            spec_elements=spec_elements,
            spec_key=spec_key,
            db_visuals=db_visuals or {},
            nid=nid,
            nid_map=nid_map,
        )
        parent_node = parent_by_node_id.get(id(node))
        parent_element = {}
        if parent_node is not None:
            parent_spec_key = spec_key_map.get(
                id(parent_node), parent_node.head.eid,
            )
            # Parent layout decision is also a layout decision — read
            # the resolved parent shape too, not the bare spec dict.
            parent_element = resolve_element(
                node=parent_node,
                spec_elements=spec_elements,
                spec_key=parent_spec_key,
                db_visuals=db_visuals or {},
                nid=nid_map.get(id(parent_node)),
                nid_map=nid_map,
            )
        parent_direction = (
            parent_element.get("layout", {}).get("direction", "")
        )
        parent_is_autolayout = parent_direction in ("horizontal", "vertical")

        visual = (
            db_visuals.get(nid, {}) or {}
            if db_visuals is not None and nid is not None
            else {}
        )

        # Determine if this node is a text type — text needs the
        # textAutoResize lock after resize per Codex F13b spec.
        etype = (
            node.head.type_or_path if node.head.head_kind == "type" else ""
        )
        # Phase E residual #1 fix (2026-04-26): same hyphen→underscore
        # normalization as Phase 1 — Phase 3 was re-reading raw
        # type_or_path. Without this, downstream lookups against
        # underscore-keyed dicts (e.g. _TEXT_TYPES, _LEAF_TYPES) miss.
        etype = etype.replace("-", "_") if isinstance(etype, str) else ""
        # Phase E #3 (2026-04-26): the previous boolean_operation
        # short-circuit at this site is REMOVED. Post-fix bool_ops
        # are deferred in Phase 1 and materialized via figma.<op>(...)
        # in Phase 2's bottom-up block. The result is a real
        # extensible BoolNode that accepts resize/position/constraints
        # like any other node — so the regular Phase 3 path applies
        # without modification. The empty createBooleanOperation()
        # frozen-node problem from the residual fix doesn't exist
        # anymore because we never call the bare constructor.
        is_text = etype in _TEXT_TYPES

        rotation_deg = _ast_prop_py(node, "rotation")
        mirror_axis = _ast_prop_py(node, "mirror")
        has_transform = (
            isinstance(rotation_deg, (int, float)) and rotation_deg != 0
        ) or isinstance(mirror_axis, str)

        if not parent_is_autolayout and element:
            elem_sizing = element.get("layout", {}).get("sizing", {})
            # F13b: support both spellings — IR-direct elements use
            # numeric `width`/`height`; AST-merged elements use
            # `widthPixels`/`heightPixels`. Mirrors `_emit_layout`'s
            # tolerant lookup at dd/renderers/figma.py:2255-2262.
            # `width`/`height` only count when numeric (string
            # values like "hug" are semantic, not pixel dims).
            pw = elem_sizing.get("widthPixels")
            if pw is None and isinstance(elem_sizing.get("width"), (int, float)):
                pw = elem_sizing.get("width")
            ph = elem_sizing.get("heightPixels")
            if ph is None and isinstance(elem_sizing.get("height"), (int, float)):
                ph = elem_sizing.get("height")
            if pw is not None and ph is not None:
                ops.append(
                    f'try {{ {var}.resize({round(pw, 2)}, {round(ph, 2)}); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{err_eid}", '
                    f'kind:"resize_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
                # F13b: for text, lock textAutoResize AFTER resize so
                # the explicit dimensions stick. Source from DB
                # (`text_auto_resize` on the node row, same authority
                # Phase 2's autolayout block reads at line 1453).
                # Order is critical per `feedback_text_layout_invariants
                # .md`: characters → resize → textAutoResize. Codex
                # F13b spec: only emit when NOT WIDTH_AND_HEIGHT —
                # WIDTH_AND_HEIGHT is the default and re-emitting it
                # after resize re-enables natural-width behavior,
                # undoing the lock.
                if is_text:
                    text_mode = visual.get("text_auto_resize")
                    if text_mode and text_mode != "WIDTH_AND_HEIGHT":
                        ops.append(
                            f'try {{ {var}.textAutoResize = "{text_mode}"; }} '
                            f'catch (__e) {{ __errors.push({{eid:"{err_eid}", '
                            f'kind:"text_auto_resize_failed", '
                            f'error: String(__e && __e.message || __e)}}); }}'
                        )
            position = element.get("layout", {}).get("position")
            if position and not has_transform:
                x_val = position.get("x", 0)
                y_val = position.get("y", 0)
                ops.append(
                    f'try {{ {var}.x = {x_val}; }} catch (__e) {{ '
                    f'__errors.push({{eid:"{err_eid}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )
                ops.append(
                    f'try {{ {var}.y = {y_val}; }} catch (__e) {{ '
                    f'__errors.push({{eid:"{err_eid}", '
                    f'kind:"position_failed", '
                    f'error: String(__e && __e.message || __e)}}); }}'
                )

        # Transform emission is driven by AST primitives and runs
        # independent of the shim path — this is what every future
        # backend walker (React / SwiftUI / Flutter) will consume
        # once the dict-IR shim is retired at M5. Reads x/y from the
        # AST as well, falling back to any shim-supplied position
        # only when the AST omits them (rare: M0 compressor emits
        # x/y for every non-origin child).
        if has_transform and not parent_is_autolayout:
            ast_x = _ast_prop_py(node, "x")
            ast_y = _ast_prop_py(node, "y")
            if not isinstance(ast_x, (int, float)):
                ast_x = (
                    element.get("layout", {}).get("position", {}).get("x", 0)
                    if element else 0
                )
            if not isinstance(ast_y, (int, float)):
                ast_y = (
                    element.get("layout", {}).get("position", {}).get("y", 0)
                    if element else 0
                )
            rot_deg = (
                float(rotation_deg)
                if isinstance(rotation_deg, (int, float)) else 0.0
            )
            axis = mirror_axis if isinstance(mirror_axis, str) else None
            rt = _reconstruct_relative_transform(
                float(ast_x), float(ast_y), rot_deg, axis,
            )
            ops.append(
                f'try {{ {var}.relativeTransform = '
                f'[[{_matrix_cell(rt[0][0])},'
                f'{_matrix_cell(rt[0][1])},'
                f'{_matrix_cell(rt[0][2])}],'
                f'[{_matrix_cell(rt[1][0])},'
                f'{_matrix_cell(rt[1][1])},'
                f'{_matrix_cell(rt[1][2])}]]; }} '
                f'catch (__e) {{ __errors.push({{eid:"{err_eid}", '
                f'kind:"position_failed", '
                f'error: String(__e && __e.message || __e)}}); }}'
            )

        c_h = visual.get("constraint_h")
        c_v = visual.get("constraint_v")
        # Phase E #3 (2026-04-26): BOOLEAN_OPERATION nodes accept
        # resize/x/y/rotation/opacity/visible writes (verified on
        # the live bridge), but NOT the `.constraints = {h, v}`
        # property — that one specifically throws "object is not
        # extensible" on a materialized BoolNode. Skip just this
        # write for bool_ops; everything else flows through.
        # Bridge probe in tests/test_boolean_operation_dispatch.py
        # documents the exact API surface boundary.
        if (c_h or c_v) and etype != "boolean_operation":
            parts = []
            if c_h:
                mapped = _CONSTRAINT_MAP.get(c_h, c_h)
                parts.append(f'horizontal: "{mapped}"')
            if c_v:
                mapped = _CONSTRAINT_MAP.get(c_v, c_v)
                parts.append(f'vertical: "{mapped}"')
            ops.append(
                f'try {{ {var}.constraints = {{{", ".join(parts)}}}; }} '
                f'catch (__e) {{ __errors.push({{eid:"{err_eid}", '
                f'kind:"constraint_failed", '
                f'error: String(__e && __e.message || __e)}}); }}'
            )

    lines: list[str] = []
    if ops:
        lines.append("")
        lines.append(
            "// Phase 3: Hydrate — text content, position, constraints"
        )
        lines.append("await new Promise(r => setTimeout(r, 0));")
        lines.append("")
        lines.extend(ops)
    lines.append('__perf.phase3_op_count = ' + str(len(ops)) + ';')
    lines.append('__mark("phase3_done");')
    return lines


def _emit_end_wrapper() -> list[str]:
    """The closing `} catch {} M[__errors]; return M;` block.

    Lives outside the Phase 1/2/3 content because it's boilerplate that
    closes the `try {` wrapper opened in the preamble. Identical bytes
    to the baseline's end wrapper.
    """
    return [
        "} catch (__thrown) {",
        "  __errors.push({kind: \"render_thrown\", "
        "error: String(__thrown && __thrown.message || __thrown), "
        "stack: (__thrown && __thrown.stack) ? "
        "String(__thrown.stack).split(\"\\n\").slice(0, 6).join(\" | \") "
        ": null});",
        "}",
        'M["__errors"] = __errors;',
        # Per-stage timing instrumentation (2026-04-24). Diagnostic
        # only — every consumer that iterates M filters this key
        # alongside __errors / __canary. See preamble for the marker
        # protocol; partial __perf is the only signal a timed-out run
        # leaves behind.
        '__perf.total_ms = Date.now() - __perf.t0;',
        'M["__perf"] = __perf;',
        "return M;",
    ]


def _original_name_from_node(node: Node) -> Optional[str]:
    """M1c-scope shortcut: return the AST eid as `.name`.

    Byte-identical to baseline ONLY when the fixture's
    `_original_name` survives `normalize_to_eid` unchanged — true for
    the minimal synthetic fixture (`"test-screen"` → `"test-screen"`)
    but NOT for real Dank screens (`"iPhone 13 Pro Max – 119"` →
    `"iphone-13-pro-max-119"`).

    M1d replaces this with a proper `eid → original_name` side-car
    from `compress_to_l3_with_maps`.
    """
    return node.head.eid
