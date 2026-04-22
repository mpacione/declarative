# Continuation — post-type-role-split handoff

**Session date**: 2026-04-22.
**End state**: `type-role-stage-4a-complete` tag on `v0.3-integration`.
**Read first to ground**: [plan-type-role-split.md](plan-type-role-split.md), then this file, then the deferred-work list below.

## What shipped this session

A focused architectural fix for the 25-drift cluster flagged in the prior handoff.

### The type/role split (11 commits)

IR now carries **`type`** (structural primitive, always present, from `node_type`) separately from **`role`** (classifier semantic label, optional, elided when `role == type`). Downstream dispatch reads `type` — renders stop crashing on classifier errors. Grammar/labeling reads `role`. See [project_type_role_split.md](../../.claude/projects/-Users-mattpacione-declarative-build/memory/project_type_role_split.md) for the shorthand; the canonical design doc is [plan-type-role-split.md](plan-type-role-split.md).

| Tag | Scope |
|---|---|
| `pre-type-role-split` | rollback point |
| `type-role-stage-0-complete` | migration 021 + backfill (49,670 nodes) |
| `type-role-stage-1-complete` | `map_node_to_element` split |
| `type-role-stage-2-complete` | eid `{role‖type}` rule tests |
| `type-role-stage-3a-complete` | `compose.py` + `corpus_retrieval.py` role-first readers |
| `type-role-stage-4a-complete` | grammar emits `role=` in markup head |

Commits: `f01d024` (plan) → `4adc0e1` (migration) → `0b86830` (backfill) → `33898e9` (classify_v2 sync) → `32041b0` (query read) → `75e4e36` (perf) → `ae09ce6` (Stage 1) → `9938618` (Stage 2) → `1189b4b` (3a compose) → `768923f` (3a corpus_retrieval) → `7085c90` (4a grammar).

### Sweep result

End-to-end parity against the Figma bridge (port 9224, 2026-04-22):

| | Pre-split | Post-split |
|---|---|---|
| is_parity=True | 179/204 | **189/204** |
| Plus 234 individual retry (transient) | | **190/204** |
| `leaf_type_append_skipped` across corpus | 22 | **0** |
| Elapsed | — | 43 min |

11 screens cleanly recovered — exactly the 217-228 leaf-type-append cluster predicted from the codegen-level preview. Zero new regressions. Test baseline: 3179 passing / 37 pre-existing failing (unchanged from session start).

## Deferred this session (priority-ordered)

### High — the 14 remaining drifts

Two bug classes, **neither is type/role** — both predate the type/role work.

1. **iPad Pro 12.9" component-FRAME inlining cluster** (13 screens: 241, 242, 243, 252, 264, 266, 268, 294, 295, 296, 321, 325, 332). All share `button/large/translucent` FRAMEs with `component_key=None` containing inlined component children (icon/font INSTANCE, Vector, text, icon/chevron-down INSTANCE). Exactly 5 `missing_child` errors each at ~0.96 parity. Start point: diff `render_batch/scripts/241.js` against walk output for the missing eids. See [feedback_ipad_component_frame_inlining.md](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_ipad_component_frame_inlining.md).

2. **Screen 180 outlier** — 32 `missing_child` errors of mixed types (buttons/containers/icons). Different pattern; dedicated investigation needed.

### Medium — type/role arc sub-stages

- **Stage 3b** — Mode 3 LLM prompt updates to teach the synthesis LLM about the `type`/`role` split. Only moves the needle when Mode 3 emission is being improved. Deferred pending Mode 3 roadmap context.
- **Stage 4b** — verifier `role_type_incompatible` compat rule feeding the M7.5 repair loop. Safety net, not unblocking anything today. Deferred pending concrete repair-loop use case.

### Lower — from prior handoff, still pending

- `docs/module-reference.md` body refresh (header partial-update notice; body is M4-era)
- Script consolidation (4×set_*_demo → 1, 3×tier_d → 1, bakeoff_som merge)
- dd/* dead-code deletions — 5 candidates entangled with M6(b) deprecation
- Designer-agent loop architecture — user wants additive orchestration, not parallel system
- `link-1` empty in archetype output (same class as leaf-type contract)
- ADR-008 Fix #4 (button/icon inheritance)
- ADR-008 Fix #5 (horizontal layout collapse)

## Pointers for next session start

```bash
# Confirm state
git tag -l 'type-role-*'
# expected: pre-type-role-split, type-role-stage-0..4a-complete

git log --oneline -11
# latest = feat(type-role-split): Stage 4a — compressor emits role=

.venv/bin/python3 -m pytest tests/ -q --tb=no --timeout=60 2>&1 | tail -3
# expected: 3179 passed, 37 failed, 6 skipped

# If picking up the iPad cluster:
.venv/bin/python3 -m dd generate --db Dank-EXP-02.declarative.db --screen 241 > /tmp/241.js
diff <(grep -E 'n[0-9]+.*icon-10|n[0-9]+.*vector-21' /tmp/241.js) <(jq '.eid_map | keys[]' render_batch/walks/241.json | grep -E 'icon-10|vector-21')
# expected: discrepancy showing where children fall through
```

## Critical session-learnings

1. **The primitive/semantic split at the data-model layer confines classifier error to an annotation class.** Wrong `role` is ugly; wrong `type` breaks renders. Separating the two fields meant downstream readers inherited correctness for free — Phase 1 createX dispatch and the leaf-parent gate both went from buggy to correct via one IR-layer change, without touching their code. MLIR's Type/Attribute split is the compiler-IR analogue; Webstudio's `{type, component, tag}` is the design-system analogue.
2. **TDD discipline plus single-source measurement** kept the 5-stage arc honest — every RED had a matching GREEN, fixture churn got committed separately from logic, and acceptance gates were measured against the real DB not re-inferred from passing tests.
3. **The remaining 14 drifts were NOT fixed by type/role and aren't supposed to be.** My plan's "≤4 other-cause drifts" estimate was optimistic; reality was 14, all of a different bug class that the sweep cleanly exposed now that the type/role noise is gone. This is progress: we now have two clean classes to attack separately.
4. **Per-screen retry layer (sweep.py commit `88c3356`) earned its keep** — 18 retries, 3 recovered to PARITY, 1 persistent transient (screen 234; individual re-run recovered it cleanly).

That's the handoff. Type/role split is shipped, measured, tagged; the iPad cluster + 180 outlier are cleanly scoped as the next drift-work bucket; Stages 3b/4b are deferred with clear triggers. Next session picks any deferred item or continues on drift cluster-A.

---

## Continuation — 2026-04-22 autonomous carryover sprint

Session after the above handoff. User ran: "do all the carryover cleanup work please. Then find the root cause of the drift which surfaced."

Safety tag: `pre-carryover-cleanup-2026-04-22`.

### Work shipped (3 commits)

1. **[`9ecaed2`](../..)** — `docs(module-reference): append v0.3 Pipeline Additions section (M5–M7)`. Adds an inventory of every M5-M7 module plus the type/role additions + migrations table; Layer 1-4 body left intact. Header timestamp bumped, currency notice rewritten to point to the new section.
2. **[`<archive commit>`](../..)** — `chore(scripts): archive 8 one-off scripts to scripts/archive/`. Zero-reference verified for each; 3180 tests still passing.
3. **[Revert of `a063ff2`]** — slot-flatten attempted fix was reverted (see § Drift root cause below).

### Explicitly deferred with rationale

- **Script consolidations** (4×`set_*_demo`, 3×`tier_d_*`, `bakeoff_som` merge) — each is a 300-line demo with property-specific AST logic; safe consolidation needs TDD against live LLM calls, which this session could not do autonomously.
- **`dd/*` dead-code deletions** — 5 candidates flagged in April cleanup were found to have live callers; ongoing M6(b) deprecation coordination owns these.
- **Designer-agent loop architecture** — user flagged this needs scope confirmation (additive orchestration vs parallel system) before starting.
- **`link-1` empty defect, ADR-008 Fix #4 (button/icon inheritance), Fix #5 (horizontal layout collapse)** — all three are Mode 3 scope; co-deferred with Stage 3b (Mode 3 LLM prompt update).

### Drift root cause (CONFIRMED, fix reverted)

**All 14 drifts are one bug class:** `compress_l3._build_node` reads `element["children"]` only. `build_semantic_tree` in `dd/ir.py` moves children into `element["slots"]` for classified nodes with slot schemas, so slotted kids silently vanish from the markup for inline-rendered nodes.

- 13 iPad Pro 12.9" screens: `button/large/translucent` FRAME with `component_key=None` classified as `button` → 5 slot children dropped each
- Screen 180: nested cascade of slot schemas (`tabs-1 → 4 buttons → 2 icon slots each`) → 32 errors

**Attempted fix** (`a063ff2`): flatten slot values into child_ids when no direct children list and head_kind != "comp-ref". Semantically correct; passed 2 new tests; full suite green (+1 skip on the stale M3 byte-parity gate).

**Reverted** (`bde96f2`): the post-fix scripts grew past Figma's 170s `PROXY_EXECUTE` timeout when rendered (many more `createInstance`/`createFrame`/`appendChild` calls per screen). Walk fails consistently across 3 retries. Failure mode degraded from `drift-with-5-missing-children` to `walk timeout` — strictly worse.

**Memory note with full diagnosis**: [feedback_ipad_component_frame_inlining.md](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_ipad_component_frame_inlining.md). Lists 5 paths forward (selective-flatten, classifier-side, render perf, walk chunking, accept drift); user should decide before next attempt.

### Final state 2026-04-22

- Tags: `pre-type-role-split` → `type-role-stage-0..4a-complete` → `pre-carryover-cleanup-2026-04-22`
- Branch: `v0.3-integration`
- Working tree: clean
- Tests: 3179 / 37 / 6 (baseline unchanged)
- Real-DB parity: 190/204 (unchanged from post-type/role-split sweep, slot-flatten fix reverted)
- Module-reference: refreshed with M5-M7 inventory
- Scripts: 8 one-offs archived

### Pickup points for next session

- **Decide drift path** (feedback_ipad_component_frame_inlining.md): pick between selective-flatten, classifier-side filter, or accept-the-drift. #1 and #2 are low-risk.
- **Resume carryover queue**: demos consolidation (TDD session), `bakeoff_som` merge, dead-code deletions (coordinate with M6(b)), designer-agent scope conversation.
- **Stage 3b + 4b**: when Mode 3 roadmap firms up / when M7.5 repair loop needs structured compat errors.
