# Stage 3 — Session loop, persistence, branching

Stage 3 is where the authoring loop becomes a workflow. `dd design --brief "..."` runs an LLM, persists every iteration, lets you resume or branch off any variant. The three new tables and the Python orchestrator are the bones of everything Stage 4+ wants to build (MCTS, linkography, DPO dataset construction).

## 1. What Stage 3 was for

Plan §3: a CLI subcommand that takes a brief, drives a bounded agent loop, persists sessions + variants + moves to SQL, supports resume and branching. Plan §4.1 Stage 3 cleanup items folded in: audit `_composition` field (flagged dead), audit unused KIND values (flagged dead), delete the four demo files (deferred — see §8).

## 2. The three-option fork

At the top of Stage 3 the user asked Codex + Sonnet for a fresh-perspective take. Three sizing options surfaced:

- **Option 1 — lean ship (~250 LOC).** Single table (session rows). Inline markup blob. No migration. No move_log.
- **Option 2 — plan-faithful (~700 LOC).** Exact plan §3.1 schema including content-addressed `markup_blob_id` / `render_blob_id` side-car table. Full reimplementation of the plan text line by line.
- **Option 3 — hybrid (~450 LOC).** Three-table schema (sessions / variants / move_log) per plan, but drop the `session_blobs` sibling table — content-addressed dedup isn't justified at 10-iters-per-session scale. Use gzipped TEXT columns inline on `variants` instead. Keep ULID PKs. Keep move_log (non-negotiable — Stage 2's `MoveLogEntry.to_dict` was designed to round-trip into it).

Unanimous pick from Codex + Sonnet: **Option 3 + B (keep move_log)**. Reasoning: lean enough to ship in days not weeks, but honours plan intent on schema without slavishly copying every line. Dropping move_log would silently truncate the NAME and CLIMB entries Stage 2 was designed to persist.

## 3. A2 — defer scoring

Codex's call. Plan §3.3 listed `propose_edits(edits, rationale) → apply + render + score` as the per-iter pipeline. In-loop scoring would be 30s+ per iter × 10 iters = 5 minutes blocking the user on every session. A1 (keep scoring in-loop) was rejected for latency. A2 (defer scoring) replaces it with:

1. Cheap per-turn structural score (`dd/agent/loop.py:188 cheap_structural_score`) — three dimensions: out-of-scope count, edit_applied boolean, change_magnitude. Used only for stall detection, not for ranking.
2. Explicit `emit_done` tool — the agent declares convergence (`dd/agent/loop.py:145`). Session halts with `halt="done"`.
3. Stall detector — N consecutive iterations with no edit_applied → halt with `halt="stalled"`.
4. All-failed detector — every proposed edit in the current iter failed apply → halt with `halt="all_failed"`.
5. Max-iters cap — configurable, default 10. Halt with `halt="max_iters"`.

Real fidelity scoring moves to a post-pass: `dd design score <session>` walks every variant and runs the render+VLM+structural pipeline once. Currently a stub (A2 deferred means no backend implementation yet) that confirms session existence + variant count.

Codex's framing, from the lit-review survey in the fork discussion: "designers iterate fast, evaluate at milestones." Matches.

## 4. B2 — Python iteration loop, stateless calls

Plan §3 Stage 3 was neutral on orchestrator shape. Codex flagged two options:

- **B1 — long-lived conversation thread.** Single multi-turn call to Anthropic, tool results stream back into the same thread. More "natural" for agent behaviour. Harder to cap at max_iters (the model decides when to finish).
- **B2 — Python for-loop of single-turn calls.** Each iter is `client.messages.create(...)` with the full turn payload rebuilt each time. Max_iters is a deterministic for-loop bound. Replayable per-iter. Matches Stage 1+2 pattern (stateless `propose_edits` / `drilled_propose_edits`).

Codex picked B2. The risk note: "context-bloat — rebuilding the payload every turn means the full focused sub-doc + move log + tool schemas are re-sent every iter." Mitigated in `dd/agent/loop.py:243 _build_user_message` + `dd/agent/loop.py:274 _move_log_summary_lines` — the payload carries the **focused subtree** (not the root doc), plus a **compact summary** of the recent log (not the raw JSONL). Token count per iter stays bounded regardless of session length.

## 5. Schema — migration 023

`migrations/023_design_sessions.sql` + the same shape in `schema.sql` for fresh installs.

```sql
CREATE TABLE design_sessions (
  id         TEXT PRIMARY KEY,        -- ULID
  brief      TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  status     TEXT CHECK(status IN ('open','closed','archived'))
);

CREATE TABLE variants (
  id              TEXT PRIMARY KEY,   -- ULID
  session_id      TEXT REFERENCES design_sessions(id),
  parent_id       TEXT REFERENCES variants(id),     -- self-FK; NULL for root
  primitive       TEXT,                             -- NAME/DRILL/CLIMB/MOVE/LATERAL/...
  edit_script     TEXT,                             -- JSON of the edits
  markup_blob     TEXT,                             -- gzipped + base64-encoded inline
  scores          TEXT,                             -- JSON (A2 — stub until score backend)
  status          TEXT CHECK(status IN ('open','pruned','promoted','frontier')),
  notes           TEXT,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE move_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT REFERENCES design_sessions(id),
  variant_id TEXT REFERENCES variants(id),
  primitive  TEXT,
  payload    TEXT,                                  -- JSON; round-trips MoveLogEntry.to_dict
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Design choices:

- **ULIDs (Crockford) for sessions + variants.** `dd/ulid.py` is ~30 LOC of roll-your-own — no `python-ulid` dependency. Why: sessions will be shared (Stage 4+ DPO dataset) and variants will be referenced by parent_id across branches; monotonically-sortable + collision-safe beats INTEGER PK here. Crockford alphabet is URL-safe.
- **`parent_id` self-FK, not a separate `branches` table.** Variants form a DAG via parent_id alone. Resuming from a non-leaf spawns a sibling chain — that IS branching. No `branches` table needed. Test `test_variant_graph_forms_dag` pins this.
- **Gzipped TEXT `markup_blob` inline, no `session_blobs` sibling table.** Plan §3.1 prescribed a content-addressed blob side-car for dedup. At 10-iters-per-session scale dedup is negligible; an extra JOIN per variant read is not. Test `test_compressed_blob_is_smaller_than_raw_for_real_doc` confirms gzip halves the size on 50-node docs.
- **No session_blobs / render_blob_id.** Renders are regenerable from `markup_blob` + the bridge. Storing PNGs would grow the DB unnecessarily.
- **`scores` JSON column** is the A2 hook — the score backend writes a JSON blob per variant; the CLI renders it back out of the column. Schema doesn't know the score shape, which is fine — the backend is still stubbed.
- **CHECK constraints on status enums** enforce the state machines at the DB layer. Runtime validation is redundant but kept for friendly error messages.

## 6. Branching falls out of resume-from-non-leaf

No `dd design branch` subcommand. Variants form a tree via `parent_id`; if you `resume <session-id>` when the session's frontier is variant `V` and the LLM picks a new iteration, the new variant's `parent_id = V.id`. If you resume and pass `--from-variant <V'>` where `V'` is a non-leaf (mid-chain) variant, the new variant's `parent_id = V'.id` — creates a sibling branch. Simplicity-check + Codex + Sonnet all unanimous: a separate `branch` verb would duplicate state the tree already encodes.

## 7. `dd design` CLI

Three subcommands (`dd/cli.py::_run_design_*`):

- **`dd design --brief "..." [--max-iters N]`** — start a new session. Runs `run_session` orchestrator. Prints session ULID + iter count + halt reason + frontier variant ULID.
- **`dd design resume <session-id> [--from-variant V] [--max-iters N]`** — pick up an existing session. If `--from-variant` is a non-leaf, creates a sibling chain (branching).
- **`dd design score <session-id>`** — currently a **stub**: confirms the session exists + prints variant count. Real fidelity backend is A2-deferred.

`_make_anthropic_client` (in `dd/cli.py`) centralises the API-key check + friendly error message path across all three subcommands. `ls` and `show` were scoped out — raw SQL on the three tables works for current single-user scale.

## 8. Audit findings — what the plan got wrong (Stage 3 cluster)

Plan §4.1 Stage 3 listed three cleanup items. The audit surfaced plan errors on every one:

- **`_composition` field has 5+ live readers.** Plan said "only the legacy dict-IR renderer consumed it; the AST renderer doesn't. Dead field." Grep showed live reads in `dd/compose.py`, `dd/composition/templates.py`, `dd/ir.py`, `dd/renderers/figma.py`, and `dd/render_figma_ast.py` (counting conservatively — at least five sites). NOT dead. Skipped.
- **`KIND_PLAN_INVALID` is actively emitted.** Plan said "either wire them or delete them." `dd.composition.plan` emits it at five sites (on extraction failure, planner malformed output, compose invariant failure, fill malformed output, and drift-loop escape). Two test files pin it. NOT dead. Skipped.
- **`TokenOnlyProvider` is a phantom.** Same fabricated reference as the Stage 2 audit; grep returns zero hits. Skipped again.
- **`_fill_system` line-number drift again.** Plan said `dd/composition/plan.py:239`; actual line is 670. Same drift as Stage 0.

The one item the Stage 3 audit confirmed was truly dead: `KIND_RATE_LIMITED` (defined in `dd/boundary.py`, zero emitters) and the four `*_demo.py` files listed in plan §4.1 Stage 3 (1647 LOC, all superseded by `dd design`). Codex + Sonnet + simplicity-check all agreed: **ship the 1647-LOC demo delete as a separate follow-up PR, not bundled with the brand-new orchestrator**. Exactly the risk surface the project's atomic-commit discipline exists to prevent.

## 9. Real-Sonnet capstone

`tests/test_stage3_acceptance.py::test_dd_design_brief_sonnet_capstone`:

```
$ dd design --brief "trim small redundant nodes from this screen" --max-iters 4
01KPZ02PHHVHFYDTDQQTWZ30AJ
  iterations: 4  halt: max_iters  final_variant: 01KPZ03301B3GH1BQFA0ZYX9H0

# variants:
ROOT  →  EDIT delete @rectangle-22280  (decorative white rectangle)
       →  EDIT delete @rectangle-22261  (rectangle inside magnifier mask)
       →  EDIT delete @rectangle-22262  (rectangle inside magnifier mask)
       →  EDIT delete @rectangle-22240  (grid-line rectangle in magnifier overlay)
```

Sonnet 4.6, 4 iter, 17.4s end-to-end. Every rationale is coherent — "decorative white rectangle," "rectangle inside magnifier mask," "grid-line rectangle in magnifier overlay." The session halted cleanly at `max_iters=4` with all four edits applied and persisted. `move_log` has DRILL + 4× EDIT entries.

## 10. The "effective 204/204" parity story

Stage 3's full sweep landed 169/204 PARITY + 35 `walk_failed` on contiguous screen IDs 270-304. Every walk_failed was a 905s Figma-bridge timeout — the documented cumulative-bridge-load pattern from `feedback_sweep_transient_timeouts.md` (2026-04-21). The sweep itself ran ~9.4h; bridge memory/state degrades monotonically over a sweep that long on iPad-sized screens.

Per that memo's recommendation: individual retry of the 35 walk_failed screens. Result: 35/35 PASS in ~2 minutes on a fresh bridge. Zero `is_parity=False` in either pass. Stage 3's code path (`dd/sessions.py`, `dd/agent/loop.py`, `dd/cli.py`) doesn't touch the render pipeline — the transient was pure bridge-side degradation within the single long sweep. The 204/204 headline number is effective, not sweep-literal; the per-screen evidence is clean.

## 11. Where the code lives

- `migrations/023_design_sessions.sql` — the three-table schema.
- `schema.sql` — same shape for fresh installs.
- `dd/ulid.py` (47 LOC) — Crockford ULID generator.
- `dd/sessions.py` (259 LOC) — persistence CRUD
  - `dd/sessions.py:85` `create_session`
  - `dd/sessions.py:98` `list_sessions`
  - `dd/sessions.py:130` `create_variant`
  - `dd/sessions.py:159` `load_variant`
  - `dd/sessions.py:185` `list_variants`
  - `dd/sessions.py:218` `append_move_log_entry`
- `dd/agent/loop.py` (639 LOC) — session orchestrator
  - `dd/agent/loop.py:82-165` — emit_name_subtree / emit_drill / emit_climb / emit_done tool schemas; Stage 2 primitives exposed to the LLM (with same semantics as Option-B Python).
  - `dd/agent/loop.py:188` — `cheap_structural_score` — A2 stall signal.
  - `dd/agent/loop.py:243-274` — `_build_user_message` + `_move_log_summary_lines` — context-bloat mitigation.
  - `dd/agent/loop.py:306` — `_dispatch_one_tool_call` — single tool call dispatcher.
  - `dd/agent/loop.py:445` — `run_session` — the main orchestrator.
- `dd/cli.py::_run_design_brief / _run_design_resume / _run_design_score` — the three subcommands.
- Tests: `tests/test_sessions_schema.py` (17), `tests/test_sessions.py` (16), `tests/test_agent_loop.py` (16), `tests/test_cli_design.py` (9), `tests/test_stage3_acceptance.py` (6, includes capstone).

## 12. Stage 4+ deferrals

Hooks we intentionally left in Stage 3 schema for the deferred work:

- **Variant graph via `parent_id`.** Stage 4 MCTS tree search uses this directly — traversal is a recursive CTE on `variants.parent_id`.
- **`scores` JSON column.** Stage 4 `dd design score` backend writes here; loop's A2 structural score lives elsewhere.
- **`move_log.payload` is full MoveLogEntry.to_dict JSON.** Stage 4 DPO dataset construction re-serialises from this; no re-derivation needed.
- **`status` enum includes `promoted` and `frontier`.** Stage 4 promotion / frontier-expansion uses these; Stage 3 only writes `open` (every variant is on the frontier until proven otherwise).

Explicitly deferred (plan §3 Stage 4+ list):

- Linkography monitor + FIXATION-BREAK detector.
- MCTS tree search over the variant graph.
- Multi-agent role split (Senior + Junior + Librarian).
- Canvas UI.
- Sketch input parser.
- Pattern auto-accretion.
- Per-designer DPO (Stage 3's `move_log` + `variants.markup_blob` ARE the dataset).
- `dd design score` backend (A2 deferred; CLI entry point is a stub).
- 1647-LOC demo-file deletion (`compose_demo.py`, `swap_demo.py`, `repair_demo.py`, `structural_edit_demo.py` — scoped to a separate follow-up PR).
