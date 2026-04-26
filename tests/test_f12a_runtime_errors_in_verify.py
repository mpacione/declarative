"""F12a — surface walk-side runtime errors in `dd verify` output.

Phase D 2026-04-25 visual-diff exposed a verifier-blindness class:
when the structural verifier reports `is_parity=True`, runtime errors
(text_set_failed, font_load_failed, component_missing) recorded by
the render script's per-op try/catch handlers are silently dropped
from the report. The structural verifier counts missing children;
runtime visual-fidelity failures (e.g. F11.1's catch-and-continue
on unloadable fonts) live on the walk side and never reach the
verifier output. Codex synthesis review caught the same gap
independently when reading the Phase D synthesis report.

F12a's contract: the verifier's --json payload AND its human-readable
output must include `runtime_error_count` + `runtime_error_kinds`
+ a verbatim `runtime_errors` list copied from the walk's `errors`.
The render-batch sweep's summary.json gains:

- `is_parity_true_clean` — subset of `is_parity_true` with 0 runtime errors
- `screens_with_runtime_errors`
- `total_runtime_errors`
- `runtime_error_kinds` (aggregated Counter)

Per-screen rows gain `runtime_error_count` + `runtime_error_kinds`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / "audit" / "20260425-1725-phaseD-fullsweep" / "audit-fresh.declarative.db"
WALK_PATH = (
    REPO
    / "audit"
    / "20260425-1725-phaseD-fullsweep"
    / "sections"
    / "07-roundtrip-render"
    / "sweep-out"
    / "walks"
    / "44.json"
)


def _has_audit_artefacts() -> bool:
    return DB_PATH.exists() and WALK_PATH.exists()


@pytest.mark.skipif(
    not _has_audit_artefacts(),
    reason="Phase D audit artefacts not present (CI / fresh checkout)",
)
class TestVerifyJsonSurfacesRuntimeErrors:
    """`dd verify ... --json` must include runtime-error fields."""

    def test_json_contains_runtime_error_count(self):
        result = subprocess.run(
            [
                ".venv/bin/python", "-m", "dd", "verify",
                "--db", str(DB_PATH),
                "--screen", "44",
                "--rendered-ref", str(WALK_PATH),
                "--json",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        # P1 (Phase E): is_parity is now strict (structural OK AND
        # runtime clean). Screen 44 has 16 runtime errors → strict
        # parity is False → exit 1. The JSON payload still goes to
        # stdout regardless of exit code.
        assert result.returncode == 1, f"stderr: {result.stderr}"
        payload = json.loads(result.stdout)
        assert "runtime_error_count" in payload, (
            "F12a contract (post-P1): --json output must include "
            "runtime_error_count so callers can distinguish "
            "structural-clean (is_structural_parity=True) from "
            "fully-clean (is_parity=True). Got keys: "
            f"{list(payload.keys())}"
        )
        # Screen 44 has 16 runtime errors per the walk.
        assert payload["runtime_error_count"] == 16

    def test_json_contains_runtime_error_kinds_breakdown(self):
        result = subprocess.run(
            [
                ".venv/bin/python", "-m", "dd", "verify",
                "--db", str(DB_PATH),
                "--screen", "44",
                "--rendered-ref", str(WALK_PATH),
                "--json",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        kinds = payload.get("runtime_error_kinds") or {}
        # Screen 44's runtime errors are 14 text_set_failed + 2 font_load_failed
        assert kinds.get("text_set_failed") == 14
        assert kinds.get("font_load_failed") == 2

    def test_json_contains_runtime_errors_verbatim(self):
        """Full walk `errors` list must be passed through so callers
        can attribute per-eid failures without re-reading the walk."""
        result = subprocess.run(
            [
                ".venv/bin/python", "-m", "dd", "verify",
                "--db", str(DB_PATH),
                "--screen", "44",
                "--rendered-ref", str(WALK_PATH),
                "--json",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        runtime_errors = payload.get("runtime_errors") or []
        assert len(runtime_errors) == 16
        # Verify entries carry the kind field.
        kinds_seen = {e.get("kind") for e in runtime_errors}
        assert kinds_seen == {"text_set_failed", "font_load_failed"}

    def test_strict_parity_requires_runtime_clean_p1_post(self):
        """P1 (Phase E Pattern 2 fix): `is_parity` is now strict —
        requires structural parity AND zero runtime errors. The
        permissive pre-P1 contract (`is_parity` ignored runtime
        errors) was the chronic verifier-blindness pattern Sonnet +
        Codex flagged in their Pattern 2 analysis. The strict
        contract is the principled one; the permissive shape lives
        on as `is_structural_parity` for callers that only want
        tree-shape signal.
        """
        result = subprocess.run(
            [
                ".venv/bin/python", "-m", "dd", "verify",
                "--db", str(DB_PATH),
                "--screen", "44",
                "--rendered-ref", str(WALK_PATH),
                "--json",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Screen 44 has 16 runtime errors, so strict is_parity is
        # False → exit 1. (Pre-P1: this exited 0 with is_parity=True
        # despite the 16 errors — the bug.)
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        # Strict parity: False, because runtime errors exist.
        assert payload["is_parity"] is False
        # Structural parity: True (tree shape matches IR).
        assert payload["is_structural_parity"] is True
        # parity_ratio remains structural-only — unaffected by runtime.
        assert payload["parity_ratio"] == 1.0
        # And runtime errors are now visible at top-level.
        assert payload["runtime_error_count"] == 16


class TestSweepSummarySurfacesRuntimeErrors:
    """The render-batch sweep's per-screen rows + summary.json must
    expose the runtime-error fields too."""

    def test_summarize_aggregates_runtime_errors_across_rows(self):
        """Post-P1: row fixtures must reflect the verifier's actual
        post-P1 output. `is_parity` is now strict (False if runtime
        errors > 0); `is_structural_parity` carries the tree-shape
        signal. The summary aggregates BOTH."""
        from render_batch.sweep import summarize

        rows = [
            {
                # Fully clean: structural OK, runtime clean → strict parity
                "screen_id": 1,
                "is_parity": True,
                "is_structural_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "runtime_error_count": 0,
                "runtime_error_kinds": {},
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
            {
                # Structural OK, but runtime errors → strict parity False
                "screen_id": 2,
                "is_parity": False,
                "is_structural_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "runtime_error_count": 16,
                "runtime_error_kinds": {
                    "text_set_failed": 14,
                    "font_load_failed": 2,
                },
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
            {
                # Structural OK, smaller runtime drift → strict parity False
                "screen_id": 3,
                "is_parity": False,
                "is_structural_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "runtime_error_count": 5,
                "runtime_error_kinds": {"text_set_failed": 5},
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
        ]
        summary = summarize(rows)

        assert summary["total"] == 3
        # Post-P1: is_parity_true counts strict parity only
        assert summary["is_parity_true"] == 1
        # New: is_structural_parity_true counts the tree-shape signal
        assert summary["is_structural_parity_true"] == 3
        # is_parity_true_clean is now an alias for is_parity_true
        assert summary["is_parity_true_clean"] == 1
        # Aggregated runtime stats unchanged
        assert summary["screens_with_runtime_errors"] == 2
        assert summary["total_runtime_errors"] == 21
        assert summary["runtime_error_kinds"] == {
            "text_set_failed": 19,
            "font_load_failed": 2,
        }

    def test_summarize_preserves_existing_keys_for_backward_compat(self):
        """Existing artefact readers / dashboards / scripts that key
        off the older summary fields must continue to work."""
        from render_batch.sweep import summarize

        rows = [
            {
                "screen_id": 1,
                "is_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
        ]
        summary = summarize(rows)
        for key in (
            "total",
            "is_parity_true",
            "is_parity_false",
            "generate_failed",
            "walk_failed",
            "retried",
            "retried_recovered",
            "error_kinds",
            "per_screen",
        ):
            assert key in summary, f"backward-compat: {key!r} must remain"

    def test_summarize_zero_runtime_errors_clean_state(self):
        """When no row has any runtime error, the F12a fields
        report clean values (0/0/{}) and is_parity_true_clean
        equals is_parity_true."""
        from render_batch.sweep import summarize

        rows = [
            {
                "screen_id": 1,
                "is_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "runtime_error_count": 0,
                "runtime_error_kinds": {},
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
            {
                "screen_id": 2,
                "is_parity": True,
                "error_kinds": [],
                "error_count": 0,
                "runtime_error_count": 0,
                "runtime_error_kinds": {},
                "generate_ok": True,
                "walk_ok": True,
                "verify_ok": True,
            },
        ]
        summary = summarize(rows)
        assert summary["is_parity_true_clean"] == 2
        assert summary["screens_with_runtime_errors"] == 0
        assert summary["total_runtime_errors"] == 0
        assert summary["runtime_error_kinds"] == {}
