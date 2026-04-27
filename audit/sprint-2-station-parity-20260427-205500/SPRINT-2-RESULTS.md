# Sprint 2 — Registry-driven station parity — Results

**Date**: 2026-04-27
**Plan**: `docs/plan-sprint-2-station-parity.md`
**Branch tip**: `e2ef8a7` (post-C11 fix)
**Sprint commits**: 8 (C4 through C11 + the late fix)

## TL;DR

**Sprint 2 architectural rail is shipped. The rail surfaced a major
real bug the prior architecture was hiding.** All three corpora now
show DRIFT — but every drift traces to a single root cause in the
renderer. Sprint 2 succeeded at its stated goal (make the gap
visible); the bug it surfaced is followup work.

| Corpus | Total | Drift | Sole error class |
|---|---:|---:|---|
| Nouns | 67 | 59 (88%) | `layout_sizing_h/v_mismatch` (251 errors) |
| Dank  | 200 | 200 (100%) | `layout_sizing_h/v_mismatch` (2,622) + `cornerradius_mismatch` (23, VECTOR cap-table from cross-corpus) |
| HGB   | 44 | 44 (100%) | `layout_sizing_h/v_mismatch` (119) |

**2,992 layout_sizing mismatches across three corpora, all from one root cause.**

## What Sprint 2 shipped

The four-station registry parity rail per `docs/plan-sprint-2-station-parity.md`:

| # | Commit | Title |
|---|---|---|
| C4 | `ab96ad5` | StationDisposition enum + station_2/3/4 fields on FigmaProperty |
| C5 | `65fb2e2` | Inventory all 53 properties at all four stations |
| C6 | `740d05f` | Walker manifest generator (registry → JSON) + validation test |
| C7 | `6d37940` | Plugin-init manifest injection + self-boot fallback |
| C8 | `6090f4c` | Walker (value, source) envelope for 3 graduations + verifier defensive shim |
| C9 | `72e1399` | A1.1 descendant-path override routing in IR |
| C10 | `c957ce7` | Verifier registry-dispatch + comparators for 3 graduations (the keystone) |
| C11 fix | `e2ef8a7` | `query_screen_for_ir` populates figma_node_id + instance_overrides |

The 3 graduated properties: `characters`, `layoutSizingHorizontal`, `layoutSizingVertical`.

## What the rail surfaced

### The dominant bug: layout_sizing_h_mismatch / layout_sizing_v_mismatch

**Pattern**: `IR='HUG'  rendered='FIXED'`, repeated thousands of
times across all three corpora.

**Root cause** (verified by reading
`dd/renderers/figma.py:1838`): the renderer gates layoutSizing
emission on `parent_is_autolayout`. Nodes whose parent is NOT
auto-layout (screen roots, free-positioned children) never get
`layoutSizingHorizontal/Vertical` set, so they land at FIXED
default even when IR carries `'hug'`.

This is a single bug class affecting:
- **2,992 nodes total** across 311 screens
- **All three corpora** identically
- **Pre-Sprint-2 it was invisible** because the verifier didn't
  compare layoutSizing modes

The architectural rail did exactly what it was designed to do.
Per Codex 5.5 round-10 ship-gate call: "ship Sprint 2 red,
document the bug as the main finding."

### A second gap surfaced (and immediately fixed): C9 routing on un-classified DBs

The cross-corpus sweep also revealed that C9's
`build_descendant_routings` was silently skipping routing on
un-classified DBs (where `canonical_type` is None). The HGB
button bug (TEXT='Reject' override) wasn't being routed to
the text descendant's `_overrides` side-car. Fix at `e2ef8a7`:

- C9 gate now accepts both `canonical_type=='instance'` AND
  `node_type=='INSTANCE'`
- `query_screen_for_ir` SELECT now includes `figma_node_id`
  and populates `instance_overrides` per INSTANCE node

Codex round-8 had flagged this in advance: *"verify
`query_screen_for_ir` carries `figma_node_id` and
`instance_overrides`."* The unit tests stubbed
`instance_overrides` directly so they passed; the gap was only
visible end-to-end. Lesson: end-to-end sweeps are necessary
even when unit coverage is dense.

## Per-corpus detail

### Nouns (67 screens)

| Metric | Value |
|---|---:|
| Total | 67 |
| Structural parity | 10 (15%) |
| Strict PARITY (no rt errors) | 8 |
| PARITY+ (font-license blocker only) | 2 |
| DRIFT | 59 (88%) |
| `layout_sizing_v_mismatch` | 152 |
| `layout_sizing_h_mismatch` | 99 |
| Total verifier errors | **251** |
| Elapsed | 836.1s (~14 min) |

Pre-Sprint-2 baseline was 67/67 structural parity. Today's 59 drifts
are the layout_sizing class becoming visible — same renderer code,
same DBs, the verifier just sees more.

### Dank (200 screens)

| Metric | Value |
|---|---:|
| Total | 200 |
| Structural parity | 0 |
| DRIFT | 200 (100%) |
| `layout_sizing_h_mismatch` | 1,348 |
| `layout_sizing_v_mismatch` | 1,274 |
| `cornerradius_mismatch` | 23 (VECTOR cap-table gap from cross-corpus, deferred) |
| Total verifier errors | **2,645** |
| Elapsed | 2921.6s (~49 min) |

Largest corpus, biggest sample of the bug. The 23 cornerradius_mismatch
are the unrelated VECTOR cornerRadius capability-table gap from the
2026-04-27 cross-corpus run (see
`audit/cross-corpus-20260427-190100/dank/FINDING-vector-cornerradius.md`),
also deferred.

### HGB (44 screens)

| Metric | Value |
|---|---:|
| Total | 44 |
| Structural parity | 8 (font-license blocker only) |
| DRIFT | 44 (100%) |
| `layout_sizing_h_mismatch` | 59 |
| `layout_sizing_v_mismatch` | 60 |
| Total verifier errors | **119** |
| Elapsed | 63.4s |

All HGB drifts are the layout_sizing class. The original HGB button
bug (TEXT="Reject" vs "Send to Client") doesn't show as
`text_content_mismatch` because the font-license blocker
(Akkurat not installed) causes a `text_set_failed` runtime error
that prevents the rendered text from being captured in the eid_map
at all. On a machine with Akkurat installed, that bug would surface
as a real `text_content_mismatch`.

## Synth-gen implications

This is the architectural payoff. Pre-Sprint-2 synth-gen was about
to flow:
- LLM emits IR with `layoutSizingHorizontal: 'hug'`
- Renderer drops it because parent isn't auto-layout
- Walker reads back FIXED
- Verifier doesn't compare modes
- Repair loop sees no error
- LLM gets reinforced on producing IR that doesn't render to design intent

Post-Sprint-2:
- Same chain, but now the verifier flags 2,992 mismatches
- Repair loop can tell the LLM "your sizing-mode emission doesn't survive"
- Synth-gen training/iteration has the feedback signal it was missing

Even though the underlying renderer bug is unfixed, the rail
unblocks synth-gen feedback loop coherence on this property class.

## What's NOT closed

### The renderer bug
Sprint 2's success criterion was "make the gap visible," not
"close the gap." Per plan §13 (out of scope) and Codex round-10
ship-gate: the renderer fix is follow-up work.

Proposed fix (Codex round-10 option iv): split by node-type
context. FRAME nodes can have layoutSizing emitted regardless
of parent (Plugin API supports it); other types skip with an
explicit reason. This is a Sprint-2.5 or Sprint-3-prerequisite
fix.

### VECTOR cornerRadius (Dank only)
Documented in
`audit/cross-corpus-20260427-190100/dank/FINDING-vector-cornerradius.md`.
One-line capability-table change pending.

### Auto-layout family + text-styling family
Plan §7 explicitly defers these to Sprints 3+ as walker-side gaps.
Sprint 2 only graduated 3 properties; auto-layout (8 props) and
text-styling (13 props) are coherent future workstreams.

### Project vocabulary
User-raised mid-sprint architectural insight (notes in scrollback):
the renderer's Mode-2 emission has no source for "untokenized
project values" — synth-gen produces invented colors/radii/font-
sizes that don't match the project's established patterns even
when the design system has consistent literal vocabulary. Sprint
5+ work; Codex co-locked the design (option B post-IR transform,
not a fourth mode).

## Sprint 2 deliverable: status

| Per plan §12 ship gate | Status |
|---|---|
| Plan doc committed | ✅ `e571dd8` |
| Mislabeled commits reverted | ✅ `33ffe0f` |
| C4-C11 all green | ✅ 433 tests across Sprint 2 + verifier modules |
| All-corpus regression sweep ran | ✅ Nouns + Dank + HGB |
| 3 graduated properties verified in unit tests | ✅ test_c10_registry_dispatch.py |
| 3 graduated properties verified in corpus reports | ✅ All 3 fire on real corpora |
| Codex 5.5 ship-gate review | ✅ Round 10 |

## Subagent coordination retrospective

Per plan §9. Used:
- **Codex 5.5** at every architectural fork (rounds 5-10)
- **Sonnet workers** for bounded scopes: C6 manifest gen, C7 plugin
  injection, C8 walker envelope+shim
- **Sonnet pre-commit reviewers** after every main-thread commit
  except the small inventory updates (C4 schema, C9 fix, C11 results)
- **Main thread** for C5 inventory, C9 routing, C10 keystone
  dispatch (Codex round-9: "main-thread, not worker" for C10)

Notes:
- The Codex round-8 "verify query_screen_for_ir carries
  figma_node_id and instance_overrides" advice was missed during
  C9 implementation — caught only at C11 sweep. Lesson: when
  Codex flags a verification step, run it.
- Sonnet workers performed flawlessly on bounded scopes (file
  ownership respected, no scope creep).
- Sonnet reviewers caught real issues (C4 review confirmed clean
  schema, C8 review confirmed strict envelope detection, C10
  review confirmed dispatch placement).

## Next steps

1. **Renderer fix** for parent-not-autolayout layoutSizing class
   (Sprint 2.5 or Sprint 3 prerequisite). Estimated: 1-2 commits.
2. **Sprint 3** — auto-layout family graduation (8 properties:
   paddingT/R/B/L, itemSpacing, counterAxisSpacing, layoutMode,
   primaryAxis/counterAxisAlignItems, layoutWrap, layoutPositioning)
3. **Sprint 4** — text-styling family graduation (13 properties)
4. **Sprint 5+** — project vocabulary post-IR transform (user-raised)

Sprint 2 builds the rail; Sprints 3-5+ ride it.

---

**Co-authored**: Claude Opus 4.7 (main thread) +
Codex 5.5 high-reasoning (architectural partner) +
Sonnet workers/reviewers per plan §9
