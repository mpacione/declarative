# Continuation — slot visibility grammar (next session)

**Session date**: 2026-04-22 (late).
**End state**: **PR 2 (Stages 1–5) shipped** — commits `0e8aeb5` / `e977ecc` / `6ddf098` / `bc193a4` on `v0.3-integration`. **PR 1 in flight** (unified visibility resolver + `hidden_children` removal, subagent `a7085f02af8acd030` in isolated worktree). When PR 1 lands HEAD will advance beyond `bc193a4`; `git reset --hard bc193a4` rolls back PR 1; `git reset --hard f1fa345` rolls back the whole slot-visibility arc.
**Read first, in order**:
1. [continuation-post-type-role-split.md](continuation-post-type-role-split.md) — the handoff that precedes this one (type/role split + carryover sprint, ends at commit `bde96f2` / tag `pre-carryover-cleanup-2026-04-22`).
2. This file (slot preservation + Phase 1 perf + visual bug + grammar decision).
3. [plan-slot-visibility-grammar.md](plan-slot-visibility-grammar.md) — the PR-2 plan (being written concurrently by a subagent; may not exist yet — create if missing).
4. [spec-dd-markup-grammar.md](spec-dd-markup-grammar.md) — grammar spec, amend per PR 2.

The previous handoff stopped at "decide drift path (feedback_ipad_component_frame_inlining.md): pick between selective-flatten, classifier-side filter, or accept-the-drift." This session picked selective-flatten (Option 2), shipped it, fixed the perf regression, hit a newly-visible rendering defect during the sweep, root-caused it to pre-existing code, and locked the grammar design for the fix.

---

## 1. Session chronology — what shipped 2026-04-22 (late)

Five commits on top of `bde96f2`, landing the deferred slot-flatten fix and a Phase-1 perf pass. Then a sweep uncovered a separate rendering bug, which was root-caused but **not** fixed.

### 1.1 Slot preservation — Option 2 (commit `27196d8`)

**Problem (from previous handoff)**: `compress_l3._build_node` read `element["children"]` only. `build_semantic_tree` in `dd/ir.py` moves children into `element["slots"]` for classified nodes with slot schemas. Slotted kids silently vanished from markup for inline-rendered nodes → 14 drifting screens post-type/role-split (13 iPad Pro 12.9" + screen 180 outlier).

**What was tried last session (reverted)**: `a063ff2` flattened slot values into `child_ids` blindly. Semantically correct but blew past Figma's 170s `PROXY_EXECUTE` timeout → reverted in `bde96f2`.

**Option 2 as shipped**:
- Compressor emits `slot=<name>` as a head `PropAssign` on each slotted child.
- Grammar parses it as a regular prop — **no schema change**, no new keyword, no SlotFill node.
- `slot=` sits in the structural `_prop_rank` bucket next to `role=` so it survives round-trip.
- Slot identity is thus preserved via the child's own head, which the renderer sees and ignores (it already dispatches on `type` / `role`).

### 1.2 Phase 1 perf cycles (commits `50b023b`, `7b7a7bc`, `e19bdba`, `f1fa345`)

After Option 2, scripts grew denser and re-hit the timeout. Four targeted perf changes landed:

| Commit | Change | Impact |
|---|---|---|
| `50b023b` | Wrapper timeout 170s → 300s (`dd/bridge/walk_ref.js` + `scripts/sweep.py`). Figma has **no hard timeout** — 170s was ours. | Unblocks heavy screens under the new density. |
| `7b7a7bc` | Sequential `await figma.loadFontAsync` → single `Promise.all([...])`. Measured 28 awaits → 1 on screen 241. | Big per-screen wall-clock win. |
| `e19bdba` | `figma.skipInvisibleInstanceChildren = true` at script entry. | Figma-level perf hint. |
| `f1fa345` | Side-car `pop()` after `replace()` (Python `id()` reuse defense) + var-map fallback-idx: when slot children aren't in `_baseline_walk_indices` (which only walks `children`, not slots), fallback starts at `max(baseline_walk_idx.values())+1`. | Correctness fix discovered while validating perf cycle 3. |

### 1.3 Targeted sweep validation

After the perf work, ran the sweep against the **14 previously-drifting screens only**:
- **Result: 14/14 PARITY in 38.5s.**
- Full test suite: 3183 passed, 37 failed (pre-existing, unchanged from type/role split), 12 skipped.

Then kicked off the full 204 sweep — **user stopped it at 36/204** when they spotted visual regressions on screens with nav chrome / toolbars (details in §2). Monitor task id `bl20byvkd` was terminated. **Do not restart the full sweep until the visual bug is fixed.**

---

## 2. The visual bug — root-caused, NOT fixed

User observed missing chrome on rendered screens:
- DANK wordmark (top-left)
- Workshop button
- Meme-00001 dropdown
- Share icon
- Toolbar-row-2 leading icons: brush-lines, opacity-disc, brush-cap

### 2.1 Root cause (confirmed)

Two co-equal call sites:
- `dd/ir.py:670-687` — the `hidden_children` SQL harvests `visible=0` descendants **by name only** (no node id, no path).
- `dd/render_figma_ast.py:895-901` and `dd/renderers/figma.py:1214-1220` — emit `var.findOne(n => n.name === "<hname>"); if (_h) _h.visible = false;`.

For masters with multiple same-name descendants, `findOne` returns the **first** by tree order. Concrete example from Dank-EXP-02:

> `nav/top-nav` contains **two** descendants named `logo/dank` — one visible (Figma node id `13930`), one hidden (`13964`). Harvest emits `{"name": "logo/dank"}`. Renderer `findOne(... name === "logo/dank")` binds `_h` to `13930` (the visible one), then sets `_h.visible = false`. The hidden twin never gets hidden (harmless); the visible logo disappears (bug).

**Pre-existing, not type/role-split regression.** Reproduced against `pre-type-role-split` tag: identical emission. The Option-2 slot-flatten fix didn't create the bug — it made more masters traverse enough depth for the `findOne` ambiguity to bite visible chrome.

### 2.2 Parallel working path already in the codebase

`build_override_tree` at `dd/ir.py:837` keys on **stable descendant identity**: semicolon-delimited Figma node ids (`;pageId:nodeId`). Renderer uses `findOne(n => n.id.endsWith(";<figmaNodeId>"))` — unambiguous.

`instance_overrides` (Plugin-API data, already in the DB) includes BOOLEAN `:visible` entries. **20,803 such rows in Dank-EXP-02.** The tree already handles them.

So the fix is: **delete the `hidden_children` parallel harvest and rely on `instance_overrides` → `override_tree`.** The only risk is coverage — are there any hidden descendants present in `hidden_children` but missing from `instance_overrides`? Subagent B is measuring this (see §4.1).

---

## 3. Research + grammar decision (locked)

### 3.1 Research agent `ab42bb9b3a8124ad5` — prior art survey

Survey covered Web Components, React/Vue/Svelte, Plasmic, Mitosis, Webstudio, Penpot, Figma. **Key finding: Figma + Penpot are the only design tools with "clone-tree + diff" override semantics.** Every other backend (React, Plasmic, Webstudio, Mitosis) renders outside-in: parent decides which children to render. No backend uses `hidden_children`-style post-hoc mutation keyed on name.

Other research agents this session:
- `ac7be9e21e07156fb` — classifier robustness (separate thread, not used for this decision)
- `ab742a1da5ee46669` — IR prior art for visibility representation
- `aa9eb2062cc0705de` — Figma perf (fed the Phase 1 cycles above)

### 3.2 Four invariants the grammar form must satisfy

Before picking a form, locked the acceptance criteria:

1. **Round-trip survival**: compress → markup → parse preserves identity.
2. **Computable from IR-level diff** (master vs instance) — **no backend consultation**. No `getMainComponentAsync`, no name lookups in the Figma runtime tree.
3. **Re-emittable by LLM** given only the master's `define` signature. The LLM can't introspect the Figma runtime; it only has the schema.
4. **Carries enough info for each backend**: Figma (override array), React/Vue (conditional render), SwiftUI (EmptyView), Mitosis (null-slot).

### 3.3 Grammar decision

**Primitive A: PathOverride with `.visible=false`** — sugar-free form, always legal:

```
-> nav/top-nav {
  left.logo/dank.visible = false
  trailing_icon = {empty}
}
```

**Sugar C: `{empty}` SlotFill sentinel** — for the common case of "this slot is empty in this instance". Parses to the same IR as a PathOverride with `.visible=false` on the slot's placeholder child.

**Rejected**: dedicated `hide` keyword (agent's option B). Redundant given PathOverride already addresses any descendant by path; a keyword adds a parser case and an IR kind with no semantic gain.

**Key invariant (restated for emphasis)**: visibility is keyed by **stable descendant identity** (slot name + type-path + optional index for homonymous siblings), NOT by Figma-runtime node ids. This means:
- Compressor can emit it from DB state alone.
- LLM can emit it from the master's `define` signature alone.
- Every backend can resolve it without a runtime tree walk.

---

## 4. PR scope (two PRs, sequenced)

### 4.1 PR 1 — data layer (small, ~4-6h, TDD)

**Scope**: Delete `hidden_children` path entirely.

- Remove the SQL harvest in `dd/ir.py:670-687`.
- Remove the `hidden_children` key from the per-node dict.
- Remove the `findOne(... name === ...)` emitter at `dd/render_figma_ast.py:895-901` AND `dd/renderers/figma.py:1214-1220`.
- Verify `instance_overrides` → `override_tree` covers every case.

**Gating**: Subagent B (already run, output at `/private/tmp/.../tasks/...output` — check before starting) measured the delta. It should report:
- How many nodes are hidden via `hidden_children` today.
- How many of those have a matching `instance_overrides` entry with `property_type='BOOLEAN'` and `property_name=':visible'`.
- The orphan count = number of nodes only reachable via `hidden_children`. **If orphan count == 0, PR 1 is go.** If non-zero, extract the missing cases into `instance_overrides` during migration or find a third source.

**Why this PR first**: the visual bug blocks the full sweep. Fixing it unblocks measurement of all downstream work. It's also strictly a deletion + verification — no new grammar, no new renderer paths.

### 4.2 PR 2 — grammar extension (~2 days, TDD)

**Scope**: Make PathOverride with `.visible=false` flow end-to-end.

- Extend `dd/compress_l3.py` to emit `PathOverride` nodes when the instance's override tree has `:visible=false` entries.
- Extend `dd/markup_l3.py` parser + emitter for `{empty}` SlotFill sugar (the dataclass may already exist — check `SlotFill`, `SlotPlaceholder`, `PropAssign` definitions).
- Extend `dd/render_figma_ast.py` to lower PathOverride → `var.findOne(... id.endsWith(";...")); _t.visible = false`.
- Round-trip tests: compress → markup text → parse → markup AST identical (modulo whitespace).
- Multi-backend stub tests: PathOverride resolves to the same semantic result in React/SwiftUI stubs (both `invariant #4`).

Subagent D is currently executing this PR. Check `git log --oneline` for its commits; check `tests/` for new test files prefixed with the slot-visibility topic.

---

## 5. Pickup points — do these in order

1. **Check subagent B output** for orphan count. Path: `/private/tmp/.../tasks/...output` (exact path in subagent's message; if unavailable, re-run the measurement — query shape in §2.2).
2. **Check subagent D's commits + tests.** `git log --oneline v0.3-integration` for anything past `f1fa345`. Run `pytest tests/test_markup*.py tests/test_compress*.py -q` on those new files.
3. **Decide PR 1 merge** based on orphan count. If 0: merge, re-run the targeted 14-screen sweep to confirm visual bug fixed (DANK wordmark present), then re-run the full 204 sweep.
4. **Do NOT restart the full sweep before the visual bug is fixed.** User stopped it mid-flight (task `bl20byvkd`) specifically because of the bug; restarting burns bridge time and produces meaningless "parity" numbers.
5. **Review PR 2** once D completes. Verify the four invariants from §3.2 are tested, not just asserted.
6. **Cross-reference check**: confirm this file and `continuation-post-type-role-split.md` both mention each other (they do — §top of this file; the previous handoff's own "pickup points" section may need an appended note linking here).

---

## 6. Critical files + commits

### Branch / tags
- Branch: `v0.3-integration`
- Latest safe commit: `f1fa345` (Phase 1 cycle 4 + side-car fix)
- Rollback tags:
  - `pre-type-role-split` — before the whole arc
  - `type-role-stage-0-complete` … `type-role-stage-4a-complete` — per-stage
  - `pre-carryover-cleanup-2026-04-22` — before the slot-flatten attempts (includes the reverted `a063ff2`)
- Rollback: `git reset --hard <tag>`

### Key files (with line citations verified 2026-04-22)
- `dd/ir.py`
  - `hidden_children` SQL: lines **670-687** (buggy — delete for PR 1)
  - `build_override_tree`: line **837** (the working path)
- `dd/compress_l3.py` — slot preservation (Option 2) + side-car pop fix from `f1fa345`
- `dd/render_figma_ast.py`
  - Preamble with `Promise.all` + `skipInvisibleInstanceChildren`: entry
  - Hide-by-name emitter: lines **895-901** (delete for PR 1)
- `dd/renderers/figma.py`
  - Hide-by-name emitter (older parallel path): lines **1214-1220** (delete for PR 1)
- `dd/markup_l3.py` — grammar parser/emitter. `SlotFill`, `SlotPlaceholder`, `PropAssign` dataclasses live here.
- `dd/bridge/walk_ref.js` + `scripts/sweep.py` — wrapper timeout (300s after `50b023b`)
- `docs/spec-dd-markup-grammar.md` — grammar spec (amend in PR 2)
- `docs/plan-slot-visibility-grammar.md` — PR 2 plan (subagent A writing; may not yet exist)

### Test baseline (2026-04-22 end of session)
```
3183 passed, 37 failed, 12 skipped, 61 warnings in 48.76s
```
The 37 failures are pre-existing and unchanged since the type/role split. Do not let them stall PR 1; they are documented in the previous handoff's deferred list.

### Real-DB parity baseline
- Pre-Option-2: 190/204 (14 drifting — the iPad cluster + screen 180)
- Post-Option-2 + Phase 1 perf: **14/14 on targeted sweep**, full sweep stopped at 36/204 because of visual bug
- Target after PR 1: full 204 sweep back to ≥190/204 with **zero visible chrome missing** (DANK wordmark test as smoke gate)

---

## 7. Don't lose these

### TDD is non-negotiable
Per the user's global `CLAUDE.md` — every production-code change must start with a failing test. This applies to PR 1 (write a test that currently passes because `hidden_children` emits, then remove `hidden_children`, the test fails, then migrate the test to exercise `instance_overrides`) and PR 2.

### User stopped the sweep mid-flight
Task id `bl20byvkd`, terminated at 36/204. Restarting before the visual bug is fixed burns ~40 minutes of bridge time on meaningless measurement. The targeted 14-screen sweep is a cheap (38.5s) smoke test.

### Research agent ids (for audit trail / follow-up)
- `ab42bb9b3a8124ad5` — slot-visibility grammar prior art (informed §3)
- `ac7be9e21e07156fb` — classifier robustness
- `ab742a1da5ee46669` — IR prior art for visibility
- `aa9eb2062cc0705de` — Figma perf (fed Phase 1 cycles)

### This bug class: structural parity ≠ visual correctness
`feedback_verifier_blind_to_visual_loss.md` in memory documents exactly this failure mode. The 190/204 "PARITY" pre-Option-2 already included the DANK-wordmark-missing class — the verifier saw every node emitted, just not that the wrong `findOne` target got hidden. Every visual-loss class needs its own `kind` + walker signal + verifier check. Consider a `KIND_HIDDEN_SIBLING_AMBIGUITY` follow-on to catch this class at compile time after PR 1 lands.

### Phase 1 perf was essential, not decorative
Without `50b023b` + `7b7a7bc` + `e19bdba`, Option 2's denser scripts would have failed with timeouts, exactly as `a063ff2` did. The perf isn't optional polish — it was a prerequisite for Option 2 to render at all on iPad Pro 12.9" screens. Keep that link in mind if PR 2 adds more density.

---

That's the handoff. Option 2 slot preservation shipped and validated (14/14 on targeted sweep); Phase 1 perf pass shipped (300s wrapper, Promise.all fonts, skipInvisibleInstanceChildren, side-car pop); full sweep uncovered a pre-existing visible-chrome-hide bug; root-caused to `hidden_children` name-only harvest with ambiguous `findOne`; grammar decision locked (PathOverride + `{empty}` sugar); two-PR plan with PR 1 (delete) sized small and currently blocked on subagent B's orphan-count verification.
