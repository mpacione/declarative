# Experiment 0 — Vanilla Baseline Memo

**Run:** 2026-04-16
**Pipeline:** `dd generate-prompt` → `render_test/run.js` → `render_test/walk_ref.js`
**DB:** `Dank-EXP-02.declarative.db` (Dank Experimental; 204 screens, 129-row
component_key_registry, 1-row component_templates)
**Bridge:** port 9231, "Generated Test" page
**Prompts:** the 12 prescribed (verbatim, no augmentation)

## Critical caveat — LLM parse step substituted

The pipeline's first stage is a Claude Haiku 4.5 call. On this
environment the configured `ANTHROPIC_API_KEY` has a zero credit
balance and the SDK refuses to issue requests (`Your credit balance
is too low`, HTTP 400). OAuth via `CLAUDE_CODE_OAUTH_TOKEN` is
explicitly not supported by the Anthropic API (`401 OAuth
authentication is currently not supported`).

Rather than abandon the experiment, I (the driver agent, Claude Opus
4.7) acted as the parser for all 12 prompts, using the EXACT system
prompt the pipeline builds (captured in
`experiments/00-vanilla-baseline/system_prompt.txt`; 1887 chars) and
output JSON conforming to the prescribed shape. The 12 parses live in
`experiments/00-vanilla-baseline/parses/`.

**What this does NOT affect:** compose, IR construction, script
generation, bridge execution, walk — all ran unchanged.

**What this DOES bias:** parse behaviour is a different-model parse
from Opus rather than Haiku. Opus on a 3-5-sentence brief to emit a
5–15 top-level JSON array should be well within Haiku's capability,
so I expect the parse distribution to be broadly similar, but the
substitution is worth flagging before Wave 2 designer ratings.

## 1. Automated observations across all 12 prompts

| | Count |
|---|---|
| Prompts that parsed (LLM → component list) | 12 / 12 |
| Prompts that composed into IR + script | 12 / 12 |
| Prompts that rendered end-to-end | **1 / 12** |
| Prompts with `__errors` entries in the render channel | 0 / 12 (the failure is a top-level throw, not a micro-guard trip) |
| `KIND_*` structured errors surfaced | **0** |
| Prompts with a valid walk.json | 1 / 12 |

**The one prompt that rendered: `09-drawer-nav`.** It has no `text`,
`heading`, or `link` components — every element is a `drawer` or
`navigation_row`, both of which the renderer lowers to FRAME nodes.

### Systemic render failure

Every other prompt dies at roughly the same place in `script.js`
with:

```
TypeError: object is not extensible
```

Inspection of the emitted scripts shows the renderer
(`dd/renderers/figma.py`) emits `n.layoutMode = "VERTICAL"` for
**every** element in Phase 1 (Materialize), including elements whose
Figma type is TEXT. Figma's Plugin API does not expose a writable
`layoutMode` on TEXT nodes; assigning it throws. The first TEXT
element's layoutMode assignment aborts the script, nodes created so
far are left orphaned on the page, and no `__errors` entry is
recorded (the error is caught only by the outer `run.js` wrapper's
`try/catch`).

`createText` count per script strictly tracks failure — the 11
failing scripts have 1–10 `createText()` calls; the one passing
script (09-drawer-nav) has 0.

This is a generator-side bug and is present on every prompt, not a
per-prompt quality issue. **It is the single blocker** for all
downstream evaluation. No KIND_* errors are surfaced because the
failure happens before the `M["__errors"] = __errors` line at script
end.

## 2. Component usage stats (48 canonical types)

**Types used (20):** avatar, button, button_group, card, drawer,
header, heading, icon_button, image, link, list, list_item,
navigation_row, pagination, screen, search_input, table, text,
text_input, toggle.

**Types NEVER used (28):** accordion, alert, badge, bottom_nav,
breadcrumbs, checkbox, combobox, context_menu, date_picker, dialog,
empty_state, fab, file_upload, icon, menu, popover, radio,
segmented_control, select, sheet, skeleton, slider, stepper, tabs,
textarea, toast, toggle_group, tooltip.

That's 20/47 coverage (excluding `screen` which every prompt must
have; the pipeline's lowering forces a top-level `screen-1` wrapper).

### Mode 2 fall-through

**Every single element of every prompt triggers Mode 2.** The
compose stage's `warnings.json` is consistent across all 12: every
type reports "no template in this project — will render as empty
frame". The cause is that `component_templates` has only ONE row
(canonical_type=`screen`, 204 instances, no variant, no
component_key). The vocabulary-builder threshold is ≥50 instances
and only `screen/default` passes; nothing else is surfaced to the
LLM. Per-prompt Mode 1 INSTANCE count is 0/0/0/…/0 across the 12.

This does NOT mean the DB has no component keys. The
`component_key_registry` has 129 rows (icon/home, ios/alpha-keyboard,
icon/chevron-right, iOS/HomeIndicator, etc., many with
instance_count ≥ 10). The registry is populated; `component_templates`
is essentially empty. The extraction pipeline populates the registry
but not the templates, or the templates-extraction heuristic is too
strict — I did not investigate further, but **there is a clear gap
between what the DB knows (129 keyed components) and what the LLM
prompt is told (1 type: `screen`).** This is exactly the
"pipeline-doesn't-surface-tokens/templates-to-the-LLM" problem the
broader research plan calls out.

## 3. Token usage

**`token_refs.json` is empty for every prompt. No emitted IR contains
any `{color.*}` or `{space.*}` reference. Everything is hardcoded
literal.**

The proximate cause: the `tokens` table has zero rows. The
`node_token_bindings` table has 293,183 rows, so the clustering
ingest has extracted raw color/font bindings, but `dd cluster && dd
accept-all` has not been run on this DB — no bindings have been
promoted to named tokens. With no named tokens, no template-visual
reference chain can emit a token reference.

Even if templates existed, the current renderer emits resolved
literals in most places; tokens surface only via the
`template_rebind_entries` path. On this DB that path is dead.

**This is the key "pipeline doesn't surface tokens to the LLM" check
the brief asks about — and the answer is stark: zero tokens reach
the LLM, zero tokens reach the IR, zero token refs in the emitted
scripts.**

## 4. Render-time failures

11 of 12 prompts failed hard with "object is not extensible" before
the end of the script. Nodes were created partially (visible in
`render_result.json` as `before → after` counts, typically +5–10
nodes) and then left orphaned on the "Generated Test" page. No
grey-box placeholders or component-missing placeholders ever got a
chance to render — the failure is earlier.

09-drawer-nav rendered successfully and the walk recorded 9 eids.
Every rendered element is a 100×100 FRAME (default sizing; no
template data to override it), except the top-level `screen-1`
(428×926, correct) and `drawer-1` (100×600). No vector-asset misses,
no effect misses, no walk-channel errors.

## 5. Latency breakdown

Rough wall-clock per prompt. Note the parse is a synthetic 0 — the
real Haiku call is replaced with a disk read.

| Stage | Typical ms | Notes |
|---|---|---|
| parse | 0 (substituted; real Haiku ~400–800 ms) | |
| compose (build IR + script) | 0–8 | pure Python, very fast |
| render | 66–157 | bridge round-trip; failure happens fast |
| walk | 66–176 | same story |

The entire 12-prompt sweep ran in under 10 seconds of wall clock
because the failures are immediate. If the generator-side bug were
fixed we'd expect roughly the screen_181.js ballpark (several
seconds per render) once there are real component instantiations to
do.

## 6. Mechanical patterns (no quality rating)

1. **Every prompt produced a flat (or minimally-nested) vertical
   stack.** compose.py's flat-stacking default is visible:
   `screen-1 → [header-1, card-1, card-2, …]` with cards containing
   1–5 child elements. Nothing more complex. There is no horizontal
   layout anywhere; nothing that looks like a grid.
2. **No prompt emitted any Mode 1 instance.** All 204 elements
   across all 12 prompts are Mode 2 frames. The pipeline in its
   current state cannot produce a single "this is the project's
   Primary Button" component reference — not because of a lookup
   miss, but because the vocabulary surfaced to the LLM contains
   zero button entries.
3. **The single canonical type that every prompt received from the
   vocabulary is `screen/default` (the implicit outer wrapper).**
   The LLM sees that `screen` is a thing with 204 instances, and
   … that's it.
4. **Prompt-length-to-component-count is roughly linear with a low
   coefficient.** Prompts of 5–15 word bodies produce 5–20 IR
   elements. The most ambitious prompt ("explicit-structure", with
   an explicit 6-element schema in prose) still only produced 9 IR
   elements — compose flattens back-buttons etc. into unused state.
5. **Every Mode-2-frame element is 100×100.** Without a template,
   the default dimensions apply uniformly. This is the "grey box"
   look at render time — when it renders.
6. **The generator emits `layoutMode = "VERTICAL"` unconditionally
   on every element, regardless of Figma type.** This is the render
   blocker and is also a quiet finding about the renderer: the type
   dispatch for layout properties is missing for TEXT.
7. **No `__errors` channel entries, no KIND_* errors.** The
   verification channel (ADR-007) only records micro-guard trips
   inside try/catch wrappers. The `layoutMode = "VERTICAL"` line
   has no such wrapper (it is in Phase 1 Materialize, after node
   creation), so the error escapes as a top-level throw. ADR-007's
   promise of "dense verification signal" is zero-signal in this
   failure mode. That's its own observation worth flagging.
8. **10-onboarding-carousel and 05-paywall produced structurally
   identical shapes** (repeated-card stack) — three near-identical
   card subtrees with heading/text/button children. With no
   template-driven differentiation, the IR is indistinguishable
   except for literal text.

## Concrete follow-up seeds

These are observations only, not rated priorities:

- **Fix the layoutMode-on-TEXT bug** in `dd/renderers/figma.py`.
  Without it, we cannot run any Wave-2 designer rating on prompt
  output because 11/12 prompts don't render.
- **Populate `component_templates`** — figure out why 129-row CKR
  collapses to 1-row templates. If it's the ≥ 50 instance threshold,
  most project components (icon/chevron-right has 62 instances,
  but icon/grid-view has only 13) fall below. Either the threshold
  needs lowering or the extraction step is broken.
- **Run `dd cluster && dd accept-all`** on this DB to populate the
  `tokens` table. Without tokens, "does the pipeline surface tokens
  to the LLM" is not measurable — right now the answer is definitionally
  "no, because there are none."
- **Add a micro-guard around layoutMode assignment in the renderer**
  so that even if the bug were left in, the failure would surface
  as a KIND_LAYOUT_MODE_FAILED per-eid entry rather than a script-
  ending throw.
- **Surface `component_key_registry` (not just templates) to the
  LLM vocabulary.** The registry has 129 useful entries with names
  like `icon/chevron-right` and `button/primary`; right now the LLM
  sees one line: "screen: default (204 instances)". This is the
  "Mode 1 starvation" that falls out directly from the plan's
  "LLM doesn't see what the DB knows" framing.

## Artefacts location

All 12 subdirectories under
`experiments/00-vanilla-baseline/artefacts/` contain:

- `prompt.txt`, `component_list.json`, `llm_raw_response.txt` (the
  JSON tip I emitted as the substitute parser)
- `ir.json`, `token_refs.json`, `warnings.json`, `script.js`
- `render_result.json`
- `notes.md` — per-prompt automated factual summary (no ratings)

11 of 12 directories also have `FAILURE.md` describing the
"object is not extensible" failure mode. Only `09-drawer-nav` has
`walk.json` + `rendered_node_id.txt`.

Cross-cutting artefacts at the experiment root:
- `activity.log` — timestamped log of every pipeline step
- `system_prompt.txt` — the exact prompt the pipeline builds for
  the LLM
- `analysis.json` — the structured roll-up the memo draws on
- `run_summary.json` — per-prompt completion summary
- `run_experiment.py`, `analyze.py`, `write_failure_files.py` —
  reproducibility
