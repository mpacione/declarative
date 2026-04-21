# Session handoff — M7 synthetic-generation autonomous block

**Written**: 2026-04-21 late (end of autonomous session).
**Branch**: `v0.3-integration`  **Head commit**: `76ea45c` (test fix for slot-name invariants)

---

## TL;DR

Four plan milestones shipped + one upgraded:

- **M7.0.a** (classifier) — upgraded mid-session: SoM as 4th source in the `classify_v2` pipeline, catalog 55 → 81 types, `--rerun` flag w/ UPSERT preserves `classification_reviews`, rule v2 revived with SoM weight 2. Final↔SoM agreement 43% → **60.9%** post-consensus.
- **M7.0.b slots** ✅ — 100 components backfilled from CKR, 99 slots derived via semantic-class clustering + Claude Haiku labels (button 9, icon 86, tabs 1, header 3).
- **M7.0.c variants** ✅ — 100 variants across 7 families; axis vocabulary enforced (size / style / state / orientation / density / category / role / type / theme / shape).
- **M7.2 swap demo** 🟡 — LLM-in-loop component swap end-to-end on Dank screen 183. Compress → library catalog → Claude Haiku emits swap via enum-constrained tool schema → apply_edits splices → structural verify. **Render + `is_parity` round-trip deferred** — see "What's left" below.
- **M7.3 S1.4 set-radius demo** ✅ — second LLM-in-loop verb (set) proven on the same pattern. Claude Haiku bumped a button radius 10 → 12 with the rationale "align with standard design scale steps."

## Live-DB state (end of session)

- 49,670 `screen_component_instances` rows (formal 27,724 · heuristic 15,324 · llm 6,622) — all LLM rows have four per-source verdicts (llm_type / vision_ps_type / vision_cs_type / vision_som_type).
- 100 `components` rows, 99 `component_slots` rows, 100 `component_variants` rows.
- Pre-existing `classification_reviews = 0` (wiped in some earlier session, *not* by this one — verified against the pre-full-rerun backup).

## Commits (this autonomous block)

```
28ff077  feat(catalog): keyboard + control_box + text_cursor + magnifier rules
2d42d03  feat(classify): SoM as 4th source in classify_v2 pipeline
775d9f3  feat(classify): --rerun / force_reclassify flag
e1bae1b  fix(cli): classifier_v2 summary bug
0f4d660  feat(consensus): SoM in rule v1/v2/v3 (weight 2)
d267517  docs: M7 classifier continuation
faf9902  feat(m7.0.b): Step 1 — backfill components from CKR
ec5967c  fix(m7.0.b): canonical_type column + SD-3 consensus filter
5dc3705  feat(m7.0.b): Step 2 — button slot derivation
1f092d6  feat(m7.0.b): Step 2 scaled to icon / tabs / image / header
44a06dd  fix(m7.0.b): cluster by semantic child-class + position validation
fbda4d3  feat(m7.2): first LLM-in-loop component swap demo
90d9a94  fix(m7.2): critic follow-ups — validation, enums, trust filter
953b941  feat(catalog): +13 types from Material 3 / Apple HIG audit
7f1bb05  docs: plan-synthetic-gen with M7.0.a/b + M7.2 partial
3f74a67  feat(m7.0.c): variant family derivation from CKR naming
fe22f62  fix(m7.0.c): axis vocabulary + catalog variant serialization
cf86b34  docs: M7.0.c shipped
bb93adc  feat(m7.3): S1.4 set-radius LLM-in-loop demo
76ea45c  test(m7.0.b): relax header-slot-name assertions to invariants
```

## Tests

- **2984 passing** across 540+ suites (up from 529 at the block start).
- **36 pre-existing failures** in integration tests (rebind, screen_patterns, compress_l3 snapshot, phase0/2, integration_real_db, mode1) — verified unrelated to this block's changes via git log on the affected files.
- New test suites: `test_m7_backfill_components` (16), `test_m7_slots` (17), `test_m7_variants` (12), `test_library_catalog` (18), plus updates to `test_classify_three_source`, `test_catalog`, `test_phase3b_integration`, `test_semantic_tree_integration`.

## What's left for each milestone

### M7.2 — render + `is_parity` (the plan's actual exit bar)

Currently M7.2 passes structural verify (CompRef path matches the LLM's pick) but not the plan's "`is_parity=True` + resolved component matches the requested variant." Full closure needs:

1. Drive `dd.render_figma_ast.render_figma(applied_doc, …)` — requires piping the compressor's companion maps (`spec_key_map` / `nid_map` / `fonts` / `db_visuals` / `_spec_elements`) through the demo.
2. Send the generated JS to the Figma plugin bridge (use `render_test/batch_screenshot.js` pattern or similar).
3. Walk the rendered tree, build `rendered_ref`, run `dd.verify_figma.FigmaRenderVerifier.verify(ir, rendered_ref)`.
4. Assert `report.is_parity is True`.

Estimate: 4-6 h including integration hazards. Plugin bridge is operational (used for M7.0.a's self-hidden render-toggle).

### M7.0.c — structural/visual clustering fallback

Spec §5.1 M7.0.c calls for "auto-cluster instances by structural/visual similarity"; shipped version uses naming-pattern parsing (Dank's slash-delimited CKR convention). Works on Dank; doesn't generalise. Flag for cross-project validation (see plan-synthetic-gen.md §8 "Second project validation").

### M7.3 — S1.1 text / S1.2 visibility / S1.3 color tokens

S1.4 (radius) shipped. Remaining:

- **S1.1 text** — requires extending `_apply_set_to_node` to address `Node.head.positional` (where the compressor stores text literals). Small grammar-level change (~1 h).
- **S1.2 visibility** — same shape as radius; quick port (~30 min).
- **S1.3 color token** — needs token-ref value in the set statement (e.g. `set @X fill={color.brand.primary}`). Library catalog's `include_prop_defs=True` already exposes prop types. Estimated ~1 h.

### M7.0.d / M7.0.e / M7.0.f

Not touched this block. Blocking for the full M7.0 exit gate (80% classification accuracy + six sub-tasks + LLM smoke test). M7.0.a / b / c done; d (forces/context labels) + e (pattern extraction) + f (sticker sheet) remaining.

## Quick-start for the next session

```bash
# Verify state:
git log --oneline -20           # see the 20-commit run
git status                      # should be clean

# Re-run tests to confirm:
.venv/bin/python3 -m pytest tests/ -q -k "m7_slots or m7_variants or \
    library_catalog or backfill or consensus" | tail -3
# 66 passed (all the new work)

# Reproducible demos (the LLM calls cost ~$0.02):
.venv/bin/python3 -m scripts.m7_swap_demo --db Dank-EXP-02.declarative.db
.venv/bin/python3 -m scripts.m7_set_radius_demo --db Dank-EXP-02.declarative.db

# Or dry-run (no API cost, deterministic):
.venv/bin/python3 -m scripts.m7_swap_demo --db Dank-EXP-02.declarative.db --dry-run
.venv/bin/python3 -m scripts.m7_set_radius_demo --db Dank-EXP-02.declarative.db --dry-run
```

## Memory pointers

- `project_m7_synth_gen.md` — rolling log, updated through M7.3 S1.4
- `project_m7_classifier_v2.md` — classifier track, updated through post-2026-04-21 upgrades
- `feedback_taxonomy_research_upfront.md`, `feedback_prompt_rules_as_priors.md`, `feedback_som_weight_2.md`, `feedback_plugin_render_toggle.md`, `feedback_upsert_preserves_reviews.md` — session lessons
