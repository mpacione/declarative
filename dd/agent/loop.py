"""Stage 3.3 — agent session-loop orchestrator.

Per Codex+Sonnet 2026-04-23 unanimous picks:
- B2 (Python iteration loop, stateless calls — matches Stage 1+2
  pattern; replayable per-iter).
- A2 + cheap per-turn structural score for stop signal (no
  render in loop; full render+VLM deferred to ``dd design score``).
- Convergence: hard cap + explicit DONE tool + stall detector.
- Persist the tree, not the conversation (LangGraph / AB-MCTS /
  Cline-Aider pattern from the lit-review; the DB is the truth,
  prompts reconstruct from path).

The loop wires together:

- Stage 1's ``propose_edits`` (7 edit verbs)
- Stage 2's ``name_subtree`` / ``drill`` / ``climb`` primitives
- Stage 3.2's ``dd/sessions.py`` persistence layer (sessions /
  variants / move_log)
- A new ``emit_done`` tool the agent can call to signal completion

Public entry point::

    run_session(
        conn, *, brief=None, parent_variant_id=None,
        client, model="claude-sonnet-4-6", max_iters=10,
        component_paths=(), starting_doc=None,
    ) -> SessionRunResult

Either ``brief`` (new session) OR ``parent_variant_id`` (resume /
branch) must be supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from dd.agent.primitives import climb, drill, name_subtree
from dd.focus import FocusContext, MoveLogEntry
from dd.markup_l3 import L3Document, parse_l3
from dd.propose_edits import (
    ProposeEditsResult,
    build_propose_edits_tools,
    parse_tool_call_to_edit,
    propose_edits as _stage1_propose_edits,
)
from dd.sessions import (
    append_move_log_entry,
    create_session,
    create_variant,
    load_variant,
)
from dd.structural_verbs import existing_eids


_DEFAULT_MODEL = "claude-sonnet-4-6"
_STALL_WINDOW = 3  # iters of no structural change → halt


# --------------------------------------------------------------------------- #
# Result shape                                                                #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SessionRunResult:
    """Outcome of one ``run_session`` call.

    ``halt_reason`` is one of: ``"done"`` (agent or implicit),
    ``"max_iters"``, ``"stalled"``, ``"all_failed"``.
    """
    session_id: str
    final_variant_id: str
    iterations: int
    halt_reason: str
    move_log_summary: list[str]


# --------------------------------------------------------------------------- #
# Tool registry                                                               #
# --------------------------------------------------------------------------- #

def _emit_name_subtree_schema(eids: list[str]) -> dict[str, Any]:
    return {
        "name": "emit_name_subtree",
        "description": (
            "NAME a subtree with a semantic description (e.g. 'product "
            "showcase section'). Pure metadata — doesn't change the "
            "doc, only the move log. Useful when you've identified a "
            "meaningful region you may want to drill into later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eid": {"type": "string", "enum": eids},
                "description": {
                    "type": "string", "minLength": 1, "maxLength": 200,
                },
            },
            "required": ["eid", "description"],
        },
    }


def _emit_drill_schema(eids: list[str]) -> dict[str, Any]:
    return {
        "name": "emit_drill",
        "description": (
            "DRILL into a subtree to scope subsequent edits. After "
            "this turn, you'll see only the named subtree as your "
            "context. Use ``emit_climb`` to pop back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eid": {"type": "string", "enum": eids},
                "focus_goal": {
                    "type": "string", "minLength": 1, "maxLength": 200,
                    "description": "Why you're drilling — for the move log.",
                },
            },
            "required": ["eid", "focus_goal"],
        },
    }


def _emit_climb_schema() -> dict[str, Any]:
    return {
        "name": "emit_climb",
        "description": (
            "CLIMB back out of a drilled subtree. Pops one level of "
            "scope. No-op at root scope."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {
                    "type": "string", "minLength": 1, "maxLength": 200,
                },
            },
            "required": ["rationale"],
        },
    }


def _emit_done_schema() -> dict[str, Any]:
    return {
        "name": "emit_done",
        "description": (
            "DONE — signal that the design is complete and no further "
            "edits are needed. Stops the loop cleanly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {
                    "type": "string", "minLength": 1, "maxLength": 280,
                    "description": "Why you're calling it done.",
                },
            },
            "required": ["rationale"],
        },
    }


def build_loop_tools(
    doc: L3Document,
    component_paths: list[str],
) -> list[dict[str, Any]]:
    """Assemble the full tool list the loop registers per turn.

    Reuses ``propose_edits``'s 7 verb schemas (built per-doc from the
    current eid set), adds the three focus primitives + DONE.
    """
    tools = list(build_propose_edits_tools(doc, component_paths))
    eids = sorted(existing_eids(doc))
    if eids:
        tools.append(_emit_name_subtree_schema(eids))
        tools.append(_emit_drill_schema(eids))
    tools.append(_emit_climb_schema())
    tools.append(_emit_done_schema())
    return tools


# --------------------------------------------------------------------------- #
# Cheap structural score (Codex's hybrid amendment)                            #
# --------------------------------------------------------------------------- #

def cheap_structural_score(
    *,
    pre_doc: L3Document,
    post_result: ProposeEditsResult,
) -> dict[str, Any]:
    """Per-turn structural score — no render, no VLM. Used as the
    stop signal (stall detector). A2's deferred render+VLM scoring
    runs separately via ``dd design score``.

    Signals:
    - ``edit_applied`` — did the propose_edits call succeed?
    - ``change_magnitude`` — eids added/removed by this turn (pure
      structural delta; doesn't catch semantic-only edits like
      a property set).
    - ``out_of_scope`` — count of eids in the post-doc that weren't
      in the pre-doc OR were dropped (used by stall detector to
      decide if "no change" really means no change).
    """
    if not post_result.ok:
        return {
            "edit_applied": False,
            "change_magnitude": 0,
            "out_of_scope": 0,
        }
    pre_eids = existing_eids(pre_doc)
    post_eids = existing_eids(post_result.applied_doc)
    added = post_eids - pre_eids
    removed = pre_eids - post_eids
    return {
        "edit_applied": True,
        "change_magnitude": len(added) + len(removed),
        "out_of_scope": 0,
    }


# --------------------------------------------------------------------------- #
# Helpers — building Sonnet's user message + dispatching one tool             #
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = (
    "You are a UI design agent. The user has a design brief and you "
    "iterate on a tree of UI elements one edit at a time using the "
    "tools provided. Tools include 7 edit verbs (set / delete / "
    "append / insert / move / swap / replace) plus three focus "
    "primitives (name_subtree / drill / climb) and an explicit "
    "emit_done tool. Call exactly ONE tool per turn. When the design "
    "is complete and no further edits are needed, call emit_done."
)


def _empty_starting_doc() -> L3Document:
    """Default doc for SYNTHESIZE mode (brief without starting_doc)."""
    return parse_l3("screen #screen-root\n")


def _build_user_message(
    *,
    brief: str,
    focus: FocusContext,
    iteration: int,
    max_iters: int,
    recent_log_summary: list[str],
) -> str:
    """Construct the per-turn user message for Sonnet.

    Per Codex's risk note (context bloat): pass the focused subtree
    (focus.doc) and a compact recent-log summary, NOT the entire
    root doc each turn.
    """
    from dd.markup_l3 import emit_l3
    parts = [
        f"### Brief\n{brief}",
        f"\n### Iteration {iteration} / {max_iters}",
        f"\n### Current scope\n```dd\n{emit_l3(focus.doc)}\n```",
    ]
    if recent_log_summary:
        parts.append(
            "\n### Recent moves (most recent last)\n"
            + "\n".join(f"- {line}" for line in recent_log_summary[-6:])
        )
    parts.append(
        "\nPick ONE tool to call. When complete, call emit_done."
    )
    return "\n".join(parts)


def _move_log_summary_lines(log: list[MoveLogEntry]) -> list[str]:
    """Compact one-line-per-entry summary for the prompt."""
    out = []
    for e in log:
        bits = [e.primitive]
        if e.scope_eid:
            bits.append(f"@{e.scope_eid}")
        if e.payload:
            for k, v in e.payload.items():
                if isinstance(v, str) and v:
                    bits.append(f"{k}={v[:40]}")
        out.append(" ".join(bits))
    return out


# --------------------------------------------------------------------------- #
# Per-turn dispatch                                                           #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _TurnOutcome:
    """What happened on one turn — drives persistence + stall check."""
    primitive: str
    edit_source: Optional[str]
    rationale: Optional[str]
    new_focus: FocusContext
    score: dict[str, Any]
    did_edit: bool   # True if the doc actually changed
    is_done: bool    # True if the agent called emit_done
    halt_no_tool: bool  # True if the LLM emitted no tool_use


def _dispatch_one_tool_call(
    *,
    focus: FocusContext,
    tool_block: Any,
    component_paths: list[str],
    client: Any,
    model: str,
) -> _TurnOutcome:
    """Apply one tool_use block. Returns a _TurnOutcome.

    For edit verbs we delegate to the per-verb edit-grammar
    lowering (propose_edits's parse_tool_call_to_edit) and apply
    against the current ROOT doc — eids stable across the doc per
    Stage 2's 2a mechanic. For NAME / DRILL / CLIMB we route to
    the focus primitives. emit_done sets is_done.
    """
    name = tool_block.name
    inp = dict(tool_block.input or {})
    rationale = inp.get("rationale")

    if name == "emit_done":
        return _TurnOutcome(
            primitive="DONE", edit_source=None, rationale=rationale,
            new_focus=focus,
            score={"edit_applied": True, "change_magnitude": 0,
                   "out_of_scope": 0},
            did_edit=False, is_done=True, halt_no_tool=False,
        )

    if name == "emit_name_subtree":
        new_focus = name_subtree(focus, inp["eid"], inp["description"])
        return _TurnOutcome(
            primitive="NAME", edit_source=None, rationale=None,
            new_focus=new_focus,
            score={"edit_applied": True, "change_magnitude": 0,
                   "out_of_scope": 0},
            did_edit=False, is_done=False, halt_no_tool=False,
        )

    if name == "emit_drill":
        new_focus = drill(focus, inp["eid"], focus_goal=inp.get("focus_goal"))
        return _TurnOutcome(
            primitive="DRILL", edit_source=None, rationale=None,
            new_focus=new_focus,
            score={"edit_applied": True, "change_magnitude": 0,
                   "out_of_scope": 0},
            did_edit=False, is_done=False, halt_no_tool=False,
        )

    if name == "emit_climb":
        new_focus = climb(focus)
        return _TurnOutcome(
            primitive="CLIMB", edit_source=None, rationale=None,
            new_focus=new_focus,
            score={"edit_applied": True, "change_magnitude": 0,
                   "out_of_scope": 0},
            did_edit=False, is_done=False, halt_no_tool=False,
        )

    # Otherwise: an edit verb. Lower to source, apply against the
    # ROOT doc (Stage 2's 2a mechanic), persist as new variant.
    try:
        edit_source = parse_tool_call_to_edit(name, inp, doc=focus.doc)
    except (KeyError, ValueError) as e:
        # Defensive — schema enum should prevent this, but if the
        # mock LLM hands us garbage, surface it as a non-edit turn.
        from dd.propose_edits import ProposeEditsResult
        result = ProposeEditsResult(
            ok=False, tool_name=name, edit_source=None,
            rationale=rationale, applied_doc=focus.root_doc,
            error_kind="KIND_PARSE_FAILED", error_detail=str(e),
        )
        return _TurnOutcome(
            primitive="EDIT", edit_source=None, rationale=rationale,
            new_focus=focus,
            score=cheap_structural_score(
                pre_doc=focus.root_doc, post_result=result,
            ),
            did_edit=False, is_done=False, halt_no_tool=False,
        )

    from dd.markup_l3 import apply_edits
    try:
        edit_doc = parse_l3(edit_source)
        new_root = apply_edits(focus.root_doc, list(edit_doc.edits))
    except Exception as e:  # noqa: BLE001
        from dd.propose_edits import ProposeEditsResult
        result = ProposeEditsResult(
            ok=False, tool_name=name, edit_source=edit_source,
            rationale=rationale, applied_doc=focus.root_doc,
            error_kind="KIND_APPLY_FAILED", error_detail=str(e),
        )
        return _TurnOutcome(
            primitive="EDIT", edit_source=edit_source, rationale=rationale,
            new_focus=focus,
            score=cheap_structural_score(
                pre_doc=focus.root_doc, post_result=result,
            ),
            did_edit=False, is_done=False, halt_no_tool=False,
        )

    from dd.propose_edits import ProposeEditsResult
    result = ProposeEditsResult(
        ok=True, tool_name=name, edit_source=edit_source,
        rationale=rationale, applied_doc=new_root,
    )
    new_focus = FocusContext(
        root_doc=new_root,
        scope_eid=focus.scope_eid,
        parent_chain=list(focus.parent_chain),
        move_log=list(focus.move_log),
    )
    return _TurnOutcome(
        primitive="EDIT", edit_source=edit_source, rationale=rationale,
        new_focus=new_focus,
        score=cheap_structural_score(
            pre_doc=focus.root_doc, post_result=result,
        ),
        did_edit=True, is_done=False, halt_no_tool=False,
    )


def _no_tool_outcome(focus: FocusContext) -> _TurnOutcome:
    """Agent emitted no tool block — treat as implicit done (per
    plan's 'least-surprising UX' Codex amendment)."""
    return _TurnOutcome(
        primitive="DONE", edit_source=None,
        rationale="agent emitted no tool call",
        new_focus=focus,
        score={"edit_applied": True, "change_magnitude": 0,
               "out_of_scope": 0},
        did_edit=False, is_done=False, halt_no_tool=True,
    )


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #

def run_session(
    conn,
    *,
    brief: Optional[str] = None,
    parent_variant_id: Optional[str] = None,
    client: Any,
    model: str = _DEFAULT_MODEL,
    max_iters: int = 10,
    component_paths: tuple[str, ...] = (),
    starting_doc: Optional[L3Document] = None,
    progress_stream: Optional[Any] = None,
) -> SessionRunResult:
    """Run one design session as an iteration loop.

    Either ``brief`` (new session, SYNTHESIZE mode) OR
    ``parent_variant_id`` (resume / branch) must be supplied.

    Per Codex's risk on context bloat: each per-turn user message
    carries the FOCUSED subtree + a compact recent-move-log summary,
    NOT the full root doc.

    When ``progress_stream`` is a file-like (the CLI passes
    ``sys.stderr``), emits a ``[iter N/M] ...`` heartbeat at the
    start of each iteration so a multi-minute demo run visibly
    advances instead of looking hung. Silent by default — library
    callers that capture stdio are unaffected.
    """
    if not brief and not parent_variant_id:
        raise ValueError(
            "must supply either `brief` (new session) or "
            "`parent_variant_id` (resume/branch)"
        )

    # ── Bootstrap ────────────────────────────────────────────────────────
    if parent_variant_id:
        parent = load_variant(conn, parent_variant_id)
        if parent is None:
            raise ValueError(
                f"parent_variant_id {parent_variant_id!r} not found"
            )
        session_id = parent.session_id
        starting = parent.doc
        # Resume brief from the existing session row (read it back).
        sess_row = conn.execute(
            "SELECT brief FROM design_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        active_brief = sess_row["brief"] if sess_row else (brief or "")
    else:
        session_id = create_session(conn, brief=brief)
        starting = starting_doc if starting_doc is not None else _empty_starting_doc()
        active_brief = brief
        # Persist a root variant snapshot so the loop's first variant
        # has something to point parent_id at.
        parent_variant_id = create_variant(
            conn, session_id=session_id, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=starting,
        )

    focus = FocusContext.root(starting)
    last_variant_id = parent_variant_id
    halt_reason: Optional[str] = None
    iterations = 0
    # Stall window tracks "iters where an EDIT verb was attempted but
    # did NOT successfully apply". A successful `set` that only
    # changes a property (no eid delta) is still productive work and
    # must NOT count toward stall — measuring structural eid-delta
    # halts any styling-only or append-then-style flow at iter 3.
    recent_edit_unproductive: list[bool] = []
    recent_failures: list[bool] = []
    move_log_summary: list[str] = []

    # ── Loop ────────────────────────────────────────────────────────────
    for i in range(1, max_iters + 1):
        iterations = i
        if progress_stream is not None:
            # Heartbeat: one line per iter. Includes the focus eid
            # so a multi-primitive session visibly shifts scope as
            # the agent DRILLs in. Written before the Anthropic
            # call so the user sees activity the moment latency
            # begins.
            try:
                print(
                    f"[iter {i}/{max_iters}] focus=@{focus.scope_eid} ...",
                    file=progress_stream, flush=True,
                )
            except Exception:
                # Don't let a broken stream abort a demo run.
                pass
        tools = build_loop_tools(focus.doc, list(component_paths))
        user_msg = _build_user_message(
            brief=active_brief or "",
            focus=focus,
            iteration=i,
            max_iters=max_iters,
            recent_log_summary=move_log_summary,
        )
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0.0,
            system=_SYSTEM_PROMPT,
            tools=tools,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_msg}],
        )
        tool_blocks = [
            b for b in (resp.content or [])
            if getattr(b, "type", None) == "tool_use"
        ]

        if not tool_blocks:
            outcome = _no_tool_outcome(focus)
        else:
            # Codex Stage 1.2 risk: enforce one tool per turn. If
            # the LLM emits multiple, take the first and warn (the
            # session loop should be more tolerant than propose_edits's
            # hard-fail since we have many turns to recover).
            outcome = _dispatch_one_tool_call(
                focus=focus, tool_block=tool_blocks[0],
                component_paths=list(component_paths),
                client=client, model=model,
            )

        # Persist the outcome.
        focus = outcome.new_focus
        if outcome.is_done or outcome.halt_no_tool:
            # A DONE doesn't create a new variant snapshot — the prior
            # variant is already the final state. But we DO log it.
            entry = MoveLogEntry(
                primitive="DONE",
                scope_eid=focus.scope_eid,
                payload={"halt_no_tool": outcome.halt_no_tool},
                rationale=outcome.rationale,
            )
            append_move_log_entry(
                conn, session_id=session_id,
                variant_id=last_variant_id, entry=entry,
            )
            move_log_summary.append(
                f"DONE rationale={(outcome.rationale or '')[:40]}"
            )
            halt_reason = "done"
            break

        # NAME / DRILL / CLIMB / EDIT all become a variant + log entry.
        new_vid = create_variant(
            conn,
            session_id=session_id,
            parent_id=last_variant_id,
            primitive=outcome.primitive,
            edit_script=outcome.edit_source,
            doc=focus.root_doc,
            notes=outcome.rationale,
        )
        last_variant_id = new_vid

        # The focus primitive paths (NAME/DRILL/CLIMB) emit log
        # entries onto focus.move_log internally; the EDIT path
        # doesn't. Persist whatever was produced PLUS an explicit
        # entry for EDIT.
        if outcome.primitive == "EDIT":
            entry = MoveLogEntry(
                primitive="EDIT",
                scope_eid=focus.scope_eid,
                payload={
                    "edit_source": outcome.edit_source,
                    "tool_name": "edit_verb",
                },
                rationale=outcome.rationale,
            )
            append_move_log_entry(
                conn, session_id=session_id,
                variant_id=new_vid, entry=entry,
            )
        else:
            # NAME / DRILL / CLIMB — copy whatever the focus primitive
            # appended onto its move_log to the SQL log.
            if focus.move_log:
                latest = focus.move_log[-1]
                append_move_log_entry(
                    conn, session_id=session_id,
                    variant_id=new_vid, entry=latest,
                )

        # Update summary for next-turn's prompt.
        if outcome.edit_source:
            move_log_summary.append(
                f"{outcome.primitive} {outcome.edit_source[:60]}"
            )
        else:
            move_log_summary.append(outcome.primitive)

        # Stall + all-failed detector.
        #
        # A turn is "unproductive" only when the AGENT attempted an
        # EDIT verb AND the apply failed. A successful `set` edit —
        # which changes a property but no eids — is productive work
        # and resets the stall window. NAME / DRILL / CLIMB are
        # structurally zero-change by design so they don't feed the
        # window at all (they neither advance nor stall it).
        is_edit_turn = outcome.primitive == "EDIT"
        is_edit_unproductive = (
            is_edit_turn and not outcome.score["edit_applied"]
        )
        recent_failures.append(not outcome.score["edit_applied"])
        if is_edit_turn:
            recent_edit_unproductive.append(is_edit_unproductive)
        if len(recent_failures) >= _STALL_WINDOW and all(
            recent_failures[-_STALL_WINDOW:]
        ):
            halt_reason = "all_failed"
            break
        if len(recent_edit_unproductive) >= _STALL_WINDOW and all(
            recent_edit_unproductive[-_STALL_WINDOW:]
        ):
            halt_reason = "stalled"
            break

    if halt_reason is None:
        halt_reason = "max_iters"

    return SessionRunResult(
        session_id=session_id,
        final_variant_id=last_variant_id,
        iterations=iterations,
        halt_reason=halt_reason,
        move_log_summary=move_log_summary,
    )
