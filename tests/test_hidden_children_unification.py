"""PR 1 — unify descendant-visibility data sourcing.

Before PR 1 there were two parallel pipelines for descendant-visibility
data:

- `instance_overrides` BOOLEAN `;<fid>:visible` rows, lowered by the PR-2
  resolver into backend-neutral PathOverrides.
- `hidden_children` — a name-based descendant walk populated by
  `ir.query_screen_visuals`, lowered by the renderer into brittle
  `findOne(n => n.name === X)` calls.

Per subagent B's 2026-04-22 audit of the Dank corpus (19,849 hides):

- 39.3% covered by `instance_overrides`.
- 60.7% NOT covered:
  - H1 master-default (77.6% of the gap) — the master itself has
    `visible=0` at this descendant. Rendered faithfully as long as the
    renderer doesn't clobber master defaults; no instance override
    needed.
  - H2 hereditary (1.4%) — a hidden ancestor inside the instance
    already hides this descendant. Redundant — filtering reduces
    emission noise.
  - H3 plugin-not-captured (18.8% = 2,041 cases) — DB `nodes.visible=0`
    but no `instance_overrides` row. Must be covered by the unified
    resolver or these descendants regress.

PR 1 extends `_fetch_descendant_visibility_overrides` to cover H3 via
a second DB-walk query AND filters H2 so the resolver is a drop-in
replacement for `hidden_children`.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd import db as dd_db
from dd.compress_l3 import _fetch_descendant_visibility_overrides
from dd.markup_l3 import Literal_, PathOverride


# ---------------------------------------------------------------------------
# Fixture helpers — synthetic instance subtrees
# ---------------------------------------------------------------------------


def _insert_screen(conn: sqlite3.Connection, screen_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO files (id, file_key, name, node_count, "
        "screen_count) VALUES (?, ?, ?, ?, ?)",
        (1, "fk_test", "Test File", 100, 5),
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, "
        "width, height) VALUES (?, ?, ?, ?, ?, ?)",
        (screen_id, 1, f"S{screen_id}:1", f"Screen {screen_id}",
         375, 812),
    )


def _insert_node(
    conn: sqlite3.Connection,
    node_id: int,
    screen_id: int,
    figma_node_id: str,
    parent_id: int | None,
    name: str,
    node_type: str,
    *,
    visible: int = 1,
    component_key: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, parent_id, path, name, "
        " node_type, depth, sort_order, visible, component_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (node_id, screen_id, figma_node_id, parent_id, f"/root/{name}",
         name, node_type, 0, 0, visible, component_key),
    )


def _insert_override(
    conn: sqlite3.Connection,
    node_id: int,
    property_name: str,
    override_value: str,
    property_type: str = "BOOLEAN",
) -> None:
    conn.execute(
        "INSERT INTO instance_overrides "
        "(node_id, property_type, property_name, override_value) "
        "VALUES (?, ?, ?, ?)",
        (node_id, property_type, property_name, override_value),
    )


# ---------------------------------------------------------------------------
# Stage 1 — H3 coverage (DB visible=0 with no instance_override row)
# ---------------------------------------------------------------------------


class TestH3Coverage:
    """The resolver must cover H3 — descendants hidden via
    `nodes.visible=0` but lacking a matching `instance_overrides` row.

    Figma's Plugin API `overrides` channel does not emit transitive
    master-default visibility; relying on `instance_overrides` alone
    drops 18.8% of hides in the Dank corpus (2,041 cases) — mostly
    deeply-nested icons inside component nav chains.
    """

    def test_resolver_covers_h3_nodes_visible_zero_without_instance_override(
        self,
    ) -> None:
        """Fabricate an instance whose descendant has `nodes.visible=0`
        and NO `instance_overrides` row. Resolver must emit a
        PathOverride `<descendant>.visible=false`.
        """
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 100, 1, "1:100", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        # Descendant hidden via nodes.visible=0, NO instance_override
        _insert_node(
            conn, 101, 1, "I1:100;1:201", 100, "icon/wallet", "INSTANCE",
            visible=0,
        )
        conn.commit()

        node_id_map = {"top-nav": 100}
        resolver_out: dict[str, dict[str, str]] = {}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
            resolver_out=resolver_out,
        )

        assert "top-nav" in overrides, (
            "H3 descendant (nodes.visible=0, no instance_override) must "
            "produce a PathOverride; got empty bucket"
        )
        bucket = overrides["top-nav"]
        assert len(bucket) == 1
        po = bucket[0]
        assert isinstance(po, PathOverride)
        assert po.path.startswith("icon-wallet")
        assert po.path.endswith(".visible")
        assert isinstance(po.value, Literal_)
        assert po.value.py is False

        # Resolver side-car must also populate the Figma-stable-id map
        # for this H3 path so the renderer can emit `id.endsWith(";...")`.
        assert "top-nav" in resolver_out
        assert po.path in resolver_out["top-nav"]
        # The descendant's stable-child suffix is the last `;`-segment.
        assert resolver_out["top-nav"][po.path] == "1:201"
        conn.close()

    def test_resolver_covers_h3_nested_depth_three(self) -> None:
        """H3 coverage must extend to arbitrary descendant depth — most
        of the 2,041 corpus H3 cases are at depth 3 (1,624 of 2,041)."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 200, 1, "1:200", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        _insert_node(
            conn, 201, 1, "I1:200;1:300", 200, "right", "FRAME",
        )
        _insert_node(
            conn, 202, 1, "I1:200;1:300;1:301", 201, "icon-group", "FRAME",
        )
        # Hidden at depth 3
        _insert_node(
            conn, 203, 1, "I1:200;1:300;1:301;1:302", 202,
            "Buy Trophy", "INSTANCE", visible=0,
        )
        conn.commit()

        node_id_map = {"top-nav": 200}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
        )
        assert "top-nav" in overrides
        paths = [po.path for po in overrides["top-nav"]]
        # The deepest hidden descendant must be covered.
        assert any(p.startswith("buy-trophy") and p.endswith(".visible")
                   for p in paths), (
            f"expected buy-trophy.visible in paths, got {paths}"
        )
        conn.close()

    def test_resolver_combines_instance_override_and_db_visible_sources(
        self,
    ) -> None:
        """Both sources feed the same resolver — an instance with a mix
        of `instance_overrides` AND `nodes.visible=0` descendants sees
        both hides emitted."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 300, 1, "1:300", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        # Source A: instance_overrides
        _insert_node(
            conn, 301, 1, "I1:300;1:400", 300, "share-icon", "INSTANCE",
            visible=1,
        )
        _insert_override(conn, 300, ";1:400:visible", "false")
        # Source B: DB visible=0 only (no instance_override)
        _insert_node(
            conn, 302, 1, "I1:300;1:401", 300, "download-icon", "INSTANCE",
            visible=0,
        )
        conn.commit()

        node_id_map = {"top-nav": 300}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
        )
        assert "top-nav" in overrides
        paths = {po.path for po in overrides["top-nav"]}
        # Both descendants must be covered.
        assert any(p.startswith("share-icon") for p in paths), paths
        assert any(p.startswith("download-icon") for p in paths), paths
        conn.close()


# ---------------------------------------------------------------------------
# Stage 1 — H2 filter (hereditary hides inside an instance)
# ---------------------------------------------------------------------------


class TestH2Filter:
    """H2 hereditary hides — descendants whose hidden ancestor is
    ALREADY inside the instance subtree — are redundant. Hiding the
    ancestor already hides all descendants; emitting a second override
    for each one adds pure script noise and risks ordering bugs.

    Per subagent B: 174 of 12,050 uncovered cases (1.4%) are H2.
    Filtering them reduces emission size on nav-heavy screens.
    """

    def test_resolver_filters_h2_hereditary_hides(self) -> None:
        """When an ancestor inside the instance subtree is already
        hidden, the descendant's own `.visible=false` must NOT be
        emitted — hiding the ancestor already hides the descendant."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 400, 1, "1:400", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        # Ancestor (hidden)
        _insert_node(
            conn, 401, 1, "I1:400;1:500", 400, "right", "FRAME",
            visible=0,
        )
        # Descendant of the hidden ancestor — also hidden in DB but
        # redundantly so. Must be filtered.
        _insert_node(
            conn, 402, 1, "I1:400;1:500;1:501", 401, "icon-wallet",
            "INSTANCE", visible=0,
        )
        conn.commit()

        node_id_map = {"top-nav": 400}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
        )
        paths = {po.path for po in overrides.get("top-nav", [])}
        # The ancestor's hide MUST be present.
        assert any(p.startswith("right") and p.endswith(".visible")
                   for p in paths), (
            f"expected ancestor `right.visible` hide, got {paths}"
        )
        # The redundant descendant hide MUST NOT be present.
        assert not any(p.startswith("icon-wallet") for p in paths), (
            f"H2 hereditary descendant leaked through filter: {paths}"
        )
        conn.close()


# ---------------------------------------------------------------------------
# Stage 1 — Dedupe: instance_override + DB visible=0 for same node
# ---------------------------------------------------------------------------


class TestResolverDedupe:
    """When a descendant has BOTH an instance_override row AND
    `nodes.visible=0` in the DB, the resolver must emit ONE
    PathOverride — not two. Dedupe by figma_node_id suffix.

    The instance_overrides source takes precedence on conflict; its
    override_value is the authoritative per-instance delta.
    """

    def test_resolver_distinguishes_instance_override_from_master_default(
        self,
    ) -> None:
        """If both sources say `visible=false`, emit once. If the
        instance_override says `true` on a DB-master-hidden descendant,
        emit `.visible=true` (the instance wants to show what the
        master hides) — the instance_override always wins."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 500, 1, "1:500", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        # Case A: instance_override=false AND DB visible=0 — dedupe, emit once
        _insert_node(
            conn, 501, 1, "I1:500;1:600", 500, "dup-both-false", "INSTANCE",
            visible=0,
        )
        _insert_override(conn, 500, ";1:600:visible", "false")
        # Case B: instance_override=true on DB-hidden descendant — emit once
        # with value=true (the instance's intent wins)
        _insert_node(
            conn, 502, 1, "I1:500;1:700", 500, "show-me", "INSTANCE",
            visible=0,
        )
        _insert_override(conn, 500, ";1:700:visible", "true")
        conn.commit()

        node_id_map = {"top-nav": 500}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
        )
        bucket = overrides.get("top-nav", [])

        # Deduplicate by path
        by_path: dict[str, PathOverride] = {}
        for po in bucket:
            assert po.path not in by_path, (
                f"duplicate PathOverride path {po.path!r} — "
                f"resolver should dedupe"
            )
            by_path[po.path] = po

        # Case A: one emission, value=false
        a_pos = [p for p in by_path if p.startswith("dup-both-false")]
        assert len(a_pos) == 1, (
            f"Case A expected exactly 1 entry, got {a_pos}"
        )
        assert by_path[a_pos[0]].value.py is False

        # Case B: one emission, value=true (instance_override wins)
        b_pos = [p for p in by_path if p.startswith("show-me")]
        assert len(b_pos) == 1, (
            f"Case B expected exactly 1 entry, got {b_pos}"
        )
        assert by_path[b_pos[0]].value.py is True, (
            "instance_override=true on master-hidden descendant must win; "
            "got false"
        )
        conn.close()


# ---------------------------------------------------------------------------
# Stage 2 — Production renderer emits id-based visibility via resolver
# ---------------------------------------------------------------------------


DANK_DB_PATH = (
    "/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db"
)


@pytest.fixture(scope="module")
def dank_conn() -> sqlite3.Connection:
    """Open the real Dank corpus DB for Stage 2's production-wiring
    test. Skip the test gracefully when the corpus isn't available
    (CI, fresh clones without the proprietary extraction)."""
    from pathlib import Path
    p = Path(DANK_DB_PATH)
    if not p.exists():
        pytest.skip(f"corpus DB not present at {p}")
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestProductionRendererUsesResolver:
    """The production `generate_figma_script` must thread the
    `descendant_visibility_resolver` through to `render_figma` so the
    emitted script uses `findOne(n => n.id.endsWith(";<fig_id>"))`
    rather than `findOne(n => n.name === X)` for descendant hides.

    Without the resolver, the renderer silently falls back to the
    markup-unaware `hidden_children` path — and when a master has two
    same-name descendants with different visibility intent (e.g.
    nav/top-nav's `icon/check` where one copy is hidden and the other
    is shown), name-based lookup hits the wrong descendant.
    """

    def test_generate_figma_script_emits_id_based_visibility_override_not_name_based(
        self, dank_conn: sqlite3.Connection,
    ) -> None:
        """Screen 118 has a nav/top-nav instance with same-name
        descendants at conflicting visibilities (confirmed by the
        2026-04-22 subagent-B audit). The production `generate_screen`
        must thread `descendant_visibility_resolver` to `render_figma`
        so the markup-PathOverride emitter fires — producing distinctive
        `{ const _h = <var>.findOne(n => n.id.endsWith(";<fig>"))` lines
        for any resolver-known hide that lands on a walked CompRef.

        Without the Stage-2 wiring the emitter is a no-op (resolver
        param defaults to `None`) and the script carries zero such
        emissions despite the markup containing `.visible` PathOverrides.
        """
        import re
        from dd.renderers.figma import generate_screen

        result = generate_screen(
            dank_conn, 118, canvas_position=(0, 0),
        )
        script = result["structure_script"]

        # PR-2 emitter signature — `{ const _h = <var>.findOne(n =>
        # n.id.endsWith(";<fig_id>")); if (_h) _h.visible = ...; }`.
        # This shape is distinct from _emit_override_tree (uses `_c`)
        # and from hidden_children (uses `n.name ===`).
        pr2_emitter_pat = re.compile(
            r'\{ const _h = \S+\.findOne\(n => '
            r'n\.id\.endsWith\("[^"]+"\)\);'
            r'\s*if \(_h\) _h\.visible = (?:true|false);'
        )
        pr2_hits = pr2_emitter_pat.findall(script)
        assert len(pr2_hits) >= 1, (
            f"expected ≥1 markup-PathOverride id-based emission on "
            f"screen 118; got 0. Production path must thread "
            f"descendant_visibility_resolver into render_figma. "
            f"First 2KB of script:\n{script[:2048]}"
        )


# ---------------------------------------------------------------------------
# Stage 3 — `hidden_children` name-based path is fully removed
# ---------------------------------------------------------------------------


class TestHiddenChildrenPathRemoved:
    """Stage 3 deletes the legacy `hidden_children` SQL builder + the
    two renderer emitter blocks that consumed it. After this lands,
    the ONLY remaining name-based `findOne(n => n.name === X); _h.visible = false`
    emission in the whole codebase is either a diagnostic string or
    belongs to a non-visibility override (e.g. text_target). Visibility
    hides are exclusively id-based via the unified resolver.
    """

    def test_hidden_children_sql_no_longer_emits_name_based_finders(
        self, dank_conn: sqlite3.Connection,
    ) -> None:
        """The generated script for screen 118 must contain ZERO
        `findOne(n => n.name === X); _h.visible = false` emissions.
        Every descendant hide must flow through the resolver's id-
        based path instead.

        Screen 118's nav/top-nav has 15 same-name `Skip` descendants
        under it (8 hidden) — the canonical case where name-based
        lookup picks the wrong child and hides a visible one.
        """
        import re
        from dd.renderers.figma import generate_screen

        result = generate_screen(
            dank_conn, 118, canvas_position=(0, 0),
        )
        script = result["structure_script"]

        # Any occurrence of `findOne(n => n.name === "X")` followed on
        # the same line by a `.visible = <bool>` write is the
        # `hidden_children` emission pattern the unified resolver
        # replaces. Stage 3 deletes that emitter; the count must be 0.
        name_based_visibility = re.findall(
            r'findOne\(n => n\.name === "[^"]+"\)'
            r'[^;]*;\s*[^}]*\.visible\s*=\s*(?:true|false)',
            script,
            re.DOTALL,
        )
        assert name_based_visibility == [], (
            f"expected 0 name-based `.visible=...` emissions on "
            f"screen 118 after Stage 3 removes `hidden_children`; "
            f"got {len(name_based_visibility)}. First mismatch:\n"
            f"{name_based_visibility[0][:300] if name_based_visibility else ''}"
        )

    def test_hidden_children_builder_returns_no_hidden_children_key(
        self, dank_conn: sqlite3.Connection,
    ) -> None:
        """`query_screen_visuals` no longer populates the
        `hidden_children` dict key — the builder is deleted. Any
        downstream code that reads `raw_visual.get("hidden_children")`
        sees `None`, which is the safe fallback."""
        from dd.ir import query_screen_visuals

        visuals = query_screen_visuals(dank_conn, 118)
        hc_lists = [
            (nid, v.get("hidden_children"))
            for nid, v in visuals.items()
            if v.get("hidden_children")
        ]
        assert hc_lists == [], (
            f"expected 0 `hidden_children` entries after Stage 3 deletes "
            f"the builder; got {len(hc_lists)} from visuals table. "
            f"First 3 offenders: {hc_lists[:3]}"
        )


# ---------------------------------------------------------------------------
# Stage 4 — Acceptance pins for the subagent-B H3 classes
# ---------------------------------------------------------------------------


class TestH3AcceptancePins:
    """Regression pins for the three largest H3 descendant-name
    classes in the Dank corpus (2026-04-22 subagent-B audit):

    - `icon/wallet` — 1,636 occurrences, overwhelmingly inside nested
      `nav/top-nav` chains. Depth 3 cases dominate.
    - `Buy Trophy` — 209 occurrences inside button/medium-translucent
      instances.
    - `icon/close` — 90 occurrences inside button/large/translucent.

    These tests use synthetic fixtures to reproduce the depth-1
    direct-slot shape (325 corpus cases sit at this depth). Each
    asserts that compress → render emits an id-based visibility
    hide for the descendant. A future regression silently dropping
    H3 coverage would fire these pins instantly.

    Production-grade end-to-end coverage (the real Dank nav chains
    at depth 3) is already pinned by
    `TestProductionRendererUsesResolver.test_generate_figma_script_...`
    above. Stage 4 adds tight, deterministic fixtures that don't
    depend on the corpus DB.
    """

    def _build_h3_instance(
        self,
        descendant_name: str,
        *,
        inst_node_id: int = 900,
        desc_node_id: int = 901,
        inst_figma_id: str = "5749:1000",
        desc_figma_suffix: str = "5749:2000",
    ) -> tuple[sqlite3.Connection, dict[str, int]]:
        """Minimal schema: one screen, one classified INSTANCE with a
        single DB-hidden descendant. No `instance_overrides` row —
        this is the H3 shape (Figma Plugin API didn't capture the
        master-default hide)."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, inst_node_id, 1, inst_figma_id, None,
            "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        _insert_node(
            conn, desc_node_id, 1,
            f"I{inst_figma_id};{desc_figma_suffix}",
            inst_node_id,
            descendant_name, "INSTANCE", visible=0,
        )
        conn.commit()
        return conn, {"top-nav": inst_node_id}

    def _assert_h3_hide_emitted(
        self,
        descendant_name: str,
        expected_path_prefix: str,
        desc_figma_suffix: str = "5749:2000",
    ) -> None:
        """Compress + assert a `<path_prefix>.visible=false` emission
        with a resolver entry pointing at `desc_figma_suffix`."""
        conn, node_id_map = self._build_h3_instance(
            descendant_name,
            desc_figma_suffix=desc_figma_suffix,
        )
        resolver_out: dict[str, dict[str, str]] = {}
        overrides = _fetch_descendant_visibility_overrides(
            conn, node_id_map, ["top-nav"],
            resolver_out=resolver_out,
        )
        try:
            assert "top-nav" in overrides, (
                f"H3 pin for descendant {descendant_name!r}: resolver "
                f"produced no PathOverride; expected ≥1"
            )
            bucket = overrides["top-nav"]
            paths = [po.path for po in bucket]
            assert any(
                p.startswith(expected_path_prefix) and p.endswith(".visible")
                for p in paths
            ), (
                f"H3 pin for descendant {descendant_name!r}: expected "
                f"a path starting with {expected_path_prefix!r}; got "
                f"{paths}"
            )
            # The resolver must map that path to the descendant's
            # Figma stable-child id (last `;`-segment), which the
            # renderer lowers to `id.endsWith(";<fig>")`.
            resolver_bucket = resolver_out.get("top-nav", {})
            matched_path = next(
                p for p in paths
                if p.startswith(expected_path_prefix)
                and p.endswith(".visible")
            )
            assert resolver_bucket.get(matched_path) == desc_figma_suffix, (
                f"H3 pin for descendant {descendant_name!r}: resolver "
                f"path→fig_id mapping wrong; got "
                f"{resolver_bucket.get(matched_path)!r}, expected "
                f"{desc_figma_suffix!r}"
            )
        finally:
            conn.close()

    def test_h3_pin_icon_wallet_hidden_at_depth_one(self) -> None:
        """`icon/wallet` is the largest H3 class (1,636 corpus hits).
        A silent regression here would re-surface a hidden wallet
        icon on every screen that classifies it into a nav chain."""
        self._assert_h3_hide_emitted(
            "icon/wallet", "icon-wallet",
        )

    def test_h3_pin_icon_close_hidden_at_depth_one(self) -> None:
        """`icon/close` — 90 cases inside button/large/translucent
        instances."""
        self._assert_h3_hide_emitted(
            "icon/close", "icon-close",
        )

    def test_h3_pin_buy_trophy_hidden_at_depth_one(self) -> None:
        """`Buy Trophy` — 209 cases inside button/medium-translucent."""
        self._assert_h3_hide_emitted(
            "Buy Trophy", "buy-trophy",
        )

    def test_h3_pin_multiple_descendants_per_instance(self) -> None:
        """Real corpus instances frequently have multiple H3 hides in
        a row (e.g. nav/top-nav's `icon/wallet` + `Buy Trophy` +
        `icon/close` all hidden together). Pin that the resolver
        emits one entry per hidden descendant with no cross-talk."""
        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        _insert_node(
            conn, 1000, 1, "5749:3000", None, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        _insert_node(
            conn, 1001, 1, "I5749:3000;5749:3100", 1000,
            "icon/wallet", "INSTANCE", visible=0,
        )
        _insert_node(
            conn, 1002, 1, "I5749:3000;5749:3200", 1000,
            "Buy Trophy", "INSTANCE", visible=0,
        )
        _insert_node(
            conn, 1003, 1, "I5749:3000;5749:3300", 1000,
            "icon/close", "INSTANCE", visible=0,
        )
        # A visible sibling that must NOT appear in the hide list.
        _insert_node(
            conn, 1004, 1, "I5749:3000;5749:3400", 1000,
            "share-icon", "INSTANCE", visible=1,
        )
        conn.commit()

        overrides = _fetch_descendant_visibility_overrides(
            conn, {"top-nav": 1000}, ["top-nav"],
        )
        paths = {po.path for po in overrides.get("top-nav", [])}
        assert any(p.startswith("icon-wallet") for p in paths), paths
        assert any(p.startswith("buy-trophy") for p in paths), paths
        assert any(p.startswith("icon-close") for p in paths), paths
        # Visible sibling is NOT hidden
        assert not any(p.startswith("share-icon") for p in paths), (
            f"visible sibling share-icon leaked into hide list: {paths}"
        )
        conn.close()

    def test_h3_pin_end_to_end_emission_in_markup_ast(self) -> None:
        """Full compress → render path: a synthetic screen with one
        H3 descendant must produce markup with a `.visible=false`
        PathOverride AND a resolver entry mapping it to the descendant
        Figma id. Exercises every pipe piece short of the live Figma
        bridge (verified via `TestProductionRendererUsesResolver`)."""
        from dd.compress_l3 import compress_to_l3_with_resolver
        from dd.markup_l3 import Node, PathOverride

        conn = dd_db.init_db(":memory:")
        _insert_screen(conn, 1)
        # Root screen frame wrapping the instance — matches the
        # compressor's synthetic-screen-wrapper collapse shape.
        _insert_node(
            conn, 1, 1, "S1:1", None, "screen-root", "FRAME",
        )
        _insert_node(
            conn, 1100, 1, "5749:5000", 1, "top-nav", "INSTANCE",
            component_key="ck_top_nav",
        )
        _insert_node(
            conn, 1101, 1, "I5749:5000;5749:5100", 1100,
            "icon/wallet", "INSTANCE", visible=0,
        )
        # Component key registry entry so the compressor resolves
        # `ck_top_nav` to `top-nav` for the Mode-1 comp-ref head.
        # Created ad-hoc because `dd.db.init_db` doesn't ship the
        # table — it's built by `dd.templates.rebuild_ckr` in the real
        # pipeline.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry ("
            "component_key TEXT PRIMARY KEY, "
            "figma_node_id TEXT, "
            "name TEXT NOT NULL, "
            "instance_count INTEGER)"
        )
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, name, figma_node_id, instance_count) "
            "VALUES (?, ?, ?, ?)",
            ("ck_top_nav", "nav/top-nav", "5749:5000", 1),
        )
        conn.commit()

        # Build a minimal CompositionSpec by hand — the resolver path
        # only requires `_node_id_map` + a root reference for the
        # classified instance. `_mode1_eligible` on the instance
        # triggers the CKR lookup that populates `eligible_eids`.
        spec: dict = {
            "root": "screen-root",
            "elements": {
                "screen-root": {
                    "type": "screen",
                    "children": ["top-nav"],
                },
                "top-nav": {
                    "type": "instance",
                    "component_key": "ck_top_nav",
                    "children": [],
                    "props": {},
                    "_mode1_eligible": True,
                },
            },
            "_node_id_map": {
                "screen-root": 1,
                "top-nav": 1100,
            },
        }
        doc, resolver = compress_to_l3_with_resolver(
            spec, conn, collapse_wrapper=False,
        )

        # Walk the AST collecting `.visible` PathOverrides on any
        # CompRef.
        visible_overrides: list[PathOverride] = []

        def walk(node: Node) -> None:
            for p in node.head.properties:
                if isinstance(p, PathOverride) and p.path.endswith(".visible"):
                    visible_overrides.append(p)
            if node.block is not None:
                for s in node.block.statements:
                    if isinstance(s, Node):
                        walk(s)

        for n in doc.top_level:
            if isinstance(n, Node):
                walk(n)

        assert len(visible_overrides) == 1, (
            f"expected exactly 1 `.visible` PathOverride for the H3 "
            f"descendant; got {len(visible_overrides)}: "
            f"{[p.path for p in visible_overrides]}"
        )
        po = visible_overrides[0]
        assert po.path.startswith("icon-wallet")
        assert po.value.py is False

        # Resolver must map the path → the descendant figma suffix.
        flat_resolver: dict[str, str] = {}
        for bucket in resolver.values():
            flat_resolver.update(bucket)
        assert flat_resolver.get(po.path) == "5749:5100", (
            f"resolver must map {po.path!r} to '5749:5100'; got "
            f"{flat_resolver.get(po.path)!r}"
        )
        conn.close()
