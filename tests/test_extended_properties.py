"""Tests for extended property extraction, normalization, and storage.

Phase 1: Schema — verify new columns exist on nodes table
Phase 2: Extraction — verify new properties are captured
Phase 3: Normalization — verify new normalize functions produce correct bindings
"""

import json
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Phase 1: Schema — new columns on nodes table
# ---------------------------------------------------------------------------

class TestExtendedSchemaColumns:
    """Verify all new columns exist on the nodes table with correct defaults."""

    EXPECTED_COLUMNS = {
        "stroke_weight": "REAL",
        "stroke_top_weight": "REAL",
        "stroke_right_weight": "REAL",
        "stroke_bottom_weight": "REAL",
        "stroke_left_weight": "REAL",
        "stroke_align": "TEXT",
        "stroke_cap": "TEXT",
        "stroke_join": "TEXT",
        "dash_pattern": "TEXT",
        "rotation": "REAL",
        "clips_content": "INTEGER",
        "constraint_h": "TEXT",
        "constraint_v": "TEXT",
        "paragraph_spacing": "REAL",
        "text_decoration": "TEXT",
        "text_case": "TEXT",
        "text_align_v": "TEXT",
        "font_style": "TEXT",
        "layout_wrap": "TEXT",
        "min_width": "REAL",
        "max_width": "REAL",
        "min_height": "REAL",
        "max_height": "REAL",
        "component_key": "TEXT",
    }

    def test_all_new_columns_exist(self, db):
        cols = {
            row[1]: row[2]
            for row in db.execute("PRAGMA table_info(nodes)").fetchall()
        }
        for col_name, col_type in self.EXPECTED_COLUMNS.items():
            assert col_name in cols, f"Missing column: nodes.{col_name}"
            assert cols[col_name] == col_type, (
                f"nodes.{col_name} should be {col_type}, got {cols[col_name]}"
            )

    def test_new_columns_default_null(self, db):
        db.execute(
            "INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'F')"
        )
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 400, 800)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (1, 1, 'n1', 'N', 'FRAME')"
        )
        db.commit()

        row = db.execute("SELECT * FROM nodes WHERE id = 1").fetchone()
        for col_name in self.EXPECTED_COLUMNS:
            assert row[col_name] is None, f"nodes.{col_name} should default to NULL"

    def test_can_write_stroke_weight(self, db):
        db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'F')")
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 400, 800)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, "
            "stroke_weight, stroke_align, rotation, clips_content) "
            "VALUES (1, 1, 'n1', 'N', 'FRAME', 2.0, 'INSIDE', 45.0, 1)"
        )
        db.commit()

        row = db.execute("SELECT stroke_weight, stroke_align, rotation, clips_content FROM nodes WHERE id = 1").fetchone()
        assert row["stroke_weight"] == 2.0
        assert row["stroke_align"] == "INSIDE"
        assert row["rotation"] == 45.0
        assert row["clips_content"] == 1


class TestInstanceOverridesTable:
    """Verify instance_overrides table exists with correct schema."""

    def test_table_exists(self, db):
        row = db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='instance_overrides'"
        ).fetchone()
        assert row[0] == 1

    def test_can_insert_override(self, db):
        db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'F')")
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 400, 800)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (1, 1, 'n1', 'N', 'INSTANCE')"
        )
        db.execute(
            "INSERT INTO instance_overrides (node_id, property_type, property_name, override_value) "
            "VALUES (1, 'TEXT', 'Button Label', 'Submit')"
        )
        db.commit()

        row = db.execute("SELECT * FROM instance_overrides WHERE node_id = 1").fetchone()
        assert row["property_type"] == "TEXT"
        assert row["property_name"] == "Button Label"
        assert row["override_value"] == "Submit"

    def test_unique_constraint(self, db):
        db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'F')")
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 400, 800)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (1, 1, 'n1', 'N', 'INSTANCE')"
        )
        db.execute(
            "INSERT INTO instance_overrides (node_id, property_type, property_name, override_value) "
            "VALUES (1, 'TEXT', 'Label', 'A')"
        )
        db.commit()

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO instance_overrides (node_id, property_type, property_name, override_value) "
                "VALUES (1, 'TEXT', 'Label', 'B')"
            )


# ---------------------------------------------------------------------------
# Phase 3: Normalization — new normalize functions
# ---------------------------------------------------------------------------

class TestNormalizeStrokeWeight:
    """normalize_stroke_weight produces correct bindings."""

    def test_uniform_stroke_weight(self):
        from dd.normalize import normalize_stroke_weight
        node = {"stroke_weight": 2.0}
        bindings = normalize_stroke_weight(node)
        assert len(bindings) == 1
        assert bindings[0]["property"] == "strokeWeight"
        assert bindings[0]["resolved_value"] == "2.0"

    def test_per_side_stroke_weights(self):
        from dd.normalize import normalize_stroke_weight
        node = {
            "stroke_weight": None,
            "stroke_top_weight": 1.0,
            "stroke_right_weight": 2.0,
            "stroke_bottom_weight": 3.0,
            "stroke_left_weight": 4.0,
        }
        bindings = normalize_stroke_weight(node)
        props = {b["property"]: b["resolved_value"] for b in bindings}
        assert props["strokeTopWeight"] == "1.0"
        assert props["strokeRightWeight"] == "2.0"
        assert props["strokeBottomWeight"] == "3.0"
        assert props["strokeLeftWeight"] == "4.0"

    def test_zero_weight_skipped(self):
        from dd.normalize import normalize_stroke_weight
        node = {"stroke_weight": 0}
        bindings = normalize_stroke_weight(node)
        assert len(bindings) == 0

    def test_none_weight_skipped(self):
        from dd.normalize import normalize_stroke_weight
        node = {"stroke_weight": None}
        bindings = normalize_stroke_weight(node)
        assert len(bindings) == 0


class TestNormalizeParagraphSpacing:
    """normalize_paragraph_spacing produces correct bindings."""

    def test_nonzero_value(self):
        from dd.normalize import normalize_paragraph_spacing
        bindings = normalize_paragraph_spacing({"paragraph_spacing": 16.0})
        assert len(bindings) == 1
        assert bindings[0]["property"] == "paragraphSpacing"
        assert bindings[0]["resolved_value"] == "16.0"

    def test_zero_skipped(self):
        from dd.normalize import normalize_paragraph_spacing
        bindings = normalize_paragraph_spacing({"paragraph_spacing": 0})
        assert len(bindings) == 0

    def test_none_skipped(self):
        from dd.normalize import normalize_paragraph_spacing
        bindings = normalize_paragraph_spacing({"paragraph_spacing": None})
        assert len(bindings) == 0


class TestNormalizeFontStyle:
    """normalize_font_style produces correct bindings."""

    def test_italic(self):
        from dd.normalize import normalize_font_style
        bindings = normalize_font_style({"font_style": "Italic"})
        assert len(bindings) == 1
        assert bindings[0]["property"] == "fontStyle"
        assert bindings[0]["resolved_value"] == "Italic"

    def test_regular_skipped(self):
        from dd.normalize import normalize_font_style
        bindings = normalize_font_style({"font_style": "Regular"})
        assert len(bindings) == 0

    def test_none_skipped(self):
        from dd.normalize import normalize_font_style
        bindings = normalize_font_style({"font_style": None})
        assert len(bindings) == 0


class TestNormalizeBackgroundBlur:
    """BACKGROUND_BLUR should be handled like LAYER_BLUR."""

    def test_background_blur_extracts_radius(self):
        from dd.normalize import normalize_effect
        effects = [{"type": "BACKGROUND_BLUR", "visible": True, "radius": 20}]
        bindings = normalize_effect(effects)
        assert len(bindings) == 1
        assert bindings[0]["property"] == "effect.0.radius"
        assert bindings[0]["resolved_value"] == "20"


class TestNormalizeImageFill:
    """IMAGE fills should produce intentionally_unbound-ready bindings."""

    def test_image_fill_stored(self):
        from dd.normalize import normalize_fill
        fills = [{"type": "IMAGE", "visible": True, "imageRef": "img123", "scaleMode": "FILL"}]
        bindings = normalize_fill(fills)
        assert len(bindings) == 1
        assert bindings[0]["property"] == "fill.0.image"
        assert bindings[0]["resolved_value"] == "image"
        assert "img123" in bindings[0]["raw_value"]


class TestNormalizeGradientStops:
    """Gradient stops should be decomposed into individual color bindings."""

    def test_gradient_with_stops(self):
        from dd.normalize import normalize_fill
        fills = [{
            "type": "GRADIENT_LINEAR",
            "visible": True,
            "gradientStops": [
                {"color": {"r": 1, "g": 0, "b": 0, "a": 1}, "position": 0},
                {"color": {"r": 0, "g": 0, "b": 1, "a": 1}, "position": 1},
            ],
        }]
        bindings = normalize_fill(fills)
        # Should have: fill.0.gradient (the whole gradient) + 2 stop color bindings
        props = [b["property"] for b in bindings]
        assert "fill.0.gradient" in props
        assert "fill.0.gradient.stop.0.color" in props
        assert "fill.0.gradient.stop.1.color" in props

        # Stop colors should be proper hex
        stop0 = next(b for b in bindings if b["property"] == "fill.0.gradient.stop.0.color")
        assert stop0["resolved_value"] == "#FF0000"

    def test_gradient_without_stops_unchanged(self):
        from dd.normalize import normalize_fill
        fills = [{"type": "GRADIENT_LINEAR", "visible": True}]
        bindings = normalize_fill(fills)
        assert len(bindings) == 1
        assert bindings[0]["property"] == "fill.0.gradient"
