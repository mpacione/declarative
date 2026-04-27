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

# Mode 3 composition — resolution boundary (ADR-008)
# Provider registry walk and DTCG cascade both feed these back through the
# existing ADR-007 per-node __errors channel. Consumers switch on `kind`.
KIND_NO_PROVIDER_MATCH = "no_provider_match"
KIND_VARIANT_NOT_FOUND = "variant_not_found"
KIND_TOKEN_UNRESOLVED = "token_unresolved"
KIND_SLOT_TYPE_MISMATCH = "slot_type_mismatch"
KIND_VARIANT_BINDING_MISSING = "variant_binding_missing"

# Prompt layer (ADR-008 v0.1.5) — upstream planner returned an invalid
# skeleton or the fill call couldn't realize it after one retry.
# ``dd.composition.plan.plan_then_fill`` emits this in the same
# structured-error shape the ADR-006 boundary promises.
KIND_PLAN_INVALID = "plan_invalid"

# Stage 0.5 (docs/plan-authoring-loop.md) — the planner named a slot
# on a node whose parent type declares a closed slot set and the
# slot name isn't in it. Log-only for the first release per plan §8
# decision 3: promote to hard-error once a rejection-free week of
# real runs lands, so hallucinated slot names can't go unnoticed.
KIND_SLOT_UNKNOWN = "slot_unknown"

# Stage 0.6 (docs/plan-authoring-loop.md) — compose output drifted from
# the planner's intent on at least one (eid, type, parent_eid)
# tuple. Different from KIND_PLAN_INVALID (which is "the plan itself
# was shaped wrong") — this fires when a validated plan doesn't
# survive the compose pass. Surfacing this keeps the planner's
# intent addressable downstream.
KIND_PLAN_DRIFT = "plan_drift"

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
# figma.loadFontAsync() threw for a specific family/style. Common cause:
# unlicensed trial fonts like "ABC Diatype Mono Medium Unlicensed Trial"
# that are present in the Figma file but can't be loaded by the Plugin
# API. Without a guard, one missing font aborts the entire script —
# including every unrelated text node that uses a different font. The
# guard localises the failure to the specific (family, style) pair.
KIND_FONT_LOAD_FAILED = "font_load_failed"

# Render-verification delta (ADR-007 Position 3)
KIND_TYPE_SUBSTITUTION = "type_substitution"
KIND_MISSING_TEXT = "missing_text"
KIND_MISSING_CHILD = "missing_child"
KIND_EXTRA_CHILD = "extra_child"
KIND_BOUNDS_MISMATCH = "bounds_mismatch"
# VECTOR / BOOLEAN_OPERATION rendered with zero path geometry — the
# node was emitted as a vector host but has no paths, so Figma falls
# back to a shape-less frame-like placeholder (i.e. a grey rectangle
# of the node's width/height). Catches the entire
# "empty grey box where illustration should be" defect class that
# the structural parity check is blind to.
KIND_MISSING_ASSET = "missing_asset"
# A node's rendered SOLID fill color differs from the IR's normalized
# fill color. Catches the visual-loss class where structural parity
# holds (correct tree shape) but the node shows the wrong color —
# e.g. a variant resolved to a different default fill, or the renderer
# emitted a stale/wrong hex. Only fires on SOLID fills for now;
# gradient-stop and image-hash mismatches are future candidates.
KIND_FILL_MISMATCH = "fill_mismatch"
# A node's rendered SOLID stroke color differs from the IR's normalized
# stroke color. Same pattern as KIND_FILL_MISMATCH but for strokes.
KIND_STROKE_MISMATCH = "stroke_mismatch"
# A node's IR declares effects (shadows, blurs) but the rendered node
# has fewer effects. Catches dropped shadows, missing blurs, etc.
KIND_EFFECT_MISSING = "effect_missing"
# A node's IR opacity differs from the rendered opacity. Pre-P1
# (forensic-audit-2) the verifier was blind to opacity drift even
# though the renderer emits it via the registry-driven path. Drift
# of >epsilon is a real visual difference (faded vs solid).
KIND_OPACITY_MISMATCH = "opacity_mismatch"
# A node's IR blendMode differs from the rendered blendMode. Drift
# here changes how a node composites against its background — e.g.
# MULTIPLY → NORMAL hides any darkening overlay.
KIND_BLENDMODE_MISMATCH = "blendmode_mismatch"
# A node's IR rotation differs from the rendered rotation (in radians,
# tolerance ~1e-3). The walker captures rotation as part of SoM
# overlay; pre-P1 the verifier never compared it.
KIND_ROTATION_MISMATCH = "rotation_mismatch"
# A node's IR isMask flag differs from the rendered isMask. A node
# silently flipped from mask to non-mask leaks the masked content;
# the inverse hides what should be visible.
KIND_MASK_MISMATCH = "mask_mismatch"
# A node's IR cornerRadius (uniform or per-corner) differs from the
# rendered cornerRadius. Pre-P1 was the only "complex" registry visual
# prop the verifier didn't compare despite being emitted.
KIND_CORNERRADIUS_MISMATCH = "cornerradius_mismatch"
# A node's IR strokeWeight differs from the rendered strokeWeight.
# A5 (forensic-audit-2 sprint, Pattern G): strokeWeight is registry-
# driven via _UNIFORM but pre-A5 had no comparator. Drift on stroke
# weight (e.g. master defaults vs override) was silent.
KIND_STROKE_WEIGHT_MISMATCH = "stroke_weight_mismatch"
# A node's IR strokeAlign (INSIDE / CENTER / OUTSIDE) differs from
# rendered. A5: strokeAlign affects stroke positioning relative to
# the geometry boundary; visible difference but pre-A5 silent.
KIND_STROKE_ALIGN_MISMATCH = "stroke_align_mismatch"
# A node's IR dashPattern (array of dash/gap lengths) differs from
# rendered. A5: a solid stroke vs a dashed stroke is a clear visual
# loss; pre-A5 silent.
KIND_DASH_PATTERN_MISMATCH = "dash_pattern_mismatch"
# A node's IR clipsContent (boolean — whether overflowing children
# get clipped) differs from rendered. A5: visible content
# leak/clip; pre-A5 silent.
KIND_CLIPS_CONTENT_MISMATCH = "clips_content_mismatch"
# Sprint 2 C10: text content (characters) differs between IR and
# rendered. The HGB button bug: IR carries override "Reject", master
# default is "Send to Client", renderer fell through to master default.
# Pre-C10 the verifier only checked empty/non-empty (KIND_MISSING_TEXT);
# value-equality compare is the C10 graduation.
KIND_TEXT_CONTENT_MISMATCH = "text_content_mismatch"
# Sprint 2 C10: layout sizing horizontal mode (HUG/FILL/FIXED) differs
# between IR and rendered. Width numbers can match while sizing mode
# drifts — surfaces auto-layout regressions invisible to bounds compare.
KIND_LAYOUT_SIZING_H_MISMATCH = "layout_sizing_h_mismatch"
# Sprint 2 C10: layout sizing vertical mode (HUG/FILL/FIXED) differs.
# Sibling of layout_sizing_h_mismatch.
KIND_LAYOUT_SIZING_V_MISMATCH = "layout_sizing_v_mismatch"
# Gradient fill has no Plugin API gradientTransform — the REST API
# handlePositions can't be reliably converted. Renderer skips the
# gradient rather than emitting a wrong matrix.
KIND_GRADIENT_TRANSFORM_MISSING = "gradient_transform_missing"
# Figma's Plugin API has getRangeOpenTypeFeatures() but no setter —
# OpenType features (SUPS, SUBS, LIGA, etc.) on specific text ranges
# are read-only from the plugin side. When IR has per-range features,
# we can't apply them via the plugin. For some specific features we
# do a lossy Unicode substitution (e.g. "0"+SUPS -> "°"), but generic
# features surface as this kind.
KIND_OPENTYPE_UNSUPPORTED = "opentype_unsupported"
# A component referenced by an INSTANCE node's swap target doesn't
# resolve at runtime (e.g. the component was deleted from the source
# file after extraction, or the file's component library was stripped).
# The renderer emits a wireframe placeholder (black-stroked frame with
# X diagonals) in place of the missing component and pushes this entry
# so the verification channel attributes the gap per-eid.
KIND_COMPONENT_MISSING = "component_missing"


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
    # M7.5 verifier-as-agent hook: a short natural-language repair
    # hint for the LLM ("swap target X was deleted earlier in this
    # sequence — either re-add it or drop the swap"). Verifiers that
    # know *how* an error should be fixed attach a hint; downstream
    # code tries to repair off the hint, and is allowed to ignore
    # when the hint is None. Free-text (not enum) to preserve the
    # option to include file paths / variant names / numeric
    # tolerances in the hint body.
    hint: str | None = None


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
    """Post-render parity report — structural + runtime.

    Symmetric with ``IngestResult`` on the ingest side: IR + rendered
    external-world state → structured diff. Every deviation is a
    ``StructuredError`` with ``id`` pointing at the IR position that
    failed, so downstream verification (CI, training loop) gets
    per-node credit assignment.

    Two error channels, both consumed by ``is_parity``:

    - ``errors``: STRUCTURAL drift from the verifier's tree walk
      (missing_child, type_mismatch, fill_mismatch, bounds_mismatch,
      missing_text, etc.). One entry per failing IR position.
    - ``runtime_errors``: RUNTIME failures recorded by the render
      script's per-op try/catch handlers (text_set_failed,
      font_load_failed, append_child_failed, group_create_failed,
      etc.). Heterogeneous shape — kept as raw dicts because the
      renderer's ``__errors.push`` calls have varied payloads (eid,
      property, family/style, node_id, name, error). One entry per
      failing operation.

    Invariants (P1 + P4):

    - ``is_structural_parity ⇔ (errors == [] AND ir_node_count == rendered_node_count)``
    - ``is_runtime_clean ⇔ len(runtime_errors) == 0``
    - ``is_parity ⇔ is_structural_parity AND is_runtime_clean``  (strict)
    - ``parity_ratio`` is structural only — monotone in ``len(errors)``,
      independent of ``runtime_errors``. **A report can have
      ``is_parity=False`` with ``parity_ratio=1.0``** (rendered tree
      matches IR shape exactly, but runtime errors were recorded).
      Use ``is_structural_parity`` when you want the historical
      shape-only signal; ``is_runtime_clean`` for runtime-only;
      ``is_parity`` for the strict combined.

    Phase E Pattern 2 fix:
    - P1 (2026-04-25): inhale ``rendered_ref["errors"]`` into
      ``runtime_errors`` (Codex Shape A); make ``is_parity`` strict.
    - P4 (2026-04-25): explicit ``is_runtime_clean`` channel + group
      raw kinds into diagnostic categories via
      ``dd/runtime_errors.py``. Sweep summary surfaces the categories
      so "1015 runtime errors" becomes "600 font_health / 268
      escaped_artifact / 131 instance_materialization / ...".
    """

    backend: str
    ir_node_count: int
    rendered_node_count: int
    errors: list[StructuredError]
    runtime_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_structural_parity(self) -> bool:
        """Pre-Phase-E definition: tree shape matches, no structural drift.

        Use when the question is "did the renderer produce the right
        TREE?", independent of whether runtime ops landed cleanly.
        """
        return (
            len(self.errors) == 0
            and self.ir_node_count == self.rendered_node_count
        )

    @property
    def is_runtime_clean(self) -> bool:
        """P4 channel: zero runtime errors, regardless of structure.

        Codex Phase E review (2026-04-25, gpt-5.5): "Add it. Reduces
        caller-specific spellings like ``runtime_error_count == 0``."

        Use when the question is "did the renderer's per-op guards
        all pass cleanly?", independent of whether the IR ↔ rendered
        tree shapes match.
        """
        return len(self.runtime_errors) == 0

    @property
    def is_parity(self) -> bool:
        """Strict parity: structural OK AND runtime clean.

        Codex Phase E review (2026-04-25): "Catch-and-continue
        prevents abort cascades and preserves diagnostic evidence.
        But makes the single ``is_parity`` boolean less truthful,
        because failures move from fatal-visible to recoverable-
        invisible unless verifier scope expands." This expansion
        closes that gap.
        """
        return self.is_structural_parity and self.is_runtime_clean

    @property
    def runtime_error_count(self) -> int:
        return len(self.runtime_errors)

    @property
    def runtime_error_kinds(self) -> dict[str, int]:
        """Counter of runtime error kinds. Convenience for callers
        that want the distribution without iterating themselves."""
        out: dict[str, int] = {}
        for e in self.runtime_errors:
            if isinstance(e, dict):
                kind = str(e.get("kind", "?"))
                out[kind] = out.get(kind, 0) + 1
        return out

    @property
    def runtime_error_categories(self) -> dict[str, int]:
        """P4 — Counter of runtime errors grouped by diagnostic
        category. Categories are defined in ``dd/runtime_errors.py``
        (single source of truth). Unknown kinds (older payloads or
        kinds added without updating the map) bucket as
        ``"uncategorized"`` — non-throwing in production; the
        convention test in ``tests/test_p4_runtime_error_categorization.py``
        fails CI when a repo-source literal is missing.

        Codex review note: "keep ``runtime_error_kinds`` for the
        sharp signal; categories are for sweep readability only."
        Both are exposed so callers can pick the right grain.
        """
        # Local import to avoid circular dependency at module-init
        # time (runtime_errors.py is a leaf module today, but if
        # something there ever needs RenderReport, this guards it).
        from dd.runtime_errors import categorize_runtime_error_kind
        out: dict[str, int] = {}
        for e in self.runtime_errors:
            if isinstance(e, dict):
                kind = str(e.get("kind", "?"))
                cat = categorize_runtime_error_kind(kind)
                out[cat] = out.get(cat, 0) + 1
        return out

    def parity_ratio(self) -> float:
        """Structural parity ratio. NOT affected by runtime_errors —
        a report can have ``parity_ratio=1.0`` with
        ``is_parity=False`` if every IR node landed in the rendered
        tree but some runtime ops threw and were caught."""
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
