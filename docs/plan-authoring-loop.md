> **Plan status**: Draft 2026-04-23 (decisions applied). Ready for user go/no-go.
> **Authors**: Claude Opus 4.7 + Codex GPT-5.2 (joint). Rationale sections reflect both agents' analyses; disagreements noted inline.
> **Supersedes**: `docs/plan-nested-compref-option-2.md` (draft), which was solving the wrong problem.
>
> **Decisions closed (2026-04-23, user review)**:
> - Neutral wrapper: `frame` only. Layout direction is a prop (`layout=horizontal|vertical|absolute`), not a type. Maps 1:1 to Figma auto-layout + constraints.
> - Slot validation: log-only first. Tighten to hard-error on trigger — one week of real-prompt runs OR 20 consecutive runs with zero rejections, whichever comes first.
> - Stage 2 primitive order: NAME → DRILL → CLIMB (cheapest-first; NAME is a logging/metadata primitive, DRILL and CLIMB depend on NAME-tagged move log being meaningful).
> - Session GC: keep forever by default. `dd design prune` is an opt-in CLI command. Sessions are the per-designer preference signal; automatic time-based GC would throw away training data.
> - Transport: CLI now. Agent-server deferred. The orchestrator function is the same either way; only transport differs.
> - Architecture cleanup: folded into each stage (not a separate PR). Each stage has an explicit cleanup audit — specific items listed in §4.1.

# Plan — The authoring loop: enable fluid multi-depth composition

## 0. Why this exists

The user has been trying to build one capability since the beginning: **a system that reads their Figma design file, understands its conventions (tokens, components, style, layout gestalt), and then lets an LLM synthesise new screens / components / variations that are contextual with that design file.** Not generic AI-design. Their design.

The infrastructure is mostly built:
- Extraction (REST + Plugin API supplement) produces a shadow DB
- Classification + token clustering produces semantic annotations and token bindings
- The dd-markup language round-trips the corpus at 204/204 structural parity
- The renderer produces Figma scripts via the bridge
- An edit grammar (7 verbs) + apply_edits + repair_agent exist
- Mode 3 composition providers + universal catalog exist

What doesn't work is the **authoring loop** — the thing that sits between "user says 'make a login screen variant with destructive-auth styling'" and "valid dd-markup edits apply in the user's Figma file, using their components and their tokens."

Test outputs show the current composition path can't nest fluidly. The user has observed this directly. Designers compose at arbitrary depth, moving up and down the abstraction ladder. The current system forces a flat catalog-constrained component array.

This plan fixes that. It doesn't rebuild the substrate. It changes what the LLM is asked to emit, what vocabulary it has to emit with, and how its moves are persisted across a session.

## 1. The diagnosis (what's actually broken)

### 1.1 The user's observation

From test outputs: "the system is not able to nest (n) elements at arbitrary levels, it's relying on rules and deterministic logic when designers think about composing screens fundamentally differently."

### 1.2 Root cause — not where we thought it was

After joint analysis by Claude Opus and Codex, the diagnosis converged on three specific upstream defects. None are in the grammar, renderer, or IR. All are in the LLM-facing construction contract.

**Defect A — Missing neutral structural wrapper in the composition vocabulary.**

`dd/catalog.py` defines 80 canonical types. Every single one is semantic — `button`, `card`, `heading`, `toggle`, `header`, `drawer`. There is no `frame`, `stack`, `group`, `section`, or `container` in the vocabulary exposed to the LLM via `dd/prompt_parser.py:164-169`.

The grammar spec §2.7 DOES have `frame`, `group`, `container` as type keywords. The parser, compressor, and renderer all handle them correctly. They just aren't exposed to the composition prompt.

Consequence: when the LLM wants to express "a section wrapping a heading and three cards," it has no neutral container to use. The only available wrapper is `card` — which is semantically "a card," not a section.

**Defect B — The prompt explicitly teaches wrong coercions.**

`dd/composition/plan.py:209-217` (the active planner prompt) contains:

```
"Mapping rules for common UI concepts that aren't in the catalog:
  - a generic container / section / wrapper → use `card`
  - a footer → use `card` at the bottom (there is no footer type)
  - a carousel / slider → use `list` (count_hint ≥ 3) of `card` children
  - a hero → use `card` with an `image` + `heading` + `text`"
```

This is coercion, not guidance. The model was inventing `container`, `footer`, `carousel` because the vocabulary lacked primitives for those concepts. The fix applied was to *force the model to call them `card` anyway*, rather than to add the missing primitives.

Net effect: every designer-intuitive intermediate entity becomes a "card." Nesting collapses to `card → card → card`.

**Defect C — Identity loss in `compose.py::_allocate_id`.**

`dd/compose.py:121-123`:

```python
def _allocate_id(comp_type: str) -> str:
    type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
    return f"{comp_type}-{type_counters[comp_type]}"
```

Even if the LLM emits a beautifully-named plan with `eid=product-showcase-section`, `compose.py` discards that and generates `frame-1`, `card-3`, `button-7`. This makes every downstream step (edit grammar, repair loop, session persistence) unable to address the LLM's named entities. The agent's own names for things don't survive the first compose pass.

**Defect D — Output contract is "emit a closed component array," not "emit subtree moves."**

`dd/prompt_parser.py:171` asks for a JSON array of components with nested `children` — a one-shot, top-down, single-pass spec. There's no vocabulary for:
- "Here's the current tree; propose a move"
- "Let me iterate on this subtree before committing"
- "I want to try three variants of this card's internal layout"
- "Let me climb back up and reconsider the parent"

Everything happens in one pass. The agent has no workspace.

### 1.3 What's *not* the problem

We spent many hours debating the following, which turned out to be non-issues:

- **Grammar nesting depth**: dd-markup parses arbitrary depth. Verified by round-trip tests.
- **Renderer depth**: `_emit_override_tree` handles depth-N via `findOne(id.endsWith(";A;B;C"))`.
- **AST recursion**: `Node.block.statements` allows nested Nodes; `SlotFill.node` is recursively-typed.
- **Override mechanics**: `build_override_tree` correctly handles arbitrary-depth instance overrides. The depth-2 `.visible=false` bug is a *compressor duplication* bug, not a grammar limitation. It's a separate 1-day cleanup that falls out naturally during Step 0.

### 1.4 The principle we landed on

**Keep closed every field the runtime dispatches on. Open only the fields the runtime treats as uninterpreted labels or addresses.**

| Dimension | State | Why |
|---|---|---|
| Primitive `type` | **Closed** (enum) | Renderer dispatches on it |
| `variant` | **Closed** (enum per type) | Master has a finite set |
| `component_key` | **Closed** (enum from CKR) | Must match a real component |
| `slot` name | **Closed** (from parent's declared slots) | Master defines its own slots |
| Property keys | **Closed** (from capability table) | Per-backend property registry |
| Edit verbs | **Closed** (7 verbs) | Renderer dispatches |
| Token paths | **Closed** (project tokens + catalog) | Must resolve |
| `eid` (node identity) | **Open** (kebab-case pattern) | Just an address |
| User copy text | **Open** | Literal content |
| Nesting depth | **Open** (arbitrary) | Parser/renderer handle it |
| Sibling count | **Open** | No structural limit |
| Intermediate groupings | **Open** (user names them, type=frame) | Designer's own ontology |

## 2. What the user-facing surface looks like, before and after

### 2.1 Before (today)

The LLM emits:

```json
[
  {"type": "header", "children": [{"type": "icon_button", "component_key": "icon/back"}]},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Features"}},
    {"type": "card", "children": [{"type": "image"}, {"type": "heading"}, {"type": "text"}]},
    {"type": "card", "children": [{"type": "image"}, {"type": "heading"}, {"type": "text"}]},
    {"type": "card", "children": [{"type": "image"}, {"type": "heading"}, {"type": "text"}]}
  ]}
]
```

What's wrong with this output:
- The outer "Features section" is a `card` (wrong type — it's a section, not a card).
- The three inner items are also `card`s (right intent, but indistinguishable from the outer "card" which is actually a section).
- No eids on anything. If the LLM later wants to say "iterate on the product-card internal layout," it has no name for it.
- The vocabulary lacks `section` / `wrapper` / `frame`, so the abstraction-ladder move (SEE `product-showcase-section` → DRILL into its layout → CLIMB back up) is impossible.

### 2.2 After (this plan)

The LLM emits a flat table of named nodes with parent pointers:

```json
{
  "nodes": [
    {"eid": "screen-root",              "type": "frame",   "parent_eid": null,                        "order": 0},
    {"eid": "top-nav",                  "type": "header",  "parent_eid": "screen-root",               "order": 0},
    {"eid": "product-showcase-section", "type": "frame",   "parent_eid": "screen-root",               "order": 1},
    {"eid": "section-title",            "type": "heading", "parent_eid": "product-showcase-section",  "order": 0},
    {"eid": "feature-card",             "type": "card",    "parent_eid": "product-showcase-section",  "order": 1, "repeat": 3}
  ]
}
```

What's right about this output:
- `product-showcase-section` is its own named entity with `type=frame`, distinguishable from the cards inside it.
- Every node has a stable eid. Downstream edits (`@product-showcase-section.gap=16`) work.
- The LLM can later emit **moves** against these eids: "append a subtitle under section-title", "swap the first feature-card's image", "create a lateral variant of the whole section with denser layout."
- Nesting depth is unconstrained but each node is independently typed.

### 2.3 Addressable from this shape: the full edit loop

Once the plan above is materialized:

```dd
// Rendered markup (conceptual; compressor produces this)
screen #screen-root {
  -> header #top-nav { ... }
  frame #product-showcase-section {
    heading #section-title "Top Picks"
    card #feature-card-1 { ... }
    card #feature-card-2 { ... }
    card #feature-card-3 { ... }
  }
}

// An edit conversation with the agent:
// User: "tighten the feature card spacing"
// Agent emits: set @product-showcase-section gap={space.sm}

// User: "try a variant with 2 cards and a taller hero image"
// Agent emits:
//   delete @feature-card-3
//   set @feature-card-1.image.height={size.lg}
//   set @feature-card-2.image.height={size.lg}
```

## 3. The plan

Four stages. Each ships independently. Each is testable.

### Stage 0 — Fix the generation contract *(prerequisite, ~3-5 days, ~300-500 LOC)*

This is the work that unblocks everything downstream. Nothing else in this plan will produce fluid multi-depth composition if Stage 0 is skipped, because the substrate works but the contract forces flattening.

#### 0.1 Add `frame` as the neutral structural primitive

**File**: `dd/prompt_parser.py`

Current (line 164-169):
```
Actions: button, icon_button, fab, button_group, menu, context_menu
Selection & Input: checkbox, radio, toggle, toggle_group, ...
...
```

Add a new category:
```
Neutral wrapper: frame
```

Rationale: `frame` is already a grammar TypeKeyword (spec §2.7). The parser, compressor, and renderer all handle it. It maps 1:1 to a Figma auto-layout frame. The LLM expresses row-vs-stack via `layout=horizontal|vertical|absolute` as a prop on the frame, not via a separate type keyword. This matches how Figma itself models layout — a frame is the primitive; layout direction is configuration.

**Decision**: `frame` only (no `stack`/`row`/`group` sugar). Keeps the vocabulary minimal and matches Figma's own model.

#### 0.2 Delete coercion rules

**File**: `dd/composition/plan.py`

Delete lines 212-217 (the "Mapping rules for common UI concepts that aren't in the catalog" block). Delete the "use `card` when wrapper needed" guidance.

Rationale: the coercion was a patch for the missing neutral wrapper. Once `frame` is in the vocabulary, the patch harms more than it helps.

#### 0.3 Change the plan output contract to flat named-node rows

**File**: `dd/composition/plan.py`

Current plan format (line 224-231):
```json
[
  {"type": "header", "id": "hdr", "children": [
    {"type": "icon_button", "id": "back"},
    {"type": "text", "id": "title"}
  ]},
  ...
]
```

Replace with flat table:
```json
{
  "nodes": [
    {"eid": "hdr",   "type": "header",      "parent_eid": null, "order": 0},
    {"eid": "back",  "type": "icon_button", "parent_eid": "hdr", "order": 0},
    {"eid": "title", "type": "text",        "parent_eid": "hdr", "order": 1}
  ]
}
```

Rationale:
- Every node has an explicit eid (addressable downstream).
- `parent_eid` is explicit (no ambiguity about the nesting relationship).
- `order` is explicit (no "position in array = z-order" implicit contract).
- `repeat: N` replaces `count_hint: N` (same meaning, cleaner name).
- Flat form is easier to validate structurally (every non-root node's parent_eid must exist).
- This is what the agent loop will later emit for subtree moves; same shape from day one.

#### 0.4 Preserve planner eids through `compose.py`

**File**: `dd/compose.py`

Current (line 121-123):
```python
def _allocate_id(comp_type: str) -> str:
    type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
    return f"{comp_type}-{type_counters[comp_type]}"
```

Replace with:
```python
def _allocate_id(comp_type: str, preferred_eid: str | None = None) -> str:
    if preferred_eid and _is_valid_eid(preferred_eid) and preferred_eid not in elements:
        return preferred_eid
    type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
    return f"{comp_type}-{type_counters[comp_type]}"
```

Every `_build_element(comp)` call that has an `eid` field in `comp` should pass it as `preferred_eid`. Fallback to the counter form only for synthesised / slot-filled children without LLM-provided names.

For `repeat: N`, expand deterministically: `feature-card` with `repeat=3` becomes `feature-card__1`, `feature-card__2`, `feature-card__3` — stable, predictable, addressable.

Rationale: the LLM names an entity for a reason. Discarding the name destroys downstream addressability. The `feature-card__N` expansion pattern is explicit and non-colliding.

#### 0.5 Validate slot names against parent's declared slots

**Files**: `dd/composition/plan.py` + `dd/composition/slots.py`

Currently `dd/composition/slots.py:30` silently ignores unknown slots. Change to:
- Load the parent component's slot table (`dd/catalog.py` slot_definitions, or `component_slots` DB table for master-derived slots).
- If the planner emits a `slot` name that isn't in the parent's declared slots, reject at validation time with `KIND_SLOT_UNKNOWN`.
- This preserves the closed-slot-name invariant. The LLM cannot invent slots; only the parent's master-defined slots are valid.

#### 0.6 Upgrade drift check to structural comparison

**File**: `dd/composition/plan.py`

Current (line 162) diffs by type count. Upgrade to compare `(eid, type, parent_eid, slot, repeat)` tuples across planner intent and compose output. Flag any mismatch as `KIND_PLAN_DRIFT` — this surfaces cases where the compose step is losing identity or shape.

#### 0.7 Rewrite the system prompt

**File**: `dd/composition/plan.py::_build_plan_system`

Full replacement. The contract is explicit:

```
You are a UI structural planner.

Emit one `emit_ui_plan` tool call with a flat list of named nodes.

HARD CONTRACT:
- `type` is CLOSED vocabulary. Use only enum values from the tool schema.
- `eid` is OPEN vocabulary. Invent meaningful kebab-case names freely.
- `slot` is CLOSED vocabulary. Use only exact slot names the parent's type declares.
  Omit when the parent has no named slots.
- Do NOT invent primitive type keywords.
- Do NOT invent slot names.
- Do NOT emit raw design values (colors, pixels, fonts) — those come later, in Fill.
- For conceptual groupings (section / wrapper / layout), create a named wrapper
  node with type="frame".
- Preserve nesting depth. Deep trees are fine.
- Every node that may be referenced later must have its own eid.
- Use `repeat: N` for repeated templates. Expansion generates eid__1, eid__2, etc.

Example:
{
  "nodes": [
    {"eid": "screen-root", "type": "frame", "parent_eid": null, "order": 0},
    {"eid": "top-nav", "type": "header", "parent_eid": "screen-root", "order": 0},
    {"eid": "product-showcase-section", "type": "frame", "parent_eid": "screen-root", "order": 1},
    {"eid": "section-title", "type": "heading", "parent_eid": "product-showcase-section", "order": 0},
    {"eid": "feature-card", "type": "card", "parent_eid": "product-showcase-section", "order": 1, "repeat": 3}
  ]
}
```

#### 0.8 Acceptance criteria for Stage 0

1. **Vocabulary smoke test**: given the prompt "a product showcase section with 3 feature cards", the planner emits a `frame` wrapping the section, not a `card`. Baseline comparison shows before=`card`, after=`frame`.
2. **Eid preservation**: for any plan output, every `eid` in the plan appears in `compose.py`'s output `elements` dict with the same name. Diff script in tests.
3. **Slot name validation**: a plan with `slot="invented_slot_name"` on a `header` parent fails with `KIND_SLOT_UNKNOWN`. Today it passes silently.
4. **204/204 parity preserved**: full sweep still passes after Stage 0. Round-trip of extracted Dank screens is unaffected because Stage 0 only touches the composition path.
5. **`_fetch_descendant_visibility_overrides` quiet cleanup**: since the compose path is being touched, delete the duplicate flat-depth resolver and let `override_tree` handle depth-N visibility. This is the nested-CompRef fix, landed incidentally as part of the same refactor.

### Stage 1 — Edit-grammar generation contract *(~1 week, ~600-800 LOC)*

With Stage 0's named nodes in place, the LLM can now emit edits against them. Stage 1 pivots the generation contract from "emit a plan" to "emit a sequence of 7-verb edits against the current tree state."

#### 1.1 New tool surface: `propose_edits`

```json
{
  "name": "propose_edits",
  "input_schema": {
    "type": "object",
    "properties": {
      "edits": {
        "type": "array",
        "items": {
          "oneOf": [
            {"$ref": "#/definitions/SetEdit"},
            {"$ref": "#/definitions/AppendEdit"},
            {"$ref": "#/definitions/InsertEdit"},
            {"$ref": "#/definitions/DeleteEdit"},
            {"$ref": "#/definitions/MoveEdit"},
            {"$ref": "#/definitions/SwapEdit"},
            {"$ref": "#/definitions/ReplaceEdit"}
          ]
        }
      },
      "rationale": {"type": "string", "maxLength": 280}
    }
  }
}
```

Each edit verb has its own schema (addresses existing eids via `@eid` or creates new nodes following the Stage 0 flat-node shape). `apply_edits` in `dd/markup_l3.py` already implements the verb semantics — no new apply logic needed.

#### 1.2 The starting-IR is the current state

Today, compose starts from empty. Stage 1 adds: the agent receives the current tree state as a context, and emits edits against it. Starting states:

- **New screen (SYNTHESIZE)**: empty root, agent emits append sequence to build from scratch
- **Variation of existing (EDIT)**: full extracted IR of a donor screen, agent emits targeted changes
- **Mid-session iteration**: whatever the session's current tree is

All three use the same `propose_edits` contract. The difference is what the starting tree is. This matches the CRAG three-mode cascade conceptually — mode is implicit in the starting IR, not in the prompt contract.

#### 1.3 Acceptance for Stage 1

- **Move an item**: prompt "move the save button to the top of the card" produces a `move @save-button to=@card position=first` edit. Applies cleanly.
- **Replace an icon**: prompt "change the back button icon to a close icon" produces `swap @back-icon with=-> icon/close`. Applies cleanly.
- **Add a variant**: prompt "make a version with the save button disabled" produces `set @save-button variant=disabled`. Applies cleanly.
- All three round-trip through render → verify → pass.

### Stage 2 — Agent primitives: NAME / DRILL / CLIMB *(~1 week, ~400-600 LOC)*

Stage 1 gives the agent edit capability. Stage 2 gives it **multi-depth fluid composition** — the thing you said was missing.

The three load-bearing cognitive primitives (per `docs/research/designer-cognition-and-agent-architecture.md` §2, and Codex's sharpening in the prior turn):

#### 2.1 NAME

Tool: `name_subtree(eid, description) -> acknowledgement`.

The agent announces "this subtree is a product-showcase-section" for its own rationale tracking. Does NOT create a new type — the node still has `type=frame` — but the name is promoted from ad-hoc eid to semantic marker. Stored in `move_log` as a `NAME` entry.

Rationale: gives the agent a vocabulary for its own abstractions without reopening the type hallucination problem.

#### 2.2 VERTICAL DRILL

Tool: `drill(eid, focus_goal) -> subtree_context`.

The agent says "I want to focus on `@product-showcase-section`'s internal layout." The loop:
1. Extract just that subtree as context.
2. Retrieve donor fragments matching the subtree's role (using `corpus_retrieval` at subtree level, not screen level — this is the hook that needs plumbing).
3. Let the agent emit edits scoped to descendants of `@product-showcase-section`.
4. When the agent says `climb` (next primitive), pop back to the parent context.

Rationale: designers don't redesign the whole screen every time they rethink a card. They zoom into the card, iterate, zoom back out. This primitive encodes that action.

#### 2.3 VERTICAL CLIMB

Tool: `climb() -> parent_context`.

After drilling, the agent checks "did my local subtree change break a parent constraint?" For example: drilling into a card and shrinking it might create layout issues at the section level. Climb re-evaluates the parent against the updated child.

Rationale: top-down-only design produces inconsistencies. Co-evolution of problem and solution (Dorst & Cross) requires the upward move.

#### 2.4 LATERAL is deferred to Stage 3

Lateral variants are powerful but require persistence (you need to hold N variants alive simultaneously). Defer until Stage 3 has the session infrastructure.

#### 2.5 Acceptance for Stage 2

- **DRILL test**: agent receives a full screen, drills into one card, emits two edits that only touch descendants of that card. Verifier confirms parent-level structure unchanged.
- **CLIMB test**: after DRILL, agent climbs, notices "card height changed from 200 to 140," proposes an edit at the section level to adjust grid gap. Verifier confirms the parent-level edit applies cleanly.
- **NAME persistence**: every DRILL / CLIMB / MOVE emits a `move_log` entry tagged with the named entity the agent was focused on. After the session, we can replay the agent's reasoning trail.

### Stage 3 — Session persistence and branching *(~1 week, ~500-800 LOC)*

Now the agent can compose at depth. Stage 3 makes those compositions persistent and branchable, so the user can explore a design space non-destructively.

This is §11 of `designer-cognition-and-agent-architecture.md`, unchanged.

#### 3.1 Schema

Migration 023:

```sql
CREATE TABLE design_sessions (
  id            TEXT PRIMARY KEY,       -- ULID
  brief         TEXT NOT NULL,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  status        TEXT                    -- open / closed / archived
);

CREATE TABLE variants (
  id              TEXT PRIMARY KEY,     -- ULID
  session_id      TEXT REFERENCES design_sessions(id),
  parent_id       TEXT REFERENCES variants(id),
  primitive       TEXT,                 -- NAME / DRILL / CLIMB / MOVE / LATERAL / etc.
  edit_script     TEXT,                 -- the edits that birthed this variant
  markup_blob_id  TEXT,                 -- content-addressed AST snapshot
  render_blob_id  TEXT,                 -- content-addressed PNG
  scores          TEXT,                 -- JSON fidelity_score output
  status          TEXT,                 -- open / pruned / promoted / frontier
  notes           TEXT,                 -- agent's rationale
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE move_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT REFERENCES design_sessions(id),
  variant_id    TEXT REFERENCES variants(id),
  primitive     TEXT,
  payload       TEXT,                   -- JSON of the move
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.2 CLI

```
dd design --brief "a login screen for a fintech app"
dd design ls                              # list sessions
dd design show <session-id>               # show tree + variants
dd design resume <session-id>             # continue where you left off
dd design branch <variant-id> --vary <axis>  # LATERAL move from a specific variant
```

#### 3.3 Orchestrator

`dd/agent/loop.py` — thin Python controller, ~300 LOC. Tool surface:
- `propose_edits(edits, rationale)` — apply + render + score
- `name_subtree(eid, description)`
- `drill(eid, focus_goal)`
- `climb()`
- `lateral(eid, variation_description)` — fork the current variant, apply a different edit script

Single Sonnet 4.6 agent. Max 10 iterations per session (configurable). Persists everything.

#### 3.4 Acceptance for Stage 3

- `dd design --brief "a login screen"` produces a session, runs NAME / DRILL / MOVE primitives, ends with a renderable screen and a full move log.
- `dd design resume <id>` picks up where a prior session left off, agent has full context.
- `dd design branch <variant-id> --vary style` produces a sibling variant with a different style axis.
- Sessions are queryable: "show me all variants where scorer.fidelity > 0.8."

### Stage 4+ — Deferred

Explicitly deferred. Do not build until Stages 0-3 are hardened and tested on real prompts:

- Linkography monitor + FIXATION-BREAK
- MCTS tree search
- Multi-agent role split (Senior + Junior + Librarian)
- Canvas UI
- Sketch input parser
- Pattern auto-accretion (promote critical moves to reusable fragments)
- Per-designer preference / DPO

Codex's sharper framing: **the doc over-indexes on monitor sophistication and multi-agent ceremony. The actual unlock is the action-space (Stages 0-3), not the observer.**

## 4. Cleanup folded into each stage

Each stage touches a region of the code. While touched, we delete accumulated drift adjacent to that region. Not a separate cleanup PR — inline with the stage work. Items come from the full-codebase enumeration Codex + Opus did earlier in this planning round.

### 4.1 Cleanup items, tagged by stage

**Stage 0** — compose path + planner prompts + visibility resolver:
- Delete coercion rules in `dd/composition/plan.py:212-217` (the `section→card`, `footer→card`, `carousel→list of card`, `hero→card` mapping).
- Delete `_fetch_descendant_visibility_overrides` in `dd/compress_l3.py` — duplicates `build_override_tree` and was the source of the depth-2 override silent-drop bug that caused the screen 333 visual defect we found earlier.
- Delete `descendant_visibility_resolver` side-car threading in `dd/render_figma_ast.py` and `dd/renderers/figma.py` — replaced by `override_tree` path which already handles depth-N correctly.
- Delete the `figma.skipInvisibleInstanceChildren = true` line at `dd/render_figma_ast.py:148`. Was added for perf but never isolated-measured; causes `findOne` to skip master-default-hidden descendants (the root cause of ~1,689 single-level override silent failures on Dank). If sweep regresses, re-add it as a scoped toggle, not a global flag.
- Rename `count_hint` → `repeat` in plan schema (clarity).
- Wire `ProjectCKRProvider` into `_build_default_mode3_registry` in `dd/compose.py:687`. It exists but isn't plugged in; was the reason "Mode 3 resolves project components" didn't actually work end-to-end. Codex and I both flagged this during enumeration.

**Stage 1** — edit grammar generation path:
- Delete `_fill_system` prompt in `dd/composition/plan.py:239` (the two-pass plan-then-fill contract is replaced by `propose_edits` in one shot).
- Delete `_extract_plan` / `_extract_fill` regex-based JSON extractors; replaced by structured tool-use output that doesn't need regex extraction.
- Delete parsed-but-unused `SlotFill` traversal dead code — the parser supports SlotFill but nothing downstream consumed it. If we're not using it, the dead traversal paths in `dd/markup_l3.py` (some of them) should go or be explicitly marked reserved-for-future.

**Stage 2** — agent primitives:
- Delete any "synthesise from scratch" composition path that doesn't go through edit ops. All generation becomes edits-against-a-tree (starting tree may be empty).
- Delete `IngestedSystemProvider` and `TokenOnlyProvider` — ADR-008 reserved them as future slots but they have no implementation and no caller. Kill the empty classes or tag them as `@abstractmethod` placeholders with a clear "not implemented" stub.
- Consolidate the two "slot" namespaces: rename `dd/slots.py` (master-child-slot derivation via Haiku) to `dd/master_slots.py` or similar, distinct from `dd/composition/slots.py` (composition-template-slot validation). The name collision has been a confusion source.

**Stage 3** — session infrastructure:
- Delete `compose_demo.py`, `swap_demo.py`, `repair_demo.py`, `structural_edit_demo.py` — all superseded by `dd design`. The demos duplicate session semantics with worse ergonomics.
- Audit and delete `_composition` legacy field references in `dd/renderers/figma.py` — only the legacy dict-IR renderer consumed it; the AST renderer doesn't. Dead field.
- Audit unused KIND values in `dd/boundary.py` — several (e.g. `KIND_RATE_LIMITED`, `KIND_PLAN_INVALID`) are defined but have no emitter. Either wire them or delete them.

### 4.2 Cleanup that does NOT fit into these stages

The following were identified but don't belong in Stages 0-3. Track separately if we want them:

- The 80-type canonical catalog still has items we likely don't need (e.g. `ruler`, `magnifier`, `eyedropper`, `mouse_cursor`, `text_cursor`). Trim requires taste judgments about what counts as UI vs. tooling — not a mechanical cleanup.
- `dd/extract_supplement.py` + `dd/extract_targeted.py` have overlapping responsibilities. Would benefit from consolidation, but not on the authoring-loop critical path.
- 27 KIND values in `dd/boundary.py` — some are per-node, some are screen-level, some are ingress-side, some are egress-side. Would benefit from a typed hierarchy, but not urgent.

## 5. Risks and how to address them

### R1 — Stage 0 breaks existing Mode-3 synthesis tests

`dd/compose.py` + `dd/composition/plan.py` are load-bearing for current Mode-3. Changing the contract will break tests that assert specific output shapes.

**Mitigation**: Stage 0 keeps the old `plan_then_fill` path behind a flag (`DD_USE_LEGACY_PLAN=1`) for the first PR. Tests that assert shape get a migration path. Default flips to new behavior in a follow-up PR once the new form is test-covered.

### R2 — LLMs may still emit `card` out of habit

Even with `frame` in the vocabulary and the coercion rules deleted, the LLM may have learned "use card for wrappers" from training data.

**Mitigation**: the system prompt explicitly says "For conceptual groupings (section / wrapper / layout), create a named wrapper node with type=frame." Combined with XGrammar constrained decoding (future work), the type field is enum-restricted so even stubborn "card-for-wrapper" habits lose to grammar enforcement.

### R3 — The agent loop may churn without converging

Giving an agent DRILL / CLIMB / LATERAL tools without guard rails can produce sessions that iterate forever.

**Mitigation**: hard iteration cap (10 per session default). Scorer dimension must monotonically improve or the loop halts with `KIND_AGENT_STALLED`. Future work (linkography monitor) adds sawtooth detection; Stage 3 ships with the simple cap.

### R4 — 204/204 parity regression

The round-trip sweep is load-bearing. Every stage must preserve it.

**Mitigation**: each stage's acceptance criteria includes "full sweep 204/204 preserved." Stage 0's compose-path change should have no effect on extracted-screen round-trip (which doesn't go through compose). Stages 1-3 touch only new code paths.

### R5 — Slot name validation regresses existing compositions

If we make slot name validation strict (Stage 0.5), existing compositions that silently passed may now fail.

**Mitigation**: first PR logs rejections without blocking; second PR promotes to hard errors once the logged instances are triaged. If any current in-flight composition emits a slot name that isn't in the parent's declared slot table, we need to understand why before enforcing.

## 6. What success looks like, end-to-end

At the end of Stage 3, the user can:

```
$ dd design --brief "make a settings screen for my Dank app, with sidebar nav
                     and a profile-info card"

> FRAME: routing brief through archetype classifier → archetype=settings_page
> SEE-AS: retrieving donor fragments from corpus → 3 donor screens matched
> NAME: screen-root (type=frame)
> APPEND: sidebar-nav (type=sidebar) under screen-root
> APPEND: content-area (type=frame) under screen-root
> DRILL into content-area
>   APPEND: profile-card (type=card) under content-area
>   DRILL into profile-card
>     APPEND: avatar (type=avatar)
>     APPEND: user-info (type=frame)
>       APPEND: display-name (type=text)
>       APPEND: email (type=text)
>     CLIMB to profile-card
>     APPEND: edit-button (type=button, variant=secondary)
>   CLIMB to content-area
> CLIMB to screen-root
> RENDER
> SCORE: fidelity=0.87, layout=0.92
> ✓ Session d1b8f2 saved

$ dd design resume d1b8f2
> Agent: the profile-card looks cramped. Would you like me to try a variant
  with the avatar on top instead of inline?

$ dd design branch d1b8f2 --vary layout
> LATERAL: creating variant d1b8f2-a with stacked layout...
> ✓ Compare at dd design show d1b8f2

$ dd design show d1b8f2
  Variants:
    root (score: 0.87)
    └── stacked-avatar (score: 0.91) ← branch
```

This is "the LLM writes dd-markup that produces real screens in your Figma file, contextual with your design system, at arbitrary composition depth."

## 7. Timeline

| Stage | Duration | Cumulative | Gate |
|---|---|---|---|
| Stage 0 | 3-5 days | Week 1 | `frame` primitive added; coercions removed; eids preserved; slot names validated; 204/204 preserved |
| Stage 1 | 5-7 days | Week 2 | Agent emits `propose_edits`; three basic tests pass (move / replace / variant) |
| Stage 2 | 5-7 days | Week 3 | DRILL/CLIMB/NAME primitives functional; multi-depth composition demonstrable |
| Stage 3 | 5-7 days | Week 4 | Session persistence + branching + `dd design` CLI |

~4 weeks to an end-to-end authoring loop.

## 8. Decisions (all resolved 2026-04-23)

| # | Question | Decision |
|---|---|---|
| 1 | Neutral wrapper scope | **`frame` only.** Maps 1:1 to Figma frame. Layout direction is a prop (`layout=horizontal/vertical/absolute`), not a type. |
| 2 | Legacy flag duration | `DD_USE_LEGACY_PLAN=1` supported for one release after Stage 0 ships. Default is new behavior immediately; flag is a safety valve for the first week. Deleted when Stage 1 lands. |
| 3 | Slot validation strictness | **Log only first.** Tighten to hard-error on trigger: one week of real-prompt runs, OR 20 consecutive runs with zero rejections, whichever comes first. Prevents re-hallucination from going unnoticed. |
| 4 | Stage 2 primitive order | **NAME → DRILL → CLIMB.** NAME is cheapest (logging/metadata only, ~50 LOC), and both DRILL and CLIMB need NAME-tagged logs to produce readable rationale trails. Each ships independently. |
| 5 | Session persistence scope | **Keep forever by default.** Sessions are per-designer preference signal — the thing DesignPref (arXiv:2511.20513) shows aggregate preference can't capture. Opt-in `dd design prune --older-than Nd --status pruned` for explicit cleanup. `status="archived"` hides from default `ls` without deletion. DB growth not a real concern at single-user scale. |
| 6 | Transport | **CLI now. Agent-server deferred.** `dd/agent/loop.py` exposes a Python function; CLI calls it directly. An eventual HTTP/WebSocket wrapper calls the same function. Pure additive migration path. |
| 7 | Architecture cleanup | **Folded into each stage** (§4.1 above). Not a separate PR. Each stage touches a region of the code; we delete adjacent drift while we're there. This prevents the "cleanup debt" trap where drift compounds between releases. |

---

*This plan is the product of Claude Opus + Codex converging after the user's "step back" directive. Disagreements are noted inline. Total net-new LOC across Stages 0-3: ~2,000. Total deletions: ~600. Net system growth: ~1,400 LOC of orchestration, zero grammar changes, zero renderer changes, zero IR changes.*

*All planning decisions are closed. The next action is implementation of Stage 0.*
