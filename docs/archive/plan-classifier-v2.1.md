# Plan — Classifier v2.1 (Tier-1 + Tier-2 accuracy stack)

**Status:** execution-ready.
**Authored:** 2026-04-20.
**Premise:** v2 bake-off hit 82.1% LLM↔PS on easy screens (+5.2 over v1's 76.9%). Full-corpus extrapolation lands ~55-65%. To reach 80%+ corpus-wide we stack 5 low-effort changes + 2 medium-effort changes, each targeting a specific failure mode from the v1 disagreement report.

---

## 1. Failure-mode → fix mapping

Primary v1 failures (from `render_batch/disagreement_report.md` + the review sprint):

| Failure pattern | Root cause | v2.1 fix |
|---|---|---|
| Top 3 clusters are `unsure` from PS | Vision misses small decorative elements | Scale-2 crops + parent outlines (Phase D) |
| 29× tooltip / 5× control-point / "icon button" typo | Catalog missing or not normalized | Catalog expansion (Phase A) |
| LLM over-calls `icon` | Text-only can't distinguish glyph from icon container | Parent/sibling context in prompt (Phase C) |
| `bottom_nav` vs `navigation_row` confusion | Synonyms in catalog | Catalog normalization (Phase A) |
| "Hard" screens drop from 77%→47% | Prompts don't leverage corpus patterns | Few-shot examples from reviews (Phase B) |
| Ambiguous mid-confidence rows flagged | No retry path | Rejection sampling (Phase E) |

---

## 2. Phase A — Catalog normalization

### Why foundational

The catalog is the IR's noun vocabulary. Classifier prompts, synthetic gen, verifier hints, dataset exports all consume it. A normalized catalog pays dividends everywhere; an undersized one forces the model into wrong-neighbor picks.

### Shape of a normalized entry

Current `component_type_catalog` has: `canonical_name`, `behavioral_description`, `aliases`, `variant_axes`, `category`. v2.1 adds/enriches:

```python
{
    "canonical_name": "tooltip",
    "category": "overlay",                        # closed enum
    "behavioral_description": (
        "Transient floating annotation that appears on hover/focus "
        "to explain the affordance or state of another element. "
        "Contains short text; points at its anchor via an arrow or "
        "nearby position."
    ),
    "aliases": ["tooltip", "hint", "popover-info"],  # CLAY + ARIA +
                                                     # project-local
    "disambiguation": [
        "NOT a dialog — dialogs are modal and require action",
        "NOT a popover — popovers hold interactive content",
        "NOT a toast — toasts appear without an anchor",
    ],
    "variant_axes": ["position", "size", "state"],   # which dims vary
    "typical_children": [
        {"type": "text", "role": "label"},
        {"type": "icon", "role": "arrow", "optional": True},
    ],
    "typical_size_px": {"min_w": 60, "max_w": 320,
                        "min_h": 20, "max_h": 120},
    "clay_equivalent": None,                          # not in CLAY
    "aria_role": "tooltip",
}
```

### Taxonomy: category tree (closed enum, ~8 values)

- **nav** — header, bottom_nav, tabs, breadcrumbs, pagination, side_nav
- **content** — card, list_item, heading, text, image, divider, empty_state
- **input** — button, text_input, checkbox, radio, toggle, slider, select, date_picker
- **overlay** — dialog, sheet, drawer, menu, popover, tooltip, toast, alert, banner
- **chrome** — status_bar, home_indicator, keyboard, system_bar
- **media** — image, icon, video, avatar, logo
- **layout** — container, frame, spacer, skeleton
- **control** — switch, stepper, radio_group, button_group

Category is the upper node in hierarchical classification (Tier-3 idea; v2.1 doesn't ship full hierarchy but the metadata is in place).

### Additions (from v1 corpus + research)

Add these canonical types (missing or non-normalized today):

- `tooltip` (user hit 29× in overrides).
- `toast`.
- `banner`.
- `empty_state`.
- `spinner` (CLAY: SPINNER).
- `progress_bar` (CLAY: PROGRESS_BAR).
- `skeleton` (loading placeholder — already in catalog; verify alias).
- `breadcrumbs`.
- `segmented_control`.
- `stepper` (CLAY: NUMBER_STEPPER).
- `control_point` (user surfaced 5× — design-tool handle primitive).

### CLAY / ARIA alignment

Add a `clay_equivalent` + `aria_role` field per entry. Ship as aliases:

```yaml
NAVIGATION_BAR → bottom_nav
TOOLBAR → header
PICTOGRAM → icon
LABEL → text
CARD_VIEW → card
LIST_ITEM → list_item
TEXT_INPUT → text_input
CHECK_BOX → checkbox
SWITCH → toggle
PAGER_INDICATOR → pagination
SPINNER → spinner
PROGRESS_BAR → progress_bar
ADVERTISEMENT → banner
DRAWER → drawer
DATE_PICKER → date_picker
NUMBER_STEPPER → stepper
```

### Acceptance

Catalog migration: one SQL migration file + updated seed data. `component_type_catalog.category` constrained to the closed 8-value enum via CHECK. 204/204 corpus parity preserved (catalog is schema-stable; only columns added).

### Effort

3-4 hours. Most of it data entry + validation.

---

## 3. Phase B — Few-shot examples from user reviews

### Why

You have **266 `accept_source` + 93 `override` = 359 human-labelled examples**. Include 3-5 similar examples in each classify prompt → model gets calibration against the authoritative labels for THIS project.

### Shape

For each classify call on candidate C, retrieve few-shot examples where:
- Parent canonical_type matches C's parent.
- Child type distribution is similar (Jaccard ≥ 0.5 on child types).
- Typed canonical in the review is in C's plausible type space.

Retrieval is `dedup_key`-family match — same signature we use for grouping. No embeddings needed; stdlib `difflib` + exact-match.

### Prompt shape

```
## Examples from human review on this project

Example 1: A node named 'Left' inside a header, with 5 icon + 1 text
child (sample text 'Filename') — the reviewer classified this as
`header`. Reason: left-zone of a header bar with navigation controls
+ filename.

Example 2: A node named 'details' inside a card, 3 text children —
reviewer: `heading`.

Example 3: ...

## Now classify these nodes:

...
```

### Implementation

New module `dd/classify_few_shot.py`:

```python
def retrieve_few_shot(
    conn, candidate, k=3,
) -> list[dict]:
    """Return k most-similar user-reviewed nodes."""
```

Called from the v2 classifier between dedup and LLM classify. Adds ~500-1500 tokens per call; cost delta small.

### Effort

~1 day. Mostly tuning the similarity function so retrieved examples are actually informative.

---

## 4. Phase C — Prompt features (geometric + screen context)

### Why

LLM currently sees structural fields (name, children, parent) but no position/size info. Adding these gives strong priors for free:

- `bottom_nav` is always full-width at the bottom.
- `status_bar` is always full-width at the top.
- `divider` is always thin (height or width ≤ ~4px).
- `icon` is small-square (aspect ratio near 1).
- `card` is usually mid-sized rectangle.

### Shape

Each candidate's prompt line gains:

```
- **node_id=128**: name="Titles"; type=FRAME; depth=3;
  size=64×26 (aspect 2.46); position=48%x, 12%y of screen (top-center);
  relative_to_parent=15% width; parent=header; ...
```

Also: screen-type context at the top of the prompt.

```
Screen: iPad Pro 12.9" (ipad_13, skeleton=standard)
Canonical types already classified on this screen: header (1),
bottom_nav (1), card (4), icon (12), text (23).
```

### Implementation

Extend `_describe_node` in `dd/classify_llm.py` + the equivalent in `dd/classify_vision_batched.py` to include geometric features. Pull screen metadata at prompt-build time.

### Effort

~0.5 day. Mostly templating.

---

## 5. Phase D — Crop upgrades

### Scale-2 crops

Figma REST supports `scale=1|2|3|4`. For retina iPad screens, scale=1 is already 2x Figma canvas (so effectively retina); for iPhone screens, scale=1 is 1x. Requesting scale=2 uniformly makes small nodes ~4x more pixels.

Tradeoff: more image tokens per call. Likely +20-30% cost per vision call. Worth it if accuracy on small nodes lifts.

### Parent + sibling outlines

Modify `crop_node_with_spotlight` to optionally accept parent_bbox + sibling_bboxes. Draw:
- Node bbox: magenta solid (current).
- Parent bbox: dashed gray.
- Sibling bboxes: thin light-gray.

Gives the model visual structural context without needing text description of it.

### Effort

~0.5 day.

---

## 6. Phase E — Rejection sampling on low confidence

### Why

Vision returns `unsure` or confidence < 0.7 on ~15% of rows. Retry those with a different prompt framing ("look again; describe what you see; then classify") — known to catch 30-50% of borderline cases.

### Shape

After the first PS pass, find rows where confidence < 0.7. For each, issue a second call with CoT prompt:

```
Look carefully at the crop. Describe what you see (2-3 sentences).
THEN classify from the catalog.
```

Result: better reason text + often a more confident classification. If the second call ALSO returns low confidence, mark as `unsure` with both reasons.

### Effort

~0.5 day. One new function + integration into the v2 orchestrator.

---

## 7. Phase F — Validation

Re-run the 10-screen bake-off (`scripts/bakeoff_v2.py`) with v2.1. Expected:

| Metric | v2 (Phase 0) | v2.1 target |
|---|---:|---:|
| LLM↔PS agreement | 82.1% | ≥ 90% |
| PS↔CS agreement | 72.3% | ≥ 85% |
| Flagged-row % | 10.8% | ≤ 5% |
| Cost per screen | ~20s | ~25-30s (bigger prompts) |

If all three hit, we re-run the full corpus and expect **≥ 80% LLM↔PS corpus-wide**.

---

## 8. Out of scope for v2.1

Deferred to v2.2 / later:

- Hierarchical classification (Tier-3 #9 — 2-stage category→type).
- Ensemble of prompt styles (Tier-3 #10).
- Active-learning loop (Tier-3 #11).
- Fine-tuning on user reviews (Tier-4 #12).

These layer cleanly on top of v2.1's catalog + few-shot infrastructure when needed.

---

## 9. Execution order

Sequential (each phase builds on the previous):

1. **A (catalog)** — 3-4h. SQL migration + seed update + tests.
2. **B (few-shot)** — 1d. New module + orchestrator integration + tests.
3. **C (prompt features)** — 0.5d. Extend describe-node helpers.
4. **D (crop upgrades)** — 0.5d. PIL tweaks + fetch-at-scale-2.
5. **E (rejection sampling)** — 0.5d. CoT retry path.
6. **F (bake-off)** — run + gate check.
7. If A-E bake-off hits 90% LLM↔PS: full corpus re-run.

Total: ~3 days focused work + ~$3-5 API for bake-offs.
