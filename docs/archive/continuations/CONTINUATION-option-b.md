# Continuation prompt — v0.3 Option B migration

**Paste this into a new session to pick up cleanly.**

---

## What happened last session (tl;dr)

I was building Option A (markup lowers to dict IR, existing renderer consumes dict). After extensive elaboration — decompressor, `$ext.nid` side-channel, canonical-type classification, master-subtree inflation, 12 archetypes migrated — I ran a Figma sweep to validate Tier 3 pixel parity.

**Result: 0/3 on the smoke test. Baseline dict-IR sweep: 3/3. The markup-via-dict path was the regression.**

Root cause: identity drift (dict-IR counter keys don't survive the AST round-trip) + content drift (decompressor bugs). Fix required a second compile-time side-channel (`$ext.spec_key`). Pattern recognition: two side-channels is scaffolding for a system being demolished. Re-reading `docs/learnings-v0.3.md` Choice 1 confirmed: "the markup is canonical; the JSON IR is implementation detail." Option A was drifting from the stated principle.

**Decision: pivot to Option B (markup-native renderer). Full rationale: `docs/decisions/v0.3-option-b-cutover.md`.**

## First things to read (in order)

1. `docs/requirements.md` — Tier 0. Core claim, MLIR analogue, invariants, roadmap.
2. `docs/requirements-v0.3.md` — Tier 1. v0.3 scope (updated for Option B).
3. `docs/decisions/v0.3-option-b-cutover.md` — **current architectural stance**. The decision record. Supersedes `v0.3-canonical-ir.md`.
4. `docs/DEPRECATION.md` — what gets deleted at M6 cutover.
5. `docs/plan-v0.3.md` — Plan A (complete) + Plan B (M0..M6+ milestones).
6. `docs/spec-l0-l3-relationship.md` §3 — rendering via markup-native walker (rewritten for Option B).
7. `docs/spec-dd-markup-grammar.md` — grammar (unchanged by pivot; backbone of Option B).
8. `docs/learnings-v0.3.md` Part 5 "Ship-risk compromises drift architectural principles" — the Option A→B pivot entry.

Memory (auto-loaded): `memory/project_v0_3_plan.md` is the session-boot summary. `memory/feedback_option_b_pivot.md` captures the architectural lesson.

## Current git state

**Branch:** `v0.3-integration`. Stay on this branch — no new branch.

**Three rollback tags (local-only; push them if you want them on the remote):**
- `pre-markup-baseline` — `main` HEAD. Clean dict-IR 204/204 before any markup work. Safe to share with external eyes (Anthropic interview).
- `markup-compressor-mvp` — `c0102d5` on v0.3-integration. Compressor MVP green; no decompressor yet. Clean Option B starting baseline if needed.
- `option-a-complete` — v0.3-integration HEAD at the Option B pivot. Full Option A elaboration archived.

```bash
# Push tags if desired:
git push --tags
```

**Uncommitted changes (drafts written last session, NOT YET COMMITTED):**

Modified:
- `docs/decisions/v0.3-canonical-ir.md` — third supersession banner
- `docs/requirements.md` — minor (React renderer callout)
- `docs/requirements-v0.3.md` — significant rewrites (§1.2, §1.4, §2.4, §2.5, §3, §4, §5, §6)
- `docs/plan-v0.3.md` — substantial (M0..M6+ milestones, migration sequencing, kickoff rewritten to start at M1)
- `docs/spec-l0-l3-relationship.md` — §3 rewritten for Option B (expansion section, tier claims)
- `docs/spec-dd-markup-grammar.md` — minimal (dict-IR references rephrased as historical)
- `docs/learnings-v0.3.md` — new Part 5 entry

New:
- `docs/DEPRECATION.md`
- `docs/decisions/v0.3-option-b-cutover.md`

Memory (outside repo, also uncommitted as memory files):
- `memory/project_v0_3_plan.md` — near-total rewrite
- `memory/MEMORY.md` — index updated
- `memory/feedback_option_b_pivot.md` — new

**Render batch artefacts from smoke test (untracked):**
- `render_batch/scripts-markup/`, `walks-markup/`, `reports-markup/`, `summary-markup.json` — Option A sweep output. Keep as forensic evidence; will be deleted at M6.

## First task in the new session

**Commit the drafts atomically.** User approved them last session. Run:

```bash
cd /Users/mattpacione/declarative-build

# Verify state
git status --short   # expect 7 modified + 2 new docs + untracked sweep artefacts
git tag -l | grep -E "pre-markup|option-a|markup-compressor"   # expect 3 tags

# Stage the doc updates (NOT the sweep artefacts — those are forensic only)
git add docs/requirements.md docs/requirements-v0.3.md docs/plan-v0.3.md \
        docs/spec-dd-markup-grammar.md docs/spec-l0-l3-relationship.md \
        docs/learnings-v0.3.md docs/DEPRECATION.md \
        docs/decisions/v0.3-canonical-ir.md docs/decisions/v0.3-option-b-cutover.md

# One atomic commit
git commit -m "docs: v0.3 architecture pivot to Option B (markup-native renderer)"
```

Then push tags if desired: `git push --tags`.

Memory files don't need git-committing (they're outside the repo).

## Second task — start M1 (markup-native Figma renderer MVP)

Per `docs/plan-v0.3.md` "Kickoff — M1" section:

1. **Create `dd/render_figma_ast.py`** (working filename) as the scaffolding for the markup-native renderer. Module exports `render_figma(doc: L3Document, conn: sqlite3.Connection) → (script: str, token_refs: list)`. Starts as a stub that walks `doc.top_level`, dispatches per `Node.head.type_or_path`, emits the minimum viable Figma JS for a single screen.

2. **Target: byte-parity on screen 181 first.** End-to-end:

   ```python
   # Option A baseline (reference)
   ir = generate_ir(conn, 181)
   script_a, refs_a = generate_figma_script(ir["spec"], ...)
   # Option B path (under test)
   doc = derive_markup(conn, 181)  # currently compress_to_l3; rename at M0
   script_b, refs_b = render_figma(doc, conn)
   assert script_a == script_b  # MUST be byte-identical
   ```

3. **A/B harness at `tests/test_option_b_parity.py`.** Per-feature parity tests. Each feature (fills, strokes, text, createInstance, vectorPaths, effects, constraints) gets its own byte-parity gate on at least one screen that exercises it.

4. **Feature coverage order** (render-critical priority):
   - Node creation dispatch (createFrame / createRectangle / createText / createInstance / createVector)
   - Sizing + position (Phase 1 resize, Phase 3 x/y)
   - Fills + strokes
   - Text properties (font, size, weight, content)
   - Component instances via `createInstance` (Mode 1 path)
   - Vector paths (DB lookup by node_id)
   - Effects (shadow, blur)
   - Constraints
   - Variant / swap handling

5. **Don't modify the Option A path.** Pre-markup `generate_figma_script` IS the reference. Any modification invalidates the A/B comparison.

## Milestones (M0..M6+)

| # | Milestone | Status |
|---|---|---|
| M0 | Markup compressor (DB → L3 AST) green at 204/204 Tier 1 | ✅ done (existing `dd/compress_l3.py::compress_to_l3`) |
| M1 | Markup-native Figma renderer MVP — walks AST + emits JS | 🔲 **next up** |
| M2 | Script byte-parity with Option A renderer on 3 reference fixtures (181/222/237) | 🔲 |
| M3 | Script byte-parity on full 204 corpus | 🔲 |
| M4 | Pixel-parity via Figma sweep on full 204 corpus | 🔲 |
| M5 | Upstream consumer migration (`dd/compose.py`, providers, verifier) | 🔲 |
| M6 | Atomic cutover PR — delete Option A code per `DEPRECATION.md` | 🔲 |
| M7+ | Stage 2 continuation (pattern expansion, `use`/import), Stage 3 (synthetic tokens), Stages 4-5 (synthesis) | 🔲 gated on M6 |

Commit prefix: `feat(option-b): Mk — <scope>` (e.g. `feat(option-b): M1 — render_figma frame walker MVP`).

## Non-negotiable invariants (still in force)

1. **204/204 pixel parity preserved** — during M1–M5, enforced on the Option A path (which stays in CI as the reference). Option B path must byte-match Option A before M6 cutover.
2. **Lossless extraction; no auto-deduplication.**
3. **No raw values in the IR** — Option B strengthens this: reference resolution happens at one place (the renderer), per-backend.
4. **No silent drift** — every failure is a named `KIND_*`.
5. **All ADR-001 through ADR-008 in force.**

Do NOT modify `dd/ir.py`, `dd/renderers/figma.py::generate_figma_script`, or `tests/test_script_parity.py` during M1–M5. They're the Option A reference.

## What transfers from Option A to Option B

**Reusable unchanged:**
- `dd/markup_l3.py` — grammar parser + emitter + AST + semantic passes. Backbone.
- `dd/compress_l3.py` — per-axis derivation logic. Becomes `derive_markup` core (rename at M0).
- `dd/archetype_library/*.dd` — 12 migrated archetypes.
- Grammar spec, L0↔L3 spec (with §3 rewritten).
- Fixture files + golden snapshots.

**Deleted at M6:**
- `dd/decompress_l3.py`
- `dd/ir.py::generate_ir()` / `build_composition_spec()` / `query_screen_visuals()`
- `dd/renderers/figma.py::generate_figma_script()` / `generate_screen()`
- `tests/test_decompress_l3.py`, `tests/test_markup_render_pipeline.py`, `tests/test_script_parity.py`
- `$ext.nid` compile-time emission
- `--via-markup` CLI flag + segregated sweep artefacts

Full list: `docs/DEPRECATION.md`.

## Tool reminder — code-graph MCP

**This project is indexed for code-graph MCP.** Use it instead of multi-step Grep/Read for code understanding:

```bash
# Start with: project architecture overview
mcp__code-graph-mcp__project_map(compact=True)

# "how is dd/renderers/figma.py structured?" → module overview
mcp__code-graph-mcp__module_overview(path="dd/renderers/")

# "who calls generate_figma_script? what will break if I delete it?"
mcp__code-graph-mcp__impact_analysis(symbol="generate_figma_script")

# "find code that does node creation dispatch"
mcp__code-graph-mcp__semantic_code_search(query="figma create node dispatch", compact=True)

# "where does the renderer emit Phase 1 resize calls?"
mcp__code-graph-mcp__ast_search(query="resize phase 1", type="fn")

# Still use Grep/Read for exact strings and specific files you'll edit.
```

Specifically for M1 work, run `impact_analysis` on `generate_figma_script` FIRST — it'll tell you every caller and every property access, which is the spec for what `render_figma` must cover.

## Verification commands

```bash
# State checks
git status --short                                 # clean after doc commit
git branch --show-current                          # v0.3-integration
git tag -l | grep -E "pre-markup|option-a|markup"  # 3 tags present

# Green test suite (markup-relevant surface)
python3 -m pytest tests/test_compress_l3.py tests/test_markup_l3.py \
                  tests/test_archetype_skeletons.py -q          # expect ~160 green

# Option A smoke test (reference baseline, still green)
python3 -m pytest tests/test_script_parity.py -q                 # expect 204/204 Tier 2

# NOTE: decompressor tests exist but will be deleted at M6.
# They're the Option A machinery; leave them green through the migration.
python3 -m pytest tests/test_decompress_l3.py tests/test_markup_render_pipeline.py -q
```

## Key files (absolute paths)

- Repo root: `/Users/mattpacione/declarative-build`
- DB: `/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db` (86,766 nodes, 204 app_screens)
- Memory: `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/`
- Figma bridge ports: 9226/9227/9228 (default 9228 for sweep)

## If something feels off

1. **Re-read the canonical doc stack top-down.** The ordering matters.
2. **Tier 0 § invariants override everything.** Any decision that breaks one is wrong.
3. **Grep the archive before building.** `docs/archive/` + `docs/learnings-v0.3.md`. Lots of relevant history there.
4. **Check `memory/feedback_*.md` files** — architectural principles from past sessions (progressive fallback, capability table, verification channel, etc.).
5. **If a second side-channel is about to accrete, stop and re-read principles.** See `memory/feedback_option_b_pivot.md`.

## TL;DR for the first reply in the new session

> "I've read the continuation prompt and the doc stack. I see the Option A → B pivot is approved but the docs aren't committed yet. First step: commit the drafts atomically. Then start M1 by running `impact_analysis` on `generate_figma_script` to scope the renderer rewrite, scaffold `dd/render_figma_ast.py`, and target byte-parity on screen 181. I'll use code-graph MCP for code exploration."
