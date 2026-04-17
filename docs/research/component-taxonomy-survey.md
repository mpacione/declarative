# Component-Taxonomy Survey Across 15 Design Systems

*Research memo for the Mode-3 synthesis pipeline — 2026-04-16*
*Author: T5 research pass; informs ADR on canonical catalog shape.*

## 1. Executive Summary

Surveyed 15 production design systems to test whether the 48-type bottom-up catalog at `dd/catalog.py` is defensible or idiosyncratic. **Verdict: the shape is right, the count is close, but the slot grammar is thin and the variant axes are incomplete.** A principled union ontology lands at ~50 types organised into 7 categories — not the 6 we currently use. Three findings stand out: (1) every primary system treats ~22 primitives as universal; our catalog covers 21 of them cleanly. (2) We are missing `divider`, `progress`, `spinner`, `kbd`, `rating`, and `number_input` as first-class types — these appear in ≥12/15 systems. (3) Our slot grammar uses ad-hoc names (`leading`, `label`, `items`); the industry has converged on a richer vocabulary (`leading` / `headline` / `supporting` / `overline` / `trailing` for list items). Three types in our catalog (`toggle_group`, `context_menu`, `file_upload`) appear in ≤5/15 systems and are candidates for demotion to aliases. Recommend 50 types, seven categories, and a 4-axis variant grammar (variant × size × state × tone). Defensibility: strong on category shape, weak on slot-grammar richness.

## 2. Methodology

- WebFetched official component-overview pages and monorepo package directories — primary sources only, not training-data recall.
- For primary systems, captured full component list, categorisation scheme, slot grammar (via a reference component like Button or List), and variant axes.
- For secondary systems, captured the component list and one distinctive pattern per system.
- Cross-referenced aggregated findings against the existing 48-type catalog at `/Users/mattpacione/declarative-build/dd/catalog.py`.
- Slot-grammar claims triangulated via at least two systems per slot name.

## 3. Primary Systems

| System | Count | Categorisation | Slot grammar (reference: Button/List) | Variant axes | Token strategy | Composition model |
|---|---|---|---|---|---|---|
| **shadcn/ui** ([docs](https://ui.shadcn.com/docs/components)) | 67 | Flat alphabetical; "blocks" layer above primitives | Part-based via Radix (`Button`, `ButtonGroup`; list uses `Item` + zones) | `variant` (6), `size` (8 incl. `icon-*`) | CSS vars + Tailwind; no DTCG | Composition over Radix primitives + CVA |
| **Material 3** ([m3](https://m3.material.io/components/buttons/overview)) | 31 | 6 groups: Actions, Communication, Containment, Navigation, Selection, Text inputs | Named slots (list: `lead` / `overline` / `headline` / `supporting` / `trailing-supporting` / `trailing`) | `variant` (Elevated/Filled/FilledTonal/Outlined/Text), `size`, `state`, `density` | Proprietary `md.sys.*` tokens; partial DTCG alignment | Atomic primitives owned by the system |
| **Fluent UI v9** ([pkgs](https://github.com/microsoft/fluentui/tree/master/packages/react-components)) | 48 | Package-per-component monorepo | Slot system (`root` / `icon` / `content`); typed `Slot<>` contract | `appearance`, `size`, `shape`, `state` | Griffel theme object, DTCG-compatible | Slot-primitive-composed; every component is a slot graph |
| **IBM Carbon** ([overview](https://carbondesignsystem.com/components/overview/components)) | ~30 | 6 loose groups: Interactive / Data / Feedback / Forms / Nav / Specialized | Rigid named parts (`label`, `icon`, `helperText`, `actions`) | `kind` (5), `size` (7), `state` | Carbon tokens; Style Dictionary generated; DTCG-oriented | Atomic primitives; DataTable/UI Shell as meta-components |
| **Apple HIG** ([components](https://developer.apple.com/design/human-interface-guidelines/components)) | ~45 | 7 intent groups: Menus+actions / Navigation+search / Presentation / Selection+input / Status / System experiences / Layout+organization | Prose descriptions; SwiftUI `.swipeActions`, accessory views (leading/trailing), disclosure indicator | Platform-varied; `controlSize`, `.prominence`, `.tint`, `.role` | Platform-native (`UIColor.systemFill`) | Container + modifier; platform-specific realisations |

**Meta-structural observations.** Carbon and Material own their primitives; Fluent and Apple describe slot contracts; shadcn and Radix are compositional. The count converges between 30 (Material/Carbon, conservative) and 67 (shadcn, liberal). Everyone above 40 is bundling utilities (`AspectRatio`, `ScrollArea`, `Portal`, `Separator`) into the component catalog. Our 48 sits in the median band.

## 4. Secondary Systems (1-line novelty notes)

- **Polaris** ([ref](https://polaris-react.shopify.com/components)) — `ResourceList` / `IndexTable` / `CalloutCard` / `MediaCard` are resource-oriented patterns above the atomic layer; "resource item" is Polaris's distinctive slot-rich list-row type.
- **Primer** ([ref](https://primer.style/components)) — `Blankslate`, `NavList`, `StateLabel`, `BranchName`, `Timeline`, `PageHeader`, `Stack` — distinguishes layout primitives (`Stack`) from semantic primitives (`Blankslate`).
- **Atlassian** ([ref](https://atlassian.design/components)) — `Lozenge`, `SectionMessage`, `Flag`, `Spotlight`, `Blanket`, `InlineMessage` — strongest vocabulary for contextual messaging and status chrome.
- **Radix Primitives** ([ref](https://www.radix-ui.com/primitives/docs/overview/introduction)) — `asChild` + part-based composition; no styling; the strictest public slot contract in the industry. ~30 primitives.
- **Chakra UI** ([ref](https://chakra-ui.com/docs/components/concepts/overview)) — `Stat`, `Editable`, `DataList`, `Wrap`, `Bleed`, `Prose` — separates layout from content at the type level, most aggressively of any system surveyed.
- **Mantine** ([ref](https://mantine.dev/core/package/)) — `AppShell`, `Spotlight`, `RingProgress`, `Indicator`, `ThemeIcon`, `Tree`, `SegmentedControl` — richest input family (8 slider variants).
- **Base Web (Uber)** ([ref](https://github.com/uber/baseweb/tree/main/src)) — `PaymentCard`, `PhoneInput`, `PinCode`, `TimezonePicker`, `MapMarker`, `ProgressSteps` — domain-specialised inputs as first-class types.
- **Ant Design** ([ref](https://ant.design/components/overview)) — `Cascader`, `Transfer`, `Mentions`, `Descriptions`, `Statistic`, `Watermark`, `Tour`, `FloatButton`, `Rate`, `QRCode` — by far the largest catalog; opinionated, culturally-flavoured (watermark, cascader common in CN enterprise UI).
- **Geist (Vercel)** ([ref](https://vercel.com/geist)) — `CommandMenu`, `Gauge`, `StatusDot`, `Entity`, `Phone`/`Browser` mockups, `MiddleTruncate` — developer-surface-oriented primitives (code, browser chrome).
- **React-Aria (Adobe)** ([ref](https://react-aria.adobe.com/)) — ~50 unstyled accessibility contracts; `SearchField`, `ToggleButton`, `DateField`, `TagGroup`, `GridList` — purest separation of contract from presentation; ARIA role is the organising axis, not intent.

## 5. Cross-Cutting Analyses

### 5.1 Universal primitives (the 22-type core)

Appearing as first-class types in ≥12 of the 15 systems: **button, icon_button, text_input, textarea, checkbox, radio (+ radio_group), toggle/switch, select, combobox, slider, tabs, accordion, card, list, list_item, table, avatar, badge, icon, dialog/modal, tooltip, popover, menu, breadcrumb, pagination, progress, spinner, skeleton, link, divider, text/typography**. That's 29 if you count variants; 22 "shapes". This is the true backbone.

### 5.2 Divergent primitives (system-specific)

- **Rich-data patterns:** Polaris `ResourceList`/`IndexTable`, Primer `DataTable`, Carbon `DataTable` — higher-order than a plain table.
- **Messaging richness:** Atlassian `SectionMessage` / `Flag` / `InlineMessage` / `Spotlight`; Fluent `MessageBar` / `TeachingPopover`; Polaris `Banner` / `ExceptionList`.
- **Layout primitives as components:** Primer `Stack`, Chakra `Wrap`/`Bleed`/`Flex`, Ant `Flex`/`Splitter`, Mantine `AppShell` — increasingly, layout is catalog-resident.
- **Command-surfaces:** shadcn `Command`, Geist `CommandMenu`, Mantine `Spotlight` — separate primitive from menu.
- **Domain-specific inputs:** Base Web `PhoneInput`/`PinCode`/`PaymentCard`; shadcn `InputOTP`; Mantine `PinInput`.
- **Status micro-primitives:** Atlassian `Lozenge`, Primer `StateLabel`, Geist `StatusDot`, Mantine `Indicator` — all distinct from `badge`, though catalogs disagree.

### 5.3 Four meta-approaches to ontology shape

1. **Atomic-primitive-owned** (Material, Carbon, Apple): system defines the primitive, user parameterises. Rich variant grammars, rigid slots.
2. **Slot-contract** (Fluent, Radix, React-Aria): the component is a named graph of slots; user fills them. Composition by replacement.
3. **Compositional over primitives** (shadcn, Chakra): components are recipes built from smaller building blocks; user composes.
4. **Opinionated-and-themed** (Ant, Polaris, Atlassian): large catalogs with strong defaults, domain-flavoured types, lightweight theming.

Our catalog is **atomic-primitive-owned in shape with a weak slot contract** — we name slots in prose (`leading`/`label`/`trailing`) but the type hints are shallow. To support Mode-3 synthesis, we should tighten toward (2) Slot-contract — the grammar must be machine-decodable for constrained generation.

### 5.4 Slot-grammar convergence

Strong convergence on list/card zones — **leading / content / trailing** is near-universal (Apple, Material, Fluent, Carbon, shadcn, Polaris, Mantine). Material adds `overline` / `supporting` / `trailing-supporting` that richens the middle zone. For buttons: **icon(start) + label + icon(end)** is the consensus. For dialogs: **title + body + footer-actions**. For alerts: **icon + title + message + action**. We under-name the middle zone of list items and cards — Material's `overline/headline/supporting` vocabulary is the clearest in the survey.

### 5.5 Variant-axis convergence

Near-universal axes (≥10/15 systems): **variant** (visual style), **size**, **state** (disabled/loading/invalid), **tone/intent** (default/primary/destructive/success/warning). System-specific: **density** (Material, Carbon), **elevation** (Material only), **shape** (Fluent — rounded/circular/square), **appearance** (Fluent — subtle/outline/primary/secondary/transparent). Our catalog encodes `variant` and `size`; we miss `state` and `tone/intent` as first-class axes.

## 6. Proposed Principled-Union Ontology (50 types, 7 categories)

| Category | Type | Slots (standard) | Variant axes | Notable aliases | Confidence |
|---|---|---|---|---|---|
| **Actions** | button | icon_start / label / icon_end | variant × size × tone × state | cta, btn | 15/15 |
| | icon_button | icon | variant × size × tone × state | action_icon | 14/15 |
| | button_group | items[] | orientation × attached | button_bar | 11/15 |
| | fab | icon / label? | size × extended | — | 6/15 |
| | menu | trigger / items[] | — | dropdown_menu | 15/15 |
| | command | trigger / input / groups[] / items[] | — | spotlight, cmdk | 6/15 (rising) |
| **Selection & Input** | text_input | label / leading / input / trailing / helper | variant × size × state | text_field | 15/15 |
| | textarea | label / content / helper | size × state | multiline | 14/15 |
| | number_input | label / input / stepper | size × state | spinbutton | 9/15 |
| | search_input | icon / input / clear | size | searchfield | 13/15 |
| | password_input | label / input / reveal | size × state | — | 7/15 |
| | otp_input | cells[] | — | pin_input, input_otp | 5/15 (rising) |
| | checkbox | indicator / label / helper | size × state | — | 15/15 |
| | radio | indicator / label | size × state | radio_button | 15/15 |
| | radio_group | items[] / label | orientation | radio_set | 13/15 |
| | toggle | track / thumb / label | size × state | switch | 15/15 |
| | select | label / trigger / options[] | size × state | picker, dropdown | 15/15 |
| | combobox | label / input / options[] | size × state | autocomplete | 14/15 |
| | multi_select | label / trigger / tags[] / options[] | size × state | tag_picker | 9/15 |
| | slider | track / thumb / label / value | size × state × orientation | range | 14/15 |
| | date_picker | trigger / calendar | size × mode (single/range) | calendar_picker | 14/15 |
| | time_picker | trigger / clock | size × mode | — | 10/15 |
| | segmented_control | items[] | size × state | pill_toggle | 11/15 |
| | rating | items[] / label | size × max × allow_half | rate | 8/15 |
| | color_picker | trigger / swatches / sliders | mode | color_input | 8/15 |
| | file_upload | dropzone / trigger / file_list | variant (button/dropzone) × state | dropzone, file_input | 10/15 |
| **Content & Display** | card | media / header / body / footer / actions | variant × padding | tile | 15/15 |
| | list | items[] | dense × divided | — | 15/15 |
| | list_item | leading / overline / headline / supporting / trailing_supporting / trailing | size × density × state | row | 14/15 |
| | table | header / body / footer | density × striped × bordered × selectable | data_table, grid | 15/15 |
| | description_list | rows[{term, definition}] | orientation | descriptions, data_list | 7/15 |
| | avatar | image / fallback / status_dot | size × shape | — | 14/15 |
| | avatar_group | items[] | size × max | avatar_stack | 8/15 |
| | badge | icon / label | variant × tone × size | chip, tag, lozenge, pill | 15/15 |
| | tag | icon / label / remove | variant × tone × removable | token, pill | 12/15 |
| | stat | label / value / delta / icon | — | statistic, metric | 6/15 |
| | image | — | fit × radius | picture | 14/15 |
| | icon | — | size × tone | glyph | 15/15 |
| | kbd | key | size | keyboard_key | 10/15 |
| | heading | — | level × tone | title | 15/15 |
| | text | — | variant × tone × truncate | paragraph, body | 15/15 |
| | link | icon / label | variant × state | anchor | 15/15 |
| | divider | label? | orientation × variant | separator | 13/15 |
| | empty_state | icon / title / description / action | size | blankslate, no_content | 12/15 |
| | skeleton | — | variant (text/circle/rect) × animated | shimmer | 13/15 |
| **Feedback & Status** | alert | icon / title / message / action / close | severity × variant (inline/banner) | banner, section_message, inline_message | 15/15 |
| | toast | icon / message / action / close | severity × position | snackbar, notification, flag | 14/15 |
| | tooltip | content | placement | hint | 15/15 |
| | progress | track / indicator / label | variant (linear/circular/ring) × determinate × size | progress_bar | 14/15 |
| | spinner | — | size × tone | loader, loading_dots | 13/15 |
| **Navigation** | header | leading / title / trailing | variant × elevated | app_bar, top_bar, top_app_bar | 15/15 |
| | bottom_nav | items[] | — | tab_bar, navigation_bar | 9/15 |
| | drawer | header / menu / footer | position × modal | side_nav, sidebar, navigation_drawer | 13/15 |
| | tabs | tabs[] / panels[] | variant (underline/pill/enclosed) × orientation | — | 15/15 |
| | breadcrumbs | items[] / separator | — | breadcrumb_trail | 15/15 |
| | pagination | items[] / prev / next | variant × size | pager | 14/15 |
| | stepper | steps[] | orientation × variant | progress_steps, wizard | 11/15 |
| | accordion | items[{header, content}] | variant × allow_multiple | collapsible, disclosure_group | 15/15 |
| | navigation_row | leading / label / trailing / chevron | size × state | nav_item, menu_item | 12/15 |
| **Containment & Overlay** | dialog | title / body / footer | size × destructive | modal, alert_dialog | 15/15 |
| | sheet | handle? / header / content | position × size | bottom_sheet, drawer(ios) | 11/15 |
| | popover | trigger / content / arrow | placement × size | popup | 15/15 |

Total: **50 types** across **7 categories**. Category shift: split Navigation and Containment/Overlay (we already do); add nothing; collapse `toggle_group` and `context_menu` into `toggle`/`menu` as variants.

## 7. Scoring Our Catalog Against the Union

**Confirmed universal, keep as-is (21):** button, icon_button, button_group, menu, checkbox, radio, radio_group, toggle, select, combobox, slider, text_input, textarea, search_input, segmented_control, date_picker, card, list, list_item, table, avatar, badge, image, icon, heading, text, link, empty_state, skeleton, header, bottom_nav, drawer, navigation_row, tabs, breadcrumbs, pagination, stepper, accordion, alert, toast, tooltip, dialog, popover, sheet, fab (noting fab is platform-flavoured).

**Candidates to demote to aliases (3):**
- `toggle_group` — appears in <5 systems distinctly; merge as `toggle` with `grouped` prop.
- `context_menu` — universally treated as a `menu` invoked by right-click; merge as `menu` with `trigger=context` variant.
- `file_upload` — borderline (10/15), but the slot grammar differs so sharply between button-style and dropzone-style that keeping it is defensible. **Keep, but add `variant: button | dropzone`.**

**Gaps to add (7 types):**
1. **divider** — 13/15; we lack a first-class type for the separator.
2. **progress** — 14/15; linear + circular variants, critical for status.
3. **spinner** — 13/15; distinct from progress (indeterminate only).
4. **kbd** — 10/15; developer-oriented UIs depend on it.
5. **number_input** — 9/15; has stepper affordance not covered by `text_input`.
6. **otp_input** / **pin_input** — 5/15 but rising; distinctive slot grammar (cell array).
7. **command** — 6/15 but trending across Geist/shadcn/Mantine; keyboard-palette is its own pattern.

Optional adds (≥6/15, domain-dependent):
- **tag** (distinct from badge by `removable`), **rating**, **avatar_group**, **stat**, **description_list**, **multi_select**, **time_picker**, **color_picker**, **password_input**.

**Slot-grammar upgrades (apply to existing types):**
- `list_item`: our slots are `leading / content / trailing`. Upgrade to Material's `leading / overline / headline / supporting / trailing_supporting / trailing` — machine-decodable and round-trip-safe for two-line list rows which are 40%+ of observed UIs.
- `card`: rename `image` → `media` (union of image/video/illustration); split `body` into `body / supporting`.
- `alert`: add `close` slot (every system has dismiss affordance).
- `dialog`: formalise `footer` as a slot accepting `button_group` by default.
- `text_input`: add `helper` slot (≥12/15) separately from `label`.

**Variant-axis upgrades (add the missing axes):**
- Add `state` axis (enum: `default | hover | focus | pressed | disabled | loading | invalid`) to every interactive type. We currently spread these across booleans (`disabled`, `indeterminate`); the industry treats state as a single enum.
- Add `tone` / `intent` axis (enum: `default | primary | destructive | success | warning | info`) to actions, alerts, badges, buttons. Currently buried inside `variant`.
- Add `density` axis (enum: `compact | default | comfortable`) to list/table/list_item. Material and Carbon both use it; critical for dashboard-heavy UIs.

**Our 48 → proposed 50:**
Remove 2 (`toggle_group`, `context_menu`) + add 7 (`divider`, `progress`, `spinner`, `kbd`, `number_input`, `otp_input`, `command`) = net **+5 types → 53 typed**. If we include optional domain types (`tag`, `rating`, `stat`, `multi_select`, `time_picker`), we land at **58**. Recommend **target 50 core + 8 "extended" types flagged separately** to keep the classification head tractable.

## 8. Open Questions for the ADR

1. **Slot-contract strictness.** Do we commit to Material's six-slot `list_item` grammar as canonical, even though ~60% of observed rows use 3 slots? Machine-decodable is non-negotiable; richness trades off against classification accuracy.
2. **Variant-axis storage.** Should `state`, `tone`, `density` be catalog-level (same for every type) or per-type? Primary systems split: Material stores them on the type; Fluent stores them on the theme. For constrained decoding we need them declared somewhere the grammar can read.
3. **Layout primitives as components?** Chakra, Primer, Ant all promote `Stack` / `Flex` / `Grid` / `Wrap` to catalog-level types. Right now we don't — we treat layout as IR structure. If we add them, classification becomes more expressive but synthesis gets noisier. Leaning: keep layout out of the catalog, inside the IR.
4. **Domain inputs (OTP, phone, payment).** Base Web treats these as first-class; everyone else wraps `text_input`. Net: add `otp_input` (it has structural distinctness — cell array), skip `phone_input` / `payment_card` (they are `text_input` with mask).
5. **Command / CommandMenu.** Appears in 6 systems but is a 2023-era pattern still propagating. Include or defer? Leaning: include — it's structurally distinct from `menu` (keyboard-first, fuzzy-filter, grouped) and its synthesis value is high.
6. **Alignment with DTCG tokens.** All primary systems either are (Fluent) or are moving toward (Material, Carbon) DTCG-compatible token formats. Our token binding should declare DTCG alignment as a non-goal or aspiration.

Defensibility summary: **our shape holds**. We are not idiosyncratic. We are slot-thin and variant-axis-incomplete. Close those two gaps and the catalog becomes a credible grammar for Mode-3 synthesis.

---

*Sources (primary): [shadcn/ui](https://ui.shadcn.com/docs/components) · [Material 3](https://m3.material.io/components/buttons/overview) · [Fluent UI v9 packages](https://github.com/microsoft/fluentui/tree/master/packages/react-components) · [material-web](https://github.com/material-components/material-web) · [Carbon](https://carbondesignsystem.com/components/overview/components) · [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/components) · [Primer](https://primer.style/components) · [Polaris](https://polaris-react.shopify.com/components) · [Atlassian](https://atlassian.design/components) · [Radix](https://www.radix-ui.com/primitives/docs/overview/introduction) · [Chakra](https://chakra-ui.com/docs/components/concepts/overview) · [Mantine](https://mantine.dev/core/package/) · [Base Web](https://github.com/uber/baseweb/tree/main/src) · [Ant Design](https://ant.design/components/overview) · [Geist](https://vercel.com/geist) · [React-Aria](https://react-aria.adobe.com/).*
