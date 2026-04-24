# Stage 2 — NAME / DRILL / CLIMB over `FocusContext`

Stage 1 gave the LLM edit capability over a single doc. Stage 2 gave the surrounding Python harness the cognitive primitives designers actually use — announce a subtree's identity, zoom into it, zoom out. It is deliberately a deterministic-Python layer, not an LLM-callable tool surface; Stage 3 chose to expose the primitives to the LLM inside the session loop, but the semantics were fixed here.

## 1. What Stage 2 was for

Plan §3 Stage 2: add NAME / DRILL / CLIMB plus a move-log that round-trips to Stage 3's future SQL. Lateral was explicitly deferred to Stage 3 because it needs persistence to hold N variants alive simultaneously.

The three primitives, from `docs/research/designer-cognition-and-agent-architecture.md` §2:

- **NAME** — the agent declares "this subtree is a product-showcase-section" for its own rationale tracking. The node stays `type=frame`; NAME is a semantic marker, not a new type. Logged.
- **DRILL** — the agent says "I want to focus on `@product-showcase-section`'s internal layout." Extract the subtree as context; edits are scoped to its descendants; a defense-in-depth verifier rejects out-of-scope writes.
- **CLIMB** — after drilling, pop one level back. Lets the agent check "did my local subtree change break a parent constraint?"

## 2. The Codex Option-B pick

Fork at the top of Stage 2: **Option A** — ship DRILL / CLIMB as LLM-callable tools in the tool registry, so the model sees them alongside `propose_edits`. **Option B** — ship them as deterministic Python primitives over `propose_edits`; the LLM never sees them directly; they shape what the LLM gets shown. Codex 2026-04-23 picked B:

> "Stage 2 should make DRILL/CLIMB *possible and correct*, not ship the multi-turn agent loop before Stage 3 has the persistence to support it. The LLM only ever sees `propose_edits`. NAME/DRILL/CLIMB sit one layer above and shape what the LLM sees. Stage 3 can later expose them as LLM-callable tools without changing semantics."

This paid off: in Stage 3 the primitives became LLM-callable via `_emit_name_subtree_schema` / `_emit_drill_schema` / `_emit_climb_schema` (`dd/agent/loop.py:82-145`) without changing any of their semantics. The Option-B layer boundary held.

## 3. The 2a mechanic — focus-as-view, edits-to-root

The core trick: DRILL does NOT fork the doc. `FocusContext` holds a `root_doc` plus a `scope_eid`; `extract_subtree(doc, eid)` returns a fresh `L3Document` view over the descendants; the LLM receives the view; but `apply_edits` runs against the **root doc**. Eids are stable across the whole doc, so an edit like `delete @rectangle-22280` resolves the same whether the scope is the screen or the card — no merge logic, no splice back, no fork reconciliation.

`drilled_propose_edits` (`dd/agent/primitives.py:89`) is the convenience wrapper: take a `FocusContext` + drill target + prompt, run `propose_edits` with the focused sub-doc as context, apply the returned edits to `focus.root_doc`, return an updated focus. CLIMB is a no-op on the doc — just a pop of `scope_eid` back up `parent_chain`.

`FocusContext` is a frozen dataclass with three composable operations (`drilled_to`, `climbed`, `with_log_entry`) — all return a new `FocusContext`, never mutate. The append-only move_log rides along.

## 4. Scope enforcement — defense in depth

`is_in_scope(focus, eid)` (`dd/focus.py:237`) is a pure function that checks whether `eid` lives under the current scope. It runs in three places:

1. Before any drill — `focus.drilled_to(eid)` rejects an out-of-scope target.
2. Inside `drilled_propose_edits` — the orchestrator rejects edits whose target isn't under the current scope, emitting `KIND_OUT_OF_SCOPE`.
3. Verifier hook — Stage 3's session loop calls `is_in_scope` on every applied edit as a safety rail.

The triplicated check is deliberate: each layer can evolve independently, and the agent can't silently escape its declared scope through any one of them.

## 5. Audit findings — things the plan got wrong

Three plan §4.1 items surfaced during Stage 2 implementation:

- **`corpus_retrieval` already accepted a context dict.** Plan said "this is the hook that needs plumbing" (§2.2 DRILL). The `context` parameter and `expected_children` ranking existed at `dd/composition/providers/corpus_retrieval.py:151` before Stage 2. DRILL just passes the right context; no plumbing work needed.
- **`TokenOnlyProvider` is a phantom.** Plan §4.1 Stage 2 prescribed "delete `IngestedSystemProvider` and `TokenOnlyProvider`." `IngestedSystemProvider` existed (53 LOC, zero callers — actually deleted in `cf677d1`). `TokenOnlyProvider` doesn't exist anywhere in the codebase; grep returns zero hits across every branch. Plan text was fabricated. Skipped from cleanup.
- **`SlotFill` traversal is NOT dead code.** Plan §4.1 Stage 1 prescribed deletion of "parsed-but-unused `SlotFill` traversal dead code." Actually load-bearing for the `{empty}` slot-visibility grammar (PR 2 `bca2dcc` / `55dc4ed`). Deletion would have been a serious regression. Skipped.

The pattern across these three: plan §4.1 was written before the slot-visibility grammar cluster shipped, so items it marked "dead" had acquired live readers between draft and execution. Always grep before deleting.

## 6. Real-LLM capstone

`tests/test_stage2_acceptance.py::test_drill_edit_capstone_haiku`: load Dank screen `ipad-pro-11-43`, build a `FocusContext.root(doc)`, DRILL into the card containing `@rectangle-22280`, run `drilled_propose_edits` with the prompt "remove the decorative white rectangle that duplicates the image boundary." Haiku-4.5 picks a `delete` verb on `@rectangle-22280` in 2.19s. Move log contains DRILL + EDIT entries in order; verifier reports zero out-of-scope writes.

Plan §2.5 acceptance criteria all green:
- DRILL test — agent receives full screen, drills into one card, emits edits that only touch descendants. Parent structure unchanged.
- CLIMB test — after DRILL, agent climbs, proposes an edit at the section level. Applies cleanly.
- NAME persistence — DRILL / EDIT / CLIMB / NAME log replay reconstructs the agent's trail.

## 7. Where the code lives

- `dd/focus.py` (253 LOC)
  - `dd/focus.py:59` — `extract_subtree(doc, eid) -> Optional[L3Document]`
  - `dd/focus.py:102` — `MoveLogEntry` dataclass (carries enough fields to promote into Stage 3's `move_log` row via `to_dict`)
  - `dd/focus.py:134` — `FocusContext` frozen dataclass; `.root()` / `.drilled_to()` / `.climbed()` / `.with_log_entry()` composition
  - `dd/focus.py:237` — `is_in_scope(focus, eid) -> bool` pure function
- `dd/agent/primitives.py` (237 LOC)
  - `dd/agent/primitives.py:26` — `name_subtree(focus, eid, description)` — metadata-only, appends NAME log entry
  - `dd/agent/primitives.py:57` — `drill(focus, eid, focus_goal=None)` — returns new FocusContext + DRILL log entry
  - `dd/agent/primitives.py:89` — `drilled_propose_edits(focus, drill_eid, focus_goal, prompt, client, component_paths)` — the convenience wrapper; runs `propose_edits` with the focused sub-doc, applies against root, appends EDIT log
  - `dd/agent/primitives.py:189` — `climb(focus)` — focus pop; at-root is a defensive no-op that deliberately doesn't pollute the log
  - `dd/agent/primitives.py:214` — `write_move_log_jsonl(focus, path)` — the Stage-3 stopgap persistence
- `tests/test_focus.py` (20 tests), `tests/test_agent_primitives.py` (25 tests), `tests/test_stage2_acceptance.py` (5 tests including the capstone).

## 8. Deferred

- **JSONL move-log is a stopgap.** Stage 3 owns the SQL schema (migration 023). `MoveLogEntry.to_dict` was designed to round-trip into the `move_log` row shape; promotion is bulk-import, no re-serialisation.
- **LATERAL primitive.** Plan §3 Stage 2 explicitly deferred lateral variants until Stage 3 has persistence. Stage 3 landed it as "branching falls out of resume-from-non-leaf" — no dedicated `lateral` primitive; the variant graph via `parent_id` is the substrate.
- **Real-LLM capstone was gated on the visibility-toggle fix** (`538ebc9`). Before the toggle reversal, the Dank iPad test screen's `@rectangle-22280` was blind to `findOne` — the delete would have applied against a doc position but rendered identically. The Stage 2 capstone only started producing interesting deltas after Stage 0.post-flight fixed the perf-flag blindness.
