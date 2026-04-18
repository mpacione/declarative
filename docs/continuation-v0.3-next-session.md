# v0.3 — Next Session Continuation

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
- KDL as the syntactic substrate (LLM-friendly + technical-reader human-readable)

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

### Priority 1 — Resolve the three architectural critiques (Reviewers 1–3)

**Not accept as truth. Investigate. Decide.** Each critique has a concrete investigation task below.

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
2. Decide per-field: grammar-first-class (add KDL syntax) / bridge-time reconstructed (document logic) / opaque pass-through (document contract).
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

### Priority 3 — Only after Priority 1 + 2 — MVP Stage 1

After Priority 1 + 2 resolve, proceed with MVP per `docs/continuation-v0.3-mvp.md`, Day 1.

**Do NOT start MVP Stage 1 before Priority 1 is resolved on paper.** Running MVP against unresolved architectural questions is the failure mode Reviewer 2's analysis is predicting.

---

## 5. How to pick up the thread

### First hour of next session

1. Read this doc.
2. Read `docs/learnings-v0.3.md` Part 7 (open architectural questions).
3. Read `docs/reviews/v0.3-review-synthesis.md` — post-decision framing.
4. Verify state: `python3 -m pytest tests/ -q [excludes]` — expect 1,950+ passing.
5. Verify parity: `python3 render_batch/sweep.py --port 9231` — expect 204/204.

### Then: start Priority 1A (underscore fields)

- `grep -n "_node_id_map" dd/` — find all sites
- `grep -n "_mode1_eligible" dd/` — find all sites
- For each field, write a short "contract" doc: what sets it, what reads it, what's the semantics. These become the basis for the representation decision.

### Success criterion for Priority 1 resolution

A single document updated at `docs/architecture-v0.3.md` §2 (or a new `§2.X — Underscore-field contracts`) that:
- Declares, per field, the representation choice (grammar / bridge / opaque)
- Shows the grammar syntax if grammar-first
- Shows the bridge reconstruction logic if bridge-time
- Shows the contract if opaque

Plus invariant 7 updated to reflect the grammar-mode decision precisely.

Plus continuation-v0.3-mvp.md §Stage 5 with explicit RenderReport migration plan.

**Once this document exists and has been reviewed, MVP Stage 1 can begin.**

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
