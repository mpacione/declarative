# Plan — M7 Catalog Taxonomy Alignment (CLAY + ARIA)

**Status:** SPEC, deferred — non-blocking strategic finding from the annotation-tool research pass.
**Authored:** 2026-04-20 (autonomous research pass via Sonnet subagent).
**Trigger to revisit:** after M7.0.a finishes (review sprint + rule v2) but before M7.0.b/c scale to the full 48-type catalog; or anytime we consider releasing a dataset.

---

## 1. The finding

Our `component_type_catalog` has **48 canonical types** (button, icon, card, heading, list_item, bottom_nav, etc.). The annotation-tool research pass identified two public taxonomies we almost-completely align with:

- **CLAY (Google Research, 2022)** — 25 component types explicitly curated to merge visually-similar Rico classes. The cleanest public component taxonomy. Names: `ROOT, BACKGROUND, IMAGE, PICTOGRAM, BUTTON, TEXT, LABEL, TEXT_INPUT, MAP, CHECK_BOX, SWITCH, PAGER_INDICATOR, SLIDER, RADIO_BUTTON, SPINNER, PROGRESS_BAR, ADVERTISEMENT, DRAWER, NAVIGATION_BAR, TOOLBAR, LIST_ITEM, CARD_VIEW, CONTAINER, DATE_PICKER, NUMBER_STEPPER`.
- **W3C WAI-ARIA widget roles** — ~35 document + widget roles. The *de jure* web accessibility standard.

Our 48 types are a near-superset of CLAY: `button`, `card`, `list_item`, `navigation_row` ≈ `NAVIGATION_BAR`, `container`, `text`, `heading` ≈ `LABEL/TEXT`, etc.

## 2. Why this matters

Two concrete wins from aligning:

**(A) Classifier prompt alignment.** Our vision classifiers use Sonnet and Haiku. These models were trained on text that uses ARIA role names + CLAY-style component names (because both appear extensively in web + mobile UI documentation). When we ask Claude to classify a node as `navigation_row`, we're asking it to map from its internal `NAVIGATION_BAR` / `nav` / ARIA `navigation` concepts. Using our project-native name adds a translation step; using the industry-standard name removes it.

Expected impact: +3-5 points of baseline classifier accuracy, no code changes. Just rename the catalog entries and re-run.

**(B) Dataset release / second-project portability.** If we eventually share a dataset (for research, customer-facing docs, second-project validation), using CLAY + ARIA vocabulary means it slots into the existing Rico / CLAY / Enrico ecosystem rather than being a 49th incompatible naming scheme. Makes M7 work citable + useful to others.

## 3. Proposed migration

### 3a. Alias map (zero-code, reversible)

Create `dd/catalog_aliases.yaml`:

```yaml
# CLAY-aligned external names → our internal canonical_name.
# The alias layer is additive; existing code keeps working with
# the internal names. Renaming to external names happens in a
# single migration at M7.0-sign-off time.
navigation_bar: navigation_row   # ours
nav: navigation_row
toolbar: header                   # our `header` maps to CLAY's TOOLBAR
card_view: card
pictogram: icon                   # CLAY's PICTOGRAM = our `icon`
progress_bar: progress            # ours
pager_indicator: pagination
label: text                       # CLAY's LABEL = our `text` at display size
# ARIA roles aliasing our types
button: button                    # identical
link: link
textbox: text_input
checkbox: checkbox
radio: radio
slider: slider
menuitem: menu_item               # if we have menu_item
listbox: list
option: list_item
combobox: select
tab: tab
tabpanel: tab_panel
```

Alias layer deploys alongside the catalog; prompts can reference EITHER name. LLM + vision prompts gain "(aliases: foo, bar)" text in the catalog description so the model sees both.

### 3b. Catalog rename (the bigger step)

One atomic renaming migration:
- `navigation_row` → `navigation_bar` (matches CLAY)
- `header` → `toolbar` (CLAY + ARIA)
- OR: keep internal names; use aliases only in prompts + exports.

**Recommendation:** don't rename. Aliases are enough. Our internal names are already working for the code path; breaking FK relationships and `canonical_type` strings in `screen_component_instances` + `component_type_catalog` + 49K rows is more risk than upside. Aliases capture the strategic win (prompt alignment) without the migration cost.

## 4. Concrete next steps

If we adopt this plan:

1. Audit our 48 types against CLAY's 25. Document each mismatch (what ours adds beyond CLAY; what CLAY has that we don't). ~1 hour.
2. Add `aliases_yaml` column to `component_type_catalog` OR create the YAML file + load at runtime. ~1 day.
3. Wire aliases into the vision + LLM prompts (show "button (alias: BTN, btn)" style). Re-run on a 10-screen dry-run to measure accuracy delta. ~1 day + ~$1 API budget.
4. If +3 points → adopt. If flat → file under "nice to have for dataset-release milestone."

## 5. Out of scope

- Renaming the catalog entries in the DB (reversibility cost is real; aliases capture 90% of the value).
- CLAY dataset import (they ship an annotation format; we'd evaluate later if multi-source classification becomes interesting).
- Absorbing CLAY's 25 types that we DON'T have (e.g., `PAGER_INDICATOR`, `SPINNER`). Add to catalog only when we hit a real node that needs one of them.

## 6. Source

Research subagent pass 2026-04-20 surfaced:
- CLAY label_map: https://github.com/google-research-datasets/clay/blob/main/label_map.txt
- Rico semantic annotations: https://github.com/google-research-datasets/rico_semantics
- ARIA widget roles: https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/widget_role

Also: Google Research's Spotlight paper (arXiv 2209.14927) is the specific reference for the bbox-visualisation improvement we shipped alongside this document — same research provenance.
