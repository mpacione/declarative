# Continuation — Synthetic Generation v0.1 implementation

> Paste this into a fresh Claude Code session. Read it top-to-bottom
> before doing anything. It captures the full state of the sprint so
> you can pick up without re-deriving.

## Orient (30-second version)

The declarative-build compiler finished its round-trip foundation phase
(204/204 parity on Dank Experimental). The next phase is **synthetic
screen generation** — prompt → IR → existing renderer → Figma.

The previous session did the research + planning + early experiments.
It produced:

- Full exploration doc at `docs/research/synthetic-generation-planning.md`
- Nine experiments (0, 2, 3, A, B, C, E, G, I) under `experiments/`
- Two renderer-bug fixes in the round-trip foundation (both latent; 204/204 parity didn't catch them because the extractor doesn't produce the triggering IR shapes)
- Engineering spec for the next major piece (Exp H — shadcn ingestion) at `experiments/H-design-systems/spec.md`
- A process correction captured in `feedback_auto_inspect_before_human_rate.md`

Your job is to implement Exp H Step 1 (shadcn MVP) and close the loop
on the visual-failure problem the previous session diagnosed but
couldn't finish fixing.

## State of the repo

Commit chain from previous session (most recent first):

```
eb69ac9  docs: Wave 2 rating template + Exp H engineering spec
03ce56d  research: Exp G positioning grammar + Exp I sizing defaults
6d38cc7  research: Wave 1.5 v3 + Exp H candidate design systems survey
240c44a  research: Wave 1.5 v2 + Exp E artefacts (auto-induction + partial fix)
880bea8  fix: widen _LEAF_TYPES to cover heading/link/image
f15b39f  fix: renderer leaf-type layout gate + outer KIND_RENDER_THROWN guard
52180bf  research: synthetic-generation-planning + Wave 1 experiment artefacts
```

Tests: 1,686 unit passing. 204/204 round-trip parity preserved.

Environment:
- `.env` has `ANTHROPIC_API_KEY`, `FIGMA_ACCESS_TOKEN`, `GOOGLE_API_KEY` — all verified working at session end.
- Figma Desktop bridge on port 9231 connected to "Dank (Experimental)". Output page is "Generated Test".
- Python 3.11+ in `.venv`, Node 18+ in `node_modules/`. `npm install` + `pip install -e .` already run.

## The diagnostic state, summarized

### What works

- Round-trip foundation: extract → generate → render → verify at `is_parity=True` for 204 app screens.
- `dd generate-prompt` pipeline executes end-to-end. Claude parses a prompt into a component list; compose builds CompositionSpec; renderer emits Figma script; script renders without crashing.

### What doesn't

**Visual output is categorically empty.** Wave 1.5 v3 ran 12 prompts
through the fixed pipeline. All 12 scripts completed with zero errors.
All 12 rendered. But the rendered screens look like this:

- A handful of text labels (`"Sign In"`, `"Forgot password?"`, `"Notifications"`) at top-left
- Everything else (buttons, inputs, cards, toggles, icons, images) renders as invisible 100×100 grey frames with no visible content
- 212 of 229 non-screen nodes at Figma's `createFrame()` default size
- Zero Mode-1 component instances across all 12 prompts
- Zero token references in any emitted IR

The previous session's last action was writing a rating form BEFORE
personally inspecting the screenshots — and when the user looked, they
(rightly) called it out. The output is too uniformly broken to be
rated. Rating belongs AFTER the pipeline produces visibly-different
output between prompts; not at this stage.

### Why this happens (the three compositional gaps)

From Wave 1.5 v3's memo:

1. **Screen-level layout absent.** `compose.py` falls back to hardcoded `y = N * 50` positioning because Dank screens have `layout_mode=None` on the root — designer practice, not a data bug. Children stack into the same vertical region when they have variable heights.
2. **Sizing has no fall-through.** The LLM emits `{type: "button", props: {text: "Save"}}`. Compose has no CKR match, no retrieval corpus, no catalog default — falls to `createFrame()` 100×100.
3. **Mode-2 has no internal templates.** Button renders as empty grey frame because nothing tells it "a button is a FRAME with a TEXT child."

All three are additive pipeline work. None are architectural.

## What you should do, in order

### Step 0 — Read first

Before any action, read in this order (all under repo root):

1. `docs/research/synthetic-generation-planning.md` — full strategic context
2. `experiments/H-design-systems/spec.md` — the engineering spec for what you're building
3. `experiments/G-positioning-vocab/grammar.md` — the 16-construct positioning grammar ingested components must normalize into
4. `experiments/I-sizing-defaults/defaults.yaml` — the 7 Dank-derived defaults to ship; 36 types flagged insufficient
5. `experiments/00c-vanilla-v3/memo.md` — concrete diagnosis of the visual-failure state you're correcting
6. `feedback_auto_inspect_before_human_rate.md` in memory — the process correction

### Step 1 — Build the auto-inspect gate

Before implementing ingestion, build the automated visual-sanity
gate. This is the piece that was missing and caused the wasted
rating ask. Scope:

- A Python module (`dd/visual_inspect.py`?) that takes a rendered
  screen's screenshot PNG and returns a structured score.
- Two implementations: (a) cheap rule-based (percentage of non-
  background pixels, count of visible non-text nodes above a size
  threshold from the walk.json); (b) Gemini 3.1 Pro VLM pass with
  a minimal rubric ("Does this rendered screen contain
  interpretable UI? 1-10 + one-line reason").
- Integration into the existing experiment runners so Wave 1.5-
  style sweeps automatically produce a sanity report, not just
  structural metrics.
- Gate: if >50% of outputs fail the VLM gate (score < 4), no
  rating template is generated; instead a "pipeline broken,
  iterate here" memo gets produced.

Estimated: half a day. Small, foundational.

### Step 2 — Exp H Step 1 (shadcn MVP)

Follow `experiments/H-design-systems/spec.md`. Key modules to create:

- `dd/ingest/common.py` — shared utilities: catalog-type classifier
  with structural validation (the alias-hijack guard from Exp I),
  G-grammar positioning normalizer, slot-contract matcher.
- `dd/ingest/shadcn.py` — shadcn-specific parser. Input: cloned
  shadcn/ui repo. Output: `IngestedComponent` instances.
- `dd/ingested_systems.py` — CLI glue (`dd ingest-design-system`,
  `dd ingested-systems list`, `dd ingested-systems link`).
- New migration for `linked_corpora` pointer table on the main DB.
- Tests mirroring the ADR-006 ingest tests — `IngestedComponent`
  shape validation, alias-hijack rejection, grammar normalization
  coverage.

Budget: 2-3 engineer-days for the MVP.

### Step 3 — Measure before adding more systems

Re-run Wave 1.5 v3's 12 prompts with shadcn linked. Use the Step 1
auto-inspect gate. Success criteria from spec.md:

- Default-100×100 node count drops from 212 to <50 across the 12
  prompts
- Either Wave 2 ratings OR Wave 3 VLM scores improve on
  intent_match + structural_quality with shadcn linked

If those pass, proceed to Material Design 3 ingest (Step 3 of
the spec). If not, iterate on the shadcn parser or retrieval
ranker before adding more corpora.

## Things to NOT do / things to guard against

- **Don't send a rating template before visually inspecting outputs yourself.** If the auto-inspect gate hasn't passed, humans don't rate.
- **Don't add IR columns to L0 for synthesis-oriented fields.** The positioning grammar from Exp G lives at L3; the lowering translates. If you're about to `ALTER TABLE nodes`, reread the planning doc's "Architecture correction — IR fields stay out of L0" section.
- **Don't assume designer practices.** Dank has `layout_mode=None` on 100% of screen roots AND no 8-point grid. The solver + L3 grammar approach handles this; hardcoded "add auto-layout to screens" fixes do not.
- **Don't over-trust name-based alias matching.** The Exp I memo's `Sidebar` → `drawer` hijack is a real pattern. Ingested components need structural validation, not just name matching.
- **Don't use mono-Claude for both generation and critique.** Gemini 3.1 Pro is the cross-family critic. The Exp E success is explicit about this.

## What's available if you need it

- Anthropic API (`claude-haiku-4-5`, `claude-sonnet-4-6`): unlimited for experiments
- Gemini 3.1 Pro: via `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent`
- Figma Desktop bridge on port 9231 (confirm via `figma_get_status`)
- 204 Dank screens + 129 CKR components + 293K node bindings as the primary corpus
- Exp G's 37,877 classified positioning patterns as reference data
- Exp I's per-type distributions at `experiments/I-sizing-defaults/per_type_details/*.json`

## Open questions still worth thinking about

- **Cold-start UX** for users with no corpus yet: preload shadcn by default, or require opt-in?
- **Token collision** when two ingested systems define the same token name — prefix all tokens, or pick a "primary" system?
- **Asset handling** for ingested components: do we ingest shadcn's Lucide icons into the asset registry, or leave icon resolution to the user?
- **Version pinning** vs HEAD tracking for ingested systems.

All deferred to discuss after Step 1 MVP shows what's actually needed.

## The five experiments that haven't happened yet

- **Wave 2** (human rating): pending auto-inspect gate + shadcn ingest making outputs rateable
- **Wave 3** (vision-critic stress test): pending outputs that VLM can distinguish between
- **Exp D** (anchor exemplar retrieval impact): pending shadcn ingest producing a retrieval corpus
- **Exp F** (critic ensemble disagreement): deferred, lowest priority
- **Exp H Steps 2-5**: Material Design 3, Carbon, Fluent UI, tier-3 systems

## If you finish Step 1-3 early

Work the open questions into concrete tests. Or start Wave 3's VLM
critic pipeline (spec in planning doc). Or advance Exp D. Or do the
Wave 2 rating pass yourself on shadcn-boosted outputs.

## Critical invariants to preserve

- 204/204 round-trip parity. Never regress. Run `python3 render_batch/sweep.py --port 9231` if you touch the renderer.
- `1,686` unit tests passing. Add tests when you add code; don't let them drop.
- ADR-006 boundary contract symmetry. Any new ingest adapter (including shadcn's) plugs in via `IngestAdapter`-shaped protocols.
- ADR-007 unified verification channel. Any new failure mode gets a `KIND_*` constant.

## Useful commands

```bash
# Run tests (unit subset; integration tests need classified DB)
source .venv/bin/activate
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Round-trip parity check (takes ~8 min)
python3 render_batch/sweep.py --port 9231

# Extract a fresh Figma file
export $(grep -v '^#' .env | xargs)
python3 -m dd extract "https://www.figma.com/design/<KEY>/<name>"
python3 -m dd extract-plugin --port 9231

# Generate from prompt (the current broken baseline)
python3 -m dd generate-prompt "a login screen" --out /tmp/out.js
node render_test/walk_ref.js /tmp/out.js /tmp/walk.json 9231
```

## Handoff note

This sprint was productive but hit context exhaustion before landing
Exp H. The previous session's mistake was sending a rating form before
visual inspection — that's codified in `feedback_auto_inspect_before_human_rate.md`
as a rule. Don't repeat it.

The spec is solid. The grammar is grounded. The measurements are
honest. The code is ready to be written. Good luck.
