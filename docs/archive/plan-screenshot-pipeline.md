# Screenshot → Classified UI pipeline (sketch)

**Status**: design sketch, 2026-04-20. Not implemented. Discuss before starting.

Sibling pipeline to the existing Figma-backed classifier. Takes a raw PNG / JPG screenshot in, emits the same JSON shape the Figma pipeline emits:

```jsonc
[
  {
    "bbox": [x, y, w, h],             // pixel coords on the input image
    "canonical_type": "button",        // from the shared 54-type catalog
    "confidence": 0.92,                 // 0.0–1.0
    "reason": "pill with label 'Continue', primary-color fill",
    "super_category": "action",         // if hierarchical two-stage lands
    "new_type_label": null              // populated when canonical_type = "new_type"
  },
  ...
]
```

The output shape matches what `run_classification_v2` writes into
`screen_component_instances`, so downstream synthesis, reports, etc.
don't need separate handling.

## Why this plan and not another one

Picked based on Tier-1/3 research findings (see
`feedback_screenshot_pipeline_research.md` and the 2026-04-20 agent
report). Three decisions justified below.

1. **OmniParser v2 for detection** — not a VLM reasoning step, a
   commodity pre-trained YOLO + Florence-2 detector. Open-source
   (Microsoft, CC-BY-4.0). Gives us the `[{bbox, coarse_type,
   caption}, ...]` stream we'd otherwise have to build ourselves.
   Replaces the "Figma node tree + width/height columns" signal.

2. **Set-of-Marks for classification** — render numbered overlays
   on the full screenshot and ask Sonnet to label each mark in one
   pass. WACV 2025 shows +7.45 pts over base prompting on Sonnet-
   class models. This specifically dodges the per-crop resolution
   loss you surfaced today in the Figma review UI — the model
   always sees the full screen with tiny icons in their sibling
   context.

3. **CLIP visual retrieval for few-shot** — name-based retrieval
   can't work (no names on pixels); CLIP embedding retrieval works
   identically on any crop, and on the Figma side fixes the
   known name-collision regression Gemini hit.

## Module layout

| New file | Responsibility |
|---|---|
| `dd/screenshot_pipeline.py` | Top-level orchestrator: image → classifications. |
| `dd/screenshot_detect.py` | OmniParser wrapper. Local inference or HF Inference API. |
| `dd/screenshot_classify.py` | Set-of-Marks overlay + Sonnet classification + hierarchical two-stage. |
| `dd/clip_retrieval.py` | CLIP embedding index (precomputed from reviewed rows). |
| `scripts/classify_screenshot.py` | CLI wrapper: `classify_screenshot.py path/to/screenshot.png` |
| `tests/test_screenshot_pipeline.py` | End-to-end with stubbed detector + mocked Sonnet client. |

Reuses (no changes needed):
- `dd/catalog.py` — same catalog
- `dd/classify_consensus.py` — same rule v1/v2 if we add multiple vision sources later
- `dd/classify_vision_gemini.py` — if Gemini comes back as a 4th source

## Data flow

```
screenshot.png
    │
    ├─[M1] image preprocessing
    │       - detect DPR / normalize to max ~1920 longest side
    │       - strip EXIF rotation
    │
    ├─[M2] OmniParser v2 region detection
    │       ↓
    │   [{bbox, coarse_type∈{icon,text,container}, caption, conf}, ...]
    │       - filter conf < 0.3
    │       - merge overlapping detections (IoU > 0.7 → keep higher conf)
    │
    ├─[M3] set-of-marks renderer
    │       ↓ numbered-overlay PNG + mark list
    │   {marks: [{mark_id: 1, bbox: [...]}, ...]}
    │
    ├─[M4] Sonnet vision pass (single API call)
    │       prompt: "Classify each numbered mark against the catalog..."
    │       ↓
    │   [{mark_id, canonical_type, confidence, reason}, ...]
    │       - constrained decoding (Anthropic tool_use enum, Nov 2025 GA)
    │       - hierarchical two-stage IF catalog super-category annotations exist
    │
    ├─[M5] CLIP few-shot augmentation (optional, post-hoc rerank)
    │       - encode each mark's crop with CLIP-ViT-B/32
    │       - k-nearest in reviewed-rows index (k=3, cosine)
    │       - if k-nearest's majority label != Sonnet's, flag for review
    │       - low-confidence marks (< 0.75) re-queried with few-shot examples
    │
    └─[M6] output JSON
        [{bbox, canonical_type, confidence, reason, ...}, ...]
```

## Dependencies + sizes

- `torch` (CPU-only wheel; ~800 MB)
- `transformers` (for CLIP + Florence-2; ~500 MB)
- `ultralytics` (for YOLO backbone; ~50 MB)
- `huggingface_hub` (for model pulls)
- OmniParser v2 weights: ~2 GB (one-time download)
- CLIP ViT-B/32: ~350 MB

All open-source, all offline-capable after first download. No new API
accounts needed; existing Anthropic + Figma keys suffice.

## Cost profile per screenshot

| Stage | Cost | Time |
|---|---:|---:|
| Preprocessing | $0 | <100ms |
| OmniParser (CPU) | $0 | ~3s |
| OmniParser (GPU) | $0 | ~100ms |
| Set-of-Marks render | $0 | ~200ms |
| Sonnet vision (~30 marks) | ~$0.02 | ~8-12s |
| CLIP retrieval (~30 marks) | $0 | ~500ms |
| **Total (CPU)** | **~$0.02** | **~15s** |
| **Total (GPU)** | **~$0.02** | **~12s** |

For batch processing 100 screenshots: ~$2, ~25 min on CPU.

## Rollout milestones

Each milestone is independently valuable — you can stop at any one.

**M1 — Detection-only (1 day)**
- `dd/screenshot_detect.py` wraps OmniParser v2 with a clean
  `detect(image_bytes) -> list[Detection]` contract.
- CLI: `classify_screenshot.py --stage detect <png>` dumps JSON.
- Success gate: OmniParser finds ≥90% of obvious UI elements on 5
  test screenshots (sample eyeball; no ground truth yet).

**M2 — Full classification pipeline, no few-shot (1 day)**
- `dd/screenshot_classify.py` takes Detection[] + image, returns
  classifications.
- Sonnet SoM prompt with constrained decoding.
- Output JSON parity with `run_classification_v2`.
- Success gate: end-to-end run on 5 screenshots produces plausible
  labels (human eyeball).

**M3 — CLIP few-shot augmentation (1 day)**
- `dd/clip_retrieval.py` precomputes embeddings for the 980 `accept_
  source`-reviewed rows (crops fetched from DB).
- Index built once, cached to disk.
- Retrieval augments Sonnet prompt for low-confidence marks.
- Success gate: on a held-out eval set, few-shot lifts match rate
  by ≥5 pts.

**M4 — Eval harness + accuracy measurement (0.5 day)**
- Render known-good Figma screens to PNG (200 screens × 1 flat each).
- Run screenshot pipeline → compare canonical_type against Figma-
  pipeline output.
- Gate: ≥70% agreement with Figma-pipeline output (baseline accuracy).

**M5 — CLI + docs (0.5 day)**
- `classify_screenshot.py path/to/image.png` → JSON to stdout.
- `classify_screenshot.py --batch dir/*.png --out results/` writes per-file JSON.
- README section in `dd/` with usage examples.

**Total effort**: ~4 days of focused work.

## Open questions

1. **Local vs hosted OmniParser?** Local is free but adds ~2GB dep
   + torch runtime. Hosted (HF Inference API) is $0.01/call but
   zero-dep. Recommend local for dev (reproducibility) + optional
   hosted for production (if latency matters).

2. **Does screenshot pipeline share the `classification_reviews`
   table with Figma pipeline?** Yes, with a new column `source` ∈
   `{figma, screenshot}`. Lets us measure per-source accuracy
   separately and use each to feed few-shot for the other.

3. **Ground-truth strategy for eval?** Render 200 Figma screens to
   PNG, run both pipelines, treat Figma-pipeline output + human
   reviews as ground truth. A clean agreement metric emerges.

4. **Cross-pipeline catalog drift?** Both pipelines read
   `component_type_catalog`. If the Figma side adds `not_ui`, the
   screenshot side picks it up for free. No separate vocabulary
   maintenance.

## Known-unknowns / risks

- **OmniParser's type taxonomy is coarser than ours.** Output types
  are ~4-6 buckets (icon, text, container, button...). We'd map
  them to super-categories; the Sonnet pass then picks leaf types.
- **CLIP might not cluster UI types well.** CLIP is trained on web
  images, not UI. Fallback: fine-tune on the 980 reviewed crops
  (~1 day of training) or use DINOv2 which has been shown to
  cluster UI elements better in recent research.
- **Set-of-Marks may saturate** when a screen has >50 distinct
  UI elements (the mark labels become unreadable). Need per-region
  bucketing for dense screens — divide the screen into quadrants,
  classify each independently, merge.
- **No parent / child structural signal** — our LLM-text source's
  best feature. Can partially reconstruct with geometric nesting
  (bbox containment) but we lose the designer-authored `name`.
  Ceiling lower than Figma pipeline.

## Not in scope (deliberately)

- OCR for text-heavy elements. OmniParser + Sonnet already handle
  text; separate OCR pass adds complexity without clear lift.
- DOM/HTML inspection from rendered pages. That's a separate flow
  (web-focused, not UI-mockup-focused).
- Animated / video UI understanding. Single-frame only.
- Layout prediction (arranging the classified elements). That's
  synthesis, not classification.

## Relationship to the Figma pipeline

This is a **sibling**, not a replacement. The Figma path is still the
authoritative high-fidelity source for Dank-style design-system
synthesis. The screenshot path is a **onramp** for:

- Ingesting competitor screenshots for pattern-library comparison
- Processing user-uploaded inspiration screenshots
- Classifying rendered Figma exports when we don't have plugin access
- Non-Figma tooling: Sketch, Penpot, Adobe XD, Miro screenshots

Both pipelines share:
- Catalog (`dd/catalog.py`)
- Consensus rules (if we extend to multi-source on screenshot side)
- Review table + `apply_reviews_to_sci`
- Accuracy report format

Both pipelines differ in:
- Detection (Figma node tree vs OmniParser)
- Deduplication (structural dedup vs CLIP-visual dedup)
- LLM-text source (Figma-only; screenshot has no structural features)
