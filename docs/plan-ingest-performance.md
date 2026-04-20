# Plan — Ingest + Classification Performance (v0.1 of the ingest pipeline)

**Status:** SPEC — defer until M7.0 through M7.2 complete.
**Authored:** 2026-04-19.
**Scope:** makes M7.0.a (and M7.0.b/c, which share the API-call shape) usable for real project onboarding. Shipping v0.0 = "50 min + $35 per Figma file" is acceptable for our own use while building M7.1+ synthesis. It is NOT acceptable for shipping to a user.
**Trigger to revisit:** after M7.2 (first LLM-in-loop demo — component swap) lands AND before validating on a second Figma project.

---

## 1. The problem

The M7.0.a three-source classification cascade takes **~50 min and ~$35** on the Dank corpus (204 app screens). The cost scales roughly linearly with screen count and node density, so a richer project takes longer.

Current per-app-screen cost:
- Haiku LLM call: ~2–5 s
- Sonnet vision per-screen streaming: ~10–15 s
- Sonnet vision cross-screen contribution (amortized): ~10–15 s
- **Total: ~30 s per app screen, sequentially.**

This is **one-time cost per project**, not per-query. But for a first-time user:
- Ingest + normalize: seconds
- Classification: 30–60 min + $35
- Then the rest of the pipeline unlocks.

That 30–60 min wall is a product-grade blocker — M7.0.b (slot derivation) and M7.0.c (variant families) will each have their own API-call phase, compounding the wait.

**The "paid once, amortized" framing is honest but not sufficient.** The cost is paying for the compositional IR index that every downstream synth-gen feature depends on, so we can't skip it — but we can dramatically reduce it.

## 2. Non-goals

- Removing the API-call dependency entirely (the vision + LLM verdicts are the substrate of consensus).
- Changing the three-source architecture (preserve option c2 from `plan-synthetic-gen.md` §5.1.a).
- Changing the consensus rule surface (v1 / v2 rules remain; they read the same persisted columns).

## 3. The five levers (by impact × effort)

### Lever A — Parallelization (HIGHEST IMPACT)

**Current:** screens processed sequentially; per-screen stages (formal → heuristic → LLM → vision_ps) also sequential.

**Target:** `concurrent.futures.ThreadPoolExecutor(max_workers=N)` around the per-screen loop. Each worker owns its own `sqlite3.Connection`; a shared reentrant lock serialises the final DB writes (or per-worker connections + SQLite WAL + explicit transactions is even better — WAL allows concurrent readers, one writer).

**API rate-limit reality:**
- Anthropic rate-limits requests/min and tokens/min, varying by tier.
- Streaming Sonnet calls with `max_tokens=32768` are expensive on the tokens/min budget — not on the requests/min budget.
- Typical headroom at Scale tier: 100+ concurrent requests fine; might start throttling at 300+. At lower tiers, 3–5 concurrent is the safe ceiling.

**Design:**
- New flag: `dd classify --workers N` (default N=1 for backwards compat).
- Per-screen work (formal + heuristic + LLM + PS) goes into worker pool.
- CS still runs serially after per-screen phase because CS batches are interdependent (same group), but CS **batches** can run concurrently within the same phase (small additional thread pool).
- Consensus runs serially at the end (pure DB operation, fast).
- Structured error collection: each worker appends to a shared `errors: list[tuple[screen_id, exception]]` so one bad screen doesn't abort the run.

**Expected speedup:**
- N=5 workers → **10x** (50 min → ~5–7 min, Anthropic-rate-limited).
- N=10 workers → **~15x** (possibly rate-throttled on lower tiers).

**Effort:** ~1–2 days TDD'd. Primary risk is SQLite concurrency correctness + transient API errors.

**Acceptance criteria:**
- `dd classify --workers 5 --three-source --limit 20` produces identical DB state to `dd classify --workers 1 ...` on the same screens.
- Single screen failure (mock a transient API error) doesn't abort the run; recorded in a structured `errors.json` alongside the log.
- 50-min sequential run → ~10 min parallel at N=5.

### Lever B — Incremental re-classification

**Current:** `--truncate` wipes all classifications; full re-run. `--since SCREEN_ID` skips earlier screens but doesn't diff existing classifications against current node state.

**Target:** `dd classify --incremental` classifies only **new or changed** nodes since the last run.

**Design:**
- Introduce `node_classification_cache` table:
  - `node_id`, `classification_hash` (SHA of `name + type + layout_mode + depth + sort_order + parent_structural_shape`), `last_classified_at`.
- `--incremental` compares current-node hash to cached hash per node; only nodes with a mismatch (or missing cache entry) enter the cascade.
- Three-source columns (`llm_type`, `vision_ps_type`, `vision_cs_type`) are **preserved** for unchanged nodes — no re-API-call, no cost.
- Consensus re-runs across all rows on affected screens (cheap pure-function; needed so rule v2 updates reflect).
- `--force-rerun-on screen_id,screen_id` override for when the user explicitly wants to re-API-classify a specific screen (e.g., suspicious verdict; manual override lost).

**Dependency:** a hash function + cache table migration. Add `dd/classify_cache.py` module.

**Acceptance criteria:**
- First run: ~same cost as today (but parallelized per Lever A).
- Second run on the same corpus with no Figma changes: **< 30 s**, zero API calls.
- Adding 3 screens: ~10–20 s per new screen (plus CS recomputation for the affected batches).

**Effort:** ~2 days TDD'd.

### Lever C — Tiered workflow

**Current:** `--three-source` runs LLM + PS + CS on every candidate. You pay the full $35 / 50 min for every node regardless of confidence.

**Target:** layered passes.

**Design:**
1. **Fast pass (default):** formal + heuristic + LLM (Haiku). ~2–5 min, ~$3–$5. Produces a usable-but-unverified classification for every node.
2. **Vision pass on demand:** `dd classify --add-vision [--threshold 0.85]` runs vision PS + CS **only** on rows where LLM confidence < threshold (or `unsure`). Adds the verdicts incrementally; consensus recomputes.
3. **Full three-source:** current `--three-source` behaviour (runs vision on every LLM row) remains as `--three-source --vision-all`.

**Confidence threshold defaults:**
- LLM confidence ≥ 0.95 → single-source commit, no vision.
- LLM confidence 0.85–0.94 → vision PS only (no CS, the expensive one).
- LLM confidence < 0.85 or `unsure` → full three-source.

**Rationale:** on the dry-run (3 iPad screens), 70 LLM rows produced 48 unanimous (zero disagreement) + 21 majority (small disagreement on ambiguous structural nodes) + 1 three-way-disagreement. The unanimous 48 didn't need vision to commit. A threshold-gated pass would have skipped ~70% of vision calls with no information loss on the computed consensus.

**Acceptance criteria:**
- Default `dd classify` (no flags) completes in ~3–5 min for a fresh project (after Lever A) at ~$5 cost.
- `dd classify --add-vision --threshold 0.85` adds vision only where LLM was uncertain; costs ~$10–15 instead of $25+.
- Consensus reads work identically regardless of which tier produced the columns.

**Effort:** ~1 day (reuses existing infrastructure; mostly flag wiring + SQL conditions).

### Lever D — Model tuning

**Current:** Sonnet 4.6 for both vision PS and vision CS (max_tokens=32768 streaming).

**Target:** use Haiku 4.5 vision for the first vision pass; escalate to Sonnet 4.6 only when Haiku returns `unsure` or when the row was flagged by LLM/formal/heuristic mismatch.

**Model-cost delta:**
- Haiku 4.5 vision: ~4x faster per call, ~3x cheaper per token than Sonnet 4.6.
- Sonnet 4.6 still matters on ambiguous cases — its reasoning is meaningfully better.

**Design:**
- `classify_batch(..., model="claude-haiku-4-5-20251001")` already parameterised.
- New escalation function: rows where Haiku vision returned `unsure` or confidence < 0.75 get re-classified by Sonnet. Vision_ps_reason + confidence overwritten with Sonnet's verdict; evidence trail preserved in a `vision_ps_escalated_from_haiku` marker column (or a `vision_ps_model` string).

**Dependency:** separate Haiku + Sonnet model paths, selective escalation.

**Acceptance criteria:**
- Full three-source with Haiku-first falls under ~3x cheaper than Sonnet-only.
- Agreement rates with the pure-Sonnet baseline stay within ±5% on a dry-run comparison.

**Effort:** ~1–2 days.

### Lever E — Batch API (deferred)

**Reality check:** Anthropic's Batch API gives 50% cost discount but runs asynchronously over hours. Not useful for an interactive ingest flow. Dropped for now; revisit if/when weekly/nightly re-classification becomes a pattern.

## 4. Sequencing

The levers layer cleanly — each is independently shippable.

| Order | Lever | Expected speedup vs today |
|---|---|---|
| 1 | A — Parallelization | 50 min → ~8 min (`--workers 5`) |
| 2 | C — Tiered workflow | Default `dd classify` → ~3 min, $5 |
| 3 | B — Incremental cache | Second run (no changes) → <30 s |
| 4 | D — Model tuning | Cost → ~$10 for full three-source |

**Combined final state** for a second Figma project:
- First run: ~3–5 min, ~$5 (default Lever C fast pass).
- Opt-in full three-source: ~8 min, ~$10 (Levers A + C + D).
- Update run (adds 3 screens): ~10–20 s, <$0.50 (Lever B).

That's shippable.

## 5. What has to land first

**Hard prerequisites** (must be done before this plan starts):
- M7.0 complete — all six M7.0.{a..f} sub-tasks. The classification cascade IS M7.0.a, and M7.0.b/c reuse the same API-call infrastructure. Building the perf plan before they ship means redoing work when they extend the call graph.
- M7.1 (edit grammar) complete — same reason: new LLM call patterns emerge.
- M7.2 (S2.5 component swap LLM-in-loop demo) complete — first real user-facing use case; tells us which latencies actually matter.

**Soft prerequisites** (nice-to-have before starting):
- Bench harness that measures end-to-end wall time + cost per stage so we can verify speedups empirically. `scripts/m7_bench.py` would time a fixed 10-screen subset across lever variants.
- Rate-limit telemetry: observe actual Anthropic rate-limit errors on real runs so we size `--workers N` correctly.

## 6. Acceptance of this plan

This is a **deferred** plan — nothing ships against it until the trigger condition is met (M7.0, M7.1, M7.2 done). When it reactivates, the bars are:

1. Every lever has an independently-committed PR, TDD'd per CLAUDE.md.
2. 204/204 corpus parity preserved end-to-end.
3. Full three-source cascade on the Dank corpus completes in **under 10 min** at **under $15**.
4. Incremental run on an unchanged Dank DB completes in **under 30 s** with **zero** API calls.
5. Default `dd classify` (fast pass, no flags) completes on a new project in **under 5 min** at **under $5**.

When all five hit green, the ingest pipeline is v0.1 and shippable to a user onboarding their own Figma file.

## 7. Open questions (resolved on pickup, not now)

- What's the correct confidence threshold for auto-escalation to Sonnet vision? Empirical — set after a bench pass.
- Does the `classification_hash` shape need to include CKR membership (in case CKR changes between runs)? Probably yes; needs verification.
- SQLite + multi-thread write contention: single writer + WAL vs a write queue thread? Probably start with single writer and measure.
- When the LLM verdict is cached but PS/CS aren't yet run, does `--add-vision` target just those rows? Yes — the tier design in Lever C already handles this.
- What happens when Anthropic deprecates Haiku 4.5 / Sonnet 4.6? Model string is a single constant in each module — easy swap, but consensus recomputability still holds because we don't re-classify on rule-v2 updates.
