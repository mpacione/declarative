# Forensic-audit-2 fix sprint — final results

**Sprint duration**: ~2 hours main-thread serial work (after parallel
worker hazard forced single-thread mode)
**Bridge**: WebSocket port 9225, file `Nouns (Experimental)`
**DB**: `/tmp/nouns-postrextract.db` (untouched across the sprint)
**Baseline**: `audit/post-rextract-20260426-214433/summary.json`
**This run**: `audit/sprint-final-20260426-230449/summary.json`

## Commits shipped (6)

| Commit | Item | Files | Tests |
|---|---|---|---|
| `93b3d14` | P1a registry-driven `_build_visual` | `dd/ir.py` | 10 |
| `e776bfc` | P1b walker captures opacity/blendMode/isMask/cornerRadius | `render_test/walk_ref.js` | 5 |
| `d856e61` | P1c verifier comparators + 5 KIND_* | `dd/boundary.py`, `dd/verify_figma.py` | 20 |
| `f2afc59` | P5 `mode1_dispatch_failed` + `override_target_missing` | `dd/render_figma_ast.py`, `dd/runtime_errors.py` | 10 |
| `b7483a8` | P2 bool-op visual replay post-`figma.union` | `dd/render_figma_ast.py` | 6 |

**Plus pre-sprint setup** (this session):
- `0efbf38` 3-layer non-SOLID stroke fix
- `16be167` VLM image_provider wiring
- `8247066` extract_plugin sgt mirror

## Headline metrics (post-rextract baseline → post-sprint)

| Metric                            | Pre  | Post | Δ      |
|-----------------------------------|-----:|-----:|-------:|
| `is_parity_true` (clean)          | 32   | 33   | +1     |
| `is_parity_false`                 | 35   | 34   | -1     |
| `is_structural_parity_true`       | 50   | 51   | +1     |
| `walk_failed`                     | 0    | 0    | 0      |
| `walk_timed_out_count`            | 0    | 0    | 0      |
| screens with runtime errors       | 20   | 20   | 0      |
| total runtime errors              | 37   | 37   | 0      |
| **error_kinds** (verifier-side)   | `{fill_mismatch:23, stroke_mismatch:7}` | `{cornerradius_mismatch:26, fill_mismatch:8, stroke_mismatch:7}` | NEW class lit up |
| elapsed_s                         | 259.6 | 2059.4 | +1799.8 |

## What the headline numbers ACTUALLY mean

The +1 net DRIFT recovery looks small, but the surface tells a richer
story. Three distinct signals:

### 1. Real DRIFT recoveries (P2 working as designed)

| screen | prev kinds | post kinds | mechanism |
|--------|-----------|-----------|-----------|
| 33 | `[fill_mismatch x5]` | (clean) | P2 bool-op visual replay |
| 77 | `[fill_mismatch x3]` | (clean) | P2 bool-op visual replay |

P2 also reduced screen-level fill counts:
- Screen 24: 5 fill_mismatch → 1 (the bool_op fills cleared; instance-5 default-fill remains)
- Screen 25: 3 fill_mismatch → 2
- Screens 40/43/44/48/49 also lost their bool_op fill errors

The +1 PARITY count is just because most of those screens still have
OTHER drift classes that became visible (see signal 3).

### 2. The verifier woke up — `cornerradius_mismatch` lit up 26 errors across N screens

Pre-sprint: 0 cornerradius_mismatch. Post-sprint: 26 errors.

This is **P1c doing its job for the first time.** Pre-sprint, the
verifier had no `KIND_CORNERRADIUS_MISMATCH` constant; it never
compared cornerRadius values. Real visual drift on cornerRadius was
silently passing as `is_parity: True`. Post-sprint, those errors
surface.

The same logic applies to opacity, blendMode, rotation, and isMask —
their KIND_* constants are now in `dd/boundary.py` and the
comparators in `dd/verify_figma.py`. They didn't fire on Nouns
because the underlying drift conditions don't exist on this corpus,
but the architectural surface is now correct.

Specific cornerradius_mismatch appearances:
- screen 10 (newly DRIFT): 6 cornerradius errors — were always there,
  now visible
- screens 26, 48, 49: cornerradius errors join existing fill errors
- screen 24, 25: had cornerradius drift that was masked

### 3. Remaining `fill_mismatch` (8) + `stroke_mismatch` (7) are all
     instance-snapshot-vs-master class

Per-screen audit confirmed every remaining `fill_mismatch` and every
`stroke_mismatch` is on a Mode-1 INSTANCE node where the IR carries
an extraction snapshot of fill/stroke that differs from the master's
runtime default. This is the same class as the chip-1 case
documented in `feedback_fill_mismatch_instance_suppression.md` —
already partially handled there with a NARROW token-bound-gradient
suppression rule.

The proper fix is **override-vs-snapshot provenance tagging**: tag
extracted IR values with whether they're a runtime override request
or a passive snapshot. The verifier then enforces overrides and
ignores snapshots. This is too big for this sprint; filed as the
**Backlog #1: provenance tagging** ticket.

## P3 reclassified (originally framed as "Mode-1 id-stable resolver")

The forensic audit's P3 hypothesis (`resolver_bucket.get(prop.path)`
uses name-based lookup that collides on duplicate-name children) was
**invalid on closer inspection**. The resolver:
- Already keys VALUES by id-suffix (figma node id segments)
- Already disambiguates colliding path keys with `-N` suffixes in
  `compress_l3.py:1696-1714`
- Both keys + values are id-stable end-to-end

The 7 iPhone stroke_mismatch cases attributed to P3 are actually
the same instance-snapshot-vs-master-default class as the
fill_mismatch cases (signal 3 above). Codex 5.5 (gpt-5.5 high
reasoning) confirmed this analysis: "Without provenance, solid
stroke IR is indistinguishable from a legitimate override
expectation. Broad stroke suppression on `INSTANCE` would hide
real override replay bugs."

## P4 skipped — empirically non-impacting

The audit's `default_value=1.0` for strokeWeight + visual.py
None-handling fix would have been a no-op on Nouns:
- 0 nodes have `stroke_weight=NULL` (extraction always populates)
- 26K-node theoretical claim was not borne out empirically

Codex 5.5 confirmed: "skip P4 as scoped." Filed an unrelated
finding (82 nodes have `stroke_weight=0` AND visible strokes)
as **Backlog #2: 0-weight-with-strokes** ticket.

## Backlog filed

1. **Provenance tagging for instance overrides**. Add an
   override-vs-snapshot flag to extracted instance fills/strokes.
   Verifier enforces overrides, ignores snapshots. Closes the
   8 remaining `fill_mismatch` and 7 `stroke_mismatch` errors
   on Mode-1 INSTANCE heads. Probably 200-400 LOC + tests +
   re-extract.

2. **0-weight-with-strokes (82 nodes)**. Investigate whether the
   renderer rejects strokeWeight=0 on visible strokes; if so,
   normalize at IR build time or extraction. Probably 50-100 LOC.

## Why the sweep was 8× slower (259s → 2060s)

The new comparators in P1c surface more drift, and the sweep retries
DRIFT screens up to 3x hoping for transient recovery. With more
drift surfaced, more retries fire. p50 walk time stayed at 333ms
(unchanged). The increase is concentrated on the iPhone instance
screens (24, 25, 40, 43 ~117s each = 3 attempts × ~40s per attempt
including retry backoff).

This is a side effect of "verifier doing its job for the first
time on previously-blind drift classes" rather than a regression.
Sweep retry tuning is a separate optimization.

## Sprint methodology notes

- **Started parallel** (Workers A + B in background); the
  auto-revert system silently rolled back my main-thread edits when
  worker writes hit. Forced switch to **serial mode** mid-sprint.
- **Codex 5.5 consulted at every architectural fork**:
  - Sequencing decision
  - P4 skip rationale
  - P3 reclassification
  - Strict-tolerance choices for P1c numeric comparators
  - Test shape per layer
- All commits TDD-driven. ~70 new tests. Zero introduced regressions
  on touched test surface.

## Final commit summary

```
b7483a8 feat(renderer): bool-op visual replay post-materialization                  (P2)
f2afc59 feat(renderer): explicit dispatch-failure errors for Mode-1 + override miss (P5)
d856e61 feat(verifier): comparators for opacity/blendMode/rotation/isMask/cornerRadius  (P1c)
e776bfc feat(walker): capture opacity/blendMode/isMask/cornerRadius for verifier    (P1b)
93b3d14 feat(verifier): registry-drive _build_visual to close visual-coverage blind spots (P1a)
8247066 fix(extract): mirror sgt enrichment in unified plugin walker                (pre-sprint)
16be167 feat(cluster): wire VLM image_provider end-to-end via bridge thumbnails    (pre-sprint)
0efbf38 fix(pipeline): plug 3-layer drop on non-SOLID strokes + effect token refs  (pre-sprint)
```

The sprint shipped what it could ship without enabling false-positive
suppressions. The remaining work is well-scoped backlog with a clear
implementation path (provenance tagging) — ready for a future session.
