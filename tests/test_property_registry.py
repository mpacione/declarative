"""Tests for the property registry — structural coverage and emit patterns."""

from dd.property_registry import (
    PROPERTIES,
    by_db_column,
    by_figma_name,
    is_capable,
)


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


class TestBackendCapabilities:
    """Properties declare per-backend node-type capabilities.

    Prevents emitting properties on node types that don't support them
    (e.g. clipsContent on RECTANGLE → 'object is not extensible' at runtime).
    Capability is the single source of truth queried at emission time; the
    same table serves as constrained-decoding grammar for synthetic IR.
    """

    def test_clips_content_constrained_to_containers(self):
        assert is_capable("clipsContent", "figma", "FRAME") is True
        assert is_capable("clipsContent", "figma", "COMPONENT") is True
        assert is_capable("clipsContent", "figma", "INSTANCE") is True
        assert is_capable("clipsContent", "figma", "SECTION") is True
        assert is_capable("clipsContent", "figma", "RECTANGLE") is False
        assert is_capable("clipsContent", "figma", "ELLIPSE") is False
        assert is_capable("clipsContent", "figma", "VECTOR") is False
        assert is_capable("clipsContent", "figma", "LINE") is False
        assert is_capable("clipsContent", "figma", "TEXT") is False

    def test_layout_properties_constrained_to_containers(self):
        for prop in ("layoutMode", "paddingTop", "paddingLeft",
                     "itemSpacing", "layoutWrap",
                     "primaryAxisAlignItems", "counterAxisAlignItems"):
            assert is_capable(prop, "figma", "FRAME") is True, prop
            assert is_capable(prop, "figma", "RECTANGLE") is False, prop
            assert is_capable(prop, "figma", "TEXT") is False, prop

    def test_text_properties_constrained_to_text(self):
        for prop in ("characters", "fontSize", "textAlignHorizontal",
                     "textAutoResize", "lineHeight"):
            assert is_capable(prop, "figma", "TEXT") is True, prop
            assert is_capable(prop, "figma", "FRAME") is False, prop
            assert is_capable(prop, "figma", "RECTANGLE") is False, prop

    def test_corner_radius_excludes_line_and_text(self):
        assert is_capable("cornerRadius", "figma", "RECTANGLE") is True
        assert is_capable("cornerRadius", "figma", "FRAME") is True
        assert is_capable("cornerRadius", "figma", "LINE") is False
        assert is_capable("cornerRadius", "figma", "TEXT") is False

    def test_type_specific_props(self):
        assert is_capable("arcData", "figma", "ELLIPSE") is True
        assert is_capable("arcData", "figma", "RECTANGLE") is False
        assert is_capable("booleanOperation", "figma", "BOOLEAN_OPERATION") is True
        assert is_capable("booleanOperation", "figma", "FRAME") is False

    def test_universal_props_capable_on_all_visible(self):
        """Properties like fills, opacity apply to every visible node type."""
        for node_type in ("FRAME", "RECTANGLE", "ELLIPSE", "VECTOR", "TEXT",
                          "INSTANCE", "LINE"):
            assert is_capable("opacity", "figma", node_type) is True, node_type
            assert is_capable("visible", "figma", node_type) is True, node_type
            assert is_capable("rotation", "figma", node_type) is True, node_type

    def test_unknown_property_returns_false(self):
        """Unknown properties must not pass capability check — fail closed here
        because this IS the output gate, not extraction (which fails open)."""
        assert is_capable("nonexistent", "figma", "FRAME") is False

    def test_unknown_backend_returns_false(self):
        """A property with no capability entry for a given backend is not
        emittable on that backend — forces explicit backend support."""
        assert is_capable("clipsContent", "react", "div") is False


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
        # REST API positive rad (CCW) → Plugin API negative degrees (CW)
        result = format_js_value(math.pi / 4, "number_radians")
        assert abs(float(result) - (-45.0)) < 0.01

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
        # REST API positive rad (CCW) → Plugin API negative degrees (CW)
        result = format_js_value(math.pi / 2, "number_radians")
        assert abs(float(result) - (-90.0)) < 0.01

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


    def test_token_refs_collected_for_bound_properties(self):
        from dd.renderers.figma import emit_from_registry
        visual = {
            "opacity": 0.5,
            "cornerRadius": 8.0,
            "_token_refs": {"opacity": "opacity.half", "cornerRadius": "radius.md"},
        }
        lines, refs = emit_from_registry("v", "e1", visual, {})
        ref_map = {prop: token for (_, prop, token) in refs}
        assert ref_map["opacity"] == "opacity.half"
        assert ref_map["cornerRadius"] == "radius.md"

    def test_no_token_refs_when_absent(self):
        from dd.renderers.figma import emit_from_registry
        visual = {"opacity": 0.5}
        _, refs = emit_from_registry("v", "e1", visual, {})
        assert not any(prop == "opacity" for (_, prop, _) in refs)


class TestCapabilityGatedEmission:
    """emit_from_registry must skip properties whose capability set doesn't
    include the given Figma native node_type. This is the output gate — it
    prevents 'object is not extensible' runtime errors from properties landing
    on node types that don't support them (e.g. clipsContent on RECTANGLE).
    """

    def test_clips_content_skipped_on_rectangle(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e", {"clipsContent": False}, {}, node_type="RECTANGLE",
        )
        assert not any("clipsContent" in l for l in lines)

    def test_clips_content_emitted_on_frame(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e", {"clipsContent": False}, {}, node_type="FRAME",
        )
        assert any("clipsContent = false" in l for l in lines)

    def test_layout_mode_skipped_on_text(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e", {"layoutMode": "VERTICAL"}, {}, node_type="TEXT",
        )
        assert not any("layoutMode" in l for l in lines)

    def test_padding_skipped_on_rectangle(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e",
            {"paddingTop": 10, "paddingLeft": 20, "itemSpacing": 8},
            {}, node_type="RECTANGLE",
        )
        assert not any("padding" in l.lower() for l in lines)
        assert not any("itemSpacing" in l for l in lines)

    def test_text_align_skipped_on_frame(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e", {"textAlignHorizontal": "CENTER"}, {}, node_type="FRAME",
        )
        assert not any("textAlignHorizontal" in l for l in lines)

    def test_corner_radius_skipped_on_line(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e", {"cornerRadius": 8}, {}, node_type="LINE",
        )
        assert not any("cornerRadius" in l for l in lines)

    def test_arc_data_skipped_on_rectangle(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e",
            {"arcData": {"startingAngle": 0, "endingAngle": 1.57, "innerRadius": 0}},
            {}, node_type="RECTANGLE",
        )
        assert not any("arcData" in l for l in lines)

    def test_arc_data_emitted_on_ellipse(self):
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry(
            "v", "e",
            {"arcData": {"startingAngle": 0, "endingAngle": 1.57, "innerRadius": 0}},
            {}, node_type="ELLIPSE",
        )
        assert any("arcData" in l for l in lines)

    def test_no_node_type_means_permissive(self):
        """Backwards compatibility: callers without node_type get full emission.
        Capability gating is opt-in at the call site (main generator passes it);
        tests and legacy callers stay permissive."""
        from dd.renderers.figma import emit_from_registry
        lines, _ = emit_from_registry("v", "e", {"clipsContent": False}, {})
        assert any("clipsContent = false" in l for l in lines)


class TestIrToFigmaType:
    """Maps IR node type strings ('rectangle', 'frame', 'text') to Figma
    native Plugin API types ('RECTANGLE', 'FRAME', 'TEXT'). Used at the
    emission site so the registry's capability table can gate correctly."""

    def test_basic_shapes(self):
        from dd.renderers.figma import ir_to_figma_type
        assert ir_to_figma_type("rectangle") == "RECTANGLE"
        assert ir_to_figma_type("ellipse") == "ELLIPSE"
        assert ir_to_figma_type("line") == "LINE"
        assert ir_to_figma_type("vector") == "VECTOR"
        assert ir_to_figma_type("boolean_operation") == "BOOLEAN_OPERATION"

    def test_text_types(self):
        from dd.renderers.figma import ir_to_figma_type
        assert ir_to_figma_type("text") == "TEXT"
        assert ir_to_figma_type("heading") == "TEXT"
        assert ir_to_figma_type("link") == "TEXT"

    def test_containers_default_to_frame(self):
        """Unknown / container-like IR types render as FRAME in Figma."""
        from dd.renderers.figma import ir_to_figma_type
        assert ir_to_figma_type("frame") == "FRAME"
        assert ir_to_figma_type("container") == "FRAME"
        assert ir_to_figma_type("screen") == "FRAME"
        assert ir_to_figma_type("section") == "FRAME"


class TestRegistryCompleteness:
    """Verify the registry covers all expected property categories."""

    def test_all_categories_present(self):
        categories = {p.category for p in PROPERTIES}
        assert categories == {"visual", "layout", "size", "text", "constraint"}

    def test_property_count(self):
        assert len(PROPERTIES) >= 52, (
            f"Expected at least 52 properties, got {len(PROPERTIES)}"
        )
