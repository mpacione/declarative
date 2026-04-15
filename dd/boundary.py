"""Boundary contract (ADR-006): structured failure channel at every
external-system boundary, both ingest and catalog-freshness directions.

This module defines the *shape* that every backend must conform to. The
Figma instantiation lives in ``dd/ingest_figma.py``; future backends
(Storybook, SwiftUI previews, Flutter widget trees) add sibling modules
that import from here.

Mirrors on the Python side the JS ``__errors`` contract from ADR-002 (see
``dd/renderers/figma.py``). The shape is identical so that the same LLM
training feedback loop can consume ``StructuredError`` entries regardless
of which boundary they came from.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Shared structured-error channel
# ---------------------------------------------------------------------------


# Stable `kind` vocabulary consumed by harness / CI / training loop. New
# backends and new failure modes add to this list; downstream switches on
# the token, not free-text error messages.
#
# Ingest side (ADR-006)
KIND_NODE_NOT_FOUND = "node_not_found"
KIND_API_ERROR = "api_error"
KIND_MALFORMED_RESPONSE = "malformed_response"
KIND_RATE_LIMITED = "rate_limited"

# Codegen-time degradation (ADR-007 Position 1)
KIND_DEGRADED_TO_MODE2 = "degraded_to_mode2"
KIND_DEGRADED_TO_LITERAL = "degraded_to_literal"
KIND_DEGRADED_TO_PLACEHOLDER = "degraded_to_placeholder"
KIND_CAPABILITY_GATED = "capability_gated"
KIND_CKR_UNBUILT = "ckr_unbuilt"

# Runtime micro-guard failures (ADR-007 Position 2) — populated by
# per-operation guards emitted in generated scripts
KIND_TEXT_SET_FAILED = "text_set_failed"
KIND_RESIZE_FAILED = "resize_failed"
KIND_CONSTRAINT_FAILED = "constraint_failed"
KIND_POSITION_FAILED = "position_failed"

# Render-verification delta (ADR-007 Position 3)
KIND_TYPE_SUBSTITUTION = "type_substitution"
KIND_MISSING_TEXT = "missing_text"
KIND_MISSING_CHILD = "missing_child"
KIND_EXTRA_CHILD = "extra_child"
KIND_BOUNDS_MISMATCH = "bounds_mismatch"


@dataclass(frozen=True)
class StructuredError:
    """A single failure entry from any boundary interaction.

    ``kind`` is a short, stable token (not free text) — consumers
    (tests, training loop, CI) switch on it. ``id`` is the external
    identifier that failed (node id, component key, asset id, etc.).
    ``context`` is for fields that are backend- or call-site-specific
    (e.g. parent screen, eid, batch id).
    """

    kind: str
    id: str | None = None
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ingest side — ``IngestAdapter.extract(ids) -> IngestResult``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestSummary:
    """Honest tally. Invariant: requested == succeeded + failed."""

    requested: int
    succeeded: int
    failed: int

    def __post_init__(self) -> None:
        if self.requested != self.succeeded + self.failed:
            raise ValueError(
                f"IngestSummary tally inconsistent: "
                f"{self.requested} != {self.succeeded} + {self.failed}"
            )


@dataclass(frozen=True)
class IngestResult:
    """Return shape of every ``IngestAdapter.extract_screens`` call.

    Invariant: ``len(errors) == summary.failed``. The adapter is
    responsible for maintaining this; ``IngestResult.__post_init__``
    enforces it at construction.
    """

    extracted: list[dict[str, Any]]
    errors: list[StructuredError]
    summary: IngestSummary

    def __post_init__(self) -> None:
        if len(self.errors) != self.summary.failed:
            raise ValueError(
                f"IngestResult invariant violated: "
                f"len(errors)={len(self.errors)} != summary.failed={self.summary.failed}"
            )


@runtime_checkable
class IngestAdapter(Protocol):
    """Backend-neutral ingest contract.

    Every concrete backend exposes a ``backend`` class constant (used for
    registry dispatch) and an ``extract_screens`` method that never
    raises on partial failure — it produces a structured entry instead.
    """

    backend: ClassVar[str]

    def extract_screens(self, ids: list[str]) -> IngestResult: ...


# ---------------------------------------------------------------------------
# Catalog side — ``ResourceProbe.probe(ids) -> FreshnessReport``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessReport:
    """Resource-catalog classification result.

    Every probed id falls into exactly one of three sets:

    - ``valid_ids``    — source confirmed the id exists
    - ``missing_ids``  — source confirmed the id does NOT exist (drift)
    - ``unknown_ids``  — couldn't decide (transient error, rate limit)

    Invariant: the three sets partition the input. ``errors`` carries
    structured detail for every id in ``unknown_ids`` (and may include
    extra entries for batch-level failures).
    """

    backend: str
    checked: int
    valid_ids: frozenset[str]
    missing_ids: frozenset[str]
    unknown_ids: frozenset[str]
    errors: list[StructuredError]

    def __post_init__(self) -> None:
        total = len(self.valid_ids) + len(self.missing_ids) + len(self.unknown_ids)
        if total != self.checked:
            raise ValueError(
                f"FreshnessReport partition violated: "
                f"valid+missing+unknown={total} != checked={self.checked}"
            )
        overlap = (
            (self.valid_ids & self.missing_ids)
            | (self.valid_ids & self.unknown_ids)
            | (self.missing_ids & self.unknown_ids)
        )
        if overlap:
            raise ValueError(f"FreshnessReport sets overlap: {overlap}")

    @property
    def is_fresh(self) -> bool:
        """True only when every probed id is confirmed valid."""
        return len(self.missing_ids) == 0 and len(self.unknown_ids) == 0

    def stale_ratio(self) -> float:
        """Fraction of probed ids that are confirmed missing (drift signal)."""
        if self.checked == 0:
            return 0.0
        return len(self.missing_ids) / self.checked


@runtime_checkable
class ResourceProbe(Protocol):
    """Backend-neutral freshness-probe contract.

    Used (1) pre-emission to gate generation against a stale catalog,
    (2) pre-decode in synthetic IR validation to reject references the
    LLM proposed against resources that no longer exist.
    """

    backend: ClassVar[str]

    def probe(self, ids: Iterable[str]) -> FreshnessReport: ...


# ---------------------------------------------------------------------------
# Post-render verification (ADR-007 Position 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderReport:
    """Post-render structural parity report.

    Symmetric with ``IngestResult`` on the ingest side: IR + rendered
    external-world state → structured diff. Every deviation is a
    ``StructuredError`` with ``id`` pointing at the IR position that
    failed, so downstream verification (CI, training loop) gets
    per-node credit assignment.

    Invariants enforced at construction:

    - ``is_parity ⇔ (errors == [] AND ir_node_count == rendered_node_count)``
    - ``parity_ratio`` is monotone in ``len(errors)``.
    """

    backend: str
    ir_node_count: int
    rendered_node_count: int
    errors: list[StructuredError]

    @property
    def is_parity(self) -> bool:
        return (
            len(self.errors) == 0
            and self.ir_node_count == self.rendered_node_count
        )

    def parity_ratio(self) -> float:
        if self.ir_node_count == 0:
            return 1.0 if len(self.errors) == 0 else 0.0
        matched = max(0, self.ir_node_count - len(self.errors))
        return matched / self.ir_node_count


@runtime_checkable
class RenderVerifier(Protocol):
    """Backend-neutral render-verification contract.

    Takes the IR and a backend-specific rendered-tree reference.
    Produces a ``RenderReport`` with per-node structured errors.

    The backend-specific part is *how* to walk the rendered tree.
    The contract shape (StructuredError entries, RenderReport
    invariants) is shared across Figma, React, SwiftUI, Flutter.

    For synthetic generation, this is the reward-signal endpoint:
    ``RenderReport.parity_ratio`` is the scalar fitness; the
    ``errors`` list provides the per-node training signal.
    """

    backend: ClassVar[str]

    def verify(self, ir: dict[str, Any], rendered_ref: Any) -> RenderReport: ...
