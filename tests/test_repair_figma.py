"""Tests for the Figma-verifier adapter to the repair loop (Tier E.1).

Before Tier E: the repair loop (M7.5) only closed over a synthetic
text-expectation verifier. This adapter lets it close over the real
`FigmaRenderVerifier` + a render/walk callable, completing the
verifier-as-agent loop against actual structural parity errors.
"""

from __future__ import annotations

from typing import Any

import pytest

from dd.boundary import RenderReport, StructuredError
from dd.markup_l3 import L3Document, parse_l3
from dd.repair_agent import RepairReport, Verifier
from dd.repair_figma import (
    FigmaRepairVerifier,
    build_figma_repair_verifier,
)


def _mk_doc(src: str) -> L3Document:
    return parse_l3(src)


_BASIC_DOC = """screen #screen-1 {
  frame #frame-1 {
    button #button-1
  }
}"""


class TestFigmaRepairVerifier:
    def test_is_a_verifier(self) -> None:
        """The adapter satisfies the repair_agent.Verifier protocol."""

        def render_and_walk(doc):
            return {"eid_map": {}, "errors": []}

        def ir_of(doc):
            return {"elements": {}}

        v = FigmaRepairVerifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        # Protocol check by duck-typing (Verifier is a Protocol).
        assert callable(v.verify)
        rep = v.verify(_mk_doc(_BASIC_DOC))
        assert isinstance(rep, RepairReport)
        assert rep.is_ok is True
        assert rep.errors == ()

    def test_returns_is_ok_false_when_errors_present(self) -> None:
        """Verifier reports missing_child → adapter flips is_ok to False
        and surfaces the error list."""

        def render_and_walk(doc):
            return {"eid_map": {}, "errors": []}

        def ir_of(doc):
            return {
                "elements": {
                    "screen-1": {"type": "screen", "children": ["button-1"]},
                    "button-1": {"type": "button"},
                },
            }

        v = FigmaRepairVerifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        rep = v.verify(_mk_doc(_BASIC_DOC))
        assert rep.is_ok is False
        assert len(rep.errors) >= 1
        # At least one missing_child entry exists (both screen-1 and
        # button-1 are absent from the empty eid_map).
        kinds = {e.kind for e in rep.errors}
        assert any("missing" in k or "MISSING" in k for k in kinds)

    def test_error_hints_propagate_intact(self) -> None:
        """Hints on StructuredError aren't mangled — they're the
        proposer's main input signal."""

        def render_and_walk(doc):
            return {
                "eid_map": {
                    "button-1": {"type": "FRAME"},  # expected INSTANCE
                },
                "errors": [],
            }

        def ir_of(doc):
            return {
                "elements": {
                    "button-1": {"type": "button", "_mode1_eligible": True},
                },
            }

        v = FigmaRepairVerifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        rep = v.verify(_mk_doc(_BASIC_DOC))
        assert rep.is_ok is False
        type_sub = [
            e for e in rep.errors if e.kind == "type_substitution"
        ]
        assert type_sub
        assert type_sub[0].hint
        assert "swap" in type_sub[0].hint

    def test_render_and_walk_receives_applied_doc(self) -> None:
        """The render callable is invoked once per verify call with
        the current doc — so subsequent iterations re-walk the
        edited output."""
        received: list[L3Document] = []

        def render_and_walk(doc):
            received.append(doc)
            return {"eid_map": {}, "errors": []}

        def ir_of(doc):
            return {"elements": {}}

        v = FigmaRepairVerifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        doc = _mk_doc(_BASIC_DOC)
        v.verify(doc)
        assert len(received) == 1
        assert received[0] is doc


class TestBuildFigmaRepairVerifier:
    def test_returns_adapter_bound_to_callables(self) -> None:
        """Factory helper wires render_and_walk + ir_of into a
        ready-to-use Verifier."""

        def rw(doc):
            return {"eid_map": {}, "errors": []}

        def ir(doc):
            return {"elements": {}}

        v = build_figma_repair_verifier(render_and_walk=rw, ir_of=ir)
        assert isinstance(v, FigmaRepairVerifier)
        # One verify call exercises the plumbing
        rep = v.verify(_mk_doc(_BASIC_DOC))
        assert isinstance(rep, RepairReport)


class TestEndToEndRepairLoop:
    """Close the loop: adapter + stub proposer + run_repair_loop."""

    def test_loop_converges_on_type_substitution(self) -> None:
        """Inject a type-substitution error in iter 0, have a stub
        proposer suggest a swap to the correct library master, verify
        iter 1 renders clean."""
        from dd.repair_agent import run_repair_loop

        iter_count = {"n": 0}

        def render_and_walk(doc):
            iter_count["n"] += 1
            # Iter 1: button-1 rendered as FRAME (Mode-1 degraded).
            # Iter 2: after swap, rendered as INSTANCE.
            if iter_count["n"] == 1:
                return {
                    "eid_map": {"button-1": {"type": "FRAME"}},
                    "errors": [],
                }
            return {
                "eid_map": {"button-1": {"type": "INSTANCE"}},
                "errors": [],
            }

        def ir_of(doc):
            return {
                "elements": {
                    "button-1": {"type": "button", "_mode1_eligible": True},
                },
            }

        class StubProposer:
            """Emit a swap suggestion when it sees
            KIND_TYPE_SUBSTITUTION."""

            def propose(self, errors, doc):
                for e in errors:
                    if e.kind == "type_substitution":
                        # Emit a swap that the parser accepts. The
                        # renderer side doesn't matter — this test
                        # only checks the loop's control flow.
                        yield (
                            f"swap @{e.id} with=-> "
                            "button/primary/default\n"
                        )

        v = build_figma_repair_verifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        outcome = run_repair_loop(
            doc=_mk_doc(_BASIC_DOC),
            verifier=v,
            proposer=StubProposer(),
            max_iterations=3,
        )
        assert outcome.succeeded is True
        assert outcome.iterations == 2
        assert any("swap" in s for s in outcome.applied_edit_sources)

    def test_loop_stops_at_cap_when_proposer_fails(self) -> None:
        """Proposer emits nothing → loop hits the cap and returns
        succeeded=False."""
        from dd.repair_agent import run_repair_loop

        def render_and_walk(doc):
            return {
                "eid_map": {"button-1": {"type": "FRAME"}},
                "errors": [],
            }

        def ir_of(doc):
            return {
                "elements": {
                    "button-1": {"type": "button", "_mode1_eligible": True},
                },
            }

        class NullProposer:
            def propose(self, errors, doc):
                return ()

        v = build_figma_repair_verifier(
            render_and_walk=render_and_walk, ir_of=ir_of,
        )
        outcome = run_repair_loop(
            doc=_mk_doc(_BASIC_DOC),
            verifier=v,
            proposer=NullProposer(),
            max_iterations=2,
        )
        assert outcome.succeeded is False
        # Proposer returned empty on iter 1 → break at that point
        assert outcome.iterations == 1
