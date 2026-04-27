"""Fidelity scorer scoped to Tier B's observed failure modes.

Per ``docs/plan-burndown.md`` Tier C.2 and
``docs/learnings-tier-b-failure-modes.md``: the scorer tests the
FOUR concrete failure classes Tier B actually surfaced, not a
generic 5-dim rubric in the dark.

The four checkable dimensions (all cost zero — no VLM call):

1. **Coverage** — ``rendered_eids / ir_elements`` (F3: cascading
   Phase-2 abort).
2. **Font readiness** — no ``text_set_failed`` errors (F1).
3. **Component-child consistency** — no ``render_thrown`` with
   "appendChild" + "instance" (F2).
4. **Leaf-type structural** — no IR element with
   ``canonical_type`` ∈ LEAF_TYPES has children > 0 (F4).

An optional FIFTH dimension runs a Gemini VLM pass on a rendered
screenshot for semantic quality — kept as a distinct, opt-in
step because it costs real money + 30% transient error rate (see
``feedback_vlm_transient_retries.md``).

Per `docs/research/evaluation-rubric-calibration.md`: the target
gate is ≥7/10 (≡ ≥3/5 on a 0-5 scale). This module emits
dimension scores in [0.0, 1.0]; a caller-decided aggregation
projects to a single 0-10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Grammar / catalog types that can't host children. A child under
# one of these is an F4 structural error. Source: Figma Plugin
# API semantics + catalog canonical_types that resolve Mode-1
# INSTANCE.
#
# TODO(Tier E.3): derive this set from the component_type_catalog
# at runtime (query `resolution_mode = 'instance'` rows) rather
# than hardcoding. The current set was hand-picked against Dank,
# where `icon_button` / `slider` / `fab` resolve as FRAME. A
# shadcn / Material-3 ingest will likely flip some of those to
# INSTANCE, and the hardcoded set would under-report.
LEAF_TYPES: frozenset[str] = frozenset({
    "text", "heading", "link",
    "rectangle", "ellipse", "line", "vector",
    "icon",     # resolves Mode-1 to INSTANCE (can't host children)
    "button",   # same — INSTANCE, not a container
    "chip",
    "switch",
    "toggle",
    "checkbox",
    "radio",
})


@dataclass
class DimensionScore:
    """One dimension of the fidelity gate."""

    name: str
    value: float          # [0.0, 1.0], 1.0 = perfect
    passed: bool          # soft/hard threshold — caller-defined
    diagnostic: str       # human-readable cause when value < 1.0


@dataclass
class FidelityReport:
    """Aggregated fidelity gate output. Each dimension is independent;
    the caller decides how to combine (typically ``min(values)``
    for a conservative gate, or weighted average for a soft one)."""

    dimensions: list[DimensionScore] = field(default_factory=list)
    vlm_dimension: Optional[DimensionScore] = None

    @property
    def aggregate_min(self) -> float:
        """Conservative: the worst dim governs. Good default for
        rejection gates where any hard failure should block."""
        vals = [d.value for d in self.dimensions]
        if self.vlm_dimension is not None:
            vals.append(self.vlm_dimension.value)
        return min(vals) if vals else 0.0

    @property
    def aggregate_mean(self) -> float:
        """Soft average — good for ranking alternatives."""
        vals = [d.value for d in self.dimensions]
        if self.vlm_dimension is not None:
            vals.append(self.vlm_dimension.value)
        return sum(vals) / len(vals) if vals else 0.0

    def to_ten(self, mode: str = "min") -> float:
        """Project to 0-10. Default to conservative min."""
        scale = self.aggregate_min if mode == "min" else self.aggregate_mean
        return round(scale * 10, 2)

    @property
    def all_passed(self) -> bool:
        dims = list(self.dimensions)
        if self.vlm_dimension is not None:
            dims.append(self.vlm_dimension)
        return all(d.passed for d in dims)


# ---------------------------------------------------------------
# Dimension 1: rendered-coverage ratio (Tier B F3)
# ---------------------------------------------------------------


def score_coverage(
    ir_elements: dict[str, Any],
    walk_eid_map: dict[str, Any],
    *,
    threshold: float = 0.8,
) -> DimensionScore:
    """``len(rendered) / len(ir)``.

    IR elements with absorbed-as-Mode-1-descendant are excluded
    from the denominator: when a Mode-1 INSTANCE hosts children
    in the IR, those children are supplied by the master
    component at render time and don't appear as independent
    rendered eids — that's expected, not a failure. We detect
    absorbed eids by walking each rendered INSTANCE's spec-side
    children and marking them as absorbed.

    ``threshold`` is the pass bar. Default 0.8 picks up prompt 3's
    3/7 (0.43) as a fail while letting partial-instance-absorption
    cases (0.9-ish) through.
    """
    absorbed: set[str] = set()

    def collect(eid: str) -> None:
        elem = ir_elements.get(eid) or {}
        for c in (elem.get("children") or []):
            if c in absorbed:
                continue
            absorbed.add(c)
            collect(c)

    for eid, rendered in walk_eid_map.items():
        if rendered.get("type") == "INSTANCE":
            collect(eid)

    expected_eids = {
        e for e in ir_elements if e not in absorbed
    }
    rendered_eids = set(walk_eid_map.keys())
    if not expected_eids:
        return DimensionScore(
            name="coverage", value=1.0, passed=True,
            diagnostic="no IR elements to cover",
        )
    matched = expected_eids & rendered_eids
    ratio = len(matched) / len(expected_eids)
    passed = ratio >= threshold
    missing = expected_eids - rendered_eids
    diag = (
        f"rendered {len(matched)}/{len(expected_eids)} "
        f"({ratio:.0%})"
        + (f"; missing={sorted(missing)[:5]}" if missing else "")
    )
    return DimensionScore(
        name="coverage", value=ratio, passed=passed, diagnostic=diag,
    )


# ---------------------------------------------------------------
# Dimension 2: font readiness (Tier B F1)
# ---------------------------------------------------------------


_FONT_NAME_PATTERN = __import__("re").compile(
    r'(?:unloaded font|font family)\s+"([^"]+)"',
    __import__("re").IGNORECASE,
)


def score_font_readiness(errors: list[dict[str, Any]]) -> DimensionScore:
    """Look for ``text_set_failed`` in the render-walk errors.

    Each occurrence means the preamble missed a font the script
    needed. Score decreases with failure count so the repair loop
    can rank alternates correctly (10 failures should score worse
    than 1). Score curve: 0.7 at 1 failure, 0.4 at 3, 0.1 at 10+.
    """
    font_failures = [
        e for e in errors
        if e.get("kind") == "text_set_failed"
    ]
    if not font_failures:
        return DimensionScore(
            name="font_readiness", value=1.0, passed=True,
            diagnostic="no font-load failures",
        )
    # Extract font names via a regex robust to format drift
    # (split('"')[1] was brittle to any error string without a
    # quoted substring).
    fonts: set[str] = set()
    for e in font_failures:
        msg = e.get("error") or ""
        match = _FONT_NAME_PATTERN.search(msg)
        if match:
            fonts.add(match.group(1))
    # Decreasing score curve. Any font failure is a hard fail
    # (text shows as empty strings, not a minor visual glitch),
    # so score is always ≤ 0.5. Curve: 1 → 0.4, 3 → 0.25, 10+ → 0.1.
    n = len(font_failures)
    value = max(0.1, 0.5 - 0.1 * n)
    diag = (
        f"{n} font-load failure(s) "
        f"across {len(fonts) or '?'} fonts: "
        f"{sorted(fonts)[:3] if fonts else '(unparseable)'}"
    )
    return DimensionScore(
        name="font_readiness", value=value, passed=False, diagnostic=diag,
    )


# ---------------------------------------------------------------
# Dimension 3: component-child consistency (Tier B F2)
# ---------------------------------------------------------------


def score_component_child_consistency(
    errors: list[dict[str, Any]],
) -> DimensionScore:
    """Look for appendChild-into-instance failures in the render-
    walk errors. F2 is the #1 blocker observed in Tier B.

    Matches two error shapes:
    - Legacy: ``kind='render_thrown'`` with "appendChild" +
      "instance" in the error string (pre-guard cascade).
    - Post-guard (b95d3bc + b26ddf7): ``kind='append_child_failed'``
      with "instance" in the error string. Per-op guards turn the
      cascade into a structured entry but the defect class is the
      same."""

    def _is_instance_append(e: dict[str, Any]) -> bool:
        msg = (e.get("error") or "").lower()
        if "appendchild" not in msg and "append child" not in msg:
            return False
        return "instance" in msg

    hits = [
        e for e in errors
        if (e.get("kind") == "render_thrown"
            or e.get("kind") == "append_child_failed")
        and _is_instance_append(e)
    ]
    if not hits:
        return DimensionScore(
            name="component_child_consistency",
            value=1.0, passed=True,
            diagnostic="no appendChild-into-instance errors",
        )
    # Single hit is fatal per Tier B observation.
    affected = sorted({e.get("eid", "?") for e in hits})[:5]
    return DimensionScore(
        name="component_child_consistency",
        value=0.2, passed=False,
        diagnostic=(
            f"{len(hits)} appendChild-into-instance error(s) "
            f"[eids: {affected}] — Mode-3 emitted a CompRef parent "
            "with a child subtree but INSTANCE nodes can't host "
            "children (Figma Plugin API constraint). See "
            "docs/learnings-tier-b-failure-modes.md F2."
        ),
    )


# ---------------------------------------------------------------
# Dimension 4: leaf-type structural (Tier B F4)
# ---------------------------------------------------------------


# ---------------------------------------------------------------
# Dimension 5: rootedness (root attached to page)
# ---------------------------------------------------------------


# Error kinds that indicate the root attach op failed. When any of
# these fires, the generated tree is DETACHED from the page —
# Figma's createFrame auto-parents to currentPage, so un-re-parented
# nodes end up flat at the page root. User-visible symptom: "no
# nesting hierarchy."
#
# Introduced with the Tier E follow-up Phase-2 guards
# (commit b95d3bc + follow-up). Before those, every appendChild
# was naked and a single throw orphaned the whole tree. The scorer
# was blind to this because coverage checked eid presence, not
# whether those eids were actually attached.
_ROOTING_ERROR_KINDS: frozenset[str] = frozenset({
    "root_append_failed",
    "append_child_failed",  # any cascading append also implies broken nesting
})


def score_rootedness(
    root_eid: str | None,
    walk_eid_map: dict[str, Any],
    walk_errors: list[dict[str, Any]],
) -> DimensionScore:
    """Check the rendered tree is actually attached to the page.

    Two signals:

    1. ``root_eid`` (typically ``"screen-1"`` for compose output)
       must appear in ``walk_eid_map``. The walker traverses from
       the page's screen-root; if it's missing, nothing showed up
       on the page.
    2. No ``root_append_failed`` or ``append_child_failed`` errors
       in the walk's ``__errors`` channel. Both indicate the tree
       wiring threw and siblings may be orphaned at page root.

    When ``root_eid`` is None, the caller didn't provide a root
    to check against — we pass-through as a soft 1.0 so the
    dimension isn't a false-positive block. Gate failures produce
    a diagnostic naming the failing kinds."""
    if not root_eid:
        return DimensionScore(
            name="rootedness", value=1.0, passed=True,
            diagnostic="no root_eid provided (dim skipped)",
        )

    # Gate 1: root exists in walk
    root_in_walk = root_eid in walk_eid_map
    # Gate 2: no rooting-related errors
    rooting_errors = [
        e for e in walk_errors
        if e.get("kind") in _ROOTING_ERROR_KINDS
    ]

    if root_in_walk and not rooting_errors:
        return DimensionScore(
            name="rootedness", value=1.0, passed=True,
            diagnostic=f"root @{root_eid} attached; no rooting errors",
        )

    # Failure path — structured diagnostic
    parts: list[str] = []
    if not root_in_walk:
        parts.append(f"root @{root_eid} missing from rendered walk")
    if rooting_errors:
        kinds = sorted({e.get("kind", "?") for e in rooting_errors})
        parts.append(
            f"{len(rooting_errors)} rooting error(s): {kinds}"
        )
    diag = "; ".join(parts)

    # Hard cap value — either failure is catastrophic (nothing on
    # page visible in the expected hierarchy).
    value = 0.1 if not root_in_walk else 0.4
    return DimensionScore(
        name="rootedness", value=value, passed=False, diagnostic=diag,
    )


# ---------------------------------------------------------------
# Dimension 6: canvas coverage (visual plausibility)
# ---------------------------------------------------------------
#
# Added 2026-04-21 after the Tier D re-gate caught a subtree
# scoring 10/10 structurally on a visually-blank output (a 396x20
# toast strip in a 428x926 screen, ~2% coverage). All four
# structural dims passed because coverage=1/1, rootedness=1.0,
# no font errors, no appendChild errors, no leaf-with-children —
# but there was literally nothing to see.
#
# Scoped per feedback_auto_inspect_before_human_rate.md:
# "Structural parity is not visual plausibility." This dim is
# rule-based (no VLM call) — just walk geometry.


def score_canvas_coverage(
    root_eid: str | None,
    ir_elements: dict[str, Any],
    walk_eid_map: dict[str, Any],
    *,
    threshold: float = 0.10,
) -> DimensionScore:
    """Fraction of the root's bbox covered by direct-child bboxes.

    A screen whose only content is a tiny element (20px toast in
    928px screen → ~2%) fails this dim. Catches outputs where
    structural dims pass but visually the screen is empty.

    Returns 1.0 (skip) when root is absent / unsized — those cases
    are rootedness's concern, not this dim's.

    ``threshold`` defaults to 0.10 — a screen root needs at least
    10% painted area to be plausibly a rendered screen. Subtree
    callers may want to tune higher.
    """
    if not root_eid:
        return DimensionScore(
            name="canvas_coverage", value=1.0, passed=True,
            diagnostic="no root_eid (dim skipped)",
        )
    root = walk_eid_map.get(root_eid) or {}
    rw = root.get("width") or 0
    rh = root.get("height") or 0
    if rw <= 0 or rh <= 0:
        return DimensionScore(
            name="canvas_coverage", value=1.0, passed=True,
            diagnostic="root has no dimensions in walk (dim skipped)",
        )
    root_area = rw * rh

    children_ids = (ir_elements.get(root_eid) or {}).get("children") or []
    child_area = 0
    for cid in children_ids:
        c = walk_eid_map.get(cid) or {}
        cw = c.get("width") or 0
        ch = c.get("height") or 0
        child_area += cw * ch

    ratio = min(child_area / root_area, 1.0) if root_area else 1.0
    passed = ratio >= threshold
    # Convert raw ratio to a 0-1 goodness score. Below threshold,
    # scale linearly (partial credit for being close); at/above,
    # full 1.0. This mirrors content_richness so aggregate_min
    # isn't dragged down by a dim that actually passed.
    value = min(ratio / threshold, 1.0) if threshold > 0 else 1.0
    diag = (
        f"direct-children cover {int(child_area)}/{int(root_area)} "
        f"({ratio:.1%}) of root"
    )
    if not passed:
        diag += (
            f" — below {threshold:.0%} threshold; visually sparse render"
        )
    return DimensionScore(
        name="canvas_coverage", value=value, passed=passed,
        diagnostic=diag,
    )


# ---------------------------------------------------------------
# Dimension 7: content richness (visual plausibility)
# ---------------------------------------------------------------


def _walk_node_is_visible(node: dict[str, Any]) -> bool:
    """True if a walked node carries some visible content.

    Signals (any one is enough):
    - ``fills`` — the walker only surfaces fills when present
    - ``strokes`` — same
    - ``characters`` — TEXT node with actual text
    - ``type == "INSTANCE"`` — paints from its master component
    - ``effectCount > 0`` — drop-shadow / blur / etc.
    """
    if node.get("fills"):
        return True
    if node.get("strokes"):
        return True
    if node.get("characters"):
        return True
    if node.get("type") == "INSTANCE":
        return True
    if (node.get("effectCount") or 0) > 0:
        return True
    return False


def score_content_richness(
    walk_eid_map: dict[str, Any],
    *,
    min_visible: int = 3,
) -> DimensionScore:
    """Fraction of rendered nodes that carry visible content.

    Value = ``min(visible_count / min_visible, 1.0)``. A render
    with fewer than ``min_visible`` visible-content nodes almost
    always reads as trivially empty to a human viewer — this dim
    catches it when the other structural dims pass.

    Passes at 0.7, so roughly ceil(``min_visible`` × 0.7) visible
    elements are needed. Default ``min_visible=3`` means we need
    at least 3 content-bearing elements for an honest pass.
    """
    if not walk_eid_map:
        # Empty walk is a different failure (coverage dim's concern).
        # Skip to avoid double-counting; a real "nothing rendered"
        # lands on coverage and rootedness already.
        return DimensionScore(
            name="content_richness", value=1.0, passed=True,
            diagnostic="no rendered nodes (dim skipped)",
        )
    visible = sum(
        1 for n in walk_eid_map.values() if _walk_node_is_visible(n)
    )
    ratio = min(visible / min_visible, 1.0) if min_visible > 0 else 1.0
    passed = ratio >= 0.7
    diag = (
        f"{visible}/{len(walk_eid_map)} rendered nodes carry visible "
        f"content"
    )
    if not passed:
        diag += (
            f" — below ~{int(min_visible * 0.7)} minimum; "
            "trivial output"
        )
    return DimensionScore(
        name="content_richness", value=ratio, passed=passed,
        diagnostic=diag,
    )


def score_leaf_type_structural(
    ir_elements: dict[str, Any],
) -> DimensionScore:
    """Count IR elements where ``type`` ∈ LEAF_TYPES has
    ``children`` > 0. F4 = LLM's mental model conflicts with the
    library's leaf-vs-container semantics."""
    violations: list[tuple[str, str, int]] = []
    for eid, elem in ir_elements.items():
        t = elem.get("type") or ""
        children = elem.get("children") or []
        if t in LEAF_TYPES and children:
            violations.append((eid, t, len(children)))
    if not violations:
        return DimensionScore(
            name="leaf_type_structural", value=1.0, passed=True,
            diagnostic="no leaf types with children",
        )
    diag = f"{len(violations)} leaf-with-children violations: " + ", ".join(
        f"{eid}({t}, n={n})" for eid, t, n in violations[:5]
    )
    return DimensionScore(
        name="leaf_type_structural", value=0.4, passed=False,
        diagnostic=diag,
    )


# ---------------------------------------------------------------
# Dimensions 8 + 9: SoM-based component coverage (precision + recall)
# ---------------------------------------------------------------
#
# Per docs/research/scorer-calibration-and-som-fidelity.md §4 (D2):
# replace the noisy 1-10 Gemini "rate the screenshot" pass with a
# structured enum-constrained classification over rendered regions,
# compared against the IR's declared canonical types.
#
# Pattern matches GenEval (NeurIPS 2023, 83% human agreement on
# natural images) and Design2Code Block-Match (ACL 2025 for HTML
# screenshot-to-code). Our substrate is SoM classification over our
# 54+ canonical UI catalog — the unpublished combination.
#
# Split into three pure/testable pieces:
# 1. ``build_som_annotations`` — IR + walk bboxes → SoM annotations
# 2. ``compute_coverage_from_types`` — bag-match expected vs detected
#    → (precision, recall, info)
# 3. ``score_component_coverage`` — top-level dim pair; takes SoM
#    classifications (either precomputed or via an injectable call)

# Types excluded by default when building expected / detected bags.
# - ``screen``: the root; generic, not a semantic component.
# - ``frame``: structural wrapper with no declared semantic type.
# - ``container``: SoM sentinel for abstract groupings.
# - ``unsure``: SoM sentinel for ambiguous regions.
_DEFAULT_COVERAGE_EXCLUDE: frozenset[str] = frozenset({
    "screen", "frame", "container", "unsure",
})


def build_som_annotations(
    ir_elements: dict[str, Any],
    walk_eid_map: dict[str, Any],
    *,
    exclude_types: frozenset[str] = _DEFAULT_COVERAGE_EXCLUDE,
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    """Build SoM annotations from IR + walk bboxes.

    Annotation format matches ``dd.classify_vision_som.render_som_overlay``:
    ``{id: int, x, y, w, h, rotation}``. ``id`` is a sequential mark
    index; ``id_to_eid`` maps it back to the IR eid so callers can
    correlate classifications with the IR's declared type.

    Elements whose ``type`` is in ``exclude_types`` (screen root, frame
    wrappers, sentinel-like terms) are skipped — SoM shouldn't be
    asked to classify structural shells as semantic components.

    Elements absent from the walk are skipped silently (the walker
    couldn't render them; nothing to mark).
    """
    annotations: list[dict[str, Any]] = []
    id_to_eid: dict[int, str] = {}
    mark_id = 1
    for eid, elem in ir_elements.items():
        etype = (elem.get("type") or "").lower()
        if etype in exclude_types:
            continue
        walked = walk_eid_map.get(eid)
        if not walked:
            continue
        annotations.append({
            "id": mark_id,
            "x": float(walked.get("x") or 0),
            "y": float(walked.get("y") or 0),
            "w": float(walked.get("width") or 0),
            "h": float(walked.get("height") or 0),
            "rotation": float(walked.get("rotation") or 0),
        })
        id_to_eid[mark_id] = eid
        mark_id += 1
    return annotations, id_to_eid


def compute_coverage_from_types(
    expected: list[str],
    detected: list[str],
    *,
    exclude: frozenset[str] = _DEFAULT_COVERAGE_EXCLUDE,
) -> tuple[float, float, dict[str, Any]]:
    """Bag-match expected vs detected canonical-type lists.

    Returns ``(precision, recall, info)`` where:
    - ``precision = matches / max(1, |detected|)``
    - ``recall    = matches / max(1, |expected|)``
    - ``info`` carries match counts + the missing-type histogram for
      diagnostic display.

    Types in ``exclude`` are filtered from BOTH sides before matching
    (screen roots, frame wrappers, SoM sentinels).

    When ``expected`` is empty, recall returns 1.0 (skip — nothing
    to match against). Precision is computed against detected as
    usual, which correctly flags "SoM saw stuff, IR expected nothing"
    as 0 unless detected is also empty.
    """
    from collections import Counter

    exp_filtered = [t.lower() for t in expected if t and t.lower() not in exclude]
    det_filtered = [t.lower() for t in detected if t and t.lower() not in exclude]

    exp_ct = Counter(exp_filtered)
    det_ct = Counter(det_filtered)

    matches = 0
    for t, n in det_ct.items():
        matches += min(n, exp_ct.get(t, 0))

    # Diagnostic: what we expected but didn't see.
    missing: dict[str, int] = {}
    for t, n in exp_ct.items():
        deficit = n - det_ct.get(t, 0)
        if deficit > 0:
            missing[t] = deficit

    # Diagnostic: what we saw but didn't expect.
    extra: dict[str, int] = {}
    for t, n in det_ct.items():
        surplus = n - exp_ct.get(t, 0)
        if surplus > 0:
            extra[t] = surplus

    if len(exp_filtered) == 0:
        recall = 1.0
    else:
        recall = matches / len(exp_filtered)

    if len(det_filtered) == 0:
        precision = 1.0 if len(exp_filtered) == 0 else 0.0
    else:
        precision = matches / len(det_filtered)

    info = {
        "matches": matches,
        "expected_count": len(exp_filtered),
        "detected_count": len(det_filtered),
        "missing": missing,
        "extra": extra,
    }
    return precision, recall, info


def score_component_coverage(
    ir_elements: dict[str, Any],
    walk_eid_map: dict[str, Any],
    *,
    classifications: list[dict[str, Any]],
    exclude_types: frozenset[str] = _DEFAULT_COVERAGE_EXCLUDE,
    pass_threshold: float = 0.7,
) -> tuple[DimensionScore, DimensionScore]:
    """Emit ``(component_precision, component_recall)`` from IR +
    SoM-classified regions.

    ``classifications`` is the list returned by
    ``dd.classify_vision_som.classify_screen_som`` (or an equivalent
    shape from a test fixture): ``[{mark_id, canonical_type, ...}]``.
    The caller is responsible for running the SoM pass; this keeps
    the dim fast to unit-test without mocking a Claude client.

    Empty-IR case: both dims skip (1.0) — no expectations, nothing
    to measure. The caller should gate with other dims to catch
    "nothing rendered" separately.

    ``pass_threshold`` default 0.7 matches GenEval / Design2Code
    practice (~80% target; 70% is the pass band we use elsewhere).
    """
    # Expected types: each non-excluded IR element's declared type.
    expected: list[str] = []
    for eid, elem in ir_elements.items():
        etype = (elem.get("type") or "").lower()
        if etype in exclude_types:
            continue
        # Only count elements that were actually rendered (else we
        # over-penalize: if the renderer dropped an element, it's
        # already captured by coverage dim).
        if eid not in walk_eid_map:
            continue
        expected.append(etype)

    detected: list[str] = [
        (c.get("canonical_type") or "").lower()
        for c in classifications
        if c.get("canonical_type")
    ]

    if not expected and not detected:
        return (
            DimensionScore(
                name="component_precision",
                value=1.0, passed=True,
                diagnostic="no expected + no detected (dim skipped)",
            ),
            DimensionScore(
                name="component_recall",
                value=1.0, passed=True,
                diagnostic="no expected + no detected (dim skipped)",
            ),
        )

    if not expected:
        return (
            DimensionScore(
                name="component_precision",
                value=1.0, passed=True,
                diagnostic="no expected (dim skipped)",
            ),
            DimensionScore(
                name="component_recall",
                value=1.0, passed=True,
                diagnostic="no expected (dim skipped)",
            ),
        )

    precision, recall, info = compute_coverage_from_types(
        expected=expected,
        detected=detected,
        exclude=exclude_types,
    )

    def _diag(value: float, label: str, info: dict[str, Any]) -> str:
        parts = [
            f"{info['matches']}/{info['detected_count']} detected match "
            f"expected ({info['expected_count']} expected)",
        ]
        if info.get("missing"):
            miss = ", ".join(f"{k}×{v}" for k, v in list(info["missing"].items())[:3])
            parts.append(f"missing: {miss}")
        if info.get("extra"):
            ex = ", ".join(f"{k}×{v}" for k, v in list(info["extra"].items())[:3])
            parts.append(f"extra: {ex}")
        return f"{label}={value:.2f}; " + "; ".join(parts)

    return (
        DimensionScore(
            name="component_precision",
            value=precision,
            passed=precision >= pass_threshold,
            diagnostic=_diag(precision, "precision", info),
        ),
        DimensionScore(
            name="component_recall",
            value=recall,
            passed=recall >= pass_threshold,
            diagnostic=_diag(recall, "recall", info),
        ),
    )


# ---------------------------------------------------------------
# Aggregate scorer
# ---------------------------------------------------------------


def score_fidelity(
    *,
    ir_elements: dict[str, Any],
    walk_eid_map: dict[str, Any],
    walk_errors: list[dict[str, Any]],
    root_eid: str | None = None,
    vlm_score: Optional[DimensionScore] = None,
    coverage_threshold: float = 0.8,
    som_classifications: Optional[list[dict[str, Any]]] = None,
) -> FidelityReport:
    """Run all structural dimensions + optional VLM. Returns a
    ``FidelityReport`` the caller can aggregate or filter.

    ``root_eid`` enables the rootedness dimension (the tree
    actually attached to the page). Default is to infer from
    ``ir_elements`` — first element is typically the root. Pass
    explicitly when the caller has better info.

    ``vlm_score`` is expected to already be computed elsewhere —
    this module doesn't make Gemini calls. See the ``vlm``
    helpers below for a thin wrapper."""
    if root_eid is None and ir_elements:
        # Best-guess: first element (typical shape has screen-1
        # as the first key). Callers that compose their own IRs
        # should pass an explicit root_eid.
        root_eid = next(iter(ir_elements), None)

    dims = [
        score_coverage(
            ir_elements, walk_eid_map, threshold=coverage_threshold,
        ),
        score_rootedness(root_eid, walk_eid_map, walk_errors),
        score_font_readiness(walk_errors),
        score_component_child_consistency(walk_errors),
        score_leaf_type_structural(ir_elements),
        # Visual-plausibility dims — added 2026-04-21 to catch the
        # Tier-D subtree case where structural dims all pass on a
        # visually-blank output.
        score_canvas_coverage(root_eid, ir_elements, walk_eid_map),
        score_content_richness(walk_eid_map),
    ]
    # SoM-based component coverage — opt-in via precomputed
    # classifications. Caller runs the SoM pass; see
    # docs/research/scorer-calibration-and-som-fidelity.md §D2.
    if som_classifications is not None:
        prec, rec = score_component_coverage(
            ir_elements=ir_elements,
            walk_eid_map=walk_eid_map,
            classifications=som_classifications,
        )
        dims.extend([prec, rec])
    return FidelityReport(
        dimensions=dims,
        vlm_dimension=vlm_score,
    )


# ---------------------------------------------------------------
# Optional VLM dimension — deliberately thin
# ---------------------------------------------------------------


def vlm_score_via_gemini(
    client,
    *,
    screenshot_png: bytes,
    prompt: str,
    model: str = "gemini-2.5-pro",
    retries: int = 3,
) -> DimensionScore:
    """Ask Gemini to rate a rendered screenshot 1-10 against the
    prompt. Retry ``retries`` times (per
    ``feedback_vlm_transient_retries.md`` — ~30% transient error
    rate is the baseline).

    Input: PNG bytes + the original prompt.
    Output: DimensionScore in [0.0, 1.0] where 0.7 is the ≥7/10
    threshold from ``evaluation-rubric-calibration.md``.

    Not invoked by ``score_fidelity`` — callers plug this in
    only when they want the paid VLM pass.
    """
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            rubric = (
                f"On a 1-10 scale, how well does this rendered "
                f"screen match the prompt: {prompt!r}. Respond with "
                "just an integer 1-10."
            )
            response = client.generate_content(
                [rubric, {"mime_type": "image/png", "data": screenshot_png}],
                model=model,
            )
            text = (response.text or "").strip()
            # Extract the first integer 1-10 from the response.
            # Regex instead of tok.isdigit() so `score=8` or "8."
            # parse correctly — the attached punctuation used to
            # drop through to the "no valid int" branch.
            import re as _re
            match = _re.search(r"\b(10|[1-9])\b", text)
            if match is not None:
                n = int(match.group(1))
                val = n / 10.0
                return DimensionScore(
                    name="vlm_semantic",
                    value=val,
                    passed=val >= 0.7,
                    diagnostic=f"Gemini: {n}/10 — {text[:80]}",
                )
            last_error = f"no valid int 1-10 in response: {text[:80]!r}"
        except Exception as e:  # noqa: BLE001
            last_error = str(e)[:120]
    return DimensionScore(
        name="vlm_semantic",
        value=0.0,
        passed=False,
        diagnostic=f"VLM unavailable after {retries} retries: {last_error}",
    )
