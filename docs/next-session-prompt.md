# Continuation prompt — next session

Copy the section below into a fresh Claude conversation to resume.

---

I'm continuing work on the declarative-build design compiler. Last
chapter drove all 204 app_screens in the Dank file through the full
ADR-007 unified verification channel, resulting in five commits that
close entire defect classes:

- `KIND_MISSING_ASSET` — VECTOR / BOOLEAN_OPERATION rendered without
  path geometry now surfaces per-eid.
- `KIND_FONT_LOAD_FAILED` — one unlicensed trial font no longer
  aborts the whole script.
- Registry-driven whitelists in `dd/extract_screens.py` — adding a
  new property to the registry auto-extends parse + insert filters.
- Vector-path extraction — three compounding silent bugs (wrong JSON
  key, invalid separator, Figma-parser-strictness) that collapsed
  26,050 vectors into 10 empty assets. Now 256 distinct content-
  addressed assets, every vector renders.
- Post-sweep: **204/204 app_screens reach is_parity=True** on the
  fresh walker+verifier combo. 0 drift, 0 walk_failed, 0
  generate_failed, 0 error_kinds in the summary.

Read these to get oriented:

- `~/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md` —
  index. Read first.
- `docs/architecture-decisions.md` — ADR-001..007 plus two chapter
  epilogues (2026-04-15 pt 1 + pt 2). The pt 2 epilogue lists the
  commits and outstanding seeds for this chapter.
- `~/.claude/projects/-Users-mattpacione-declarative-build/memory/project_t5_progress.md` —
  round-trip state, defect-class table.
- `~/.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_verifier_blind_to_visual_loss.md` —
  the pattern for growing verifier vocabulary.
- `~/.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_figma_vector_path_roundtrip.md` —
  Figma's Plugin API vector output doesn't round-trip through its
  own vectorPaths setter.

## What I want to do this session

Continue the pattern: sweep the corpus, find a new defect class, add
a `kind` that attributes it per-eid, add the walker signal if needed,
add the verifier check, fix the data/renderer layer that caused it.
Each cycle adds one vocabulary entry to the structured-error channel
and drops one visual-loss class.

Pre-identified seeds from the pt 2 epilogue:

1. **Icon variant drift** (screen 175 Community modal-row icon
   resolves to the wrong master). The verifier can't catch this by
   IR↔rendered comparison — needs IR-vs-SOURCE drift detection via
   `ResourceProbe` (ADR-006). Likely ties into `dd drift` output.
2. **Color / fill / effect drift**: a rendered node with the wrong
   solid fill (e.g. the renderer picked a variant that uses
   `#FF0000` when IR says `#00FF00`) still reports is_parity=True.
   Candidate kinds: `KIND_FILL_MISMATCH`, `KIND_EFFECT_MISSING`,
   `KIND_STROKE_MISMATCH`.
3. **Mixed-winding paths**: a single asset currently stores ONE
   windingRule but real Figma paths sometimes mix NONZERO + EVENODD
   sub-paths. Low frequency; split into multiple VectorPath
   entries when it's the right time.
4. **Remaining non-parity screens** (if any remain after the pt 2
   sweep): each one's failure mode is a candidate new `kind`. Run
   `python3 render_batch/sweep.py` as the first step and diagnose
   whatever drift remains.

## Workflow notes

- Figma Desktop Bridge runs on whatever port
  `mcp__figma-console__figma_get_status` reports (9228 as of
  session end).
- `render_test/walk_ref.js` is the canonical walker (replaces the
  scratch /tmp/gen_175_walk.js). It captures per-eid type + text +
  geometry counts. Passing port + paths as CLI args.
- `render_batch/sweep.py` is the corpus driver. Generates scripts
  + walks + verifies + aggregates kind histograms into
  `render_batch/summary.json`. Scripts + walks + reports are
  gitignored; only the driver is in the repo.
- `dd verify --db ... --screen N --rendered-ref ... [--json]` is
  the per-screen CLI. Exit nonzero on `is_parity != True`.
- `dd extract_targeted --mode vector-geometry --port <bridge>`
  populates fill_geometry/stroke_geometry from the live Plugin
  API. Re-run this whenever the DB's geometry is stale.
- `python3 -c "from dd.extract_assets import process_vector_geometry;
  import sqlite3; c=sqlite3.connect('Dank-EXP-02.declarative.db');
  c.execute('DELETE FROM node_asset_refs'); c.execute('DELETE FROM assets');
  c.commit(); process_vector_geometry(c)"` re-processes geometry
  into content-addressed assets after a data change.

## Suggested kickoff

Start by re-running `render_batch/sweep.py` to see what current state
looks like, then dig into the first screen that reports drift. Every
new failure mode is an opportunity for a new `kind`.

Look at `docs/architecture-decisions.md` chapter epilogue pt 2
for the full list of outstanding seeds and the pattern for addressing
them.

TDD is mandatory per the global CLAUDE.md. Failing test first, then
implementation, then refactor. Commits: only when explicitly asked,
OR after each meaningful defect-class fix lands cleanly. Match the
commit-message style from the recent history (specific symptom →
root cause → fix shape → verification).

If you find a defect class that doesn't fit any existing `kind` in
`dd/boundary.py`, **add a new constant** rather than forcing it into
an existing one. The vocabulary is meant to grow.
