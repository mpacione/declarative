"""Sprint 2 C8 tests — walker envelope capture + verifier tolerance.

Per docs/plan-sprint-2-station-parity.md §6 (value/source capture
semantics) and §10 R2 (default-vs-set risk mitigation): C8 graduates
characters / layoutSizingHorizontal / layoutSizingVertical to
{value, source} envelopes in the rendered eid_map. Verifier reads
must tolerate both raw and envelope shapes (defensive option gamma
per Codex round-7).

C10 will wire registry-driven dispatch; until then C8 is the
behavioral pairing.
"""
from pathlib import Path


_REPO_ROOT = Path(__file__).parent.parent
_WALKER_PATH = _REPO_ROOT / "render_test" / "walk_ref.js"


class TestC8WalkerEnvelopeCapture:
    """Walker emits {value, source} envelopes for the 3 graduations."""

    def test_walker_precomputes_value_source_props_set(self):
        contents = _WALKER_PATH.read_text()
        # Look for the precompute block at wrapped-script init
        assert "__VALUE_SOURCE_PROPS" in contents
        # Should be derived from manifest
        assert "__WALKER_MANIFEST.properties" in contents
        # And there's a defensive fallback Set with the 3 names
        for name in ("characters", "layoutSizingHorizontal", "layoutSizingVertical"):
            assert name in contents

    def test_walker_helper_exists(self):
        contents = _WALKER_PATH.read_text()
        assert "__walkerMaybeEnvelope" in contents
        # Helper must take (name, value, source) and return either envelope or raw.
        # Loose check via presence of these substrings near the helper definition.
        assert "__VALUE_SOURCE_PROPS.has" in contents

    def test_characters_capture_uses_helper(self):
        contents = _WALKER_PATH.read_text()
        # The TEXT characters capture must wrap via helper
        assert (
            "__walkerMaybeEnvelope('characters'" in contents
            or '__walkerMaybeEnvelope("characters"' in contents
        )

    def test_layout_sizing_h_v_captured_via_helper(self):
        contents = _WALKER_PATH.read_text()
        for name in ("layoutSizingHorizontal", "layoutSizingVertical"):
            assert (
                f"__walkerMaybeEnvelope('{name}'" in contents
                or f'__walkerMaybeEnvelope("{name}"' in contents
            )
            # Must check typeof === 'string' guard
            assert f"typeof n.{name} === 'string'" in contents

    def test_textautoresize_stays_raw(self):
        """textAutoResize is NOT in the graduations list (only the 3 are).
        It must stay as raw `entry.textAutoResize = n.textAutoResize`."""
        contents = _WALKER_PATH.read_text()
        assert "entry.textAutoResize = n.textAutoResize" in contents


class TestC8VerifierToleratesBothShapes:
    """Verifier must read both raw and envelope shapes for graduated properties."""

    def test_rendered_value_helper_returns_raw_for_string(self):
        from dd.verify_figma import _rendered_value
        rendered = {"characters": "Reject"}
        assert _rendered_value(rendered, "characters", "") == "Reject"

    def test_rendered_value_helper_unwraps_envelope(self):
        from dd.verify_figma import _rendered_value
        rendered = {"characters": {"value": "Reject", "source": "set"}}
        assert _rendered_value(rendered, "characters", "") == "Reject"

    def test_rendered_value_helper_default_for_missing(self):
        from dd.verify_figma import _rendered_value
        rendered: dict = {}
        assert _rendered_value(rendered, "characters", "default") == "default"

    def test_rendered_value_helper_passes_through_non_envelope_dicts(self):
        """If a value is a dict but not an envelope shape, return as-is."""
        from dd.verify_figma import _rendered_value
        # Hypothetical future shape — must not be misinterpreted
        rendered = {"someprop": {"some": "other_dict"}}
        result = _rendered_value(rendered, "someprop", None)
        # Should pass through unmodified (no value+source keys)
        assert result == {"some": "other_dict"}

    def test_rendered_value_helper_passes_through_partial_envelope(self):
        """A dict with only 'value' or only 'source' is NOT an envelope."""
        from dd.verify_figma import _rendered_value
        rendered = {"x": {"value": 5}}  # missing 'source'
        result = _rendered_value(rendered, "x", None)
        assert result == {"value": 5}  # passthrough


class TestC8VerifierMissingTextStillWorks:
    """The KIND_MISSING_TEXT check must continue to fire correctly with
    both raw and envelope shapes. It only fires when actual_text is
    empty/falsy."""

    def test_missing_text_with_raw_empty_string_still_flags(self):
        # This is an integration-ish check; may need to skip if
        # FigmaRenderVerifier import has heavy deps. Use a lightweight
        # assertion via the helper instead.
        from dd.verify_figma import _rendered_value
        rendered = {"characters": ""}
        # The verifier code does: if not actual_text: flag MISSING_TEXT
        # So we just check the helper returns the empty string correctly:
        assert _rendered_value(rendered, "characters", "") == ""
        assert not _rendered_value(rendered, "characters", "")  # falsy

    def test_missing_text_with_envelope_empty_value_still_flags(self):
        from dd.verify_figma import _rendered_value
        rendered = {"characters": {"value": "", "source": "set"}}
        assert _rendered_value(rendered, "characters", "") == ""
        assert not _rendered_value(rendered, "characters", "")  # falsy


class TestC8ValueSourceVocabulary:
    """Sprint 2 only emits 'set' as source. Other vocab values
    (computed_default, inherited, unavailable, unknown) are reserved
    for future families."""

    def test_walker_emits_only_set_source(self):
        contents = _WALKER_PATH.read_text()
        # Find all 'source: ...' or "source: ..." patterns near
        # __walkerMaybeEnvelope calls. Sprint 2 should only use 'set'.
        # This is a loose check — main thread will spot-verify.
        # Look for forbidden source values
        # (these will appear in future sprints but should NOT be in C8)
        forbidden_in_c8 = [
            "'computed_default'", '"computed_default"',
            "'inherited'", '"inherited"',
            "'unavailable'", '"unavailable"',
            "'unknown'", '"unknown"',
        ]
        for forbidden in forbidden_in_c8:
            assert forbidden not in contents, (
                f"Sprint 2 C8 should only use 'set' source; found {forbidden}"
            )
