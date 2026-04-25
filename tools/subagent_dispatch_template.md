# Subagent dispatch template — v0.4 execution

Every subagent dispatch during v0.4 work MUST start with the
prelude below. Copy-paste into the dispatch prompt verbatim.
Reason: per plan §9 ("Plan-version pinning"), if the plan
mutates between dispatch and review, A and B work on different
versions silently. The coordinator pins the hash; the subagent's
first action is to re-read the plan at that hash.

---

## Pinned plan revision (REPLACE EACH SESSION)

**Pinned commit-hash for `docs/plan-v0.4.md`**: `e1c6254`
(plan v3.1 — corpus-aligned demo anchors, 2026-04-25)

**Subagent first actions** (do these before answering anything):

1. `cd /Users/mattpacione/declarative-build`
2. `git show e1c6254:docs/plan-v0.4.md | wc -l` — confirm the
   pinned plan exists at that hash. If `wc -l` returns < 2200
   lines, the hash is wrong; STOP and ask the coordinator.
3. Read the plan at the pinned hash (`git show e1c6254:docs/plan-v0.4.md`)
   and proceed against IT, not the working-tree copy. The
   working-tree version may have drifted in this session.
4. If you write code or edits, do them against the working tree
   (HEAD); only the plan READ is at the pinned hash.

## How to update this hash

The coordinator (the main session) updates this hash whenever a
plan-edit commit lands. Bump the hash; bump the version note;
add a one-line history entry below.

## Hash history

- `e1c6254` (2026-04-25, plan v3.1) — Phase 0 W0.A demo
  anchor repoint (333/333/118/311 with auto-named tokens
  from `dd cluster`).
- `cbfb5eb` (2026-04-25, plan v3) — initial v3 plan with
  Phase-0 Day-1 runbook, gate metric commands, enum-size
  bounds, cost authorization, interim demo logistics.
