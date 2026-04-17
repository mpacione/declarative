# Synthetic generation — deep diagnosis of the visual-failure state

> **Status:** diagnostic memo, 2026-04-16 (session pt 8).
> **Prior memo:** `experiments/00c-vanilla-v3/memo.md` (initial taxonomy).
> **Why this exists:** the v3 memo flagged the symptoms ("212 of 229 nodes
> at 100×100, Mode-2 has no templates") but stopped at symptoms. Before
> ingesting shadcn/ui we wanted to verify the pipeline is wired
> correctly. It isn't. This memo traces every failure mode to its exact
> source in the codebase.

## 0. Executive summary

The synthetic-generation pipeline produces categorically-broken output
(gate: 10/12 rule-based broken, 12/12 Gemini-confirmed broken) **not
because the renderer is bad, but because there is no code path that
turns an LLM component into a structurally-plausible Figma subtree when
the user's corpus does not already contain that component as a known
`component_key`.**

The gap is not "missing component library." It is a missing pipeline
stage. Concretely:

1. The LLM emits `button {text: "Sign In"}` correctly.
2. `compose_screen` preserves `props.text` in the IR correctly.
3. The Figma renderer's Mode-2 branch emits `createFrame()` with
   `fills: []` and no children — **the renderer never consults
   `props.text` for non-text types** (it only routes `props.text` into
   `.characters` when `etype in {"text", "heading", "link"}`).
4. No code path exists that consumes `dd/catalog.py`'s rich
   `slot_definitions` to synthesise an internal subtree.
5. `component_key_registry` is populated (129 rows) but
   `build_project_vocabulary` reads from `component_templates` (1 row)
   so the LLM sees zero project-specific component keys.

There's no single bug. There's a design gap: the renderer was built for
the round-trip case (extracted IR with a `component_key` or with
L0 visual properties copied from the DB) and has no "Mode 3" for
"synthesise from catalog slot definitions + LLM props."

Ingesting shadcn/ui would add more `component_key`s to fall through to,
but until the pipeline can consume those keys (which it currently
can't, because it doesn't surface the CKR to the LLM and doesn't
synthesise Mode-2 internals), shadcn ingestion is premature.

## 1. Methodology

- Re-ran the sanity gate on the v3 artefacts (rule-based + Gemini
  VLM) — 10/12 and 12/12 broken respectively.
- Surveyed all 12 prompts' `ir.json` and `walk.json`: per-type
  frequency, observed `props` keys, `children` presence, rendered
  dimensions.
- Traced one representative prompt (`01-login`) from LLM JSON → IR →
  script, identifying where `props.text` is dropped.
- Audited the relevant DB tables (`component_templates`,
  `component_key_registry`, `screen_component_instances`).
- Audited `dd/catalog.py` for structural metadata (slot_definitions,
  prop_definitions) and checked whether anything in
  `dd/compose.py` or `dd/renderers/figma.py` references them.
- Read the renderer's Mode-2 branch end-to-end to map the emission
  contract.

## 2. Failure taxonomy (from the 12-prompt survey)

Every non-screen element across the 12 prompts, by type, props observed,
and rendered dimensions. (Aggregated via script over the v3 artefacts.)

| Type | Count | Props observed | Children in IR | Rendered size |
|---|--:|---|---|---|
| **heading** | 34 | `text(34)` | 0/34 with | 0/34 @100×100 ✓ |
| **card** | 33 | — | 33/33 with | 0/33 @100×100 |
| **list_item** | 30 | `text(30)` | 0/30 with | **30/30 @100×100** |
| **text** | 24 | `text(24)` | 0/24 with | 0/24 @100×100 ✓ |
| **button** | 23 | `text(23)`, `variant(1)` | 0/23 with | **23/23 @100×100** |
| **image** | 11 | `alt(9)`, `src(6)` | 0/11 with | 11/11 @100×100 |
| **header** | 9 | `text(9)`, `backButton(1)`, `actions(1)` | 0/9 with | 9/9 @100×100 |
| **toggle** | 9 | `label(9)`, `checked(7)` | 0/9 with | 9/9 @100×100 |
| **list** | 7 | — | 7/7 with | 0/7 @100×100 |
| **navigation_row** | 7 | `text(7)` | 0/7 with | 7/7 @100×100 |
| **button_group** | 5 | — | 5/5 with | 0/5 @100×100 |
| **text_input** | 4 | `label(4)`, `placeholder(2)`, `value(2)` | 0/4 with | 4/4 @100×100 |
| **icon_button** | 4 | `text(4)` | 0/4 with | 4/4 @100×100 |
| **pagination** | 3 | `text(2)`, `currentPage(1)`, `totalPages(1)` | 0/3 with | 3/3 @100×100 |
| **avatar** | 2 | `initials(1)`, `text(1)` | 0/2 with | 2/2 @100×100 |
| **segmented_control** | 2 | `options(2)` | 0/2 with | 2/2 @100×100 |
| **link** | 1 | `text(1)` | 0/1 with | 0/1 @100×100 ✓ |
| **badge / fab / empty_state / search_input / select** | 5 | various | 0/5 with | 5/5 @100×100 |
| **table / bottom_nav / drawer / toggle_group** | 4 | — | 4/4 with | 0/4 @100×100 |

Reading the table:

- **Text-typed elements (heading, text, link)** render correctly — the
  `text` / `heading` / `link` types fall into `_TEXT_TYPES` and their
  `props.text` is plumbed to `.characters`. These are the labels you
  see at top-left in every v3 screenshot.
- **Every other type** renders as a 100×100 empty frame, regardless of
  whether it carried a `text`, `label`, `placeholder`, or `options`
  prop. The props are never consumed.
- **Containers that should have children** (`list`, `button_group`,
  `drawer`, `bottom_nav`, `pagination`, `toggle_group`, `table`) are
  emitted by the LLM without children. The LLM's `SYSTEM_PROMPT`
  doesn't teach it which types are containers, only that they exist.
- **Cards render empty** even though they have children because the
  card's own size is still 100×100. Its auto-layout VERTICAL packs
  three 100×100 children into a 100×100 card which overflows the
  screen in vertical space.

## 3. Pipeline trace — where `props.text` goes to die

Using `01-login`'s `button-1` as a concrete example:

### Stage 1 — LLM output

`component_list.json:22-31`:

```json
{"type": "button", "props": {"text": "Sign In"}}
```

Correct. The LLM fulfilled the contract of `SYSTEM_PROMPT` exactly.

### Stage 2 — compose_screen → IR

`ir.json:38-46`:

```json
"button-1": {
  "type": "button",
  "layout": {"direction": "vertical"},
  "props": {"text": "Sign In"}
}
```

Also correct. `compose.py:91-93` does `element["props"] = dict(props)`
— the props pass through intact. **Note: no `children` field.** The
composer never synthesises an internal text child from the prop.

### Stage 3 — generate_figma_script → script.js

`script.js:53-58`:

```javascript
const n7 = figma.createFrame();
n7.name = "button-1";
n7.layoutMode = "VERTICAL";
n7.fills = [];
n7.clipsContent = false;
```

**"Sign In" is gone.** No text child, no characters, no label.

### Where it died

`dd/renderers/figma.py:1326`:

```python
if is_text:   # is_text = etype in _TEXT_TYPES = {"text","heading","link"}
    …
    text_content = element.get("props", {}).get("text", "")
    if text_content:
        text_characters.append((var, escaped, eid))
```

`is_text` is `False` for `button`, so the `props.text` branch is never
entered. The only other code path that could emit child nodes is
`_emit_composition_children` (line 1334):

```python
composition = element.get("_composition")
has_ir_children = bool(element.get("children"))
if composition and not is_text and not has_ir_children:
    _emit_composition_children(var, eid, composition, phase1_lines, idx * 100)
```

`_composition` is only set by `build_template_visuals`
(`compose.py:268`) when a matching template in `component_templates`
carries a `children_composition` field — but there are **no templates
with children_composition** (see §4). So the branch never fires for
synthetic IR.

The button ends up as a bare `createFrame()` with `layoutMode`, empty
fills, and nothing else. Same story for `text_input`, `toggle`,
`list_item`, `navigation_row`, `icon_button`, `avatar`, `badge`,
`fab`, `empty_state`, `search_input`, `select`, `pagination`,
`segmented_control`.

## 4. Data-layer findings

### 4.1 `component_templates` is effectively empty

```
SELECT catalog_type, COUNT(*), SUM(instance_count)
FROM component_templates GROUP BY catalog_type;
=> screen  1  204
```

Exactly one row. Every other catalog type has zero templates. This is
because `extract_templates` (`dd/templates.py`) builds templates by
grouping `screen_component_instances` — and `screen_component_instances`
is also empty (the formal `dd classify` stage hasn't been run on the
Dank DB; the round-trip pipeline doesn't need it).

Consequence: `build_project_vocabulary` reports only `screen: default
(204 instances)` to the LLM. Consumed system-prompt length is
**253 chars, 36 words** — the "vocabulary block" is a no-op.

### 4.2 `component_key_registry` is populated but invisible

```
SELECT COUNT(*) FROM component_key_registry;  => 129
```

Sample rows:

```
('00d2dfc…', '5749:84317', 'ios/alpha-keyboard', 10)
('0164bca…', '5749:82420', 'icon/decap', 16)
('0169c54…', '5749:82149', 'icon/grid-view', 13)
```

129 component keys exist with stable `figma_node_id`s. These are
exactly what Mode-1 needs to `getNodeByIdAsync().createInstance()`.
But nothing surfaces them to the LLM — `build_project_vocabulary` only
reads `component_templates`. **Mode-1 starvation is not because the DB
has no CKR; it's because the existing vocabulary builder ignores CKR.**

### 4.3 `dd/catalog.py`'s slot_definitions are rich and unused

Every catalog entry has a `slot_definitions` field naming its internal
structure. Examples (verbatim):

```python
"button": {
  "slot_definitions": {
    "icon": {"allowed": ["icon"], "required": False, "position": "start", "quantity": "single"},
    "label": {"allowed": ["text"], "required": True, "position": "fill", "quantity": "single"},
    "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"}
  }
}

"text_input": {
  # (checked separately — has label, placeholder, value slots)
}

"icon_button": {
  "slot_definitions": {
    "icon": {"allowed": ["icon"], "required": True}
  }
}

"toggle" / "checkbox" / "radio": {
  "slot_definitions": {
    "label": {"allowed": ["text"], "required": False}
  }
}
```

These structures are exactly what a Mode-3 synthesiser needs: they tell
us "a button is a frame containing a required `text` label and an
optional `icon`."

**Grep for `slot_definitions` in `dd/compose.py` or
`dd/renderers/figma.py`: zero references.** The catalog's structural
knowledge is seeded into the DB's `component_type_catalog` table (via
`seed_catalog`) but never consumed by any pipeline stage after
classification.

### 4.4 Screen root hard-codes `direction: absolute`

`compose.py:106-109`:

```python
screen_layout: dict[str, Any] = {
  "direction": "absolute",
  "sizing": {"width": 428, "height": 926},
}
```

Children then get `position: {x: 0, y: y_cursor}` where `y_cursor`
increments by `child_height` — **or by a hardcoded `50` when the
composer doesn't know the child's height** (`compose.py:132`). Since
it never knows the child's height (no template, no intrinsic sizing
logic for Mode-2), every child lands 50px below the previous one.

That's how `02-profile-settings` puts `card-1` at `y=150` (height=460)
and `card-2` at `y=200` (50px down) — a 410-px overlap. You don't get
"vertical stack"; you get "overlapping column."

### 4.5 No per-type default sizing

`compose.py`'s `_build_layout_from_template` falls through to
`direction: "vertical"` with no sizing when no template matches. The
renderer then emits `createFrame()` with no `resize()` call, so Figma's
default 100×100 sticks. Every non-screen frame ends up 100×100 unless
a specific code path intervenes — and for synthetic IR, none does.

Exp I's `defaults.yaml` has per-type median sizes for 12 catalog types
from Dank data (button: 48×52 HUG/FIXED; heading: 66×22 HUG;
navigation_row / list_item: no data). Nothing currently reads that file.

## 5. The architectural gap — the missing "Mode 3"

The renderer today has two modes:

**Mode 1 — Instance lookup.** IR node has `component_key`. Renderer
calls `figma.getNodeByIdAsync(component_figma_id).createInstance()`.
The component's internal structure comes from Figma; we just parameterise
it with `.characters` overrides via `_build_text_finder`.

**Mode 2 — L0 synthesis.** IR node has no `component_key` but has rich
L0 visual properties (from DB: fills, strokes, effects, width, height,
children_composition). Renderer emits `createFrame()` and applies the
L0 properties one by one. `_emit_composition_children` adds child
instances based on the extracted template's `children_composition`.

**The missing Mode 3 — Catalog synthesis.** IR node has no
`component_key` AND no L0 visual properties (because synthetic IR
never came from the DB). All we have is:
- A catalog type (`button`, `text_input`, …)
- The LLM's `props` payload
- The catalog's `slot_definitions` for that type

No current code path turns `(type, props, slot_definitions)` into a
Figma subtree. The renderer needs one of:

- **Mode 3a — compose-layer expansion.** `compose_screen` inspects
  the type's slot_definitions, synthesises child IR elements
  ("button-1__label" text element, "text_input-1__placeholder" text
  element), and wires them as IR `children`. The renderer then renders
  the synthetic children via the existing Mode-2 text path. *Advantages:*
  IR remains honest; verifier + inspectors see the full tree; no
  renderer changes. *Disadvantages:* requires compose to know per-type
  layouts (button is HORIZONTAL padded 12x16, text_input is VERTICAL
  stacked label-above-input).

- **Mode 3b — renderer-layer expansion.** Renderer, seeing a Mode-2
  element with no children and a known text/label prop, synthesises
  a `createText()` child inline. *Advantages:* smaller footprint.
  *Disadvantages:* IR understates the tree; verifier must be taught
  the synthesis; every backend renderer has to duplicate the logic.

Mode 3a is the compositionally-correct answer. Mode 3b is the
short-term hack.

## 6. Fix list, ordered by blast radius

### Tier 1 — make Mode-2 leaves visibly non-empty (required before any ratings)

**Fix 1.1 — Expand Mode-2 leaves from slot_definitions at compose time.**

Concrete shape:

```python
# in compose.py, after _build_element resolves an element
catalog_entry = get_catalog(comp_type)    # from dd.catalog
slot_defs = catalog_entry.get("slot_definitions") or {}

# Heuristic: if any slot has allowed=["text"] and the LLM gave us a
# matching prop, synthesise a text child.
for slot_name, slot_def in slot_defs.items():
  if slot_def.get("allowed") == ["text"]:
    prop_value = props.get(slot_name) or props.get("text") or props.get("label")
    if prop_value:
      child_eid = _allocate_id(f"{comp_type}_{slot_name}")
      elements[child_eid] = {
        "type": "text",
        "props": {"text": prop_value},
        "layout": {"direction": "vertical"},
      }
      element.setdefault("children", []).append(child_eid)
```

Coverage: 10 of the broken 12 classes gain visible content in one
swoop (button, text_input, toggle, list_item, navigation_row,
icon_button, avatar, badge, fab, empty_state, search_input, select,
header-as-leaf). About 30 lines of code. 1 test file of ~150 lines.

**Fix 1.2 — Per-type default frame sizing from Exp I + catalog.**

Compose-time: load `experiments/I-sizing-defaults/defaults.yaml`
(fallback per-type sizes); for types Exp I flagged insufficient, fall
back to a minimal default (`frame 200×40 HUG/FIXED`). Every Mode-2
leaf gets an `intrinsicSize` hint applied at lowering. Renderer emits
`resize()` whenever the IR carries an explicit width/height.

Scope: 50-line loader + sizing-injection function + test that reads
the YAML.

**Fix 1.3 — Screen root auto-layout by default.**

Change `compose.py:106-109` to emit VERTICAL auto-layout with
`paddingTop/Bottom/Left/Right: 16, itemSpacing: 12` by default, and
drop the hardcoded `y_cursor` loop. Every direct child of the screen
gets `layoutSizingHorizontal: FILL` so cards become 396px wide instead
of 100px wide in a 428px screen.

Scope: ~20 lines. Covers v3 memo items 1+2. Re-run the 12 prompts to
measure impact.

### Tier 2 — surface what already exists to the LLM

**Fix 2.1 — Expose `component_key_registry` in build_project_vocabulary.**

`prompt_parser.py:32-38` currently reads only `component_templates`.
Union with `component_key_registry` so the 129 CKR entries reach the
LLM. For each CKR entry, show `component_key`, `name`, `instance_count`.
LLM can start emitting `component_key: "icon/chevron-right"` on
icon_buttons — Mode-1 takes over from there.

Scope: ~30 lines + a test that the vocabulary block contains at least
one CKR-sourced entry for the Dank DB.

**Fix 2.2 — Teach the LLM which types are containers.**

`SYSTEM_PROMPT` doesn't list container semantics. Add a short section:
"These types typically have children: `card`, `list`, `list_item`,
`button_group`, `drawer`, `bottom_nav`, `pagination`, `toggle_group`,
`table`, `tabs`, `accordion`, `dialog`, `sheet`." Optional: per-type
hint (`list_item: one icon + one label + optional chevron`).

Scope: ~15 lines of prompt content. Measure: fraction of `list` /
`list_item` IR elements that have `children` in the re-run.

### Tier 3 — ingest external corpora (shadcn MVP)

Only valuable after Tier 1+2. Tier 1 fixes Mode-2 to render visible
content; Tier 2 gives the LLM more Mode-1 ammunition from the user's
own corpus. Once those land, Tier 3 widens the `component_key` pool
beyond what the user has extracted — e.g. giving the LLM a
`shadcn:card` to reach for when the user's corpus has no card.

The spec at `experiments/H-design-systems/spec.md` stands. The only
caveat: the spec's success criterion "reduce default-100×100 count
from 212 to <50" bakes in the assumption that Mode-2 is broken for
compositional reasons, when actually it's broken for pipeline-wiring
reasons. After Tier 1 lands, the baseline count will already be far
below 50 — so the shadcn-vs-no-shadcn delta will be a quality delta
(richer internal structure, real colours) rather than a presence
delta.

## 7. Relationship to prior sprint items

| Prior item | Status after this diagnosis |
|---|---|
| Exp H Step 1 (shadcn MVP) | Deferred until Tier 1 + 2 land. |
| Exp D (anchor exemplar impact) | Blocked — meaningful only after retrieval corpus exists. |
| Exp I per-type defaults | Ready to wire in Fix 1.2. YAML is authoritative for the 12 Dank-backed types. |
| Exp G positioning grammar | Not yet load-bearing — Tier 1 fixes surface-level emptiness before positioning matters. |
| Wave 2 designer ratings | Do not issue until gate passes on the next baseline run. |
| Wave 3 VLM critic | Gemini pass already wired in the auto-inspect gate; full critic with UICrit few-shot still pending. |

## 8. Decision points for the user

1. **Proceed with Tier 1 now?** The three fixes are contained in
   `dd/compose.py` and `dd/prompt_parser.py` (plus one new test file).
   Estimated 1 engineer-day including tests.

2. **Mode 3a vs 3b?** Recommendation: 3a (compose-time expansion).
   Keeps the IR honest; verifier / inspectors see the synthesised
   subtree; no per-backend duplication. Downside: compose now knows
   per-type layout (`button HORIZONTAL`, `text_input VERTICAL`), but
   that knowledge already lives in `dd/catalog.py`'s
   `slot_definitions` — we're just starting to consume it.

3. **Shadcn ingestion after Tier 1+2 ship?** Yes, but scope it against
   what Tier 1+2 *didn't* fix, not against v3. The visible-content
   problem disappears with Tier 1; shadcn then adds richer structural
   exemplars and richer tokens.

## 9. Invariants this diagnosis does not threaten

- 204/204 round-trip parity (untouched; renderer Mode-1 and Mode-2-
  from-DB paths unchanged).
- Existing unit test count (now 1,713 including the new
  `test_visual_inspect.py`).
- ADR-006 ingest-side symmetry (no change).
- ADR-007 verification channel (no change; Mode-3 synthesis at the
  compose layer will naturally generate per-node ids so the verifier
  sees the full tree).
