"""Stage 2.2 — NAME primitive + JSONL move-log writer.

Per docs/plan-authoring-loop.md §2.1: ``name_subtree(eid, description)``
announces "this subtree is a product-showcase-section" for the
agent's own rationale tracking. Does NOT create a new type — the
node still has type=frame — the name is promoted from ad-hoc eid
to semantic marker. Stored in move_log as a NAME entry.

Per Codex 2026-04-23 fork: option B — NAME is a deterministic
orchestrator entry point, not an LLM-callable tool. Pure function
of (focus, eid, description) → updated focus.

JSONL writer is the persistence stopgap for Stage 2 (Stage 3 owns
the SQL ``move_log`` table via migration 023). Per the audit, no
table exists today; the JSONL shape round-trips into the future
SQL schema row-for-row.
"""

from __future__ import annotations

import json

import pytest

from dd.agent.primitives import name_subtree, write_move_log_jsonl
from dd.focus import FocusContext, MoveLogEntry
from dd.markup_l3 import parse_l3


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _three_section_doc():
    return parse_l3(
        "screen #screen-root {\n"
        "  header #top-bar {\n"
        "    text #title \"Title\"\n"
        "  }\n"
        "  frame #features-section {\n"
        "    heading #features-heading \"Features\"\n"
        "    card #feature-card-1\n"
        "  }\n"
        "}\n"
    )


# --------------------------------------------------------------------------- #
# name_subtree                                                                #
# --------------------------------------------------------------------------- #

class TestNameSubtree:
    """The NAME primitive: tag a subtree with a semantic description.
    Pure metadata — does not change the doc, only the move log."""

    def test_returns_focus_with_appended_name_entry(self):
        focus = FocusContext.root(_three_section_doc())
        new_focus = name_subtree(
            focus, "features-section", "product showcase section",
        )
        assert len(new_focus.move_log) == 1
        entry = new_focus.move_log[0]
        assert entry.primitive == "NAME"
        assert entry.scope_eid == "features-section"
        assert entry.payload["description"] == "product showcase section"

    def test_does_not_mutate_input_focus(self):
        focus = FocusContext.root(_three_section_doc())
        name_subtree(focus, "features-section", "product showcase section")
        assert focus.move_log == []  # input untouched

    def test_does_not_change_doc_or_scope(self):
        focus = FocusContext.root(_three_section_doc()).drilled_to("features-section")
        new_focus = name_subtree(
            focus, "feature-card-1", "the first feature card",
        )
        assert new_focus.scope_eid == "features-section"
        assert new_focus.parent_chain == focus.parent_chain
        assert new_focus.root_doc is focus.root_doc

    def test_rejects_eid_not_in_root_doc(self):
        """Naming a node that isn't in the root doc is a no-op-with-
        warning. Silent acceptance would let the LLM accumulate names
        on nodes that don't exist; loud rejection forces a real eid."""
        focus = FocusContext.root(_three_section_doc())
        with pytest.raises(ValueError, match="ghost-eid"):
            name_subtree(focus, "ghost-eid", "phantom")

    def test_naming_works_outside_current_scope(self):
        """NAME is metadata; it should work on any eid in the root
        doc, regardless of current focus scope. The agent might want
        to label sibling subtrees while drilled into another."""
        focus = FocusContext.root(_three_section_doc()).drilled_to("features-section")
        new_focus = name_subtree(focus, "top-bar", "the top navigation")
        # Even though top-bar is OUT of scope, the NAME entry was
        # recorded — it's pure metadata.
        assert len(new_focus.move_log) == 1
        assert new_focus.move_log[0].scope_eid == "top-bar"

    def test_multiple_names_accumulate_in_log(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = name_subtree(focus, "features-section", "showcase")
        f2 = name_subtree(f1, "top-bar", "nav")
        assert len(f2.move_log) == 2
        assert f2.move_log[0].payload["description"] == "showcase"
        assert f2.move_log[1].payload["description"] == "nav"


# --------------------------------------------------------------------------- #
# write_move_log_jsonl                                                        #
# --------------------------------------------------------------------------- #

class TestMoveLogJsonl:
    """JSONL persistence stopgap. Stage 3's SQL schema (migration
    023) consumes the same shape via ``MoveLogEntry.to_dict``, so a
    Stage 2 .jsonl file is a forward-compatible artifact."""

    def test_writes_one_line_per_entry(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        focus = name_subtree(focus, "top-bar", "nav")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_each_line_is_parseable_json(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        line = out.read_text().strip()
        parsed = json.loads(line)
        assert parsed["primitive"] == "NAME"
        assert parsed["scope_eid"] == "features-section"
        assert parsed["payload"]["description"] == "showcase"
        assert "ts" in parsed

    def test_empty_log_produces_empty_file(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        assert out.read_text() == ""

    def test_jsonl_round_trips_to_movelogentry(self, tmp_path):
        """Codex's risk: design with Stage 3 in mind. A read-back
        helper proves the JSONL shape is the same shape Stage 3's
        SQL row would carry — promoting from JSONL to SQL is a
        bulk-import, not a re-serialization."""
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        # Read back the only row, reconstruct an entry, compare to the
        # in-memory entry's to_dict output.
        line = json.loads(out.read_text().strip())
        original = focus.move_log[0]
        assert line == original.to_dict()
