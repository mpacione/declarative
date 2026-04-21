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
