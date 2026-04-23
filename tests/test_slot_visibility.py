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

import re
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
        #
        # Empirically on Dank (4996/4996 samples on 2026-04-22) the
        # shape is strictly `^\d+:\d+$` — two integer components
        # joined by `:`. Nested-override forms (e.g.
        # `5749:84278;5749:82462`) are flattened at resolver-build
        # time into one entry per descendant, so the `;` separator
        # never reaches the renderer. This gate enforces that
        # contract so a future regression (re-introducing the
        # raw compound form) surfaces immediately.
        fig_id_pattern = re.compile(r"\d+:\d+")
        for instance_eid, descendant_map in resolver.items():
            for path, fig_id in descendant_map.items():
                assert path.endswith(".visible")
                assert isinstance(fig_id, str)
                assert fig_id and ";" not in fig_id
                assert fig_id_pattern.fullmatch(fig_id), (
                    f"fig_id {fig_id!r} at "
                    f"{instance_eid!r}/{path!r} does not match "
                    f"Figma NNN:NNN id shape"
                )

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


# ---------------------------------------------------------------------------
# Stage 5 — Multi-backend stub test (backend-neutrality lock)
# ---------------------------------------------------------------------------


class TestMarkupIsBackendNeutral:
    """The markup layer carries intent — every backend adapter lowers
    the same AST to its native representation.

    This test pins the invariant by implementing a FAKE HTML renderer
    stub that reads the exact same markup the Figma renderer consumes
    and emits a stubby JSX-like output. The stub proves no Figma-
    specific data (e.g. `$ext.target_figma_id`) leaks into the markup;
    if it did, the HTML stub wouldn't know what to do with it.
    """

    def _fake_html_render(self, doc: L3Document) -> list[str]:
        """Minimal HTML adapter: walk the AST and emit a pseudo-JSX
        comment per compref + per visibility PathOverride. Real HTML
        rendering is out of scope — this stub only exercises the
        markup reading path.

        Reads PathOverrides from BOTH positions the grammar allows:
        head.properties (compressor-emitted) AND block.statements
        (author-emitted / round-tripped-from-emit).
        """
        out: list[str] = []

        def _emit_path_override(
            p: PathOverride, indent: str,
        ) -> None:
            if not p.path.endswith(".visible"):
                return
            descendant = p.path[:-len(".visible")]
            bool_py = getattr(p.value, "py", None)
            if bool_py is False:
                out.append(f'{indent}  {{/* hidden: {descendant} */}}')
            elif bool_py is True:
                out.append(f'{indent}  {{/* shown: {descendant} */}}')

        def walk(node: Node, depth: int = 0) -> None:
            indent = "  " * depth
            head = node.head
            if head.head_kind == "comp-ref":
                out.append(f'{indent}<{head.type_or_path}>')
                # PathOverrides on the compref head (compressor form)
                for p in head.properties:
                    if isinstance(p, PathOverride):
                        _emit_path_override(p, indent)
                # PathOverrides in the compref block (author form)
                if node.block is not None:
                    for s in node.block.statements:
                        if isinstance(s, PathOverride):
                            _emit_path_override(s, indent)
                out.append(f'{indent}</{head.type_or_path}>')
            elif head.head_kind == "type":
                out.append(f'{indent}<{head.type_or_path}>')
                if node.block is not None:
                    for s in node.block.statements:
                        if isinstance(s, Node):
                            walk(s, depth + 1)
                out.append(f'{indent}</{head.type_or_path}>')

        for item in doc.top_level:
            if isinstance(item, Node):
                walk(item)
        return out

    def test_fake_html_renderer_reads_same_markup_as_figma(self) -> None:
        """A fake HTML renderer stub consumes the exact same L3Document
        the Figma renderer does — no Figma-specific side-cars needed —
        and produces stub JSX comments indicating the would-be
        conditional render. Proves the markup layer is backend-neutral.
        """
        src = (
            "screen #s { "
            "-> nav/top-nav #n { "
            "logo-dank.visible = false "
            "share-icon.visible = true "
            "} "
            "}"
        )
        doc = parse_l3(src)

        html = self._fake_html_render(doc)
        html_text = "\n".join(html)

        # Every backend-neutral PathOverride is visible to the stub.
        assert "hidden: logo-dank" in html_text
        assert "shown: share-icon" in html_text
        assert "<nav/top-nav>" in html_text

        # Crucially: no Figma-specific identifiers leak through the
        # markup. The stub should see NO `findOne`, no `id.endsWith`,
        # no `;<node:id>` — those are Figma's private vocabulary.
        assert "findOne" not in html_text
        assert "endsWith" not in html_text
        # Semicolon-prefixed ids would be the fingerprint of a leaked
        # Figma node id. Absent.
        for line in html:
            # Allow semicolons in JSX comments as punctuation, but not
            # `;<digits>:<digits>` which is the Figma-id shape.
            assert not re.search(r';\d+:\d+', line), (
                f"Figma node id leaked into backend-neutral markup: {line}"
            )

    def test_same_markup_lowers_differently_per_backend(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """The same AST grammar (PathOverride `.visible=false` on a
        comp-ref) produces a FIGMA-specific `findOne(id.endsWith(...))`
        in one backend and a HTML-specific conditional-render comment
        in the other.

        V1 audit (2026-04-22) flagged the prior version of this test
        as hand-concat'ing a fake Figma lowering instead of invoking
        the real renderer. Now: the Figma branch runs the actual
        `render_figma` pipeline on a real DB-compressed screen with
        visibility overrides, and the HTML branch runs the stub
        adapter on hand-authored markup. The shared invariant is the
        grammar (PathOverride `.visible`), not the source bytes —
        backend-neutrality means the AST is a ground truth both
        adapters read, but each produces different native output."""
        from dd.compress_l3 import (
            compress_to_l3_with_maps, compress_to_l3_with_resolver,
        )
        from dd.ir import generate_ir, query_screen_visuals
        from dd.render_figma_ast import render_figma
        from dd.renderers.figma import collect_fonts

        # --- HTML branch: hand-authored markup via the stub ---
        html_src = (
            "screen #s { -> button/large #n { "
            "icon-delete.visible = false } }"
        )
        html_doc = parse_l3(html_src)
        html_lines = self._fake_html_render(html_doc)
        html_text = "\n".join(html_lines)
        assert "hidden: icon-delete" in html_text
        assert "findOne" not in html_text
        assert "endsWith" not in html_text

        # --- Figma branch: real render_figma on a real DB screen ---
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
        doc, eid_nid, node_nid, node_spec_key, node_original_name = (
            compress_to_l3_with_maps(spec, db_conn, screen_id=screen_id)
        )
        _, resolver = compress_to_l3_with_resolver(
            spec, db_conn, screen_id=screen_id,
        )
        fonts = collect_fonts(spec, db_visuals=db_visuals)
        figma_script, _refs = render_figma(
            doc, db_conn, node_nid,
            fonts=fonts,
            spec_key_map=node_spec_key,
            original_name_map=node_original_name,
            db_visuals=db_visuals,
            _spec_elements=spec.get("elements"),
            _spec_tokens=spec.get("tokens"),
            descendant_visibility_resolver=resolver,
        )

        # The Figma script uses its native vocabulary — findOne +
        # id.endsWith + .visible assignment — to lower the same
        # grammar construct (PathOverride .visible) that the HTML
        # stub renders as a JSX comment.
        assert "findOne" in figma_script, (
            "real Figma renderer must emit findOne for visibility "
            "PathOverrides"
        )
        assert "id.endsWith" in figma_script, (
            "real Figma renderer must use stable-id addressing"
        )
        assert ".visible" in figma_script, (
            "real Figma renderer must set the visible property"
        )

        # Per-backend vocabulary is strictly disjoint: HTML knows
        # nothing about findOne / id.endsWith, and Figma emits no
        # JSX-style `hidden: <name>` comments.
        assert "findOne" not in html_text
        assert "hidden: icon-delete" in html_text
        assert "hidden: icon-delete" not in figma_script
        # JSX comment syntax `{/* */}` never appears in Figma output
        assert "{/*" not in figma_script


def _find_instance_with_disambiguation(
    conn: sqlite3.Connection,
) -> tuple[int, list[str], str, list[str]] | None:
    """Scan `instance_overrides` for an instance whose emitted
    PathOverride paths actually exercise the `-N` disambiguation code
    path in ``_fetch_descendant_visibility_overrides`` (lines ~1638-
    1649 of dd/compress_l3.py).

    True disambiguation requires: the same descendant ``desc_eid``
    appears twice in the merged map, forcing the compressor to emit
    the bare ``<desc_eid>.visible`` once and ``<desc_eid>-2.visible``
    on the collision. Detect by shape of the resulting paths: group
    each path by stripping a trailing ``-N`` (N≥2) and require at
    least one group where the bare root is present alongside one or
    more ``-N`` siblings. Distinguishes genuine disambiguation from
    names that happen to contain ``-<digits>`` in the Figma source
    (e.g. ``ellipse-46`` — the ``-46`` is part of the Figma name,
    not an appended collision suffix).

    Returns ``(node_id, disambig_members, root_eid, all_paths)`` on
    the first match, or None if no real disambiguation occurs in the
    corpus (in which case the caller should skip).
    """
    from dd.compress_l3 import _fetch_descendant_visibility_overrides

    # All instances with ≥2 :visible overrides — disambiguation can
    # only fire when the instance has at least two descendants, and
    # even then usually not (most instances have distinctly-named
    # children). Bound to 500 to keep the test fast.
    rows = conn.execute(
        "SELECT node_id FROM instance_overrides "
        "WHERE property_type='BOOLEAN' "
        "  AND property_name LIKE ';%:visible' "
        "GROUP BY node_id HAVING COUNT(*) >= 2 "
        "LIMIT 500"
    ).fetchall()
    dedup_suffix = re.compile(r"^(.+)-(\d+)$")
    for row in rows:
        nid = row[0]
        overrides = _fetch_descendant_visibility_overrides(
            conn, {"target": nid}, ["target"],
        )
        paths = [po.path for po in overrides.get("target", [])]
        # Group by root
        groups: dict[str, list[str]] = {}
        for p in paths:
            if not p.endswith(".visible"):
                continue
            base = p[:-len(".visible")]
            m = dedup_suffix.match(base)
            if m and int(m.group(2)) >= 2:
                root = m.group(1)
            else:
                root = base
            groups.setdefault(root, []).append(base)
        for root, members in groups.items():
            # True disambig: bare root appears AND at least one -N sibling.
            if root in members and len(members) >= 2:
                return nid, sorted(members), root, paths
    return None


class TestSameNameDescendantsDisambiguated:
    def test_same_name_descendants_get_disambiguated(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Two descendants with the same original_name get disambiguated
        with `-N` suffixes so PathOverride paths remain unambiguous.

        This is the motivating fix: `logo/dank` appears twice under
        `nav/top-nav`. Emitting both as `logo-dank.visible=false`
        would be ambiguous — only one can be expressed. The compressor
        must emit `logo-dank.visible=false` AND
        `logo-dank-2.visible=false` (or equivalent distinct paths).

        V1 audit (2026-04-22) found the prior version of this test
        picked the FIRST instance with ≥2 visibility overrides, which
        typically has uniquely-named descendants — so the
        disambiguation code path never fired and the test was a
        uniqueness check over a trivially-unique list. This version
        explicitly seeks an instance whose paths contain a real
        collision (bare root + `-N` sibling)."""
        # Seek an instance that actually exercises the disambiguation
        # code path at dd/compress_l3.py:1638-1649.
        hit = _find_instance_with_disambiguation(db_conn)
        if hit is None:
            pytest.skip(
                "no instance in this corpus exercises -N disambiguation; "
                "not a real-data invariant but a code-path test"
            )
        nid, disambig_members, root, all_paths = hit

        # Invariant 1: paths are globally unique within the instance.
        assert len(all_paths) == len(set(all_paths)), (
            f"duplicate PathOverride paths for instance {nid}: "
            f"{all_paths}"
        )

        # Invariant 2: bare root + `-N` sibling both present — this
        # is the exact shape the compressor emits when two descendants
        # normalize to the same eid.
        assert root in disambig_members, (
            f"expected bare root {root!r} in disambig group "
            f"{disambig_members}"
        )
        n_suffixed = [
            m for m in disambig_members if m != root
        ]
        assert n_suffixed, (
            f"expected at least one `-N`-suffixed sibling for "
            f"root {root!r}; got {disambig_members}"
        )

        # Invariant 3: suffixes are sequential starting at 2 (no `-1`;
        # no gaps). This pins the exact disambiguation algorithm at
        # dd/compress_l3.py:1639 (n=2 then +1).
        suffixes = sorted(
            int(m.rsplit("-", 1)[1]) for m in n_suffixed
        )
        assert suffixes[0] == 2, (
            f"first disambig suffix must be 2 (not 1, not 0); got "
            f"{suffixes[0]} in {disambig_members}"
        )
        assert suffixes == list(range(2, 2 + len(suffixes))), (
            f"disambig suffixes must be sequential from 2 with no "
            f"gaps; got {suffixes} in {disambig_members}"
        )


class TestEmptyNodeGuardsInDefineBody:
    """V1 audit (2026-04-22) found an unguarded EmptyNode consumer in
    the Define-body branch of ``_check_function_names`` at
    ``dd/markup_l3.py:2673``. When a define body contains a direct
    ``slot = {empty}`` SlotFill statement, the semantic pass calls
    ``scan_node(stmt.node)`` without first checking
    ``isinstance(stmt.node, EmptyNode)`` — unlike the sibling branch
    at line 2649 which DOES guard. Result: AttributeError on valid
    grammar.

    The fix is a symmetric isinstance guard; these tests pin the
    invariant so future maintainers can't regress it.
    """

    def test_parse_define_with_empty_slot_body_does_not_crash(self) -> None:
        """Reproducer from V1 audit. Before fix: AttributeError."""
        from dd.markup_l3 import parse_l3
        src = "define my_pat() {\n  foo = {empty}\n}\n"
        # The parse itself is fine — the crash was in the semantic
        # pass that runs after parsing.
        doc = parse_l3(src)
        assert doc is not None

    def test_parse_define_with_mixed_empty_and_real_body_fills(self) -> None:
        """Multiple slot-fills in a body, some empty some real, all
        must survive the semantic pass without AttributeError."""
        from dd.markup_l3 import parse_l3
        src = (
            "define my_pat() {\n"
            "  leading = {empty}\n"
            "  label = frame #l\n"
            "  trailing = {empty}\n"
            "}\n"
        )
        doc = parse_l3(src)
        assert doc is not None

    def test_parse_nested_define_empty_roundtrip(self) -> None:
        """Round-trip: a define containing `{empty}` must emit and
        reparse cleanly."""
        from dd.markup_l3 import emit_l3, parse_l3
        src = "define my_pat() {\n  foo = {empty}\n}\n"
        doc1 = parse_l3(src)
        emitted = emit_l3(doc1)
        doc2 = parse_l3(emitted)
        # Structural equality — the semantic pass runs again on doc2.
        assert doc1.top_level == doc2.top_level
