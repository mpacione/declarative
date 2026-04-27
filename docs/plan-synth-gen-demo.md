# Synth-gen demo plan

**Branch**: `v0.3-integration`
**Start tip**: `b00570f` (post-13-item burndown plan)
**Plan authors**: Claude Opus 4.7 (main thread / orchestrator) +
                  Codex 5.5 high-reasoning (architectural partner)
**Date**: 2026-04-27

User authorized: *"spec this out carefully and then write it down as a
plan, and get started. Use codex 5.5 for a second opinion and Sonnet
subagents for writing code and reviewing. You should orchestrate."*
+ later *"continue working until the demo is ready"* (autonomous mode).

## §1 The demo target

```bash
# Seed root from a Dank screen (no agent turns; just persist source)
dd design --brief "frame as a mobile commerce product detail surface" \
  --starting-screen N \
  --project-db /tmp/dank-fresh-20260427.db \
  --db /tmp/dd-demo.db \
  --max-iters 0

# Three lateral siblings + project-vocab snapping + render to Figma
dd design lateral <root-variant-id> \
  --brief "Conversion-focused: emphasize primary action, reduce decorative noise" \
  --brief "Editorial discovery: storytelling + imagery + premium browsing" \
  --brief "Dense power-user: more product metadata + secondary actions" \
  --use-project-vocab \
  --render-to-figma --bridge-port 9225 \
  --variant-only \
  --db /tmp/dd-demo.db --project-db /tmp/dank-fresh-20260427.db

# Show variant tree + move log for demo narration
dd design variants <session-id> --db /tmp/dd-demo.db
dd design log <session-id> --db /tmp/dd-demo.db
```

End state: source screen on Dank's canvas, three sibling Figma pages
(named `design session <SID8> / <VID12>`), each rendered with
project-native colors / radii / spacing / font sizes; persisted move
log per variant; queryable variant tree.

## §2 What's already shipped vs what's missing

### Shipped (verified by reading code)

- `dd/agent/loop.py:run_session` — agent loop with name/drill/climb +
  7 edit verbs
- `dd/agent/primitives.py` — drill / climb / name_subtree
- `dd/sessions.py` + `design_sessions` / `variants` / `move_log` tables
- `dd/cli.py` `dd design --brief / resume / log` subcommands
- `dd/fidelity_score.py`, `dd/patterns.py`, `dd/prompt_parser.py`,
  `dd/composition/archetype_classifier.py`,
  `dd/composition/providers/corpus_retrieval.py`
- Item 1 layoutSizing fix uncommitted (5 modified files + 1 new test file,
  16 tests green, 912/912 across full IR/verifier suite)

### Missing (Codex round-13 confirmed)

- `--bridge-port` CLI flag — `dd/apply_render.py:execute_script_via_bridge`
  takes `ws_port`, but `dd/cli.py:_render_session_to_figma` doesn't pass
  it. Three call sites at lines 2730, 2734, 2758. Default is 9228; active
  bridge is 9225. **Hard demo blocker.**
- `dd design lateral` subcommand — variant data model supports siblings
  via `parent_id`, but no CLI command exists to produce N siblings from
  a parent in one call.
- `dd design variants <session>` listing — convenience for demo
  narration; deferrable (raw SQL or `dd design log` substitutes).
- `dd/project_vocabulary.py` — module doesn't exist. Mode 2 emission today
  uses raw IR values; demo without it shows visibly off-brand colors.

## §3 The 5 commits

### C1 — Commit Item 1 layoutSizing fix

**Intent**: clean tree before agent-loop work; ship the layoutSizing
canonicalization that closes the dominant Sprint 2 C11 drift class.

**Files**: already-modified
- `dd/ir.py` (IR-side canonicalization post-pass)
- `dd/visual.py` (`_resolve_one_axis` validates DB against context)
- `dd/renderers/figma.py` (emit layoutSizing when self/parent is
  auto-layout-relevant)
- `dd/render_figma_ast.py` (same threading)
- `tests/test_item1_layout_sizing_canonicalization.py` (16 tests)
- `tests/test_generate.py` (2 stale assertions updated)

**Dependencies**: none (uncommitted work).

**Acceptance gates**:
- `pytest tests/test_item1_layout_sizing_canonicalization.py` all green
- Full IR/verifier suite still green (912/912)
- Commit message acknowledges this is a tactical fix on the deprecated
  dict-IR pipeline, to be migrated when M6(b) cutover executes

**Rollback**: trivial — `git revert`.

**Owner**: main thread.

---

### C2 — Add `--bridge-port` flag

**Intent**: unblock `--render-to-figma` for demo. CLI hardcodes 9228;
real bridge is on 9225.

**Files**: `dd/cli.py`
- argparser at ~line 1838 (design parent) + line 1936 (resume) — add
  `--bridge-port int default=9228` flag
- `_run_design_brief` signature — accept `bridge_port` param (line 2214)
- `_run_design_resume` signature — same (line 2816)
- `_run_design` dispatcher — pass through (line 2135)
- `_render_session_to_figma` signature — accept + pass to all three
  `execute_script_via_bridge` calls (lines 2730, 2734, 2758)

**Dependencies**: C1 must be committed (clean tree).

**Acceptance gates**:
- `dd design --help` shows `--bridge-port`
- Default `--bridge-port` is 9228 (no behavior change for existing flows)
- `--bridge-port 9225` reaches `execute_script_via_bridge(ws_port=9225)`
  end-to-end (verified by adding a unit test that mocks
  `execute_script_via_bridge` and asserts the port arg)
- Existing `dd design --brief --render-to-figma` (no port flag) still
  hits 9228

**Rollback**: revert; no semantic dependencies.

**Owner**: main thread (small focused change, no parallelizable work).

**LOC**: 35-60.

---

### C3 — `dd design lateral` subcommand

**Intent**: produce N sibling variants from one parent in one CLI call.
The actual missing demo capability — the seam between "agent edits a
screen" and "designer explores variants."

**Files**: `dd/cli.py`
- new `design_lateral_parser` under existing `design_subparsers`
  (around line 1810)
- new `_run_design_lateral(db_path, *, parent_variant_id, briefs,
  bridge_port, render_to_figma, variant_only, project_db, dump_scripts,
  labels, max_iters, use_project_vocab)` dispatcher
- loops over briefs, calls `run_session(conn, brief=brief,
  parent_variant_id=parent, ...)` per brief
- collects final variant ids; if `--render-to-figma`, calls
  `_render_session_to_figma` per leaf
- prints summary: `<session_id> / <root_variant>` then per-sibling
  `<variant_id> / <brief excerpt> / <page_name if rendered>`

**Open question**: does `run_session` already accept
`parent_variant_id` or do we need to add it? Verify before
implementation. If not, smaller workaround: use
`_run_design_resume`-style code path with the parent's L3 doc as
starting state.

**Dependencies**: C2 (bridge port) must land first because C3's
render path uses the same execute_script_via_bridge call sites.

**Acceptance gates**:
- `dd design lateral --help` shows the schema
- `dd design lateral <root-variant-id> --brief X --brief Y` produces
  2 siblings, both persisted under same parent in `variants` table
- `--render-to-figma --bridge-port 9225 --variant-only` renders both
  siblings to two separate Figma pages
- Unit test for the lateral dispatcher with mocked `run_session`
  asserts N briefs → N `run_session` calls with same `parent_variant_id`

**Rollback**: revert; doesn't touch existing subcommands.

**Owner**: Sonnet worker (bounded scope, single file). Pre-commit
Sonnet reviewer.

**LOC**: 120-180.

---

### C4 — `dd design variants <session>` listing (DEFERRABLE)

**Intent**: convenience for demo operator to surface variant tree
without raw SQL.

**Files**: `dd/cli.py`
- new `design_variants_parser` under `design_subparsers`
- new `_run_design_variants(db_path, session_id)` reads
  `dd/sessions.py:list_variants`
- prints tree: parent → children with brief excerpt + page_name + variant_id

**Dependencies**: C1 (clean tree). Independent of C2-C3.

**Acceptance gates**:
- `dd design variants <session>` lists all variants for a session
- Output format human-readable in CLI (root + indented siblings)
- Unit test with seeded session DB

**Rollback**: trivial.

**Deferral note**: if time pressure hits before C5, drop C4. Demo
operator can run `dd design log <session>` (already exists) for the
move log; variant tree can be exposed via raw SQL. C4 is polish.

**Owner**: Sonnet worker. Pre-commit Sonnet reviewer.

**LOC**: 60-100.

---

### C5 — `dd/project_vocabulary.py` + `--use-project-vocab` flag

**Intent**: snap Mode 2 emissions to project-canonical literal values
so demo variants look native to the source design system. The
visible-difference commit.

**Files**:
- NEW `dd/project_vocabulary.py` (~180-230 LOC)
- `dd/cli.py` — add `--use-project-vocab` flag to design / lateral /
  resume parsers, thread through to call sites (~60-90 LOC)
- post-IR transform pass insertion in design pipeline (after
  `build_composition_spec`, before render handoff)
- NEW `tests/test_project_vocabulary.py` (~80-120 LOC)

**Module spec** (Codex round-13 lock):

```python
def build_project_vocabulary(db_path: str) -> ProjectVocabulary:
    """Frequency-based top-K extraction per dimension.

    Caps:
      fills: 16 chromatic + 8 neutral (split via OKLCH chroma >0.05)
      radii: 8
      spacing/padding: 12
      fontSize: 8
    """

def snap_ir_to_vocabulary(spec: dict, vocab: ProjectVocabulary) -> tuple[dict, SnapReport]:
    """Walk every untokenized literal in spec; snap to nearest
    vocab value if within thresholds:
      - colors: OKLCH ΔE ≤ 10; chromatic also requires hue Δ ≤ 24°;
        neutrals require lightness Δ ≤ 0.10
      - radius: abs Δ ≤ 2px OR rel Δ ≤ 20%
      - spacing/padding: abs Δ ≤ 3px OR rel Δ ≤ 20%
      - fontSize: abs Δ ≤ 2px OR rel Δ ≤ 12%

    Returns (mutated_spec, SnapReport(fills_snapped=N, radii_snapped=N,
    spacing_snapped=N, fontSize_snapped=N)).
    """
```

**Reuses**:
- `dd.color.hex_to_oklch`, `oklch_delta_e` (verify presence)
- `dd.cluster_spacing.query_spacing_census` (verify presence)
- `dd.cluster_misc.query_radius_census` (verify presence)

**Default behavior**: `--use-project-vocab` is OFF by default; demo
toggles on. No effect on existing flows.

**Dependencies**: C3 (because C3 adds the lateral command that needs
the flag wired through).

**Acceptance gates**:
- `pytest tests/test_project_vocabulary.py` all green:
  - vocabulary extraction returns top-K per dimension
  - chromatic/neutral split works
  - snap rules apply correct thresholds
  - SnapReport counts match
- `dd design lateral --use-project-vocab --help` shows flag
- Demo before/after: same lateral run with/without flag produces
  visibly different colors / radii on at least one variant
- "project vocab: fills N, radii N, spacing N, fontSize N snapped"
  printed during run

**Rollback**: revert; flag-default-off ensures safe rollback.

**Owner**: Sonnet worker (bounded scope, mostly new code, math reuse
from existing modules). Pre-commit Sonnet reviewer.

**LOC**: 350-450 (180-230 module + 60-90 CLI + 80-120 tests).

**Failure mode (Codex round-13 lock)**: if scope balloons, fall back
to Option C — colors-only. Defer radii/spacing/fontSize. Still ships
demo-visible difference because brand colors are the dominant
visual fingerprint.

---

## §4 Orchestration

### Subagent coordination per Codex round-13

- **Codex 5.5** at every architectural fork. Already locked: scope per
  commit, vocab spec, snap thresholds, smoke gates.
- **Sonnet workers** for C3 + C4 + C5 — bounded scopes, single-file
  ownership, must NOT touch other modules or reorganize parser.
- **Sonnet pre-commit reviewers** after each Sonnet-worker commit.
  Verify: parser regressions, default behavior preserved, help output
  intact, tests deterministic.
- **Main thread** for C1 (already-uncommitted) + C2 (small CLI
  plumbing) + final demo run.

### Serial pipeline (no parallel writes)

C2-C5 all touch `dd/cli.py`. Per Sprint 1's parallel-write hazard,
serial only. Worker dispatched after prior commit lands and passes
smoke.

```
main C1 → main C2 → worker C3 + reviewer → worker C4 + reviewer → worker C5 + reviewer → demo run
```

### Smoke gates between commits

After every commit:
- `dd design --help` still works (parser regression check)
- Existing `dd design --brief` (no new flags) still default-renders
  to port 9228 (or whatever default existed pre-commit)
- Full IR/verifier test suite green (no regression on Sprint 2 work)

After C5 specifically:
- Run with `--use-project-vocab`: produces snap report
- Run WITHOUT flag: no behavior change vs C4-state demo

## §5 Demo run script

After all commits land:

1. **Bridge guard**: confirm Figma plugin connected to Dank file on
   port 9225 (`figma_get_status` + `figma_execute` for verification)
2. **Survey Dank app_screens**: query `screens WHERE
   screen_type='app_screen' ORDER BY id LIMIT 20`. Pick 1-3 reasonable
   starting screens (mid-complexity, not iPad-Pro 12.9 monsters,
   not icons or icon-defs)
3. **API key preflight**: confirm `.env` is loaded by `dd` —
   `python -c "from dotenv import load_dotenv; load_dotenv();
   import os; print('ANTHROPIC_API_KEY set:',
   bool(os.environ.get('ANTHROPIC_API_KEY')))"`
4. **Smoke run**: `dd design --brief "..." --starting-screen N
   --max-iters 1 --db /tmp/dd-demo-smoke.db
   --project-db /tmp/dank-fresh-20260427.db` (no render). Verify agent
   loop + persistence works.
5. **Full demo run**: lateral with 3 briefs + `--use-project-vocab`
   + `--render-to-figma` + `--bridge-port 9225` + `--variant-only`
6. **Capture**: command, session_id, root variant_id, sibling
   variant_ids, page names, snap report
7. **Show**: `dd design variants` + `dd design log` against the
   session for demo narration

## §6 Failure-mode contingencies (Codex round-13 lock)

| If | Then |
|---|---|
| C5 takes longer than 4h | Option C: colors-only (defer radii / spacing / fontSize); still demos visible difference |
| C5 still bigger after Option C | Option A: ship without C5; demo narration acknowledges style drift |
| Time tightens before C4 | Drop C4; use raw SQL or `dd design log` for variant tree narration |
| Render times out per variant | `--variant-only` already in plan; if still timing out, dump scripts via `--dump-scripts` and demo from saved JS |
| Bridge connection fails | Check `figma_get_status` / `figma_list_open_files`; verify Dank is the active file |
| Anthropic API key missing | Confirm `.env` loading; if absent, demo halts before agent loop |
| LLM produces low-effort variant | Bump `--max-iters` from 3 to 5-8 per session; or refine briefs to be more specific |

## §7 Definition of done

The demo is ready when:

- ✅ All 5 commits (or 4 if C4 deferred) on `v0.3-integration`
- ✅ Smoke run completes (agent loop + persistence)
- ✅ Full demo run produces 3 Figma pages with rendered variants
- ✅ Snap report visible during run (proves project-vocab is firing)
- ✅ `dd design log` outputs LLM's edit narrative for demo
- ✅ Captured demo command + session_id documented for re-run

---

**Co-authored**: Claude Opus 4.7 (orchestrator) +
Codex 5.5 (Round 13 sequencing call) +
Sonnet workers/reviewers per §4
