"""Structural completeness tests for the property pipeline.

Fix 3C: every Figma visual property is either registered in the property
registry or documented as an intentional exclusion. This prevents silent
data loss when Figma adds new properties or when extraction captures
fields that never reach the renderer.
"""

import sqlite3

import pytest

from dd.db import init_db
from dd.property_registry import PROPERTIES, by_db_column, by_figma_name


# ---------------------------------------------------------------------------
# Canonical Figma Plugin API visual properties
# ---------------------------------------------------------------------------
# Source: Figma Plugin API reference (SceneNode properties that affect rendering).
# Each entry is the Plugin API property name.

_CANONICAL_FIGMA_PROPERTIES: set[str] = {
    # Visual appearance
    "fills", "strokes", "effects",
    "opacity", "blendMode", "visible",
    "isMask",

    # Stroke details
    "strokeWeight", "strokeAlign", "strokeCap", "strokeJoin", "dashPattern",

    # Corner radius
    "cornerRadius", "cornerSmoothing",

    # Transform
    "rotation", "clipsContent",

    # Layout (auto-layout container)
    "layoutMode",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "itemSpacing", "counterAxisSpacing",
    "primaryAxisAlignItems", "counterAxisAlignItems",
    "layoutWrap",

    # Layout (child sizing)
    "layoutSizingHorizontal", "layoutSizingVertical",
    "layoutPositioning",

    # Size
    "width", "height",
    "minWidth", "maxWidth", "minHeight", "maxHeight",

    # Typography
    "characters", "fontSize", "fontFamily", "fontWeight", "fontStyle",
    "textAlignHorizontal", "textAlignVertical",
    "textAutoResize", "textDecoration", "textCase",
    "lineHeight", "letterSpacing", "paragraphSpacing",

    # Constraints
    "constraints.horizontal", "constraints.vertical",

    # Vector / boolean / arc
    "booleanOperation", "arcData",
}


# Properties intentionally excluded from the registry with documented reasons.
_DOCUMENTED_EXCLUSIONS: dict[str, str] = {
    # Per-side stroke weights handled as separate DB columns, not via the registry's
    # single-property model. Extraction captures them; emission uses the uniform
    # strokeWeight or individual columns directly.
    "strokeTopWeight": "Per-side stroke weights stored as separate DB columns (stroke_top_weight, etc.)",
    "strokeRightWeight": "Per-side stroke weights stored as separate DB columns",
    "strokeBottomWeight": "Per-side stroke weights stored as separate DB columns",
    "strokeLeftWeight": "Per-side stroke weights stored as separate DB columns",

    # Vector geometry is stored in DB but not emitted via property registry.
    # Vector nodes use asset-backed rendering (createVector + vectorPaths).
    "fillGeometry": "Vector path data — asset-backed rendering via SVG pipeline, not property emission",
    "strokeGeometry": "Vector path data — asset-backed rendering via SVG pipeline, not property emission",

    # Grid layout properties — stored in DB, not yet in registry (future work).
    "gridRowCount": "Grid layout — extracted and stored, emission planned for grid support",
    "gridColumnCount": "Grid layout — extracted and stored, emission planned for grid support",
    "gridRowGap": "Grid layout — extracted and stored, emission planned for grid support",
    "gridColumnGap": "Grid layout — extracted and stored, emission planned for grid support",
    "gridRowSizes": "Grid layout — extracted and stored, emission planned for grid support",
    "gridColumnSizes": "Grid layout — extracted and stored, emission planned for grid support",

    # Component key is structural (instance→component reference), not a visual property.
    "componentKey": "Structural reference for INSTANCE nodes, not a visual property",
}


# Structural DB columns that are NOT visual properties (no registry entry needed).
_STRUCTURAL_DB_COLUMNS: set[str] = {
    "id", "screen_id", "figma_node_id", "parent_id", "path",
    "name", "node_type", "depth", "sort_order", "is_semantic",
    "component_id", "component_key",
    "x", "y",  # Position is spatial encoding, not a visual property
    "extracted_at",
    # Per-side stroke weights (handled directly, not via registry)
    "stroke_top_weight", "stroke_right_weight",
    "stroke_bottom_weight", "stroke_left_weight",
    # Vector geometry (asset pipeline)
    "fill_geometry", "stroke_geometry",
    # Grid layout (future)
    "grid_row_count", "grid_column_count",
    "grid_row_gap", "grid_column_gap",
    "grid_row_sizes", "grid_column_sizes",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistryCompleteness:
    """Every canonical Figma property has a registry entry or documented exclusion."""

    def test_all_canonical_properties_accounted_for(self):
        """No canonical Figma property is silently missing from the registry."""
        registered = {p.figma_name for p in PROPERTIES}
        excluded = set(_DOCUMENTED_EXCLUSIONS.keys())
        accounted = registered | excluded

        missing = _CANONICAL_FIGMA_PROPERTIES - accounted
        assert not missing, (
            f"Canonical Figma properties missing from registry AND exclusions: {sorted(missing)}. "
            f"Add to PROPERTIES in property_registry.py or to _DOCUMENTED_EXCLUSIONS with reason."
        )

    def test_no_stale_exclusions(self):
        """Documented exclusions don't overlap with registered properties."""
        registered = {p.figma_name for p in PROPERTIES}
        excluded = set(_DOCUMENTED_EXCLUSIONS.keys())

        overlap = registered & excluded
        assert not overlap, (
            f"Properties in BOTH registry and exclusions (remove from exclusions): {sorted(overlap)}"
        )


class TestDBSchemaAlignment:
    """Every DB column maps to a registry entry or is documented as structural."""

    @pytest.fixture
    def db_columns(self) -> set[str]:
        conn = init_db(":memory:")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
        conn.close()
        return cols

    def test_all_db_columns_accounted_for(self, db_columns: set[str]):
        """No DB column is silently missing from registry or structural list."""
        registry_cols = {p.db_column for p in PROPERTIES if p.db_column}
        accounted = registry_cols | _STRUCTURAL_DB_COLUMNS

        missing = db_columns - accounted
        assert not missing, (
            f"DB columns not in registry or structural list: {sorted(missing)}. "
            f"Add to PROPERTIES or _STRUCTURAL_DB_COLUMNS."
        )

    def test_all_registry_columns_exist_in_db(self, db_columns: set[str]):
        """No registry entry references a DB column that doesn't exist."""
        registry_cols = {p.db_column for p in PROPERTIES if p.db_column}

        missing = registry_cols - db_columns
        assert not missing, (
            f"Registry references DB columns that don't exist: {sorted(missing)}. "
            f"Add column to schema.sql or fix db_column in registry."
        )

    def test_no_stale_structural_columns(self, db_columns: set[str]):
        """Structural column list doesn't include non-existent columns."""
        missing = _STRUCTURAL_DB_COLUMNS - db_columns
        assert not missing, (
            f"Structural list includes non-existent DB columns: {sorted(missing)}. "
            f"Remove from _STRUCTURAL_DB_COLUMNS."
        )


class TestExtractionAlignment:
    """Extraction scripts capture all registered properties."""

    def test_plugin_api_captures_registered_visual_properties(self):
        """The Plugin API extraction script reads all key visual properties."""
        from dd.extract_screens import generate_extraction_script
        script = generate_extraction_script("1:1")

        # Properties that must appear in extraction JS (by Figma API name)
        required_in_script = {
            "fills", "strokes", "effects",
            "cornerRadius", "cornerSmoothing",
            "opacity", "blendMode", "visible",
            "strokeWeight", "strokeAlign",
            "rotation", "clipsContent",
            "isMask",
            "booleanOperation", "arcData",
            "layoutMode",
            "fontSize",
        }

        missing = {name for name in required_in_script if name not in script}
        assert not missing, (
            f"Plugin API extraction script missing properties: {sorted(missing)}"
        )
