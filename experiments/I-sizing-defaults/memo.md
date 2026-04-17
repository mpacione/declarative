# Experiment I — per-canonical-type sizing defaults

**Goal.** Derive default sizes per catalog type from the Dank corpus
so the pipeline has something concrete to fall back to when no exemplar
is retrievable. Wave 1.5 v3 showed 212/229 non-screen nodes rendering
at Figma's `createFrame()` default of 100×100 because synthetic IR has
no sizing fall-through.

**Method.** Classified all 79,833 nodes on Dank's 204 `app_screen`s via
`derive_canonical_type` (name-match against the 48-type catalog +
aliases) with `apply_heuristic_rules` as a fall-through for TEXT and
generic frames. This replicates what `screen_component_instances` would
contain — the SCI table is empty because the formal classification
stage hasn't been run on this extraction. For each type, computed
median/mean/stdev/p25/p75/p95 width and height, sizing-mode
distribution, aspect-ratio distribution, and per-variant breakdown
(variants = first `/`-segment after the type prefix, e.g.
`button/small/solid` → variant `small`). Types with <10 instances get
`data: insufficient`.

## 1. Coverage

**12 of 48** catalog types have ≥10 Dank instances. Two non-catalog
classifications — `system_chrome` (2,256) and `container` (1,760) —
also cleared the threshold and are appended as a bonus section.

| Type | Count | Source |
|---|---|---|
| icon | 15,965 | name match (`icon/*`) |
| text | 9,098 | heuristic (font_size 8-18) |
| button | 8,440 | name match (`button/*`) |
| heading | 2,608 | heuristic (font_size ≥ 18) |
| image | 816 | name match (alias `logo/*`) |
| tabs | 205 | name match (`tabs/*`) |
| header | 204 | name match |
| card | 172 | name match (`card/*`) |
| drawer | 135 | name match (alias `Sidebar` — see §3) |
| badge | 66 | name match (alias `Label`) |
| slider | 51 | name match (`Slider`) |
| button_group | 12 | name match (`button set - leading/trailing`) |

**36 of 48** types have zero matches — including `avatar`, `checkbox`,
`text_input`, `list_item`, `toggle`, `dialog`. Dank doesn't name these
as top-level components; any real checkbox/toggle/input is nested
inside larger composites. Name-matching cannot recover them.

## 2. Bimodal / multi-modal distributions

Two types split meaningfully and get `variants:` entries:

- **button** — bimodal at (40×40, `small`, 3,323 instances, 39%) vs
  (48×52, `large`/default, 3,644 instances, 43%). The 40×40 cluster
  is functionally an icon-button. Two further distinct variants:
  `toolbar` (296×60, HUG/HUG) and `slider` button (340×22, FILL/FIXED).
- **icon** — 70+ glyph variants all at 20×20, with a few at 30×30 and
  40×40 for device-specific icons. Variants are suppressed in the YAML
  because they carry glyph identity, not sizing information.

Types with clean single modes: `header` (width tracks device —
428/834/1536 — height always 111), `tabs` (489×44), `slider` (340×22),
`badge` (39×24).

## 3. Most surprising distribution

**`drawer` is an alias-hijack.** The catalog aliases "sidebar" as a
synonym for `drawer`. In Dank, "Sidebar" is an *instance* of the
`New Folder` component — a sidebar-toggle icon button — appearing 135
times at exactly 31×22 px. This dominates the `drawer` classification,
producing a 31×22 default that would render as a pixel sliver instead
of a side panel.

A second hijack: `image` matches only `logo` / `logo/dank` instances
(24×24 median). Useful as a logo default; wrong as a photo default.
Real photos in Dank are named `image 326`, `image-box`, etc. and fall
into UNKNOWN because the suffix breaks strict name-matching. Both are
flagged with `note:` fields in `defaults.yaml`.

## 4. Good enough, or exemplars?

**Honest answer: enough for cold-start, not enough to replace retrieval.**

For **button, icon, heading, text, header, tabs** (together ~37K of
38K sufficient-data instances) the distributions are tight enough that
the median is a real, defensible default. A synthetic `{type: "button"}`
falling through to width:48 height:52 sizing_h:HUG renders plausibly.
This is the v0.1 win — it unambiguously beats 100×100.

For **card** (428×328, HUG/HUG) the defaults are Dank-convention-
specific: "card" in Dank means a full-width modal/sheet body, not a
compact product tile. The `screen_width_ratio_median=0.513` flag warns
this is an iPhone-form-factor median. Other projects' "card" won't
look like this. Retrieval exemplars are load-bearing here.

For the **36 missing types**, mid-averaging isn't an option — no data.
Pipeline needs Exp H's public-system defaults (shadcn, Material,
Fluent) merged in, or must refuse synthesis for those types.

**v0.1-ready with caveats.** The 12 sufficient entries cover the
cold-start `button/icon/text/heading/header/tabs` cases that dominate
realistic prompts. But `drawer` and `image` need the alias-hijack
cleaned up (demote to insufficient), and the 36 zero-count types must
be backfilled from Exp H before the table becomes the single source
of truth.

## 5. Recommendation

- Ship the 7 defensible entries (`button`, `icon`, `text`, `heading`,
  `header`, `tabs`, `badge`) as-is for v0.1. These cover ~96% of the
  non-screen nodes synthetic IR would realistically emit.
- Demote `drawer`, `image`, `slider` to `data: insufficient` in the
  pipeline consumer (even though we have numbers) and merge public-
  system defaults from Exp H.
- Backfill all 36 zero-count types from Exp H before relying on this
  table as the universal fall-through.
- The table format (`value` + `sizing` + `min` + `max` + optional
  `variants`) is the right shape; keep as the v0.1 contract.

**Data sources.** `Dank-EXP-02.declarative.db` (204 app_screens,
79,833 nodes, extracted pt-6). Classification at query time via
`dd.classify_rules` + `dd.catalog.CATALOG_ENTRIES`. Script runs in ~5s.
