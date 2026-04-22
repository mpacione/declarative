"""Figma-specific adapter for the repair loop (Tier E.1).

The repair loop (``dd.repair_agent.run_repair_loop``) is generic
over the ``Verifier`` protocol. Before this module, the only
concrete Verifier in the tree was a synthetic
``TextExpectationVerifier`` used in M7.5 smoke tests. This adapter
closes the loop against the **real** :class:`FigmaRenderVerifier`,
so hints emitted from structural-parity errors feed an LLM
proposer that emits corrective L3 edit statements.

The adapter is deliberately thin: it receives a ``render_and_walk``
callable (doc → rendered_ref dict) and an ``ir_of`` callable
(doc → IR-spec dict) so tests and demos can stub either side.
A production wiring would pass:
  - ``render_and_walk = lambda doc: walk_rendered_via_bridge(
        render_applied_doc(...).script)``
  - ``ir_of = lambda doc: spec_from_ir_generator(doc)``

See ``scripts/repair_demo.py`` for the end-to-end wiring (bridge
+ real verifier + Claude proposer).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from dd.markup_l3 import L3Document
from dd.repair_agent import RepairReport, Verifier
from dd.verify_figma import FigmaRenderVerifier


@dataclass
class FigmaRepairVerifier:
    """Concrete :class:`dd.repair_agent.Verifier` that runs
    :class:`FigmaRenderVerifier` under the hood.

    Each ``verify(doc)`` call:
      1. Extracts the IR-spec from ``doc`` via ``ir_of``.
      2. Produces a ``rendered_ref`` via ``render_and_walk``.
      3. Runs the Figma verifier, which emits
         ``StructuredError`` entries with populated ``hint``
         fields where applicable.
      4. Wraps the report as a ``RepairReport(is_ok=is_parity,
         errors=tuple(errors))``.

    Both callables receive the CURRENT (possibly edited) doc —
    subsequent iterations re-walk the edited output.
    """

    render_and_walk: Callable[[L3Document], dict[str, Any]]
    ir_of: Callable[[L3Document], dict[str, Any]]

    def verify(self, doc: L3Document) -> RepairReport:
        rendered_ref = self.render_and_walk(doc)
        ir = self.ir_of(doc)
        report = FigmaRenderVerifier().verify(ir, rendered_ref)
        return RepairReport(
            is_ok=report.is_parity,
            errors=tuple(report.errors),
        )


def build_figma_repair_verifier(
    *,
    render_and_walk: Callable[[L3Document], dict[str, Any]],
    ir_of: Callable[[L3Document], dict[str, Any]],
) -> FigmaRepairVerifier:
    """Factory that returns a ready :class:`FigmaRepairVerifier`.

    Prefer this over constructing the dataclass directly — the
    factory is the stable public API; the dataclass shape is
    subject to change as repair-loop iteration policy evolves."""
    return FigmaRepairVerifier(
        render_and_walk=render_and_walk,
        ir_of=ir_of,
    )
