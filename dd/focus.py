"""Stage 2.1 — focus primitives (FocusContext + extract_subtree).

Per Codex 2026-04-23 fork: NAME / DRILL / CLIMB are deterministic
orchestrator entry points (option B), not LLM-callable tools
(option A). The LLM only ever sees `propose_edits`. The focus
layer sits above propose_edits and shapes the doc / context the
LLM gets to see and act on.

Designed for Stage 3 reuse:
- `FocusContext` is frozen + composable (drilled_to / climbed return
  new contexts, never mutate).
- `parent_chain` is a list (Stage 3's session loop will replay it).
- `MoveLogEntry` carries enough fields to promote into Stage 3's
  ``move_log`` SQL table (migration 023) with no schema change —
  just a JSONL → row import.
- `is_in_scope(focus, eid)` is a pure function the verifier hook
  calls on every applied edit to confirm DRILL scope held.

This module is a pure-Python data layer. No I/O, no LLM calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

from dd.markup_l3 import Block, L3Document, Node


# --------------------------------------------------------------------------- #
# Subtree extraction                                                          #
# --------------------------------------------------------------------------- #

def _walk_nodes_in(node: Node) -> Iterable[Node]:
    """Yield ``node`` then every descendant Node."""
    yield node
    blk = getattr(node, "block", None)
    if blk is None:
        return
    for stmt in blk.statements:
        if isinstance(stmt, Node):
            yield from _walk_nodes_in(stmt)


def _walk_doc_nodes(doc: L3Document) -> Iterable[Node]:
    for top in doc.top_level:
        if isinstance(top, Node):
            yield from _walk_nodes_in(top)


def _find_node_by_eid(doc: L3Document, eid: str) -> Optional[Node]:
    for n in _walk_doc_nodes(doc):
        if getattr(n.head, "eid", None) == eid:
            return n
    return None


def extract_subtree(doc: L3Document, eid: str) -> Optional[L3Document]:
    """Return a fresh ``L3Document`` rooted at the named node.

    Used by DRILL to give the LLM a sub-doc whose top_level is
    exactly the named subtree. Returns ``None`` if the eid isn't
    in the doc — caller's job to surface that as a user-visible
    error rather than guess.

    The original doc's namespace / uses / tokens are preserved so
    the sub-doc still parses against the same project vocabulary.
    Edits are NOT preserved — sub-docs are read-only views; the
    edit pipeline targets the root doc.
    """
    node = _find_node_by_eid(doc, eid)
    if node is None:
        return None
    return L3Document(
        namespace=doc.namespace,
        uses=doc.uses,
        tokens=doc.tokens,
        top_level=(node,),
        edits=(),
        warnings=(),
        source_path=doc.source_path,
    )


def _descendant_eids(doc: L3Document, root_eid: str) -> set[str]:
    """All eids in the subtree rooted at ``root_eid``, inclusive."""
    root = _find_node_by_eid(doc, root_eid)
    if root is None:
        return set()
    return {
        n.head.eid for n in _walk_nodes_in(root)
        if getattr(n.head, "eid", None)
    }


# --------------------------------------------------------------------------- #
# MoveLogEntry — the JSONL/move_log shape                                     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MoveLogEntry:
    """One row in the agent's reasoning trail.

    Fields are designed to round-trip into Stage 3's ``move_log`` SQL
    table (migration 023) with no schema change — just a JSONL → row
    import. ``payload`` is a freeform dict per-primitive (NAME ships
    a description; DRILL ships the focus_goal; EDIT ships the edit
    source). ``rationale`` is the LLM's one-sentence reason from
    ``ProposeEditsResult.rationale``.
    """
    primitive: str  # NAME / DRILL / CLIMB / EDIT (Stage 3 adds LATERAL)
    scope_eid: Optional[str]  # the eid this entry was about
    payload: dict[str, Any] = field(default_factory=dict)
    rationale: Optional[str] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the dict shape Stage 3's move_log row will hold."""
        return {
            "primitive": self.primitive,
            "scope_eid": self.scope_eid,
            "payload": dict(self.payload),
            "rationale": self.rationale,
            "ts": self.ts,
        }


# --------------------------------------------------------------------------- #
# FocusContext                                                                #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FocusContext:
    """The agent's current focus scope on a doc.

    Stage 2.1 ships this as a pure-data dataclass; Stage 3's session
    loop will wrap it with persistence + variant tracking. The shape
    is designed not to change — Stage 3 should only need to add a
    sibling persistence layer, never mutate the focus dataclass.

    Fields:
    - ``root_doc`` — the original full doc. Always the source of
      truth; DRILL never mutates it (we hold a focused VIEW).
    - ``scope_eid`` — the eid the focus is currently scoped to,
      or None for root (whole doc).
    - ``parent_chain`` — list of scope_eids climbed-through to reach
      the current scope. Empty at root. Last element is the
      immediate parent's scope_eid (which may be None for root scope).
    - ``move_log`` — append-only list of MoveLogEntry. Stage 3
      promotes to SQL.
    """
    root_doc: L3Document
    scope_eid: Optional[str] = None
    parent_chain: list[Optional[str]] = field(default_factory=list)
    move_log: list[MoveLogEntry] = field(default_factory=list)

    @classmethod
    def root(cls, doc: L3Document) -> "FocusContext":
        """Construct a root-scoped focus on ``doc``."""
        return cls(root_doc=doc, scope_eid=None, parent_chain=[], move_log=[])

    @property
    def doc(self) -> L3Document:
        """The doc IN the current scope.

        At root scope this is the full ``root_doc``. After DRILL it's
        the extracted subtree — what the LLM sees + what propose_edits
        is called against. Per the option-2a mechanic chosen
        2026-04-23: subtree-scoped edits address the parent doc by
        ``@eid``; the focus doesn't fork the root, just narrows what
        the LLM is shown.
        """
        if self.scope_eid is None:
            return self.root_doc
        sub = extract_subtree(self.root_doc, self.scope_eid)
        if sub is None:
            # Defensive — should be unreachable if drilled_to validated.
            raise ValueError(
                f"focus scope_eid {self.scope_eid!r} no longer present in root doc"
            )
        return sub

    def drilled_to(self, eid: str) -> "FocusContext":
        """Return a new focus scoped one level deeper.

        Raises ``ValueError`` if ``eid`` isn't in the current scope —
        silent no-op would cascade as 'why doesn't the LLM see
        anything?' (per docstring on the test).
        """
        if not is_in_scope(self, eid):
            raise ValueError(
                f"cannot drill: no eid {eid!r} in current scope "
                f"(scope={self.scope_eid!r})"
            )
        new_chain = list(self.parent_chain) + [self.scope_eid]
        return replace(
            self,
            scope_eid=eid,
            parent_chain=new_chain,
            move_log=list(self.move_log),  # copy so mutation can't bleed
        )

    def climbed(self) -> "FocusContext":
        """Return a new focus scoped one level shallower.

        At root scope (``parent_chain == []``) this is a no-op —
        defensive against double-climb in agent loops.
        """
        if not self.parent_chain:
            return self
        new_chain = list(self.parent_chain)
        prev_scope = new_chain.pop()
        return replace(
            self,
            scope_eid=prev_scope,
            parent_chain=new_chain,
            move_log=list(self.move_log),
        )

    def with_log_entry(self, entry: MoveLogEntry) -> "FocusContext":
        """Return a new focus with ``entry`` appended to the move log.

        Stage 2.2+ orchestrator helpers (NAME / DRILL / CLIMB / EDIT)
        call this to record their move. Append-only; no mutation.
        """
        return replace(
            self,
            move_log=list(self.move_log) + [entry],
        )


# --------------------------------------------------------------------------- #
# Scope check                                                                 #
# --------------------------------------------------------------------------- #

def is_in_scope(focus: FocusContext, eid: str) -> bool:
    """Is ``eid`` part of the subtree the focus is scoped to?

    Pure function; no side effects. Stage 3's session loop will call
    this on every applied edit to verify DRILL scope held — i.e. the
    LLM didn't reach outside its drilled subtree.

    At root scope, every eid in the doc is in scope. After a DRILL,
    only descendants of ``focus.scope_eid`` (inclusive) count.
    """
    if focus.scope_eid is None:
        # Root scope — every eid in the doc.
        for n in _walk_doc_nodes(focus.root_doc):
            if getattr(n.head, "eid", None) == eid:
                return True
        return False
    return eid in _descendant_eids(focus.root_doc, focus.scope_eid)
