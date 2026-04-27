"""Three-source consensus computation (M7.0.a rule v1, rule v2, rule v3).

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

Rule v2 (source-weighted):

    LLM = 1 vote, Vision PS = 1 vote, Vision CS = 2 votes.

A verdict wins if its total weight strictly exceeds the next highest;
ties still flag for review. Derived from a biased 266-review sample
early in the project and later found to over-fit (see rule-v3). Kept
available for rollback.

Rule v3 (per-type calibrated):

    Each (source, predicted_type) pair has its own weight derived
    empirically from `accept_source` review history:
    ``weight(src, T) = (accepts + α) / (predictions + 2α)``
    with α=1 Laplace smoothing so low-sample types don't explode.

    Voting sums weights per candidate type. Strict winner commits as
    "calibrated_majority"; tie flags as "calibrated_tie". ``unsure``
    from any source short-circuits to "any_unsure" (preserved from
    v1/v2). Missing weights default to 0.5.

    Rule v3 is the right long-term answer: it learns per-type source
    accuracy from reviews, so the consensus rule improves as the
    review corpus grows. Uniform weights degenerate to rule v1.

Rules v1/v2/v3 can all be re-applied to the DB without re-classifying
because llm_type / vision_ps_type / vision_cs_type are persisted
columns. Swap via ``apply_consensus_to_screen(..., rule=...)``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

UNSURE = "unsure"

# Rule v2 source weights. Derived from the 2026-04-20 full-corpus
# run: Vision CS was ~17 pts more accurate than PS/LLM on the
# user's `accept_source` review corpus. Later found to over-fit.
# 2026-04-21: vision_som added as 4th source at weight 2 (equal to
# CS). Adjudication on full-corpus showed SoM winning 62-69% of
# head-to-head disagreements against PS, so it earns tied-top
# weight with CS. Calibrated weights (rule v3) are the right long-
# term answer; this is a sane starting point.
V2_WEIGHTS = {
    "llm": 1, "vision_ps": 1, "vision_cs": 2, "vision_som": 2,
}

# Rule v3 defaults. Laplace smoothing strength; higher α pulls
# low-sample weights harder toward 0.5.
V3_SMOOTHING_ALPHA = 1.0
# Sources without weight data fall back to this neutral weight.
V3_DEFAULT_WEIGHT = 0.5

# Typed alias: a (source, predicted_type) → weight lookup.
WeightsTable = dict[tuple[str, str], float]


def compute_consensus_v1(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
    vision_som_type: str | None = None,
) -> tuple[str | None, str, bool]:
    """Apply rule v1 to up to four source verdicts.

    Returns ``(canonical_type, consensus_method, flagged_for_review)``.

    Arguments may be ``None`` when a source didn't produce a verdict
    (stage skipped, model failed to emit a parseable tool_use, network
    error, etc.). ``vision_som_type`` is the newest source and
    defaults to None so pre-SoM callers / tests keep working.

    Rule v1 with N sources (plurality, tie flags):
      - 0 present → flag (no sources)
      - any unsure → flag (any_unsure)
      - 1 present → single_source (flag iff unsure)
      - 2+ present → plurality wins IFF strictly greater than
        runner-up; equal top counts flag as two_way / multi_way
        disagreement.
    """
    verdicts = {
        "llm": llm_type,
        "vision_ps": vision_ps_type,
        "vision_cs": vision_cs_type,
        "vision_som": vision_som_type,
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

    counts = Counter(present.values())
    ranked = counts.most_common()
    winner, winner_count = ranked[0]

    if len(ranked) == 1:
        method = "unanimous" if len(present) >= 3 else "two_source_unanimous"
        return (winner, method, False)

    runner_up_count = ranked[1][1]
    if winner_count > runner_up_count:
        method = "majority" if len(present) >= 3 else "two_source_unanimous"
        return (winner, method, False)

    # Tie at the top — disagree. Name the method by source count so
    # downstream reporting can distinguish two-way from four-way.
    disagreement_methods = {
        2: "two_way_disagreement",
        3: "three_way_disagreement",
        4: "four_way_disagreement",
    }
    return (
        UNSURE,
        disagreement_methods.get(len(present), "multi_way_disagreement"),
        True,
    )


def compute_consensus_v2(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
    vision_som_type: str | None = None,
) -> tuple[str | None, str, bool]:
    """Apply rule v2 (weighted) to up to four source verdicts.

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
        "vision_som": vision_som_type,
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


def compute_consensus_v3(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
    vision_som_type: str | None = None,
    *,
    weights: WeightsTable,
) -> tuple[str | None, str, bool]:
    """Apply rule v3 (per-type calibrated) to up to four source
    verdicts.

    Each ``(source, predicted_type)`` pair has a weight looked up from
    ``weights``. Missing entries default to ``V3_DEFAULT_WEIGHT``. If
    any source says ``unsure`` the row flags immediately (matches v1/v2
    conservatism on abstentions).

    Winner commits as "calibrated_majority" when it strictly outweighs
    the runner-up; ties flag as "calibrated_tie". If no sources are
    present, return ``(None, "no_sources", True)``.
    """
    verdicts = {
        "llm": llm_type,
        "vision_ps": vision_ps_type,
        "vision_cs": vision_cs_type,
        "vision_som": vision_som_type,
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

    votes: dict[str, float] = {}
    for source, ctype in present.items():
        w = weights.get((source, ctype), V3_DEFAULT_WEIGHT)
        votes[ctype] = votes.get(ctype, 0.0) + w

    sorted_votes = sorted(votes.items(), key=lambda x: -x[1])
    winner_type, winner_w = sorted_votes[0]

    if len(sorted_votes) == 1:
        # All present sources picked the same type.
        method = "unanimous" if len(present) == 3 else "two_source_unanimous"
        return (winner_type, method, False)

    runner_up_w = sorted_votes[1][1]
    if winner_w > runner_up_w:
        return (winner_type, "calibrated_majority", False)
    return (UNSURE, "calibrated_tie", True)


def build_calibrated_weights(
    reviews: list[dict[str, Any]],
    *,
    alpha: float = V3_SMOOTHING_ALPHA,
) -> WeightsTable:
    """Compute rule-v3 weights from review history.

    Each review is expected to be a dict with keys:
      - ``decision_type`` (only ``accept_source`` rows contribute)
      - ``source_accepted`` (``llm`` / ``vision_ps`` / ``vision_cs``)
      - ``llm_type``, ``vision_ps_type``, ``vision_cs_type``

    For each ``(source, predicted_type)`` pair seen in the reviews:
      - ``predictions``: number of times that source predicted that type
      - ``accepts``: subset where the user's ``source_accepted`` was
        this source (i.e., the user ratified this source's verdict).

    Smoothed weight: ``(accepts + α) / (predictions + 2α)``. At α=1 a
    single confirmation yields 2/3; a single rejection yields 1/3. By
    10 samples the smoothing is mostly washed out.

    Reviews with other ``decision_type`` values are ignored — only
    direct acceptances carry enough signal to update the weights.
    Missing source verdicts (None) on a given review are also
    ignored.
    """
    predictions: dict[tuple[str, str], int] = {}
    accepts: dict[tuple[str, str], int] = {}

    for r in reviews:
        if r.get("decision_type") not in (None, "accept_source"):
            continue
        src_accepted = r.get("source_accepted")
        if src_accepted not in ("llm", "vision_ps", "vision_cs"):
            continue
        for src in ("llm", "vision_ps", "vision_cs"):
            pred_type = r.get(f"{src}_type")
            if not isinstance(pred_type, str) or pred_type == UNSURE:
                continue
            key = (src, pred_type)
            predictions[key] = predictions.get(key, 0) + 1
            if src == src_accepted:
                accepts[key] = accepts.get(key, 0) + 1

    weights: WeightsTable = {}
    for key, total in predictions.items():
        a = accepts.get(key, 0)
        weights[key] = (a + alpha) / (total + 2 * alpha)
    return weights
