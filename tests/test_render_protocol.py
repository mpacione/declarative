"""Tests for the multi-backend Renderer protocol (Tier C.1).

The scope is the protocol's shape, not the backend's internal
correctness (FigmaRenderer's wrappers are thin — the underlying
modules have their own test suites).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dd.boundary import RenderReport
from dd.render_protocol import (
    FigmaRenderer,
    RenderArtifact,
    Renderer,
    WalkResult,
)


class TestProtocolShape:
    def test_artifact_dataclass_required_fields(self) -> None:
        a = RenderArtifact(
            kind="figma-js", payload="const M = {};",
            metadata={"token_refs": []},
        )
        assert a.kind == "figma-js"
        assert a.payload.startswith("const M")
        assert a.metadata["token_refs"] == []

    def test_walkresult_dataclass_required_fields(self) -> None:
        w = WalkResult(
            ok=True,
            eid_map={"screen-1": {"type": "FRAME"}},
            errors=[],
            raw={"__ok": True},
        )
        assert w.ok is True
        assert w.eid_map["screen-1"]["type"] == "FRAME"
        assert w.errors == []

    def test_renderer_is_abstract(self) -> None:
        """Can't instantiate the protocol directly."""
        with pytest.raises(TypeError):
            Renderer()  # type: ignore[abstract]


class TestFigmaRenderer:
    def test_backend_identifier(self) -> None:
        assert FigmaRenderer.backend == "figma"

    def test_render_wraps_render_figma_ast(self) -> None:
        """FigmaRenderer.render delegates to render_figma_ast."""
        renderer = FigmaRenderer()
        fake_ast = MagicMock(name="L3Document")
        ctx = {
            "conn": MagicMock(),
            "nid_map": {},
            "fonts": [("Inter", "Regular")],
            "spec_key_map": {},
        }
        with patch(
            "dd.render_figma_ast.render_figma",
            return_value=("SCRIPT", [("eid", "prop", "tok")]),
        ) as mock_render:
            artifact = renderer.render(fake_ast, ctx=ctx)
        mock_render.assert_called_once()
        assert artifact.kind == "figma-js"
        assert artifact.payload == "SCRIPT"
        assert artifact.metadata["token_refs"] == [("eid", "prop", "tok")]

    def test_walk_wraps_apply_render_bridge(self) -> None:
        renderer = FigmaRenderer()
        artifact = RenderArtifact(
            kind="figma-js", payload="const M = {};", metadata={},
        )
        fake_payload = {
            "__ok": True,
            "eid_map": {"screen-1": {"type": "FRAME"}},
            "errors": [{"kind": "some_error", "error": "e"}],
        }
        with patch(
            "dd.apply_render.walk_rendered_via_bridge",
            return_value=fake_payload,
        ) as mock_walk:
            result = renderer.walk(
                artifact,
                ctx={"ws_port": 9228, "timeout": 60.0},
            )
        mock_walk.assert_called_once_with(
            script="const M = {};",
            ws_port=9228,
            timeout=60.0,
            node_binary=None,
            keep_artifacts=False,
            artifact_dir=None,
        )
        assert result.ok is True
        assert result.eid_map == {"screen-1": {"type": "FRAME"}}
        assert len(result.errors) == 1

    def test_walk_with_default_ctx(self) -> None:
        """Passing no ctx defaults to port 9228 / 320s timeout.
        Outer Python watchdog must exceed walk_ref.js's 310s client
        watchdog, which itself exceeds the 300s PROXY_EXECUTE cap
        (Phase 1 perf 2026-04-22 — bumped from 170s, which was ours
        not Figma's)."""
        renderer = FigmaRenderer()
        artifact = RenderArtifact(
            kind="figma-js", payload="x", metadata={},
        )
        with patch(
            "dd.apply_render.walk_rendered_via_bridge",
            return_value={"__ok": True, "eid_map": {}, "errors": []},
        ) as mock_walk:
            renderer.walk(artifact)
        assert mock_walk.call_args.kwargs["ws_port"] == 9228
        assert mock_walk.call_args.kwargs["timeout"] == 320.0

    def test_walk_passes_walk_script_through_ctx(self) -> None:
        """Docstring lists walk_script as a valid ctx key — verify
        it's actually wired through."""
        renderer = FigmaRenderer()
        artifact = RenderArtifact(
            kind="figma-js", payload="x", metadata={},
        )
        from pathlib import Path
        walk_script = Path("render_test/walk_ref.js")
        with patch(
            "dd.apply_render.walk_rendered_via_bridge",
            return_value={"__ok": True, "eid_map": {}, "errors": []},
        ) as mock_walk:
            renderer.walk(artifact, ctx={"walk_script": walk_script})
        assert mock_walk.call_args.kwargs["walk_script"] == walk_script

    def test_verify_wraps_figma_render_verifier(self) -> None:
        renderer = FigmaRenderer()
        ir = {"root": "screen-1", "elements": {"screen-1": {"type": "screen"}}}
        walk = WalkResult(
            ok=True,
            eid_map={"screen-1": {"type": "FRAME"}},
            errors=[],
            raw={},
        )
        report = renderer.verify(ir, walk)
        assert isinstance(report, RenderReport)
        assert report.backend == "figma"
        assert report.ir_node_count == 1
        assert report.rendered_node_count == 1
        assert report.is_parity is True


class TestProtocolSwappability:
    """Prove the protocol works with a non-Figma stub impl."""

    def test_custom_backend_satisfies_protocol(self) -> None:
        class StubRenderer(Renderer):
            backend = "stub"

            def render(self, ast, *, ctx):
                return RenderArtifact(
                    kind="stub", payload=str(ast), metadata={},
                )

            def walk(self, artifact, *, ctx=None):
                return WalkResult(
                    ok=True, eid_map={"stub-1": {"type": "STUB"}},
                    errors=[], raw={},
                )

            def verify(self, ir, walk):
                return RenderReport(
                    backend=self.backend,
                    ir_node_count=0,
                    rendered_node_count=0,
                    errors=[],
                )

        r = StubRenderer()
        artifact = r.render("ast", ctx={})
        assert artifact.kind == "stub"
        walk = r.walk(artifact)
        assert walk.ok is True
        report = r.verify({}, walk)
        assert report.backend == "stub"
