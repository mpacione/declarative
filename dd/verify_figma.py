"""Figma instantiation of the ADR-007 Position 3 ``RenderVerifier``.

Walks a rendered-tree payload and diffs against the IR, producing a
``RenderReport`` with per-node ``StructuredError`` entries.

For unit-testability, the verifier takes a lightweight dict describing
the rendered tree (keyed by eid) instead of reaching into the Figma
Plugin API directly. Live callers (the ``dd verify`` CLI and the
round-trip harness) build that payload via the plugin's walk then hand
it here.

This mirrors the ``IngestAdapter`` pattern: the IO part (walking the
external world) is injectable; the diff logic is a pure function.
"""

from __future__ import annotations

from typing import Any, ClassVar

from dd.boundary import (
    KIND_MISSING_CHILD,
    KIND_MISSING_TEXT,
    KIND_TYPE_SUBSTITUTION,
    RenderReport,
    StructuredError,
)


# Figma native type expected for each IR element type. Entries marked
# as frozenset describe multiple acceptable targets.
_IR_TO_FIGMA_TYPE: dict[str, frozenset[str]] = {
    "screen": frozenset({"FRAME"}),
    "frame": frozenset({"FRAME"}),
    "button": frozenset({"INSTANCE", "FRAME"}),
    "card": frozenset({"INSTANCE", "FRAME"}),
    "header": frozenset({"INSTANCE", "FRAME"}),
    "icon": frozenset({"INSTANCE", "FRAME", "VECTOR"}),
    "instance": frozenset({"INSTANCE"}),
    "text": frozenset({"TEXT"}),
    "group": frozenset({"GROUP", "FRAME"}),
    "rectangle": frozenset({"RECTANGLE"}),
    "ellipse": frozenset({"ELLIPSE"}),
    "vector": frozenset({"VECTOR", "BOOLEAN_OPERATION"}),
}

# Semantic types that should resolve to INSTANCE when the pipeline
# has a catalog match. A type-substitution entry fires when the IR
# expected INSTANCE and the render produced a fallback (FRAME).
_SHOULD_BE_INSTANCE: frozenset[str] = frozenset({
    "button", "card", "header", "instance",
})


class FigmaRenderVerifier:
    """Figma-specific render verifier.

    ``verify(ir, rendered_ref)`` expects ``rendered_ref`` to be a dict:

    ::

        {
            "eid_map": {
                "<eid>": {
                    "type": "<FIGMA_TYPE>",
                    "characters": "<text, optional>",
                    ...
                },
                ...
            },
        }

    Live callers construct this by walking the rendered Figma subtree
    via the Plugin API and keying by the eid recorded in ``M[eid] =
    node.id``.
    """

    backend: ClassVar[str] = "figma"

    def verify(
        self, ir: dict[str, Any], rendered_ref: Any,
    ) -> RenderReport:
        elements = ir.get("elements", {}) if isinstance(ir, dict) else {}
        eid_map: dict[str, dict[str, Any]] = {}
        if isinstance(rendered_ref, dict):
            eid_map = rendered_ref.get("eid_map", {}) or {}

        # Mode 1 absorbs IR descendants: when an IR node rendered as an
        # INSTANCE, its IR descendants are instantiated from the master
        # component and do NOT appear in M. We skip them in the verifier
        # walk so they don't generate spurious missing_child entries.
        absorbed: set[str] = set()

        def _collect_descendants(eid: str) -> None:
            elem = elements.get(eid)
            if not elem:
                return
            for child_eid in elem.get("children", []) or []:
                absorbed.add(child_eid)
                _collect_descendants(child_eid)

        for eid, rendered in eid_map.items():
            if rendered.get("type") == "INSTANCE":
                _collect_descendants(eid)

        errors: list[StructuredError] = []
        ir_count = 0
        rendered_count = 0

        for eid, element in elements.items():
            if eid in absorbed:
                # Descendant of a Mode 1 instance; rendered from master
                continue
            ir_count += 1
            rendered = eid_map.get(eid)

            if rendered is None:
                errors.append(StructuredError(
                    kind=KIND_MISSING_CHILD,
                    id=eid,
                    error="element present in IR but missing from render",
                ))
                continue

            rendered_count += 1
            ir_type = element.get("type", "")
            rendered_type = rendered.get("type", "")

            # Type-substitution check
            expected = _IR_TO_FIGMA_TYPE.get(ir_type)
            if expected and rendered_type not in expected:
                errors.append(StructuredError(
                    kind=KIND_TYPE_SUBSTITUTION,
                    id=eid,
                    error=(
                        f"expected one of {sorted(expected)}, "
                        f"got {rendered_type}"
                    ),
                    context={"ir_type": ir_type, "rendered_type": rendered_type},
                ))
                continue

            # Catalog-mapped elements that should have materialised as
            # INSTANCE but instead rendered as FRAME are specifically
            # the ADR-007 Defect-1 class. Only flag when Mode 1 was
            # actually eligible for this element. `_mode1_eligible` is
            # computed at IR-build time from DB state (see ir.py
            # map_node_to_element). When False, the element is a
            # name-only classified FRAME — the renderer correctly
            # emitted createFrame and the semantic tag is a classifier
            # heuristic, not a resolvable INSTANCE reference.
            if (
                ir_type in _SHOULD_BE_INSTANCE
                and rendered_type == "FRAME"
                and "INSTANCE" in (expected or frozenset())
                and element.get("_mode1_eligible", True)
            ):
                errors.append(StructuredError(
                    kind=KIND_TYPE_SUBSTITUTION,
                    id=eid,
                    error=(
                        f"IR expected INSTANCE ({ir_type}); "
                        f"render produced FRAME (ADR-007 Defect 1)"
                    ),
                    context={"ir_type": ir_type, "rendered_type": rendered_type},
                ))
                continue

            # Empty-text check — Defect 2 surfaces here
            expected_text = (element.get("props") or {}).get("text")
            if ir_type == "text" and expected_text:
                actual_text = rendered.get("characters", "")
                if not actual_text:
                    errors.append(StructuredError(
                        kind=KIND_MISSING_TEXT,
                        id=eid,
                        error=f"expected characters={expected_text!r}, got empty",
                        context={"expected": expected_text},
                    ))

        return RenderReport(
            backend=self.backend,
            ir_node_count=ir_count,
            rendered_node_count=rendered_count,
            errors=errors,
        )
