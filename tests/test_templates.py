"""Tests for component template extraction (Phase 4a)."""

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.templates import compute_mode_template, extract_templates, query_templates


class TestComputeModeTemplate:
    """Verify compute_mode_template takes the most common value per field."""

    def test_most_common_layout_mode(self):
        instances = [
            {"layout_mode": "HORIZONTAL", "width": 200, "height": 48},
            {"layout_mode": "HORIZONTAL", "width": 200, "height": 48},
            {"layout_mode": "VERTICAL", "width": 200, "height": 48},
        ]
        template = compute_mode_template(instances)
        assert template["layout_mode"] == "HORIZONTAL"

    def test_most_common_dimensions(self):
        instances = [
            {"width": 48, "height": 52},
            {"width": 48, "height": 52},
            {"width": 200, "height": 44},
        ]
        template = compute_mode_template(instances)
        assert template["width"] == 48
        assert template["height"] == 52

    def test_most_common_padding(self):
        instances = [
            {"padding_top": 16, "padding_right": 24},
            {"padding_top": 16, "padding_right": 24},
            {"padding_top": 8, "padding_right": 12},
        ]
        template = compute_mode_template(instances)
        assert template["padding_top"] == 16
        assert template["padding_right"] == 24

    def test_handles_none_values(self):
        instances = [
            {"layout_mode": None, "width": 20, "height": 20},
            {"layout_mode": None, "width": 20, "height": 20},
        ]
        template = compute_mode_template(instances)
        assert template["layout_mode"] is None

    def test_single_instance(self):
        instances = [
            {"layout_mode": "HORIZONTAL", "width": 428, "height": 111, "padding_top": 16},
        ]
        template = compute_mode_template(instances)
        assert template["layout_mode"] == "HORIZONTAL"
        assert template["width"] == 428

    def test_instance_count(self):
        instances = [{"width": 20}, {"width": 20}, {"width": 20}]
        template = compute_mode_template(instances)
        assert template["instance_count"] == 3

    def test_representative_node_id(self):
        instances = [
            {"node_id": 10, "width": 48, "height": 52},
            {"node_id": 11, "width": 48, "height": 52},
            {"node_id": 12, "width": 200, "height": 44},
        ]
        template = compute_mode_template(instances)
        assert template["representative_node_id"] in (10, 11)


# ---------------------------------------------------------------------------
# DB-level tests
# ---------------------------------------------------------------------------

def _seed_template_data(db: sqlite3.Connection) -> None:
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height, screen_type) "
        "VALUES (1, 1, 's1', 'Settings', 428, 926, 'app_screen')"
    )

    nodes = [
        # 3 button instances (same component key, same structure)
        (10, 1, "b1", "button/large/solid", "INSTANCE", 1, 0, 0, 0, 48, 52,
         "HORIZONTAL", 0, 14, 0, 14, 10, None, None, "10", None, None, None, 1.0, "key_btn_lg_solid"),
        (11, 1, "b2", "button/large/solid", "INSTANCE", 1, 1, 60, 0, 48, 52,
         "HORIZONTAL", 0, 14, 0, 14, 10, None, None, "10", None, None, None, 1.0, "key_btn_lg_solid"),
        # 1 button with different key
        (12, 1, "b3", "button/small/solid", "INSTANCE", 1, 2, 120, 0, 40, 40,
         "HORIZONTAL", 0, 8, 0, 8, 6, None, None, "8", None, None, None, 1.0, "key_btn_sm_solid"),
        # 2 heading instances (no component key)
        (20, 1, "h1", "Section Title", "TEXT", 1, 3, 0, 100, 396, 28,
         None, None, None, None, None, None, None, None, None, None, None, None, 1.0, None),
        (21, 1, "h2", "Other Title", "TEXT", 1, 4, 0, 140, 396, 28,
         None, None, None, None, None, None, None, None, None, None, None, None, 1.0, None),
    ]
    db.executemany(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order, x, y, width, height, "
        "layout_mode, padding_top, padding_right, padding_bottom, padding_left, item_spacing, "
        "primary_align, counter_align, corner_radius, fills, strokes, effects, opacity, component_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )

    sci_rows = [
        (1, 10, "button", 1.0, "formal"),
        (1, 11, "button", 1.0, "formal"),
        (1, 12, "button", 1.0, "formal"),
        (1, 20, "heading", 0.9, "heuristic"),
        (1, 21, "heading", 0.9, "heuristic"),
    ]
    db.executemany(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (?, ?, ?, ?, ?)",
        sci_rows,
    )
    db.commit()


class TestExtractTemplates:
    """Verify extract_templates populates the component_templates table."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_template_data(conn)
        yield conn
        conn.close()

    def test_populates_templates_table(self, db):
        extract_templates(db, file_id=1)
        count = db.execute("SELECT COUNT(*) FROM component_templates").fetchone()[0]
        assert count > 0

    def test_creates_template_per_component_key(self, db):
        extract_templates(db, file_id=1)
        button_templates = db.execute(
            "SELECT catalog_type, variant, component_key FROM component_templates "
            "WHERE catalog_type = 'button' ORDER BY variant"
        ).fetchall()
        assert len(button_templates) >= 2
        keys = {r[2] for r in button_templates}
        assert "key_btn_lg_solid" in keys
        assert "key_btn_sm_solid" in keys

    def test_creates_template_for_keyless_type(self, db):
        extract_templates(db, file_id=1)
        heading = db.execute(
            "SELECT * FROM component_templates WHERE catalog_type = 'heading'"
        ).fetchone()
        assert heading is not None

    def test_template_has_structure_data(self, db):
        extract_templates(db, file_id=1)
        btn = db.execute(
            "SELECT layout_mode, width, height, padding_right, item_spacing, corner_radius "
            "FROM component_templates WHERE component_key = 'key_btn_lg_solid'"
        ).fetchone()
        assert btn[0] == "HORIZONTAL"
        assert btn[1] == 48
        assert btn[2] == 52
        assert btn[3] == 14
        assert btn[4] == 10

    def test_template_has_instance_count(self, db):
        extract_templates(db, file_id=1)
        btn = db.execute(
            "SELECT instance_count FROM component_templates WHERE component_key = 'key_btn_lg_solid'"
        ).fetchone()
        assert btn[0] == 2

    def test_idempotent(self, db):
        extract_templates(db, file_id=1)
        count1 = db.execute("SELECT COUNT(*) FROM component_templates").fetchone()[0]
        extract_templates(db, file_id=1)
        count2 = db.execute("SELECT COUNT(*) FROM component_templates").fetchone()[0]
        assert count1 == count2


class TestQueryTemplates:
    """Verify query_templates returns templates keyed by catalog_type."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_template_data(conn)
        extract_templates(conn, file_id=1)
        yield conn
        conn.close()

    def test_returns_dict_keyed_by_catalog_type(self, db):
        templates = query_templates(db)
        assert isinstance(templates, dict)
        assert "button" in templates
        assert "heading" in templates

    def test_button_has_multiple_variants(self, db):
        templates = query_templates(db)
        assert len(templates["button"]) >= 2

    def test_template_dict_has_required_fields(self, db):
        templates = query_templates(db)
        btn = templates["button"][0]
        assert "component_key" in btn
        assert "layout_mode" in btn
        assert "width" in btn
        assert "height" in btn
        assert "instance_count" in btn


# ---------------------------------------------------------------------------
# Font property tests
# ---------------------------------------------------------------------------

class TestFontPropertiesInTemplates:
    """Verify font properties flow through template extraction and query."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height, screen_type) "
            "VALUES (1, 1, 's1', 'Screen', 428, 926, 'app_screen')"
        )
        # 3 text nodes with font properties
        nodes = [
            (30, 1, "t1", "body text", "TEXT", 1, 0, 0, 0, 200, 16,
             None, None, None, None, None, None, None, None, None, None, None, None, 1.0, None,
             "Inter Variable", 600, 16.0, "Regular", '{"unit": "AUTO"}', None, "LEFT"),
            (31, 1, "t2", "body text", "TEXT", 1, 1, 0, 20, 200, 16,
             None, None, None, None, None, None, None, None, None, None, None, None, 1.0, None,
             "Inter Variable", 600, 16.0, "Regular", '{"unit": "AUTO"}', None, "LEFT"),
            (32, 1, "t3", "body text", "TEXT", 1, 2, 0, 40, 200, 16,
             None, None, None, None, None, None, None, None, None, None, None, None, 1.0, None,
             "Inter Variable", 500, 14.0, "Regular", '{"value": 22, "unit": "PIXELS"}', None, "LEFT"),
        ]
        conn.executemany(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, sort_order, x, y, width, height, "
            "layout_mode, padding_top, padding_right, padding_bottom, padding_left, item_spacing, "
            "primary_align, counter_align, corner_radius, fills, strokes, effects, opacity, component_key, "
            "font_family, font_weight, font_size, font_style, line_height, letter_spacing, text_align) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            nodes,
        )
        sci_rows = [
            (1, 30, "text", 0.9, "heuristic"),
            (1, 31, "text", 0.9, "heuristic"),
            (1, 32, "text", 0.9, "heuristic"),
        ]
        conn.executemany(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (?, ?, ?, ?, ?)",
            sci_rows,
        )
        conn.commit()
        yield conn
        conn.close()

    def test_compute_mode_template_font_family(self):
        instances = [
            {"font_family": "Inter Variable"},
            {"font_family": "Inter Variable"},
            {"font_family": "Roboto"},
        ]
        template = compute_mode_template(instances)
        assert template["font_family"] == "Inter Variable"

    def test_compute_mode_template_font_size(self):
        instances = [
            {"font_size": 16.0},
            {"font_size": 16.0},
            {"font_size": 14.0},
        ]
        template = compute_mode_template(instances)
        assert template["font_size"] == 16.0

    def test_compute_mode_template_font_weight(self):
        instances = [
            {"font_weight": 600},
            {"font_weight": 600},
            {"font_weight": 400},
        ]
        template = compute_mode_template(instances)
        assert template["font_weight"] == 600

    def test_extract_templates_stores_font_fields(self, db):
        extract_templates(db, file_id=1)
        row = db.execute(
            "SELECT font_family, font_size, font_weight, font_style, text_align "
            "FROM component_templates WHERE catalog_type = 'text'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Inter Variable"
        assert row[1] == 16.0  # mode of 16, 16, 14
        assert row[2] == 600   # mode of 600, 600, 500

    def test_query_templates_returns_font_fields(self, db):
        extract_templates(db, file_id=1)
        templates = query_templates(db)
        text_tmpl = templates["text"][0]
        assert text_tmpl.get("font_family") == "Inter Variable"
        assert text_tmpl.get("font_size") == 16.0
        assert text_tmpl.get("font_weight") == 600
