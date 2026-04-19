"""Markup-native Figma renderer — Option B walker.

This module replaces `dd.renderers.figma.generate_figma_script` at M6
cutover per `docs/decisions/v0.3-option-b-cutover.md`. Until then it
coexists with the dict-IR renderer in CI; an A/B harness
(`tests/test_option_b_parity.py`) asserts the two paths produce
byte-identical Figma scripts.

Current scope (M1b): `render_figma_preamble` only — emits the
pre-Phase-1 prefix byte-identical to `generate_figma_script`'s
corresponding region. Full Phase 1/2/3 walker lands across M1c–M1d.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from dd.markup_l3 import L3Document, Node
from dd.renderers.figma import (
    MISSING_COMPONENT_PLACEHOLDER_BLOCK,
    _collect_swap_targets_from_tree,
    _escape_js,
)


# Baseline createText defaults when the AST carries no typography
# (the current M0 compressor output). These match
# `dd.renderers.figma.generate_figma_script` emission for a bare text
# element with empty `style` — byte-parity on M1c depends on using the
# exact same fallback values.
_DEFAULT_TEXT_FONT_FAMILY = "Inter"
_DEFAULT_TEXT_FONT_STYLE = "Regular"
_DEFAULT_TEXT_FONT_SIZE = 14


# AST types that map to Figma native types for createCalls.
_TYPE_TO_CREATE_CALL: dict[str, str] = {
    "frame": "figma.createFrame()",
    "rectangle": "figma.createRectangle()",
    "text": "figma.createText()",
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

    all_fonts = [("Inter", "Regular")] + [
        f for f in fonts if f != ("Inter", "Regular")
    ]
    for family, style in all_fonts:
        family_js = _escape_js(family)
        style_js = _escape_js(style)
        preamble.append(
            "await (async () => { try { "
            f"await figma.loadFontAsync({{family: \"{family_js}\", style: \"{style_js}\"}}); "
            "} catch (__e) { "
            f"__errors.push({{kind:\"font_load_failed\", family:\"{family_js}\", style:\"{style_js}\", "
            "error: String(__e && __e.message || __e)}); } })();"
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

    needed_node_ids: set[str] = set()
    if db_visuals is not None:
        for _nid, vis in db_visuals.items():
            figma_id = vis.get("component_figma_id")
            if figma_id:
                needed_node_ids.add(figma_id)
            _collect_swap_targets_from_tree(
                vis.get("override_tree"), needed_node_ids,
            )

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
    nid_map: dict[str, int],
    *,
    fonts: list[tuple[str, str]],
    spec_key_map: dict[str, str],
    db_visuals: Optional[dict[int, dict[str, Any]]] = None,
    ckr_built: bool = True,
    page_name: Optional[str] = None,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Full markup-native Figma render-script walker.

    Walks `doc` in pre-order, dispatches per `Node.head.type_or_path`,
    emits a three-phase Figma JS script with the same shape baseline
    `generate_figma_script` produces for dict-IR input.

    M1c scope: frame / rectangle / text dispatch + Phase 1 intrinsic
    property emission + Phase 2 appendChild chain + end-wrapper. No
    instances, layout, fills, strokes, effects, vector paths,
    constraints, or overrides yet — those are M1d / M2+ scope.

    `spec_key_map` bridges AST eid → CompositionSpec element key. The
    baseline renderer emits ``M["<spec_key>"] = nN.id;`` to track
    node identity across the render/walk/verify round trip; this
    walker must use the same keys for byte-parity. At M5 (verifier
    migration) the scheme flips to AST eids and the bridge goes away.

    `page_name` support lands at M1d alongside instance resolution;
    the signature is reserved for caller compatibility with
    `generate_figma_script`.
    """
    walk = list(_walk_ast(doc))

    uses_placeholder = False

    preamble = render_figma_preamble(
        doc, conn, nid_map,
        fonts=fonts, db_visuals=db_visuals, ckr_built=ckr_built,
        uses_placeholder=uses_placeholder,
    )

    var_map: dict[str, str] = {
        node.head.eid: f"n{idx}" for idx, (node, _p) in enumerate(walk)
    }

    phase1 = _emit_phase1(walk, var_map, spec_key_map)
    text_chars = _collect_text_chars(walk, var_map)
    phase2 = _emit_phase2(
        walk, var_map, text_chars, spec_key_map, doc, page_name,
    )

    end = _emit_end_wrapper()

    body_lines = phase1 + phase2 + end
    script = preamble + "\n".join(body_lines)

    token_refs: list[tuple[str, str, str]] = []
    return script, token_refs


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
    var_map: dict[str, str],
    spec_key_map: dict[str, str],
) -> list[str]:
    """Phase 1 — materialize nodes + set intrinsic properties.

    One blank line after each node's emission acts as the separator
    between nodes; this matches baseline's per-node trailing
    `phase1_lines.append("")`.

    `spec_key_map` resolves each AST eid back to the spec element key
    used by the baseline for ``M[...]`` emission. See `render_figma`.
    """
    lines: list[str] = []
    lines.append(
        "// Phase 1: Materialize — create nodes, set intrinsic properties"
    )

    for node, _parent in walk:
        eid = node.head.eid
        var = var_map[eid]
        etype = node.head.type_or_path

        create_call = _TYPE_TO_CREATE_CALL.get(etype, "figma.createFrame()")
        lines.append(f"const {var} = {create_call};")

        original_name = _original_name_from_node(node)
        if original_name:
            name_js = _escape_js(original_name)
            lines.append(f'{var}.name = "{name_js}";')

        if etype == "frame":
            lines.append(f"{var}.fills = [];")
            lines.append(f"{var}.clipsContent = false;")
        elif etype == "rectangle":
            lines.append(f"{var}.fills = [];")
        elif etype == "text":
            font_js = (
                f'{{family: "{_DEFAULT_TEXT_FONT_FAMILY}", '
                f'style: "{_DEFAULT_TEXT_FONT_STYLE}"}}'
            )
            err_eid = spec_key_map.get(eid, eid)
            err_eid_js = _escape_js(err_eid)
            lines.append(
                f"try {{ {var}.fontName = {font_js}; }} "
                f"catch (__e) {{ __errors.push({{eid:\"{err_eid_js}\", "
                f"kind:\"text_set_failed\", "
                f"error: String(__e && __e.message || __e)}}); }}"
            )
            # Baseline emits `<var>.fontSize = N;` when the IR's `style`
            # has a concrete fontSize value — the AST doesn't yet carry
            # typography (compressor M1a scope) so we skip it here. The
            # fontSize resolution lands with the rest of the typography
            # axis at M2 when compress_l3 starts emitting text props.

        m_key = spec_key_map.get(eid, eid)
        lines.append(f'M["{_escape_js(m_key)}"] = {var}.id;')
        lines.append("")

    return lines


def _collect_text_chars(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[str, str],
) -> dict[str, tuple[str, str]]:
    """Map eid → (var, escaped_text) for every text node with a
    positional literal value. Baseline emits these in Phase 2 after
    each node's `appendChild`.
    """
    out: dict[str, tuple[str, str]] = {}
    for node, _parent in walk:
        if node.head.type_or_path != "text":
            continue
        pos = node.head.positional
        if pos is None:
            continue
        py_value = getattr(pos, "py", None)
        if not isinstance(py_value, str) or not py_value:
            continue
        eid = node.head.eid
        out[eid] = (var_map[eid], _escape_js(py_value))
    return out


def _emit_phase2(
    walk: list[tuple[Node, Optional[Node]]],
    var_map: dict[str, str],
    text_chars: dict[str, tuple[str, str]],
    spec_key_map: dict[str, str],
    doc: L3Document,
    page_name: Optional[str],
) -> list[str]:
    """Phase 2 — wire tree via appendChild; emit text characters.

    The leading blank line is what separates Phase 1's last node-block
    from the Phase 2 section; it's part of phase2_lines in baseline
    (line 1475) for the same reason.
    """
    lines: list[str] = []
    lines.append("")
    lines.append("// Phase 2: Compose — wire tree, set layoutSizing")
    lines.append("await new Promise(r => setTimeout(r, 0));")
    lines.append("")

    for node, parent in walk:
        if parent is None:
            continue
        eid = node.head.eid
        if eid not in var_map:
            continue
        parent_eid = parent.head.eid
        if parent_eid not in var_map:
            continue
        child_var = var_map[eid]
        parent_var = var_map[parent_eid]
        lines.append(f"{parent_var}.appendChild({child_var});")
        if eid in text_chars:
            var, escaped = text_chars[eid]
            err_eid = spec_key_map.get(eid, eid)
            err_eid_js = _escape_js(err_eid)
            lines.append(
                f'try {{ {var}.characters = "{escaped}"; }} '
                f'catch (__e) {{ __errors.push({{eid:"{err_eid_js}", '
                f'kind:"text_set_failed", '
                f'error: String(__e && __e.message || __e)}}); }}'
            )

    if doc.top_level:
        root_eid = doc.top_level[0].head.eid
        root_var = var_map.get(root_eid)
        if root_var is not None:
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
                lines.append(f"_page.appendChild({root_var});")
                lines.append("await figma.setCurrentPageAsync(_page);")
            else:
                lines.append(f"_rootPage.appendChild({root_var});")

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
