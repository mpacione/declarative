"""Tests for force_renormalize mode in the binding extraction pipeline.

When normalization rules change (e.g., alpha-baked colors), bound bindings
have stale resolved_values. The force_renormalize flag on insert_bindings()
updates resolved_value on bound bindings while preserving binding_status.
"""

import json
import sqlite3


def _seed_file_screen_node(conn: sqlite3.Connection, fills=None, strokes=None, effects=None):
    """Seed a file, screen, and node with given paint data. Return node DB id."""
    conn.execute(
        "INSERT INTO files (id, file_key, name, node_count, screen_count) VALUES (1, 'k', 'F', 1, 1)"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 's1', 'S', 400, 800)"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (1, 1, 'n1', 'N', 'RECTANGLE')"
    )
    if fills is not None:
        conn.execute("UPDATE nodes SET fills = ? WHERE id = 1", (json.dumps(fills),))
    if strokes is not None:
        conn.execute("UPDATE nodes SET strokes = ? WHERE id = 1", (json.dumps(strokes),))
    if effects is not None:
        conn.execute("UPDATE nodes SET effects = ? WHERE id = 1", (json.dumps(effects),))
    conn.commit()
    return 1


def _insert_binding(conn: sqlite3.Connection, node_id: int, prop: str, resolved: str, status="bound"):
    conn.execute(
        "INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) "
        "VALUES (?, ?, '{}', ?, ?)",
        (node_id, prop, resolved, status),
    )
    conn.commit()


def _get_binding_row(conn: sqlite3.Connection, node_id: int, prop: str):
    return conn.execute(
        "SELECT resolved_value, binding_status FROM node_token_bindings WHERE node_id = ? AND property = ?",
        (node_id, prop),
    ).fetchone()


class TestInsertBindingsForceRenormalize:
    """insert_bindings(force_renormalize=True) updates bound values without changing status."""

    def test_updates_bound_binding_value(self, db):
        """Bound binding with stale value should get updated resolved_value."""
        from dd.extract_bindings import insert_bindings

        _seed_file_screen_node(db)
        _insert_binding(db, 1, "fill.0.color", "#09090B", status="bound")

        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#09090B0D"}]
        insert_bindings(db, 1, new_bindings, force_renormalize=True)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#09090B0D"
        assert row["binding_status"] == "bound"

    def test_updates_proposed_binding_value(self, db):
        """Proposed binding with stale value should also get updated."""
        from dd.extract_bindings import insert_bindings

        _seed_file_screen_node(db)
        _insert_binding(db, 1, "fill.0.color", "#000000", status="proposed")

        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#00000080"}]
        insert_bindings(db, 1, new_bindings, force_renormalize=True)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#00000080"
        assert row["binding_status"] == "proposed"

    def test_does_not_change_unchanged_values(self, db):
        """Bindings where value hasn't changed should not be touched."""
        from dd.extract_bindings import insert_bindings

        _seed_file_screen_node(db)
        _insert_binding(db, 1, "fill.0.color", "#FFFFFF", status="bound")

        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#FFFFFF"}]
        count = insert_bindings(db, 1, new_bindings, force_renormalize=True)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#FFFFFF"
        assert row["binding_status"] == "bound"
        assert count == 0

    def test_without_flag_marks_overridden(self, db):
        """Without force_renormalize, changed bound bindings become overridden (existing behavior)."""
        from dd.extract_bindings import insert_bindings

        _seed_file_screen_node(db)
        _insert_binding(db, 1, "fill.0.color", "#09090B", status="bound")

        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#09090B0D"}]
        insert_bindings(db, 1, new_bindings)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#09090B0D"
        assert row["binding_status"] == "overridden"


class TestCreateBindingsForScreenForceRenormalize:
    """create_bindings_for_screen(force_renormalize=True) threads the flag through."""

    def test_fill_with_sub_one_opacity_gets_eight_digit_hex(self, db):
        """A bound fill with paint opacity 0.05 should produce #RRGGBBAA."""
        from dd.extract_bindings import create_bindings_for_screen

        fills = [{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043}, "opacity": 0.05}]
        _seed_file_screen_node(db, fills=fills)
        _insert_binding(db, 1, "fill.0.color", "#09090B", status="bound")

        create_bindings_for_screen(db, screen_id=1, force_renormalize=True)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#09090B0D"
        assert row["binding_status"] == "bound"

    def test_stroke_with_sub_one_opacity(self, db):
        from dd.extract_bindings import create_bindings_for_screen

        strokes = [{"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0}, "opacity": 0.2}]
        _seed_file_screen_node(db, strokes=strokes)
        _insert_binding(db, 1, "stroke.0.color", "#FF0000", status="bound")

        create_bindings_for_screen(db, screen_id=1, force_renormalize=True)

        row = _get_binding_row(db, 1, "stroke.0.color")
        assert row["resolved_value"] == "#FF000033"
        assert row["binding_status"] == "bound"

    def test_effect_color_with_alpha(self, db):
        from dd.extract_bindings import create_bindings_for_screen

        effects = [{
            "type": "DROP_SHADOW",
            "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.25},
            "radius": 8, "offset": {"x": 0, "y": 4}, "spread": 0,
        }]
        _seed_file_screen_node(db, effects=effects)
        _insert_binding(db, 1, "effect.0.color", "#000000", status="bound")

        create_bindings_for_screen(db, screen_id=1, force_renormalize=True)

        row = _get_binding_row(db, 1, "effect.0.color")
        assert row["resolved_value"] == "#00000040"
        assert row["binding_status"] == "bound"

    def test_full_opacity_stays_six_digit(self, db):
        from dd.extract_bindings import create_bindings_for_screen

        fills = [{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}, "opacity": 1.0}]
        _seed_file_screen_node(db, fills=fills)
        _insert_binding(db, 1, "fill.0.color", "#FFFFFF", status="bound")

        create_bindings_for_screen(db, screen_id=1, force_renormalize=True)

        row = _get_binding_row(db, 1, "fill.0.color")
        assert row["resolved_value"] == "#FFFFFF"
        assert row["binding_status"] == "bound"

    def test_non_color_bindings_untouched(self, db):
        from dd.extract_bindings import create_bindings_for_screen

        fills = [{"type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0}, "opacity": 0.5}]
        _seed_file_screen_node(db, fills=fills)
        _insert_binding(db, 1, "fill.0.color", "#000000", status="bound")
        _insert_binding(db, 1, "cornerRadius", "8", status="bound")

        create_bindings_for_screen(db, screen_id=1, force_renormalize=True)

        row = _get_binding_row(db, 1, "cornerRadius")
        assert row["resolved_value"] == "8"
        assert row["binding_status"] == "bound"
