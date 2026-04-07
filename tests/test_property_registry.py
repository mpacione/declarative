"""Tests for the property registry — structural coverage and emit patterns."""

from dd.property_registry import PROPERTIES, by_db_column, by_figma_name


class TestRegistryEmitCoverage:
    """Every property must be classified: template, handler, or deferred."""

    # Properties with HANDLER sentinel — dispatched to _FIGMA_HANDLERS
    _HANDLER_EMIT = frozenset({
        "fills", "strokes", "effects",  # JSON array emitters
        "cornerRadius",                  # uniform vs per-corner
        "clipsContent",                  # JS boolean + always-emit
    })

    # Properties emitted in deferred/special sections (empty emit dict)
    _DEFERRED_EMIT = frozenset({
        "constraints.horizontal", "constraints.vertical",  # deferred after position
        "width", "height",              # resize() call
        "layoutSizingHorizontal", "layoutSizingVertical",  # conditional on context
        "visible",                       # main generation loop
        "characters",                    # _emit_text_props
        "fontFamily", "fontWeight",      # combined into fontName in _emit_text_props
    })

    def test_every_property_classified(self):
        """Every property must be template, handler, or deferred."""
        from dd.property_registry import HANDLER
        unclassified = []
        for prop in PROPERTIES:
            emit = prop.emit
            if not emit:
                if prop.figma_name not in self._DEFERRED_EMIT:
                    unclassified.append(prop.figma_name)
                continue
            spec = emit.get("figma")
            if spec is HANDLER:
                continue
            if isinstance(spec, str):
                continue
            unclassified.append(prop.figma_name)
        assert not unclassified, (
            f"Properties not classified as template/handler/deferred: {unclassified}"
        )

    def test_handler_properties_have_handler_sentinel(self):
        from dd.property_registry import HANDLER
        for prop in PROPERTIES:
            if prop.figma_name in self._HANDLER_EMIT:
                assert prop.emit.get("figma") is HANDLER, (
                    f"{prop.figma_name} should use HANDLER sentinel"
                )

    def test_handler_properties_registered(self):
        from dd.renderers.figma import _FIGMA_HANDLERS, _register_figma_handlers
        _register_figma_handlers()
        for name in self._HANDLER_EMIT:
            assert name in _FIGMA_HANDLERS, (
                f"{name} is HANDLER but has no entry in _FIGMA_HANDLERS"
            )

    def test_deferred_properties_have_empty_emit(self):
        for prop in PROPERTIES:
            if prop.figma_name in self._DEFERRED_EMIT:
                assert not prop.emit, (
                    f"{prop.figma_name} is deferred but has emit={prop.emit}"
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


class TestFormatJsValue:
    """Verify type-aware JS value formatting."""

    def test_number(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(42, "number") == "42"
        assert format_js_value(0.5, "number") == "0.5"

    def test_number_radians_passthrough_as_degrees(self):
        import math
        from dd.renderers.figma import format_js_value
        result = format_js_value(math.pi / 4, "number_radians")
        assert abs(float(result) - 45.0) < 0.01

    def test_enum(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value("CENTER", "enum") == '"CENTER"'

    def test_string(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value("hello", "string") == '"hello"'

    def test_string_escapes_quotes(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value('say "hi"', "string") == '"say \\"hi\\""'

    def test_boolean_true(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(True, "boolean") == "true"

    def test_boolean_false(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(False, "boolean") == "false"

    def test_boolean_string_true(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value("true", "boolean") == "true"

    def test_boolean_string_false(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value("false", "boolean") == "false"

    def test_boolean_int_0(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(0, "boolean") == "false"

    def test_boolean_int_1(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(1, "boolean") == "true"

    def test_json_dict(self):
        from dd.renderers.figma import format_js_value
        result = format_js_value({"value": 24, "unit": "PIXELS"}, "json")
        assert '"value": 24' in result
        assert '"unit": "PIXELS"' in result

    def test_json_already_string(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value('{"value": 24}', "json") == '{"value": 24}'

    def test_json_array(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value([10, 5], "json_array") == "[10, 5]"

    def test_number_radians_converts_to_degrees(self):
        import math
        from dd.renderers.figma import format_js_value
        result = format_js_value(math.pi / 2, "number_radians")
        assert abs(float(result) - 90.0) < 0.01

    def test_number_or_mixed(self):
        from dd.renderers.figma import format_js_value
        assert format_js_value(16, "number_or_mixed") == "16"


class TestRegistryEmitHelper:
    """Verify the registry-driven emit helper produces correct JS."""

    def test_emit_simple_number(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry("v", "e", {"opacity": 0.5}, {})
        assert 'v.opacity = 0.5;' in lines

    def test_emit_simple_enum(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry("v", "e", {"strokeAlign": "INSIDE"}, {})
        assert 'v.strokeAlign = "INSIDE";' in lines

    def test_skips_none_values(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry("v", "e", {"opacity": None}, {})
        assert not any("opacity" in l for l in lines)

    def test_handler_properties_dispatched(self):
        from dd.renderers.figma import emit_from_registry
        lines, refs = emit_from_registry("v", "e", {
            "fills": [{"type": "solid", "color": "#FF0000"}],
        }, {})
        assert any("fills" in l for l in lines)

    def test_emits_multiple_properties(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry("v", "e", {
            "strokeAlign": "OUTSIDE",
            "minWidth": 100,
            "layoutWrap": "WRAP",
        }, {})
        assert 'v.strokeAlign = "OUTSIDE";' in lines
        assert 'v.minWidth = 100;' in lines
        assert 'v.layoutWrap = "WRAP";' in lines

    def test_clips_content_emits_js_boolean(self):
        from dd.renderers.figma import emit_from_registry
        lines_true, _ = emit_from_registry("v", "e", {"clipsContent": True}, {})
        assert any("clipsContent = true" in l for l in lines_true)
        lines_false, _ = emit_from_registry("v", "e", {"clipsContent": False}, {})
        assert any("clipsContent = false" in l for l in lines_false)


class TestRegistryCompleteness:
    """Verify the registry covers all expected property categories."""

    def test_all_categories_present(self):
        categories = {p.category for p in PROPERTIES}
        assert categories == {"visual", "layout", "size", "text", "constraint"}

    def test_property_count(self):
        assert len(PROPERTIES) >= 48, (
            f"Expected at least 48 properties, got {len(PROPERTIES)}"
        )
