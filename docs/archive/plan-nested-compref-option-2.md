> **Plan status**: draft 2026-04-22 (end of slot-visibility arc); awaiting user review before any code lands.

# Plan — Nested CompRef as the canonical form for instance composition

## 0. Who this is for, and what it fixes

**The audience, literally**: the constrained-decoded LLM that will (soon) author dd-markup, the compressor that generates training corpus from Figma, and the renderer that must accept both.

**The fix**: today the compressor produces `-> nav/top-nav {flat PathOverrides...}`. This silently discards 7,024 depth-2 instance overrides across the Dank corpus — every "which icon does this nested button show" decision. Option 2 replaces the flat form with **recursive CompRef SlotFills** (`-> nav/top-nav { left = -> button/small/translucent { icon = -> icon/menu } }`). The *same information that Figma stores natively* becomes the *same information the LLM authors* becomes the *same information the renderer consumes* — one shape, three populations, three directions of traffic.

## 1. Constraints and invariants I am treating as non-negotiable

These came out of the document audit; violating any is grounds for rejecting the plan.

1. **Round-trip is the proof-of-correctness artifact, not a test.** Every screen in the corpus must survive extract→compress→emit→parse→render→walk→verify. If the new emission breaks any of those, we don't ship. (Sources: `feedback_option_b_pivot.md`, `feedback_renderer_walks_db.md`, compiler-architecture §7.)

2. **The grammar extracts what the LLM emits.** Anything the compressor can't produce, the LLM can't be prompted or trained to produce. (Source: architecture-v0.3 §10.)

3. **Decode with the same knowledge that encoded.** Shared utilities between compressor (encode) and renderer (decode). No parallel suffix maps. (Source: `feedback_override_decomposition.md`.)

4. **Capability-gated emission.** `is_capable(prop, backend, node_type)` is the one source of truth. Adding new forms means registering them in `dd/property_registry.py`, not branching in the renderer. (Source: `feedback_capability_gated_emission.md`.)

5. **Stable-id addressing only.** `findOne(n.id.endsWith(";<figId>"))` — never `n.name === "..."`. Name collisions under a master are the PR-1 failure we just fixed. (Source: `feedback_hidden_children_broken_path.md`.)

6. **Structured failure channel in both directions.** Every new lowering step emits a KIND on failure. Silence is not success. (Sources: `feedback_boundary_contract.md`, ADR-007.)

7. **Fail open.** Unknown nested properties pass through; never whitelist-strip. (Source: `feedback_fail_open_not_closed.md`.)

8. **Structural parity is visual parity only for the properties we've verified.** Adding new emission without adding new verifier checks is a regression in disguise. (Source: `feedback_verifier_blind_to_visual_loss.md`.)

## 2. The grammar question — already answered

**The parser, emitter, and AST already support nested CompRef SlotFills.** The audit ran `parse_l3 ∘ emit_l3` on the exact form this plan needs and got a byte-exact round-trip. `SlotFill.node: Union[Node, EmptyNode]` — `Node` is fully recursive; `Block.statements` is a heterogeneous tuple that accepts nested Nodes.

So there is **no grammar change**. There's a grammar *clarification*: §2.7.2 and §3.2 of `spec-dd-markup-grammar.md` need an explicit example showing the form is canonical, not exotic. The EBNF is already correct.

**What the LLM will see — the canonical form:**

```
-> nav/top-nav #nav {
  button-small-translucent-2 = -> button/small/translucent {
    icon-menu = -> icon/menu
  }
  button-small-translucent-5 = -> button/small/translucent {
    icon-close = -> icon/close
  }
  logo-dank.visible = true
}
```

Three things to notice:
- The LHS of a nested SlotFill is the *descendant's eid* (normalized from its name under the master). Same rule as a PathOverride path, one level deep.
- The RHS is a full `NodeExpr`, which for instance slots means another `-> comp/path` with its own `{block}`.
- Leaf-level visibility toggles are still PathOverrides (`logo-dank.visible = true`) when the descendant is *not* an instance. PathOverride and nested SlotFill are not exclusive; they coexist in the same block.

## 3. DB truth — what we have to express

Empirical shape of `instance_overrides` after 4-source classifier:

| Depth | Rows | Distinct screens | Property types |
|------:|----:|----:|---|
| 0 (`:self:*`) | 32,203 | 204 | 16 (sizing, padding, fills, swap, …) |
| 1 (`;A:*`) | 17,772 | 204 | 7 (BOOLEAN, TEXT, FILLS, INSTANCE_SWAP, …) |
| 2 (`;A;B:*`) | **7,024** | 204 | 4 (BOOLEAN, STROKES, TEXT, FILLS) |
| 3 (`;A;B;C:*`) | **15** | 5 | 1 (STROKES) |

Two facts that simplify the design:
- **INSTANCE_SWAP maxes out at depth 1**. Dank never nests component swaps. The canonical form handles depth-1 swap via the SlotFill RHS itself; no chained `swapComponent` calls needed.
- **95%+ of depth-2 rows** trace to one master family: `nav/top-nav` → `button/small/translucent` → (icon | label) slots. Fixing this one pattern fixes the corpus.
- **Depth 3 is 15 rows total**, all STROKES on one icon three layers deep. Supporting it is trivial (recursive compressor), but we can defer verifier coverage to a later stage if it simplifies the first rev.

## 4. Architectural contract

### 4.1 Compressor emission rule (new)

**Input**: one instance-override row `(node_id, property_name, property_type, override_value)` where `property_name = ";A:(prop)"` or `";A;B:(prop)"` or `";A;B;C:(prop)"`.

**Output**: zero or one statement inside the outermost CompRef block, choosing based on segment depth and property:

| Depth | Property | Emitted form |
|---|---|---|
| `;A:*` | any | as today — flat PathOverride or PropAssign on the head |
| `;A:INSTANCE_SWAP` | — | as today — becomes a nested CompRef (SlotFill with `slot-eid = -> new/master`), with `comp_key` resolved through `component_key_registry` |
| `;A;B:*` | any | **nested CompRef**: materialize a `SlotFill(slot_name=eid_of(A), node=Node(head=comp-ref-to-master-of-A, block=Block([inner statements for ;B:*])))`. Recurse into the inner block with the remaining path segments. |
| `;A;B;C:*` | any | **recursive**: one more level of nesting. |

**Determinism rule**: if two rows share prefix `;A`, they MUST merge into the same nested SlotFill. The compressor collects all rows for an instance, groups by first `;`-segment, emits one SlotFill per group, recurses on the group's children.

**Slot name resolution**: `slot_name` = `normalize_to_eid(descendant_name_at_A)` where `descendant_name_at_A` is the name of the DB node whose `figma_node_id` last segment is `A`. This is the same `normalize_to_eid` already used for PathOverride paths (`feedback_override_decomposition.md` — shared utility).

**Master resolution for nested CompRef head**: `component_key_registry[descendant.component_key].name` → slash-path for the CompRef head. If `component_key` is null (the descendant is not an instance), **fail over to a flat PathOverride**, emit a KIND_NESTED_OVERRIDE_ON_NON_INSTANCE warning. This is the fail-open principle.

**Resolver side-car**: the current `descendant_visibility_resolver: {eid: {path: figma_id}}` is replaced / augmented with a *tree-shaped* resolver:
```python
descendant_resolver = {
    outer_eid: {
        slot_eid: {
            "__figma_id": "5749:84278",    # the outer slot's master child id
            "__paths": {
                "icon-menu.visible": "5749:82462",
            },
            "__nested": {
                slot_eid_inner: {...},
            },
        },
    },
}
```
The renderer walks this tree in lockstep with the emitted AST. Same shape as the AST ⇒ same walker logic.

### 4.2 Parser & AST — no change required

Audit confirmed:
- Grammar EBNF already permits `SlotFill ::= IDENT '=' NodeExpr` where `NodeExpr → Node → NodeHead Block?`.
- `_parse_block_statement` (`dd/markup_l3.py:1780`) dispatches to `_parse_node` on `IDENT = ->`.
- `SlotFill.node: Union[Node, EmptyNode]` is fully recursive.
- `emit_l3` writes `<slot_name> = <head>` + ` {` + recursive `emit_block`.
- Byte-for-byte round-trip tested and passes.

**Action**: add one round-trip test that pins this behaviour (we have none currently), and update the grammar spec to advertise the form. No code change.

**Side-bug to file separately**: `_parse_node`'s property-continuation loop (lines 1607-1697) greedily consumes `IDENT = value` following a blockless node head as a property on *that* node rather than a sibling statement. Doesn't bite us in the emitted form (we always emit blocks under CompRef), but will bite hand-authoring. Flag it; don't block on it.

### 4.3 Renderer lowering (new)

**Entry point**: `_emit_mode1_create` at `render_figma_ast.py:799-999`. Today it:
1. Creates outer instance via `__src.createInstance()`.
2. Writes head properties (`name`, `resize`, padding, ...) onto the outer instance.
3. For each `PathOverride(.visible)`, emits `findOne(id.endsWith(";<figId>"))` + `_h.visible = bool`.

**Recursive extension**:
4. For each `SlotFill` in the node's block:
   - Look up the outer slot's figma child id from the tree-resolver.
   - Emit: `{ const _slot = outer.findOne(n => n.id.endsWith(";<A_figId>")); if (_slot && _slot.type === "INSTANCE") { _slot.swapComponent(<master_of_B>); /* recurse into _slot for nested overrides */ } }`
   - Recursion: `_slot` becomes the new "outer" for the nested statements. Same emitter, one level deeper. The walker maintains a `var_stack` so each nested level has its own JS variable name.

**Critical ordering** (from `feedback_text_layout_invariants.md`, `feedback_supplement_extraction_is_ground_truth.md`, Plugin API audit):
- Phase 2's `appendChild` calls only touch the OUTER instance; nested-instance descendants are internal to Figma's representation.
- `swapComponent` on a nested descendant replaces that descendant's subtree wholesale. Any PathOverride targeting the old subtree's ids won't match. The renderer must emit swaps BEFORE any child PathOverrides; the compressor must emit overrides scoped to the post-swap subtree.
- `layoutSizing{H,V}` on swap targets is deferred to Phase 3 (existing mechanism via `override_deferred` accumulator).

**`skipInvisibleInstanceChildren` handling**: this is the corpus-wide bug we surfaced in this investigation. The flag is set at script entry for perf, but it makes `findOne(slotId)` return null when the slot's master default is `visible=0`. The canonical fix is *scoped toggling*: set it to `false` immediately before `findOne` calls in the override-emission section, restore to `true` after. We also question whether the flag earns its keep — per audit, its attribution to the 38.5s sweep number is document-only, not corpus-measured. Stage 0 is to turn it OFF as the default and measure the sweep again; re-enable narrowly if the regression is real.

### 4.4 Verifier (new KIND)

**`KIND_INSTANCE_VARIANT_MISMATCH`** (per-node, emitted in `dd/verify_figma.py`).

**Signal**: the walker (`walk_ref.js`) reports `mainComponent_key` for every rendered INSTANCE. The verifier compares each `eid → mainComponent_key` against what the markup declared. If markup said the slot was `-> icon/menu` but Figma rendered `icon/back`, fire the KIND.

**Source of truth for expected variant**:
- If the markup has a nested SlotFill, the expected master's CKR is the RHS CompRef's `type_or_path`.
- If the markup has no override for that slot, the expected master is the master's default descendant's `component_key`.

**Walker additions**:
- `mainComponent_key` via `await n.getMainComponentAsync()` on every INSTANCE.
- `componentProperties` if Figma's Component Properties API is in use (Dank isn't — confirmed in audit — but future libraries may be).

**Reverifier surface area**: while we're in there, also plumb through the missing classes from the audit when feasible without exploding scope:
- `KIND_FILL_VARIANT_MISMATCH` — gradient/image fills beyond solid.
- `KIND_LAYOUT_MISMATCH` — autolayout direction, padding, itemSpacing diffs.
- `KIND_GEOMETRY_MISMATCH` — non-text width/height/x/y where IR has FIXED sizing.
- `KIND_EFFECT_PARAM_MISMATCH` — effect params beyond count.

These can land in a follow-up; they're not on the critical path for this fix. But they should be registered in `dd/boundary.py` as reserved KINDs so the taxonomy doesn't regress.

### 4.5 Migration of existing emission paths

| Current emission | New emission | Behaviour |
|---|---|---|
| `logo-dank.visible = false` on `-> nav/top-nav` head | unchanged — leaf descendants are still flat PathOverrides | no change |
| `button-small-translucent-2.visible = true` on `-> nav/top-nav` head (today, when the button has no nested overrides) | unchanged | no change |
| **Missing today**: `;5749:84278;5749:82462:visible = true` (button 84278 should show its icon slot 82462) | **new**: `button-small-translucent-2 = -> button/small/translucent { icon-menu = -> icon/menu }` | net-new information the current pipeline discards |

## 5. Stage plan

Each stage is independently shippable, keeps round-trip green, and introduces one new measurable signal.

### Stage 0 — Remove the `skipInvisibleInstanceChildren` bug
- Remove the flag emission from `render_figma_preamble` (1 line).
- Full sweep; measure timing. Hypothesis: the 38.5s stays 38.5s; if not, re-emit the flag in a scoped block *after* Phase 3.
- **Expected impact**: 1,689 single-level overrides that flip master-hidden slots to visible start actually working. `is_parity` count UNCHANGED (the verifier is blind to this class) but visual inspection will show icons returning.
- **Proof**: rerun batch_screenshot on screen 333; back/shape/check icons appear.

### Stage 1 — Walker emits `mainComponent_key` per INSTANCE
- `walk_ref.js`: add `mainComponent_key` field via `getMainComponentAsync()` on INSTANCE nodes.
- No verifier change yet. Just the signal.
- **Why first**: this is the signal everything else depends on. Independent of emission changes.

### Stage 2 — Verifier: `KIND_INSTANCE_VARIANT_MISMATCH`
- Compare expected variant (from markup) to rendered `mainComponent_key`.
- Expect the 204/204 parity to drop — that's the point. Every screen with nested variant overrides that today silently fails will now fail loudly.
- **Result**: an honest baseline. We now know how many screens are actually broken.

### Stage 3 — Compressor: nested SlotFill emission
- Extend `_fetch_descendant_visibility_overrides` to return a *tree* of overrides grouped by first `;`-segment.
- New function `_build_nested_override_tree` in `dd/compress_l3.py`.
- `_compress_element` consumes the tree: for each first-segment group, emit a nested SlotFill Node; recurse into inner groups.
- Resolver becomes tree-shaped (same structure as the AST).
- **Test strategy**: add one round-trip test for `-> A { slot = -> B { prop = ... } }`. Update ~4-6 IMPL tests in `test_compress_l3.py` + `test_slot_visibility.py` that pin flat emission shape; each should now assert on the nested form.

### Stage 4 — Renderer: nested SlotFill lowering
- `_emit_mode1_create` grows a `_descend_into_slot_fill` helper.
- For each nested SlotFill in the node, emit `findOne + swapComponent + recurse`.
- Extend `render_applied_doc` to thread the tree-shaped resolver (currently drops it — known gap per audit).
- **Verify**: Stage 2's KIND drops from "widespread failures" to 0 (for nested variants specifically).

### Stage 5 — Grammar spec update + canonical LLM docs
- `docs/spec-dd-markup-grammar.md` §2.7.2: add an explicit nested-CompRef-as-SlotFill example.
- `docs/spec-dd-markup-grammar.md` §3.2: note that `IDENT = -> ...` RHS is a nested CompRef SlotFill (not a PathOverride).
- Write a short "how the LLM sees a screen" doc that shows one extracted nav/top-nav example in the canonical form. This becomes the prompt reference.

### Stage 6 — Fix the `_parse_node` property-continuation side-bug
- Unrelated to this plan, surfaced during audit. Flag, fix, forget.
- Not on critical path.

### Stage 7 — Follow-up verifier KINDs (separate plan)
- Fills beyond solid, geometry, autolayout, effects params.
- Tracked in a new plan doc; out of scope here.

## 6. Risks and how I'd address them

### R1 — Stage 3/4 mutual dependency
The compressor emits nested SlotFills; if the renderer doesn't yet lower them, round-trip breaks.

*Mitigation*: behind a feature flag (`COMPRESS_NESTED_OVERRIDES=1` env var). Default off until Stage 4 lands. Flip to default-on as the last step of Stage 4.

### R2 — Stage 2 will report widespread parity regressions
That's expected — it's the current state becoming visible.

*Mitigation*: land Stage 2 with a loud note ("structural parity dropped because the verifier got sharper, NOT because of new bugs"). MEMORY.md entry. Don't block shipping other work on it.

### R3 — Nested CompRef breaks on non-instance descendants
Some nested overrides target non-INSTANCE descendants (e.g. a FRAME inside a button master with its own override chain). `swapComponent` on a non-INSTANCE throws.

*Mitigation*: compressor gate — only emit SlotFill when the descendant at segment A has `component_key != null`. Otherwise flatten to a PathOverride path. Capability-gated emission principle; single source of truth in the registry.

### R4 — Recursive emission explodes token count
7,024 depth-2 rows means the emitted dd-markup for complex screens gets noticeably larger.

*Mitigation*: measure. If growth is >20%, revisit. Most existing screens only have 1-3 overrides per instance, so the nesting is usually shallow in practice. Also: the LLM will train on shorter forms when overrides collapse to defaults (empty nested blocks → can be elided per grammar rules).

### R5 — `skipInvisibleInstanceChildren` being off could hurt large-screen perf
Without a controlled measurement we don't know.

*Mitigation*: Stage 0 measures. If we see regression, re-introduce the flag but *scoped* — set to true in the preamble, to false inside `_emit_mode1_create`'s override block, restore to true in the end wrapper. Narrow scope = no silent breakage.

### R6 — Verifier parity drop makes sweep look broken
UX concern for anyone reading `render_batch/summary.json`.

*Mitigation*: Stage 2 commit message + CHANGELOG note. The new number is the honest number.

## 7. Tests I want to add up front

Before touching code (TDD per global CLAUDE.md):

1. **Round-trip test** for nested CompRef SlotFill (`test_dd_markup_l3_nodes.py`): the example from §2 above parses, emits, re-parses, is AST-equal.
2. **Compressor test** (`test_compress_l3.py`): given an `instance_overrides` fixture with depth-2 rows, assert the emitted markup contains a nested SlotFill (not a PathOverride).
3. **Renderer test** (`test_render_figma_ast.py`): given a parsed nested SlotFill, emit JS containing `findOne(...).swapComponent(...)` pattern at the right nesting level.
4. **Resolver tree test** (`test_compress_l3.py`): tree shape is the expected recursive shape for a mocked 3-deep override set.
5. **Verifier test** (`test_verify_figma.py`): given a walk where an INSTANCE has `mainComponent_key = X` but markup says `-> Y`, emit `KIND_INSTANCE_VARIANT_MISMATCH`.
6. **Integration test**: pick screen 333 (the one you flagged); assert after Stage 4 that the emitted markup contains the nested form for the shape-toolbar buttons and that rendered variants match markup.

Each test is RED before its stage lands and GREEN after. No stage is considered done without a passing test.

## 8. What I explicitly am NOT proposing

- **Not changing** the EBNF / lexical grammar. Audit confirms parser already handles this.
- **Not adding** a new AST class. `SlotFill.node: Union[Node, EmptyNode]` is sufficient.
- **Not changing** the PathOverride form — it stays as-is for non-instance descendants.
- **Not touching** the `component_slots` pipeline (M7.0.b). Nested CompRef compression is DB-derived; slot-name resolution uses the descendant's `normalize_to_eid(name)`, not the component's authored slot table. (That'd be a future refinement.)
- **Not solving** all verifier gaps. Just `KIND_INSTANCE_VARIANT_MISMATCH`. Others are follow-ups.
- **Not deferring** until M7.6 finishes. This plan is an M6.5 equivalent — it sharpens the language before more synthesis work rides on it.

## 9. Decision points I need your read on before any code lands

1. **Should the descendant slot name be the master's original name (`button-small-translucent-2`) or its classifier role (`right-action-button`)?** The audit suggests using `normalize_to_eid(name)` from the DB — stable, deterministic, works without component_slots data. But this locks the LLM into naming patterns from the extracted corpus; synthetic screens from an LLM might prefer role-based names. Pick one; I'll follow.

2. **`skipInvisibleInstanceChildren` — default off or scoped-off?** Default-off is simplest and I lean that way. Scoped-off preserves perf optionality. Your call on how aggressively to remove today's perf optimization.

3. **Should Stage 2 (verifier KIND) land before Stage 3 (compressor emission)?** My preference is yes — it makes the baseline honest first. You'd see `is_parity=True` drop from 204 to some lower number immediately, which is a temporary step backward before the fix lands in Stage 3-4.

4. **Depth cap**. Do we support depth 3+ (15 corpus rows, all strokes) in Stage 3, or defer to a later stage? I lean "support from day one" since the compressor is naturally recursive. But if depth 3 complicates anything, cap at 2.

5. **Shipping cadence**. All stages in one week of focused work, or staggered across multiple weeks with measurement gaps? I'd favor one uninterrupted sprint — the stages are tightly coupled and staggering creates half-states.

---

**Bottom line**: the plan is mostly surgical because the grammar and parser already support the form we need. The work is in: (a) the compressor's emission logic (new recursive walk), (b) the renderer's lowering logic (new recursive emit), (c) one new verifier KIND, (d) removing a perf flag that silently eats 1,689 simpler overrides. No grammar rewrite, no AST surgery, no new lexer tokens. The corpus stays the corpus; only the representation of it gets richer and honest.
