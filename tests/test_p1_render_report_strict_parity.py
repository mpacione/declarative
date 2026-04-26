"""P1 (Phase E Pattern 2 fix) — RenderReport strict-parity contract.

Phase D Codex synthesis caught one verifier-blindness instance: the
verifier ignored walk runtime errors in its parity verdict. F12a
surfaced `runtime_error_count` in the CLI but `is_parity` never
consumed it. Phase E (N2 + Pattern 2 deep dive) confirmed this is the
chronic pattern: every new renderer guard converts a fatal throw into
a recoverable `__errors` entry the verifier doesn't see.

P1 closes the loop by inhaling runtime errors INTO `RenderReport` and
redefining `is_parity` to require both structural AND runtime
cleanliness. The pre-fix definition lives on as `is_structural_parity`
for callers that only want tree-shape signal (e.g. fidelity scoring).

Codex design review (2026-04-25): Shape B chosen over A and C —
default-empty `runtime_errors: list[dict]` field preserves existing
direct constructors; `is_structural_parity` keeps the old definition
addressable; `is_parity` becomes the strict one; `parity_ratio` stays
structural-only.
"""

from __future__ import annotations

from dd.boundary import RenderReport, StructuredError, KIND_MISSING_CHILD


def _empty_report(**kwargs) -> RenderReport:
    """Constructor helper. Defaults make a clean structural-parity
    report; pass overrides to test variations."""
    defaults = {
        "backend": "figma",
        "ir_node_count": 5,
        "rendered_node_count": 5,
        "errors": [],
    }
    defaults.update(kwargs)
    return RenderReport(**defaults)


class TestStructuralParityPreservesOldShape:
    def test_empty_errors_and_matched_counts_is_structural_parity(self):
        r = _empty_report()
        assert r.is_structural_parity is True
        assert r.parity_ratio() == 1.0

    def test_structural_drift_breaks_structural_parity(self):
        r = _empty_report(
            errors=[StructuredError(kind=KIND_MISSING_CHILD, id="e1")],
        )
        assert r.is_structural_parity is False

    def test_count_mismatch_breaks_structural_parity(self):
        r = _empty_report(rendered_node_count=4)
        assert r.is_structural_parity is False


class TestStrictParityRequiresRuntimeClean:
    """P1 contract: `is_parity` requires structural + runtime clean."""

    def test_clean_report_is_strict_parity(self):
        r = _empty_report()
        assert r.is_parity is True
        assert r.is_structural_parity is True

    def test_runtime_error_breaks_strict_parity(self):
        """The headline P1 contract: a structurally-clean report with
        ANY runtime error is no longer is_parity=True. Pre-P1 this
        was True — the bug Sonnet + Codex flagged."""
        r = _empty_report(
            runtime_errors=[
                {"kind": "text_set_failed", "property": "characters",
                 "error": "Cannot use unloaded font"},
            ],
        )
        assert r.is_structural_parity is True, (
            "structural shape unaffected by runtime errors"
        )
        assert r.is_parity is False, (
            "P1: strict parity requires runtime_errors to be empty too"
        )

    def test_runtime_error_count_property(self):
        r = _empty_report(
            runtime_errors=[
                {"kind": "text_set_failed", "error": "x"},
                {"kind": "font_load_failed", "family": "Akkurat",
                 "style": "Regular", "error": "x"},
                {"kind": "font_load_failed", "family": "Akkurat-Bold",
                 "style": "Bold", "error": "x"},
            ],
        )
        assert r.runtime_error_count == 3

    def test_runtime_error_kinds_counter(self):
        r = _empty_report(
            runtime_errors=[
                {"kind": "text_set_failed", "error": "x"},
                {"kind": "text_set_failed", "error": "y"},
                {"kind": "font_load_failed", "family": "F", "style": "S"},
            ],
        )
        assert r.runtime_error_kinds == {
            "text_set_failed": 2,
            "font_load_failed": 1,
        }

    def test_non_dict_runtime_entries_skipped_in_kinds(self):
        """Defensive: runtime_errors is typed list[dict], but if a
        malformed walk slipped a non-dict in, the kinds counter
        shouldn't crash — it should silently skip."""
        # Bypass the dataclass type check by constructing with
        # mixed list — this exercises the .get('kind') fallback.
        r = _empty_report(
            runtime_errors=[
                {"kind": "text_set_failed", "error": "x"},
                "not a dict",  # type: ignore
                {"kind": "font_load_failed", "family": "F", "style": "S"},
            ],
        )
        # Both real dict-shaped entries should be counted; the str
        # entry is skipped silently.
        assert r.runtime_error_kinds == {
            "text_set_failed": 1,
            "font_load_failed": 1,
        }


class TestParityRatioStaysStructural:
    """Codex design-review catch: `parity_ratio()` is STRUCTURAL only.
    A report can have `parity_ratio=1.0` and `is_parity=False` if the
    rendered tree shape matches IR exactly but runtime errors were
    recorded. Don't conflate the two."""

    def test_clean_structural_ratio_one_with_runtime_errors(self):
        r = _empty_report(
            runtime_errors=[
                {"kind": "text_set_failed", "error": "x"},
            ] * 50,  # lots of runtime errors
        )
        assert r.parity_ratio() == 1.0, (
            "ratio is structural-only; runtime errors don't affect it"
        )
        assert r.is_parity is False, "but strict parity is False"

    def test_structural_drift_lowers_ratio(self):
        r = _empty_report(
            errors=[
                StructuredError(kind=KIND_MISSING_CHILD, id=f"e{i}")
                for i in range(2)
            ],
        )
        # 2 structural errors out of 5 IR nodes → 3/5 matched
        assert r.parity_ratio() == 0.6


class TestBackwardCompatConstruction:
    """Existing call sites that construct RenderReport without the
    `runtime_errors` arg must keep working. Default-empty preserves
    the pre-P1 behavior at construction time."""

    def test_default_runtime_errors_is_empty(self):
        r = _empty_report()
        assert r.runtime_errors == []
        assert r.runtime_error_count == 0
        assert r.runtime_error_kinds == {}

    def test_default_constructor_yields_strict_parity(self):
        """Old call sites that didn't pass runtime_errors still
        produce is_parity=True when structural is clean — they're
        not silently flipped to False."""
        r = _empty_report()
        assert r.is_parity is True


class TestVerifierInhalesRenderedRefErrors:
    """`FigmaRenderVerifier.verify` must read `rendered_ref["errors"]`
    and populate `RenderReport.runtime_errors` from it."""

    def test_verify_inhales_runtime_errors_from_walk(self):
        from dd.verify_figma import FigmaRenderVerifier
        ir = {"elements": {}}
        rendered_ref = {
            "eid_map": {},
            "errors": [
                {"kind": "font_load_failed", "family": "Akkurat",
                 "style": "Regular", "error": "could not load"},
                {"kind": "text_set_failed", "property": "characters",
                 "node_id": "I1;2", "error": "Cannot use unloaded"},
            ],
        }
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        assert report.runtime_error_count == 2
        assert report.runtime_error_kinds == {
            "font_load_failed": 1,
            "text_set_failed": 1,
        }
        # And strict parity is False (zero IR nodes structurally
        # match, but runtime errors break strict parity regardless).
        assert report.is_parity is False

    def test_verify_handles_missing_errors_field(self):
        """Walks from older versions or generated-then-aborted runs
        may not have an `errors` field. Verifier should default to
        empty runtime_errors, not crash."""
        from dd.verify_figma import FigmaRenderVerifier
        ir = {"elements": {}}
        rendered_ref = {"eid_map": {}}  # no `errors` key
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        assert report.runtime_error_count == 0

    def test_verify_runtime_errors_deep_copied(self):
        """Codex design-review note: runtime_errors must be deep-copied
        so the frozen RenderReport isn't backed by mutable walk
        payload state. Mutating the original walk after verify()
        must not leak into the report."""
        from dd.verify_figma import FigmaRenderVerifier
        original = {"kind": "text_set_failed", "property": "characters"}
        rendered_ref = {
            "eid_map": {},
            "errors": [original],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        # Mutate the original
        original["property"] = "MUTATED"
        # Report's copy is unchanged
        assert report.runtime_errors[0]["property"] == "characters"
