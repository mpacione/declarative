"""Tests for ``dd.apply_render`` — render-map maintenance across edits.

M7.2 closure (plan-synthetic-gen §5 M7.2): ``apply_edits`` splices a
mutated AST with new Python object identities. The renderer's
``spec_key_map``, ``nid_map``, ``original_name_map`` — all keyed on
``id(Node)`` — stop covering the new subtree. ``rebuild_maps_after_edits``
walks applied + original in parallel, carries old entries forward onto
the new keys, and injects a synthetic CKR lookup for swap targets so
Mode-1 ``createInstance`` resolves the new master.

Tests treat the helper as a pure function over (applied_doc,
original_doc, edits, old_maps, conn). The Figma bridge is out of scope
here — the downstream round-trip test lives in the integration module.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from dd.apply_render import (
    AppliedRenderMaps,
    BridgeError,
    RenderedApplied,
    SwapUnresolvedInCKR,
    adjust_spec_elements_for_edits,
    execute_script_via_bridge,
    rebuild_maps_after_edits,
    render_applied_doc,
    walk_rendered_via_bridge,
)
from dd.markup_l3 import apply_edits, parse_l3


def _parse_fixture() -> tuple[object, object, object, object]:
    """Return ``(doc, screen_node, frame_node, button_node)`` for the
    minimal ``screen → frame → button-comp-ref`` tree used across these
    tests."""
    src = (
        "screen #screen-1 {\n"
        "  frame #frame-1 {\n"
        "    -> button/primary/lg #button-1\n"
        "  }\n"
        "}\n"
    )
    doc = parse_l3(src)
    screen = doc.top_level[0]
    frame = screen.block.statements[0]
    button = frame.block.statements[0]
    return doc, screen, frame, button


def _setup_ckr(conn: sqlite3.Connection, rows: list[tuple[str, str, str]]) -> None:
    """Build a minimal ``component_key_registry`` with the rows provided.

    Each row is ``(component_key, figma_node_id, name)``.
    """
    conn.execute(
        "CREATE TABLE component_key_registry ("
        "component_key TEXT PRIMARY KEY, figma_node_id TEXT, name TEXT)"
    )
    conn.executemany(
        "INSERT INTO component_key_registry "
        "(component_key, figma_node_id, name) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


class TestRebuildMapsAfterEdits:
    def test_empty_edits_returns_identity_maps(self) -> None:
        """No edits: ``apply_edits`` returns the same doc object, so the
        existing maps already cover every node. The helper should return
        them unchanged rather than invent new entries."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [("k-lg", "fig-lg", "button/primary/lg")])

        nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = {
            id(screen): "Screen",
            id(frame): "Frame",
            id(button): "Button/Primary/Lg",
        }

        applied = apply_edits(doc, [])

        out = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=doc,
            edits=[],
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=conn,
        )

        assert isinstance(out, AppliedRenderMaps)
        assert out.nid_map == nid_map
        assert out.spec_key_map == spec_key_map
        assert out.original_name_map == original_name_map
        assert out.db_visuals_patch == {}

    def test_swap_carries_sibling_path_maps_forward(self) -> None:
        """After a swap, the path from root to target has new ``id()``
        values (``_splice_node`` replaces every ancestor). The helper
        must emit entries for each new id."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(
            conn,
            [
                ("k-lg", "fig-lg", "button/primary/lg"),
                ("k-md", "fig-md", "button/secondary/md"),
            ],
        )
        nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = {
            id(screen): "Screen",
            id(frame): "Frame",
            id(button): "Button/Primary/Lg",
        }

        edits = list(
            parse_l3("swap @button-1 with=-> button/secondary/md").edits
        )
        applied = apply_edits(doc, edits)
        a_screen = applied.top_level[0]
        a_frame = a_screen.block.statements[0]
        a_button = a_frame.block.statements[0]

        out = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=doc,
            edits=edits,
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=conn,
        )

        # Ancestors (screen + frame) — structurally unchanged by the
        # swap but their id() shifted because _splice_node walks back
        # up. The helper must carry their old maps forward.
        assert out.nid_map[id(a_screen)] == 1001
        assert out.nid_map[id(a_frame)] == 1002
        assert out.spec_key_map[id(a_screen)] == "screen-1"
        assert out.spec_key_map[id(a_frame)] == "frame-1"
        assert out.original_name_map[id(a_screen)] == "Screen"
        assert out.original_name_map[id(a_frame)] == "Frame"

    def test_swap_target_gets_synthetic_ckr_entry(self) -> None:
        """The swapped node has no DB node_id — we fabricate a negative
        synthetic nid and stash a ``db_visuals_patch`` entry containing
        the new master's CKR ``figma_node_id``. That's what Mode-1
        ``createInstance`` emission in ``render_figma_ast._emit_phase1``
        keys off to resolve the new master."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(
            conn,
            [
                ("k-lg", "fig-lg", "button/primary/lg"),
                ("k-md", "fig-md-NEW", "button/secondary/md"),
            ],
        )

        nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = {
            id(screen): "Screen",
            id(frame): "Frame",
            id(button): "Button/Primary/Lg",
        }

        edits = list(
            parse_l3("swap @button-1 with=-> button/secondary/md").edits
        )
        applied = apply_edits(doc, edits)
        a_button = applied.top_level[0].block.statements[0].block.statements[0]

        out = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=doc,
            edits=edits,
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=conn,
        )

        # The swapped button gets an entry — the nid is synthetic
        # (negative, distinct from any real DB id).
        assert id(a_button) in out.nid_map
        synth_nid = out.nid_map[id(a_button)]
        assert synth_nid < 0, "swap-synthesised nids should be negative"

        # Spec-key carries the old eid forward (the renderer uses
        # spec_key to emit the ``M[<key>] = nN.id`` entry).
        assert out.spec_key_map[id(a_button)] == "button-1"
        # Name is the new master (the renderer uses this to label the
        # rendered Figma node).
        assert "secondary" in out.original_name_map[id(a_button)].lower()

        # db_visuals_patch has the CKR resolution keyed on synth_nid.
        patch = out.db_visuals_patch
        assert synth_nid in patch
        entry = patch[synth_nid]
        assert entry.get("component_figma_id") == "fig-md-NEW"
        assert entry.get("node_type") == "INSTANCE"

    # ------------------------------------------------------------
    # Tier A.2 — append / insert coverage
    # ------------------------------------------------------------

    def test_append_maps_carry_siblings_forward_and_mark_new_child(
        self,
    ) -> None:
        """A new child appended to a parent must not disturb the
        sibling maps. Existing nodes (screen/frame/button) keep
        their old nid/spec_key/original_name entries onto the new
        id(). The appended node itself gets a spec_key entry so
        the renderer's M[] emission reaches it; no DB nid (not in
        the original tree)."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [("k-lg", "fig-lg", "button/primary/lg")])

        nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = {
            id(screen): "Screen",
            id(frame): "Frame",
            id(button): "Button",
        }

        edits = list(
            parse_l3(
                "append to=@frame-1 {\n  text #new-label \"hi\"\n}"
            ).edits
        )
        applied = apply_edits(doc, edits)
        a_screen = applied.top_level[0]
        a_frame = a_screen.block.statements[0]
        a_button = a_frame.block.statements[0]
        a_new = a_frame.block.statements[1]

        out = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=doc,
            edits=edits,
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=conn,
        )
        # Pre-existing nodes keep their maps, re-keyed on new id()
        assert out.nid_map[id(a_screen)] == 1001
        assert out.nid_map[id(a_frame)] == 1002
        assert out.nid_map[id(a_button)] == 1003
        # New node has NO nid entry (never existed in DB) but HAS
        # a spec_key entry so renderer writes M["new-label"] = nN.id
        assert id(a_new) not in out.nid_map
        assert out.spec_key_map[id(a_new)] == "new-label"
        # Original name = eid is fine (renderer uses this as node
        # name on the Figma canvas).
        assert out.original_name_map[id(a_new)] == "new-label"

    def test_insert_after_anchor_keeps_alignment(self) -> None:
        """Insert places a new sibling mid-block (after an anchor).
        The applied tree has +1 node; positional BFS would go out
        of alignment after the insertion point. Path-based matching
        is what keeps siblings correctly paired."""
        src = (
            "screen #screen-1 {\n"
            "  frame #frame-1 {\n"
            "    text #title \"hi\"\n"
            "    text #subtitle \"yo\"\n"
            "  }\n"
            "}\n"
        )
        doc = parse_l3(src)
        screen = doc.top_level[0]
        frame = screen.block.statements[0]
        title = frame.block.statements[0]
        subtitle = frame.block.statements[1]

        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [])
        nid_map = {
            id(screen): 100, id(frame): 101,
            id(title): 102, id(subtitle): 103,
        }
        spec_key_map = {
            id(screen): "screen-1", id(frame): "frame-1",
            id(title): "title", id(subtitle): "subtitle",
        }
        original_name_map = dict(spec_key_map)

        edits = list(
            parse_l3(
                "insert into=@frame-1 after=@title {\n"
                "  text #pin \"pin\"\n"
                "}"
            ).edits
        )
        applied = apply_edits(doc, edits)
        a_screen = applied.top_level[0]
        a_frame = a_screen.block.statements[0]
        a_title = a_frame.block.statements[0]
        a_pin = a_frame.block.statements[1]
        a_subtitle = a_frame.block.statements[2]

        out = rebuild_maps_after_edits(
            applied_doc=applied, original_doc=doc, edits=edits,
            old_nid_map=nid_map, old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map, conn=conn,
        )
        # Every PRE-EXISTING node is re-keyed correctly — including
        # subtitle, which shifted from position 1 to position 2.
        assert out.nid_map[id(a_screen)] == 100
        assert out.nid_map[id(a_frame)] == 101
        assert out.nid_map[id(a_title)] == 102
        assert out.nid_map[id(a_subtitle)] == 103
        # The inserted node gets a spec_key + name; no DB nid.
        assert id(a_pin) not in out.nid_map
        assert out.spec_key_map[id(a_pin)] == "pin"

    def test_append_nested_block_all_new_nodes_mapped(self) -> None:
        """Append can introduce a WHOLE subtree — a frame with its
        own children. Every new node needs a spec_key + name so the
        renderer M[] emission reaches them."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [("k-lg", "fig-lg", "button/primary/lg")])
        nid_map = {id(screen): 1, id(frame): 2, id(button): 3}
        spec_key_map = {
            id(screen): "screen-1", id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = dict(spec_key_map)

        edits = list(
            parse_l3(
                "append to=@frame-1 {\n"
                "  frame #wrap {\n"
                "    heading #wrap-title \"title\"\n"
                "    text #wrap-body \"body\"\n"
                "  }\n"
                "}"
            ).edits
        )
        applied = apply_edits(doc, edits)
        a_frame = applied.top_level[0].block.statements[0]
        a_wrap = a_frame.block.statements[1]  # after existing button
        a_wrap_title = a_wrap.block.statements[0]
        a_wrap_body = a_wrap.block.statements[1]

        out = rebuild_maps_after_edits(
            applied_doc=applied, original_doc=doc, edits=edits,
            old_nid_map=nid_map, old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map, conn=conn,
        )
        # Every new node has a spec_key
        assert out.spec_key_map[id(a_wrap)] == "wrap"
        assert out.spec_key_map[id(a_wrap_title)] == "wrap-title"
        assert out.spec_key_map[id(a_wrap_body)] == "wrap-body"

    def test_cousin_eid_collision_resolved_by_path(self) -> None:
        """Grammar §2.3.1 allows cousins (different parents, same
        eid). Path-keyed index must keep them distinct — otherwise
        the second cousin silently overwrites the first in
        ``original_by_path``."""
        src = (
            "screen #screen-1 {\n"
            "  frame #left {\n"
            "    text #twin \"L\"\n"
            "  }\n"
            "  frame #right {\n"
            "    text #twin \"R\"\n"
            "  }\n"
            "}\n"
        )
        doc = parse_l3(src)
        screen = doc.top_level[0]
        left = screen.block.statements[0]
        right = screen.block.statements[1]
        left_twin = left.block.statements[0]
        right_twin = right.block.statements[0]

        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [])
        nid_map = {
            id(screen): 1, id(left): 2, id(right): 3,
            id(left_twin): 10, id(right_twin): 20,
        }
        spec_key_map = {
            id(screen): "screen-1", id(left): "left", id(right): "right",
            id(left_twin): "twin-L", id(right_twin): "twin-R",
        }
        original_name_map = {
            id(screen): "Screen", id(left): "Left", id(right): "Right",
            id(left_twin): "Twin L", id(right_twin): "Twin R",
        }

        # No edits — identity. But the rebuild still exercises the
        # path index, so cousin twins must be distinct.
        applied = apply_edits(
            doc,
            list(parse_l3(
                "append to=@left {\n  text #l-tail \"tail\"\n}"
            ).edits),
        )
        a_left = applied.top_level[0].block.statements[0]
        a_right = applied.top_level[0].block.statements[1]
        a_left_twin = a_left.block.statements[0]
        a_right_twin = a_right.block.statements[0]

        out = rebuild_maps_after_edits(
            applied_doc=applied, original_doc=doc,
            edits=list(parse_l3(
                "append to=@left {\n  text #l-tail \"tail\"\n}"
            ).edits),
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=conn,
        )
        # Both cousin twins preserve their DISTINCT old nids /
        # spec_keys / names — they didn't collide in the path index.
        assert out.nid_map[id(a_left_twin)] == 10
        assert out.nid_map[id(a_right_twin)] == 20
        assert out.spec_key_map[id(a_left_twin)] == "twin-L"
        assert out.spec_key_map[id(a_right_twin)] == "twin-R"

    def test_multiple_swaps_get_distinct_synth_nids(self) -> None:
        """Two swap statements in one edit sequence → two distinct
        synthetic nids. Reuse would break Mode-1 createInstance
        routing."""
        src = (
            "screen #screen-1 {\n"
            "  frame #frame-1 {\n"
            "    -> button/primary/lg #b-a\n"
            "    -> button/primary/lg #b-b\n"
            "  }\n"
            "}\n"
        )
        doc = parse_l3(src)
        screen = doc.top_level[0]
        frame = screen.block.statements[0]
        ba = frame.block.statements[0]
        bb = frame.block.statements[1]

        conn = sqlite3.connect(":memory:")
        _setup_ckr(
            conn,
            [
                ("k-lg", "fig-lg", "button/primary/lg"),
                ("k-sec", "fig-sec", "button/secondary/md"),
                ("k-tert", "fig-tert", "button/tertiary/sm"),
            ],
        )
        nid_map = {id(screen): 1, id(frame): 2, id(ba): 3, id(bb): 4}
        spec_key_map = {
            id(screen): "screen-1", id(frame): "frame-1",
            id(ba): "b-a", id(bb): "b-b",
        }
        original_name_map = dict(spec_key_map)

        edits = list(
            parse_l3(
                "swap @b-a with=-> button/secondary/md\n"
                "swap @b-b with=-> button/tertiary/sm"
            ).edits
        )
        applied = apply_edits(doc, edits)
        a_frame = applied.top_level[0].block.statements[0]
        a_ba = a_frame.block.statements[0]
        a_bb = a_frame.block.statements[1]

        out = rebuild_maps_after_edits(
            applied_doc=applied, original_doc=doc, edits=edits,
            old_nid_map=nid_map, old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map, conn=conn,
        )
        nid_a = out.nid_map[id(a_ba)]
        nid_b = out.nid_map[id(a_bb)]
        # Both swapped, both synth (negative), both distinct.
        assert nid_a < 0
        assert nid_b < 0
        assert nid_a != nid_b
        # Each gets its own CKR patch entry with the correct
        # figma_id for its new master.
        assert out.db_visuals_patch[nid_a]["component_figma_id"] == "fig-sec"
        assert out.db_visuals_patch[nid_b]["component_figma_id"] == "fig-tert"

    def test_swap_to_master_not_in_ckr_raises(self) -> None:
        """If the LLM asked for a master the CKR doesn't know about,
        we refuse — the renderer would fall through to a wireframe
        placeholder, which is never what the demo wanted."""
        doc, screen, frame, button = _parse_fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [("k-lg", "fig-lg", "button/primary/lg")])

        nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        original_name_map = {
            id(screen): "Screen",
            id(frame): "Frame",
            id(button): "Button",
        }

        edits = list(
            parse_l3(
                "swap @button-1 with=-> button/never/heard/of/it"
            ).edits
        )
        applied = apply_edits(doc, edits)

        with pytest.raises(SwapUnresolvedInCKR) as exc_info:
            rebuild_maps_after_edits(
                applied_doc=applied,
                original_doc=doc,
                edits=edits,
                old_nid_map=nid_map,
                old_spec_key_map=spec_key_map,
                old_original_name_map=original_name_map,
                conn=conn,
            )
        assert "button/never/heard/of/it" in str(exc_info.value)


class TestAdjustSpecElementsForEdits:
    def test_empty_edits_passthrough(self) -> None:
        """No edits → returned dict is a shallow copy of the original."""
        elements = {
            "screen-1": {"type": "screen", "visual": {"fills": []}},
            "button-1": {
                "type": "button",
                "comp_ref": "button/primary/lg",
                "visual": {
                    "fills": [{"type": "solid", "color": "#FF0000"}],
                    "strokes": [{"type": "solid", "color": "#000000"}],
                    "effects": [{"type": "drop_shadow"}],
                },
            },
        }

        out = adjust_spec_elements_for_edits(elements, edits=[])
        assert out == elements
        # Not a mutation of the input
        assert out is not elements

    def test_swap_drops_old_visuals_on_target(self) -> None:
        """When the eid is swapped, its ``visual.fills/strokes/effects``
        describe the OLD master — the new master supplies its own at
        render time via ``createInstance``. Dropping them keeps the
        verifier's fill/stroke/effect comparison skipped (it's gated on
        both sides having lists).
        """
        elements = {
            "button-1": {
                "type": "button",
                "comp_ref": "button/primary/lg",
                "children": [],
                "props": {"text": "Sign in"},
                "visual": {
                    "fills": [{"type": "solid", "color": "#FF0000"}],
                    "strokes": [{"type": "solid", "color": "#000000"}],
                    "effects": [{"type": "drop_shadow"}],
                },
                "layout": {"sizing": {"widthPixels": 120, "heightPixels": 44}},
            },
        }

        edits = list(
            parse_l3("swap @button-1 with=-> button/secondary/md").edits
        )
        out = adjust_spec_elements_for_edits(elements, edits=edits)

        btn = out["button-1"]
        vis = btn.get("visual") or {}
        # Lists stripped → verifier fill/stroke/effect compare skipped
        assert vis.get("fills") in (None, [])
        assert vis.get("strokes") in (None, [])
        assert vis.get("effects") in (None, [])
        # Comp-ref path updated to the new master
        assert btn["comp_ref"] == "button/secondary/md"
        # Type + layout preserved (sizing still needed by placeholder
        # fallback in _emit_mode1_create)
        assert btn["type"] == "button"
        assert btn["layout"]["sizing"]["widthPixels"] == 120

    def test_multiple_swaps_all_applied(self) -> None:
        elements = {
            "btn-a": {
                "type": "button",
                "comp_ref": "button/primary/lg",
                "visual": {"fills": [{"type": "solid", "color": "#FF0000"}]},
            },
            "btn-b": {
                "type": "button",
                "comp_ref": "button/primary/lg",
                "visual": {"fills": [{"type": "solid", "color": "#00FF00"}]},
            },
        }
        edits = list(
            parse_l3(
                "swap @btn-a with=-> button/secondary/md\n"
                "swap @btn-b with=-> button/tertiary/sm"
            ).edits
        )
        out = adjust_spec_elements_for_edits(elements, edits=edits)
        assert out["btn-a"]["comp_ref"] == "button/secondary/md"
        assert out["btn-b"]["comp_ref"] == "button/tertiary/sm"
        assert out["btn-a"]["visual"].get("fills") in (None, [])
        assert out["btn-b"]["visual"].get("fills") in (None, [])


class TestRenderAppliedDoc:
    """End-to-end wiring: rebuild_maps + adjust_spec_elements +
    render_figma produce a Figma script that emits
    ``createInstance`` against the *new* master's CKR figma_node_id.

    Uses a hand-built spec/doc pair to avoid coupling to the
    compressor's DB lookups — the pieces under test are the
    apply_render wrapper's wiring, not the compressor.
    """

    def _fixture(self) -> tuple[dict[str, Any], object, object, object, object]:
        """Build a minimal spec + compressed L3 shape by hand."""
        doc, screen, frame, button = _parse_fixture()
        spec = {
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "children": ["frame-1"],
                    "props": {},
                    "layout": {"sizing": {
                        "widthPixels": 375, "heightPixels": 812,
                    }},
                    "visual": {},
                },
                "frame-1": {
                    "type": "frame",
                    "children": ["button-1"],
                    "props": {},
                    "layout": {},
                    "visual": {},
                },
                "button-1": {
                    "type": "button",
                    "comp_ref": "button/primary/lg",
                    "children": [],
                    "props": {},
                    "layout": {"sizing": {
                        "widthPixels": 120, "heightPixels": 44,
                    }},
                    "visual": {
                        "fills": [{"type": "solid", "color": "#FF0000"}],
                    },
                },
            },
            "tokens": {},
        }
        return spec, doc, screen, frame, button

    def test_rendered_script_targets_new_master_via_ckr_lookup(self) -> None:
        """After a swap, the emitted Phase 1 block must call
        ``getNodeByIdAsync("fig-md-NEW")`` — the new master's CKR
        figma_node_id — not the old one. That's what Mode-1
        ``createInstance`` needs to produce the right INSTANCE."""
        spec, doc, screen, frame, button = self._fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(
            conn,
            [
                ("k-lg", "fig-lg", "button/primary/lg"),
                ("k-md", "fig-md-NEW", "button/secondary/md"),
            ],
        )

        # Pretend the compressor produced these three maps. The button
        # row's db_visuals has a component_figma_id — that's how the
        # unswapped render resolves Mode 1.
        old_nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        old_spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        old_original_name_map = {
            id(screen): "Screen 1",
            id(frame): "Frame 1",
            id(button): "Button/Primary/Lg",
        }
        db_visuals = {
            1001: {"node_type": "FRAME"},
            1002: {"node_type": "FRAME"},
            1003: {
                "node_type": "INSTANCE",
                "component_figma_id": "fig-lg",
                "component_key": "k-lg",
                "figma_node_id": "inst-1003",
            },
        }

        edits = list(
            parse_l3("swap @button-1 with=-> button/secondary/md").edits
        )
        applied = apply_edits(doc, edits)

        out = render_applied_doc(
            applied_doc=applied,
            original_doc=doc,
            edits=edits,
            spec=spec,
            conn=conn,
            db_visuals=db_visuals,
            fonts=[("Inter", "Regular")],
            old_nid_map=old_nid_map,
            old_spec_key_map=old_spec_key_map,
            old_original_name_map=old_original_name_map,
            ckr_built=True,
        )

        assert isinstance(out, RenderedApplied)
        # Script references the NEW master — both in the prefetch and
        # in the Mode-1 createInstance emission.
        assert "fig-md-NEW" in out.script
        # The swap target's Mode-1 block must invoke createInstance
        # against the NEW master, not the old one. We key on the
        # error-handler kind=create_instance_failed + id field.
        assert (
            'kind:"create_instance_failed", id:"fig-md-NEW"'
            in out.script
        )
        # Conversely, no createInstance for the old master — the old
        # master may appear in the prefetch (it's still in db_visuals)
        # but shouldn't drive any createInstance call.
        assert (
            'kind:"create_instance_failed", id:"fig-lg"'
            not in out.script
        )
        # The swap target still writes its eid into the M map so the
        # verifier can find it after the walk.
        assert 'M["button-1"]' in out.script
        # The adjusted spec has the new comp_ref + null visual fills
        btn = out.adjusted_spec["elements"]["button-1"]
        assert btn["comp_ref"] == "button/secondary/md"
        assert (btn.get("visual") or {}).get("fills") in (None, [])

    def test_no_edits_renders_identical_to_baseline_spec(self) -> None:
        """When no edits fire, render_applied_doc should emit the
        same script as the original render path would have produced."""
        spec, doc, screen, frame, button = self._fixture()
        conn = sqlite3.connect(":memory:")
        _setup_ckr(conn, [("k-lg", "fig-lg", "button/primary/lg")])
        old_nid_map = {id(screen): 1001, id(frame): 1002, id(button): 1003}
        old_spec_key_map = {
            id(screen): "screen-1",
            id(frame): "frame-1",
            id(button): "button-1",
        }
        old_original_name_map = {
            id(screen): "Screen 1",
            id(frame): "Frame 1",
            id(button): "Button/Primary/Lg",
        }
        db_visuals = {
            1003: {
                "node_type": "INSTANCE",
                "component_figma_id": "fig-lg",
                "component_key": "k-lg",
                "figma_node_id": "inst-1003",
            },
        }

        out = render_applied_doc(
            applied_doc=doc,
            original_doc=doc,
            edits=[],
            spec=spec,
            conn=conn,
            db_visuals=db_visuals,
            fonts=[("Inter", "Regular")],
            old_nid_map=old_nid_map,
            old_spec_key_map=old_spec_key_map,
            old_original_name_map=old_original_name_map,
        )
        assert "fig-lg" in out.script
        assert out.applied_maps.db_visuals_patch == {}


class TestWalkRenderedViaBridge:
    """Guard-rail tests for the bridge wrapper. The live-bridge smoke
    test is a separate integration asset — here we check error paths
    that don't require a running WebSocket server plus the
    success-path contract via a subprocess stub."""

    def test_raises_when_walk_script_missing(self, tmp_path) -> None:
        bogus = tmp_path / "does-not-exist.js"
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;",
                walk_script=bogus,
            )
        assert "walk script not found" in str(exc.value)

    def test_raises_when_node_binary_missing(
        self, tmp_path, monkeypatch,
    ) -> None:
        """If PATH has no node binary and caller passed no explicit
        path, we fail loud with BridgeError (never try to guess)."""
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;",
                walk_script=walk,
            )
        assert "node" in str(exc.value).lower()

    def test_success_path_returns_parsed_json(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Subprocess exits 0 + writes a valid JSON payload → the
        wrapper returns the parsed dict."""
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        fake_node = tmp_path / "node"
        fake_node.write_text("#!/bin/sh\necho stub")
        fake_node.chmod(0o755)
        monkeypatch.setattr("shutil.which", lambda _: str(fake_node))

        expected = {"__ok": True, "eid_map": {"screen-1": {"type": "FRAME"}}}

        def fake_run(cmd, *args, **kwargs):
            # cmd = [node_binary, walk_script, script_path, out_path, port]
            out_path = Path(cmd[3])
            out_path.write_text(json.dumps(expected))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)

        payload = walk_rendered_via_bridge(
            script="const x = 1;", walk_script=walk,
        )
        assert payload == expected

    def test_raises_on_nonzero_exit(self, tmp_path, monkeypatch) -> None:
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="",
                stderr="FAIL: Execution timed out after 170000ms",
            )

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;", walk_script=walk,
            )
        assert "exited 1" in str(exc.value)
        assert "timed out" in str(exc.value)

    def test_raises_on_timeout(self, tmp_path, monkeypatch) -> None:
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;", walk_script=walk, timeout=5.0,
            )
        assert "timed out after 5.0s" in str(exc.value)

    def test_raises_when_output_is_invalid_json(
        self, tmp_path, monkeypatch,
    ) -> None:
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            Path(cmd[3]).write_text("not valid json {")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;", walk_script=walk,
            )
        assert "invalid JSON" in str(exc.value)

    def test_raises_when_output_file_missing(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Subprocess exits 0 but never wrote the output — usually
        means the wrapper script died after the PROXY_EXECUTE reply
        but before fs.writeFileSync. Surface a clear BridgeError."""
        walk = tmp_path / "walk_ref.js"
        walk.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            walk_rendered_via_bridge(
                script="const x = 1;", walk_script=walk,
            )
        assert "no output JSON" in str(exc.value)


class TestExecuteScriptViaBridge:
    """Fire-and-ack wrapper: send a Figma script to the plugin bridge
    without walking the rendered tree.

    M1 of the authoring-loop Figma round-trip needs to run the generated
    `render_applied_doc` script in the user's live Figma session, with
    no downstream verification — the visible canvas IS the demo. Walking
    would add 30-60s per call and expose the demo to every walk-class
    failure mode (large trees, hidden subtrees under
    skipInvisibleInstanceChildren) for no benefit.

    The wrapper shells out to a thin Node script
    (`render_test/execute_ref.js`) that opens a WebSocket to the bridge,
    sends `{type: "PROXY_EXECUTE", id, code, timeout}`, and waits for
    the `PROXY_EXECUTE_RESULT` ack. Any bridge-side error surfaces as
    BridgeError — same shape as `walk_rendered_via_bridge`."""

    def test_raises_when_execute_script_missing(self, tmp_path) -> None:
        bogus = tmp_path / "does-not-exist.js"
        with pytest.raises(BridgeError) as exc:
            execute_script_via_bridge(
                script="const x = 1;",
                execute_script=bogus,
            )
        assert "execute script not found" in str(exc.value)

    def test_raises_when_node_binary_missing(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Same invariant as walk: no silent fallback — caller must
        surface the missing-node case explicitly."""
        execute = tmp_path / "execute_ref.js"
        execute.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(BridgeError) as exc:
            execute_script_via_bridge(
                script="const x = 1;",
                execute_script=execute,
            )
        assert "node" in str(exc.value).lower()

    def test_success_path_returns_bridge_ack(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Subprocess exits 0 → the wrapper returns an ack dict that
        carries the PROXY_EXECUTE_RESULT payload (errors list + any
        returned M references the caller may want to log).

        The execute helper writes an ack JSON to out_path the same way
        walk_ref does, but the payload shape is
        `{__ok: bool, errors: [...], request_id: str}` — no eid_map,
        no rendered_root, no counts. Only what the bridge itself
        reported back."""
        execute = tmp_path / "execute_ref.js"
        execute.write_text("// stub")
        fake_node = tmp_path / "node"
        fake_node.write_text("#!/bin/sh\necho stub")
        fake_node.chmod(0o755)
        monkeypatch.setattr("shutil.which", lambda _: str(fake_node))

        expected = {
            "__ok": True,
            "errors": [],
            "request_id": "exec_123",
        }

        def fake_run(cmd, *args, **kwargs):
            out_path = Path(cmd[3])
            out_path.write_text(json.dumps(expected))
            return subprocess.CompletedProcess(
                cmd, 0, stdout="", stderr="",
            )

        monkeypatch.setattr("subprocess.run", fake_run)

        payload = execute_script_via_bridge(
            script="const x = 1;", execute_script=execute,
        )
        assert payload == expected

    def test_raises_on_nonzero_exit_with_bridge_error(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Codex's risk — silent partial execution. When the bridge
        replies `{error: "..."}` or times out, the Node wrapper exits
        non-zero with the message on stderr. Surface it verbatim so a
        demo failure looks like `bridge rejected: ...`, not `Figma is
        slow`."""
        execute = tmp_path / "execute_ref.js"
        execute.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="",
                stderr="FAIL: PROXY_EXECUTE rejected: bad script",
            )

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            execute_script_via_bridge(
                script="const x = 1;", execute_script=execute,
            )
        assert "exited 1" in str(exc.value)
        assert "bad script" in str(exc.value)

    def test_raises_on_timeout(self, tmp_path, monkeypatch) -> None:
        execute = tmp_path / "execute_ref.js"
        execute.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        def fake_run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(BridgeError) as exc:
            execute_script_via_bridge(
                script="const x = 1;",
                execute_script=execute,
                timeout=5.0,
            )
        assert "timed out after 5.0s" in str(exc.value)

    def test_sends_configured_ws_port_in_cmd(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The ws_port arg is what routes the demo to the user's
        bridge (Desktop Bridge picks between 9223-9231 depending on
        what's bound). Explicitly confirm the value is passed through
        to the subprocess — a silent default would send the demo to
        the wrong port."""
        execute = tmp_path / "execute_ref.js"
        execute.write_text("// stub")
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/node")

        captured_cmds: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            Path(cmd[3]).write_text(
                json.dumps({"__ok": True, "errors": [], "request_id": "x"})
            )
            return subprocess.CompletedProcess(
                cmd, 0, stdout="", stderr="",
            )

        monkeypatch.setattr("subprocess.run", fake_run)

        execute_script_via_bridge(
            script="const x = 1;",
            execute_script=execute,
            ws_port=9231,
        )
        assert captured_cmds
        assert "9231" in captured_cmds[0]


class TestRebuildMapsStrictCoverage:
    """Opt-in invariant on ``rebuild_maps_after_edits``: when the
    caller passes ``strict_mapping=<floor>``, the function must raise
    :class:`DegradedMapping` if ``nid_map`` covers less than
    ``floor`` fraction of the applied-doc nodes whose eid-chain paths
    also appear in the original doc (the "expected survivors").

    Rationale from the 2026-04-24 M1 live-capstone bug — a silent
    wrapper-collapse mismatch produced 0/109 nid_map coverage on a
    pure-delete session; every surviving node fell to Mode-2
    cheap-emission and the Figma render came out as an empty frame.
    The function reported success. Codex's framing: don't flag on a
    flat floor — measure against expected survivors so legit heavy-
    delete edits don't false-positive.

    The CLI's demo path (``dd design --render-to-figma``) passes
    ``strict_mapping=0.9`` so the next wrapper-collapse-class bug
    surfaces as a loud BridgeError equivalent rather than a blank
    render that looks successful."""

    def _setup_maps(self):
        from dd.markup_l3 import apply_edits, parse_l3
        # 30+ node fixture so the M1-class (root-only survivor) is
        # clearly distinguishable from floor=0.9. The shape-mismatch
        # case collapses to ~1 mapped over ~30 eligible (3.3%), well
        # below any reasonable floor.
        #
        # Structure: screen > header/main/footer, each with nested
        # frames + texts. Total = 1 screen + 3 section frames
        # + 3 sub-frames + 24 text/button leaves = 31 nodes.
        chunks = ["screen #s1 {\n"]
        for sect in ("header", "main", "footer"):
            chunks.append(f"  frame #{sect} {{\n")
            for sub_i in range(1, 3):
                chunks.append(
                    f"    frame #{sect}-sub{sub_i} {{\n"
                )
                for leaf_i in range(1, 5):
                    chunks.append(
                        f"      text #{sect}-sub{sub_i}-t{leaf_i} "
                        f'"leaf-{sect}-{sub_i}-{leaf_i}"\n'
                    )
                chunks.append("    }\n")
            chunks.append("  }\n")
        chunks.append("}\n")
        doc = parse_l3("".join(chunks))
        # Fake nid map with entries for every node in the original doc.
        from dd.markup_l3 import Node
        nodes = []
        q = list(doc.top_level)
        while q:
            n = q.pop(0)
            if isinstance(n, Node):
                nodes.append(n)
                if n.block is not None:
                    q.extend(n.block.statements)
        nid_map = {id(n): 1000 + i for i, n in enumerate(nodes)}
        spec_key_map = {id(n): n.head.eid for n in nodes}
        original_name_map = {id(n): n.head.eid for n in nodes}
        return doc, nid_map, spec_key_map, original_name_map

    @staticmethod
    def _build_wrapper_collapse_applied():
        """Parse an applied doc with the same eids as ``_setup_maps``
        but wrapped under an extra frame. Every descendant's eid-path
        shifts by one level, so path-based rebuild misses the old
        nid_map; eid set still overlaps at ~100%. This is the M1
        2026-04-24 wrapper-collapse regression class."""
        from dd.markup_l3 import parse_l3
        chunks = ["screen #s1 {\n  frame #wrapper-extra {\n"]
        for sect in ("header", "main", "footer"):
            chunks.append(f"    frame #{sect} {{\n")
            for sub_i in range(1, 3):
                chunks.append(f"      frame #{sect}-sub{sub_i} {{\n")
                for leaf_i in range(1, 5):
                    chunks.append(
                        f"        text #{sect}-sub{sub_i}-t{leaf_i} "
                        f'"leaf-{sect}-{sub_i}-{leaf_i}"\n'
                    )
                chunks.append("      }\n")
            chunks.append("    }\n")
        chunks.append("  }\n}\n")
        return parse_l3("".join(chunks))

    def test_strict_mapping_passes_on_well_aligned_trees(self):
        """When applied and original were compressed with the same
        settings, path-match covers every eligible surviving node —
        coverage is 100% and strict_mapping succeeds."""
        from dd.markup_l3 import apply_edits, parse_l3
        orig, nid_map, spec_key_map, original_name_map = (
            self._setup_maps()
        )
        # Pure-delete edit: drop one leaf. Every other node stays
        # eid-matched + path-matched with 100% nid_map coverage.
        edit_doc = parse_l3("delete @header-sub1-t1\n")
        applied = apply_edits(orig, list(edit_doc.edits))
        # Pass the strict floor — should not raise.
        maps = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=orig,
            edits=list(edit_doc.edits),
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=None,  # no swaps in this test, conn unused
            strict_mapping=0.9,
        )
        # Applied doc = 34 orig nodes − 1 deleted leaf = 33. All
        # remaining eids exist in original, all paths match, all
        # get nid_map entries.
        from dd.markup_l3 import Node
        applied_nodes = []
        q = list(applied.top_level)
        while q:
            n = q.pop(0)
            if isinstance(n, Node):
                applied_nodes.append(n)
                if n.block is not None:
                    q.extend(n.block.statements)
        assert len(applied_nodes) == 33
        assert len(maps.nid_map) == 33

    def test_strict_mapping_raises_on_shape_mismatch(self):
        """When applied and original were compressed with different
        wrapper shapes (the M1 regression class), every descendant
        eid-path shifts under the extra wrapper. Path-based rebuild
        can't carry forward the old nid_map — only root survives.
        Coverage plummets to 1/34 ≈ 2.9%, well below 0.9 floor.

        eid_overlap stays at 100% (the wrapper just adds one new
        eid to applied, so overlap = 34/35 against min=34). That
        satisfies the >0.8 second-check guard, so the invariant
        fires and names the compression-shape cause."""
        from dd.apply_render import DegradedMapping
        from dd.markup_l3 import parse_l3
        orig, nid_map, spec_key_map, original_name_map = (
            self._setup_maps()
        )
        applied = self._build_wrapper_collapse_applied()
        # Non-empty edit list so rebuild_maps_after_edits doesn't
        # short-circuit back to identity maps.
        edits = list(parse_l3("delete @non-existent-eid\n").edits)
        with pytest.raises(DegradedMapping) as exc:
            rebuild_maps_after_edits(
                applied_doc=applied,
                original_doc=orig,
                edits=edits,
                old_nid_map=nid_map,
                old_spec_key_map=spec_key_map,
                old_original_name_map=original_name_map,
                conn=None,
                strict_mapping=0.9,
            )
        msg = str(exc.value)
        # Diagnostic names coverage ratio, eid_overlap, AND points
        # at compression-shape as the likely cause (Codex's risk
        # note — fail with context, not just a number).
        assert "coverage" in msg.lower() or "mapped" in msg.lower()
        assert "eid_overlap" in msg.lower()
        assert "wrapper" in msg.lower() or "compress" in msg.lower()

    def test_no_strict_mapping_defaults_silent(self):
        """The invariant is OPT-IN. Callers that don't pass
        strict_mapping get the historical silent-degradation
        behavior — Mode-3 composition, synthetic-gen, and all the
        pre-existing tests continue to work unchanged. A case that
        WOULD raise under strict_mapping=0.9 must pass silently
        when no strict_mapping is given."""
        from dd.markup_l3 import parse_l3
        orig, nid_map, spec_key_map, original_name_map = (
            self._setup_maps()
        )
        applied = self._build_wrapper_collapse_applied()
        edits = list(parse_l3("delete @non-existent-eid\n").edits)
        # No strict_mapping kwarg → no raise, even though coverage
        # is 2.9%.
        maps = rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=orig,
            edits=edits,
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=None,
        )
        # Only root s1 gets carried forward (same eid-path in both
        # trees). Everything below diverges by the wrapper-extra
        # level. Silent degradation: most nodes fall to Mode-2
        # cheap-emit with no DB nid. This is the historical
        # behavior the M1 bug rode on.
        assert len(maps.nid_map) == 1

    def test_strict_mapping_handles_heavy_delete_without_false_positive(
        self,
    ):
        """Codex's framing: the invariant must not false-positive on
        legit heavy deletes. Measure against "eligible" (applied-doc
        nodes whose head.eid is in the original) rather than a flat
        fraction of applied-doc nodes.

        A session that deletes 80% of the tree should still pass
        strict_mapping=0.9 if the remaining 20% are all correctly
        eid-matched."""
        from dd.markup_l3 import apply_edits, parse_l3
        orig, nid_map, spec_key_map, original_name_map = (
            self._setup_maps()
        )
        # Delete many leaves across the tree — heavy delete.
        heavy_delete = "\n".join(
            f"delete @header-sub1-t{i}"
            for i in range(1, 5)
        ) + "\n" + "\n".join(
            f"delete @main-sub1-t{i}"
            for i in range(1, 5)
        ) + "\n" + "\n".join(
            f"delete @footer-sub2-t{i}"
            for i in range(1, 5)
        ) + "\n"
        edit_doc = parse_l3(heavy_delete)
        applied = apply_edits(orig, list(edit_doc.edits))
        # Should succeed: surviving nodes all eid-match the original.
        rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=orig,
            edits=list(edit_doc.edits),
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=None,
            strict_mapping=0.9,
        )

    def test_strict_mapping_passes_on_heavy_append_with_reused_eids(
        self,
    ):
        """Codex's eid_overlap risk note: a session can legitimately
        introduce new subtrees whose eids collide with eids already
        elsewhere in the original doc. Grammar §2.3.1 only forbids
        duplicate eids within a parent block — cousin subtrees can
        reuse eids freely.

        In that case the applied doc's eid set is a superset of the
        original's (new nodes use reused-from-elsewhere eids), but
        those new nodes wouldn't be in the nid_map. Coverage could
        look low, but it's a legitimate append pattern — not a
        compression-shape mismatch.

        The eid_overlap > 0.8 guard keeps this case quiet: applied
        has every original eid + new ones, so ``|applied ∩ orig| /
        min(|applied|, |orig|)`` = 1.0 (all original eids present),
        but the invariant should still not fire because coverage is
        high against the *eligible* set.

        Edge case: if the reused eids cause applied_eids to contain
        many duplicates, eid_overlap stays high and coverage stays
        high — the invariant passes cleanly."""
        from dd.markup_l3 import apply_edits, parse_l3
        orig, nid_map, spec_key_map, original_name_map = (
            self._setup_maps()
        )
        # Append a new subtree to footer whose children reuse eids
        # that exist elsewhere in the tree (legal — different
        # parents). The new nodes have fresh id()s and no nid_map
        # entry.
        append_src = (
            "append to=@footer {\n"
            "  frame #new-section {\n"
            # These eids already exist in header / main subtrees —
            # legal to reuse under different parents.
            "    text #header-sub1-t1 \"reused-from-header\"\n"
            "    text #main-sub1-t2 \"reused-from-main\"\n"
            "  }\n"
            "}\n"
        )
        edit_doc = parse_l3(append_src)
        applied = apply_edits(orig, list(edit_doc.edits))
        # Should NOT raise: the original 30+ nodes all eid-match and
        # are covered by nid_map. The 3 new nodes (new-section +
        # 2 text children) add to the eligible pool because their
        # eids happen to be in the original, but those new id()s
        # aren't in nid_map. Coverage drops from 100% to ~94%
        # (30/32), still above the 0.9 floor. Even if it dropped
        # below, the eid_overlap guard would keep quiet because
        # applied introduces a new eid (`new-section`) that isn't
        # in the original — eid_overlap = 30/31 ≈ 0.97, still >0.8,
        # so this test verifies the coverage stays high enough
        # even when the eid_overlap guard cannot save it.
        rebuild_maps_after_edits(
            applied_doc=applied,
            original_doc=orig,
            edits=list(edit_doc.edits),
            old_nid_map=nid_map,
            old_spec_key_map=spec_key_map,
            old_original_name_map=original_name_map,
            conn=None,
            strict_mapping=0.9,
        )
