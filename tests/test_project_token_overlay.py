"""Mode-3 visual gap fix — project-token alias overlay.

Pre-fix Mode-3 cards rendered with shadcn-default white-on-white
because dd/compose.py:_UNIVERSAL_MODE3_TOKENS was the only token
source consulted at compose time. Even though the project DB had
4500+ bound surface-color bindings (Nouns Phase E), none of them
informed the universal template's `{color.surface.card}` ref.

The fix is a compose-time alias overlay
(dd/composition/project_tokens.py:build_project_token_overlay)
that queries the project DB for the most-bound token under each
universal name's selector and seeds those values onto the spec's
`tokens` dict BEFORE _UNIVERSAL_MODE3_TOKENS is merged. Project
wins; shadcn fills gaps.

Codex 2026-04-26 (gpt-5.5 high reasoning):
"compose-time alias overlay; keep universal templates emitting
stable refs. Do not put this in resolve_style_value (intentionally
exact flat lookup); do not make providers project-aware."
"""

from __future__ import annotations

import sqlite3

import pytest

from dd import db as dd_db
from dd.composition.project_tokens import (
    _SELECTORS,
    build_project_token_overlay,
)


def _make_db_with_tokens(rows: list[dict]) -> sqlite3.Connection:
    """Build a fresh DB and seed clusters of tokens + bindings.

    Each row is a dict with:
      token_name, token_value, property, canonical_type (optional),
      n_bindings (default 1)

    Token + value rows are auto-created. canonical_type, when set,
    creates an SCI row pointing at a node + screen.
    """
    conn = dd_db.init_db(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO files (id, file_key, name) "
        "VALUES (1, 'test', 'test.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, "
        "width, height) "
        "VALUES (1, 1, '1:1', 'Screen 1', 375, 812)"
    )
    cur = conn.execute(
        "INSERT INTO token_collections (file_id, name) "
        "VALUES (1, 'Test')"
    )
    cid = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO token_modes (collection_id, name) "
        "VALUES (?, 'Default')",
        (cid,),
    )
    mid = cur.lastrowid
    # Seed catalog so SCI can reference catalog_type_id.
    from dd.catalog import seed_catalog
    seed_catalog(conn)

    node_id_counter = 100
    for row in rows:
        cur = conn.execute(
            "INSERT INTO tokens (collection_id, name, type, tier) "
            "VALUES (?, ?, 'color', 'extracted')",
            (cid, row["token_name"]),
        )
        token_id = cur.lastrowid
        conn.execute(
            "INSERT INTO token_values "
            "(token_id, mode_id, raw_value, resolved_value) "
            "VALUES (?, ?, ?, ?)",
            (token_id, mid, row["token_value"], row["token_value"]),
        )
        # Create N nodes with bindings to this token.
        for _ in range(row.get("n_bindings", 1)):
            node_id_counter += 1
            conn.execute(
                "INSERT INTO nodes "
                "(id, screen_id, figma_node_id, name, node_type) "
                "VALUES (?, 1, ?, ?, 'FRAME')",
                (
                    node_id_counter,
                    f"1:{node_id_counter}",
                    f"node{node_id_counter}",
                ),
            )
            conn.execute(
                "INSERT INTO node_token_bindings "
                "(node_id, property, raw_value, resolved_value, "
                "binding_status, token_id) "
                "VALUES (?, ?, ?, ?, 'bound', ?)",
                (
                    node_id_counter,
                    row["property"],
                    row["token_value"],
                    row["token_value"],
                    token_id,
                ),
            )
            if row.get("canonical_type"):
                # Look up catalog_type_id
                ct_row = conn.execute(
                    "SELECT id FROM component_type_catalog "
                    "WHERE canonical_name = ?",
                    (row["canonical_type"],),
                ).fetchone()
                catalog_type_id = ct_row[0] if ct_row else None
                conn.execute(
                    "INSERT INTO screen_component_instances "
                    "(screen_id, node_id, canonical_type, "
                    "catalog_type_id, classification_source, confidence) "
                    "VALUES (1, ?, ?, ?, 'heuristic', 1.0)",
                    (
                        node_id_counter,
                        row["canonical_type"],
                        catalog_type_id,
                    ),
                )

    conn.commit()
    return conn


class TestEmptyDBYieldsEmptyOverlay:
    """Defensive: missing tables / empty DB → empty overlay (caller
    falls back to _UNIVERSAL_MODE3_TOKENS)."""

    def test_fresh_db_yields_empty_overlay(self):
        conn = dd_db.init_db(":memory:")
        overlay = build_project_token_overlay(conn)
        assert overlay == {}, (
            "A DB with no tokens should produce no overlay so the "
            "shadcn baseline shines through."
        )


class TestColorSurfaceCardResolution:
    """The headline contract — `color.surface.card` resolves to the
    project's most-bound color.surface.* token among card-classified
    nodes."""

    def test_card_specific_surface_wins_over_global(self):
        """Two surface tokens: one bound on a card (10 bindings),
        another bound globally (50 bindings on non-card nodes). The
        card-specific one should win for color.surface.card."""
        conn = _make_db_with_tokens([
            # Card-bound surface
            {
                "token_name": "color.surface.10",
                "token_value": "#FAC8F5",
                "property": "fill.0.color",
                "canonical_type": "card",
                "n_bindings": 10,
            },
            # Globally-bound surface (more total bindings)
            {
                "token_name": "color.surface.99",
                "token_value": "#FFFFFF",
                "property": "fill.0.color",
                "canonical_type": "screen",
                "n_bindings": 50,
            },
        ])
        overlay = build_project_token_overlay(conn)
        assert overlay.get("color.surface.card") == "#FAC8F5", (
            "color.surface.card should prefer the card-bound token "
            "(10 bindings) over the more-bound screen-bound token "
            "(50 bindings). Selector's preferred_canonical_type='card' "
            "filters to card-bound bindings first."
        )

    def test_global_fallback_when_no_card_canonical_match(self):
        """When no card-typed nodes exist, fall back to global
        most-used color.surface.*."""
        conn = _make_db_with_tokens([
            {
                "token_name": "color.surface.global",
                "token_value": "#222222",
                "property": "fill.0.color",
                "canonical_type": None,
                "n_bindings": 5,
            },
        ])
        overlay = build_project_token_overlay(conn)
        assert overlay.get("color.surface.card") == "#222222", (
            "When no card-classified nodes exist, color.surface.card "
            "should fall back to the most-used global "
            "color.surface.* token."
        )


class TestRadiusResolution:
    """Radius resolves to project's most-bound radius.* under
    cornerRadius bindings."""

    def test_radius_card_resolves_to_most_bound_radius_token(self):
        conn = _make_db_with_tokens([
            {
                "token_name": "radius.lg",
                "token_value": "12",
                "property": "cornerRadius",
                "canonical_type": "card",
                "n_bindings": 7,
            },
            {
                "token_name": "radius.sm",
                "token_value": "4",
                "property": "cornerRadius",
                "canonical_type": "card",
                "n_bindings": 2,
            },
        ])
        overlay = build_project_token_overlay(conn)
        # Numeric coercion (12 not "12") so renderer emits
        # cornerRadius = 12; not = "12";
        assert overlay.get("radius.card") == 12, (
            f"radius.card should resolve to the most-bound card "
            f"cornerRadius token (radius.lg → 12). "
            f"Got: {overlay.get('radius.card')!r}"
        )


class TestSpacingResolution:
    """Spacing resolves to project's most-bound space.* under
    padding/itemSpacing bindings."""

    def test_space_card_padding_x_resolves_correctly(self):
        conn = _make_db_with_tokens([
            {
                "token_name": "space.16",
                "token_value": "16",
                "property": "padding.left",
                "canonical_type": "card",
                "n_bindings": 5,
            },
        ])
        overlay = build_project_token_overlay(conn)
        assert overlay.get("space.card.padding_x") == 16


class TestProjectOverlayMergesIntoCompose:
    """End-to-end: compose_screen with conn= seeds the project
    overlay onto the spec's tokens dict so universal template
    refs resolve to project values at render time."""

    def test_compose_screen_seeds_project_tokens(self):
        from dd.compose import compose_screen
        conn = _make_db_with_tokens([
            {
                "token_name": "color.surface.brand",
                "token_value": "#FF00FF",
                "property": "fill.0.color",
                "canonical_type": "card",
                "n_bindings": 5,
            },
        ])
        spec = compose_screen(
            [{"type": "card", "children": []}],
            templates={},
            conn=conn,
        )
        # _UNIVERSAL_MODE3_TOKENS provides shadcn default for any
        # universal name without project match. Project should have
        # OVERWRITTEN color.surface.card.
        assert spec["tokens"].get("color.surface.card") == "#FF00FF", (
            "compose_screen with conn= should overlay project tokens "
            "onto _UNIVERSAL_MODE3_TOKENS so universal template refs "
            "resolve to project colors."
        )

    def test_compose_screen_without_conn_uses_shadcn_only(self):
        from dd.compose import compose_screen
        spec = compose_screen(
            [{"type": "card", "children": []}],
            templates={},
            conn=None,
        )
        # color.surface.card should be the shadcn default (#FFFFFF).
        assert spec["tokens"].get("color.surface.card") == "#FFFFFF"


class TestCoercionShape:
    """The overlay returns native Python types (int for round
    numerics, str for hex colors), not just strings — the renderer
    emits `n.itemSpacing = 16;` not `n.itemSpacing = "16";`."""

    def test_int_coercion_for_round_numerics(self):
        from dd.composition.project_tokens import _coerce
        assert _coerce("16") == 16
        assert isinstance(_coerce("16"), int)
        assert _coerce("16.0") == 16

    def test_float_coercion_for_decimals(self):
        from dd.composition.project_tokens import _coerce
        assert _coerce("16.5") == 16.5
        assert isinstance(_coerce("16.5"), float)

    def test_hex_color_passes_through(self):
        from dd.composition.project_tokens import _coerce
        assert _coerce("#FAC8F5") == "#FAC8F5"

    def test_json_string_passes_through(self):
        from dd.composition.project_tokens import _coerce
        assert _coerce('{"value": -0.55, "unit": "PERCENT"}') == \
            '{"value": -0.55, "unit": "PERCENT"}'


class TestSelectorTableValid:
    """Sanity: every selector entry has the required keys."""

    def test_all_selectors_have_required_keys(self):
        for name, selector in _SELECTORS.items():
            assert "name_prefix" in selector, name
            assert "property_families" in selector, name
            assert "preferred_canonical_type" in selector, name
            # property_families must be a tuple of strings
            assert isinstance(selector["property_families"], tuple), name
            assert all(
                isinstance(p, str)
                for p in selector["property_families"]
            ), name

    def test_card_selectors_target_card_canonical(self):
        """The {*.card} family selectors should target canonical_type='card'."""
        for name in ("color.surface.card", "color.surface.card_border", "radius.card"):
            spec = _SELECTORS[name]
            assert spec["preferred_canonical_type"] == "card", (
                f"{name} should prefer card-bound bindings."
            )
