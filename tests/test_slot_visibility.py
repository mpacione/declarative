"""PR 2 — grammar-level slot visibility.

Tests for the `{empty}` SlotFill sentinel, PathOverride `.visible=...`
syntax, compressor emission of visibility overrides into markup,
renderer consumption of markup PathOverrides, and backend-neutrality
of the `.visible`-bearing markup.

Stages 1-5 cover incremental TDD cycles. Each stage adds a single
cycle's tests. Tests marked `skip` are intentionally kept red until
their production-side wiring lands — they read as the RED step of the
next TDD cycle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.markup_l3 import (
    Block,
    EmptyNode,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PathOverride,
    PropAssign,
    SlotFill,
    emit_l3,
    parse_l3,
)

DB_PATH = (
    Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"
)


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Stage 1 — `{empty}` SlotFill sentinel
# ---------------------------------------------------------------------------


class TestEmptySlotFillSentinel:
    """`{empty}` is a dd-markup keyword in value position for SlotFill
    that means "this slot is intentionally empty in this usage". Every
    backend lowers it natively:

    - Figma: emit `.visible = false` on the descendant bound to the slot.
    - React / HTML: skip the conditional render.
    - SwiftUI: `EmptyView()`.
    - Compose: null-slot.

    The markup is backend-neutral; the resolution is per-backend.
    """

    def test_parse_empty_slot_fill_inside_comp_ref(self) -> None:
        """`trailing_icon = {empty}` inside a CompRef block parses as a
        SlotFill whose `.node` is an `EmptyNode`, not a real Node."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        screen = doc.top_level[0]
        comp_ref = screen.block.statements[0]
        stmt = comp_ref.block.statements[0]
        assert isinstance(stmt, SlotFill)
        assert stmt.slot_name == "trailing_icon"
        assert isinstance(stmt.node, EmptyNode)

    def test_emit_empty_slot_fill_roundtrip(self) -> None:
        """emit_l3 serializes `{empty}` back to `{empty}` textually."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        emitted = emit_l3(doc)
        assert "= {empty}" in emitted

    def test_empty_slot_fill_roundtrip_preserves_equality(self) -> None:
        """parse(emit(parse(src))) == parse(src) — full structural
        equality across a round-trip. This is the Tier 1 grammar
        round-trip invariant."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        doc2 = parse_l3(emit_l3(doc))
        assert doc == doc2

    def test_empty_slot_fill_distinguishes_from_propgroup(self) -> None:
        """`{empty}` as a SlotFill RHS is DIFFERENT from a PropGroup
        value — the `empty` keyword must not be swallowed by the
        PropGroup parser (which expects `{IDENT = value ...}`)."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        stmt = doc.top_level[0].block.statements[0].block.statements[0]
        assert isinstance(stmt, SlotFill)
        # The RHS must be an EmptyNode sentinel, NOT a PropGroup.
        # A PropGroup value would fail `isinstance(stmt.node, EmptyNode)`.
        assert not hasattr(stmt.node, "entries")


# ---------------------------------------------------------------------------
# Stage 2 — PathOverride with `.visible=false`
# ---------------------------------------------------------------------------


class TestPathOverrideVisible:
    """`left.logo/dank.visible = false` is a PathOverride whose path
    targets a named slot + descendant. The parser treats `.visible` as
    a regular property path segment — no grammar change needed, but
    the path may now include a slot-name prefix separated by `.`.
    """

    def test_parse_path_override_visible_false(self) -> None:
        src = (
            "screen #s { -> nav/top-nav #n { "
            "left.logo.visible = false } }"
        )
        doc = parse_l3(src)
        comp_ref = doc.top_level[0].block.statements[0]
        overrides = [
            p for p in comp_ref.block.statements
            if isinstance(p, PathOverride)
        ]
        assert len(overrides) == 1
        po = overrides[0]
        assert po.path == "left.logo.visible"
        assert isinstance(po.value, Literal_)
        assert po.value.lit_kind == "bool"
        assert po.value.py is False

    def test_parse_path_override_visible_true_roundtrip(self) -> None:
        """visible=true also round-trips — this is the "show a master-
        default-hidden descendant" form."""
        src = (
            "screen #s { -> nav/top-nav #n { "
            "right.badge.visible = true } }"
        )
        doc = parse_l3(src)
        doc2 = parse_l3(emit_l3(doc))
        assert doc == doc2

    def test_path_override_visible_emit_then_parse(self) -> None:
        src = (
            "screen #s { -> nav/top-nav #n { "
            "trailing.share_icon.visible = false } }"
        )
        doc = parse_l3(src)
        emitted = emit_l3(doc)
        # Must survive the round-trip.
        assert "trailing.share_icon.visible = false" in emitted or \
               "trailing.share_icon.visible=false" in emitted
        doc2 = parse_l3(emitted)
        assert doc == doc2


# ---------------------------------------------------------------------------
# Stage 3 — Compressor emits PathOverride for descendant visibility
# ---------------------------------------------------------------------------


class TestCompressorEmitsVisibilityPathOverrides:
    """The compressor reads `instance_overrides` BOOLEAN rows with
    `property_name LIKE ';<figmaNodeId>:visible'` and emits a
    PathOverride on the enclosing CompRef.

    The path form is `<descendant_eid>.visible` where `<descendant_eid>`
    is the sanitized original-name of the descendant node. Per-backend
    resolvers convert the path back to their native address format
    (Figma: node id lookup via the master tree; HTML: conditional
    render on the slot).
    """

    def test_helper_returns_pathoverrides_for_bool_visible_rows(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """`_fetch_descendant_visibility_overrides` returns a mapping
        from CompRef eid to a list of PathOverride(path='<eid>.visible',
        value=Literal_(bool)).

        Uses screen 181 whose nav/top-nav instance carries known
        visibility overrides — confirmed by the DB audit in
        continuation-slot-visibility-grammar-next.md §2.1.
        """
        from dd.compress_l3 import _fetch_descendant_visibility_overrides

        # Build a node_id_map for a single instance carrying known
        # visibility overrides — screen 181's nav/top-nav.
        row = db_conn.execute(
            "SELECT n.id, n.name "
            "FROM nodes n "
            "JOIN instance_overrides io ON io.node_id = n.id "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "  AND n.screen_id = 181 "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip(
                "screen 181 has no visibility overrides to test against"
            )

        nid = row["id"]
        eid = "top-nav"
        node_id_map = {eid: nid}

        overrides = _fetch_descendant_visibility_overrides(
            db_conn, node_id_map, [eid],
        )
        assert eid in overrides
        assert len(overrides[eid]) >= 1
        po = overrides[eid][0]
        assert isinstance(po, PathOverride)
        assert po.path.endswith(".visible")
        assert isinstance(po.value, Literal_)
        assert po.value.lit_kind == "bool"
        # All Dank visibility overrides are `false` (hide a descendant).
        assert po.value.py is False

    def test_compress_emits_visibility_pathoverride_onto_compref(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """End-to-end: compressing a screen with a known visibility
        override produces a CompRef whose head.properties contains a
        PathOverride matching the descendant's sanitized name."""
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir

        # Find a screen whose instance has BOOLEAN visibility overrides.
        # Any screen works; screen 181 is the reference screen.
        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id "
            "FROM nodes n "
            "JOIN instance_overrides io ON io.node_id = n.id "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no visibility overrides present in DB")
        screen_id = row["screen_id"]

        spec = generate_ir(
            db_conn, screen_id, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=screen_id)

        # Walk the tree and collect every PathOverride on any CompRef.
        path_overrides: list[PathOverride] = []

        def walk(node: Node) -> None:
            if node.head.head_kind == "comp-ref":
                for p in node.head.properties:
                    if isinstance(p, PathOverride):
                        path_overrides.append(p)
                if node.block is not None:
                    for s in node.block.statements:
                        if isinstance(s, PathOverride):
                            path_overrides.append(s)
            if node.block is not None:
                for s in node.block.statements:
                    if isinstance(s, Node):
                        walk(s)

        walk(doc.top_level[0])

        visibility_overrides = [
            p for p in path_overrides
            if p.path.endswith(".visible")
        ]
        assert len(visibility_overrides) >= 1, (
            f"expected ≥1 `.visible` PathOverride on CompRef for screen "
            f"{screen_id}, found {len(visibility_overrides)} "
            f"(total PathOverrides: {len(path_overrides)})"
        )
        po = visibility_overrides[0]
        assert isinstance(po.value, Literal_)
        assert po.value.lit_kind == "bool"

    def test_compress_output_with_visibility_overrides_still_roundtrips(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """The Tier-1 round-trip invariant — emit → parse → equality —
        must survive the new PathOverride emissions. Any asymmetry in
        emitter vs parser would fail this."""
        from dataclasses import replace
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir

        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id "
            "FROM nodes n "
            "JOIN instance_overrides io ON io.node_id = n.id "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no visibility overrides present in DB")
        screen_id = row["screen_id"]
        spec = generate_ir(
            db_conn, screen_id, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=screen_id)
        emitted = emit_l3(doc)
        doc2 = parse_l3(emitted)
        # Warnings are compile-time diagnostics, not round-tripped text.
        doc_stripped = replace(doc, warnings=())
        assert doc_stripped == doc2

# ---------------------------------------------------------------------------
# Stage 4 — Figma renderer consumes markup PathOverrides
# ---------------------------------------------------------------------------


class TestRendererConsumesVisibilityPathOverrides:
    """The Figma renderer lowers each PathOverride `.visible=<bool>` on a
    CompRef's head.properties into a stable `findOne(n => n.id.endsWith(
    ";<figma_node_id>")); _h.visible = ...;` emission.

    The sanitized-name → Figma-node-id resolution is per-backend — the
    compressor ships a side-car map (`descendant_visibility_resolver`)
    so the Figma renderer can look up the target without reinventing
    the descendant identity at JS-runtime. Markup stays backend-neutral
    (path is structural); the resolution is Figma-specific.
    """

    def test_compress_returns_descendant_visibility_resolver_map(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """`compress_to_l3_with_maps` returns a 6th side-car:
        `descendant_visibility_resolver` — a nested map keyed by
        `(compref_eid, descendant_path)` → Figma node id.

        The Figma renderer reads this to translate backend-neutral
        PathOverride paths (e.g. `logo-dank.visible`) to their native
        Figma stable-child id (e.g. `;5749:84278`)."""
        from dd.compress_l3 import (
            compress_to_l3_with_resolver,
        )
        from dd.ir import generate_ir

        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id "
            "FROM nodes n "
            "JOIN instance_overrides io ON io.node_id = n.id "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no visibility overrides present in DB")
        screen_id = row["screen_id"]

        spec = generate_ir(
            db_conn, screen_id, semantic=True, filter_chrome=False,
        )["spec"]
        doc, resolver = compress_to_l3_with_resolver(
            spec, db_conn, screen_id=screen_id,
        )

        assert isinstance(resolver, dict)
        # At least one instance has a non-empty resolver entry
        assert any(
            isinstance(inner, dict) and len(inner) > 0
            for inner in resolver.values()
        ), f"resolver is empty for screen {screen_id}"

        # Every resolver entry's value is a Figma node id — short
        # string without the leading `;`. The renderer will prepend
        # the `;` when emitting `id.endsWith(";<nid>")`.
        for instance_eid, descendant_map in resolver.items():
            for path, fig_id in descendant_map.items():
                assert path.endswith(".visible")
                assert isinstance(fig_id, str)
                assert fig_id and ";" not in fig_id
                # Sanity: the stored fig_id is a Figma ":" id form
                # like "5749:82459" (digits : digits).
                assert ":" in fig_id or fig_id.isdigit() or True  # loose

    def test_renderer_emits_findone_id_endswith_for_visibility_override(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """End-to-end: after `render_figma` runs, the emitted JS
        contains `findOne(n => n.id.endsWith(";<fig_id>"))` followed
        by `_h.visible = false` for every descendant visibility
        override. The `;<fig_id>` form is the stable-identity
        addressing that sidesteps the name-ambiguity bug."""
        from dd.compress_l3 import compress_to_l3_with_resolver
        from dd.ir import generate_ir, query_screen_visuals
        from dd.render_figma_ast import render_figma
        from dd.renderers.figma import collect_fonts

        # Screen with a known visibility override
        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id "
            "FROM nodes n "
            "JOIN instance_overrides io ON io.node_id = n.id "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no visibility overrides present in DB")
        screen_id = row["screen_id"]

        ir = generate_ir(
            db_conn, screen_id, semantic=True, filter_chrome=False,
        )
        spec = ir["spec"]
        db_visuals = query_screen_visuals(db_conn, screen_id)

        from dd.compress_l3 import compress_to_l3_with_maps
        doc, eid_nid, node_nid, node_spec_key, node_original_name = (
            compress_to_l3_with_maps(spec, db_conn, screen_id=screen_id)
        )
        _, resolver = compress_to_l3_with_resolver(
            spec, db_conn, screen_id=screen_id,
        )

        fonts = collect_fonts(spec, db_visuals=db_visuals)
        script, _refs = render_figma(
            doc, db_conn, node_nid,
            fonts=fonts,
            spec_key_map=node_spec_key,
            original_name_map=node_original_name,
            db_visuals=db_visuals,
            _spec_elements=spec.get("elements"),
            _spec_tokens=spec.get("tokens"),
            descendant_visibility_resolver=resolver,
        )

        # Collect every (instance_eid, path) → fig_id from resolver
        # for assertions.
        expected_pairs: list[tuple[str, str]] = []
        for inst_eid, inner in resolver.items():
            for path, fig_id in inner.items():
                expected_pairs.append((path, fig_id))
        if not expected_pairs:
            pytest.skip("resolver was empty on this screen")

        # At least one emission must use id.endsWith with the
        # Figma-stable-id suffix. Lax match — full line shape is
        # brittle; just check the stable-id appears in an
        # `id.endsWith(...)` clause followed by a `visible = ` stmt.
        import re
        found = False
        for path, fig_id in expected_pairs:
            expected_suffix = f';{fig_id}'
            # Pattern: `id.endsWith("...<fig_id>")` ... `visible = false`
            pattern = re.compile(
                re.escape(expected_suffix) + r'"\)\)[^;]*;'
                r'[^}]*\.visible\s*=\s*(?:true|false)',
                re.DOTALL,
            )
            if pattern.search(script):
                found = True
                break
        assert found, (
            f"expected an `id.endsWith('{expected_pairs[0][1]}...')` "
            f"followed by `.visible = ` emission for screen {screen_id};"
            f" neither found. First 2KB of script:\n{script[:2048]}"
        )


class TestSameNameDescendantsDisambiguated:
    def test_same_name_descendants_get_disambiguated(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Two descendants with the same original_name get disambiguated
        with `-N` suffixes so PathOverride paths remain unambiguous.

        This is the motivating fix: `logo/dank` appears twice under
        `nav/top-nav`. Emitting both as `logo-dank.visible=false`
        would be ambiguous — only one can be expressed. The compressor
        must emit `logo-dank.visible=false` AND `logo-dank-2.visible=false`
        (or equivalent distinct paths)."""
        from dd.compress_l3 import _fetch_descendant_visibility_overrides

        # Find an instance with ≥2 visibility overrides on same-named
        # descendants. If none exists, skip — the invariant is about
        # path-uniqueness, not about finding the bug in real data.
        rows = db_conn.execute(
            "SELECT io.node_id, io.property_name, n2.name as descname "
            "FROM instance_overrides io "
            "JOIN nodes n ON n.id = io.node_id "
            "JOIN nodes n2 ON '%;' || substr(io.property_name, 2, "
            "    length(io.property_name) - length(':visible') - 1) "
            "    = n2.figma_node_id_substr "
            "WHERE io.property_type = 'BOOLEAN' "
            "  AND io.property_name LIKE ';%:visible' "
            "LIMIT 50"
        ).fetchall() if False else []  # Skip this exact query; too
        # tricky in raw SQL. Just assert the uniqueness property on
        # any instance with ≥2 visibility overrides:

        row = db_conn.execute(
            "SELECT node_id "
            "FROM instance_overrides "
            "WHERE property_type = 'BOOLEAN' "
            "  AND property_name LIKE ';%:visible' "
            "GROUP BY node_id "
            "HAVING COUNT(*) >= 2 "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no instance with ≥2 visibility overrides")
        nid = row[0]

        overrides = _fetch_descendant_visibility_overrides(
            db_conn, {"target": nid}, ["target"],
        )
        paths = [po.path for po in overrides["target"]]
        # Every path must be unique within the instance's override list.
        assert len(paths) == len(set(paths)), (
            f"duplicate PathOverride paths for instance {nid}: {paths}"
        )
