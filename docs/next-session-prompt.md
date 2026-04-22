# Continuation prompt — next session

Copy the section below into a fresh Claude conversation to resume M7.0.a (library population) execution.

---

I'm continuing work on the declarative-build design compiler. We're in the middle of **M7.0.a** — the library-population milestone of the M7 synthetic-generation plan (M7 is Priority 1 after the v0.3 Option B cutover completed 2026-04-19).

## Read these first, in order

1. **`docs/plan-synthetic-gen.md` §5.1.a + §5.1.b** — M7.0.a deep-dive with all decisions locked, and the 12-step execution plan for this session. **§5.1.b is your task list.**
2. **`memory/project_m7_0a_classification.md`** — session-boot summary; cross-references the plan doc.
3. **`memory/project_v0_3_plan.md`** — v0.3 state (complete; M6(a) shipped).
4. **`memory/project_system_overview.md`** — system overview.
5. **`CLAUDE.md`** — TDD non-negotiable; no production code without a failing test.

## What's decided (do NOT re-litigate)

The 2026-04-19 session made these decisions; they're locked:

- **Three-source classification architecture** (option c2). Formal + heuristic rules → LLM text (Haiku 4.5, tool-use) → vision per-screen (Sonnet 4.6, full-screen image + bboxes) → vision cross-screen (Sonnet 4.6, N=5 screens batched by `(device_class, skeleton_type)`).
- **All three sources persisted permanently.** `canonical_type` becomes a *computed consensus*, not a primary signal.
- **Consensus rule v1**: majority + `unsure` catch-all. Rule v2 bias-aware overrides deferred until real disagreement data exists.
- **Decode stack**: Claude tool-use for all LLM/vision work. Grammar-constrained decoding deferred to M7.5+.
- **Review workflow**: Tier 1.5 — CLI TUI for input + three visual layers (Figma deep-link, local PNG via `open`, inline terminal image if iTerm2/Kitty/Ghostty) + HTML companion page.
- **Spot-check audit** separate from review (`dd classify-audit --sample N`).
- **Cost envelope**: ~$35 for full 204-screen three-source cascade. Cheap enough that info loss from single-source collapse is the real cost.
- **Prompt rules v1 locked** (2026-04-19): `unsure` below 0.75; no `container`-regression when specific evidence exists; empty-grid → `skeleton`; decorative-child → `icon`.

## Where we are

**Shipped in the 2026-04-19 session:**
- `62be113` — component_key formal-match fallback
- `7c5da22` — LLM + vision stages rewritten with tool-use
- `46dee2d` — truncate / since-resume / progress_callback / `--limit` on `dd classify`
- `18f6b12` — `classification_reason` persistence (migration 011)
- `4e9d293` — cross-screen batched vision (`dd/classify_vision_batched.py`) + bake-off infrastructure + dry-run reports
- `b083243` — prompt tightening v1 + bake-off v2 (v1 74.4% → v2 76.9% agreement on 10 screens)
- `a2820fa` — M7.0.a decisions captured in plan §5.1.a

**Tests:** 107/107 classify tests pass. 204/204 corpus parity on v0.3 Option B walker.

## What you build this session

Follow `docs/plan-synthetic-gen.md` §5.1.b step-by-step. Twelve steps, TDD per CLAUDE.md, commits per-step. Rough order:

1. **Migration 012** — schema extension: three-source columns on `screen_component_instances` + `classification_reviews` table. Update `schema.sql`. Apply to Dank DB.
2. **Rename** `classification_reason` → `llm_reason` for clarity (migration preserves data).
3. **`dd/classify_consensus.py`** — pure-function consensus computation with rule v1. Unit tests cover every branch.
4. **Orchestrator update** — `dd/classify.py::run_classification` runs all three sources per screen, applies consensus, flags divergences.
5. **CLI flags** — `dd classify --three-source` wiring.
6. **`dd classify-review` CLI** — interactive TUI + three visual-reference layers.
7. **`dd classify-review-index` HTML** — scrollable companion page.
8. **`dd classify-audit`** — spot-check for all-agree rows.
9. **Full 204-screen cascade run** (~$35 budget). Log per-screen progress.
10. **`scripts/disagreement_report.py`** — markdown report with disagreement patterns.
11. **Manual review sprint** — user works through flagged queue.
12. **Rule v2 design** — encode bias-aware overrides from override patterns.

Steps 1–8 are pure code, TDD, no API costs. Step 9 is the big run. Steps 10–12 iterate on data.

## Infrastructure reminders

- `.env` at repo root has `ANTHROPIC_API_KEY` + `FIGMA_ACCESS_TOKEN`. Scripts load via direct assignment (not `setdefault`) — shell `ANTHROPIC_API_KEY=""` overrides otherwise.
- Python: `/Users/mattpacione/declarative-build/.venv/bin/python3` (has `anthropic`, `pytest`, etc.).
- DB: `Dank-EXP-02.declarative.db` at repo root.
- Figma Desktop Bridge on port 9228 for screen rendering + screenshots.
- Existing bake-off infrastructure: `scripts/vision_bakeoff.py`, `scripts/dry_run_10.py`, `scripts/preview_llm_classify_prompt.py`. Useful for probing tweaks.
- Vision calls use streaming (`max_tokens=32768`); SDK's long-request gate otherwise trips. See `dd/classify_vision_batched.py::classify_batch`.

## Cadence

User cadence preference: **B+D** — autonomous parallel execution with check-ins at judgment points. User is generally async but available for specific design decisions. Surface questions inline when you hit a real fork (prompt shape, migration schema, ambiguous rules, etc.). Don't ask for permission to do obvious work.

## Non-negotiables

- TDD per CLAUDE.md. Failing test first, always.
- All three sources persisted. Never collapse raw verdicts.
- Consensus recomputes from persisted data. Iterating on rule v2 must not require re-classification.
- 204/204 corpus parity preserved.

If you hit an unknown, surface it rather than guess. Start by reading the plan doc + memory; after that, begin Step 1.

---

Previous continuation material (pre-M7) is in `docs/continuation.md`. For the v0.3 Option B cutover thread specifically, see `memory/project_v0_3_plan.md` and commit `6377105`.
