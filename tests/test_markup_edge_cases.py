"""dd markup — edge-case hardening tests.

Complements `test_markup_roundtrip.py` (which proves the 204-corpus works)
with tests for cases the corpus doesn't exercise but a production parser
must handle: unicode, escapes, deep nesting, numeric edge cases, empty
collections, error surfaces.

Each test describes a property that must hold after hardening.
"""

from __future__ import annotations

import pytest

from dd.markup import (
    DDMarkupError,
    DDMarkupParseError,
    parse_dd,
    serialize_ir,
)


def _roundtrip(spec: dict) -> dict:
    """Shortcut — returns `parse_dd(serialize_ir(spec))`."""
    return parse_dd(serialize_ir(spec))


def _minimal_spec(**overrides) -> dict:
    base = {
        "version": "1.0",
        "root": "",
        "elements": {},
        "tokens": {},
        "_node_id_map": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Empty collections
# ---------------------------------------------------------------------------


class TestEmptyCollections:
    def test_empty_list_roundtrips(self) -> None:
        spec = _minimal_spec(
            root="frame-1",
            elements={
                "frame-1": {
                    "type": "frame",
                    "layout": {"effects": []},
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_empty_children_list_roundtrips(self) -> None:
        """`"children": []` must distinguish from absent children."""
        spec = _minimal_spec(
            root="frame-1",
            elements={"frame-1": {"type": "frame", "children": []}},
        )
        assert _roundtrip(spec) == spec

    def test_absent_children_stays_absent(self) -> None:
        """No `children` key in input → no `children` key in output."""
        spec = _minimal_spec(
            root="rect-1",
            elements={"rect-1": {"type": "rectangle"}},
        )
        result = _roundtrip(spec)
        assert "children" not in result["elements"]["rect-1"]

    def test_empty_nested_dict_roundtrips(self) -> None:
        spec = _minimal_spec(
            root="frame-1",
            elements={"frame-1": {"type": "frame", "visual": {}}},
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# String escape sequences
# ---------------------------------------------------------------------------


class TestStringEscapes:
    def test_double_quote_in_string(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {
                    "type": "text",
                    "_original_name": 'She said "hi"',
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_backslash_in_string(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {"type": "text", "_original_name": r"path\to\file"},
            },
        )
        assert _roundtrip(spec) == spec

    def test_newline_in_string(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {
                    "type": "text",
                    "_original_name": "line1\nline2\nline3",
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_tab_in_string(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {"type": "text", "_original_name": "a\tb\tc"},
            },
        )
        assert _roundtrip(spec) == spec

    def test_empty_string_value(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={"s": {"type": "text", "_original_name": ""}},
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Unicode
# ---------------------------------------------------------------------------


class TestUnicode:
    def test_unicode_in_string_value(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {"type": "text", "_original_name": "café résumé 日本語 🎨"},
            },
        )
        assert _roundtrip(spec) == spec

    def test_emoji_in_string(self) -> None:
        spec = _minimal_spec(
            root="s",
            elements={
                "s": {"type": "text", "_original_name": "🔥💯👀"},
            },
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Numeric edge cases
# ---------------------------------------------------------------------------


class TestNumbers:
    def test_integer_positive(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={"e": {"type": "t", "layout": {"sizing": {"width": 42}}}},
        )
        assert _roundtrip(spec) == spec

    def test_integer_negative(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "layout": {"position": {"x": -100, "y": -42}},
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_integer_zero(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "layout": {"position": {"x": 0, "y": 0}},
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_float_positive(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "layout": {"sizing": {"width": 375.5, "height": 812.25}},
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_float_negative(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {"type": "t", "layout": {"position": {"x": -42.125}}},
            },
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Booleans and null
# ---------------------------------------------------------------------------


class TestBooleansAndNull:
    def test_bool_true(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={"e": {"type": "t", "visible": True, "_mode1_eligible": True}},
        )
        assert _roundtrip(spec) == spec

    def test_bool_false(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={"e": {"type": "t", "visible": False, "_mode1_eligible": False}},
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Deep nesting
# ---------------------------------------------------------------------------


class TestDeepNesting:
    def test_five_levels_of_nested_dicts(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "visual": {
                        "a": {"b": {"c": {"d": {"e": "deep"}}}},
                    },
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_tree_with_six_levels_of_children(self) -> None:
        elements = {}
        for i in range(6):
            eid = f"level-{i}"
            elements[eid] = {"type": "frame"}
            if i < 5:
                elements[eid]["children"] = [f"level-{i+1}"]
        spec = _minimal_spec(root="level-0", elements=elements)
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Token refs vs raw values (Mode E compatibility)
# ---------------------------------------------------------------------------


class TestTokenRefs:
    def test_token_ref_preserved(self) -> None:
        """Token refs like `{color.brand.primary}` are strings in Mode E.

        They survive round-trip unchanged — resolution happens downstream
        in TokenCascade, not in the serde.
        """
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "visual": {
                        "fills": [{"type": "solid", "color": "{color.brand.primary}"}],
                    },
                },
            },
        )
        assert _roundtrip(spec) == spec

    def test_mixed_raw_and_token_refs(self) -> None:
        spec = _minimal_spec(
            root="e",
            elements={
                "e": {
                    "type": "t",
                    "visual": {
                        "fills": [
                            {"type": "solid", "color": "#F6F6F6"},
                            {"type": "solid", "color": "{color.accent}"},
                        ],
                    },
                },
            },
        )
        assert _roundtrip(spec) == spec


# ---------------------------------------------------------------------------
# Error surface
# ---------------------------------------------------------------------------


class TestErrorSurface:
    def test_parse_error_is_typed(self) -> None:
        """Bad input raises a typed error, not a bare ValueError."""
        with pytest.raises(DDMarkupParseError):
            parse_dd('version "1.0"\nroot "x"\nunknown_top_level_node {}\n')

    def test_parse_error_inherits_base(self) -> None:
        with pytest.raises(DDMarkupError):
            parse_dd('version "1.0"\nroot "x"\nunknown_top_level_node {}\n')

    def test_parse_error_includes_line_info(self) -> None:
        """Error message should tell the user where in the source to look."""
        try:
            parse_dd('version "1.0"\nroot "x"\nbroken_node\n')
        except DDMarkupParseError as e:
            msg = str(e)
            # Some mention of line/position context
            assert "line" in msg.lower() or "position" in msg.lower() or "col" in msg.lower()
        else:
            pytest.fail("Expected DDMarkupParseError")

    def test_unterminated_string_is_typed_error(self) -> None:
        with pytest.raises(DDMarkupParseError):
            parse_dd('version "unterminated\n')

    def test_unexpected_char_is_typed_error(self) -> None:
        with pytest.raises(DDMarkupParseError):
            parse_dd("version @notvalid\n")
