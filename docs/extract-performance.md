# Extract pipeline performance

Longitudinal timing log lives at `~/.cache/dd/extract_timings.jsonl`. Every
run of `dd extract`, `dd extract-supplement`, and `python -m dd.extract_targeted`
appends a record with per-stage durations, throughput, and run metadata
(screen count, node count, file key). Use for spotting regressions and
before/after comparisons on perf work.

## Measured baseline (Dank Experimental, 2026-04-16)

- 338 screens / 204 app screens / 86,766 nodes
- 25,860 INSTANCE nodes with component_key
- Full pipeline: extract → supplement → 4× targeted = **361s total**

| Stage | Duration | Throughput | % of total |
|-------|---------:|-----------:|-----------:|
| REST extract (fetch + process) | **104s** | 3.2 screens/s | 29% |
| ├─ rest_fetch_screens | 79s | 4.3 screens/s | 22% |
| └─ process_screens | 24s | 13.9 screens/s | 7% |
| Plugin supplement | **127s** | 1.6 screens/s | 35% |
| Plugin transforms | 34s | 6.0 screens/s | 9% |
| Plugin properties | 28s | 7.3 screens/s | 8% |
| Plugin sizing | 28s | 7.3 screens/s | 8% |
| Plugin vector-geometry | 40s | 5.1 screens/s | 11% |

## Improvement opportunities (ranked by impact)

### 1. Parallelize REST fetch — 79s → ~15s

`FigmaIngestAdapter.extract_screens()` in `dd/ingest_figma.py` currently runs
batches sequentially. Measured on this file:

- Sequential 40 screens / 4 batches: 5.68s
- Parallel 4 workers, same 4 batches: 0.74s (**7.6× wall-time speedup**)

Figma allows ~50 req/s at the published rate limit; we're at ~0.4 req/s
serialized. ThreadPoolExecutor with `max_workers=4..8` is the fix. The
adapter's null-handling / structured-error path is already per-batch, so
parallelization is drop-in.

### 2. Read `component_key` from REST response — save ~60s of supplement

**Key discovery**: the REST `/v1/files/{key}/nodes` response includes a
per-screen `components` map with `key` on every referenced component:

```json
{
  "nodes": {
    "5749:82465": {
      "document": {...},
      "components": {
        "5749:82238": { "key": "21ade1acf1c0a1a556c1ffa2f375863bf7f82e3c",
                         "name": "icon/more", "remote": false, ... }
      }
    }
  }
}
```

Verified **100% parity** on the first 10 screens of Dank Experimental: 58
distinct component keys from REST, 58 from the Plugin API supplement,
zero diff.

This eliminates the biggest cost in the supplement pass: 25,860
`getMainComponentAsync()` calls (one per INSTANCE). `_add_component_reference`
in `dd/figma_api.py` already captures `componentId` but doesn't resolve it
to `key` via the file-level components map.

Supplement drops from 127s → ~60s by removing the async component lookups.

### 3. Consolidate 5 Plugin-API passes into 1 walk — save ~130s

The current pipeline runs **five separate Plugin-API walks of the same
node trees**:

| Pass | Collects | Currently |
|------|----------|----------:|
| supplement | componentKey, layoutPositioning, Grid, overrides | 127s |
| transforms | relativeTransform, vectorPaths, w/h, openTypeFeatures | 34s |
| properties | is_mask, boolean_operation, corner_smoothing, arc_data | 28s |
| sizing | layoutSizingH/V, textAutoResize, font_style, text_decoration, paragraph_spacing, layout_wrap | 28s |
| vector-geometry | fillGeometry, strokeGeometry | 40s |

All five are read-only — no ordering dependency. Merging into a single walk
is ~60s (most of the cost is the per-INSTANCE async component lookup;
traversal alone is cheap). Combined with #2 (no lookup needed), the unified
pass drops to ~30–40s.

## Combined impact projection

| | Current | After #1 | After #1+#2 | After #1+#2+#3 |
|---|--------:|---------:|------------:|---------------:|
| REST fetch | 79s | 15s | 15s | 15s |
| REST process | 24s | 24s | 24s | 24s |
| Plugin passes | 257s | 257s | ~200s | ~35s |
| **Total** | **361s** | **296s** | **239s** | **74s** |
| **Speedup** | 1.0× | 1.2× | 1.5× | **4.9×** |

## Measured results (post-implementation)

| Stage | Baseline | After | Delta |
|---|--:|--:|--:|
| REST extract (fetch + process) | 104s | 107s | — |
| Plugin pipeline | 257s (5 passes) | **114s** (unified) | **−143s (−56%)** |
| **Total** | **361s** | **221s** | **−140s (−39%, 1.63×)** |

### Deltas vs the projection

- **#1 didn't deliver.** Figma's 429 rate limiter aggressively
  throttles parallel fetch. At max_workers=4 the burst trips 429s
  mid-run and drops ~30 screens after the retry budget is
  exhausted. At max_workers=2 the jittered backoff serializes the
  workers and wall time lands at 81s (same as sequential 79s). The
  code path is preserved for callers on higher-tier API plans, but
  the default is now max_workers=1.

- **#2 delivered fully.** REST ingest now populates `component_key`
  for 27,811 / 27,811 INSTANCE nodes (100%). The supplement's per-
  INSTANCE `getMainComponentAsync()` call is no longer on the hot
  path — the rare swap-detection case is still covered by the
  light-slice walker.

- **#3 delivered but had to split.** A single unified walk of every
  Plugin field exceeds Figma's ~64KB PROXY_EXECUTE result buffer on
  moderate-sized screens. Solution: split into a "light" slice
  (small per-node payload) and a "heavy" slice (per-node transforms
  + per-vector geometries). Still 2 passes instead of 5; still a
  2.25× speedup on the Plugin-API stage (257s → 114s).

### Also landed in this chapter

- **Pipe-drain bug fix**: the old Node.js runner called
  `process.exit(0)` immediately after `console.log(JSON.stringify(msg))`.
  `process.exit()` does not wait for stdout to flush, and macOS
  pipes default to a 64KB buffer — any payload larger than that was
  silently truncated at the 64KB boundary. Replaced with
  `process.stdout.write(..., callback)` in both
  `_run_extract_supplement` and `_run_extract_plugin`. This was a
  latent bug affecting any sufficiently large supplement output.

- **Backoff jitter**: `_request_with_retry` now adds up to 50%
  jitter on the 429 backoff so concurrent workers don't synchronize
  their retry attempts and re-trip the limiter at the same tick.
  Retry budget raised from 5 → 8 attempts.

## Secondary improvements (lower priority)

4. **Daemonize Node.js/WebSocket** — currently every batch spawns a fresh
   `node -e` subprocess and opens a new WebSocket. At ~100ms startup × 41
   batches × 5 passes ≈ 20s of pure process overhead. Subsumed by #3 once
   the passes are consolidated.

5. **Parallel `process_screens`** — 24s is already fast; it's pure-CPU tree
   walk + binding creation. Multiprocessing could halve it. Low priority.

6. **Batch-size tuning** — supplement at size 5, others at size 10. Larger
   batches reduce overhead but risk script-size truncation (the auto-halve
   fallback on "Unterminated string" handles this). Worth trying size 25 on
   non-supplement passes after #3 is done.
