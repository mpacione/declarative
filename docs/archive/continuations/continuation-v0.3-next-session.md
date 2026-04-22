# v0.3 — Next Session Continuation

> ### ⚠ SUPERSEDED 2026-04-18 (late session)
>
> The investigation priorities listed below were **all resolved** (then partially reframed after premature CRAG work was reverted). The current canonical plan is **`docs/plan-v0.3.md`**, which supersedes this doc for "what to do next."
>
> **What's still useful:** §1 (where we were at session start) and §2 (what happened in the mid-session) remain accurate historical record.
>
> **What's changed:** Priorities 0/1A/1B/1C/2/3/4 are closed (some reframed). The new top-of-stack docs are:
>   1. `docs/requirements.md` (Tier 0 — overall requirements)
>   2. `docs/requirements-v0.3.md` (Tier 1 — v0.3 phase)
>   3. `docs/plan-v0.3.md` (the current plan)
>
> Non-destructive banner; original content preserved below for historical context.

---

Comprehensive historical context for whoever picks this up next. Written at the close of the 2026-04-17 / 2026-04-18 session that produced the v0.3 architecture. Read this first.

---

## 1. Where we were at session start

### Last shipped: v0.2 corpus retrieval (6 commits, `705c074` through `698f164`)

**State:**
- 1,950 unit tests green
- 204/204 round-trip parity on Dank Experimental
- 42,938 nodes classified (via `dd classify`, Phase-1 `classify_formal` + `classify_heuristics` + `link_parent_instances` + `extract_skeleton` — 338 skeletons generated)
- 00g canonical: mean render-fid 0.728
- 00i breadth: mean 0.722, 17/20 identical to baseline
- 01-login VLM retrieval=10 vs baseline=9 (retrieval actually better on visual quality)
- `CorpusRetrievalProvider` behind `DD_ENABLE_CORPUS_RETRIEVAL=1` (default OFF)
- Component-level retrieval with structural match ranking (Jaccard on child-type bag)
- Mobile-size filter (300-500 px) + descendant-count caps per catalog type
- Text substitution fixes: no DB-text leak; image-type fallback to universal catalog when retrieved root has no visible paint

**The binding spec at that point:** `docs/continuation-v0.2-corpus-retrieval.md`.

### Four defect classes still open at session start

From `memory/project_corpus_retrieval_v0_2.md`:
1. Baked-× icon inheritance (Dank's `button/large/translucent` with inherited `×` child)
2. Image placeholder polish (`_imagePlaceholder` helper)
3. Horizontal layout collapse (pricing-compare, carousels)
4. Meme-feed Phase-2 `layoutMode` perf (Figma reflow cascade)

---

## 2. What happened in this session

### The "stepping back" moment

User asked: *"we HAVE A WORKING RENDERER. is it that for some reason, synthetic generation fundamentally does not work the same way?"*

Pattern recognition across all v0.1.5 / v0.2 patches: the round-trip path works because the renderer receives IR created by real designers. Mode 3 fails because it synthesizes IR atom-by-atom and defaults to vertical stacking. The reframe: **the renderer is fine. The issue is the quality of IR being handed to it.**

### Research fan-out (18 threads total)

**First 10 (architecture):**
Retrieval + cascade; edit grammars; multi-target catalog; verify+refine loops; intent parsing; multi-donor composition; evaluation methodology; pattern mining; constraints; verifier-as-agent + provenance-markup.

**Then 4 markup-design tradeoffs:**
Scoping + imports + cycles (Elm/KDL/Sass precedents, hard-error on cycles via three-color DFS); hierarchical IDs (MLIR symbol tables + CSS Shadow Parts + React keys composite); parametrization (three primitives — scalar args + slots + path overrides — never unify); extract-vs-author distinction (dual-sigil `->` vs `&`, Rule of Three for pattern detection).

**Then 5 competitive landscape threads:**
Initial 10-property × 14-system coverage scan; patent + stealth; enterprise internal tools (Lona failed 2019, Relay sunset April 2025); academic research frontier (Apple Athena + Zhejiang SpecifyUI as closest); design tool roadmaps (Figma explicitly chose NOT to build a typed IR).

**Conclusion:** the specific combination (bidirectional + multi-target + typed IR + round-trip + token-bound + retrieval-augmented) is unoccupied at shipping scale. The pre-LLM attempts at formal IRs (Lona, Relay) failed because they had no LLM fallback. Post-LLM, scaffolded IRs are the accepted 2025 architectural frame (Apple, Zhejiang).

User's response to "is anyone else doing this": *"this is not relevant right now. i was only asking to learn about how novel our thing is, not to turn into a business right now."*

### Archive archaeology found the markup language

`docs/archive/t5-pattern-language.md` (2026-03-31) specified the Pattern Language as 5-level compositional descent. `docs/archive/t5-four-layer-architecture.md` specified IR as token-refs-only, raw values in DB, synthetic tokens for untokenized visuals. `docs/research/format-comparison-examples.md` evaluated 8 markup formats (custom DSL vs YAML vs JSON, etc.). **All specified; the implementation had drifted.**

This is the second time this session-shape recurred: T5 had designed something, it was forgotten, we rediscovered it. First instance: `dd classify` pipeline existed but had never been run on current DB. Second instance: markup language.

### The v0.3 architecture crystallized

Key decisions across conversation:
- Axis-polymorphic markup (5 axes: Structure/Content/Spatial/Visual/System)
- Density-per-node, not pipeline levels (levels are a pipeline optimization for cheap exploration)
- Named definitions with three parametrization primitives
- Seven-verb edit grammar in the same markup
- CRAG three-mode cascade (SCREEN_EDIT / COMPOSITION / SYNTHESIS)
- Verifier-as-agent emitting edit grammar
- Synthetic tokens for cold start (clustering at extract time + universal defaults for zero-corpus)
- Multi-target catalog schema extension (per-target JSON sub-objects, Code Connect pattern)
- KDL v2 as the syntactic substrate for dd markup (file extension `.dd`; LLM-friendly + technical-reader human-readable). Name decided 2026-04-18: call our dialect **dd markup**, not a rebranded acronym — avoids SQL-DDL / UIML / XAML / DML collisions and doesn't pretend to be vanilla KDL.

### 5-reviewer audit

Five sonnet reviewers dispatched in parallel (2026-04-18) with distinct angles:

1. **Architectural consistency** — found 3 real inconsistencies: axis/density conflation, "one grammar" falseness, Pattern Language reframe as straw man.
2. **MVP + implementation risk** — Day 6 IR bridge is 5-8 days not 1; MVP 20-35% probability as scoped.
3. **Existing-codebase alignment** — 5 underscore fields break "IR unchanged" claim; ADR-001 sync broken; RenderReport schema extension is breaking not additive.
4. **Red-team (out of scope per user)** — designer-usability concern, `$extensions` escape hatch predicted to compromise "single grammar" Day 7.
5. **Strategic (out of scope per user)** — no buyer/distribution/pricing; plugin pivot proposal.

**User scope decisions:**
- v0.3 is **internal infrastructure**, not productized. Reviewers 4+5 out of scope.
- Grammar audience: **LLM-friendly + technical-reader human-readable** (engineer, not designer). Reviewer 4 designer-usability concern dismissed.
- MVP goal: **both** (grammar completeness AND Figma round-trip). Reviewer 2's smaller-MVP rejected.
- Competitive landscape: **context only**, not driver. Reviewer 5's plugin pivot rejected.
- Reviewers 1–3 architectural critiques: **investigate, don't accept as truth, in next session.**

---

## 3. Current state

### Artifacts produced this session

| File | Status | Purpose |
|---|---|---|
| `docs/architecture-v0.3.md` | Committed-pending | Canonical architecture. 10 sections. Internal-tool scoped. |
| `docs/continuation-v0.3-mvp.md` | Committed-pending | MVP plan — blocked on investigation. |
| `docs/research/v0.3-architecture-research.md` | Committed-pending | 18-thread research record. Source provenance. |
| `docs/learnings-v0.3.md` | Committed-pending | Philosophical choices + architecture spec + debates + trade-offs. |
| `docs/reviews/v0.3-reviews-full.md` | Committed-pending | 5 reviewer reports in full. |
| `docs/reviews/v0.3-review-synthesis.md` | Committed-pending | Synthesis + post-decision framing. |
| `docs/continuation-v0.3-next-session.md` | Committed-pending | **This doc.** |
| `memory/project_v0_3_architecture.md` | Committed-pending | Cross-session v0.3 snapshot. |

### Code state

- No code written for v0.3 yet. Purely documents.
- v0.2 code (`dd/composition/providers/corpus_retrieval.py`, `dd/compose.py` splice logic, `dd/composition/protocol.py::PresentationTemplate.corpus_subtree`) still in place.
- `dd classify` has been run. `screen_component_instances` table populated with 42,938 rows. `screen_skeletons` with 338.
- 204/204 round-trip parity intact (last verified 2026-04-17).

### Invariants at session close

- 204/204 parity ✓
- 1,950+ unit tests green ✓
- All ADRs (001–008) in force ✓
- No flag-gated changes broke defaults ✓

---

## 4. Next-session priorities

### Priority 0 — The dual-representation question (architectural foundation)

**The finding (raised 2026-04-18 by user, after reviewer audit):** we currently have TWO representations of the same ground truth:

- **Round-trip path:** DB → dict IR (registry-driven, Python dict with conventions) → render walk → Figma
- **v0.3 proposal:** **dd markup** (file extension `.dd`; KDL v2 as lexical substrate; our dialect per `architecture-v0.3.md` §2) for LLM-facing generation/editing, bridged to the dict IR

This is the M×N problem (from `project_ir_purpose.md`) re-emerging at a higher layer. Every capability added has to land in both places — grammar schema AND dict IR schema — or the bridge leaks. Two validators, two emission gates, two places to add a new property. Architecturally ugly and guarantees drift.

**The honest question:** is dd markup the canonical IR going forward, or is it a projection of the dict IR with a bidirectional bridge?

**Two positions:**

1. **Aggressive (unify):** dd markup becomes the canonical in-memory and on-wire IR. Extract emits parsed-dd AST. Renderers walk parsed-dd AST. Composition providers emit dd fragments. The registry/capabilities table constrains the dd schema — no second schema. One source of truth. The 7-verb edit grammar, density-per-node, named definitions, synthetic tokens are ALL first-class IR features, not LLM conveniences.

2. **Conservative (bridge):** dd markup is a serialization/edit format layered over the existing dict IR. Bridge round-trippably between them. Faster to ship; preserves existing 204/204 investment. Bakes in dual-representation debt that will erode as features split-brain.

**The proof gate (applies either way):** before any MVP feature code or synthetic generation, we must demonstrate dd-markup round-trip parity on the existing 204 corpus. Serialize each screen's current IR as `.dd`, re-parse, render through the existing pipeline, verify `is_parity=True` per ADR-007. If we can't clear that bar on known-good screens, the grammar is incomplete — and we'd rather discover that now than when it blurs with generation-quality failures on synthetic screens.

**The investigation task:**

1. Design a minimal dd-markup serde for the current dict IR: walk each IR field and decide (a) first-class dd node / attribute, (b) dd-addressable via underscore-field (see 1A), or (c) structural artifact that doesn't need to round-trip through the markup at all.
2. Implement as a throwaway-quality prototype in a branch: `dd/markup.py::serialize_ir`, `parse_dd`. Target: make it work on ONE screen end-to-end.
3. Run against all 204. Count parity wins/losses. Categorize losses by cause.
4. Write a decision record: which position (aggressive / conservative) does the data support? What's the cost of aggressive's refactor? What drift-pressure does conservative accept?
5. Update `docs/architecture-v0.3.md` with the answer — and with a fundamental invariant: dd-markup completeness is measured against the 204 corpus, not against synthetic distributions.

**Relationship to Priorities 1A/1B:** Priority 0 reframes both. If dd markup IS the IR (position 1), then underscore fields get first-class grammar representation (1A becomes "add these to the grammar"), and grammar modes collapse to a single schema with a separate clustering-validity validator (1B becomes "one schema, clustering as a separate check"). If dd markup is a bridge (position 2), 1A and 1B stand as originally framed.

**Output:** `docs/architecture-v0.3.md` §1.5 (new) — "The canonical IR question" with position taken, supporting evidence, and the 204-corpus parity number. Plus a decision record at `docs/decisions/v0.3-canonical-ir.md`.

**Timing:** this investigation MUST run before 1A/1B/1C because it determines how those questions are framed.

---

### Priority 1 — Resolve the three architectural critiques (Reviewers 1–3)

**Not accept as truth. Investigate. Decide.** Each critique has a concrete investigation task below. **Read in light of Priority 0's answer.**

#### 1A. Underscore field representation

**The finding** (Reviewer 3): 5 IR fields carry load-bearing state that has no representation in the markup grammar:

| Field | Where | What it does |
|---|---|---|
| `_node_id_map` | `spec["_node_id_map"]` | eid → node_id (real DB positive IDs on round-trip; synthetic negatives on compose) |
| `_mode1_eligible` | per-element bool | Mode 1 viability hint for verifier |
| `_corpus_source_node_id` | per-element int | v0.2 retrieval provenance → donor DB node |
| `_original_name` | per-element string | Source Figma name, for placeholder labels |
| `_composition` | per-element list | build_template_visuals children_composition extract |

**The investigation task:**
1. For each field, read the code at the sites consuming it (Reviewer 3 cites specific line numbers in their report). Understand the contract.
2. Decide per-field: grammar-first-class (add dd-markup syntax) / bridge-time reconstructed (document logic) / opaque pass-through (document contract).
3. Specifically for `_corpus_source_node_id`: does invariant 7 ("IR never holds raw values") need an exception, or does provenance need a different representation (e.g., as a token path like `{provenance.corpus.node-440}`)?
4. Document the decision per-field in architecture-v0.3.md §2 (markup grammar) with explicit grammar rules or explicit bridge logic.

**Output:** a one-page decision record for the 5 fields + updated architecture doc section.

#### 1B. Grammar mode question (raw vs token-only)

**The finding** (Reviewers 1+3): extract path emits raw values pre-clustering; synthesis path is grammar-constrained to token refs only. Architecture claims "one grammar" but these are different validation modes.

**The investigation task:**
1. Look at extraction code: `dd/ir.py::generate_ir` and `dd/compose.py::build_template_visuals`. Where do raw hex values enter the IR? At what stage does clustering occur (or not)?
2. Decide the honest framing: "one grammar with two validation modes" or "two grammars sharing syntax"?
3. Decide: does clustering happen AT extraction time (no raw values ever in IR) or as a separate later stage (raw values tolerated temporarily)?
4. Update invariant 7 to reflect the decision precisely.

**Output:** grammar modes declared explicitly in architecture-v0.3.md §2; invariant 7 reworded if needed.

#### 1C. RenderReport schema extension

**The finding** (Reviewer 3): the verifier-as-agent proposal adds a `proposed_edits` field to `RenderReport`, which is a frozen dataclass. This is a breaking change, not additive.

**The investigation task:**
1. Read `dd/boundary.py::RenderReport`. Enumerate consumers (grep for usage).
2. Decide: add `proposed_edits: list[MarkupEdit] = field(default_factory=list)` as a backward-compatible field (with default), OR wrap with a new class `VerifierOutput(report: RenderReport, proposed_edits: ...)`.
3. Migration plan: update consumers one-by-one OR provide compatibility shim.
4. Promote this to an explicit Stage 5 task; remove the "additive" framing.

**Output:** updated continuation-v0.3-mvp.md §Stage 5 with explicit migration steps.

### Priority 2 — Minor cleanup

- Fix `_UNIVERSAL_MODE3_TOKENS` duplicate keys (`dd/compose.py` lines 444+446 and 445+447). Trivial fix; do during investigation.

### Priority 3 — Provider obsolescence audit (what v0.3 unwires)

**The finding (raised 2026-04-18 by user):** `dd/composition/providers/*` contains code built for v0.2 Mode 3 composition (universal, ingested, project_ckr, corpus_retrieval) plus cascade/protocol/registry. Some of this is load-bearing for v0.3's CRAG 3-mode cascade; some is obsoleted by the new design; some needs rewriting. Building v0.3 on top of v0.2 scaffolding without an audit guarantees that we'll be discovering obsolescence mid-MVP — exactly the context-switching that makes refactors fail.

**Code-graph baseline:** 4 files in `dd/composition/providers/` (32 functions), 10 files in `dd/composition/` (29 functions). `resolve()` is a hot symbol — it's the protocol method each provider implements.

**The investigation task:**

1. For each file in `dd/composition/` and `dd/composition/providers/`, tag with one of:
   - **SURVIVES** — load-bearing for v0.3 as-is (probably `cascade.py`, `protocol.py`, `registry.py`, `universal.py`)
   - **REWRITES** — conceptually right, implementation needs update for new grammar (likely `ingested.py`, `project_ckr.py`)
   - **OBSOLETED** — v0.3 design absorbs or eliminates (likely `corpus_retrieval.py` — subsumed by the CRAG COMPOSITION mode? — needs investigation)
   - **UNCLEAR** — can't tell without Priority 0 resolved
2. Extend the audit to `dd/compose.py` itself — `_UNIVERSAL_MODE3_TOKENS`, `build_template_visuals`, splice logic — what survives, what moves, what dies?
3. Check `dd/ir.py::generate_ir` — this is the extract-side IR constructor. Does v0.3 keep it, replace it with a dd-markup parser, or make it emit dd markup directly?
4. Check `dd/renderers/figma.py` — 1,800 lines, NOT to be refactored per §6. Which of the renderer's IR consumption sites need to change for Priority 0 position 1 (dd-markup AST instead of dict)? Enumerate the access patterns without editing.

**Output:** `docs/decisions/v0.3-provider-audit.md` with a table: file / role / status / notes / risk-if-wrong. Feeds directly into MVP day-by-day sequencing.

**Depends on:** Priority 0 resolved. "Obsoleted" vs "rewrites" depends on whether dd markup is the IR or bridges to it.

### Priority 4 — Parity-gated branching strategy

**The finding (raised 2026-04-18 by user):** the 204/204 round-trip parity is our foundational invariant (ADR-007). Any v0.3 work that silently breaks parity is worse than v0.3 work that doesn't ship. We need an explicit branching + CI strategy that makes parity loss impossible to merge, not a "we'll check at the end" approach.

**The investigation task:**

1. Decide the branch topology for v0.3:
   - Single long-lived `v0.3` branch from `main`? (rebase nightmare vs `main` changes)
   - Series of short-lived feature branches each green against `main`? (harder to integrate later)
   - A `v0.3-kdl-ir` branch with mandatory 204/204 green before any squash-merge? (probably the right answer)
2. Decide the CI gate:
   - Does `render_batch/sweep.py --port 9231` become a blocking pre-commit check? (slow; infeasible)
   - Does it become a pre-push / pre-PR hook? (more feasible, adds Figma-side dependency)
   - Does it become a nightly cron with hard-fail and rollback? (catches regressions, but lets them land)
   - Combination: a sampled 10-screen fast path on every PR + full 204 nightly?
3. Decide the rollback protocol: if a v0.3 commit silently drops parity to 203/204, what's the revert trigger? How do we avoid a week's work compounding on top of one broken screen?
4. Document in `docs/continuation-v0.3-mvp.md` §Pre-requisites (new) before any Day 1 work.

**Output:** a short branching + CI strategy doc as a §Pre-requisites addition to the MVP plan.

**Cost:** ~1 day to set up; pays back every commit afterwards.

### Priority 5 — Only after Priorities 0–4 resolved — MVP Stage 1

After Priorities 0–4 resolve, proceed with MVP per `docs/continuation-v0.3-mvp.md`, Day 1 (potentially rewritten by Priority 0's answer).

**Do NOT start MVP Stage 1 before Priorities 0–1 are resolved on paper.** Running MVP against unresolved architectural questions is the failure mode Reviewer 2's analysis is predicting. Priorities 3–4 can land in parallel once Priority 0 is settled.

---

## 5. How to pick up the thread

### First hour of next session

1. Read this doc.
2. Read `docs/learnings-v0.3.md` Part 7 (open architectural questions).
3. Read `docs/reviews/v0.3-review-synthesis.md` — post-decision framing.
4. Verify state: `python3 -m pytest tests/ -q [excludes]` — expect 1,950+ passing.
5. Verify parity: `python3 render_batch/sweep.py --port 9231` — expect 204/204.

### Then: start Priority 0 (canonical-IR question)

**This is the reframing question and comes before 1A/1B/1C.**

- Read `memory/project_ir_purpose.md` — original M×N problem statement.
- Read `docs/architecture-v0.3.md` §2 — current grammar spec.
- Use `code-graph-mcp overview dd/` to map current IR consumption sites.
- Pick ONE screen (suggest a mid-complexity one, not the simplest) as the dd-markup serde prototype target.
- Draft `dd/markup.py` throwaway prototype — serialize + parse. Measure round-trip parity for that one screen.
- If the one-screen test passes, scale to all 204. Deliver parity count + loss taxonomy.
- Output `docs/decisions/v0.3-canonical-ir.md` with position + evidence.

### Then: Priority 1A (underscore fields) — framed by Priority 0's answer

- `code-graph-mcp grep "_node_id_map" dd/` — find all sites with AST context
- Repeat for `_mode1_eligible`, `_corpus_source_node_id`, `_original_name`, `_composition`
- For each field, write a short "contract" doc: what sets it, what reads it, what's the semantics.
- The representation decision is informed by Priority 0: grammar-first is easy if dd markup IS the IR; bridge logic is needed if it's a bridge.

### Success criterion for all investigation priorities

All these artifacts exist before any MVP Stage 1 code lands:

1. `docs/decisions/v0.3-canonical-ir.md` — Priority 0 position + 204-corpus parity number
2. `docs/architecture-v0.3.md` §1.5 — canonical-IR invariant stated
3. `docs/architecture-v0.3.md` §2.X — underscore-field contracts (representation choices)
4. `docs/architecture-v0.3.md` §2 invariant 7 — grammar-mode decision reworded
5. `docs/continuation-v0.3-mvp.md` §Stage 5 — RenderReport migration plan
6. `docs/decisions/v0.3-provider-audit.md` — file-by-file fate of `dd/composition/*`
7. `docs/continuation-v0.3-mvp.md` §Pre-requisites — branching + CI strategy
8. `dd/compose.py` — `_UNIVERSAL_MODE3_TOKENS` duplicate keys fixed
9. 204/204 parity green at the start AND end of each investigation (every artifact lands without parity loss — even throwaway prototypes get reverted, not merged)

**Once these documents exist and have been reviewed, MVP Stage 1 can begin.**

---

## 6. Don't forget

### Key load-bearing files to not touch casually

- `dd/renderers/figma.py` — 1,800+ lines. Do not refactor. Read-only unless fixing a verified bug.
- `render_batch/sweep.py` — the parity oracle. Changes here affect every commit.
- `dd/boundary.py` — ADR-006 structured error channel. KIND_* constants load-bearing.
- `dd/ir.py::generate_ir` — round-trip IR generation. The foundation.

### Memory records worth re-reading

Before diving into Priority 1, skim:
- `memory/feedback_capability_gated_emission.md` — ADR-001 philosophy, relevant to grammar-vs-capability-table sync question
- `memory/feedback_unified_verification_channel.md` — ADR-007, relevant to RenderReport schema question
- `memory/feedback_classify_chain_was_dormant.md` — the "archive had the answer" pattern, relevant to remembering the markup language came from archive
- `memory/project_v0_3_architecture.md` — cross-session v0.3 snapshot
- `memory/project_corpus_retrieval_v0_2.md` — v0.2 state, still relevant

### Commits to preserve

Latest commit at session close: depends on cleanup commit. Expected graph:
```
<latest> chore: archive experiments + old continuations + DB backups
<prev>   docs(v0.3): architecture + MVP + research record + learnings + reviews
98f637a  fix(vlm): switch to gemini-2.5-pro
7c8d3f8  fix(v0.2): no DB-text leak + image-fallback + breadth validation
...
```

### When in doubt

The architecture doc is canonical. The research record is source provenance. The reviews are historical critique (with some actionable investigation targets). The learnings doc is WHY. This doc is WHAT NEXT.

If a conflict arises between docs, the user's stated decisions take precedence (internal infrastructure; LLM + technical-reader; both MVP goals; reviewers 1-3 to investigate, 4-5 noise).

---

*Session closed 2026-04-18 with architecture defined, reviews captured, open questions enumerated, investigation priorities clear. Next session inherits all artifacts + investigation list.*
