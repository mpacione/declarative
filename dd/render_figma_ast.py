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

from dd.markup_l3 import L3Document
from dd.renderers.figma import (
    MISSING_COMPONENT_PLACEHOLDER_BLOCK,
    _collect_swap_targets_from_tree,
    _escape_js,
)


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
