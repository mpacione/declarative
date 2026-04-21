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
    KIND_BOUNDS_MISMATCH,
    KIND_EFFECT_MISSING,
    KIND_FILL_MISMATCH,
    KIND_MISSING_ASSET,
    KIND_MISSING_CHILD,
    KIND_MISSING_TEXT,
    KIND_STROKE_MISMATCH,
    KIND_TYPE_SUBSTITUTION,
    RenderReport,
    StructuredError,
)


# Text height tolerance before we flag a wrap.
#
# Real wraps observed in testing produce ratios of 3x or more (a 3-line
# wrap of 15px-expected text renders at ~48px; a pathological per-char
# wrap produces 20x+). A 1.5x threshold catches those reliably but
# fires false positives on single-line text where the DB's recorded
# height is a tighter bounding-box metric than Figma's actual
# line-height at the rendered font size — e.g. Inter 20pt Semi Bold
# renders at ~24px line-height while the source DB captures 15px.
#
# 2.0x gives comfortable headroom above typical font-metric drift
# while still catching 2-line wraps and everything worse.
_TEXT_HEIGHT_WRAP_RATIO = 2.0


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

# Figma node types whose visible output is defined entirely by their
# vector path geometry. A node of one of these types that rendered
# with both fillGeometry and strokeGeometry empty is a missing asset.
_VECTOR_HOSTS: frozenset[str] = frozenset({
    "VECTOR", "BOOLEAN_OPERATION",
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
                    hint=(
                        f"IR expects an element at @{eid} but the "
                        "render produced no matching node. Options: "
                        "(a) `delete @{eid}` if the element is no "
                        "longer needed; (b) confirm the parent "
                        "didn't absorb the child under a Mode-1 "
                        "INSTANCE; (c) check the compressor didn't "
                        "inline it away."
                    ).replace("{eid}", eid),
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
                    hint=(
                        f"The IR at @{eid} expects a {ir_type} "
                        f"(Figma type in {sorted(expected)}) but "
                        f"got {rendered_type}. Either `swap @{eid} "
                        "with=-> <master>` to a library component "
                        "of the right type, or `delete @{eid}` if "
                        "the classification was wrong."
                    ).replace("{eid}", eid),
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

            # Missing-asset check — a VECTOR / BOOLEAN_OPERATION
            # rendered with zero fillGeometry AND zero strokeGeometry
            # has no paths to draw. Figma falls back to the node's
            # intrinsic bounding box (a grey rectangle), so visually
            # the illustration/icon disappears. Gated on BOTH geom
            # keys being present in the rendered ref: older walks that
            # omit the signal stay silent (no false positives).
            if rendered_type in _VECTOR_HOSTS:
                fg = rendered.get("fillGeometryCount")
                sg = rendered.get("strokeGeometryCount")
                if (
                    isinstance(fg, int)
                    and isinstance(sg, int)
                    and fg == 0
                    and sg == 0
                ):
                    errors.append(StructuredError(
                        kind=KIND_MISSING_ASSET,
                        id=eid,
                        error=(
                            f"{rendered_type} rendered with no path geometry"
                            f" (fillGeometryCount=0, strokeGeometryCount=0)"
                        ),
                        context={
                            "rendered_type": rendered_type,
                            "ir_type": ir_type,
                        },
                    ))

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

            # Text-wrap detection: rendered height far exceeds the IR
            # height → text almost certainly wrapped to multiple lines.
            # Catches regressions like the screen 175 "Commun / ity"
            # visible wrap where Figma's resize() flipped autoResize
            # into HEIGHT mode, and the screen 176 "M/o/r/e" vertical
            # wrap where FILL sizing handed the text a 0-width parent.
            #
            # Gate on rendered_type (not IR type) because the classifier
            # assigns heading/title/text semantic labels interchangeably
            # to TEXT nodes. Prefer sizing.heightPixels when
            # sizing.height is a semantic string ("hug"/"fill").
            if rendered_type == "TEXT" and rendered.get("height") is not None:
                sizing = (element.get("layout") or {}).get("sizing") or {}
                ir_h = sizing.get("heightPixels")
                if not isinstance(ir_h, (int, float)):
                    raw_h = sizing.get("height")
                    if isinstance(raw_h, (int, float)):
                        ir_h = raw_h
                rendered_h = rendered.get("height")
                if (
                    isinstance(ir_h, (int, float))
                    and isinstance(rendered_h, (int, float))
                    and ir_h > 0
                    and rendered_h > ir_h * _TEXT_HEIGHT_WRAP_RATIO
                ):
                    errors.append(StructuredError(
                        kind=KIND_BOUNDS_MISMATCH,
                        id=eid,
                        error=(
                            f"rendered height={rendered_h} exceeds "
                            f"IR height={ir_h} by > {_TEXT_HEIGHT_WRAP_RATIO}x "
                            f"— text likely wrapped"
                        ),
                        context={
                            "ir_height": ir_h,
                            "rendered_height": rendered_h,
                            "ratio": rendered_h / ir_h,
                        },
                    ))

            # Fill-color comparison: each IR solid fill is compared against
            # the corresponding rendered solid fill. Token-bound fills (color
            # starts with '{') are skipped — the IR value is a reference, not
            # a concrete hex. Gated on both sides having a 'fills' key so
            # older walkers that omit fills don't trigger false positives.
            ir_fills = (element.get("visual") or {}).get("fills")
            rendered_fills = rendered.get("fills")
            if isinstance(ir_fills, list) and isinstance(rendered_fills, list):
                ir_solids = [f for f in ir_fills if f.get("type") == "solid"]
                rd_solids = [f for f in rendered_fills if f.get("type") == "solid"]

                if len(ir_solids) != len(rd_solids):
                    errors.append(StructuredError(
                        kind=KIND_FILL_MISMATCH,
                        id=eid,
                        error=(
                            f"solid fill count: IR={len(ir_solids)}, "
                            f"rendered={len(rd_solids)}"
                        ),
                        context={
                            "ir_solid_count": len(ir_solids),
                            "rendered_solid_count": len(rd_solids),
                        },
                    ))
                else:
                    for fi, (ir_fill, rd_fill) in enumerate(zip(ir_solids, rd_solids)):
                        ir_color = (ir_fill.get("color") or "").upper()
                        rd_color = (rd_fill.get("color") or "").upper()
                        if ir_color.startswith("{"):
                            continue
                        if ir_color != rd_color:
                            errors.append(StructuredError(
                                kind=KIND_FILL_MISMATCH,
                                id=eid,
                                error=(
                                    f"fill[{fi}] color: IR={ir_color}, "
                                    f"rendered={rd_color}"
                                ),
                                context={
                                    "fill_index": fi,
                                    "ir_color": ir_fill.get("color"),
                                    "rendered_color": rd_fill.get("color"),
                                },
                            ))

            # Stroke-color comparison: same shape as fill comparison.
            ir_strokes = (element.get("visual") or {}).get("strokes")
            rendered_strokes = rendered.get("strokes")
            if isinstance(ir_strokes, list) and isinstance(rendered_strokes, list):
                ir_ss = [s for s in ir_strokes if s.get("type") == "solid"]
                rd_ss = [s for s in rendered_strokes if s.get("type") == "solid"]

                if len(ir_ss) != len(rd_ss):
                    errors.append(StructuredError(
                        kind=KIND_STROKE_MISMATCH,
                        id=eid,
                        error=(
                            f"solid stroke count: IR={len(ir_ss)}, "
                            f"rendered={len(rd_ss)}"
                        ),
                        context={
                            "ir_solid_count": len(ir_ss),
                            "rendered_solid_count": len(rd_ss),
                        },
                    ))
                else:
                    for si, (ir_s, rd_s) in enumerate(zip(ir_ss, rd_ss)):
                        ir_sc = (ir_s.get("color") or "").upper()
                        rd_sc = (rd_s.get("color") or "").upper()
                        if ir_sc.startswith("{"):
                            continue
                        if ir_sc != rd_sc:
                            errors.append(StructuredError(
                                kind=KIND_STROKE_MISMATCH,
                                id=eid,
                                error=(
                                    f"stroke[{si}] color: IR={ir_sc}, "
                                    f"rendered={rd_sc}"
                                ),
                                context={
                                    "stroke_index": si,
                                    "ir_color": ir_s.get("color"),
                                    "rendered_color": rd_s.get("color"),
                                },
                            ))

            # Effect-count comparison: IR effect count vs rendered.
            # Walker captures effectCount (simpler than full effect diff).
            ir_effects = (element.get("visual") or {}).get("effects")
            rendered_effect_count = rendered.get("effectCount")
            if (
                isinstance(ir_effects, list)
                and isinstance(rendered_effect_count, int)
            ):
                ir_ec = len(ir_effects)
                if rendered_effect_count < ir_ec:
                    errors.append(StructuredError(
                        kind=KIND_EFFECT_MISSING,
                        id=eid,
                        error=(
                            f"effect count: IR={ir_ec}, "
                            f"rendered={rendered_effect_count}"
                        ),
                        context={
                            "ir_effect_count": ir_ec,
                            "rendered_effect_count": rendered_effect_count,
                        },
                    ))

        return RenderReport(
            backend=self.backend,
            ir_node_count=ir_count,
            rendered_node_count=rendered_count,
            errors=errors,
        )
