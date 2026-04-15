"""Boundary contract tests — ADR-006.

Every external-system boundary (ingest and freshness-probe) produces the same
shape of output:

  - Extracted / valid data for the parts that succeeded
  - A structured error entry for each part that failed
  - An honest summary whose counts agree with the error list

These tests document the contract by exercising the Figma instantiation as
the first concrete backend. Future backends (Storybook, SwiftUI previews,
Flutter widget trees) must satisfy the same tests, parameterized.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixtures: fake Figma /v1/files/{key}/nodes responses
# ---------------------------------------------------------------------------


def _fake_node_doc(node_id: str, name: str = "Frame") -> dict[str, Any]:
    """Shape matches what Figma's REST API returns under .nodes[id].document."""
    return {
        "id": node_id,
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 428, "height": 926},
        "fills": [],
        "strokes": [],
        "effects": [],
        "children": [],
    }


def make_fake_api(
    *,
    valid: dict[str, dict] | None = None,
    null_ids: set[str] | None = None,
    raise_for_ids: set[str] | None = None,
    raise_exc: Exception | None = None,
) -> Callable[[str, str, list[str]], dict]:
    """Build a stand-in for figma_api.get_screen_nodes.

    - valid: id -> document dict (or use _fake_node_doc default)
    - null_ids: ids that the real API would return with value None
    - raise_for_ids: ids that trigger a raised exception (e.g. network error)
    - raise_exc: the exception to raise if any requested id is in raise_for_ids
    """
    valid = valid or {}
    null_ids = null_ids or set()
    raise_for_ids = raise_for_ids or set()

    def fake(file_key: str, token: str, ids: list[str]) -> dict:
        if raise_for_ids & set(ids):
            raise (raise_exc or RuntimeError("simulated network error"))
        nodes: dict[str, Any] = {}
        for nid in ids:
            if nid in null_ids:
                nodes[nid] = None
            elif nid in valid:
                nodes[nid] = {"document": valid[nid]}
            else:
                nodes[nid] = {"document": _fake_node_doc(nid)}
        return {"nodes": nodes}

    return fake


# ---------------------------------------------------------------------------
# Ingest contract — exercised through FigmaIngestAdapter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIngestAdapterContract:
    """The ingest-side of ADR-006: null-safe boundary with honest summary."""

    def test_all_valid_ids_produce_extracted_list_and_no_errors(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test",
            token="tok",
            api_client=make_fake_api(),
        )

        result = adapter.extract_screens(["1:1", "2:2", "3:3"])

        assert len(result.extracted) == 3
        assert result.errors == []
        assert result.summary.requested == 3
        assert result.summary.succeeded == 3
        assert result.summary.failed == 0

    def test_null_response_produces_structured_error_not_crash(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test",
            token="tok",
            api_client=make_fake_api(null_ids={"2:2"}),
        )

        result = adapter.extract_screens(["1:1", "2:2", "3:3"])

        assert len(result.extracted) == 2
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err.kind == "node_not_found"
        assert err.id == "2:2"

    def test_summary_counts_match_error_list_length(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test",
            token="tok",
            api_client=make_fake_api(null_ids={"2:2", "4:4"}),
        )

        result = adapter.extract_screens(["1:1", "2:2", "3:3", "4:4"])

        assert result.summary.requested == 4
        assert result.summary.succeeded == 2
        assert result.summary.failed == len(result.errors) == 2
        assert result.summary.requested == result.summary.succeeded + result.summary.failed

    def test_network_error_on_batch_produces_error_per_requested_id(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test",
            token="tok",
            api_client=make_fake_api(
                raise_for_ids={"2:2"},
                raise_exc=ConnectionError("timeout"),
            ),
        )

        result = adapter.extract_screens(["1:1", "2:2"])

        assert result.extracted == []
        assert len(result.errors) == 2
        assert {e.kind for e in result.errors} == {"api_error"}
        assert {e.id for e in result.errors} == {"1:1", "2:2"}
        assert all("timeout" in (e.error or "") for e in result.errors)

    def test_backend_identifier_is_exposed(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test", token="tok", api_client=make_fake_api()
        )
        assert adapter.backend == "figma"


# ---------------------------------------------------------------------------
# Freshness-probe contract — exercised through FigmaResourceProbe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResourceProbeContract:
    """The catalog-side of ADR-006: classify ids as valid/missing/unknown."""

    def test_all_ids_resolve_reports_fresh(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test",
            token="tok",
            api_client=make_fake_api(),
        )

        report = probe.probe(["1:1", "2:2"])

        assert report.is_fresh
        assert report.valid_ids == frozenset({"1:1", "2:2"})
        assert report.missing_ids == frozenset()
        assert report.unknown_ids == frozenset()
        assert report.errors == []
        assert report.stale_ratio() == 0.0

    def test_missing_ids_are_classified_separately_from_unknown(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test",
            token="tok",
            api_client=make_fake_api(null_ids={"2:2"}),
        )

        report = probe.probe(["1:1", "2:2", "3:3"])

        assert not report.is_fresh
        assert report.valid_ids == frozenset({"1:1", "3:3"})
        assert report.missing_ids == frozenset({"2:2"})
        assert report.unknown_ids == frozenset()
        assert report.stale_ratio() == pytest.approx(1 / 3)

    def test_network_error_classifies_ids_as_unknown_not_missing(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test",
            token="tok",
            api_client=make_fake_api(
                raise_for_ids={"2:2"},
                raise_exc=ConnectionError("timeout"),
            ),
        )

        report = probe.probe(["1:1", "2:2"])

        assert report.unknown_ids == frozenset({"1:1", "2:2"})
        assert report.missing_ids == frozenset()
        assert report.valid_ids == frozenset()
        assert len(report.errors) >= 1
        assert any(e.kind == "api_error" for e in report.errors)

    def test_freshness_counts_agree(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test",
            token="tok",
            api_client=make_fake_api(null_ids={"2:2"}),
        )

        report = probe.probe(["1:1", "2:2", "3:3", "4:4"])

        assert report.checked == 4
        assert (
            len(report.valid_ids) + len(report.missing_ids) + len(report.unknown_ids)
            == report.checked
        )

    def test_backend_identifier_is_exposed(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test", token="tok", api_client=make_fake_api()
        )
        assert probe.backend == "figma"


# ---------------------------------------------------------------------------
# Shared invariant — structured error shape is uniform
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStructuredErrorKindVocabulary:
    """ADR-007 Position 1: codegen degradation uses a stable shared `kind`
    vocabulary so that downstream consumers (harness, CI, training loop)
    can switch on well-known tokens instead of free-text error messages.
    """

    def test_kind_constants_exported_from_boundary(self):
        from dd import boundary
        # Ingest-side kinds (pre-existing, ADR-006)
        assert boundary.KIND_NODE_NOT_FOUND == "node_not_found"
        assert boundary.KIND_API_ERROR == "api_error"
        assert boundary.KIND_MALFORMED_RESPONSE == "malformed_response"
        # Codegen-degradation kinds (new, ADR-007 Position 1)
        assert boundary.KIND_DEGRADED_TO_MODE2 == "degraded_to_mode2"
        assert boundary.KIND_DEGRADED_TO_LITERAL == "degraded_to_literal"
        assert boundary.KIND_DEGRADED_TO_PLACEHOLDER == "degraded_to_placeholder"
        assert boundary.KIND_CAPABILITY_GATED == "capability_gated"
        assert boundary.KIND_CKR_UNBUILT == "ckr_unbuilt"

    def test_kind_constants_are_strings(self):
        from dd import boundary
        for name in dir(boundary):
            if name.startswith("KIND_"):
                assert isinstance(getattr(boundary, name), str)


@pytest.mark.unit
class TestRenderReportContract:
    """ADR-007 Position 3: post-render verification. The RenderReport
    mirrors IngestResult / FreshnessReport in shape — invariants
    enforced at construction, uniform StructuredError entries, per-node
    attribution via eid. Round-trip success is redefined to require
    `is_parity == True`, not just `__ok:true`.
    """

    def test_is_parity_true_for_zero_errors_and_matching_counts(self):
        from dd.boundary import RenderReport
        report = RenderReport(
            backend="figma",
            ir_node_count=10,
            rendered_node_count=10,
            errors=[],
        )
        assert report.is_parity is True
        assert report.parity_ratio() == 1.0

    def test_is_parity_false_when_errors_present(self):
        from dd.boundary import RenderReport, StructuredError, KIND_TYPE_SUBSTITUTION
        report = RenderReport(
            backend="figma",
            ir_node_count=10,
            rendered_node_count=10,
            errors=[StructuredError(
                kind=KIND_TYPE_SUBSTITUTION, id="button-1",
                error="expected INSTANCE, got FRAME",
            )],
        )
        assert report.is_parity is False
        assert report.parity_ratio() == 0.9  # (10 - 1) / 10

    def test_is_parity_false_when_counts_mismatch(self):
        from dd.boundary import RenderReport
        report = RenderReport(
            backend="figma",
            ir_node_count=10,
            rendered_node_count=12,
            errors=[],
        )
        assert report.is_parity is False

    def test_parity_ratio_zero_ir_returns_zero(self):
        from dd.boundary import RenderReport
        report = RenderReport(
            backend="figma",
            ir_node_count=0,
            rendered_node_count=0,
            errors=[],
        )
        assert report.parity_ratio() == 0.0 or report.parity_ratio() == 1.0
        # Empty IR is a degenerate case; either is acceptable as long
        # as it doesn't crash.


@pytest.mark.unit
class TestRenderVerifierContract:
    """FigmaRenderVerifier walks a rendered tree (described as a
    lightweight dict for unit-testability) and diffs it against an IR.
    Produces a RenderReport with structured entries.
    """

    def _ir(self, elements):
        return {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {"type": "screen", "children": list(elements.keys())},
                **elements,
            },
        }

    def _rendered(self, by_eid):
        """Build a minimal rendered-tree payload. Each entry is
        {'type': <FigmaType>, 'characters': <str>, 'children': [...]}.
        Unit tests avoid driving the Plugin API."""
        return {
            "eid_map": by_eid,  # eid → {type, characters?, ...}
        }

    def test_exact_parity_returns_is_parity_true(self):
        from dd.verify_figma import FigmaRenderVerifier
        ir = self._ir({
            "button-1": {"type": "button"},
        })
        rendered = self._rendered({
            "screen-1": {"type": "FRAME"},
            "button-1": {"type": "INSTANCE"},
        })
        report = FigmaRenderVerifier().verify(ir, rendered)
        assert report.is_parity is True
        assert report.errors == []

    def test_instance_rendered_as_frame_flagged_as_type_substitution(self):
        from dd.verify_figma import FigmaRenderVerifier
        from dd.boundary import KIND_TYPE_SUBSTITUTION
        ir = self._ir({
            "button-1": {"type": "button"},
        })
        rendered = self._rendered({
            "screen-1": {"type": "FRAME"},
            "button-1": {"type": "FRAME"},  # should have been INSTANCE
        })
        report = FigmaRenderVerifier().verify(ir, rendered)
        assert report.is_parity is False
        substitution_errors = [e for e in report.errors if e.kind == KIND_TYPE_SUBSTITUTION]
        assert len(substitution_errors) == 1
        assert substitution_errors[0].id == "button-1"

    def test_empty_text_flagged_as_missing_text(self):
        from dd.verify_figma import FigmaRenderVerifier
        from dd.boundary import KIND_MISSING_TEXT
        ir = self._ir({
            "text-1": {"type": "text", "props": {"text": "Hello"}},
        })
        rendered = self._rendered({
            "screen-1": {"type": "FRAME"},
            "text-1": {"type": "TEXT", "characters": ""},
        })
        report = FigmaRenderVerifier().verify(ir, rendered)
        assert not report.is_parity
        missing = [e for e in report.errors if e.kind == KIND_MISSING_TEXT]
        assert len(missing) == 1
        assert missing[0].id == "text-1"

    def test_missing_eid_in_rendered_flagged_as_missing_child(self):
        from dd.verify_figma import FigmaRenderVerifier
        from dd.boundary import KIND_MISSING_CHILD
        ir = self._ir({
            "button-1": {"type": "button"},
            "icon-1": {"type": "icon"},
        })
        rendered = self._rendered({
            "screen-1": {"type": "FRAME"},
            "button-1": {"type": "INSTANCE"},
            # icon-1 missing
        })
        report = FigmaRenderVerifier().verify(ir, rendered)
        missing = [e for e in report.errors if e.kind == KIND_MISSING_CHILD]
        assert len(missing) == 1
        assert missing[0].id == "icon-1"

    def test_backend_identifier_exposed(self):
        from dd.verify_figma import FigmaRenderVerifier
        assert FigmaRenderVerifier().backend == "figma"


@pytest.mark.unit
class TestStructuredErrorShape:
    """Whatever the backend or failure mode, error entries have uniform shape."""

    def test_error_fields_present_for_ingest_null(self):
        from dd.ingest_figma import FigmaIngestAdapter

        adapter = FigmaIngestAdapter(
            file_key="test", token="tok",
            api_client=make_fake_api(null_ids={"2:2"}),
        )
        err = adapter.extract_screens(["2:2"]).errors[0]

        assert isinstance(err.kind, str) and err.kind
        assert err.id == "2:2"
        assert isinstance(err.context, dict)

    def test_error_fields_present_for_probe_api_error(self):
        from dd.ingest_figma import FigmaResourceProbe

        probe = FigmaResourceProbe(
            file_key="test", token="tok",
            api_client=make_fake_api(
                raise_for_ids={"1:1"},
                raise_exc=RuntimeError("boom"),
            ),
        )
        report = probe.probe(["1:1"])
        err = report.errors[0]

        assert err.kind == "api_error"
        assert "boom" in (err.error or "")
