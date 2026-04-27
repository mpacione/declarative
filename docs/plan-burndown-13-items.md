# Sequential 13-item burn-down plan

**Branch**: `v0.3-integration`
**Start tip**: `05a3337` (post-Sprint-2)
**Plan authors**: Claude Opus 4.7 (main thread) + Codex 5.5 high-reasoning (architectural partner)
**Date**: 2026-04-27

User directive: *"work through each of these sequentially up to #13"* +
*"same routine. use codex and sonnet subagents to help provide second
opinions, coding, reviews."*

This doc captures the sequencing locked at Codex round-11 and serves
as the master burn-down. Per-item docs (sprint results) ship as they
land.

## The 13 items

| # | Item | Type | Predicted commits |
|---|---|---|---:|
| 1 | Renderer `parent_is_autolayout` gate fix | Tactical bug fix | 1-2 |
| 2 | VECTOR cornerRadius capability gap | One-line fix | 1 |
| 3 | Sprint 3: auto-layout family (8 props) | Sprint | ~5 |
| 4 | Sprint 4: text-styling family (13 props) | Sprint | ~5-6 |
| 5 | Sprint 5: min/max sizing family (4 props) | Sprint | ~3 |
| 6 | Sprint 6: constraints family (2 props) | Sprint | ~2 |
| 7 | Project vocabulary post-IR transform | Architectural | TBD (design first) |
| 8 | Multi-backend abstraction promotion | **Gated** (defer) | 0 — design only |
| 9 | `test_mode3_contract.py` 2 failures | Test fix | 1-2 |
| 10 | `test_phase2_integration.py` 5 failures | Test fix | 1-2 |
| 11 | `test_component_key_registry.py` schema drift | Test fix | 1 |
| 12 | 13 other pre-existing test failures triage | Triage | TBD |
| 13 | M7 synth-gen continuation | Multi-sprint | Own plan doc |

**Total predicted Sprint 2 → 13 commits**: ~30+ excluding item 13.

## Order rationale (Codex round-11 lock)

- **1-7 sequential as planned**: each extends the rail in dependency
  order. Renderer gate → capability gap → property family
  graduations → vocabulary.
- **8 is a documented gate**: defer execution until backend #2 ships.
  Document the dispatch boundary and trigger.
- **9-12 cluster operationally** as a "test cleanup sprint" but stay
  visible as four items (different failure causes).
- **13 is last**: synth-gen consumes the extended rail.

## Pre-item-3 prerequisite: known-fail ledger

Per Codex round-11: *"before starting item 3, record a known-fail
ledger for 9-12 so later test output can distinguish new regressions
from pre-existing noise."*

Ledger lives at `docs/known-test-failures-pre-burndown.md` (will be
created when items 1-2 are done; updated as items 9-12 close).

## Per-item structure

### Items 1, 2 (tactical fixes)

- Single-commit (item 1 may be 2 if Plugin API per-type splits)
- Codex consult only if architectural fork emerges
- Sonnet pre-commit reviewer
- Targeted Dank re-sweep to verify the bug actually closes
- No results doc (commit message is the artifact)

### Items 3, 4, 5, 6 (Sprint-style)

Reuse the Sprint 2 commit shape (trimmed where C6/C7/C10
infrastructure already exists):

1. Inventory disposition shifts (registry `_STATION_3/4_INVENTORY`
   updates)
2. Walker capture additions (the per-property `entry.<name>`
   assignments)
3. Registry `compare_figma=` metadata wiring
4. KIND_* constants + comparator implementations (or reuse generic
   `enum_equality` / `numeric_equality`)
5. Cross-corpus regression sweep + results doc

Predicted shapes per Codex round-11:
- Sprint 3 auto-layout: ~5 commits
- Sprint 4 text-styling: ~5-6 commits (lineHeight/letterSpacing may
  need unit normalization)
- Sprint 5 min/max: ~3 commits
- Sprint 6 constraints: ~2 commits

### Special comparators (Codex round-11 flag)

Beyond `text_equality` / `enum_equality` / `numeric_equality`:

- **padding*, itemSpacing, counterAxisSpacing** (Sprint 3): numeric
  tolerance + absent-vs-zero semantics
- **fontName** (Sprint 4): structured comparison, family/style
  normalization
- **lineHeight** (Sprint 4): pixels / percent / auto / mixed shapes
- **letterSpacing** (Sprint 4): pixels or percent units
- **min/max sizing** (Sprint 5): numeric tolerance + absent/undefined
- **constraints** (Sprint 6): structured enum/object, don't flatten
  casually

These all become new entries in `dd/verify_figma.py:_COMPARATOR_IMPLS`
with their own implementation functions (Sprint 2 C10 pattern).

### Item 7 (project vocabulary) — design first

Per Codex round-mid-Sprint-2 lock + round-11 caveat *"Vocabulary can
easily sprawl"*: write `docs/plan-project-vocabulary.md` co-locked
with Codex BEFORE writing code. New module
`dd/project_vocabulary.py`; reuse `dd/cluster.py` math; Codex option B
post-IR transform (NOT a fourth mode).

Inputs:
- Source vocabulary computation (frequency + clustering per property type)
- Snap-or-keep policy (high-confidence threshold, semantic-outlier
  protection)
- Validation (offline A/B harness before VLM)

### Item 8 (multi-backend) — gated, document only

Codex round-11: *"do not execute promotion yet. Treat it as a gated
architecture checkpoint."* Deliverable:

- `docs/plan-multi-backend-promotion.md` — describes when the
  current `compare_figma` / `FigmaComparatorSpec` naming graduates
  to per-backend dispatch (`compare={"figma": ..., "html": ...}`)
- Trigger condition: backend #2 design ships
- No code commits in this item

### Items 9, 10, 11, 12 (test cleanup)

Cluster into one "Sprint X: test cleanup" with four sub-items.
Per item:
- Identify the failure root cause
- Sonnet worker fixes if scope is bounded
- Main thread reviews
- Update the known-fail ledger as each closes

### Item 13 (M7 synth-gen) — own plan doc

After items 1-12 land. Per memory M7 track:
- M7.6 S4.1, S4.3-S4.6
- VLM fidelity gate
- GBNF grammar generation from registry (consumes Sprint 2-7 rail)
- Second-project validation

Big enough to warrant its own multi-sprint plan
(`docs/plan-m7-synth-gen-continuation.md`).

## Coordination per item (Codex round-11 lock)

- **Codex 5.5** at every architectural fork (sprint-plan time +
  decision moments). Singular per fork.
- **Sonnet workers** for parallelizable leaf work (capture/property
  edits). Workers own ONLY leaf files; never shared registries.
- **Sonnet pre-commit reviewers** after every main-thread commit
  except trivial inventory updates.
- **Main thread (me)** owns: registry schema, comparator dispatch,
  manifest schema, IR build, final integration.

## Checkpoints (Codex round-11 lock)

Major boundary checkpoints (not every commit):

- After items 1+2 (one-line fixes done)
- After Sprint 3 (auto-layout family)
- After Sprint 4 (text-styling family)
- After Sprint 5/6 together (small families)
- After item 7 (vocabulary)
- After test cleanup (items 9-12)
- Before item 13 (synth-gen launch)

User check-in expected at each checkpoint unless they push through.

## Risk register

### R1 — Pre-existing tests masking new failures

**Mitigation** (Codex round-11): record known-fail ledger before item 3.

### R2 — Parallel-write hazard with multiple Sonnet workers

**Mitigation**: workers own disjoint property files only. Main thread
serial on shared infrastructure (registry, dispatch, manifest schema).

### R3 — Item 7 (vocabulary) bloats mid-implementation

**Mitigation**: design doc co-locked with Codex before any code.
Codex round-mid-Sprint-2 already laid the architecture (option B
post-IR transform); item 7 just executes against that design.

### R4 — Items 3-7 take longer than estimated, item 13 starts late

**Mitigation**: items 9-12 are interruptible — can defer to
post-item-13 if schedule pressure hits.

### R5 — Stop-and-ship point unclear

**Mitigation** per Codex round-11: *"after item 7 is the right
natural checkpoint. If schedule pressure hits earlier, after Sprint 4
is also defensible."*

## Definition of done

The full 13-item burn-down is done when:

1. ✅ Plan doc committed (this file)
2. Items 1-12 each land per their per-item criterion above
3. Item 13 has its own plan doc + at least the M7.6 remaining S4.x
   work shipped
4. The cross-corpus sweep on Nouns + Dank + HGB shows clean-or-real-bugs
   with the layoutSizing class closed and family graduations
   adding signal
5. Synth-gen feedback loop coherence is observable in `dd design
   score` against synthetic IR

---

**Co-authored**: Claude Opus 4.7 + Codex 5.5 round-11 architectural
sequencing call
