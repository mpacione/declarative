"""Tests for the property registry — structural coverage and emit patterns."""

from dd.property_registry import PROPERTIES, by_db_column, by_figma_name


class TestRegistryEmitCoverage:
    """Every property must declare how it is emitted by each registered renderer."""

    # Properties handled by custom emit functions (not string templates)
    _COMPLEX_EMIT = frozenset({
        "fills", "strokes", "effects",  # JSON array emitters
        "cornerRadius",                  # uniform vs per-corner
        "fontFamily", "fontWeight",      # combined into fontName
        "characters",                    # text content
    })

    # Properties emitted in deferred/special sections (not main emit block)
    _DEFERRED_EMIT = frozenset({
        "constraints.horizontal", "constraints.vertical",  # deferred after position
        "width", "height",              # resize() call
        "layoutSizingHorizontal", "layoutSizingVertical",  # conditional on context
    })

    def test_every_property_has_figma_emit_pattern(self):
        missing = []
        for prop in PROPERTIES:
            if prop.figma_name in self._COMPLEX_EMIT:
                continue
            if prop.figma_name in self._DEFERRED_EMIT:
                continue
            emit = getattr(prop, "emit", {})
            if "figma" not in emit:
                missing.append(prop.figma_name)
        assert not missing, (
            f"Properties missing figma emit pattern: {missing}"
        )

    def test_complex_properties_have_none_emit(self):
        for prop in PROPERTIES:
            if prop.figma_name in self._COMPLEX_EMIT:
                emit = getattr(prop, "emit", {})
                assert emit.get("figma") is None, (
                    f"{prop.figma_name} is complex but has a string emit pattern"
                )


class TestRegistryLookups:
    """Verify registry lookup helpers return correct results."""

    def test_by_db_column_finds_property(self):
        prop = by_db_column("stroke_align")
        assert prop is not None
        assert prop.figma_name == "strokeAlign"

    def test_by_figma_name_finds_property(self):
        prop = by_figma_name("layoutWrap")
        assert prop is not None
        assert prop.db_column == "layout_wrap"

    def test_by_db_column_returns_none_for_unknown(self):
        assert by_db_column("nonexistent") is None

    def test_by_figma_name_returns_none_for_unknown(self):
        assert by_figma_name("nonexistent") is None


class TestRegistryEmitHelper:
    """Verify the registry-driven emit helper produces correct JS."""

    def test_emit_simple_number(self):
        from dd.generate import emit_from_registry
        lines = emit_from_registry("v", {"opacity": 0.5}, renderer="figma")
        assert 'v.opacity = 0.5;' in lines

    def test_emit_simple_enum(self):
        from dd.generate import emit_from_registry
        lines = emit_from_registry("v", {"strokeAlign": "INSIDE"}, renderer="figma")
        assert 'v.strokeAlign = "INSIDE";' in lines

    def test_skips_none_values(self):
        from dd.generate import emit_from_registry
        lines = emit_from_registry("v", {"opacity": None}, renderer="figma")
        assert not any("opacity" in l for l in lines)

    def test_skips_complex_properties(self):
        from dd.generate import emit_from_registry
        lines = emit_from_registry("v", {"fills": [{"type": "solid"}]}, renderer="figma")
        assert not any("fills" in l for l in lines)

    def test_emits_multiple_properties(self):
        from dd.generate import emit_from_registry
        lines = emit_from_registry("v", {
            "strokeAlign": "OUTSIDE",
            "minWidth": 100,
            "layoutWrap": "WRAP",
        }, renderer="figma")
        assert 'v.strokeAlign = "OUTSIDE";' in lines
        assert 'v.minWidth = 100;' in lines
        assert 'v.layoutWrap = "WRAP";' in lines


class TestRegistryCompleteness:
    """Verify the registry covers all expected property categories."""

    def test_all_categories_present(self):
        categories = {p.category for p in PROPERTIES}
        assert categories == {"visual", "layout", "size", "text", "constraint"}

    def test_property_count(self):
        assert len(PROPERTIES) >= 48, (
            f"Expected at least 48 properties, got {len(PROPERTIES)}"
        )
