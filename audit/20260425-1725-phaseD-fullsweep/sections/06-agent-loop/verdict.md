# Section 06-agent-loop — verdict (Phase D)

**Verdict:** WORKS-CLEAN

## Summary
Section 6 (Agent loop, real Sonnet) — WORKS-CLEAN, all 3 briefs exit 0. Wall times: brief 1 = 8.92s, brief 2 = 9.38s, brief 3 = 9.40s. All 3 sessions persisted (3 design_sessions, 13 move_log entries, 14 variants).

- Brief 1 (Login Splash, simple delete): 4 iter, halt=`max_iters`, 4 `delete @line-{2,3,4} / @vector-23` edits with sensible "decorative shape, removing to minimize" rationales.
- Brief 2 (Transactions, variant edit): 4 iter, halt=`done`, NAME `component-54` + DRILL into it + EDIT `set @component-54 variant=secondary` + DONE.
- Brief 3 (Login Splash, append): 4 iter, halt=`max_iters`, EDIT `replace @logo-hgb-light { text #forgot-password-link "Forgot password?" }` + EDIT `set @forgot-password-link label="Forgot password?"` + NAME `forgot-password-link` + EDIT `move @line-3 to=@logo-hgb-light position=last`.

**TokenRef syntax not exercised in this Phase D run.** Phase B brief 3 happened to emit `set color={color.border.15}` (TokenRef brace form, F3 end-to-end signal). Phase D brief 3 chose a different solution path (replace + set label= + move) — non-deterministic LLM output. Direct DB query of all 14 variants' `markup_blob` and all 12 move_log `edit_source` fields shows zero `color={...}` matches. F3 was not regressed (the parser/compressor changes are unchanged in source); the agent simply did not pick a TokenRef-shaped edit on this run. The agent loop and all 3 primitives (NAME / DRILL / EDIT / DONE) demonstrably work end-to-end.

## Evidence
- `audit/20260425-1725-phaseD-fullsweep/sections/06-agent-loop/brief{1,2,3}-*.{exit-code,stdout,stderr}.txt` — all exit 0
- DB query (`audit-fresh.declarative.db`, sessions `01KQ3JYPP5...`, `01KQ3JYZDD...`, `01KQ3JZ8HP...`): 4 moves per session; primitives `EDIT`/`NAME`/`DRILL`/`DONE`; 14 variants total across 3 sessions; status=open
- DB grep across recent 100 variants for `color={`, `={color`, `"{color`: 0 matches (TokenRef path not exercised by LLM choices this run; not a regression)
