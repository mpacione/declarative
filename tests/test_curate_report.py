"""Tests for the curate-report command — surfaces curation work the agent should do."""

import sqlite3

from dd.curate_report import generate_curation_report
from dd.db import init_db


def _seed_db(conn: sqlite3.Connection) -> int:
    """Seed a DB with realistic token data and return file_id."""
    conn.execute(
        "INSERT INTO files (file_key, name) VALUES ('abc123', 'Test File')"
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create a collection + mode
    conn.execute(
        "INSERT INTO token_collections (file_id, name) VALUES (?, 'Colors')",
        (file_id,),
    )
    coll_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'default', 1)",
        (coll_id,),
    )
    mode_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Screen + nodes for bindings
    conn.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
        "VALUES (?, '1:1', 'Screen1', 375, 812)",
        (file_id,),
    )
    screen_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    node_ids = []
    for i in range(20):
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (?, ?, ?, 'FRAME', 0, ?)",
            (screen_id, f"node:{i}", f"Node {i}", i),
        )
        node_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    return file_id, coll_id, mode_id, node_ids


def _add_token(conn, coll_id, mode_id, name, token_type, value, tier="curated"):
    conn.execute(
        "INSERT INTO tokens (collection_id, name, type, tier) VALUES (?, ?, ?, ?)",
        (coll_id, name, token_type, tier),
    )
    token_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) "
        "VALUES (?, ?, ?, ?)",
        (token_id, mode_id, value, value),
    )
    return token_id


def _bind(conn, node_id, token_id, prop, value):
    conn.execute(
        "INSERT INTO node_token_bindings (node_id, token_id, property, raw_value, resolved_value, binding_status) "
        "VALUES (?, ?, ?, ?, ?, 'bound')",
        (node_id, token_id, prop, value, value),
    )


class TestCurationReportNumericNames:
    def test_flags_tokens_with_numeric_segments(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.surface.4", "color", "#FF0000")
        _add_token(conn, coll_id, mode_id, "color.surface.primary", "color", "#0000FF")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert len(report["numeric_names"]) == 1
        assert report["numeric_names"][0]["name"] == "color.surface.4"

    def test_does_not_flag_semantic_names(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.surface.primary", "color", "#FF0000")
        _add_token(conn, coll_id, mode_id, "type.body.md.fontSize", "dimension", "16")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert len(report["numeric_names"]) == 0


class TestCurationReportNearDuplicates:
    def test_flags_colors_within_delta_e_threshold(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.a", "color", "#DADADA")
        _add_token(conn, coll_id, mode_id, "color.b", "color", "#D1D3D9")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert len(report["near_duplicates"]) == 1
        pair = report["near_duplicates"][0]
        assert pair["delta_e"] < 3.0

    def test_does_not_flag_distant_colors(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.a", "color", "#FF0000")
        _add_token(conn, coll_id, mode_id, "color.b", "color", "#0000FF")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert len(report["near_duplicates"]) == 0


class TestCurationReportLowUse:
    def test_flags_tokens_with_few_bindings(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        lonely = _add_token(conn, coll_id, mode_id, "color.lonely", "color", "#123456")
        popular = _add_token(conn, coll_id, mode_id, "color.popular", "color", "#ABCDEF")

        _bind(conn, nodes[0], lonely, "stroke.0.color", "#123456")
        for i in range(10):
            _bind(conn, nodes[i], popular, "fill.0.color", "#ABCDEF")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        low_names = [t["name"] for t in report["low_use"]]
        assert "color.lonely" in low_names
        assert "color.popular" not in low_names


class TestCurationReportSemanticLayer:
    def test_reports_no_semantic_layer_when_zero_aliases(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.primary", "color", "#FF0000")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert report["semantic_layer"]["alias_count"] == 0
        assert report["semantic_layer"]["has_semantic_layer"] is False

    def test_reports_semantic_layer_exists_when_aliases_present(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.primary", "color", "#FF0000")
        _add_token(conn, coll_id, mode_id, "color.danger", "color", "#FF0000", tier="aliased")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert report["semantic_layer"]["alias_count"] == 1
        assert report["semantic_layer"]["has_semantic_layer"] is True


class TestCurationReportFractionalSizes:
    def test_flags_fractional_font_sizes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "type.body.md.fontSize", "dimension", "36.85981369018555")
        _add_token(conn, coll_id, mode_id, "type.heading.lg.fontSize", "dimension", "16")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        frac_names = [f["name"] for f in report["fractional_sizes"]]
        assert "type.body.md.fontSize" in frac_names
        assert "type.heading.lg.fontSize" not in frac_names


class TestCurationReportSummary:
    def test_includes_action_counts(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        file_id, coll_id, mode_id, nodes = _seed_db(conn)

        _add_token(conn, coll_id, mode_id, "color.surface.4", "color", "#DADADA")
        _add_token(conn, coll_id, mode_id, "color.surface.5", "color", "#D1D3D9")
        conn.commit()

        report = generate_curation_report(conn, file_id)

        assert "summary" in report
        assert "total_actions" in report["summary"]
        assert report["summary"]["total_actions"] > 0
