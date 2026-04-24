"""Stage 2 of `docs/plan-authoring-loop.md` — focus primitives.

Stage 2.1 — `FocusContext` + `extract_subtree`.

Per Codex's 2026-04-23 fork: NAME / DRILL / CLIMB are deterministic
orchestrator entry points (option B), not LLM-callable tools
(option A). The LLM only ever sees `propose_edits`. The focus
layer sits one level above and shapes the doc / context the LLM
sees.

`FocusContext` is the load-bearing dataclass — it carries:
- the original (root) doc,
- the parent chain of eids that drill into to reach the current scope,
- the current scope's eid (or None for screen-root scope),
- a move log of NAME / DRILL / CLIMB / EDIT entries.

Designed for Stage 3 reuse: parent_chain is a list (DAG-friendly),
move_log is append-only, and the scope check is a pure function
of focus + node_eid (so Stage 3's session loop can call it).

Codex risk: design FocusContext with Stage 3 in mind so we don't
retrofit. These tests pin the shape.
"""

from __future__ import annotations

import pytest

from dd.focus import (
    FocusContext,
    MoveLogEntry,
    extract_subtree,
    is_in_scope,
)
from dd.markup_l3 import parse_l3
from dd.structural_verbs import _walk_nodes, existing_eids


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _three_section_doc():
    """A small but multi-depth doc that exercises drill/climb."""
    return parse_l3(
        "screen #screen-root {\n"
        "  header #top-bar {\n"
        "    text #title \"Title\"\n"
        "  }\n"
        "  frame #features-section {\n"
        "    heading #features-heading \"Features\"\n"
        "    card #feature-card-1 {\n"
        "      text #card-1-title \"One\"\n"
        "    }\n"
        "    card #feature-card-2 {\n"
        "      text #card-2-title \"Two\"\n"
        "    }\n"
        "  }\n"
        "  frame #footer\n"
        "}\n"
    )


# --------------------------------------------------------------------------- #
# extract_subtree                                                             #
# --------------------------------------------------------------------------- #

class TestExtractSubtree:
    """Take an L3Document + an eid; return a doc rooted at that eid.
    Used by DRILL to give the LLM a sub-doc to scope its edits."""

    def test_extracts_named_subtree(self):
        doc = _three_section_doc()
        sub = extract_subtree(doc, "features-section")
        assert sub is not None
        # The sub-doc's top-level is exactly the named node.
        eids = existing_eids(sub)
        assert "features-section" in eids
        assert "features-heading" in eids
        assert "feature-card-1" in eids
        assert "card-2-title" in eids

    def test_subtree_excludes_siblings_and_parents(self):
        doc = _three_section_doc()
        sub = extract_subtree(doc, "features-section")
        eids = existing_eids(sub)
        # screen-root and footer are NOT in the subtree.
        assert "screen-root" not in eids
        assert "footer" not in eids
        # top-bar and its title are NOT either (sibling of features).
        assert "top-bar" not in eids
        assert "title" not in eids

    def test_subtree_of_leaf_returns_just_the_leaf(self):
        doc = _three_section_doc()
        sub = extract_subtree(doc, "card-1-title")
        eids = existing_eids(sub)
        assert eids == {"card-1-title"}

    def test_subtree_of_unknown_eid_returns_none(self):
        doc = _three_section_doc()
        assert extract_subtree(doc, "no-such-eid") is None

    def test_subtree_of_root_returns_full_doc(self):
        doc = _three_section_doc()
        sub = extract_subtree(doc, "screen-root")
        # The full screen — every eid present.
        full = existing_eids(doc)
        sub_eids = existing_eids(sub)
        assert sub_eids == full

    def test_subtree_top_level_has_exactly_one_node(self):
        """The extracted doc is rooted at the named eid — its
        top_level should be exactly that one node, not unwrap
        children to siblings of the original."""
        doc = _three_section_doc()
        sub = extract_subtree(doc, "feature-card-1")
        assert len(sub.top_level) == 1
        assert sub.top_level[0].head.eid == "feature-card-1"


# --------------------------------------------------------------------------- #
# FocusContext                                                                #
# --------------------------------------------------------------------------- #

class TestFocusContextShape:
    """Pin the dataclass shape now so Stage 3 inherits a stable
    contract. Per Codex 2026-04-23: design with Stage 3 in mind —
    stable ids, parent chain, scope-check hooks."""

    def test_root_focus_has_no_parent_chain(self):
        doc = _three_section_doc()
        focus = FocusContext.root(doc)
        assert focus.parent_chain == []
        assert focus.scope_eid is None
        assert focus.root_doc is doc
        assert focus.move_log == []

    def test_root_focus_doc_is_root(self):
        """`focus.doc` returns the in-scope view. At root scope
        that's the whole doc."""
        doc = _three_section_doc()
        focus = FocusContext.root(doc)
        assert focus.doc is doc

    def test_drilled_focus_carries_parent_chain(self):
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        drilled = root.drilled_to("features-section")
        assert drilled.parent_chain == [None]  # parent was root scope
        assert drilled.scope_eid == "features-section"
        # root_doc unchanged — DRILL is a view, not a fork.
        assert drilled.root_doc is doc

    def test_drilled_focus_doc_is_subtree(self):
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        drilled = root.drilled_to("features-section")
        sub_eids = existing_eids(drilled.doc)
        assert "features-section" in sub_eids
        assert "screen-root" not in sub_eids

    def test_double_drill_carries_full_chain(self):
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        f1 = root.drilled_to("features-section")
        f2 = f1.drilled_to("feature-card-1")
        assert f2.parent_chain == [None, "features-section"]
        assert f2.scope_eid == "feature-card-1"

    def test_climb_pops_one_level(self):
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        f1 = root.drilled_to("features-section")
        f2 = f1.drilled_to("feature-card-1")
        # Climb once: back to features-section
        c1 = f2.climbed()
        assert c1.scope_eid == "features-section"
        assert c1.parent_chain == [None]
        # Climb again: back to root
        c2 = c1.climbed()
        assert c2.scope_eid is None
        assert c2.parent_chain == []

    def test_climb_at_root_returns_self(self):
        """Climb is a no-op at root scope — defensive against
        double-climb in agent loops."""
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        climbed = root.climbed()
        assert climbed.scope_eid is None
        assert climbed.parent_chain == []

    def test_drilling_to_unknown_eid_raises(self):
        """If the LLM (or test harness) tries to drill into an eid
        that isn't in the current scope, fail loudly. Silent failure
        would cascade as 'why doesn't the LLM see anything?'"""
        doc = _three_section_doc()
        root = FocusContext.root(doc)
        with pytest.raises(ValueError, match="no.*ghost"):
            root.drilled_to("ghost-eid")


# --------------------------------------------------------------------------- #
# is_in_scope (scope check Stage 3 will reuse)                                #
# --------------------------------------------------------------------------- #

class TestIsInScope:
    """For the verifier hook: 'after a DRILL-scoped edit applies to
    the root doc, did it touch only descendants of focus.scope_eid?'
    Pure function of focus + node_eid + root_doc; Stage 3's session
    loop will call this on every applied edit."""

    def test_root_scope_includes_everything(self):
        doc = _three_section_doc()
        focus = FocusContext.root(doc)
        assert is_in_scope(focus, "title") is True
        assert is_in_scope(focus, "footer") is True
        assert is_in_scope(focus, "card-2-title") is True

    def test_drilled_scope_includes_descendants(self):
        doc = _three_section_doc()
        focus = FocusContext.root(doc).drilled_to("features-section")
        assert is_in_scope(focus, "features-section") is True
        assert is_in_scope(focus, "features-heading") is True
        assert is_in_scope(focus, "feature-card-1") is True
        assert is_in_scope(focus, "card-2-title") is True

    def test_drilled_scope_excludes_outside(self):
        doc = _three_section_doc()
        focus = FocusContext.root(doc).drilled_to("features-section")
        assert is_in_scope(focus, "screen-root") is False
        assert is_in_scope(focus, "title") is False
        assert is_in_scope(focus, "footer") is False

    def test_unknown_eid_returns_false(self):
        doc = _three_section_doc()
        focus = FocusContext.root(doc).drilled_to("features-section")
        assert is_in_scope(focus, "no-such-eid") is False


# --------------------------------------------------------------------------- #
# MoveLogEntry shape                                                          #
# --------------------------------------------------------------------------- #

class TestMoveLogEntryShape:
    """Pin the log-entry shape now so Stage 3's SQL schema can
    promote from JSONL with no schema migration."""

    def test_required_fields(self):
        entry = MoveLogEntry(
            primitive="DRILL",
            scope_eid="features-section",
            payload={"focus_goal": "tighten card spacing"},
            rationale="user wants denser layout",
        )
        assert entry.primitive == "DRILL"
        assert entry.scope_eid == "features-section"
        assert entry.payload == {"focus_goal": "tighten card spacing"}
        assert entry.rationale == "user wants denser layout"

    def test_to_dict_round_trips_for_jsonl(self):
        entry = MoveLogEntry(
            primitive="NAME",
            scope_eid="features-section",
            payload={"description": "product showcase section"},
            rationale=None,
        )
        d = entry.to_dict()
        assert d["primitive"] == "NAME"
        assert d["scope_eid"] == "features-section"
        assert d["payload"] == {"description": "product showcase section"}
        assert d["rationale"] is None
        assert "ts" in d  # timestamp for sorting / replay
