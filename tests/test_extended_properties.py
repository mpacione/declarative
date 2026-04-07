"""Tests for extended property extraction, normalization, and storage.

Phase 1: Schema — verify new columns exist on nodes table
Phase 2: Extraction — verify new properties are captured
Phase 3: Normalization — verify new normalize functions produce correct bindings
"""

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
        "is_mask": "INTEGER",
        "boolean_operation": "TEXT",
        "corner_smoothing": "REAL",
        "arc_data": "TEXT",
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


# ---------------------------------------------------------------------------
# Instance override extraction and storage
# ---------------------------------------------------------------------------

class TestInstanceOverrideExtraction:
    """Verify override extraction generates correct JS and stores results."""

    def test_supplement_script_includes_override_collection(self):
        from dd.extract_supplement import generate_supplement_script

        script = generate_supplement_script(["100:1"])
        assert "overrides" in script
        assert "overriddenFields" in script

    def test_apply_supplement_creates_override_rows(self):
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, is_semantic, visible, extracted_at) "
            "VALUES (10, 1, '200:10', 'nav/top-nav', 'INSTANCE', 1, 0, 1, 1, '2026-01-01')"
        )
        conn.commit()

        supplement_data = {
            "200:10": {
                "ck": "nav_key_123",
                "ov": [
                    {"cid": ";1835:155173", "f": ["characters"], "text_content": "Meme-00001", "t": "TEXT"},
                    {"cid": ";1334:10838", "f": ["swap"], "swapId": "1315:139154", "t": "INSTANCE"},
                    {"cid": ";1835:25921", "f": ["visible"], "visible": False, "t": "TEXT"},
                ],
            }
        }
        result = apply_supplement(conn, supplement_data)

        rows = conn.execute("SELECT * FROM instance_overrides WHERE node_id = 10").fetchall()
        assert len(rows) == 3

    def test_override_row_has_correct_fields(self):
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, is_semantic, visible, extracted_at) "
            "VALUES (10, 1, '200:10', 'header', 'INSTANCE', 1, 0, 1, 1, '2026-01-01')"
        )
        conn.commit()

        supplement_data = {
            "200:10": {
                "ov": [
                    {"cid": ";1835:155173", "f": ["characters"], "text_content": "Hello", "t": "TEXT"},
                ],
            }
        }
        apply_supplement(conn, supplement_data)

        row = conn.execute(
            "SELECT node_id, property_type, property_name, override_value "
            "FROM instance_overrides WHERE node_id = 10"
        ).fetchone()
        assert row[0] == 10  # node_id
        assert row[1] == "TEXT"  # property_type
        assert row[2] == ";1835:155173"  # child relative ID
        assert row[3] == "Hello"  # override value

    def test_fills_override_stored(self):
        """Fills overrides should be captured as FILLS entries."""
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, is_semantic, visible, extracted_at) "
            "VALUES (10, 1, '200:10', 'button', 'INSTANCE', 1, 0, 1, 1, '2026-01-01')"
        )
        conn.commit()

        supplement_data = {
            "200:10": {
                "ov": [
                    {"cid": ":self", "f": ["fills", "height", "width"], "t": "INSTANCE",
                     "fills": '[{"type":"SOLID","visible":false,"opacity":0.05}]',
                     "width": 48, "height": 52},
                ],
            }
        }
        apply_supplement(conn, supplement_data)

        rows = conn.execute(
            "SELECT property_type, property_name, override_value "
            "FROM instance_overrides WHERE node_id = 10 ORDER BY property_type"
        ).fetchall()
        types = {r[0] for r in rows}
        assert "FILLS" in types
        assert "WIDTH" in types
        assert "HEIGHT" in types

        fills_row = next(r for r in rows if r[0] == "FILLS")
        assert '"SOLID"' in fills_row[2]

    def test_self_override_uses_self_marker(self):
        """Self-overrides use ':self' as child ID."""
        from dd.extract_supplement import generate_supplement_script

        script = generate_supplement_script(["100:1"])
        assert ":self" in script


# ---------------------------------------------------------------------------
# Phase 4: Gradient enrichment — supplement captures gradientTransform
# ---------------------------------------------------------------------------

class TestGradientEnrichment:
    """Verify supplement extraction enriches gradient fills with Plugin API format.

    The REST API stores gradientHandlePositions (3 points). The Plugin API
    provides gradientTransform (2x3 matrix). Both are needed: different
    renderers prefer different representations.

    ORDERING RISK: The supplement ENRICHES the existing fills column — it
    must preserve REST API fields (gradientHandlePositions) while adding
    Plugin API fields (gradientTransform). If REST extraction re-runs after
    supplement, the enrichment is lost. If supplement re-runs, it re-enriches.
    """

    def test_supplement_script_captures_gradient_transforms(self):
        """The generated JS should extract gradientTransform from gradient fills."""
        from dd.extract_supplement import generate_supplement_script

        script = generate_supplement_script(["100:1"])
        assert "gradientTransform" in script

    def test_apply_supplement_enriches_gradient_fills(self):
        """apply_supplement should merge gradientTransform into existing fills JSON."""
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        # Insert node with REST API gradient fills (has handlePositions, no transform)
        import json
        rest_fills = json.dumps([{
            "type": "GRADIENT_LINEAR",
            "opacity": 0.1,
            "gradientHandlePositions": [
                {"x": 0.5, "y": 0}, {"x": 0.5, "y": 1}, {"x": 0, "y": 0}
            ],
            "gradientStops": [
                {"color": {"r": 0, "g": 0, "b": 0, "a": 0}, "position": 0},
                {"color": {"r": 0, "g": 0, "b": 0, "a": 1}, "position": 1},
            ],
        }])
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, "
            "depth, sort_order, is_semantic, visible, extracted_at, fills) "
            "VALUES (10, 1, '200:10', 'Overlay', 'FRAME', 1, 0, 1, 1, '2026-01-01', ?)",
            (rest_fills,),
        )
        conn.commit()

        # Supplement provides Plugin API gradient format (has gradientTransform)
        plugin_transform = [[-0.81, 0.19, 0.80], [-0.19, -0.21, 0.71]]
        supplement_data = {
            "200:10": {
                "gt": [{
                    "fillIndex": 0,
                    "gradientTransform": plugin_transform,
                }],
            }
        }
        apply_supplement(conn, supplement_data)

        # Verify fills column now has BOTH handlePositions and gradientTransform
        row = conn.execute("SELECT fills FROM nodes WHERE id = 10").fetchone()
        fills = json.loads(row[0])
        assert len(fills) == 1
        assert "gradientHandlePositions" in fills[0], "REST API field should be preserved"
        assert "gradientTransform" in fills[0], "Plugin API field should be added"
        assert fills[0]["gradientTransform"] == plugin_transform

    def test_apply_supplement_preserves_solid_fills(self):
        """Solid fills in the fills column should not be modified by gradient enrichment."""
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement
        import json

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        solid_fills = json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0}}])
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, "
            "depth, sort_order, is_semantic, visible, extracted_at, fills) "
            "VALUES (10, 1, '200:10', 'card', 'FRAME', 1, 0, 1, 1, '2026-01-01', ?)",
            (solid_fills,),
        )
        conn.commit()

        # No gradient transforms to enrich
        supplement_data = {"200:10": {"lp": "ABSOLUTE"}}
        apply_supplement(conn, supplement_data)

        row = conn.execute("SELECT fills FROM nodes WHERE id = 10").fetchone()
        fills = json.loads(row[0])
        assert fills[0]["type"] == "SOLID"
        assert "gradientTransform" not in fills[0]

    def test_normalize_fills_preserves_gradient_transform(self):
        """normalize_fills should pass through gradientTransform when present."""
        from dd.ir import normalize_fills

        fills = normalize_fills(
            '[{"type": "GRADIENT_LINEAR", "opacity": 0.1, '
            '"gradientHandlePositions": [{"x":0.5,"y":0},{"x":0.5,"y":1},{"x":0,"y":0}], '
            '"gradientTransform": [[0,1,0],[1,0,0]], '
            '"gradientStops": [{"color":{"r":0,"g":0,"b":0,"a":0},"position":0},'
            '{"color":{"r":0,"g":0,"b":0,"a":1},"position":1}]}]',
            [],
        )
        assert len(fills) == 1
        assert fills[0]["type"] == "gradient-linear"
        assert "handlePositions" in fills[0]
        assert "gradientTransform" in fills[0]
        assert fills[0]["gradientTransform"] == [[0, 1, 0], [1, 0, 0]]

    def test_emit_fills_produces_gradient_output(self):
        """_emit_fills should emit gradient fills with gradientTransform."""
        from dd.renderers.figma import _emit_fills

        fills = [{
            "type": "gradient-linear",
            "stops": [
                {"color": "#000000", "position": 0.0},
                {"color": "#000000", "position": 1.0},
            ],
            "gradientTransform": [[0, -1, 1], [1, 0, 0]],
            "opacity": 0.1,
        }]
        lines, refs = _emit_fills("node", "eid-1", fills, {})
        assert len(lines) == 1
        js = lines[0]
        assert "GRADIENT_LINEAR" in js
        assert "gradientTransform" in js
        assert "gradientStops" in js
        assert "0.1" in js  # opacity


class TestTextAutoResizeExtraction:
    """Verify textAutoResize is captured by supplement extraction."""

    def test_supplement_script_captures_text_auto_resize(self):
        from dd.extract_supplement import generate_supplement_script

        script = generate_supplement_script(["100:1"])
        assert "textAutoResize" in script

    def test_apply_supplement_stores_text_auto_resize(self):
        from dd.db import init_db
        from dd.extract_supplement import apply_supplement

        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen', 428, 926)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, "
            "depth, sort_order, is_semantic, visible, extracted_at) "
            "VALUES (10, 1, '200:10', 'Title', 'TEXT', 1, 0, 1, 1, '2026-01-01')"
        )
        conn.commit()

        supplement_data = {"200:10": {"tar": "HEIGHT"}}
        apply_supplement(conn, supplement_data)

        row = conn.execute("SELECT text_auto_resize FROM nodes WHERE id = 10").fetchone()
        assert row[0] == "HEIGHT"
