"""Three-source consensus computation (M7.0.a rule v1).

Per plan-synthetic-gen.md §5.1.a, classification cascade persists
three independent verdicts per node: LLM text, vision per-screen (PS),
and vision cross-screen (CS). The raw verdicts never collapse — this
module computes a canonical_type from them via a naive rule, and the
rule can change without re-classifying because the inputs are in the
DB.

Rule v1 (maximally conservative):

    if all three agree         → commit, "unanimous"
    elif any is `unsure`       → `unsure`, "any_unsure"         (flag)
    elif 2/3 agree             → commit majority, "majority"
    else all differ            → `unsure`, "three_way_disagreement" (flag)

Extended branches cover degraded input (one or two sources present,
e.g., vision failed or hasn't run) with deterministic fallbacks:

    all None                    → (None, "no_sources", flag)
    one source, non-unsure      → pass through, "single_source"
    one source, unsure          → unsure, "single_source" (flag)
    two sources, agree          → commit, "two_source_unanimous"
    two sources, any unsure     → unsure, "any_unsure" (flag)
    two sources, disagree       → unsure, "two_way_disagreement" (flag)

Rule v2 (bias-aware overrides) ratchets in after the full corpus run
exposes real disagreement patterns; it's a drop-in replacement that
reads the same persisted columns.
"""

from __future__ import annotations

UNSURE = "unsure"


def compute_consensus_v1(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
) -> tuple[str | None, str, bool]:
    """Apply rule v1 to three source verdicts.

    Returns ``(canonical_type, consensus_method, flagged_for_review)``.

    Arguments may be ``None`` when a source didn't produce a verdict
    (stage skipped, model failed to emit a parseable tool_use, network
    error, etc.). Rule v1 doesn't interrogate confidence — rule v2
    will.
    """
    verdicts = [llm_type, vision_ps_type, vision_cs_type]
    present = [v for v in verdicts if v is not None]

    if not present:
        return (None, "no_sources", True)

    if len(present) == 1:
        only = present[0]
        return (only, "single_source", only == UNSURE)

    if len(present) == 2:
        a, b = present
        if a == UNSURE or b == UNSURE:
            return (UNSURE, "any_unsure", True)
        if a == b:
            return (a, "two_source_unanimous", False)
        return (UNSURE, "two_way_disagreement", True)

    # Three sources present — the canonical rule v1 branches. Order
    # matters: `any_unsure` is checked FIRST so "unanimous on unsure"
    # still flags for review. `unsure` as a final type always means
    # "needs review"; treating it as an agreement would silently bury
    # low-confidence cases.
    a, b, c = present
    if UNSURE in (a, b, c):
        return (UNSURE, "any_unsure", True)
    if a == b == c:
        return (a, "unanimous", False)
    if a == b or a == c:
        return (a, "majority", False)
    if b == c:
        return (b, "majority", False)
    return (UNSURE, "three_way_disagreement", True)
