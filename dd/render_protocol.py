"""Multi-backend render protocol.

Declares the interface every backend implementation (Figma today,
React/HTML/Android later) must satisfy. Pencils in the abstraction
before the scorer / repair loop / forensics bind to Figma-specific
code.

Per `docs/plan-burndown.md` Tier C.1: even though only Figma ships
today, exposing the protocol here makes every downstream tool
multi-backend-ready by construction. The cost to the Figma-only
case is near-zero — ``FigmaRenderer`` is a thin wrapper around
``render_figma`` + ``walk_rendered_via_bridge`` + ``FigmaRenderVerifier``.

Architectural boundaries:
  - ``render(ast, ctx) -> RenderArtifact``: pure compile. No
    external IO; emits the script (or whatever the backend's
    rendering representation is) as bytes.
  - ``walk(artifact) -> WalkResult``: execute + observe. Usually
    touches the external world (Figma plugin bridge, headless
    browser, etc.). Returns a dict-keyed-by-eid tree.
  - ``verify(ast, walk) -> RenderReport``: pure diff. Produces the
    StructuredError list (ADR-007).

Each backend implements these three. The scorer (``dd.fidelity_score``)
consumes the output of ``walk`` and ``verify``, not the backend
internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from dd.boundary import RenderReport


@dataclass
class RenderArtifact:
    """The output of ``Renderer.render``. Backend-specific payload
    plus metadata for the walk step to consume.

    ``payload`` is whatever the backend's execute step takes — a
    JS string for Figma, possibly HTML + CSS for React, a layout
    JSON for Android. Deliberately opaque.

    ``metadata`` carries sidecar info (fonts, token refs,
    diagnostic channels). ``kind`` tags the payload type for
    callers that need to route.
    """

    kind: str
    payload: str
    metadata: dict[str, Any]


@dataclass
class WalkResult:
    """The rendered-tree observation backing ``Renderer.walk``.

    Invariants (all backends):
      - ``ok`` is True when the render executed end-to-end
        (possibly with per-node errors inside ``errors``).
      - ``eid_map`` is keyed on the spec_key / eid that the
        verifier's IR uses. Backends MUST normalise to whatever
        key the verifier compares against (e.g. Figma uses the
        ``M[<spec_key>] = nN.id`` channel).
      - ``errors`` is a list of per-node diagnostics in the
        ``StructuredError``-compatible shape (at minimum a
        ``kind`` + ``error`` string; ideally ``id`` + ``context``).
    """

    ok: bool
    eid_map: dict[str, dict[str, Any]]
    errors: list[dict[str, Any]]
    raw: dict[str, Any]  # backend-native payload for debugging


class Renderer(ABC):
    """Protocol every backend implements.

    ``backend`` is a class-level identifier (``"figma"``, ``"react"``
    in the future). The scorer + forensic tools route per-backend
    rules off this.
    """

    backend: str

    @abstractmethod
    def render(
        self,
        ast: Any,
        *,
        ctx: dict[str, Any],
    ) -> RenderArtifact:
        """AST + context → ``RenderArtifact``. Pure; no external IO."""

    @abstractmethod
    def walk(
        self,
        artifact: RenderArtifact,
        *,
        ctx: Optional[dict[str, Any]] = None,
    ) -> WalkResult:
        """Execute the artifact + observe the rendered tree. May
        do external IO (Figma plugin bridge, headless browser,
        etc.). Raises :class:`dd.apply_render.BridgeError` (or a
        backend-specific equivalent) when the execution
        environment is unreachable."""

    @abstractmethod
    def verify(
        self,
        ir: Any,
        walk: WalkResult,
    ) -> RenderReport:
        """Pure diff of IR-expected against observed rendered tree.
        Returns the standard :class:`RenderReport` so the repair
        loop + scorer can consume across backends."""


# ---------------------------------------------------------------------------
# Figma backend — wraps the M7.2 stack
# ---------------------------------------------------------------------------


class FigmaRenderer(Renderer):
    """First concrete :class:`Renderer` impl. Thin wrapper over
    ``dd.render_figma_ast.render_figma`` (render) +
    ``dd.apply_render.walk_rendered_via_bridge`` (walk) +
    ``dd.verify_figma.FigmaRenderVerifier`` (verify).

    Scope: *adapter only*. No new behavior; the Figma-specific
    plumbing already lives in those modules. The adapter just
    presents them under the multi-backend protocol.
    """

    backend = "figma"

    def render(
        self,
        ast: Any,
        *,
        ctx: dict[str, Any],
    ) -> RenderArtifact:
        """Wraps ``dd.render_figma_ast.render_figma``.

        ``ctx`` must supply: ``conn`` (sqlite3.Connection),
        ``nid_map``, ``fonts``, ``spec_key_map``, plus optional
        ``original_name_map`` / ``db_visuals`` / ``ckr_built`` /
        ``page_name`` / ``canvas_position`` / ``_spec_elements`` /
        ``_spec_tokens``. Callers using the applied-doc path
        should route through ``dd.apply_render.render_applied_doc``
        instead.
        """
        from dd.render_figma_ast import render_figma

        script, token_refs = render_figma(
            ast,
            ctx.get("conn"),
            ctx["nid_map"],
            fonts=ctx["fonts"],
            spec_key_map=ctx["spec_key_map"],
            original_name_map=ctx.get("original_name_map"),
            db_visuals=ctx.get("db_visuals"),
            ckr_built=ctx.get("ckr_built", True),
            page_name=ctx.get("page_name"),
            canvas_position=ctx.get("canvas_position"),
            _spec_elements=ctx.get("_spec_elements"),
            _spec_tokens=ctx.get("_spec_tokens"),
        )
        return RenderArtifact(
            kind="figma-js",
            payload=script,
            metadata={"token_refs": token_refs},
        )

    def walk(
        self,
        artifact: RenderArtifact,
        *,
        ctx: Optional[dict[str, Any]] = None,
    ) -> WalkResult:
        """Wraps ``dd.apply_render.walk_rendered_via_bridge``.

        ``ctx`` optionally supplies ``ws_port`` / ``timeout`` /
        ``node_binary`` / ``keep_artifacts`` / ``artifact_dir`` /
        ``walk_script``. Defaults align with the underlying wrapper
        (timeout=320s — Python subprocess must exceed the JS
        watchdog at 310s which itself exceeds the PROXY_EXECUTE
        limit at 300s; see walk_ref.js + sweep.py WALK_TIMEOUT).
        """
        from dd.apply_render import walk_rendered_via_bridge

        ctx = ctx or {}
        kwargs: dict[str, Any] = {
            "script": artifact.payload,
            "ws_port": ctx.get("ws_port", 9228),
            "timeout": ctx.get("timeout", 320.0),
            "node_binary": ctx.get("node_binary"),
            "keep_artifacts": ctx.get("keep_artifacts", False),
            "artifact_dir": ctx.get("artifact_dir"),
        }
        if "walk_script" in ctx:
            kwargs["walk_script"] = ctx["walk_script"]
        payload = walk_rendered_via_bridge(**kwargs)
        return WalkResult(
            ok=bool(payload.get("__ok")),
            eid_map=payload.get("eid_map") or {},
            errors=list(payload.get("errors") or []),
            raw=payload,
        )

    def verify(
        self,
        ir: Any,
        walk: WalkResult,
    ) -> RenderReport:
        """Wraps :class:`dd.verify_figma.FigmaRenderVerifier`.

        The verifier's expected shape is ``{"eid_map": {...}}`` —
        we rebuild that from the ``WalkResult`` so the existing
        verifier's diff logic doesn't need to know about the
        protocol.
        """
        from dd.verify_figma import FigmaRenderVerifier

        rendered_ref = {
            "eid_map": walk.eid_map,
            "errors": walk.errors,
        }
        return FigmaRenderVerifier().verify(ir, rendered_ref)
