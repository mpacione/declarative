# declarative-build — project-level Claude instructions

> This file is loaded automatically at session start in this repo. Subagents
> spawned in this working directory inherit it. The user-global
> `~/.claude/CLAUDE.md` also applies; this file refines it for this codebase's
> specific tool surface and known failure modes.

## NEVER BLINDLY TRUST

This is the project's prime directive. Earlier sessions burned hours acting on
unverified subagent claims, stale plan citations, and assumptions about file
contents that were wrong. **Always verify, always double-check, always be
critical and question, always ask a subagent for a second opinion, always use
symbolic/AST search in addition to grep and other tools to help verify.**

A claim is not a fact until you have independently verified it. This applies
to: subagent and Codex output, MCP tool results, claims in plans / docs /
memory, file:line citations, "X exists / doesn't exist" assertions,
dead-code reports, and your own previous statements within the same session.

The full operational checklist lives in user-global `~/.claude/CLAUDE.md`
under `## Working with Claude → ### Verification (NEVER BLINDLY TRUST)`. Read
it. Apply it.

## Tool surface in this repo

### Symbolic / AST tools (PRIMARY for code questions)

`code-graph-mcp` is installed as a CLI on this machine. ripgrep is installed
(verify with `which rg`). When asking "does X exist?" / "where is X called?"
/ "what would break if I change X?" / "is this dead code?", **start with
code-graph-mcp, not grep**.

Practical commands (Bash tool):

```
code-graph-mcp ast-search "<query>" --type fn   # functions matching
code-graph-mcp grep "<pattern>" <path>          # AST-context grep
code-graph-mcp callgraph <symbol> --direction callers|callees|both --depth 3
code-graph-mcp refs <symbol>                    # find every reference
code-graph-mcp impact <symbol>                  # blast radius (use BEFORE editing)
code-graph-mcp dead-code <path>                 # orphaned + exported-unused
code-graph-mcp overview <path>                  # symbols grouped by file/type
code-graph-mcp map                              # project architecture map
code-graph-mcp show <symbol>                    # full code + signature
code-graph-mcp deps <file>                      # dependency graph
code-graph-mcp similar <symbol>                 # semantically similar code
code-graph-mcp health-check                     # index status
```

If `code-graph-mcp grep` returns "ripgrep (rg) not found", run `brew install
ripgrep` and retry. If callgraph returns empty for a function you can see, it
may be an intra-file call indexing gap — fall back to `refs` + `Read` rather
than concluding the function is orphaned.

### Codex MCP (`mcp__codex__codex`)

Available via the codex MCP server.

- **`gpt-5.5`** with `model_reasoning_effort: high` — thinking partner /
  architect / ship-gate. Singular per decision. Use for design forks, plan
  critique, architectural calls, ship/no-ship gates, multi-perspective
  synthesis. Do not burn it on mechanical tasks.
- **`gpt-5.4`** — mechanical Codex tasks. Plural; fan out for breadth. Use
  for "is this safe to delete," dependency-graph questions, sanity checks,
  basic refactor proposals, "find dead paths."
- **`gpt-5.5-pro` is NOT available on the ChatGPT account.** The MCP returns
  400 if requested. Don't.

When making any non-trivial architectural call, get a Codex second opinion.
The MoE-of-critics pattern (3-4 Sonnet subagents with distinct lenses + one
gpt-5.5 synthesis) is the canonical shape for hard decisions, not a
once-per-week treat.

### figma-console-mcp (`mcp__figma-console__*`)

The Figma plugin bridge. Tools include `figma_get_status`,
`figma_list_open_files`, `figma_execute` (run JS in Figma's plugin context),
plus design-creation helpers.

**Active port today is `9223`** (verify with `figma_get_status`); plan
documents that cite `9228` are stale. Bridge state:

- Connected file is whichever Figma file currently has the Desktop Bridge
  plugin open. **Always run `figma_get_status` or `figma_list_open_files`
  before assuming what file is connected** — the user may have switched.
- The "current page" is whatever the user is viewing. **Never switch pages
  programmatically** unless the user has authorized it. Read the current
  page; if you need a different page, ask first.
- `figma_execute` runs arbitrary JS — destructive operations are possible.
  Default-read; only mutate after explicit user authorization for the
  specific operation.
- Async return values from `figma.getNodeByIdAsync` etc. sometimes time out
  on 5s timeouts; use `timeout: 30000` on probe queries.

**Bridge truth beats REST truth.** If the REST API and the bridge disagree,
trust the bridge — REST `?depth=1` has been observed to return 0 children
on pages that the bridge sees as having dozens.

### Subagents

- `Explore` (Sonnet, all tools except edit/write) — codebase exploration.
- `Plan` — architectural design.
- `general-purpose` (all tools) — multi-step research / search.
- Dispatch specifying `subagent_type`. For code-investigation work, the
  prompt MUST tell the subagent to use code-graph-mcp as primary tool per
  this CLAUDE.md.

### Other tools available

- Built-in: `Bash`, `Read`, `Edit`, `Write`, `WebFetch`, `WebSearch`, `TodoWrite`, `Agent`.
- The `dd` Python CLI is the project's main interface. `.venv/bin/python -m
  dd <subcommand> --help` for any subcommand.

## Project state — summary as of 2026-04-25

(This section is point-in-time; verify against current `git log` and
`ENTRYPOINT.md` before relying on it.)

- Branch `v0.3-integration` (tip ~`102176a`) is the active branch.
- 116 Python files in `dd/`, ~50K LOC, 3578 tests collected, 142 test files.
- The two main user commands: `dd extract <figma-file>` and `dd design --brief`.
- The compiler's parse-render boundary (`dd/markup_l3.py`,
  `dd/compress_l3.py`, `dd/render_figma_ast.py`, `dd/renderers/figma.py`,
  `dd/compose.py`) has known cyclic imports and concentrated complexity.
- A v0.4 IR refactor is in `docs/plan-v0.4.md` but Phase 0 audits surfaced
  drift between the plan and real code; do not treat the plan as
  authoritative without verification.
- `Dank-EXP-02.declarative.db` at the repo root is the primary corpus. Do
  not run `dd cluster` against it without first snapshotting to
  `archive/db-snapshots/`.

## Known failure modes — do not repeat

These are documented failures from prior sessions. Each is a concrete
cautionary example of "claim accepted without verification."

1. **Pseudo-verb names in plan docs.** Plans cited `emit_drill`,
   `emit_set_edit`, `emit_done`, `emit_climb`, `emit_name`. None exist. The
   real verbs in `dd/structural_verbs.py` are `set / delete / append /
   insert / move / swap / replace`. Verify with
   `code-graph-mcp ast-search "build_.*_tool_schema" --type fn` before
   referencing any verb name from a plan.

2. **Wrong file for the KIND taxonomy.** Plans cited `dd/verify_figma.py`;
   actual location is `dd/boundary.py` (34 KIND constants, lines 32-131).
   `verify_figma.py` imports from `boundary`. Verify with
   `code-graph-mcp grep "^KIND_" dd/`.

3. **"Dead code at line 904."** Plans called
   `dd/renderers/figma.py:904` "dead Mode-3 code." It's live code in the
   active `_emit_override_tree` override walk. Verify with
   `code-graph-mcp callgraph _emit_override_tree --direction callers`
   before calling anything dead.

4. **Subagent claimed a file doesn't exist.** A round-1 audit reported
   `dd/ast_to_element.py` doesn't exist. It exists (13KB, real). Always
   `ls` the cited path before passing the claim through to synthesis.

5. **Empty SQL `tokens` table read as "no design system."** The table is
   empty pre-cluster by design. The actual design system in some files
   lives in hand-authored Figma Variables (374 vars, 8 collections in
   `Dank Experimental`). Probe via the bridge
   (`figma.variables.getLocalVariableCollectionsAsync()`) before concluding
   token state.

6. **`dd/markup.py` (the original) vs `dd/markup_l3.py` (the spine).** Two
   files with similar names; one is dead, the other is the
   most-load-bearing module in the codebase (4502 LOC, parser, 28 tests).
   Never recommend deletion of either without
   `code-graph-mcp refs dd.markup` AND `code-graph-mcp refs dd.markup_l3`
   AND a Codex second opinion.

7. **REST `?depth=1` returned 0 children for pages that have 44 + 124
   children.** Trust the bridge over REST for fresh-file inspection.

8. **Page switch without authorization.** A subagent ran
   `figma.setCurrentPageAsync(...)` to inspect a different page, which
   navigated the user's open Figma session away from where they were
   working. Never switch pages programmatically unless the user has
   explicitly authorized that specific operation.

## Tool-discipline default

For any code investigation task in this repo, the default tool order is:

1. `code-graph-mcp` (AST/symbolic) for "what exists, what calls what, what
   would break"
2. `code-graph-mcp grep` or `rg` for text search
3. `Read` for actual file content
4. Subagent / Codex second opinion before any non-trivial conclusion

If you find yourself reaching for plain `grep -rn` as the first move on a
code question in this repo, stop and ask whether `code-graph-mcp` answers it
better. The answer is usually yes.

## Conventions inherited from user-global

The user-global `~/.claude/CLAUDE.md` carries TDD discipline, TypeScript
style rules, and the broader "Working with Claude" expectations. They apply
here, with the obvious caveat that this codebase is Python, not TypeScript —
read the spirit (test-first, behavior-not-implementation, schema-as-truth)
not the literal language hooks.

The user-global `### Verification (NEVER BLINDLY TRUST)` section is the
operational checklist for the prime directive at the top of this file. Read
it.
