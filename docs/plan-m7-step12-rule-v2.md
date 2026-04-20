# Plan — M7.0.a Step 12: Consensus Rule v2 (bias-aware overrides)

**Status:** spec, deferred — blocks on full disagreement-report data from Step 9 + override patterns from Step 11 manual review.
**Authored:** 2026-04-19 (autonomous draft while user is away).
**Trigger to revisit:** after the manual review sprint exposes ≥50 reviewed rows, OR after the full disagreement report shows clear pattern clusters.

---

## 1. Why rule v2

Rule v1 (shipping) is intentionally conservative: any source returning `unsure` flags the row, and 3-way disagreement flags. The dry-run mid-cascade snapshot showed:

- LLM↔PS agreement: **47.8%** (much lower than the bake-off's 76.9%)
- PS over-calls `container` and `image`; LLM over-calls `icon` and `card`
- PS hedges with `unsure` (~140 rows) where LLM commits

Rule v1 will flag the majority of LLM rows for review, which doesn't scale. Rule v2 encodes the SYSTEMATIC biases observed in the data so the consensus chooses correctly without human intervention on common patterns, leaving genuine ambiguity to Step 11 review.

**Non-goal:** improving model accuracy. Rule v2 doesn't make any source MORE accurate — it picks the right source per pattern.

## 2. Drop-in replacement contract

Rule v2 replaces `compute_consensus_v1` in `dd/classify_consensus.py` with `compute_consensus_v2`. Same signature, same return shape:

```python
def compute_consensus_v2(
    llm_type: str | None,
    vision_ps_type: str | None,
    vision_cs_type: str | None,
    *,
    llm_confidence: float | None = None,
    vision_ps_confidence: float | None = None,
    vision_cs_confidence: float | None = None,
) -> tuple[str | None, str, bool]:
    """Returns (canonical_type, consensus_method, flagged)."""
```

The orchestrator's `apply_consensus_to_screen` reads `llm_confidence`, `vision_ps_confidence`, `vision_cs_confidence` from the row and passes them through. Rule v2 uses confidence as a tiebreaker.

**Critical invariant:** rule v2 reads ONLY the persisted `llm_type` / `vision_ps_type` / `vision_cs_type` (+ confidences). No re-classification. Re-running consensus is `apply_consensus_to_screen` over every row → seconds, no API cost.

## 3. Rule v2 override patterns (proposed, pending data)

Each override is a check that runs BEFORE the rule-v1 logic. If the override matches, it returns its verdict and skips v1.

### Override A — "discount cross-screen-alone container"

The bake-off showed CS systematically regresses to `container` on header / status-bar / chrome nodes when the cross-screen pattern is "lots of similar-shaped frames." LLM + PS often agree on the specific type (e.g., `header`, `status_bar`). Rule v2:

```
if vision_cs_type == "container"
   and llm_type == vision_ps_type
   and llm_type not in ("container", "unsure"):
    return (llm_type, "v2_cs_container_drift", False)
```

Expected impact: drops a lot of currently-flagged rows where CS dragged the consensus down.

### Override B — "honor cross-screen-alone skeleton on empty grids"

Cross-screen vision sees the WHOLE screen and can detect "this is the loading-skeleton variant of the same screen." LLM + PS see only the local node and call it `image` or `container`. CS calling `skeleton` while others disagree is usually right.

```
if vision_cs_type == "skeleton"
   and llm_type in ("image", "container")
   and vision_ps_type in ("image", "container", "unsure"):
    return (vision_cs_type, "v2_cs_skeleton_signal", False)
```

### Override C — "PS vision wins on visual-distinctive types"

For types where the visual signal is unambiguous (icon, image, divider), trust PS over LLM when they disagree:

```
VISUAL_DISTINCTIVE = {"icon", "image", "divider", "switch", "checkbox", "radio"}
if vision_ps_type in VISUAL_DISTINCTIVE
   and llm_type != vision_ps_type
   and (vision_ps_confidence or 0) >= 0.85:
    return (vision_ps_type, "v2_ps_visual_specific", False)
```

The dry-run showed LLM under-calls `image` 3.6×; this override addresses that.

### Override D — "LLM wins on text-content-distinctive types"

For types where the SAMPLE TEXT is the primary signal (heading, button labels, links), trust LLM over vision when they disagree:

```
TEXT_DISTINCTIVE = {"heading", "button", "link", "tabs", "navigation_row"}
if llm_type in TEXT_DISTINCTIVE
   and vision_ps_type != llm_type
   and (llm_confidence or 0) >= 0.85:
    return (llm_type, "v2_llm_text_specific", False)
```

### Override E — "confidence tiebreaker on 3-way disagreement"

When all three differ AND none of overrides A–D match, pick the highest-confidence verdict:

```
if all three differ:
    candidates = [(llm_type, llm_confidence),
                  (vision_ps_type, vision_ps_confidence),
                  (vision_cs_type, vision_cs_confidence)]
    candidates = [(t, c) for t, c in candidates
                  if t is not None and t != "unsure"
                  and c is not None]
    if candidates:
        winner = max(candidates, key=lambda x: x[1])
        if winner[1] >= 0.85:
            return (winner[0], "v2_confidence_tiebreaker", False)
    # Fall through to v1's three_way_disagreement (flagged).
```

### Override F — "single source unsure → still flag"

Rule v1's `single_source` doesn't flag when type isn't `unsure`. But a single source verdict (e.g., LLM only, no vision) on a low-confidence verdict is risky. Rule v2:

```
if vision_ps_type is None and vision_cs_type is None:
    if llm_type == "unsure" or (llm_confidence or 0) < 0.85:
        return ("unsure", "v2_single_low_confidence", True)  # flag
    return (llm_type, "single_source", False)
```

## 4. Validation method

Before shipping rule v2 to production, validate against the **manual review data** (Step 11 outputs):

1. Take the set of reviewed rows (from `classification_reviews` where `decision_type` IN `{accept_source, override}` and `decided_by='human'`).
2. For each reviewed row, compare:
   - The human's chosen `decision_canonical_type`
   - Rule v1's prediction (already in the DB as `canonical_type`)
   - Rule v2's prediction (compute fresh from the persisted columns)
3. Metrics:
   - **Agreement rate v1 vs human:** `% of reviewed rows where v1 == human`.
   - **Agreement rate v2 vs human:** `% where v2 == human`.
   - **Flagged-rows reduction:** how many fewer rows v2 flags vs v1.

Rule v2 ships when:
- Agreement rate ≥ rule v1's agreement (we don't regress).
- Flagged rows reduced by ≥ 50%.

If those bars aren't met, the override patterns need adjustment based on which they got wrong.

## 5. Migration

After rule v2 lands:

```bash
# 1. Update consensus_method values for every row.
.venv/bin/python3 -m scripts.m7_recompute_consensus --db ...
# Emits a diff: how many rows changed canonical_type / flagged status.

# 2. Re-render the disagreement report on the new state.
.venv/bin/python3 -m scripts.m7_disagreement_report --db ... --out ...

# 3. Re-render the review-index HTML so flagged rows reflect v2.
.venv/bin/python3 -m dd classify-review-index --out ...
```

`scripts/m7_recompute_consensus.py` is a new helper that walks every screen and calls `apply_consensus_to_screen` again — no API cost, just SQL.

## 6. Open questions (resolve when data lands)

- Should rule v2 be opt-in (`--rule v2`) or replace v1 entirely? Recommend opt-in initially; promote to default after agreement metrics hit.
- The `VISUAL_DISTINCTIVE` and `TEXT_DISTINCTIVE` sets are guesses based on the dry-run + bake-off observations. Real data may show different splits.
- Does rule v2 need a "training set" of human reviews to fit thresholds (the 0.85 confidence cutoffs)? Or are those reasonable a priori? Recommend: ship at 0.85, tune after the first 100 reviews if agreement is poor.

## 7. Acceptance bar

Rule v2 is shippable when:

- All Step 11 reviewed rows that touched a v2 override pattern: ≥80% agree with human.
- Flagged-rows count: ≥50% reduction vs v1 on the same data.
- 204/204 corpus parity preserved (consensus rule doesn't touch the renderer).
- 100% of `dd/classify_consensus.py` tests pass after porting v1 → v2 + adding override-specific tests.

When all four hit green, rule v2 becomes the default consensus rule for M7.0.a.
