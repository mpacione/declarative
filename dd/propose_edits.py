"""Stage 1.2 — unified propose_edits orchestrator.

Wraps all 7 verb tool schemas (built by ``dd.structural_verbs``) into
one entry point the LLM uses to emit a single edit against the
current tree state.

**The three starting-IR modes** (per docs/plan-authoring-loop.md
Stage 1.3) all use the same contract — only the ``doc`` argument
differs:

- **SYNTHESIZE** — pass an empty doc (e.g. ``parse_l3("screen
  #screen-root\\n")``). The LLM proposes appends to build a screen
  from scratch, one edit per turn.
- **EDIT (variation)** — pass a donor screen's full extracted IR.
  Stage 1.4 capstone uses Dank screen 333 for this. The LLM
  proposes targeted changes (swap an icon, set a variant, etc.).
- **MID-SESSION** — pass whatever the session's current tree is.
  Stage 3's session loop will own this — for Stage 1, callers
  pass any in-memory doc.

Stage 1.3 is intentionally code-free (Codex 2026-04-23): the
contract is satisfied by Stage 1.2's "accept any doc" plus 1.4's
acceptance tests that exercise all three modes. Convenience
helpers (``load_doc_from_screen``, ``new_empty_doc``, etc.) belong
to whichever Stage 2/3 caller actually needs them — building them
now would lock in a shape the session-aware caller will likely
redesign.

The orchestrator:

1. Builds the per-verb schemas restricted to candidates discovered
   in the current ``doc`` (set/swap/replace target eids; append
   parent eids; insert/move pair indices; swap component_paths).
2. Calls Claude with all applicable verbs registered as tools.
3. Validates Claude returned exactly one tool_use content block —
   multiple tool calls per turn are a Codex-flagged risk
   (2026-04-23 Stage 1.2 fork) and produce KIND_MULTIPLE_TOOL_CALLS
   rather than silent first-pick.
4. Lowers the chosen tool_use input dict into edit-grammar source.
5. Parses the source via ``parse_l3``, then calls ``apply_edits`` on
   the original doc — returning the applied doc + structured result
   metadata for downstream session-log / repair-loop consumption.

Per Codex's 2026-04-23 fork decision: B (register all 7 tools)
beats A (one tool with discriminator) because Anthropic tool-use's
native "pick one of these tools" matches verb-pick semantics, and
discriminator + nested oneOf produces worse error modes when
Claude picks the wrong nested shape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from dd.markup_l3 import DDMarkupParseError, apply_edits, emit_l3, parse_l3
from dd.structural_verbs import (
    build_append_tool_schema,
    build_delete_tool_schema,
    build_insert_tool_schema,
    build_move_tool_schema,
    build_replace_tool_schema,
    build_set_tool_schema,
    build_swap_tool_schema,
    collect_insert_candidates,
    collect_move_candidates,
    collect_parent_candidates,
    collect_removable_candidates,
    unique_eids,
)


_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class ProposeEditsResult:
    """Outcome of one propose_edits call.

    ``ok`` is True iff Claude returned exactly one valid tool call
    AND the resulting edit applied cleanly. ``applied_doc`` is the
    post-apply document on success; on failure it's the original.
    """
    ok: bool
    tool_name: Optional[str]
    edit_source: Optional[str]
    rationale: Optional[str]
    applied_doc: Any
    error_kind: Optional[str] = None
    error_detail: Optional[str] = None


# --------------------------------------------------------------------------- #
# Tool registry                                                               #
# --------------------------------------------------------------------------- #

def build_propose_edits_tools(
    doc: Any,
    component_paths: list[str],
) -> list[dict[str, Any]]:
    """Return the per-verb tool schemas applicable to this doc.

    Verbs with empty candidate lists are OMITTED rather than emitted
    with empty enums (Anthropic rejects ``enum: []``). Specifically:

    - ``swap`` requires at least one component_path; if the project's
      CKR is empty, swap is omitted.
    - ``append`` requires at least one parent-with-block.
    - ``insert`` requires at least one (parent, anchor) pair.
    - ``move`` requires at least one (target, dest) pair.
    - ``set`` / ``delete`` / ``replace`` always work as long as the
      doc has any unique eids.
    """
    tools: list[dict[str, Any]] = []
    eids = unique_eids(doc)

    # Always-applicable verbs (assuming there are eids).
    if eids:
        tools.append(build_set_tool_schema(eids))
        # delete excludes the root via collect_removable_candidates
        removable = [c["eid"] for c in collect_removable_candidates(doc)][:32]
        if removable:
            tools.append(build_delete_tool_schema(removable))
        tools.append(build_replace_tool_schema(eids))

    # Append needs parent-with-block candidates.
    parents = [c["eid"] for c in collect_parent_candidates(doc)][:32]
    if parents:
        tools.append(build_append_tool_schema(parents))

    # Insert needs (parent, anchor) pairs.
    insert_pairs = collect_insert_candidates(doc)[:32]
    if insert_pairs:
        tools.append(build_insert_tool_schema(insert_pairs))

    # Move needs (target, dest) pairs.
    move_pairs = collect_move_candidates(doc)[:32]
    if move_pairs:
        tools.append(build_move_tool_schema(move_pairs))

    # Swap needs at least one CKR component path.
    if eids and component_paths:
        tools.append(build_swap_tool_schema(eids, list(component_paths)[:64]))

    return tools


# --------------------------------------------------------------------------- #
# Tool-call → edit-grammar source                                             #
# --------------------------------------------------------------------------- #

# Per grammar §2.6 + dd/markup_l3.py `_TEXT_BEARING_TYPES`, only these
# catalog types accept a positional string trailer (`<type> #eid "text"`).
# The structural-verb schemas also expose "heading" in their appendable
# set; we keep the allowlist in sync with the grammar so the lowering
# can safely emit the compact form when (and only when) it's valid.
_BARE_STRING_TRAILER_TYPES = frozenset(("text", "heading"))

# Grammar §3.1 — eid pattern is `^[a-z][a-z0-9-]{1,38}$` (max 39 chars).
# Mirrors dd/structural_verbs.py tool-schema constraint.
_EID_MAX_LEN = 39

_LABEL_SUFFIX = "-label"


def _derive_text_child_eid(base_eid: str) -> str:
    """Derive a unique, in-grammar eid for a synthesized text child.

    When an LLM supplies ``child_text`` on a non-text-bearing parent
    (e.g. ``frame``), we lower to a nested ``text #<derived> "..."``
    child rather than a bare-string trailer (which only text-bearing
    types can carry — see Codex A-fix).

    The derived eid is ``<base>-label`` when that fits within the
    39-char grammar cap; otherwise we truncate ``<base>`` and append a
    short sha1-prefix-suffix so the derived eid stays unique to this
    base eid while remaining within the cap.
    """
    candidate = f"{base_eid}{_LABEL_SUFFIX}"
    if len(candidate) <= _EID_MAX_LEN:
        return candidate
    digest = hashlib.sha1(base_eid.encode("utf-8")).hexdigest()[:4]
    # Reserve room for "-<4hex>-label" (11 chars) — digests are a-z0-9,
    # fully kebab-grammar-safe. If `<base>` is already short enough that
    # trimming wouldn't help, we still land in-bounds because the cap is
    # 39 and the reserved suffix is 11, leaving 28 truncation-chars.
    reserved = len(digest) + 1 + len(_LABEL_SUFFIX)  # -<digest>-label
    truncated = base_eid[: _EID_MAX_LEN - reserved]
    return f"{truncated}-{digest}{_LABEL_SUFFIX}"


def _lower_child_body(
    *,
    child_type: str,
    child_eid: str,
    child_text: Optional[str],
) -> str:
    """Build the inner body for an ``append``/``insert``/``replace``
    statement's ``{ ... }`` block.

    Per Codex A-fix (2026-04-24):

    - text-bearing types (``text`` / ``heading``) emit the compact
      ``<type> #eid "text"`` form — grammar-legal, minimal nesting.
    - ``frame`` with ``child_text`` lowers to a nested text child:
      ``frame #eid { text #eid-label "text" }`` so the output is
      valid L3.
    - Non-text, non-frame types (``rectangle`` / ``ellipse`` / ...)
      silently drop ``child_text`` — text inside a rectangle is
      surprising and the LLM should never have supplied it; the
      schema description even says so. Drop is intentional.
    """
    if child_type in _BARE_STRING_TRAILER_TYPES and child_text:
        esc = child_text.replace("\\", "\\\\").replace('"', '\\"')
        return f'{child_type} #{child_eid} "{esc}"'
    if child_type == "frame" and child_text:
        label_eid = _derive_text_child_eid(child_eid)
        esc = child_text.replace("\\", "\\\\").replace('"', '\\"')
        return (
            f"{child_type} #{child_eid} "
            f'{{ text #{label_eid} "{esc}" }}'
        )
    # No text, or a non-text-capable type with text-to-drop.
    return f"{child_type} #{child_eid}"


def parse_tool_call_to_edit(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    doc: Any,
) -> str:
    """Lower a tool_use input dict into a valid edit-grammar source line.

    For ``insert`` / ``move`` (which use pair_index addressing), the
    ``doc`` is consulted to resolve pair_index → (parent, anchor) /
    (target, dest) eids. Other verbs only need ``tool_input``.

    Raises ``ValueError`` for unknown ``tool_name`` (defensive — the
    enum constraint at the LLM layer should prevent this).
    """
    if tool_name == "emit_delete_edit":
        return f"delete @{tool_input['target_eid']}"

    if tool_name == "emit_set_edit":
        # Lower the LLM's string value into the right grammar form:
        #   - token ref ({...}) → pass through
        #   - number / bool / null → pass through
        #   - identifier-like (enum value: variant=disabled) → bare
        #   - everything else (sentences, phrases) → quoted string
        import re as _re
        raw = tool_input["value"]
        is_token_ref = raw.startswith("{") and raw.endswith("}")
        is_number = bool(_re.fullmatch(r"-?\d+(\.\d+)?", raw))
        is_keyword = raw in ("true", "false", "null", "hug", "fill", "fixed")
        is_bare_ident = bool(_re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", raw))
        if is_token_ref or is_number or is_keyword or is_bare_ident:
            value = raw
        else:
            # Escape embedded quotes per grammar string rules.
            esc = raw.replace("\\", "\\\\").replace('"', '\\"')
            value = f'"{esc}"'
        return f'set @{tool_input["target_eid"]} {tool_input["property"]}={value}'

    if tool_name == "emit_swap_edit":
        return (
            f"swap @{tool_input['target_eid']} "
            f"with=-> {tool_input['with_component']}"
        )

    if tool_name == "emit_append_edit":
        body = _lower_child_body(
            child_type=tool_input["child_type"],
            child_eid=tool_input["child_eid"],
            child_text=tool_input.get("child_text"),
        )
        src = f"append to=@{tool_input['parent_eid']} {{ {body} }}"
        return _validate_l3_or_raise(src, tool_name=tool_name)

    if tool_name == "emit_insert_edit":
        # pair_index → (parent_eid, anchor_eid)
        pairs = collect_insert_candidates(doc)
        idx = int(tool_input["pair_index"])
        if idx < 0 or idx >= len(pairs):
            raise ValueError(
                f"insert pair_index {idx} out of range "
                f"(have {len(pairs)} pairs)"
            )
        pair = pairs[idx]
        body = _lower_child_body(
            child_type=tool_input["child_type"],
            child_eid=tool_input["child_eid"],
            child_text=tool_input.get("child_text"),
        )
        src = (
            f"insert into=@{pair['parent_eid']} "
            f"after=@{pair['anchor_eid']} {{ {body} }}"
        )
        return _validate_l3_or_raise(src, tool_name=tool_name)

    if tool_name == "emit_move_edit":
        pairs = collect_move_candidates(doc)
        idx = int(tool_input["pair_index"])
        if idx < 0 or idx >= len(pairs):
            raise ValueError(
                f"move pair_index {idx} out of range "
                f"(have {len(pairs)} pairs)"
            )
        pair = pairs[idx]
        src = (
            f"move @{pair['target_eid']} "
            f"to=@{pair['dest_eid']} "
            f"position={tool_input['position']}"
        )
        return _validate_l3_or_raise(src, tool_name=tool_name)

    if tool_name == "emit_replace_edit":
        body = _lower_child_body(
            child_type=tool_input["replacement_root_type"],
            child_eid=tool_input["replacement_root_eid"],
            child_text=tool_input.get("replacement_root_text"),
        )
        src = f"replace @{tool_input['target_eid']} {{ {body} }}"
        return _validate_l3_or_raise(src, tool_name=tool_name)

    raise ValueError(f"unknown tool name: {tool_name!r}")


def _validate_l3_or_raise(src: str, *, tool_name: str) -> str:
    """Codex C-fix (2026-04-24): final validation boundary.

    ``parse_tool_call_to_edit`` must never return L3 that won't parse.
    Routing failures through ``ValueError`` is load-bearing: the
    downstream handler at ``dd/agent/loop.py`` already catches
    ``(KeyError, ValueError)`` from the lowering and converts it to a
    ``KIND_PARSE_FAILED`` non-edit turn — so a bad lowering doesn't
    persist a variant row with an invalid ``edit_script``.
    """
    try:
        parse_l3(src)
    except DDMarkupParseError as e:
        raise ValueError(
            f"invalid L3 from {tool_name} lowering: {e}"
        ) from e
    return src


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = (
    "You propose ONE edit to a UI tree at a time using the seven "
    "edit verbs (set / delete / append / insert / move / swap / "
    "replace). Each verb is exposed as its own tool — call exactly "
    "ONE tool per turn. The current tree is in the user message; "
    "the user's request describes the desired change."
)


def propose_edits(
    *,
    doc: Any,
    prompt: str,
    client: Any,
    component_paths: list[str],
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> ProposeEditsResult:
    """Drive Claude to propose one edit and apply it.

    Returns a :class:`ProposeEditsResult`. On success ``ok=True`` and
    ``applied_doc`` is the post-edit document. On failure ``ok=False``
    and ``error_kind`` is one of:

    - ``KIND_NO_TOOL_CALL`` — Claude responded without calling a tool.
    - ``KIND_MULTIPLE_TOOL_CALLS`` — Claude called >1 tool in one turn.
    - ``KIND_PARSE_FAILED`` — emitted edit-grammar source didn't parse.
    - ``KIND_APPLY_FAILED`` — apply_edits raised on the parsed edit.
    """
    tools = build_propose_edits_tools(doc, component_paths)
    if not tools:
        return ProposeEditsResult(
            ok=False, tool_name=None, edit_source=None, rationale=None,
            applied_doc=doc, error_kind="KIND_NO_TOOLS",
            error_detail="no applicable verb candidates for this doc",
        )

    # User message carries (a) the current tree as edit-grammar
    # source, (b) the user's request. This is the load-bearing
    # change from Stage 0 ("here's an empty IR") to Stage 1
    # ("here's the current state").
    tree_source = emit_l3(doc)
    user_text = (
        f"### Current tree\n```dd\n{tree_source}\n```\n\n"
        f"### Request\n{prompt}\n\n"
        "Pick one of the seven edit tools and emit a single edit "
        "that satisfies the request."
    )

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=_SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_text}],
    )

    tool_blocks = [b for b in (resp.content or []) if getattr(b, "type", None) == "tool_use"]

    if not tool_blocks:
        return ProposeEditsResult(
            ok=False, tool_name=None, edit_source=None, rationale=None,
            applied_doc=doc, error_kind="KIND_NO_TOOL_CALL",
            error_detail="LLM returned no tool_use content blocks",
        )

    if len(tool_blocks) > 1:
        return ProposeEditsResult(
            ok=False,
            tool_name=tool_blocks[0].name,
            edit_source=None, rationale=None,
            applied_doc=doc,
            error_kind="KIND_MULTIPLE_TOOL_CALLS",
            error_detail=(
                f"LLM emitted {len(tool_blocks)} tool calls in one "
                f"turn; expected exactly 1 — picked names: "
                f"{[b.name for b in tool_blocks]}"
            ),
        )

    block = tool_blocks[0]
    tool_input = dict(block.input or {})
    rationale = tool_input.get("rationale")

    try:
        edit_source = parse_tool_call_to_edit(
            block.name, tool_input, doc=doc,
        )
    except (KeyError, ValueError) as e:
        return ProposeEditsResult(
            ok=False, tool_name=block.name,
            edit_source=None, rationale=rationale,
            applied_doc=doc, error_kind="KIND_PARSE_FAILED",
            error_detail=str(e),
        )

    try:
        edit_doc = parse_l3(edit_source)
        applied = apply_edits(doc, list(edit_doc.edits))
    except Exception as e:  # noqa: BLE001
        return ProposeEditsResult(
            ok=False, tool_name=block.name,
            edit_source=edit_source, rationale=rationale,
            applied_doc=doc, error_kind="KIND_APPLY_FAILED",
            error_detail=str(e),
        )

    return ProposeEditsResult(
        ok=True, tool_name=block.name, edit_source=edit_source,
        rationale=rationale, applied_doc=applied,
    )
