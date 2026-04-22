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
    phase1, uses_placeholder, phase1_refs, override_deferred = _emit_phase1(
        walk, var_map, spec_key_map, original_name_map,
        nid_map=nid_map, db_visuals=db_visuals,
        spec_elements=spec_elements, spec_tokens=spec_tokens,
        node_id_vars=node_id_vars,
        descendant_visibility_resolver=descendant_visibility_resolver,
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
    )
    phase3 = _emit_phase3(
        walk, var_map, spec_key_map,
        nid_map=nid_map, db_visuals=db_visuals,
        spec_elements=spec_elements,
        override_deferred=override_deferred,
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
) -> tuple[list[str], bool, list[tuple[str, str, str]], list[str]]:
    """Phase 1 — materialize nodes + set intrinsic properties.

    Returns `(lines, uses_placeholder, token_refs, override_deferred)`
    where:

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
    """
    spec_elements = spec_elements or {}
    spec_tokens = spec_tokens or {}
    node_id_vars = node_id_vars or {}
    lines: list[str] = []
    lines.append(
        "// Phase 1: Materialize — create nodes, set intrinsic properties"
    )
    uses_placeholder = False
    token_refs: list[tuple[str, str, str]] = []
    override_deferred: list[str] = []

    for node, _parent in walk:
        eid = node.head.eid
        var = var_map[id(node)]
        head_kind = node.head.head_kind
        etype = node.head.type_or_path if head_kind == "type" else ""

        raw_visual: dict[str, Any] = {}
        if db_visuals is not None:
            nid = nid_map.get(id(node))
            if nid is not None:
                raw_visual = db_visuals.get(nid, {}) or {}

        spec_key = spec_key_map.get(id(node), eid)
        element = spec_elements.get(spec_key, {}) if spec_elements else {}

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

        if use_mode1 and (component_figma_id or instance_figma_node_id):
            emitted, mode1_ok = _emit_mode1_create(
                var, node, spec_key_map, original_name_map,
                component_figma_id, instance_figma_node_id,
                raw_visual, element,
                deferred_lines=override_deferred,
                node_id_vars=node_id_vars,
                descendant_visibility_resolver=(
                    descendant_visibility_resolver
                ),
            )
            if mode1_ok:
                lines.extend(emitted)
                uses_placeholder = True
                m_key = spec_key_map.get(id(node), eid)
                lines.append(
                    f'M["{_escape_js(m_key)}"] = {var}.id;'
                )
                lines.append("")
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

        create_call = _TYPE_TO_CREATE_CALL.get(etype, "figma.createFrame()")
        lines.append(f"const {var} = {create_call};")

        original_name = original_name_map.get(id(node)) or eid
        name_js = _escape_js(original_name)
        lines.append(f'{var}.name = "{name_js}";')

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
                lines.extend(visual_lines)
                # `_emit_visual` returns pre-built ``(eid, prop,
                # token_name)`` 3-tuples keyed on the eid it received
                # (== ``spec_key_for_emit``). Pass through — rebuilding
                # here was a shape-mismatch bug that happened to be
                # dormant on the Dank corpus (DB-extracted specs have
                # empty ``_token_refs`` maps) and only surfaced on the
                # synthetic compose.py path.
                token_refs.extend(visual_refs)
            elif etype == "frame":
                lines.append(f"{var}.fills = [];")
                lines.append(f"{var}.clipsContent = false;")
            elif etype in ("rectangle", "ellipse", "vector", "boolean_operation"):
                lines.append(f"{var}.fills = [];")

            text_auto_resize = None
            if is_text:
                text_auto_resize = raw_visual.get("text_auto_resize")

            if layout and not is_text:
                layout_lines, layout_refs = _emit_layout(
                    var, spec_key_for_emit, layout, spec_tokens,
                    text_auto_resize=text_auto_resize, etype=etype,
                )
                lines.extend(layout_lines)
                token_refs.extend(layout_refs)

            if is_text:
                db_font = raw_visual.get("font") or raw_visual
                _emit_text_props(
                    var, element, style, spec_tokens, lines,
                    db_font=db_font, eid=spec_key_for_emit,
                )
            if etype in ("vector", "boolean_operation") and raw_visual:
                _emit_vector_paths(var, raw_visual, lines)

            # Clear default fills on non-text nodes when the DB row
            # has no fills — matches baseline figma.py:1401–1402. Any
            # `figma.createRectangle / createVector / createFrame`
            # ships with a default white fill, which has to be cleared
            # explicitly when the DB says the node is unfilled.
            if not is_text and not visual.get("fills"):
                lines.append(f"{var}.fills = [];")

            # Clear default stroke on vector / line — `createVector()`
            # and `createLine()` ship with a 1px black stroke that
            # must be cleared when the DB row has no strokes. Matches
            # baseline figma.py:1404–1413.
            if etype in ("vector", "line") and not visual.get("strokes"):
                lines.append(f"{var}.strokes = [];")

            # Clear default `clipsContent=true` on frames when the DB
            # value is NULL / falsy. Matches baseline
            # figma.py:1424–1428 — `createFrame()` ships with
            # clipsContent=true and that value clobbers overflow visual
            # when the DB intends no clipping.
            if (
                etype == "frame"
                and not visual.get("clipsContent")
            ):
                lines.append(f"{var}.clipsContent = false;")
        else:
            if etype == "frame":
                lines.append(f"{var}.fills = [];")
                lines.append(f"{var}.clipsContent = false;")
            elif etype in ("rectangle", "ellipse", "vector", "boolean_operation"):
                lines.append(f"{var}.fills = [];")
            elif etype in _TEXT_TYPES:
                font_js = (
                    f'{{family: "{_DEFAULT_TEXT_FONT_FAMILY}", '
                    f'style: "{_DEFAULT_TEXT_FONT_STYLE}"}}'
                )
                err_eid = spec_key_map.get(id(node), eid)
                err_eid_js = _escape_js(err_eid)
                lines.append(
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
            lines.append(f"{var}.visible = false;")

        m_key = spec_key_map.get(id(node), eid)
        lines.append(f'M["{_escape_js(m_key)}"] = {var}.id;')
        lines.append("")

    return lines, uses_placeholder, token_refs, override_deferred


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
    else:
        return [], False

    original_name = original_name_map.get(id(node)) or eid
    lines.append(f'{var}.name = "{_escape_js(original_name)}";')

    props = element.get("props") or {}
    text_override = props.get("text", "")
    if text_override:
        text_target = props.get("text_target")
        find_expr = _build_text_finder(var, text_target)
        lines.append(
            f'{{ const _t = {find_expr}; '
            f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
            f'_t.characters = "{_escape_js(text_override)}"; }} }}'
        )

    subtitle_override = props.get("subtitle", "")
    if subtitle_override:
        sub_find = _build_text_finder(var, None, subtitle=True)
        lines.append(
            f'{{ const _t = {sub_find}; '
            f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
            f'_t.characters = "{_escape_js(subtitle_override)}"; }} }}'
        )

    hidden_children = raw_visual.get("hidden_children") or []
    for hc in hidden_children:
        hname = _escape_js(hc.get("name", ""))
        lines.append(
            f'{{ const _h = {var}.findOne(n => n.name === "{hname}"); '
            f'if (_h) _h.visible = false; }}'
        )

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
        spec_key_for_resolver = spec_key_map.get(
            id(node), node.head.eid,
        )
        resolver_bucket = descendant_visibility_resolver.get(
            spec_key_for_resolver, {},
        )
        for prop in node.head.properties:
            if not isinstance(prop, PathOverride):
                continue
            if not prop.path.endswith(".visible"):
                continue
            fig_child_id = resolver_bucket.get(prop.path)
            if not fig_child_id:
                continue
            bool_py = getattr(prop.value, "py", None)
            if not isinstance(bool_py, bool):
                continue
            js_bool = "true" if bool_py else "false"
            suffix = f";{fig_child_id}"
            esc_suffix = _escape_js(suffix)
            lines.append(
                f'{{ const _h = {var}.findOne(n => '
                f'n.id.endsWith("{esc_suffix}")); '
                f'if (_h) _h.visible = {js_bool}; }}'
            )

    # Scalar rotation only when AST carries no transform primitives
    # (``rotation`` / ``mirror``). When either is present, Phase 3
    # emits a full ``relativeTransform`` matrix that subsumes both
    # rotation and translation; emitting scalar ``rotation`` here
    # would race the matrix and leave an ambiguous pivot.
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
    inst_opacity = raw_visual.get("opacity")
    if isinstance(inst_opacity, (int, float)) and inst_opacity < 1.0:
        lines.append(f"{var}.opacity = {inst_opacity};")

    if element.get("visible") is False:
        lines.append(f"{var}.visible = false;")

    return lines, True


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
) -> list[str]:
    """Phase 2 — wire tree via appendChild; emit text characters +
    per-node layoutSizing when parent is auto-layout.

    Guards against the LEAF_TYPE_APPEND defect (baseline lines
    1499–1524): leaf-type AST parents (text / line / rectangle /
    etc.) cannot accept children; emitting `parent.appendChild(...)`
    then throws at runtime and orphans the subtree. Skip silently
    and push a structured diagnostic.
    """
    nid_map = nid_map or {}
    spec_elements = spec_elements or {}
    lines: list[str] = []
    lines.append("")
    lines.append("// Phase 2: Compose — wire tree, set layoutSizing")
    lines.append("await new Promise(r => setTimeout(r, 0));")
    lines.append("")

    for node, parent in walk:
        if parent is None:
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
        child_var = var_map[id(node)]
        parent_var = var_map[id(parent)]
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
            sizing_h, sizing_v = _resolve_layout_sizing(
                elem_sizing, db_sizing_h, db_sizing_v,
                text_auto_resize, is_text, etype,
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
) -> list[str]:
    """Phase 3 — resize (for non-auto-layout children), position,
    constraints, and override-tree-deferred ops. Baseline emits the
    Phase 3 comment only when there are hydrate_ops; preserving that
    behaviour keeps non-positioned screens free of a stray Phase 3
    header.
    """
    spec_elements = spec_elements or {}
    override_deferred = override_deferred or []
    ops: list[str] = list(override_deferred)
    parent_by_node_id: dict[int, Optional[Node]] = {
        id(n): p for n, p in walk
    }

    for node, _parent in walk:
        eid = node.head.eid
        if id(node) not in var_map:
            continue
        var = var_map[id(node)]
        spec_key = spec_key_map.get(id(node), eid)
        err_eid = _escape_js(spec_key)
        element = spec_elements.get(spec_key, {})
        parent_node = parent_by_node_id.get(id(node))
        parent_element = {}
        if parent_node is not None:
            parent_spec_key = spec_key_map.get(
                id(parent_node), parent_node.head.eid,
            )
            parent_element = spec_elements.get(parent_spec_key, {})
        parent_direction = (
            parent_element.get("layout", {}).get("direction", "")
        )
        parent_is_autolayout = parent_direction in ("horizontal", "vertical")

        nid = nid_map.get(id(node))
        visual = (
            db_visuals.get(nid, {}) or {}
            if db_visuals is not None and nid is not None
            else {}
        )

        rotation_deg = _ast_prop_py(node, "rotation")
        mirror_axis = _ast_prop_py(node, "mirror")
        has_transform = (
            isinstance(rotation_deg, (int, float)) and rotation_deg != 0
        ) or isinstance(mirror_axis, str)

        if not parent_is_autolayout and element:
            elem_sizing = element.get("layout", {}).get("sizing", {})
            pw = elem_sizing.get("widthPixels")
            ph = elem_sizing.get("heightPixels")
            if pw is not None and ph is not None:
                ops.append(
                    f'try {{ {var}.resize({round(pw, 2)}, {round(ph, 2)}); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{err_eid}", '
                    f'kind:"resize_failed", '
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
        if c_h or c_v:
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

    if not ops:
        return []

    lines: list[str] = []
    lines.append("")
    lines.append("// Phase 3: Hydrate — text content, position, constraints")
    lines.append("await new Promise(r => setTimeout(r, 0));")
    lines.append("")
    lines.extend(ops)
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
