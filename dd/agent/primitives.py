"""Stage 2 — agent primitives over FocusContext.

Per docs/plan-authoring-loop.md §2 + Codex 2026-04-23 fork: NAME /
DRILL / CLIMB are deterministic orchestrator entry points. They
take a FocusContext (and sometimes a doc/eid/prompt), perform
their structural action, and return a new FocusContext with the
move-log appended.

Stage 2.2 ships NAME + the JSONL writer (persistence stopgap until
Stage 3's SQL ``move_log`` table lands via migration 023).
Stage 2.3 adds DRILL + drilled_propose_edits.
Stage 2.4 adds CLIMB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from dd.focus import FocusContext, MoveLogEntry, _find_node_by_eid, is_in_scope
from dd.markup_l3 import apply_edits, parse_l3
from dd.propose_edits import ProposeEditsResult, propose_edits


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


def drill(
    focus: FocusContext,
    eid: str,
    focus_goal: Optional[str] = None,
) -> FocusContext:
    """DRILL primitive — narrow the agent's focus into a subtree.

    Pure function. Returns a new FocusContext whose ``scope_eid`` is
    ``eid``; ``focus.doc`` will then return the extracted subtree
    (the LLM sees less). Doesn't itself call propose_edits — the
    caller follows up with ``drilled_propose_edits`` (or directly
    with ``propose_edits(focus.doc, ...)``) to act inside the new
    scope.

    Per Codex 2026-04-23 risk note: the resulting focus carries a
    DRILL move-log entry tagged with ``focus_goal`` so the agent's
    intent at drill-time is recoverable for replay / audit.

    Raises ``ValueError`` if ``eid`` isn't in the current scope —
    silent failure would cascade as "why doesn't the LLM see
    anything inside the new scope?".
    """
    drilled = focus.drilled_to(eid)  # validates scope membership
    entry = MoveLogEntry(
        primitive="DRILL",
        scope_eid=eid,
        payload={"focus_goal": focus_goal} if focus_goal else {"focus_goal": None},
        rationale=None,
    )
    return drilled.with_log_entry(entry)


def drilled_propose_edits(
    *,
    focus: FocusContext,
    drill_eid: str,
    focus_goal: Optional[str],
    prompt: str,
    client: Any,
    component_paths: list[str],
    **propose_kwargs: Any,
) -> tuple[FocusContext, ProposeEditsResult]:
    """DRILL + propose_edits in one call, with scope enforcement.

    The 2a mechanic chosen 2026-04-23: the LLM sees the SUB-doc, but
    the edit applies against the ROOT doc (so the change persists).
    Same edit-grammar source applies to both because eids are stable
    across the doc.

    Verifier hook: every applied edit is checked against
    ``is_in_scope(focus, target_eid)`` before being lifted to the
    root. If the LLM somehow names a node outside the drill scope,
    the edit is REJECTED (KIND_OUT_OF_SCOPE) and the root doc is
    untouched.

    Returns ``(new_focus, propose_result)``. On success ``new_focus``
    has root_doc=applied root + DRILL/EDIT log entries. On scope
    violation ``new_focus`` keeps the original root_doc + DRILL log
    entry (no EDIT entry — the edit didn't apply).
    """
    drilled = drill(focus, drill_eid, focus_goal=focus_goal)
    sub_result = propose_edits(
        doc=drilled.doc,
        prompt=prompt,
        client=client,
        component_paths=component_paths,
        **propose_kwargs,
    )
    if not sub_result.ok:
        return drilled, sub_result

    # Scope check: parse the proposed edit, find its target eid,
    # confirm it's in scope. (For multi-target verbs like move,
    # both target and dest must be in scope.)
    edit_doc = parse_l3(sub_result.edit_source)
    edits = list(edit_doc.edits)
    for stmt in edits:
        for attr in ("target", "to", "into", "from_", "anchor"):
            ref = getattr(stmt, attr, None)
            if ref is None:
                continue
            ref_eid = getattr(ref, "eid", None)
            if ref_eid is None:
                continue
            if not is_in_scope(drilled, ref_eid):
                violation = ProposeEditsResult(
                    ok=False,
                    tool_name=sub_result.tool_name,
                    edit_source=sub_result.edit_source,
                    rationale=sub_result.rationale,
                    applied_doc=drilled.doc,  # keep sub-doc unchanged
                    error_kind="KIND_OUT_OF_SCOPE",
                    error_detail=(
                        f"edit references eid {ref_eid!r} outside the "
                        f"DRILL scope {drilled.scope_eid!r}"
                    ),
                )
                return drilled, violation

    # Apply the same edit-source against the ROOT doc — eids are
    # stable so the edit is well-defined at root scope too.
    new_root = apply_edits(drilled.root_doc, edits)
    edit_entry = MoveLogEntry(
        primitive="EDIT",
        scope_eid=drilled.scope_eid,
        payload={
            "edit_source": sub_result.edit_source,
            "tool_name": sub_result.tool_name,
        },
        rationale=sub_result.rationale,
    )
    new_focus = FocusContext(
        root_doc=new_root,
        scope_eid=drilled.scope_eid,
        parent_chain=list(drilled.parent_chain),
        move_log=list(drilled.move_log) + [edit_entry],
    )
    # ProposeEditsResult.applied_doc is the SUB-doc post-edit; we
    # update it to the new root for caller convenience (so they can
    # use either doc depending on what they need).
    promoted = ProposeEditsResult(
        ok=sub_result.ok,
        tool_name=sub_result.tool_name,
        edit_source=sub_result.edit_source,
        rationale=sub_result.rationale,
        applied_doc=new_root,
        error_kind=None,
        error_detail=None,
    )
    return new_focus, promoted


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
