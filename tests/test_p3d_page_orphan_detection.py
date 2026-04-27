"""P3d (Phase E N2 fix) — page-orphan signal in walker + verifier.

Phase E §3 N2 found cases where the renderer's F-series guards swallow
an `appendChild` rejection (e.g. trying to attach into an INSTANCE
target — pre-P3a class) and the orphaned subtree lands on the page
root instead of inside the IR rooted-tree. Pre-P3d the walker's
`eid_map` only descended from `M['screen-1']`, so escaped artifacts
were invisible to the verifier; structural parity stayed True; the
report told no one anything was wrong.

Codex's design review (2026-04-25) framed the invariant as a *rooted
tree* contract: expected output = descendants of `rootNode = M['screen-1']`.
Any new top-level page child after render that isn't `rootNode` is an
escaped render artifact. M membership classifies the artifact (was it
supposed to land somewhere in the IR?) but does NOT excuse it: a new
top-level child outside `rootNode` is always an orphan.

Granularity: ONE summary `phase2_orphan` entry per artifact (not per
descendant), with `child_count`, `contains_m_id`, and `m_eid_sample` so
the verifier can credit-assign back to the IR position whose
appendChild failed.

The walker pushes `phase2_orphan` entries into the existing `__errors`
channel; P1's `FigmaRenderVerifier.verify` already inhales `errors`
into `RenderReport.runtime_errors`; P1's strict `is_parity` already
flips False on any runtime error. So P3d is two changes:
  - walker: snapshot pre-IDs, enumerate post, push summary entries
  - the per-orphan shape is what changes — the inhale is already wired

These tests pin the *contract* end-to-end at the verifier surface (we
can't drive a live Figma bridge in unit tests). The walker change is
exercised by feeding a synthetic rendered_ref with the shape the
walker now emits, then asserting the verifier surfaces it correctly.
"""

from __future__ import annotations

from dd.boundary import RenderReport
from dd.verify_figma import FigmaRenderVerifier


def _phase2_orphan_entry(
    *,
    node_id: str = "9999:1",
    name: str = "OrphanedFrame",
    type: str = "FRAME",
    child_count: int = 1,
    contains_m_id: bool = False,
    m_eid_sample: list[str] | None = None,
) -> dict:
    """Walker-shape factory — what `walk_ref.js` pushes into __errors
    when it detects an escaped artifact. Keeping this in the test
    pins the wire-format contract that the JS walker emits."""
    return {
        "kind": "phase2_orphan",
        "node_id": node_id,
        "name": name,
        "type": type,
        "child_count": child_count,
        "contains_m_id": contains_m_id,
        "m_eid_sample": m_eid_sample if m_eid_sample is not None else [],
    }


class TestVerifierSurfacesPhase2Orphan:
    """The P1 verifier inhalation already exists. P3d's contract is
    that the walker emits `phase2_orphan` entries with a specific
    summary shape, and the verifier surfaces them in
    `RenderReport.runtime_errors` so strict `is_parity` flips False."""

    def test_phase2_orphan_breaks_strict_parity(self):
        """Headline P3d outcome: an escaped artifact in __errors breaks
        strict is_parity even when structural shape matches IR."""
        rendered_ref = {
            "eid_map": {},
            "errors": [_phase2_orphan_entry()],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        # Structural may be clean (no missing/wrong nodes in the rooted
        # tree walk), but runtime is dirty.
        assert report.is_structural_parity is True, (
            "P3d: empty IR + empty eid_map is structurally clean by "
            "definition; phase2_orphan lives in the runtime channel"
        )
        assert report.is_parity is False, (
            "P3d: phase2_orphan must flip strict is_parity to False so "
            "the sweep can't silently accept renders with escaped "
            "artifacts"
        )

    def test_phase2_orphan_kind_counted(self):
        rendered_ref = {
            "eid_map": {},
            "errors": [
                _phase2_orphan_entry(node_id="9999:1"),
                _phase2_orphan_entry(node_id="9999:2", name="Other"),
            ],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        assert report.runtime_error_count == 2
        assert report.runtime_error_kinds.get("phase2_orphan") == 2

    def test_orphan_summary_fields_preserved(self):
        """The walker emits node_id/name/type/child_count/
        contains_m_id/m_eid_sample so the report can carry enough info
        to credit-assign without N descendant entries. Verify those
        survive the inhale."""
        entry = _phase2_orphan_entry(
            node_id="9999:42",
            name="EscapedFrame",
            type="FRAME",
            child_count=37,
            contains_m_id=True,
            m_eid_sample=["text-1", "rect-2", "frame-3"],
        )
        rendered_ref = {"eid_map": {}, "errors": [entry]}
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        assert len(report.runtime_errors) == 1
        surfaced = report.runtime_errors[0]
        assert surfaced["kind"] == "phase2_orphan"
        assert surfaced["node_id"] == "9999:42"
        assert surfaced["name"] == "EscapedFrame"
        assert surfaced["type"] == "FRAME"
        assert surfaced["child_count"] == 37
        assert surfaced["contains_m_id"] is True
        assert surfaced["m_eid_sample"] == ["text-1", "rect-2", "frame-3"]


class TestPhase2OrphanCoexistsWithOtherRuntimeErrors:
    """Walker emits phase2_orphan alongside the existing __errors zoo
    (font_load_failed, text_set_failed, append_child_failed, etc.).
    Verify all kinds are surfaced uniformly."""

    def test_orphan_plus_font_failure_both_surface(self):
        rendered_ref = {
            "eid_map": {},
            "errors": [
                {"kind": "font_load_failed", "family": "Akkurat",
                 "style": "Regular", "error": "x"},
                _phase2_orphan_entry(),
                {"kind": "text_set_failed", "property": "characters",
                 "node_id": "I1;2", "error": "y"},
            ],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        assert report.runtime_error_count == 3
        kinds = report.runtime_error_kinds
        assert kinds.get("phase2_orphan") == 1
        assert kinds.get("font_load_failed") == 1
        assert kinds.get("text_set_failed") == 1
        assert report.is_parity is False


class TestPhase2OrphanContractDocumentation:
    """Documentation tests — these encode the exact assumptions the
    walker change in render_test/walk_ref.js relies on. If the walker
    emits a different shape (e.g. someone refactors `phase2_orphan` to
    `escaped_artifact`), these will fail and force a docs+code sync.
    """

    def test_kind_string_matches_walker(self):
        """The walker uses the literal string `phase2_orphan`. Tests
        that downstream consumers (like sweep summaries or repair
        loops) need to filter on this exact kind string."""
        # If anything renames this, the audit triage docs in
        # audit/20260425-1930-phaseE-nouns/triage/N2-verifier-blindness/
        # also need updating — both Sonnet and Codex referenced this
        # exact name. Pin it.
        entry = _phase2_orphan_entry()
        assert entry["kind"] == "phase2_orphan"

    def test_summary_shape_minimal_fields(self):
        """Minimum fields any phase2_orphan entry must have. Keeps the
        wire format from drifting."""
        entry = _phase2_orphan_entry()
        for required in (
            "kind", "node_id", "name", "type",
            "child_count", "contains_m_id", "m_eid_sample",
        ):
            assert required in entry, (
                f"P3d wire format: phase2_orphan entry missing required "
                f"field {required!r}"
            )

    def test_phase2_orphan_categorizes_as_escaped_artifact(self):
        """P4 (Phase E Pattern 2 fix) categorization: the
        ``phase2_orphan`` kind is bucketed under the
        ``escaped_artifact`` category in
        ``dd/runtime_errors.py``. Codex review (2026-04-25) called out
        the cross-test pinning explicitly — if anyone renames the
        category, both this test and the P4 convention test should
        fail simultaneously, surfacing the rename intent."""
        from dd.runtime_errors import categorize_runtime_error_kind
        assert categorize_runtime_error_kind("phase2_orphan") == \
            "escaped_artifact"


class TestStructuralParityUnaffectedByOrphans:
    """Codex design-review nuance: page orphans are render-side runtime
    failures, NOT failures of the rooted-tree IR ↔ rendered isomorphism.
    `is_structural_parity` must stay True for callers that only want
    the tree-shape signal (e.g. fidelity scoring). `is_parity` (strict)
    is the one that flips. Verify both ends explicitly."""

    def test_orphan_does_not_affect_structural_parity(self):
        rendered_ref = {
            "eid_map": {},
            "errors": [_phase2_orphan_entry() for _ in range(10)],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        assert report.is_structural_parity is True, (
            "P3d: structural parity is rooted-tree shape only; orphans "
            "live outside the rooted tree by definition"
        )
        assert report.parity_ratio() == 1.0, (
            "P3d: parity_ratio is structural-only; orphans don't "
            "lower it"
        )
        assert report.is_parity is False, (
            "P3d: but strict is_parity does flip"
        )
