"""Three-source consensus computation (M7.0.a rule v1, rule v2).

Per plan-synthetic-gen.md §5.1.a, classification cascade persists
three independent verdicts per node: LLM text, vision per-screen (PS),
and vision cross-screen (CS). The raw verdicts never collapse — this
module computes a canonical_type from them via a rule, and the rule
can change without re-classifying because the inputs are in the DB.

Rule v1 (maximally conservative):

    if all three agree         → commit, "unanimous"
    elif any is `unsure`       → `unsure`, "any_unsure"         (flag)
    elif 2/3 agree             → commit majority, "majority"
    else all differ            → `unsure`, "three_way_disagreement" (flag)

Extended branches cover degraded input (one or two sources present,
e.g., vision failed or hasn't run) with deterministic fallbacks.

Rule v2 (weighted, data-driven):

    LLM = 1 vote, Vision PS = 1 vote, Vision CS = 2 votes.

A verdict wins if its total weight strictly exceeds the next highest;
ties still flag for review. The weight came from the full-corpus
accuracy report on 2026-04-20: against 266 user `accept_source`
decisions, Vision CS matched 67.6% alone vs 55.7% for LLM and 51.0%
for PS. Doubling CS's weight let CS outvote an LLM+PS majority on
three-way disagreements — where cross-screen comparison is the
source with the most context. Empirical lift: +6.4 pts overall match
rate on the 236 matched-denominator sample (66.1% → 72.5%).

Rule v1 remains available for rollback. Either rule can be re-applied
to the DB without re-classifying because llm_type / vision_ps_type /
vision_cs_type are persisted columns.
"""

from __future__ import annotations

from collections import Counter

UNSURE = "unsure"

# Rule v2 source weights. Derived from the 2026-04-20 full-corpus
# run: Vision CS was ~17 pts more accurate than PS/LLM on the
# user's `accept_source` review corpus. If future reviews shift
# this relative accuracy, rebalance here and re-apply.
V2_WEIGHTS = {"llm": 1, "vision_ps": 1, "vision_cs": 2}


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


def compute_consensus_v2(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
) -> tuple[str | None, str, bool]:
    """Apply rule v2 (weighted) to three source verdicts.

    Weights in ``V2_WEIGHTS``. A verdict wins if its total weight is
    strictly greater than the next highest; ties flag. ``unsure``
    short-circuits — matches rule v1's "any unsure means needs review."

    Extended branches for degraded inputs (≤2 sources present) mirror
    v1's deterministic fallbacks so a caller can swap rules safely.
    """
    verdicts = {
        "llm": llm_type,
        "vision_ps": vision_ps_type,
        "vision_cs": vision_cs_type,
    }
    present = {k: v for k, v in verdicts.items() if v is not None}

    if not present:
        return (None, "no_sources", True)

    if any(v == UNSURE for v in present.values()):
        if len(present) == 1:
            return (UNSURE, "single_source", True)
        return (UNSURE, "any_unsure", True)

    if len(present) == 1:
        only = next(iter(present.values()))
        return (only, "single_source", False)

    votes: Counter[str] = Counter()
    for source, ctype in present.items():
        votes[ctype] += V2_WEIGHTS[source]

    top = votes.most_common()
    winner_type, winner_votes = top[0]

    if len(top) == 1:
        # All present sources picked the same type.
        method = "unanimous" if len(present) == 3 else "two_source_unanimous"
        return (winner_type, method, False)

    runner_up_votes = top[1][1]
    if winner_votes > runner_up_votes:
        return (winner_type, "weighted_majority", False)
    return (UNSURE, "weighted_tie", True)
