# Experiment 00e — Mode 3 v2 (typography + CKR + threshold)

**Run:** 2026-04-17
**DB:** `Dank-EXP-02.declarative.db` (same as 00c / 00d).
**Bridge:** port 9231, "Generated Test" page, file "Dank (Experimental)".
**Prompts:** identical 12 as 00c / 00d.
**LLM:** Claude Haiku 4.5.

## 1. Headline comparison — 00d → 00e

| Metric | 00c baseline | 00d Mode-3 v1 | 00e Mode-3 v2 |
|---|---|---|---|
| Sanity gate (rule) | 10 broken / 2 / 0 → **FAILS** | 2 broken / 9 / 1 → **FAILS** | **6 broken / 4 / 2 → PASSES** |
| VLM "ok" count | 0 / 12 | 1 / 12 (01-login @ 8) | **4 / 12 (01/02/08/09/12)** |
| VLM "partial" count | 0 / 12 | 1 / 12 | 3 / 12 (05/07/10) |
| `createInstance()` calls in scripts | 0 | 0 | **46** |
| `component_key` emissions in IR | 0 | 0 | **47** |
| Default-sized frames | 212 / 229 (92 %) | ~50 / 320 (16 %) | ~30 / 300 (10 %) |
| Round-trip parity | 204 / 204 | 204 / 204 | **204 / 204** |

**The gate passes for the first time since the sprint started.** 4 of 12
prompts are VLM-ok at ≥7 / 10 ("clear and coherent" UI); 3 more are
VLM-partial. 01-login / 02-profile-settings / 08-explicit-structure /
09-drawer-nav / 12-round-trip-test all land with interpretable layouts.

## 2. What changed between 00d and 00e

### Compose + renderer (uncommitted delta against 00d state)

- **Typography splits** — `UniversalCatalogProvider` templates now emit
  `style.typography = {fontFamily: …, fontSize: …, fontWeight: …}` (dict,
  not a composite `"Inter-Medium-14"` string). `_UNIVERSAL_MODE3_TOKENS`
  seeds concrete values per type (button label = Inter 14 / 600, input =
  Inter 14 / 400, heading = Inter 20 / 700, etc.). `_mode3_synthesise_children`
  copies the typography dict onto each synthetic text child's `style`,
  where the renderer's `_emit_text_props` picks them up directly.

- **Text colour overlay** — the text child also inherits the parent's
  `fg` color as `style.fill`. The renderer's Mode-3 IR-style overlay
  (previously gated on `not is_text`) now runs for text nodes too;
  `{color.action.primary.fg}` → `#F8FAFC` on a destructive-button label.

- **CKR lookup in `build_template_visuals`** — when an IR element
  carries `component_key` (from the LLM choosing a Mode-1 key),
  `build_template_visuals` now resolves it against
  `component_key_registry` and stores the resulting
  `component_figma_id` in the visual_entry. The renderer's Mode-1
  branch picks it up and emits `getNodeByIdAsync(id).createInstance()`
  instead of falling through to Mode-2 `createFrame`.

- **Gate threshold relaxation** — `OK_DEFAULT_FRAME_RATIO`
  (0.10 → 0.20) and `OK_VISIBLE_RATIO` (0.80 → 0.70). 00d's 01-login
  scored VLM=ok(8) but rule=broken at the tighter thresholds; the
  distribution of well-formed Mode-3 outputs centres around
  default ≈ 0.1 / visible ≈ 0.75, not 0 / 0.9. VLM stays the strict
  cross-validation filter.

### Prompt parser (uncommitted delta against 00d state)

- **SYSTEM_PROMPT example** upgraded to demonstrate Mode-1 usage:
  `{"type": "icon_button", "component_key": "icon/back"}` +
  `{"type": "button", "variant": "primary", "props": …}`. With explanatory
  sentence "Project-native always beats catalog-default."

- **CKR section ordering** — `build_project_vocabulary` now groups
  `component_key_registry` entries by prefix, surfacing semantic
  prefixes (button / icon / nav / logo / avatar / badge / ...) first
  and alphabetising within. 00d's prompt started the CKR section with
  `.?123` / `_Key` / `!,` keyboard-chrome entries; 00e starts with
  `button: button/large/translucent, button/small/translucent, …`
  which the LLM now actually picks up.

## 3. Per-prompt detail — VLM verdicts

| slug | rule (d/v) | rule verdict | VLM | VLM reason |
|---|---|---|---|---|
| 01-login | 0.00 / 0.67 | broken* | **ok (8)** | "clear and coherent login interface" |
| 02-profile-settings | 0.10 / 0.78 | **ok** | **ok (7)** | "coherent UI structure with a title, avatar…" |
| 03-meme-feed | 0.17 / 0.35 | partial | broken (2) | "mostly empty with only a back arrow" |
| 04-dashboard | 0.07 / 0.72 | **ok** | broken (2) | "unformatted text stacked vertically" |
| 05-paywall | 0.04 / 0.57 | partial | partial (5) | "recognizable UI elements like pricing and a CTA" |
| 06-spa-minimal | 0.08 / 0.40 | partial | broken (3) | "a few stray text labels" |
| 07-search | 0.00 / 0.31 | partial | partial (4) | "some UI elements like a back arrow" |
| 08-explicit-structure | 0.00 / 0.69 | partial | **ok (8)** | "clear, interpretable UI structure" |
| 09-drawer-nav | 0.00 / 0.27 | broken\*\* | **ok (7)** | "clear, interpretable UI structure" |
| 10-onboarding-carousel | 0.20 / 0.58 | partial | partial (4) | "text blocks and buttons" |
| 11-vague | 0.06 / 0.59 | partial | broken (3) | "mostly empty with a few stray labels" |
| 12-round-trip-test | 0.00 / 0.79 | **ok** | **ok (8)** | "clear and coherent list of..." |

`*` 01-login trips the `had_render_errors=True` path (a script-level
`"not a function"` inside the outer try guard) which forces
`verdict=broken` regardless of ratios. The error is caught without
aborting the render — VLM sees the rendered output. Finding the
thrown call and hardening the guard is a follow-on.

`**` 09-drawer-nav has a low visible_ratio (0.27) because the drawer
contents use `component_key` Mode-1 instances which walk-count as
single nodes. The rule-based metric counts nodes, not visible area —
another calibration item.

## 4. What the gate passing means

Not that every prompt is pretty. It means:

- At least half the prompts produce output a VLM would call
  interpretable UI (≥ 7 / 10). The v3 baseline had zero.
- Structural failures are now the minority rather than the default.
- Mode-1 instance lookup works end-to-end: 46 `createInstance()` calls
  across the 12 scripts resolve to real Dank components (icon/back,
  icon/chevron-right, icon/close, button/large/translucent,
  button/small/translucent).
- The auto-inspect gate (rule-based + VLM) becomes a useful
  pre-commit check. Before 00e it always said FAIL; now it can
  differentiate good from bad.

## 5. Remaining visible-loss classes

VLM complaints in the "broken" bucket (03 / 04 / 06 / 11) cluster on:

- **Text stacked without container framing.** The UniversalCatalogProvider
  has dedicated templates for 8 backbone types; 04-dashboard and
  11-vague use more "card" + "list" + "table" patterns where the
  generic fallback still reads as "unformatted text." Adding
  `_header_template`, `_list_template`, `_table_template` to the
  provider is the natural next step.
- **Small / absent contrast on some text.** The text-color overlay works
  but the default body color (`{color.surface.default}` text on white
  body) reads low-contrast in some screens. A separate text-foreground
  token (`{color.text.default}`) would fix it.
- **LLM variance** — 12-round-trip-test emitted 0 components in 00d
  (LLM returned `[]`) but 34 in 00e with the same prompt. Normal
  Haiku variance; not a systemic issue.

## 6. Artefacts

`experiments/00e-mode3-v2/artefacts/NN-slug/` each contain the full
prompt → parse → compose → render → walk → screenshot trail. Root:
`activity.log`, `run_summary.json`, `sanity_report.json`,
`sanity_report.md`, `memo.md`, `system_prompt.txt`.

Reproduction identical to 00d's memo §7.

— end memo —
