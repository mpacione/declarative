"""F13a — `_deep_merge_element_keys` must merge nested dicts recursively.

Phase D visual-diff exposed: HGB Transactions Selected rendered the
"table with border" frame at 100x950 instead of source 1400x950, with
contents clipped. Bridge query:

  source: w=1400, h=950, layoutSizingH=HUG
  rendered: w=100, h=950, layoutSizingH=FIXED

The renderer's `_emit_layout` correctly emits `resize(widthPixels,
heightPixels)` from the IR. But `widthPixels: 1400.0` was getting
silently dropped between IR and the renderer.

Root cause: `dd/ast_to_element.py:_deep_merge_element_keys` was a
two-level merge. When `base["layout"]["sizing"]` had:
    {"width": "hug", "widthPixels": 1400, "height": 950}
and AST head's `overlay["layout"]["sizing"]` had:
    {"width": "hug", "heightPixels": 950}
the merge replaced `base.layout.sizing` whole with overlay's sizing
dict, losing `widthPixels: 1400` and `height: 950`. Even though the
function's docstring promised "only keys PRESENT in `overlay` are
touched."

F13a fixes the merge to recurse into nested dicts so the contract
holds at every depth. Codex gpt-5.5 review (2026-04-25): "Make
`_deep_merge_element_keys` recursively deep-merge dicts while
continuing to replace lists whole. That preserves
`layout.sizing.widthPixels` without requiring AST head emission to
know about spec provenance."
"""

from __future__ import annotations

from dd.ast_to_element import _deep_merge_element_keys


class TestRecursiveDictMerge:
    def test_top_level_key_only_in_base_survives(self):
        """Absent overlay key must not clobber base. (Was already
        true at top level pre-F13a; pinned for clarity.)"""
        base = {"a": 1, "b": 2}
        overlay = {"a": 10}
        result = _deep_merge_element_keys(base, overlay)
        assert result == {"a": 10, "b": 2}

    def test_nested_dict_key_only_in_base_survives(self):
        """The actual F13a bug: nested keys present in base but
        absent in overlay must NOT be clobbered when overlay has the
        outer dict."""
        base = {
            "layout": {
                "sizing": {
                    "width": "hug",
                    "widthPixels": 1400,
                    "height": 950,
                },
                "direction": "vertical",
            }
        }
        overlay = {
            "layout": {
                "sizing": {
                    "width": "hug",
                    "heightPixels": 950,
                },
            }
        }
        result = _deep_merge_element_keys(base, overlay)
        # widthPixels and height MUST survive; heightPixels added.
        assert result["layout"]["sizing"] == {
            "width": "hug",
            "widthPixels": 1400,
            "heightPixels": 950,
            "height": 950,
        }
        # And direction MUST survive (overlay didn't mention it).
        assert result["layout"]["direction"] == "vertical"

    def test_three_level_nesting_also_merges(self):
        """Recursion is unbounded — visual.shadow.color etc. should
        also work."""
        base = {
            "visual": {
                "effects": {
                    "shadow": {"x": 0, "y": 4, "color": "#000"},
                },
            },
        }
        overlay = {
            "visual": {
                "effects": {
                    "shadow": {"y": 8},
                },
            },
        }
        result = _deep_merge_element_keys(base, overlay)
        assert result["visual"]["effects"]["shadow"] == {
            "x": 0, "y": 8, "color": "#000",
        }

    def test_overlay_value_not_a_dict_replaces_base_dict(self):
        """If overlay supplies a non-dict where base had a dict,
        overlay wins (no merge possible). This preserves the
        existing 'overlay wins on type-mismatch' semantics."""
        base = {"layout": {"sizing": {"width": "hug"}}}
        overlay = {"layout": "not_a_dict"}
        result = _deep_merge_element_keys(base, overlay)
        assert result["layout"] == "not_a_dict"

    def test_lists_are_replaced_whole_not_merged(self):
        """Fills/strokes are ordered stacks; merging by index
        would silently corrupt the stack."""
        base = {
            "visual": {
                "fills": [
                    {"type": "solid", "color": "#fff"},
                    {"type": "solid", "color": "#000"},
                ],
            },
        }
        overlay = {
            "visual": {
                "fills": [{"type": "solid", "color": "#f00"}],
            },
        }
        result = _deep_merge_element_keys(base, overlay)
        assert result["visual"]["fills"] == [
            {"type": "solid", "color": "#f00"},
        ]

    def test_does_not_mutate_inputs(self):
        """The function must be pure (callers depend on this)."""
        base = {"layout": {"sizing": {"width": "hug", "widthPixels": 1400}}}
        overlay = {"layout": {"sizing": {"heightPixels": 950}}}
        base_snapshot = {"layout": {"sizing": {"width": "hug", "widthPixels": 1400}}}
        overlay_snapshot = {"layout": {"sizing": {"heightPixels": 950}}}
        _ = _deep_merge_element_keys(base, overlay)
        assert base == base_snapshot
        assert overlay == overlay_snapshot

    def test_empty_overlay_returns_base_copy(self):
        base = {"layout": {"sizing": {"width": "hug"}}}
        result = _deep_merge_element_keys(base, {})
        assert result == base
        # Different dict identity (the function returns a copy).
        assert result is not base


class TestF13aRegressionBugC:
    """Pin the table-with-border case end-to-end through resolve_element."""

    def test_table_with_border_widthPixels_survives_ast_head_overlay(self):
        """The exact case that broke HGB Transactions Selected:
        spec carries widthPixels=1400 (DB ground truth); AST head
        carries width=hug (semantic); the resolved layout MUST
        carry both so `_emit_layout` can `resize(1400, 950)`."""
        from dd.ast_to_element import _deep_merge_element_keys

        spec_element = {
            "type": "frame",
            "layout": {
                "direction": "vertical",
                "sizing": {
                    "width": "hug",
                    "widthPixels": 1400.0,
                    "height": 950.0,
                },
                "position": {"x": 20.0, "y": 172.0},
            },
        }
        # Simulating ast_head_to_element output for a head with
        # `width=hug height=950 layout=vertical`
        head_overlay = {
            "layout": {
                "sizing": {
                    "width": "hug",
                    "heightPixels": 950,
                },
                "direction": "vertical",
            },
        }
        merged = _deep_merge_element_keys(spec_element, head_overlay)
        # widthPixels MUST survive — that's what _emit_layout needs.
        assert merged["layout"]["sizing"].get("widthPixels") == 1400.0
        # height MUST survive too (the original DB pixel value).
        assert merged["layout"]["sizing"].get("height") == 950.0
        # And the AST-introduced heightPixels is also present.
        assert merged["layout"]["sizing"].get("heightPixels") == 950
