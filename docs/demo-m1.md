# Demo M1 — Close the Figma Round-Trip

What this shows: an LLM writes dd-markup edits against a real screen, the
compiler renders both the original and the variant side-by-side on a new
Figma page. One command, one visible before/after.

## Pre-demo checklist

1. **Duplicate the Figma file before demoing.** Don't demo against the
   source of truth. The script creates a new page via
   `figma.createPage()` — non-destructive to existing pages — but any
   bug could still pollute the file. Belt-and-suspenders.
2. **Figma Desktop open** with the duplicated file as the active tab.
3. **figma-console-mcp bridge running.** It's spawned by Claude Desktop
   when that client is running with the patched MCP config. See
   `patches/figma-console-mcp-proxy-execute.patch`.
4. **Verify the bridge is actually listening.** It binds IPv6 `::1`,
   not IPv4 `127.0.0.1`, so clients that probe `127.0.0.1` will
   misreport "not listening" even when it is. Port may be 9224 or 9228
   — scan the 9223-9231 range:
   ```
   python3 -c "import socket; s=socket.create_connection(('localhost', 9228), timeout=0.5); print('OK')"
   ```
5. **`.env` has `ANTHROPIC_API_KEY` set.** Watch for a stale empty
   `ANTHROPIC_API_KEY=""` already exported in the shell — dotenv
   doesn't override already-set vars, so an empty one wins silently.
   Export explicitly (or `unset` the stale one) if the run dies with
   "anthropic client failed."
6. **Target a mid-complexity screen** (60-90 nodes, clean structure).
   Dank screen 333 (iPad Pro 11" - 43) is the validated safe choice.
   Append-heavy briefs are safer than substitutive ones — the
   swap-then-text residual is deferred (see
   `feedback_skipinvisible_findone_blindness.md`).

## The demo command

Init the session DB first (one-time per demo), then run the design
loop:

```
.venv/bin/python -c "from dd.db import init_db; init_db('/tmp/demo.db').close()"

.venv/bin/python -m dd design \
  --brief "Trim 1-2 small redundant decorative rectangles" \
  --starting-screen 333 \
  --project-db Dank-EXP-02.declarative.db \
  --db /tmp/demo.db \
  --max-iters 3 \
  --render-to-figma
```

## What the output should look like

Stdout prints the session ULID on its own line, then `iterations:`,
`halt:`, `final_variant:`, and finally:
```
→ rendered to Figma page 'design session <ULID prefix>'
```

In Figma, a new page by that name appears with two frames side-by-side:
original at `(0, 0)`, variant at `(screen_width + 200, 0)`.

## Expected runtime

15 seconds to ~4 minutes, depending on `--max-iters` and how chatty
Sonnet is. The capstone test clocks ~14s at 3 iters; a full Dank
session can hit 4m+ when Sonnet hits the iter cap.

## Known limitations

- **Swap-then-text residual on screen 333.** If the brief implies
  changing text, the swap path can produce mis-addressed text
  (deferred in the Stage 3 post-mortem). Pick appends over substitutions.
- **`dd design score` is a stub.** CLI accepts it, returns "deferred"
  (A2 per Codex/Sonnet sign-off).
- **Session DB needs `init_db` before first use** — this is a
  two-command demo, not one.
- **max-iters=3 is a subtle diff.** For a more visible "look what the
  agent did" moment, bump to 5-6 and write a brief implying more change.

## The guardrail (new 2026-04-24)

The CLI's render path passes `strict_mapping=0.9` to
`render_applied_doc`. If nid_map coverage drops below 90%, the CLI
exits 1 with a `DegradedMapping` error instead of rendering an empty
frame. This catches the class of bugs that made the live capstone
initially render blank. See commit `e596cbf`.

## If it goes wrong during the demo

- **"Empty variant frame"**: the wrapper-shape class is now caught
  by `DegradedMapping`. If the frame is empty and the CLI exited 0,
  it's a new class — check stderr first, then inspect
  `variant_rendered.script` for Mode-2 cheap-emit tell-tales
  (`createFrame()` with no fills/strokes set).
- **"Bridge connection refused"**: plugin not running. Restart Claude
  Desktop and wait ~15s for the MCP to rebind.
- **"Anthropic client failed"**: stale empty env var. Run
  `unset ANTHROPIC_API_KEY && .venv/bin/python -m dd design ...`
- **"screen 333 not found"**: wrong `--project-db` path. Check
  `Dank-EXP-02.declarative.db` exists at the repo root.

## Deeper context

- [`docs/rationale/stage-3-session-loop.md`](rationale/stage-3-session-loop.md)
  — why the session loop is Python-iterative, stateless Sonnet calls,
  move_log JSONL, and branching-falls-out-of-resume.
- [`ENTRYPOINT.md`](../ENTRYPOINT.md) — the Stage 0-3 throughline.
