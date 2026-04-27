# Cross-corpus validation — Dank + HGB sweeps post-architectural-sprint

**Date**: 2026-04-27
**Branch tip**: `91a67f2` (post-sprint, post-cornerRadius-float fix)
**Method**: fresh REST extract → fresh extract-plugin → full sweep, both files
**Bridge port**: 9225 (default 9223 → fallback 9225 active)
**Discipline**: bridge-guard verified (`figma_get_status` + `figma_execute`
returning fileKey/fileName/currentPage) before every bridge step

## TL;DR

**Sprint generalizes.** HGB hits 100% structural parity, 0 verifier
mismatches on first observation. Dank hits 88.5% structural parity
with the remaining 11.5% all clustered on one new bug class
(VECTOR `cornerRadius` capability-table gap), which the new A5
comparators correctly surfaced — exactly the architectural-sprint
working-as-designed pattern.

| Corpus | Total | Structural parity | Verifier kinds | DRIFT |
|---|---:|---:|---:|---:|
| Nouns (sprint baseline) | 67 | 67 (100%) | 0 | 0 |
| **Dank** (this run) | **200** | **177 (88.5%)** | **23 cornerradius_mismatch** | **23** |
| **HGB** (this run, no prior baseline) | **44** | **44 (100%)** | **0** | **0** |
| **Total all three corpora** | **311** | **288 (92.6%)** | **23** | **23** |

## 1. Bridge guard discipline

Per Codex 5.5's design call, every bridge-bound step preceded by:

```
figma_navigate(<file URL>)        # explicit switch
figma_execute(return {fileName, fileKey, currentPage})   # verify
```

Verified state at each step (timestamps in `audit/.../bridge-state.txt`
not generated; recorded in this session log):

- Pre-Dank-extract: `Dank (Experimental)`, `drxXOUOdYEBBQ09mrXJeYu`,
  page `Generated Test`, 0 children
- Pre-Dank-sweep: same, 0 children
- Pre-HGB-extract: `HGB (Experimental)`, `PsYyNUTuIE1IPifyoDIesy`,
  page `Generated Test`, 0 children
- Pre-HGB-sweep: same

No cross-contamination occurred.

## 2. Dank — observations

### 2.1 Pipeline state

| Stage | Result |
|---|---|
| REST extract | 201 screens, 80,245 nodes, 0 failed |
| Plugin extract | 157,082 nodes touched, 56,108 instance_overrides rows populated |
| `screen_type` classification | 200 app_screen, 1 design_canvas |
| Sweep | 200 app_screens in 439s |

### 2.2 Outcome

| Metric | Value |
|---|---:|
| total | 200 |
| is_structural_parity | **177 (88.5%)** |
| strict PARITY (no rt errors) | 174 |
| PARITY+ (rt errors only) | 3 |
| DRIFT (verifier-flagged) | **23** |
| walk_failed | 0 |
| walk_timed_out | 0 |
| retried | 0 |
| elapsed_s | 439.1 |

### 2.3 Failure-class breakdown

| kind | count | analysis |
|---|---:|---|
| `cornerradius_mismatch` | **23** | NEW BUG CLASS — see §2.4 |
| `fill_mismatch` | 0 | A1.1/A1.2/A1.3 closed this class on Dank too ✓ |
| `stroke_mismatch` | 0 | Same ✓ |
| any other verifier kind | 0 | Clean |
| `text_set_failed` (rt) | 3 | font-license blocker, out-of-scope |
| `font_load_failed` (rt) | 3 | same |

### 2.4 New bug class: VECTOR `cornerRadius`

All 23 DRIFT screens are single-error `cornerradius_mismatch`,
all on VECTOR nodes:

```
screen 62  : id='vector-1'   IR=2.0, rendered=0
screen 89  : id='vector-52'  IR=2.0, rendered=0
... 23 total, identical pattern
```

**Root cause** (see `dank/FINDING-vector-cornerradius.md`):
`dd/property_registry.py:51` defines

```python
_FIGMA_CORNER_CAPABLE = _FIGMA_CONTAINERS | _FIGMA_BASIC_SHAPES
# = {FRAME, COMPONENT, INSTANCE, SECTION} ∪ {RECTANGLE, ELLIPSE, POLYGON, STAR}
# missing: VECTOR, BOOLEAN_OPERATION
```

The renderer's emission gate calls
`is_capable("cornerRadius", "VECTOR") -> False` and silently
skips. The IR correctly carries `cornerRadius=2.0`, the verifier
correctly flags the missing emission. Only the capability table
is wrong.

**Codex 5.5 confirmed** the Plugin API DOES support `cornerRadius`
on `VectorNode` and `BooleanOperationNode` (Figma docs cite both
the `VectorNode` page and the cornerRadius properties page).

**Status**: Documented but NOT FIXED in this validation pass per
user directive. One-line fix:
```python
_FIGMA_CORNER_CAPABLE = _FIGMA_CONTAINERS | _FIGMA_BASIC_SHAPES | {"VECTOR", "BOOLEAN_OPERATION"}
```
Test plan: failing test asserting
`is_capable("cornerRadius", "VECTOR") == True` → green via
table fix → re-sweep Dank confirming 23 → 0.

### 2.5 Architectural-sprint validation on Dank

| Sprint deliverable | Validation on Dank |
|---|---|
| A1.1 IR `_overrides` side-car | 56,108 instance_overrides rows feed it; renderer/verifier exercise the chain |
| A1.2 renderer per-prop gating | 0 fill_mismatch, 0 stroke_mismatch on 8,895 FILLS + 2,382 STROKES override rows |
| A1.3 verifier per-prop gating | Same — would otherwise have flagged thousands of false positives |
| A5 new comparators | Exactly as designed: surfaced VECTOR cornerRadius gap |
| A3.2/A4 Mode-3 paths | Not exercised on Dank sweep (Mode-1-heavy corpus) |
| Backlog #4 retry skip | 0 retries fired — DRIFT screens correctly classified non-transient |

## 3. HGB — observations

### 3.1 Pipeline state

| Stage | Result |
|---|---|
| REST extract | 44 screens, ~14k nodes, 0 failed |
| Plugin extract | 40,550 nodes touched, 6,999 instance_overrides rows populated |
| `screen_type` classification | 44 app_screen, 0 others |
| Sweep | 44 app_screens in 84.2s |

First observation, no prior baseline.

### 3.2 Outcome

| Metric | Value |
|---|---:|
| total | 44 |
| is_structural_parity | **44 (100%)** |
| strict PARITY (no rt errors) | 11 |
| PARITY+ (rt errors only) | 33 |
| DRIFT (verifier-flagged) | **0** |
| walk_failed | 0 |
| retried | 0 |
| elapsed_s | 84.2 |

### 3.3 Failure-class breakdown

| kind | count | analysis |
|---|---:|---|
| any verifier kind | **0** | Clean run |
| `text_set_failed` (rt) | 528 | font-license blocker — 'Akkurat'/'Akkurat-Bold' family not installed |
| `font_load_failed` (rt) | 60 | same root cause |

Sample error from screen 39:
```json
{"kind": "font_load_failed", "family": "Akkurat", "style": "Regular",
 "error": "The font \"Akkurat Regular\" could not be loaded"}
```

Same out-of-scope class as the 20 PARITY+ screens on Nouns
(GT Walsheim Trial / GT America Mono).

## 4. Cross-corpus signal

### 4.1 The architectural sprint generalizes

| Class A1.1+A1.2+A1.3 closes | Nouns | Dank | HGB |
|---|---:|---:|---:|
| `fill_mismatch` count | 0 | 0 | 0 |
| `stroke_mismatch` count | 0 | 0 | 0 |
| (was 8 + 7 on Nouns pre-sprint) | | | |

The provenance chain works on three different corpora with
three different INSTANCE-override patterns
(Nouns 2,403 + Dank 56,108 + HGB 6,999 override rows).

### 4.2 New bug discovered by A5 comparators

The cross-corpus exercise paid for itself: VECTOR cornerRadius
capability gap was invisible on Nouns (no VECTORs with corner
radii in the source) and appeared immediately on Dank. This is
exactly what cross-corpus validation is for.

### 4.3 Sprint-design validation

Codex 5.5's pre-sprint hypothesis was that the new comparators
would surface real drift, then we'd fix the underlying bugs.
That happened twice now:

1. Sprint, Nouns: A5 surfaced 26 cornerradius_mismatch on FRAME →
   `int()` truncation bug → fixed at `9037a05` → 0 mismatches
2. Cross-corpus, Dank: A5 surfaced 23 cornerradius_mismatch on
   VECTOR → capability-table gap → fix queued (this doc)

The pattern holds. Future corpus runs will likely surface more.

## 5. What's NOT in scope of this validation

- The VECTOR cornerRadius fix (queued per user)
- The font-license blocker (Akkurat / GT Walsheim / GT America Mono
  not installed locally — out of engineering scope)
- Mode-3 composition validation (no synthetic IR exercised in
  these sweeps — same gap as Nouns sprint)
- Performance/perf regression measurement (Dank 200 screens in
  439s = 2.2s/screen avg, HGB 44 in 84s = 1.9s/screen avg —
  consistent with post-sprint Nouns 0.8s/screen at parity, the
  difference is the larger node counts on Dank/HGB)

## 6. Files generated

- `audit/cross-corpus-20260427-190100/dank/`
  - `extract.stdout.txt` — REST extract log
  - `extract-plugin.stdout.txt` — bridge plugin walk log
  - `sweep.stdout.txt` — full per-screen sweep transcript
  - `summary.json` — sweep aggregate
  - `reports/` — 200 per-screen verifier reports
  - `walks/` — 200 per-screen walk results
  - `scripts/` — 200 generated render scripts
  - `FINDING-vector-cornerradius.md` — bug writeup
- `audit/cross-corpus-20260427-190100/hgb/`
  - `extract.stdout.txt` — REST extract log
  - `extract-plugin.stdout.txt` — bridge plugin walk log
  - `sweep.stdout.txt` — full per-screen sweep transcript
  - `summary.json` — sweep aggregate
  - `reports/` — 44 per-screen verifier reports
  - `walks/` — 44 per-screen walk results
  - `scripts/` — 44 per-screen render scripts

DBs (not committed; in `/tmp/`):
- `/tmp/dank-fresh-20260427.db`
- `/tmp/hgb-fresh-20260427.db`

Working files (not used; bad-schema attempt deleted):
- `/tmp/dank-cross-corpus-20260427.db` (deleted — schema drift on
  copy-from-existing-DB; fresh-DB approach worked)

## 7. Recommended next steps

1. **Apply VECTOR cornerRadius fix** (one-line capability-table
   change + test). Re-sweep Dank: 177 → 200 expected. Re-sweep
   HGB to confirm no regression. Re-sweep Nouns to confirm no
   regression on the FRAME-cornerRadius path. Commit.
2. **Audit other capability-table omissions** per Codex 5.5
   suggestion: COMPONENT_SET, SLIDE, HIGHLIGHT, SLOT for corner
   support; do an end-to-end check that every property's
   capability set matches Plugin API reality.
3. **Mode-3 corpus validation** still pending from sprint
   §5 — needs a brief-driven `dd design --brief` run to
   exercise A3.2/A4 paths, none of these three corpus sweeps
   exercise Mode 3.
