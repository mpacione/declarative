# Experiment 00b — Vanilla Baseline v2 Memo

**Run:** 2026-04-17 (≈ 30 min wall clock for the driven pipeline)
**Pipeline:** `dd generate-prompt` → `render_test/run.js` → `render_test/walk_ref.js`
**DB:** `Dank-EXP-02.declarative.db` (Dank Experimental — 338 screens,
204 non-synthetic, 129-row `component_key_registry`, 1-row
`component_templates`, 0-row `tokens`)
**Bridge:** port 9231, "Generated Test" page (name-asserted)
**Prompts:** identical 12 as Exp 0, verbatim
**Pipeline commit:** `f15b39f` — leaf-type gate + outer `render_thrown` guard
**LLM:** Claude Haiku 4.5 (real; API credits restored; usage: ~540 in /
300-900 out tokens per call)

## 1. Baseline for v0.1

| | Exp 0 | Exp 00b |
|---|---|---|
| Pipeline `__ok=true` to bridge | 1 / 12 | **12 / 12** |
| `__errors` entries | 0 | **11** (`render_thrown`) |
| Full-subtree render (walk covers all IR eids) | 1 (drawer-nav) | 1 (**meme-feed, 27 eids**) |
| Root-only render (throw caught early) | 0 | 11 |

Every generated script returns `__ok: true` because the outer try/catch
(f15b39f Fix 2) catches the leaf-type bug and pushes `render_thrown`
before `M["__errors"] = __errors`. But 11/12 are just the root
`screen-1` frame — the throw hits on the first `createText()` +
`layoutMode` collision and ends Phase 1. Only `03-meme-feed` rendered
its full 27-element tree (8.9 KB screenshot vs 3.5 KB blank-frame
everywhere else).

**The renderer fix is partial.** `_LEAF_TYPES` contains `"text"` but
not `"heading"` or `"link"` — both render as `figma.createText()` per
`_TEXT_TYPES = {"text", "heading", "link"}`. Every prompt except
`03-meme-feed` has a `heading`, triggering the same
`.layoutMode = "VERTICAL"` on a TEXT node. 2-4 collisions per failing
prompt. Narrow fix: add `heading`/`link` to `_LEAF_TYPES` (three-line
change); would plausibly take 11/12 → 12/12 without other work. Per
"do not fix mid-run" I did not apply it.

## 2. `__errors` content — outer guard validation

Every failing render surfaces exactly one structured entry:

```json
{"kind": "render_thrown", "error": "object is not extensible",
 "stack": "    at <anonymous> (<input>:43:3) | "}
```

No `KIND_DEGRADED_TO_MODE2` (no IR element marked `is_db_instance` —
see §3). No `KIND_MISSING_ASSET` (no vector/SVG paths requested). No
`text_set_failed` — the TEXT nodes died before Phase 2 `characters`
assignment. Exp 0 had 0 errors despite 11 failures; Exp 00b surfaces
exactly one entry per failing prompt with location (`<input>:LINE:COL`)
and kind. Outer guard works as specified.

## 3. Component usage — still 0 Mode-1 emissions

20 of 48 catalog types used across the 12 prompts (same coverage as
Exp 0; distribution similar). Top: `list_item: 30, card: 29,
heading: 26, text: 22, button: 19, navigation_row: 14, image: 11,
header: 9, icon_button: 8`. Never used: 28 types including
`accordion, alert, bottom_nav, breadcrumbs, checkbox, dialog, fab,
segmented_control, sheet, skeleton, slider, tabs, toast, tooltip`.

**Mode-1 count: 0.** Zero `createInstance()` calls, zero non-empty
`variant` fields, zero component_key bindings. `component_templates`
still has one row (`screen/default`, 204 instances) so
`build_project_vocabulary()` surfaces one line to the LLM: "screen:
default". 261 Mode-2 warnings across the 12 prompts (one per
non-screen IR element). The 129-row `component_key_registry` —
`icon/chevron-right`, `iOS/HomeIndicator`, etc. — remains invisible
to the LLM. Unchanged from Exp 0.

## 4. Tokens — zero references, zero bindings

`token_refs.json` is empty for every prompt. No `{color.*}`/`{space.*}`
emission. Every color is a literal (e.g. `screen-1` fills hardcoded to
`#F6F6F6`). Root cause unchanged: `tokens` table has 0 rows; no
`dd cluster && dd accept-all` has been run. 293K raw bindings exist
in `node_token_bindings` but none have been promoted. Upstream of
synthesis — nothing has told the LLM there's a palette.

## 5. Latency

Per-prompt wall-clock, end to end:

| Stage | min (ms) | p50 (ms) | max (ms) |
|---|---|---|---|
| parse (Haiku, real) | 1000 | 3000 | 8000 |
| compose (pure Python) | ~1 | ~3 | ~8 |
| render (bridge) | 63 | 143 | 302 |
| walk (bridge) | ~70 | ~140 | ~300 |

Parse dominates — Haiku runs 1-8 s depending on output size (larger
prompts like paywall, which produced 35 components, took ~8 s).
Exp 0's synthetic 0-ms parse understated reality by ~3 orders of
magnitude. Render is fast regardless of outcome — 11/12 throw around
t+100 ms; 03-meme-feed's full 27-node Phase 1-3 execution came in at
216 ms. No bridge disconnects.

## 6. Mechanical observations (no quality ratings)

1. **Flat vertical stack, no horizontal or grid layout.** Every prompt
   ended up as `screen-1 → {header, card-1..N, …}` with cards holding
   1-5 vertically-stacked children. compose.py's flat-stacking default
   dominates; system prompt never asks for side-by-side arrangements.

2. **Mode-2 everything → 100×100 grey frames.** 14 of 27 rendered
   nodes in 03-meme-feed are the default 100×100. The visible output
   (`screenshot.png`, 8.9 KB) is 4 text captions stacked with invisible
   100×100 image/button frames between them — auto-layout positions
   correctly but visuals are absent. All other prompts' screenshots
   are 3.5 KB blank grey frames (rendered throw = childless root).

3. **Repeated-card shapes are structurally identical.** 05-paywall
   (3 price tiers + testimonial) and 10-onboarding-carousel (3 slides)
   produce near-duplicate card subtrees in the IR. Same as Exp 0.

4. **`09-drawer-nav` regressed from Exp 0's one-success.** Opus in
   Exp 0 emitted no text-ish types; Haiku in Exp 00b added a "Menu"
   `heading`, which triggered the bug. Parse-distribution drift, not
   a pipeline regression. `03-meme-feed` succeeded purely because
   Haiku happened to emit `text` instead of `heading` — a single-token
   LLM-stochasticity difference gates whether the whole screen renders.

5. **Zero vector assets, zero icons, zero images.** icon_button and
   image elements all rendered as 100×100 transparent frames — they
   can't resolve to real instances or raster assets. Mode-1 starvation,
   same as Exp 0.

6. **Component-to-IR count is monotonic + 1.** Compose adds one
   `screen` wrapper; otherwise no IR pruning, no expansion. 12 / 12.

## 7. What's different from Exp 0

Exp 0 had Opus substituting for Haiku (credits exhausted), no outer
guard, and the layoutMode-on-TEXT bug affecting all three text catalog
types. Exp 00b uses real Haiku, has the outer guard, and the
leaf-type gate covers `text` but misses `heading`/`link`. Net: 1 →
11 structured errors; 1 → 12 `__ok=true` returns; 11 → 0 orphaned
nodes on page; same 1 full render per run (different prompt each
time — pure parse drift). Mode-1 and token counts stayed at 0.

**Surprises:**

- The f15b39f fix is narrower than its commit message implies — it
  stops the `"text"` type but not `"heading"`/`"link"`. Round-trip
  parity stayed green because the extraction side *never* sets
  `layout.direction` on text-like nodes; synthetic-gen is the first
  caller to exercise this path. Same "latent extractor-only"
  characterisation that motivated the f15b39f fix in the first place.
- The `render_thrown` entry carries raw exception message **and**
  script `line:col`. Enough for a codegen-side auto-repair loop to
  parse the stack, identify the offending property, and retry with it
  suppressed. Mechanical feasibility looks high.
- Whether `03-meme-feed` or `09-drawer-nav` rendered successfully in
  each run is essentially a 1-token LLM stochasticity difference
  (emit `text` vs `heading`). An auto-repair loop closes it in one
  retry.

**What stayed the same:** Mode-1 starvation, zero tokens, flat-stack
composition, 28 never-used catalog types, 100×100 default sizing. All
of §2-§6 of the original Exp 0 memo applies verbatim.

## Artefacts

`experiments/00b-vanilla-v2/artefacts/NN-slug/` each contain:
`prompt.txt`, `llm_raw_response.txt`, `component_list.json`, `ir.json`,
`warnings.json`, `token_refs.json`, `script.js`, `render_result.json`,
`walk.json` + `rendered_node_id.txt`, `screenshot.png`, `notes.md`.
Root: `activity.log`, `run_summary.json`, `system_prompt.txt`,
`screenshot_manifest*.json`, plus the four Python driver scripts.
Reproduction: run `run_experiment.py`, `run_walks_and_finalize.py`,
`write_notes.py` in order (bridge live on 9231, Generated Test page
present).

## Follow-up seeds (no priorities)

- **Add `"heading"` + `"link"` to `_LEAF_TYPES`.** Three-line fix;
  12/12 full renders in this exact experiment without any other
  change.
- **Structured-error auto-repair.** `render_thrown` carries `error` +
  `stack`; codegen-side retry could parse the stack, suppress the
  offending property, regenerate.
- **Promote `component_key_registry` into `build_project_vocabulary()`.**
  129 entries with instance counts remain invisible to the LLM — same
  "Mode-1 starvation" Exp 0 flagged.
- **Run `dd cluster && dd accept-all`** before Wave 3. Otherwise "does
  the pipeline surface tokens" stays definitionally "no".

— end memo —
