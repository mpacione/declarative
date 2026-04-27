"""Backlog #4 — sweep retry skips real-bug DRIFT.

Phase: forensic-audit-2 architectural sprint, smaller cleanup.

Pre-fix: ``process_screen_with_retry`` retried ANY DRIFT screen
up to 2 times (3 attempts total) hoping the failure was a
transient bridge issue. Per
``feedback_sweep_transient_timeouts.md``, the bridge does
accumulate load mid-sweep and ``missing_component_node`` /
``component_missing`` errors do resolve on retry — that's the
real motivation for retry.

But after the verifier got a bunch of new comparators (P1,
A1.3, A5), DRIFT screens now include real-bug mismatches
(``fill_mismatch``, ``stroke_mismatch``, ``cornerradius_mismatch``,
``opacity_mismatch``, etc.) that don't resolve on retry — same
data, same comparison, same drift. The retry just wastes wall
time.

Symptom: post-A1.3 sweep took 8x longer (260s → 2060s) on the
same Nouns DB because retries fired on real-bug DRIFT.

Fix: classify the failure kinds in a row's ``error_kinds``
(verifier) and ``runtime_error_kinds`` (walker). If ALL kinds
are real-bug class (no transient class), skip retry.

Codex 5.5 framing: "Most recurring DRIFT is now caused by
verifier-side mismatches the audit surfaced; those don't
benefit from retry. Keep retry for the bridge-transient class
that originally motivated it."
"""

from __future__ import annotations

from render_batch.sweep import _is_likely_transient_failure


# ---------------------------------------------------------------------
# Real-bug class — should NOT retry
# ---------------------------------------------------------------------

class TestRealBugFailuresSkipRetry:
    """Verifier-side mismatches and similar deterministic failures
    should not trigger retry — same data, same diff, same
    failure on rerun."""

    def test_fill_mismatch_alone_is_not_transient(self):
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": ["fill_mismatch"],
            "runtime_error_kinds": {},
        }
        assert _is_likely_transient_failure(row) is False

    def test_stroke_mismatch_alone_is_not_transient(self):
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": ["stroke_mismatch"],
            "runtime_error_kinds": {},
        }
        assert _is_likely_transient_failure(row) is False

    def test_multiple_verifier_kinds_not_transient(self):
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": [
                "fill_mismatch",
                "cornerradius_mismatch",
                "opacity_mismatch",
            ],
            "runtime_error_kinds": {},
        }
        assert _is_likely_transient_failure(row) is False

    def test_all_a5_kinds_not_transient(self):
        """The A5 stroke-geometry comparators are deterministic
        verifier checks; not transient."""
        for kind in (
            "stroke_weight_mismatch",
            "stroke_align_mismatch",
            "dash_pattern_mismatch",
            "clips_content_mismatch",
        ):
            row = {
                "is_parity": False,
                "is_structural_parity": False,
                "error_kinds": [kind],
                "runtime_error_kinds": {},
            }
            assert _is_likely_transient_failure(row) is False, kind


# ---------------------------------------------------------------------
# Transient class — SHOULD retry
# ---------------------------------------------------------------------

class TestTransientFailuresStillRetry:
    """The original retry motivation: bridge accumulates load,
    getNodeByIdAsync silently returns null mid-sweep. These
    should still trigger retry."""

    def test_walk_failed_is_transient(self):
        """Outright walk failure (script timeout, bridge error) —
        the canonical transient case."""
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "walk_ok": False,
            "walk_failure_class": "walk_timed_out",
            "error_kinds": [],
            "runtime_error_kinds": {},
        }
        assert _is_likely_transient_failure(row) is True

    def test_missing_component_node_is_transient(self):
        """Per feedback_sweep_transient_timeouts.md: the prefetch-
        returned-null class. Resolves on retry."""
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": [],
            "runtime_error_kinds": {"missing_component_node": 5},
        }
        assert _is_likely_transient_failure(row) is True

    def test_component_missing_is_transient(self):
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": [],
            "runtime_error_kinds": {"component_missing": 3},
        }
        assert _is_likely_transient_failure(row) is True

    def test_create_instance_failed_is_transient(self):
        """createInstance failures often resolve on a fresh
        bridge attempt."""
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": [],
            "runtime_error_kinds": {"create_instance_failed": 1},
        }
        assert _is_likely_transient_failure(row) is True


# ---------------------------------------------------------------------
# Mixed — has at least one transient → SHOULD retry (be conservative)
# ---------------------------------------------------------------------

class TestMixedFailuresRetry:
    """When a row has both real-bug AND transient kinds, retry
    (conservative — the transient might be the root cause and
    fix the verifier mismatches too)."""

    def test_fill_mismatch_plus_missing_component_retries(self):
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": ["fill_mismatch"],
            "runtime_error_kinds": {"missing_component_node": 1},
        }
        assert _is_likely_transient_failure(row) is True


# ---------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------

class TestEdgeCases:
    def test_clean_pass_short_circuit_in_caller(self):
        """is_parity=True → caller short-circuits BEFORE calling
        the helper. The helper's behavior on is_parity=True rows
        is therefore irrelevant. This test documents the contract:
        the caller's responsibility is to skip the helper on
        success rows; the helper itself defaults to 'retry' on
        empty-error rows because that's the right call for
        is_parity=False (unknown cause).
        """
        row = {
            "is_parity": True,
            "is_structural_parity": True,
            "error_kinds": [],
            "runtime_error_kinds": {},
        }
        # The helper returns True (retry) on empty-error rows by
        # design — that case shouldn't be reached for
        # is_parity=True because the caller short-circuits earlier.
        # We assert the caller-side behavior in
        # process_screen_with_retry returning early on
        # row.get("is_parity") is True.
        assert _is_likely_transient_failure(row) is True

    def test_empty_kinds_default_treats_as_transient(self):
        """Defensive: when error_kinds is empty AND
        runtime_error_kinds is empty but is_parity=False, the
        cause is unknown. Conservative default: retry once."""
        row = {
            "is_parity": False,
            "is_structural_parity": False,
            "error_kinds": [],
            "runtime_error_kinds": {},
        }
        # Empty error info on a DRIFT row is suspicious; safer to
        # retry than to assume real bug.
        assert _is_likely_transient_failure(row) is True
