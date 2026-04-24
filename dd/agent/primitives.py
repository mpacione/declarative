"""Stage 2 — agent primitives over FocusContext.

Per docs/plan-authoring-loop.md §2 + Codex 2026-04-23 fork: NAME /
DRILL / CLIMB are deterministic orchestrator entry points. They
take a FocusContext (and sometimes a doc/eid/prompt), perform
their structural action, and return a new FocusContext with the
move-log appended.

Stage 2.2 ships NAME + the JSONL writer (persistence stopgap until
Stage 3's SQL ``move_log`` table lands via migration 023).
Stage 2.3+ will extend this module with DRILL and CLIMB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dd.focus import FocusContext, MoveLogEntry, _find_node_by_eid


def name_subtree(
    focus: FocusContext,
    eid: str,
    description: str,
) -> FocusContext:
    """NAME primitive — tag a subtree with a semantic description.

    Pure metadata. Does NOT change the doc or the focus scope; only
    the move log gets a NAME entry. Per plan §2.1: "the agent
    announces 'this subtree is a product-showcase-section' for its
    own rationale tracking."

    NAME works on any eid in ``focus.root_doc``, regardless of
    current scope — the agent might want to label sibling subtrees
    while drilled into another. Raises ``ValueError`` if the eid
    isn't in the root doc (silent acceptance would let the LLM
    accumulate names on phantom nodes).
    """
    if _find_node_by_eid(focus.root_doc, eid) is None:
        raise ValueError(
            f"cannot NAME unknown eid {eid!r} (not in root doc)"
        )
    entry = MoveLogEntry(
        primitive="NAME",
        scope_eid=eid,
        payload={"description": description},
        rationale=None,
    )
    return focus.with_log_entry(entry)


def write_move_log_jsonl(
    focus: FocusContext,
    path: str | Path,
) -> None:
    """Persist ``focus.move_log`` as JSONL — one entry per line.

    Stage 2 stopgap. Stage 3's SQL ``move_log`` table (migration 023)
    consumes the same shape via :meth:`MoveLogEntry.to_dict`, so a
    Stage 2 .jsonl file is a forward-compatible artifact: bulk
    importing it into the future SQL table is a row-by-row insert,
    not a re-serialization.

    Empty log writes an empty file (atomic — caller can re-run
    without race-window inconsistency).
    """
    p = Path(path)
    if not focus.move_log:
        p.write_text("")
        return
    lines = [
        json.dumps(entry.to_dict(), separators=(",", ":"))
        for entry in focus.move_log
    ]
    p.write_text("\n".join(lines) + "\n")
