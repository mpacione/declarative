# Plan — Classifier v2 (dedup + filter + per-node crops)

**Status:** execution-ready spec.
**Authored:** 2026-04-20.
**Premise:** M7.0.a v1 classifier sent every node to the API individually, sent full screens to vision with bbox lists, and didn't filter full-screen nodes. Outcome: 47% LLM↔PS agreement on the full corpus (vs 77% on the bake-off), 674 flagged rows, ~$70 spent. The user's review data is the ground truth we'll validate v2 against (266 `accept_source` decisions).

**Hypothesis:** three changes together push agreement to 80%+ and cut cost 5-8×.

---

## 1. The three changes

### 1a. Dedup before classification

**Problem:** 6,233 LLM rows on the full corpus; review data showed 674 flagged rows collapsed to 218 unique patterns via `(llm, ps, cs, name)`. Pre-classification structural signature would collapse harder — probably **5-8×** reduction in API calls.

**Dedup key:** a tuple of structural signals that, when equal across two nodes, means they're the same pattern:

```python
dedup_key = (
    node.name,                        # "Left", "image-box", "Frame 362"
    node.node_type,                   # FRAME / INSTANCE / COMPONENT
    parent.canonical_type,            # classified parent's type (or None)
    tuple(sorted(                     # child shape — e.g. (('FRAME', 2), ('TEXT', 1))
        child_type_counts.items())),
    sample_text_first_60_chars,       # "Filename", "Sign in", None
    node.component_key or "",         # Figma master key (INSTANCE nodes)
)
```

Two nodes with identical keys → same verdict. Classify one; propagate to all sci rows with the same key.

### 1b. Filter full-screen nodes

**Problem:** some depth=1 FRAMEs fill ≥ 95% of the screen's viewport — they're "canvas/root" containers, not classifiable components. They were getting sent anyway and the user skipped them.

**Filter:** add to the candidate query:
```sql
AND (n.width < s.width * 0.95 OR n.height < s.height * 0.95)
```

A node that's visually ≥95% of the screen in either dimension is a canvas. Classify as `container` via heuristic, skip LLM/vision.

### 1c. Per-node crops with spotlight

**Problem:** vision Sonnet gets a 1536×1152 screen + a bbox list and has to visually find each target. A 16×16 child is 0.01% of the pixels. Same reason the review UX was broken — solved on the human side by cropping + spotlighting.

**v2:** do the same server-side BEFORE the API call:
- Crop to `(bbox + 40px padding)` from the screen image.
- Dim pixels outside the bbox to 45% brightness.
- Stroke the bbox edge (magenta 3px + white 5px halo).
- Upscale tiny crops to 400px min-side for legibility.

Send ONE image per node (or per dedup group representative) to Sonnet instead of one screen + N bboxes.

---

## 2. Architecture

### New modules

- `dd/classify_dedup.py` — `dedup_key(node, context) → tuple` + `group_candidates(candidates) → dict[key, list[candidate]]`.
- `dd/classify_vision_crop.py` — the crop pipeline extracted from `scripts/m7_review_server.py` (which already works). Reusable from classifier + review server.

### Modified modules

- `dd/classify_vision_batched.py`:
  - `_fetch_unclassified_for_screen` gains a `skip_full_screen=True` param (width/height 95% filter).
  - New function `classify_crops(conn, candidates, client, crops: dict[node_id, bytes]) → list[dict]` — accepts pre-cropped images; no bbox-list-inside-screen trick.
  - Legacy `classify_batch` retained for v1 compat until cutover.
- `dd/classify.py`:
  - `run_classification(three_source=True, classifier_v2=True)` — new flag.
  - New orchestrator path: fetch candidates → compute dedup keys → classify one representative per key → propagate verdicts → link parents → extract skeleton → consensus.

### Flag-gated rollout

`dd classify --classifier-v2` opts in. Default stays v1 until the bake-off validates. Everything new is additive — no breaking changes to the v1 code path.

---

## 3. Validation plan (before spending real $)

### 3a. Bake-off on 10 screens (~$1)

Pick the original bake-off set (screens 150-159). Run v2; compare:

| Metric | v1 baseline (bake-off v2 report) | v2 target |
|---|---|---|
| LLM↔PS agreement | 76.9% | ≥85% |
| PS↔CS agreement | (not measured, but ~PS v1) | ≥85% |
| API calls | 10 × (LLM + PS + CS) = ~30 | ≤50% of v1 via dedup |
| Cost | ~$0.50 | ≤$0.25 |
| Wall time | ~45s | ≤30s |

### 3b. Ground-truth validation against user review data

We have **266 `accept_source` decisions** where you explicitly picked LLM/PS/CS as the right answer. For each of those:
- Fetch the new v2 canonical_type for the same node.
- Compare: does v2 match the source you picked in review?

A well-calibrated v2 matches your review decision >80% on these 266 rows. If lower, classifier v2 is wrong. If higher, it's aligned with human judgment where v1 needed help.

### 3c. Additional: override row validation

The 93 `override` decisions are harder cases — user picked a type none of the three sources found. For each:
- v2 probably won't match the user (override target not in the three-source vote space).
- But we can flag how MANY of these v2 would have caught via better classification.

### Gate criteria

Full corpus re-run IF:
1. v2 LLM↔PS agreement ≥ 80% on bake-off (10-point lift over v1's baseline).
2. v2 matches ≥ 70% of `accept_source` review decisions on those 10 screens.
3. Cost ≤ 60% of v1 per-screen.

---

## 4. Implementation sequence (TDD)

Each step is a commit; tests precede code per CLAUDE.md.

**Step 1 — `classify_dedup.py`** (pure function + unit tests).
- Tests: identical nodes → same key; different names → different keys; None parent → handles gracefully; duplicate sample_text stripped to 60 chars.

**Step 2 — full-screen filter** (one-line SQL change + test).
- Test: node equal to its screen's width is excluded; node at 94% is included.

**Step 3 — `classify_vision_crop.py`** (extract from server; unit tests against fixture PNG).
- Tests: bbox inside screen → crops to padded region; bbox out of bounds → handled; tiny node → upscaled.

**Step 4 — `classify_crops` in vision_batched** (takes pre-cropped images).
- Tests: mock client receives one image per node; returns parsed classifications.

**Step 5 — Orchestrator v2** (dedup → classify representative → propagate).
- Tests: 3 duplicate nodes + 1 unique → 2 classify calls (1 group + 1 unique); all 4 rows get verdicts.

**Step 6 — CLI flag** (`--classifier-v2` routes to the new orchestrator).

**Step 7 — Bake-off script** (`scripts/m7_bakeoff_v2.py`).
- Runs v1 + v2 on the same 10 screens.
- Emits `render_batch/m7_bakeoff_v2_report.md` with agreement rates + review-ground-truth match + cost.

**Step 8 — Full corpus run if gate passes.**

---

## 5. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Dedup key too loose → misgroups dissimilar nodes | Start with the strict 6-tuple key; tune by checking "surprising-group" cases manually. |
| Dedup key too tight → no dedup actually happens | Check group count on dry-run; if equal to candidate count, key's too specific. |
| Per-node crops balloon API calls even after dedup | Dedup IS the cost control. If dedup ratio is weak, either fix it or fall back to batched crops (one call carries N crops). |
| Spotlight crops confuse the model vs helping | First 10-screen run will show; if agreement DROPS, disable spotlight, keep crops. |
| Vision API becomes more expensive per-call (1 image per request vs multiple nodes-per-screen) | Anthropic pricing is per-token not per-request; image tokens scale with area. Cropped 400×400 images are much smaller than full 1536×1152 screens → usually CHEAPER per call. |
| v2 disagrees with user reviews more than v1 | Gate criterion catches this; don't scale if v2 ≥ user-review match rate isn't met. |

---

## 6. Out of scope for classifier v2

- Rule v2 consensus (separate plan, `docs/plan-m7-step12-rule-v2.md`). Runs on whatever sources v2 produces.
- CLAY/ARIA alignment (separate plan, `docs/plan-m7-taxonomy-alignment.md`). Prompt-language alignment, not architectural.
- M7.0.b slot derivation. Needs classifier output; stays downstream.
- Parallelization (`docs/plan-ingest-performance.md`). Can layer on after v2 ships.
- Changing the three-source architecture itself (LLM + PS + CS). v2 is per-source improvements, not a rethink.

---

## 7. Acceptance

Classifier v2 ships when:
1. All 7 steps land (dedup, filter, crop, classify_crops, orchestrator, CLI, bake-off).
2. Bake-off agreement ≥ 85% LLM↔PS and ≥ 70% match against user review decisions.
3. 204/204 corpus parity preserved (classifier v2 touches DB writes but not render path).
4. Full corpus re-run completes; flagged count drops from 674 to ≤ 250 (≥62% reduction).
5. Test suite adds: dedup tests, filter tests, crop tests, orchestrator tests — all green.

When all five hit, v2 becomes the classifier default. v1 stays in the code under `--classifier-v1` for one milestone before deletion.
