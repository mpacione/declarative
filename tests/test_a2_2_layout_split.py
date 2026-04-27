"""A2.2: per-property dispatch for `_emit_layout()` in `dd/renderers/figma.py`.

Forensic-audit-2 found that `_emit_layout()` bundles all auto-layout
container properties into one emission. This blocks per-property
provenance gating (Backlog #1): when an instance has a `padding`
override but not an `itemSpacing` override, the renderer must be able
to emit only padding. With the bundle, that's impossible.

A2.2 splits the function into a per-property dispatch table while
preserving:
- The existing call-site signature (back-compat with two callers).
- Existing leaf-type behaviour (rectangle/text/etc. skip auto-layout).
- The resize() block (different lifecycle: parent-context dependent).
- Token-binding ref propagation for tokenizable properties.

Codex 5.5 review (gpt-5.5 high reasoning, 2026-04-26):
"Lower semantic layout names → Figma names via dispatch table, then
emit per-property through registry capability gates. Don't drag
resize() into the layout gate. Use a small dispatch table rather than
many bespoke functions."

The dispatch table doubles as a provenance gate hook for future work:
each entry's figma_name maps cleanly to a property in
`dd/property_registry.py:171-218` and (eventually) to a single override
field in `_overrides`.
"""

from dd.renderers.figma import _emit_layout, _LAYOUT_DISPATCH


class TestPerPropertyEmissionContract:
    """The headline A2.2 contract: each layout property is independently
    gated and emitted. Today's bundle behaviour is replaced by a
    per-property dispatch."""

    def test_layout_emits_padding_only_when_padding_present(self):
        """An IR layout dict carrying ONLY padding must produce padding
        lines and NO itemSpacing / layoutMode / alignment lines.
        Pre-A2.2 the bundle still emitted layoutMode/alignment as
        side-effects of the same call; A2.2 makes each property
        independent."""
        layout = {"padding": {"top": 8, "left": 16, "right": 16, "bottom": 8}}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert "paddingTop = 8" in joined
        assert "paddingLeft = 16" in joined
        assert "paddingRight = 16" in joined
        assert "paddingBottom = 8" in joined
        assert "layoutMode" not in joined, (
            "A2.2: padding-only IR must not synthesize layoutMode"
        )
        assert "itemSpacing" not in joined, (
            "A2.2: padding-only IR must not synthesize itemSpacing"
        )
        assert "primaryAxisAlignItems" not in joined
        assert "counterAxisAlignItems" not in joined

    def test_layout_emits_itemspacing_independently(self):
        """An IR layout dict carrying ONLY gap (itemSpacing) must produce
        an itemSpacing line and no padding. Symmetric to the previous
        test — proves itemSpacing isn't coupled to padding emission."""
        layout = {"gap": 12}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert "itemSpacing = 12" in joined
        assert "padding" not in joined.lower(), (
            "A2.2: gap-only IR must not synthesize padding"
        )
        assert "layoutMode" not in joined

    def test_layout_emits_direction_independently(self):
        """An IR layout dict carrying ONLY direction must produce
        layoutMode and nothing else."""
        layout = {"direction": "horizontal"}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert 'layoutMode = "HORIZONTAL"' in joined
        assert "itemSpacing" not in joined
        assert "padding" not in joined.lower()
        assert "primaryAxisAlignItems" not in joined

    def test_layout_emits_main_axis_alignment_independently(self):
        """Alignment props were in a SECOND `not is_leaf` block in the
        pre-split code (after resize). A2.2 unifies them into the
        dispatch but must still emit only when the property is set."""
        layout = {"mainAxisAlignment": "center"}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert 'primaryAxisAlignItems = "CENTER"' in joined
        assert "counterAxisAlignItems" not in joined
        assert "layoutMode" not in joined

    def test_layout_emits_counter_axis_gap_independently(self):
        """counterAxisGap → counterAxisSpacing. Independent of itemSpacing."""
        layout = {"counterAxisGap": 4}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert "counterAxisSpacing = 4" in joined
        assert "itemSpacing" not in joined

    def test_layout_emits_wrap_independently(self):
        """wrap=WRAP emits layoutWrap. NO_WRAP is the default and is
        skipped (preserves pre-split behaviour)."""
        layout = {"wrap": "WRAP"}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert 'layoutWrap = "WRAP"' in joined

        layout_no_wrap = {"wrap": "NO_WRAP"}
        lines2, _refs2 = _emit_layout(
            "v", "eid", layout_no_wrap, {}, etype="frame",
        )
        joined2 = "\n".join(lines2)
        assert "layoutWrap" not in joined2, (
            "NO_WRAP is the Plugin API default — skip emit (matches "
            "pre-split behaviour and skip_emit_if_default convention)."
        )


class TestCapabilityGating:
    """Per-property gates skip auto-layout props when the etype's
    Figma native node type doesn't support them. The leaf-type pre-gate
    is preserved as a defense-in-depth backstop for etypes whose IR-to-
    Figma-type mapping is incomplete (`star`, `polygon`, `image` —
    bridge gap; out of scope for A2.2 to fix)."""

    def test_layout_skips_padding_on_non_container_type(self):
        """rectangle is a leaf type — auto-layout-only props skipped.
        The existing test_emit_layout_skips_auto_layout_props_on_text_etype
        test pinned this for `text`; here we add coverage for rectangle."""
        layout = {
            "direction": "vertical",
            "gap": 16,
            "padding": {"top": 8, "left": 16, "right": 16, "bottom": 8},
            "mainAxisAlignment": "center",
            "crossAxisAlignment": "start",
        }
        lines, _refs = _emit_layout(
            "v", "eid", layout, {}, etype="rectangle",
        )
        joined = "\n".join(lines)
        assert "layoutMode" not in joined
        assert "itemSpacing" not in joined
        assert "padding" not in joined.lower()
        assert "primaryAxisAlignItems" not in joined
        assert "counterAxisAlignItems" not in joined

    def test_layout_legacy_caller_no_etype_emits_all_properties(self):
        """When etype is None (legacy callers — pre-A2.2 behaviour),
        the leaf-type pre-gate is bypassed and ALL properties emit.
        Extracted IR never has layout.direction set on a leaf node so
        this is safe; it preserves back-compat for any caller that
        doesn't pass etype."""
        layout = {
            "direction": "vertical",
            "gap": 8,
            "padding": {"top": 4},
        }
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype=None)
        joined = "\n".join(lines)
        assert 'layoutMode = "VERTICAL"' in joined
        assert "itemSpacing = 8" in joined
        assert "paddingTop = 4" in joined


class TestTokenBindingPreservation:
    """Token-bound layout properties must propagate to the returned
    `refs` list. Each entry is `(eid, semantic_path, token_name)` —
    the semantic path matches the pre-split labels (e.g. `padding.top`,
    not `paddingTop`) so consumers don't break."""

    def test_token_bound_itemspacing_propagates_to_refs(self):
        layout = {"gap": "{space.s16}"}
        tokens = {"space.s16": 16}
        lines, refs = _emit_layout(
            "v", "eid", layout, tokens, etype="frame",
        )
        joined = "\n".join(lines)
        assert "itemSpacing = 16" in joined
        assert ("eid", "itemSpacing", "space.s16") in refs

    def test_token_bound_counter_axis_spacing_propagates_to_refs(self):
        layout = {"counterAxisGap": "{space.s4}"}
        tokens = {"space.s4": 4}
        lines, refs = _emit_layout(
            "v", "eid", layout, tokens, etype="frame",
        )
        joined = "\n".join(lines)
        assert "counterAxisSpacing = 4" in joined
        assert ("eid", "counterAxisSpacing", "space.s4") in refs

    def test_token_bound_padding_uses_dotted_semantic_label(self):
        """Pre-split, padding token refs used the `padding.top` label
        (NOT the figma name `paddingTop`). Preserve that — downstream
        consumers compare on the semantic label."""
        layout = {"padding": {"top": "{space.s8}", "left": "{space.s16}"}}
        tokens = {"space.s8": 8, "space.s16": 16}
        lines, refs = _emit_layout(
            "v", "eid", layout, tokens, etype="frame",
        )
        joined = "\n".join(lines)
        assert "paddingTop = 8" in joined
        assert "paddingLeft = 16" in joined
        ref_set = set(refs)
        assert ("eid", "padding.top", "space.s8") in ref_set
        assert ("eid", "padding.left", "space.s16") in ref_set


class TestResizeInvariants:
    """Codex 5.5: 'Don't drag resize() into the layout gate — different
    ordering + parent context semantics.' The resize block stays as-is.
    These tests pin the resize behaviour against accidental regression."""

    def test_resize_emitted_for_pixel_sizing(self):
        layout = {"sizing": {"widthPixels": 320, "heightPixels": 200}}
        lines, _refs = _emit_layout("v", "eid", layout, {}, etype="frame")
        joined = "\n".join(lines)
        assert "resize(320, 200)" in joined

    def test_resize_skipped_for_text_with_width_and_height_autoresize(self):
        """Text-node guard: WIDTH_AND_HEIGHT autoResize means content
        determines size; resize() would lock the width and break wrap."""
        layout = {"sizing": {"widthPixels": 100, "heightPixels": 24}}
        lines, _refs = _emit_layout(
            "v", "eid", layout, {},
            text_auto_resize="WIDTH_AND_HEIGHT", etype="text",
        )
        joined = "\n".join(lines)
        assert "resize(" not in joined

    def test_resize_emitted_for_leaf_types_without_layout_props(self):
        """Leaf types still get resize — width/height are universally
        supported. Just no auto-layout props."""
        layout = {
            "direction": "vertical",  # gated out
            "sizing": {"widthPixels": 120, "heightPixels": 40},
        }
        lines, _refs = _emit_layout(
            "v", "eid", layout, {}, etype="rectangle",
        )
        joined = "\n".join(lines)
        assert "layoutMode" not in joined
        assert "resize(120, 40)" in joined


class TestEmissionOrder:
    """Codex 5.5: 'Preserve current emission order. Alignment currently
    happens after resize(). Don't accidentally move all layout props
    into one pre-resize loop.' Pin that order."""

    def test_alignment_emitted_after_resize(self):
        """Pre-split: layoutMode/padding/itemSpacing → resize() →
        alignment. Preserve that ordering."""
        layout = {
            "direction": "vertical",
            "sizing": {"widthPixels": 100, "heightPixels": 50},
            "mainAxisAlignment": "center",
        }
        lines, _refs = _emit_layout(
            "v", "eid", layout, {}, etype="frame",
        )
        # Find indices of the marker substrings
        idx_layout_mode = next(
            i for i, l in enumerate(lines) if "layoutMode" in l
        )
        idx_resize = next(
            i for i, l in enumerate(lines) if "resize(" in l
        )
        idx_align = next(
            i for i, l in enumerate(lines) if "primaryAxisAlignItems" in l
        )
        assert idx_layout_mode < idx_resize < idx_align, (
            f"Expected layoutMode → resize → alignment ordering; got "
            f"indices {idx_layout_mode}, {idx_resize}, {idx_align}: "
            f"{lines}"
        )


class TestNoLayoutEmissionForText:
    """Regression guard for the existing call-site contract: in
    dd/render_figma_ast.py:1086 the call site itself gates with
    `if layout and not is_text`. Inside _emit_layout, text_auto_resize
    + etype='text' is the secondary guard. This pins that contract."""

    def test_no_layout_emission_for_text_etype(self):
        """Setting auto-layout props on a TEXT node throws Plugin API
        'object is not extensible'. The leaf-type gate must catch
        every text etype."""
        from dd.renderers.figma import _TEXT_TYPES

        layout = {
            "direction": "vertical",
            "gap": 16,
            "padding": {"top": 8},
            "mainAxisAlignment": "center",
        }
        for text_etype in _TEXT_TYPES:
            lines, _refs = _emit_layout(
                "v", "eid", layout, {}, etype=text_etype,
            )
            joined = "\n".join(lines)
            assert "layoutMode" not in joined, (
                f"text etype {text_etype!r} must skip layoutMode"
            )
            assert "itemSpacing" not in joined
            assert "padding" not in joined.lower()
            assert "primaryAxisAlignItems" not in joined


class TestDispatchTableStructure:
    """The dispatch table is module-level so it's inspectable +
    testable. Pin its shape so future edits don't accidentally change
    the contract."""

    def test_dispatch_table_is_module_level(self):
        """`_LAYOUT_DISPATCH` exists as a module-level constant."""
        assert _LAYOUT_DISPATCH is not None
        assert len(_LAYOUT_DISPATCH) > 0

    def test_dispatch_table_covers_every_layout_property(self):
        """Every figma_name in the dispatch must correspond to a
        registry property in the 'layout' category. Conversely every
        layout property the registry knows about (excluding deferred
        ones) must be in the dispatch table — otherwise we silently
        dropped emission."""
        from dd.property_registry import PROPERTIES

        dispatch_figma_names = {
            entry["figma_name"] for entry in _LAYOUT_DISPATCH
        }
        registry_layout_names = {
            p.figma_name for p in PROPERTIES
            if p.category == "layout"
        }
        # Deferred (handled outside _emit_layout):
        # - layoutSizingHorizontal/Vertical: emitted post-appendChild
        # - layoutPositioning: not currently emitted by this path
        deferred = {
            "layoutSizingHorizontal",
            "layoutSizingVertical",
            "layoutPositioning",
        }
        expected = registry_layout_names - deferred
        assert dispatch_figma_names == expected, (
            f"Dispatch ↔ registry skew: "
            f"only-in-dispatch={dispatch_figma_names - expected}, "
            f"only-in-registry={expected - dispatch_figma_names}"
        )


class TestProvenanceGatingHook:
    """Forward-looking: the dispatch table is the future hook for
    Backlog #1 per-property provenance gating. Pin the shape that
    enables that without yet wiring the gate. The test asserts the
    figma_name on each entry is unique (so a future provenance check
    `figma_name in instance._overrides` is unambiguous)."""

    def test_each_dispatch_entry_has_unique_figma_name(self):
        figma_names = [entry["figma_name"] for entry in _LAYOUT_DISPATCH]
        assert len(figma_names) == len(set(figma_names)), (
            f"Duplicate figma_name in dispatch table: {figma_names}"
        )
