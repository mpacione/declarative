"""Stage 1.4 — Stage 1 acceptance tests (3 synthetic fixtures).

Per docs/plan-authoring-loop.md §1.3, Stage 1's three acceptance
tests:

1. **Move an item**: prompt "move the save button to the top of
   the card" produces a `move @save-button to=@card position=first`
   edit. Applies cleanly.
2. **Replace an icon**: prompt "change the back button icon to a
   close icon" produces `swap @back-icon with=-> icon/close`.
   Applies cleanly.
3. **Add a variant**: prompt "make a version with the save button
   disabled" produces `set @save-button variant=disabled`.
   Applies cleanly.

Each test:
- Builds a small synthetic L3 doc as the starting IR (donor mode).
- Mocks Claude returning the expected tool call (deterministic;
  zero API spend; isolates the orchestrator + apply path from
  prompt-engineering quality).
- Calls ``propose_edits`` and asserts: ok=True, the right verb
  was picked, the lowered edit-grammar source is well-formed,
  and the applied doc reflects the expected change.

These tests pin the contract — that propose_edits CAN handle each
of the three motivating use cases when the LLM cooperates. Stage
1.5 capstones with one real-LLM end-to-end test against Dank
screen 333, where the LLM has to actually pick the right verb and
arguments from a real screen's IR.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dd.markup_l3 import parse_l3
from dd.propose_edits import propose_edits
from dd.structural_verbs import _walk_nodes


# --------------------------------------------------------------------------- #
# Mock helpers (mirror Stage 1.2's test patterns)                             #
# --------------------------------------------------------------------------- #

def _mock_tool_use(tool_name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    msg = MagicMock()
    msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _children_of(doc, parent_eid: str) -> list[str]:
    """Helper: return ordered child eids of the named parent in a doc."""
    for n in _walk_nodes(doc):
        if n.head.eid == parent_eid and getattr(n, "block", None):
            return [
                s.head.eid for s in n.block.statements
                if hasattr(s, "head") and s.head.eid
            ]
    return []


def _find_node_by_eid(doc, eid: str):
    for n in _walk_nodes(doc):
        if n.head.eid == eid:
            return n
    return None


# --------------------------------------------------------------------------- #
# Test 1 — MOVE the save button to the top of the card                        #
# --------------------------------------------------------------------------- #

class TestAcceptanceMove:
    """Plan §1.3 Test 1: move @save-button to=@card position=first."""

    def _donor(self):
        # A card with two children where save-button is currently last.
        # The acceptance prompt asks to move it to first. (button uses
        # label= rather than positional-string — the latter is only
        # legal for text-bearing types like text/heading.)
        return parse_l3(
            'card #card {\n'
            '  text #title "Confirm action"\n'
            '  button #save-button label="Save"\n'
            '}\n'
        )

    def test_move_save_button_to_top_of_card(self):
        doc = self._donor()
        # Sanity: pre-state has title first, save-button last.
        assert _children_of(doc, "card") == ["title", "save-button"]

        # Mock Claude picking the move verb. The orchestrator's
        # collect_move_candidates produces (target, dest) pairs;
        # we need to find the right pair_index.
        from dd.structural_verbs import collect_move_candidates
        pairs = collect_move_candidates(doc)
        idx = next(
            i for i, p in enumerate(pairs)
            if p["target_eid"] == "save-button" and p["dest_eid"] == "card"
        )

        client = _mock_client(_mock_tool_use(
            "emit_move_edit",
            {
                "pair_index": idx,
                "position": "first",
                "rationale": "user wants save button at top of card",
            },
        ))
        result = propose_edits(
            doc=doc,
            prompt="move the save button to the top of the card",
            client=client,
            component_paths=[],
        )

        assert result.ok is True, f"failed: {result.error_kind} {result.error_detail}"
        assert result.tool_name == "emit_move_edit"
        # The lowered edit-grammar source is well-formed.
        assert "move @save-button" in result.edit_source
        assert "to=@card" in result.edit_source
        assert "position=first" in result.edit_source
        # Post-state: save-button now first, title second.
        post_kids = _children_of(result.applied_doc, "card")
        assert post_kids == ["save-button", "title"], (
            f"expected save-button first; got {post_kids}"
        )


# --------------------------------------------------------------------------- #
# Test 2 — SWAP the back-button icon for a close icon                         #
# --------------------------------------------------------------------------- #

class TestAcceptanceSwap:
    """Plan §1.3 Test 2: swap @back-icon with=-> icon/close.

    The plan explicitly calls this a `swap` (Mode-1 component swap),
    not a `replace` (subtree substitution) — the back-button icon is
    an INSTANCE pointing at one master; the user wants it to point
    at a different master with the same shape.
    """

    def _donor(self):
        # A back button that wraps an icon instance pointing at
        # `icon/back`. The acceptance prompt asks to flip the icon
        # to `icon/close`.
        return parse_l3(
            'header #top-bar {\n'
            '  -> icon/back #back-icon\n'
            '}\n'
        )

    def test_swap_back_icon_to_close_icon(self):
        doc = self._donor()
        # Sanity: the back-icon currently references icon/back.
        node = _find_node_by_eid(doc, "back-icon")
        assert node is not None
        # type_or_path on a comp-ref is the master path.
        assert node.head.type_or_path == "icon/back"

        client = _mock_client(_mock_tool_use(
            "emit_swap_edit",
            {
                "target_eid": "back-icon",
                "with_component": "icon/close",
                "rationale": "user wants close icon instead of back",
            },
        ))
        result = propose_edits(
            doc=doc,
            prompt="change the back button icon to a close icon",
            client=client,
            component_paths=["icon/back", "icon/close"],
        )

        assert result.ok is True, f"failed: {result.error_kind} {result.error_detail}"
        assert result.tool_name == "emit_swap_edit"
        assert "swap @back-icon" in result.edit_source
        assert "icon/close" in result.edit_source
        # Post-state: the node's master path is icon/close.
        post = _find_node_by_eid(result.applied_doc, "back-icon")
        assert post is not None
        assert post.head.type_or_path == "icon/close", (
            f"expected icon/close; got {post.head.type_or_path}"
        )


# --------------------------------------------------------------------------- #
# Test 3 — SET save-button variant to disabled                                #
# --------------------------------------------------------------------------- #

class TestAcceptanceVariantFlip:
    """Plan §1.3 Test 3: set @save-button variant=disabled."""

    def _donor(self):
        # A button with no variant set (implicit default). label= form
        # because positional-string isn't valid in a block for button.
        return parse_l3(
            'card #card {\n'
            '  button #save-button label="Save"\n'
            '}\n'
        )

    def test_set_save_button_variant_disabled(self):
        doc = self._donor()
        # Sanity: pre-state has no variant on save-button.
        node = _find_node_by_eid(doc, "save-button")
        assert node is not None

        client = _mock_client(_mock_tool_use(
            "emit_set_edit",
            {
                "target_eid": "save-button",
                "property": "variant",
                "value": "disabled",
                "rationale": "user wants disabled variant",
            },
        ))
        result = propose_edits(
            doc=doc,
            prompt="make a version with the save button disabled",
            client=client,
            component_paths=[],
        )

        assert result.ok is True, f"failed: {result.error_kind} {result.error_detail}"
        assert result.tool_name == "emit_set_edit"
        assert "set @save-button" in result.edit_source
        assert "variant=disabled" in result.edit_source
        # Post-state: the save-button now carries variant=disabled.
        post = _find_node_by_eid(result.applied_doc, "save-button")
        assert post is not None
        # variant lives in the head's properties tuple as a PropAssign.
        prop_keys = {
            getattr(p, "key", None)
            for p in (post.head.properties or ())
        }
        assert "variant" in prop_keys, (
            f"expected variant property after set; got keys {prop_keys}"
        )


# --------------------------------------------------------------------------- #
# Round-trip — proves the lowered edit re-parses cleanly                      #
# --------------------------------------------------------------------------- #

class TestRoundTripContract:
    """The lowered edit-grammar source must re-parse via `parse_l3`
    cleanly — that's how the orchestrator dispatches to apply_edits.
    Stage 0 had a bug where the synthetic fixture didn't round-trip
    the contract; Stage 1 pins it for each verb."""

    def test_move_lowered_source_round_trips(self):
        from dd.markup_l3 import parse_l3 as p
        # Re-using TestAcceptanceMove's lowered source.
        src = "move @save-button to=@card position=first"
        edits = list(p(src).edits)
        assert len(edits) == 1

    def test_swap_lowered_source_round_trips(self):
        from dd.markup_l3 import parse_l3 as p
        src = "swap @back-icon with=-> icon/close"
        edits = list(p(src).edits)
        assert len(edits) == 1

    def test_set_lowered_source_round_trips(self):
        from dd.markup_l3 import parse_l3 as p
        src = "set @save-button variant=disabled"
        edits = list(p(src).edits)
        assert len(edits) == 1
