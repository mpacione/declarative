# Experiment 00c — Vanilla Baseline v3 Memo

**Run:** 2026-04-17 (≈ 1 min wall clock end-to-end; 12/12 renders + walks)
**Pipeline commit:** `880bea8` — `_LEAF_TYPES` widened to cover every
`createText()` etype (grounded on the existing `_TEXT_TYPES` set plus
shape / image types).
**DB:** `Dank-EXP-02.declarative.db` (same as v2).
**Bridge:** port 9231, "Generated Test" page, file "Dank (Experimental)".
**Prompts:** identical 12 as Exp 00b, verbatim.
**LLM:** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`).

## 1. Direct comparison to v2

v2 left 11 of 12 prompts with a structured `render_thrown` on the first
`createText()` + `layoutMode` collision, terminating Phase 1 early.
Only `03-meme-feed` rendered its full subtree (27 walked eids); the
other eleven walks returned 1 (just the empty `screen-1` root).

v3 renders **12 / 12** full subtrees. Every walk covers every IR
element exactly — no composition loss, no early termination. The
`render_thrown` class is gone:

| | Exp 00b v2 | Exp 00c v3 |
|---|---|---|
| Pipeline `__ok=true` to bridge | 12 / 12 | **12 / 12** |
| Full-subtree render (walk == IR) | 1 / 12 | **12 / 12** |
| Root-only render (early throw) | 11 / 12 | **0 / 12** |
| `__errors` entries (total) | 11 (`render_thrown`) | **0** |
| Screenshot PNG min / max | 3.4k / 8.7k | **4.0k / 22.6k** |

The widened `_LEAF_TYPES` set (`_TEXT_TYPES ∪ {shape types, image}`)
cleanly eliminated the initial blocker. No new blocker surfaced — the
renderer produces valid Figma nodes for every IR element across all
12 prompts. What remains are **semantic / visual loss**, not crashes:
the script runs to completion but the layout that comes out the other
side does not render recognisable content.

## 2. Walked eid counts per prompt

Full distribution. For every prompt, `walk.eid_count == ir.elements`
— the renderer traverses and materialises the entire IR.

| slug | v2 eids | v3 eids | IR els |
|---|---|---|---|
| 01-login | 1 | **8** | 8 |
| 02-profile-settings | 1 | **14** | 14 |
| 03-meme-feed | 27 | 27 | 27 |
| 04-dashboard | 1 | **14** | 14 |
| 05-paywall | 1 | **39** | 39 |
| 06-spa-minimal | 1 | **24** | 24 |
| 07-search | 1 | **18** | 18 |
| 08-explicit-structure | 1 | **9** | 9 |
| 09-drawer-nav | 1 | **9** | 9 |
| 10-onboarding-carousel | 1 | **15** | 15 |
| 11-vague | 1 | **25** | 25 |
| 12-round-trip-test | 1 | **27** | 27 |

Sum: 13 eids across v2's 12 prompts → **229 eids** across v3's 12.
Seventeen-fold increase in materialised nodes.

## 3. `__errors` vocabulary

Empty, for every prompt. Not a single entry of any kind:

```
{kind histogram}: {}
```

No `render_thrown`. No `text_set_failed`. No `resize_failed`. No
`position_failed`. No `font_load_failed`. No new previously-unseen
kinds. The per-call try/catch wrappers at every `characters =`,
`resize()`, `x = `, `y = ` all silently succeed. This is the clearest
signal that the class of bug v2 surfaced (`layoutMode` on a TEXT
node) has been removed at the source — not just suppressed by a
catch. Every Phase 1 / 2 / 3 property write lands.

## 4. Structural observations — the next bottleneck

With crashes gone, what's visible in the screenshots is a narrow but
pervasive layout defect. Three stacking problems dominate:

**a) 212 of 229 non-screen nodes are exactly 100 × 100 px.**
`figma.createFrame()`'s default is 100×100. The renderer never
`resize()`s non-screen frames — only `screen-1` is resized to the
device (428×926). Auto-layout children inside a parent *with*
`layoutMode` do get `layoutSizingHorizontal = "FILL"` (paywall:
18 such calls). But the parent card / drawer / button frame is still
100px wide, so "fill" fills 100px. Cards stacked inside a non-auto-
layout screen sit at 100px width in a 428px frame.

**b) `screen-1` has no `layoutMode`.** Screen children are positioned
by explicit `x` / `y` coordinates in Phase 3 (e.g. `card-1.y=150`,
`card-2.y=200`, `card-3.y=250`). The y step is a hardcoded ~50px
increment regardless of actual child heights. card-1 has
`height=460`, but card-2 starts 50px below card-1's top — so card-2
visually overlaps all of card-1. 05-paywall and 10-onboarding-carousel
show this most dramatically (text from 3 tiers / 3 slides overlaps
in the top-left corner). 08-explicit-structure does the same at
smaller scale.

**c) Leaf component types have no internal template.** `button`,
`text_input`, `toggle`, `icon_button`, `avatar`, `badge`, `pagination`,
`search_input`, `fab`, `empty_state` — all Mode-2 defaulted to empty
100×100 frames. The LLM emitted `text_input {label: "Email",
placeholder: "Enter your email"}`, `button {text: "Sign In"}`,
`navigation_row {text: "Home"}`, but the Mode-2 composer drops the
label / placeholder / text props entirely for frame-backed types,
and the frame renders as a grey box. **217 Mode-2 warnings** were
recorded across the 12 prompts — one per non-screen non-text IR
element. That is the dominant cause of "screens look blank except
for headings".

The visible-text content of every rendered screen comes from three
etypes only: `heading`, `text`, and `link` — because those three route
through `createText()` which writes `characters`. Everything else is
an invisible frame.

## 5. Component resolution — still zero Mode-1

Zero `component_key`s in IR. Zero `createInstance()` calls. Zero
matched CKR entries. Same as v2: `component_templates` exposes
exactly one row (`screen: default`) to the LLM via
`build_project_vocabulary()`, and the 129-row `component_key_registry`
remains invisible. The system prompt (1,887 chars, 543 input tokens
on average) contains zero component keys. The LLM has no way to
produce Mode-1 output because there's no target vocabulary.

Compose reports **217 "no-template" warnings** across the 12 prompts.
Every non-screen non-text IR element falls through to Mode-2 (empty
frame). Nothing has changed on this axis.

## 6. Tokens — still zero

`token_refs.json` is empty for all 12. Zero `{color.*}` / `{space.*}`
references. Every color is a literal (`#F6F6F6` on screen-1, no fills
anywhere else). Root cause unchanged: `tokens` table has 0 rows;
no `dd cluster && dd accept-all` has been run.

## 7. What's actionable for v0.1

The generator must:

1. **Emit `layoutMode: VERTICAL` on `screen-1` by default.** The
   single change that turns overlap into a readable stack. Position
   children via order-in-children, not y-coordinates, so `card-1`
   actually ends where it ends and `card-2` starts after it. Phase 3
   `x=0/y=N` writes can be dropped entirely for screens with an
   auto-layout screen root.

2. **Emit `primaryAxisSizingMode: "AUTO"` and
   `counterAxisSizingMode: "FIXED"` on auto-layout screens, plus
   `layoutSizingHorizontal: "FILL"` on every direct child of the
   screen.** Cards expand to the 428px screen width instead of
   staying at the createFrame default 100px. This alone fixes the
   "content crammed into the left 100px of the screen" class across
   all 12 prompts.

3. **For Mode-2 leaf types (`button`, `text_input`, `toggle`,
   `icon_button`, etc.), synthesise a minimum-viable internal
   template from the LLM's `props`.** Specifically: for `button {text}`
   emit `createFrame` with a single `createText` child holding the
   text + `layoutMode HORIZONTAL` + FILL. For `text_input {label,
   placeholder}` emit a frame containing a label text above an
   input-looking frame containing placeholder text. These templates
   are type-specific but small and deterministic. 217 Mode-2
   warnings become 217 rendered leaf components instead of 217 grey
   boxes.

4. **Resize every non-screen frame to a sensible default other than
   100×100.** Even just `resize(428, 120)` on top-level cards would
   stop the "invisible child + text overflowing the visible bounds"
   artefact. Better: chain it with the sizing mode above (AUTO height,
   FILL width).

5. **Promote `component_key_registry` into `build_project_vocabulary()`.**
   129 keys (`icon/chevron-right`, `iOS/HomeIndicator`, etc.) are
   present in the DB but not in the system prompt. Once surfaced,
   the LLM can start emitting `component_key: "icon/chevron-right"`
   on icon_buttons, which Mode-1 will pick up. Same "mechanism"
   as the mode-1 starvation note in v2, unchanged.

6. **Run `dd cluster && dd accept-all`** once before Wave 3 so
   `tokens` is not definitionally empty.

Items (1)-(4) are the v0.1 scope. (5)-(6) are prerequisites for
anything beyond v0.1.

## Artefacts

`experiments/00c-vanilla-v3/artefacts/NN-slug/` each contain:
`prompt.txt`, `llm_raw_response.txt`, `component_list.json`, `ir.json`,
`warnings.json`, `token_refs.json`, `script.js`, `render_result.json`,
`walk.json`, `rendered_node_id.txt`, `screenshot.png`, `notes.md`.
Root: `activity.log`, `run_summary.json`, `screenshot_manifest.json`,
`screenshot_manifest.results.json`, plus the three Python driver
scripts (`run_experiment.py`, `run_walks_and_finalize.py`,
`save_png.py`). Reproduction: run those three in order (bridge live
on 9231, Generated Test page present).

## Surprises / notes

- No intermediate blocker surfaced. The narrow leaf-type-gate widening
  moved the pipeline from "dies at the first `createText` per prompt"
  directly to "runs to completion on every prompt." No second bug
  class emerged at Phase 1-3 once Phase 1 stopped throwing. In
  particular, `resize(...)` on autoload frames, `layoutSizingHorizontal`
  on text children, and `fills = []` on auto-layout frames all land
  without complaint for every prompt. This makes the next bottleneck
  purely compositional / semantic, not crash-oriented.
- Parse drift from v2: Haiku used 27 distinct catalog types in v3
  (vs 21 in v2). New in v3 (not in v2): `bottom_nav`, `empty_state`,
  `fab`, `segmented_control`, `select`, `toggle_group`. Same
  stochasticity between runs; the generator still can't depend on any
  particular type showing up.
- The single clearest "now works" signal is 05-paywall: 22.6 KB
  screenshot with three tier names (Starter / Pro / Enterprise),
  three price lines, three feature descriptions, plus a testimonial
  card — in v2 it was a 3.4 KB blank grey frame. The content *is
  there*, just crammed into the left 100px.
- `__errors` being empty rather than "a few text_set_failed here, a
  few resize_failed there" tells us the per-call try/catch wrappers
  weren't hiding a secondary failure mode. The path is clean.

— end memo —
