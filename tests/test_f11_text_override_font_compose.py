"""F11 — Mode-1 text-override font composition + font-load guards.

Two compounding bugs surfaced 2026-04-25 on a Phase D probe of HGB
(Figma file using Akkurat / Akkurat-Bold via team-library components):

A. **Virtual font-identity setters.** The override emitter routed
   `fontFamily` / `fontWeight` / `fontStyle` through `by_figma_name`
   and emitted `_textNode.fontFamily = "DM Sans"`. TEXT nodes have no
   such setter — only a composed `_textNode.fontName = {family, style}`.
   Direct writes throw "object is not extensible". 18 of 21 walk
   errors on screen 1's probe were this class.

B. **Text-property writes without font preload.** Setting
   `letterSpacing`, `fontSize`, `textAlignVertical`, etc. on a TEXT
   node requires the node's CURRENT `fontName` to be loaded. The
   `characters` branch (line 363-368) already does this; other text
   props don't. When the master is library-imported (HGB pattern),
   the font isn't in the preamble's preload list, and the first
   override write throws "Cannot write to node with unloaded font 'X'".

This file pins both fixes:
- Composition: stray `fontFamily` etc. produce a single `fontName`
  write with the new font preloaded.
- Guard: every other text-category write is wrapped in
  `loadFontAsync(_t.fontName)` + `figma.mixed` skip.
"""

from __future__ import annotations

from dd.renderers.figma import (
    _FONT_IDENTITY_PROPS,
    _compose_font_identity_op,
    _emit_override_op,
    _emit_override_tree,
)


def _emit(node: dict) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    deferred: list[str] = []
    _emit_override_tree(node, "instance_var", {}, lines, deferred)
    return lines, deferred


class TestFontIdentityComposition:
    """A. Virtual fontFamily/fontWeight/fontStyle compose into fontName."""

    def test_font_identity_props_constant_is_correct(self):
        """The set must be exactly the three virtual identity props.
        Adding more (or fewer) silently changes which props get
        composed vs which get emitted directly."""
        assert _FONT_IDENTITY_PROPS == frozenset(
            {"fontFamily", "fontStyle", "fontWeight"}
        )

    def test_compose_no_font_props_returns_unchanged(self):
        """When no font-identity props are present, returns ("", original)
        so the caller iterates the unchanged list."""
        props = [
            {"property": "letterSpacing", "value": {"value": 0, "unit": "PIXELS"}},
            {"property": "fontSize", "value": 14},
        ]
        op, remaining = _compose_font_identity_op(props, "_c")
        assert op == ""
        # Identity (not just equality) preserves call-site behavior.
        assert remaining is props

    def test_compose_pulls_only_font_identity_props(self):
        """Other text props (letterSpacing, fontSize) must remain in
        `remaining` for the caller to emit normally."""
        props = [
            {"property": "fontFamily", "value": "DM Sans"},
            {"property": "letterSpacing", "value": {"value": 0, "unit": "PIXELS"}},
            {"property": "fontSize", "value": 14},
        ]
        op, remaining = _compose_font_identity_op(props, "_c")
        assert op != ""
        remaining_names = {p["property"] for p in remaining}
        assert remaining_names == {"letterSpacing", "fontSize"}, (
            f"font-identity composition must remove only the identity "
            f"members; got remaining = {remaining_names!r}"
        )

    def test_compose_family_only_uses_current_style(self):
        """When only fontFamily is overridden, the composed write must
        carry the current node's fontName.style (no setter for style
        means we want to keep the existing style)."""
        props = [{"property": "fontFamily", "value": "DM Sans"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert '"DM Sans"' in op, "family override must appear in the op"
        assert "__cur.style" in op, (
            "family-only override must default style to current node's "
            "fontName.style; otherwise we'd lose Bold/Medium variants"
        )

    def test_compose_style_only_uses_current_family(self):
        """Symmetric: style-only override keeps current family."""
        props = [{"property": "fontStyle", "value": "Bold"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert '"Bold"' in op
        assert "__cur.family" in op

    def test_compose_weight_only_normalizes_to_style(self):
        """fontWeight is numeric (700) → must convert to Figma style
        name ("Bold") for the fontName.style field."""
        props = [{"property": "fontWeight", "value": 700}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert '"Bold"' in op, (
            "fontWeight=700 must convert to style 'Bold' for the "
            "composed fontName write"
        )
        assert "__cur.family" in op

    def test_compose_loads_new_font_before_writing_fontname(self):
        """The composed write must call loadFontAsync on the NEW font
        BEFORE assigning fontName. Setting fontName to an unloaded
        font throws 'Cannot use unloaded font'."""
        props = [{"property": "fontFamily", "value": "Akkurat-Bold"}]
        op, _ = _compose_font_identity_op(props, "_c")
        # loadFontAsync must come before the fontName assignment.
        load_idx = op.find("loadFontAsync(")
        assign_idx = op.find(".fontName = ")
        assert 0 <= load_idx < assign_idx, (
            f"loadFontAsync must precede fontName assignment; "
            f"got load@{load_idx}, assign@{assign_idx} in:\n{op}"
        )

    def test_compose_handles_figma_mixed_font(self):
        """When the node has a mixed font run (figma.mixed sentinel),
        the composer must not blow up trying to read .fontName.family.
        Falls back to {Inter, Regular} as the structural anchor."""
        props = [{"property": "fontFamily", "value": "DM Sans"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert "figma.mixed" in op, (
            "compose op must check for figma.mixed (mixed-font runs) and "
            "fall back to a known font; otherwise reading .fontName.style "
            "on a mixed node throws"
        )

    def test_compose_gates_emission_on_text_type(self):
        """The composed write only makes sense on TEXT nodes — guard
        with `target.type === 'TEXT'` so non-text descendants are
        skipped silently (defensive, since composition is upstream)."""
        props = [{"property": "fontFamily", "value": "DM Sans"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert 'type === "TEXT"' in op


class TestNoRawFontFamilyEmission:
    """A. The renderer must NEVER emit `_c.fontFamily = ...` —
    Codex sharp-edge from F11 design review."""

    def test_override_tree_with_fontfamily_does_not_emit_raw_setter(self):
        """`_c.fontFamily = "DM Sans"` would throw 'object is not
        extensible' on a TEXT node. Composition removes the prop
        before emission; the raw setter must not appear anywhere."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "fontFamily", "value": "DM Sans"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "_c.fontFamily =" not in joined, (
            "raw fontFamily setter must not be emitted (TEXT nodes don't "
            "have one — throws 'object is not extensible')"
        )
        # And the composed fontName write must appear.
        assert "fontName = " in joined, (
            "composition produces a single fontName write for the family "
            "override; missing implies the composer didn't run"
        )

    def test_override_tree_with_fontweight_does_not_emit_raw_setter(self):
        """Same for fontWeight — TEXT nodes have no .fontWeight
        setter, the value must compose into fontName.style."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "fontWeight", "value": 700},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "_c.fontWeight =" not in joined
        assert "fontName = " in joined

    def test_override_tree_with_fontstyle_does_not_emit_raw_setter(self):
        """Same for fontStyle — even though the registry lists it as
        a text prop, the only Figma TEXT setter is .fontName."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "fontStyle", "value": "Italic"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "_c.fontStyle =" not in joined
        assert "fontName = " in joined

    def test_emit_override_op_skips_stray_font_identity_silently(self):
        """Defense in depth: if a font-identity prop somehow reaches
        `_emit_override_op` directly (composer bypass), it must
        silently return empty rather than emit a guaranteed-throw
        setter. Caller iterating remainders won't ever pass these
        through normally, but a future refactor might."""
        op = _emit_override_op(
            {"property": "fontFamily", "value": "DM Sans"},
            "_c", {}, "instance_var", [],
        )
        assert op == "", (
            "_emit_override_op must skip font-identity props (composition "
            "is the only correct path); raw emission would throw at runtime"
        )


class TestTextPropertyFontLoadGuard:
    """B. Text-category writes are wrapped in loadFontAsync(_t.fontName)."""

    def test_letter_spacing_write_loads_current_font(self):
        """letterSpacing is the canonical case — was the proximate
        cause of the Phase D probe's 'unloaded font Akkurat-Bold Bold'
        errors. Must wrap with loadFontAsync(_c.fontName)."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "letterSpacing",
                         "value": {"value": 0, "unit": "PIXELS"}},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "loadFontAsync(_c.fontName)" in joined, (
            "letterSpacing write on a TEXT node must preload _c.fontName "
            "first; otherwise Figma throws 'Cannot write to node with "
            "unloaded font' when the font wasn't in the preamble preload"
        )
        # And the actual write must come AFTER the load.
        load_idx = joined.find("loadFontAsync(_c.fontName)")
        write_idx = joined.find("_c.letterSpacing")
        assert 0 <= load_idx < write_idx

    def test_font_size_write_loads_current_font(self):
        """fontSize is also affected — same setter contract."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "fontSize", "value": 16},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "loadFontAsync(_c.fontName)" in joined

    def test_text_align_vertical_write_loads_current_font(self):
        """All text-category props need the guard, including the
        non-numeric ones like textAlignVertical."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "textAlignVertical", "value": "TOP"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "loadFontAsync(_c.fontName)" in joined

    def test_non_text_property_does_not_get_font_load_guard(self):
        """Non-text props (cornerRadius, fills, paddingTop, etc.) must
        NOT be wrapped — they don't need a font loaded and the wrap
        would add unnecessary cost + an unwanted TEXT-type gate."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";frame-1",
                    "properties": [
                        {"property": "cornerRadius", "value": 8},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "loadFontAsync" not in joined, (
            "non-text writes must not pay the font-load cost or be "
            "gated on type === 'TEXT'"
        )

    def test_guard_skips_figma_mixed_font(self):
        """If the TEXT node has a mixed-font run (`fontName ===
        figma.mixed`), loadFontAsync would reject the sentinel.
        Skip the load in that case — the write itself will then
        throw, but we can't preemptively load N fonts at compile time."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "letterSpacing",
                         "value": {"value": 0, "unit": "PIXELS"}},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "figma.mixed" in joined, (
            "guard must check `_c.fontName !== figma.mixed` before calling "
            "loadFontAsync; passing the mixed sentinel rejects the load"
        )

    def test_guard_includes_text_type_check(self):
        """The guard must check `_c.type === 'TEXT'` because the
        override target might be a non-TEXT node (defensive — the
        spec/registry pairing usually prevents this, but the runtime
        check is the safety net)."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "fontSize", "value": 16},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert 'type === "TEXT"' in joined


class TestF11CatchShapesAttributeFailures:
    """Codex review (F11 round 2): every text-write path must have a
    try/catch that pushes a structured `__errors` entry with enough
    context to attribute the failure. Without it, one bad text node
    throws a fatal exception that aborts subsequent override emission
    for the entire instance."""

    def test_compose_op_catches_load_failure(self):
        """Composed fontName write may throw if the new font is
        unavailable in this Figma session (paid commercial font, etc.).
        The catch must record family + style for diagnosis."""
        props = [{"property": "fontFamily", "value": "Akkurat-Bold"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert "try {" in op and "catch" in op, (
            "composed write must be try/catch wrapped — loadFontAsync can "
            "reject for unavailable fonts (paid/library imports)"
        )
        assert 'kind:"text_set_failed"' in op, (
            "catch must push a text_set_failed __errors entry"
        )
        # Family + style appear so attribution is possible.
        assert "family:" in op and "style:" in op

    def test_text_prop_op_catches_load_or_write_failure(self):
        """Codex sharp catch: even with loadFontAsync prefix, the
        load can REJECT (font unavailable), and then the next-line
        write throws. The block needs try/catch — the outer block
        only has try/finally, which doesn't catch."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "letterSpacing",
                         "value": {"value": 0, "unit": "PIXELS"}},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # The text-prop write block must be try/catch wrapped.
        # Ordering: outer findOne block has try/finally; the inner
        # per-prop block must additionally be try/catch around the
        # load+write pair.
        assert "text_set_failed" in joined, (
            "each text-prop write must push a text_set_failed __errors "
            "entry on failure (font unavailable, mixed-style write, etc.)"
        )
        # And the per-op catch shape must include the property name.
        assert 'property:"letterSpacing"' in joined, (
            "catch attribution must include the property name; otherwise "
            "you can't tell which write failed"
        )


class TestF11RegressionCharactersBranchUnchanged:
    """The pre-existing `characters` branch must keep its load
    semantics — F11.1 added the same try/catch wrap that F11 added
    to other text-prop writes, but the load+write pair is unchanged."""

    def test_characters_override_still_loads_current_font(self):
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "characters", "value": "Hello"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # The original `_c.characters = "..."` pattern after a
        # loadFontAsync(_c.fontName) call.
        assert "loadFontAsync(_c.fontName)" in joined
        assert '_c.characters = "Hello"' in joined


class TestF12EidAttributionInCatches:
    """F12 — Phase D visual diff exposed that F11.1's catch shapes
    push `text_set_failed` with `property` but no node identity.
    Looking at a 16-runtime-error walk for screen 44, several entries
    say `kind: text_set_failed, property: characters` with no eid /
    no node_id, making them unattributable.

    F12 adds `node_id` + `name` to the catch payloads so callers can
    map a "Rooms" instead of "Travel Request" symptom back to the
    offending DB override row by figma_node_id."""

    def test_characters_catch_includes_node_id(self):
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "characters", "value": "Hello"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "node_id:" in joined and "name:" in joined, (
            "F11.1 catch in characters branch must carry node_id + name "
            "for per-eid attribution; otherwise the runtime-error channel "
            "can't be cross-referenced to a specific override row"
        )

    def test_text_prop_catch_includes_node_id(self):
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "letterSpacing",
                         "value": {"value": 0, "unit": "PIXELS"}},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "node_id:" in joined and "name:" in joined

    def test_compose_op_catch_includes_node_id(self):
        props = [{"property": "fontFamily", "value": "Akkurat-Bold"}]
        op, _ = _compose_font_identity_op(props, "_c")
        assert "node_id:" in op and "name:" in op


class TestF111CharactersBranchCatch:
    """F11.1 — add the per-op try/catch around the characters
    branch's load+write pair. Without it, an unloadable font (paid
    commercial font like Akkurat-Bold the user hasn't licensed)
    rejects loadFontAsync, the write throws, and the surrounding
    findOne block's try/finally doesn't catch — kills Phase 1.

    Observed Phase D 2026-04-25 sweep on HGB: 17 of 44 screens
    aborted at the first instance whose master used Akkurat, so only
    1 of N IR elements rendered. Akkurat is genuinely unavailable
    via Plugin API (only Akkurat-Mono of 9777 fonts is loadable on
    this Figma session); the script needed to record-and-continue.
    """

    def test_characters_branch_wraps_load_and_write_in_try_catch(self):
        """The load+write pair must be try/catch wrapped so a font
        that can't be loaded (paid font, library-only) doesn't kill
        Phase 1. Mirrors the same shape applied to other text props
        in F11."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "characters", "value": "Reject"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # try/catch must wrap the load+write — finding the catch
        # near the loadFontAsync.
        assert "try {" in joined and "catch" in joined, (
            "characters branch must be try/catch wrapped — without it "
            "an unloadable font's loadFontAsync rejection aborts Phase 1"
        )
        assert "text_set_failed" in joined, (
            "catch must push a structured __errors entry"
        )
        assert 'property:"characters"' in joined, (
            "catch attribution must include the property name so "
            "operators can tell which write failed"
        )

    def test_characters_load_inside_inner_try(self):
        """The loadFontAsync MUST be inside the inner try/catch.
        If it's outside, the rejection still propagates. Codex review
        of F11 (round 2) flagged this exact pattern."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";text-1",
                    "properties": [
                        {"property": "characters", "value": "Hi"},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # Find the try { ... } catch ordering — load must be after
        # the try { and before the catch.
        try_idx = joined.find("try {")
        load_idx = joined.find("loadFontAsync")
        catch_idx = joined.find("catch")
        assert 0 <= try_idx < load_idx < catch_idx, (
            "loadFontAsync must be inside the try block (otherwise the "
            "rejection isn't caught); got "
            f"try@{try_idx}, load@{load_idx}, catch@{catch_idx}"
        )
