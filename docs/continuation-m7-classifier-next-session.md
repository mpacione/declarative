# Continuation — M7 classifier, post-2026-04-21 session

**Revised**: 2026-04-21. Supersedes the 2026-04-20 draft.

---

## Where we landed

**Branch**: `v0.3-integration`
**Head commit**: `0f4d660` feat(consensus): SoM as 4th source in rule v1/v2/v3 (weight 2)
**Live DB**: `Dank-EXP-02.declarative.db`. Backup from just before
the full rerun:
`Dank-EXP-02.declarative.pre-full-rerun-20260421-012543.bak.db`.

### Shipped this session (2026-04-21)

| Commit | Summary |
|---|---|
| `cfbd2ff` | SoM label anchored to rotated TL, not AABB TL |
| `1a06ff9` | Tighter dedup (drop sample_text, cross-screen in bake-off, Frame-NNN normalization) |
| `81b3ce3` | Plugin render-toggle + checkerboard for self-hidden nodes |
| `0c4e4e5` | Soften rule 3 + add SoM prompt rules 7a / 8 / 9 / 10 |
| `822c24e` | +3 catalog types (magnifier / mouse_cursor / coach_mark = 65 total) |
| `52e3f1c` | Plugin retry + SoM verdict persistence (`--persist-som`) |
| `28ff077` | +3 catalog types (keyboard / control_box / text_cursor = 68) |
| `953b941` | +13 catalog types from Material 3 / Apple HIG audit (81 total) |
| `2d42d03` | SoM as 4th source in `classify_v2.py` pipeline |
| `775d9f3` | `--rerun` / `force_reclassify` + UPSERT (preserves reviews) |
| `e1bae1b` | Fix CLI summary KeyError for classifier_v2 |
| `0f4d660` | Consensus rule v1/v2/v3 accept SoM; V2_WEIGHTS["vision_som"]=2 |

### Pipeline state

- **Catalog: 81 types.** Added this session: magnifier, mouse_cursor,
  coach_mark, keyboard, control_box, text_cursor, sidebar, toolbar,
  bottom_sheet, color_picker, color_swatch, ruler, stepper_input,
  banner, snackbar, action_sheet, progress_ring, eyedropper,
  edit_menu. Naming collision: existing `stepper` kept (flow
  progress); new numeric +/- is `stepper_input`.

- **4-source classify_v2 pipeline**. LLM + PS + CS + SoM all run on
  the same deduped rep set; Pass 9 writes all four verdicts to
  members via `_propagate_vision_to_members`.

- **Plugin render-toggle shipped** for self-hidden nodes
  (`dd/plugin_render.py` + `dd/checkerboard.py`). One retry on
  transient bridge errors with 3s backoff. Falls through to
  dedup-twin / LLM-text cascade when plugin unreachable.

- **`--rerun` flag** (`dd classify --classifier-v2 --rerun`)
  re-classifies against the current catalog without destroying
  classification_reviews. UPSERT on `(screen_id, node_id)`.

- **Rule v2 REVIVED** with SoM=2 (equal to CS). Final↔SoM jumped
  43% → **60.9%** on the post-rerun consensus re-apply.

### Live-DB metrics (end of session)

- 49,670 sci rows (formal 27,724 · heuristic 15,324 · llm 6,622)
- 6,622 LLM rows all have four per-source verdicts populated
- 913 `weighted_tie` rows flagged for review (4-source equal-evidence
  disagreement — correct flag behaviour)
- Classification_reviews table: empty (wiped in some pre-session
  action, not by the rerun)

### Full-corpus rerun wall time / cost

- ~27 min, dominated by PS (5 min) + CS (5 min) + SoM (3 min) +
  plugin prefetch with retries (~10 min on slow screens). ~$5-7 API.

---

## What's next (in priority order)

### 1. Adjudicate the 913 weighted_ties

Spot-check a random sample of 20-30 to validate the tie rate is
tolerable. If SoM's verdict is right on most, consider weight=3
for SoM to break more ties in its favor. If the ties are genuinely
ambiguous (human can't decide), leave them flagged.

Tool: `.venv/bin/python3 -m scripts.som_adjudicate --port 8766
--results <bake-off JSONL>`.

### 2. Audit the 10 never-reaching types

These reached 0 instances across all 4 sources on the full-corpus
run: sidebar, ruler, stepper_input, snackbar, action_sheet,
progress_ring, eyedropper, edit_menu, mouse_cursor, coach_mark.

Two hypotheses:
- **Genuinely absent** from Dank → remove from catalog to keep the
  constrained-decoding enum focused.
- **Present but missed** → add prompt visual-pattern rules (like
  rules 7-10 for control_point / magnifier / keyboard / text_cursor).

To test: screenshot sample of 20 Dank screens, manually scan for each
type, note presence.

### 3. Build rule v3 calibration from accumulated adjudications

We have ~130 judgments across multiple rounds (276-285, 286-295,
160-189, FULL) in `render_batch/som_adjudication_*.jsonl`. Convert
to `classification_reviews` rows (or similar), then run
`scripts/calibrate_consensus.py` to derive per-(source, type)
weights. Replace the hand-set SoM=2 with empirically calibrated
weights.

### 4. Bake-off validation run post-v2-revival

Spot-adjudicate 20-30 cases that changed between Final↔SoM 43% and
61%. Confirm the consensus shift is positive, not noise.

### 5. Consider weight=3 for SoM if adjudications still favor it

If #1 shows SoM winning >70% of remaining ties, bump weight.
`V2_WEIGHTS = {"llm": 1, "vision_ps": 1, "vision_cs": 2, "vision_som": 3}`.

---

## Known-good commands

```bash
# Full classifier rerun against current catalog (preserves reviews):
.venv/bin/python3 -m dd classify \
    --db Dank-EXP-02.declarative.db \
    --llm --vision --classifier-v2 --rerun

# Re-apply consensus only (no re-classification):
.venv/bin/python3 -c "
from dd.db import get_connection
from dd.classify import apply_consensus_to_screen
conn = get_connection('Dank-EXP-02.declarative.db')
for sid in [r[0] for r in conn.execute(
    'SELECT DISTINCT screen_id FROM screen_component_instances '
    \"WHERE classification_source='llm'\")]:
    apply_consensus_to_screen(conn, sid, rule='v2')
conn.commit()"

# SoM-only bake-off (~90s, small subset):
.venv/bin/python3 -m scripts.bakeoff_som \
    --db Dank-EXP-02.declarative.db \
    --screens 276,277,278,279,280 --workers 4

# Adjudicator on bake-off results:
.venv/bin/python3 -m scripts.som_adjudicate \
    --port 8766 \
    --results render_batch/bakeoff_som_FULL_v2_results.jsonl
```

## Test baseline

- 480 tests green across classify / catalog / crop / dedup /
  bakeoff / plugin_render / checkerboard / som / consensus

## Cross-references

- `project_m7_classifier_v2.md` — full project memory
- `feedback_som_weight_2.md`, `feedback_plugin_render_toggle.md`,
  `feedback_upsert_preserves_reviews.md`,
  `feedback_prompt_rules_as_priors.md`,
  `feedback_taxonomy_research_upfront.md` — session's lessons
