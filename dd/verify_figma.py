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
    KIND_BLENDMODE_MISMATCH,
    KIND_BOUNDS_MISMATCH,
    KIND_CLIPS_CONTENT_MISMATCH,
    KIND_CORNERRADIUS_MISMATCH,
    KIND_DASH_PATTERN_MISMATCH,
    KIND_EFFECT_MISSING,
    KIND_FILL_MISMATCH,
    KIND_MASK_MISMATCH,
    KIND_MISSING_ASSET,
    KIND_MISSING_CHILD,
    KIND_MISSING_TEXT,
    KIND_OPACITY_MISMATCH,
    KIND_ROTATION_MISMATCH,
    KIND_STROKE_ALIGN_MISMATCH,
    KIND_STROKE_MISMATCH,
    KIND_STROKE_WEIGHT_MISMATCH,
    KIND_TYPE_SUBSTITUTION,
    RenderReport,
    StructuredError,
)
from dd.property_registry import (
    FigmaComparatorSpec,
    PROPERTIES,
    StationDisposition,
)

# Tolerances for the new P1c numeric comparators. Float jitter from
# the deg→rad walker conversion + IR build paths needs slack.
_OPACITY_TOLERANCE = 1e-3      # 0.001 — well below visible difference
_ROTATION_TOLERANCE = 1e-3     # ~0.06° — covers walker conversion error
_CORNER_RADIUS_TOLERANCE = 1e-3  # sub-pixel


# ---------------------------------------------------------------------
# Sprint 2 C10 — registry-driven comparator dispatch
# ---------------------------------------------------------------------
# Per docs/plan-sprint-2-station-parity.md §3 (station model) and
# Codex 5.5 round-9 architectural fork: graduated properties (those
# with station_4 == COMPARE_DISPATCH and a compare_figma spec) are
# compared via this dispatch, NOT the hand-rolled paths above. The
# 11 existing comparators (fills/strokes/cornerRadius/etc.) keep
# their hand-rolled implementations because they pre-date Sprint 2
# and bundling the migration with the rail risks scope-creep.
#
# Single comparator signature: ``(ir_value, rendered_value, element,
# *, spec)`` — keyword-only spec lets generic comparators like
# enum_equality emit different KIND_* errors per property. Closes
# the bug class A1.3 left open: drift on uncompared properties.


def _ir_value_for(element: dict[str, Any], figma_name: str) -> Any:
    """Read the IR-side value for a graduated property.

    Codex round-9 lock: helper switch (NOT declarative ir_path on
    spec) because some properties need normalization across the
    IR-vs-walker shape boundary. Layout sizing in particular: IR
    stores ``"hug"/"fill"`` lowercase strings or numeric pixel
    widths (FIXED); walker emits ``"HUG"/"FILL"/"FIXED"`` uppercase.
    Helper normalizes IR side to walker's enum.

    Returns ``None`` when the element has no value for the property —
    the dispatch loop skips comparison rather than treating absence
    as drift.
    """
    if figma_name == "characters":
        return (element.get("props") or {}).get("text")

    if figma_name in ("layoutSizingHorizontal", "layoutSizingVertical"):
        sizing = (element.get("layout") or {}).get("sizing") or {}
        axis_key = "width" if figma_name == "layoutSizingHorizontal" else "height"
        raw = sizing.get(axis_key)
        if raw is None:
            return None
        if isinstance(raw, str):
            # IR lowercase ("hug" / "fill" / "fixed") → walker uppercase
            return raw.upper()
        if isinstance(raw, (int, float)):
            # Numeric pixel value implies FIXED sizing mode in the IR
            return "FIXED"
        return None

    return None  # unknown graduation; defensive


def _compare_text_equality(
    ir_value: Any, rendered_value: Any, element: dict[str, Any],
    *, spec: "FigmaComparatorSpec",
) -> "StructuredError | None":
    """C10 graduation: text content equality. Used by ``characters``.

    Empty strings compare normally per Codex round-9: empty == empty
    is a match, empty IR vs non-empty rendered is a mismatch.
    """
    if ir_value == rendered_value:
        return None
    return StructuredError(
        kind=spec.kind,
        id=element.get("id", "?"),
        error=(
            f"text: IR={ir_value!r}, rendered={rendered_value!r}"
        ),
        context={
            "ir_text": ir_value,
            "rendered_text": rendered_value,
        },
    )


def _compare_enum_equality(
    ir_value: Any, rendered_value: Any, element: dict[str, Any],
    *, spec: "FigmaComparatorSpec",
) -> "StructuredError | None":
    """C10 graduation: enum string equality. Used by
    ``layoutSizingHorizontal/Vertical`` — same impl, different
    ``spec.kind`` per property. The spec drives error metadata so
    the comparator stays generic.
    """
    if ir_value == rendered_value:
        return None
    return StructuredError(
        kind=spec.kind,
        id=element.get("id", "?"),
        error=(
            f"{spec.walker_key}: IR={ir_value!r}, rendered={rendered_value!r}"
        ),
        context={
            "ir_value": ir_value,
            "rendered_value": rendered_value,
        },
    )


# Registered comparator implementations, keyed by FigmaComparatorSpec.comparator.
# Adding a new comparator id requires an entry here AND a registry
# property pointing at it via compare_figma. The C10 coverage test
# fails if any COMPARE_DISPATCH property points to an unregistered id.
_COMPARATOR_IMPLS: dict[str, Any] = {
    "text_equality": _compare_text_equality,
    "enum_equality": _compare_enum_equality,
}


def _rendered_value(
    rendered: dict[str, Any], key: str, default: Any = None,
) -> Any:
    """Sprint 2 C8: read a rendered value that may be either:

    - raw value (legacy / non-graduated properties)
    - envelope ``{"value": <v>, "source": <tag>}`` (Sprint 2+
      graduated properties per
      ``docs/plan-sprint-2-station-parity.md`` §6)

    Returns the underlying value in either case. Verifier code uses
    this helper for properties that may have been graduated; the
    envelope-vs-raw distinction is invisible at the comparator
    level. C10 will wire registry-driven dispatch so every read site
    flows through the same path; until then the helper is the
    defensive shim.

    A dict is treated as an envelope only when it has BOTH ``value``
    and ``source`` keys — partial dicts ({"value": x} alone, or
    arbitrary dicts that happen to include a ``value`` key) pass
    through unchanged so future shape additions are not
    misinterpreted.
    """
    raw = rendered.get(key, default)
    if isinstance(raw, dict) and "value" in raw and "source" in raw:
        return raw["value"]
    return raw


def _is_snapshot_skip(
    rendered_type: str | None, prop_name: str, element: dict[str, Any],
) -> bool:
    """A1.3 (Backlog #1, provenance plan): per-property snapshot
    gate for Mode-1 INSTANCE heads.

    Returns ``True`` when the verifier should SKIP the comparison
    because the IR value is an extraction-time snapshot of master
    defaults rather than a real override directive.

    Conditions for skip:
    - rendered node IS an INSTANCE (only Mode-1 has the
      snapshot-vs-master-default ambiguity)
    - the property is NOT in ``element["_overrides"]``

    When ``element["_overrides"]`` is missing entirely (legacy IR
    pre-A1.1), default to "snapshot" — Codex 5.5: "missing
    provenance on Mode-1 INSTANCE defaults to snapshot, not
    override; safer to under-flag than over-flag false-positives."

    Non-INSTANCE rendered nodes never get the gate. They don't
    delegate visual rendering to a master, so the IR snapshot IS
    the render-time directive.
    """
    if rendered_type != "INSTANCE":
        return False
    overrides = element.get("_overrides")
    if overrides is None:
        # Legacy IR: default snapshot (skip).
        return True
    return prop_name not in overrides


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
        # Phase E Pattern 2 fix (P1): inhale walk-side runtime errors.
        # Pre-fix, the verifier read only `eid_map` and ignored
        # `rendered_ref["errors"]` — leaving 31 distinct __errors
        # kinds entirely invisible to the parity verdict. Sonnet +
        # Codex independently flagged this as the chronic verifier-
        # blindness pattern. F12a surfaced runtime_error_count in
        # CLI output but `is_parity` never consumed it. The runtime
        # errors are deep-copied into the frozen RenderReport so
        # downstream mutation of the walk JSON doesn't corrupt the
        # report's invariants.
        runtime_errors: list[dict[str, Any]] = []
        if isinstance(rendered_ref, dict):
            eid_map = rendered_ref.get("eid_map", {}) or {}
            raw_errs = rendered_ref.get("errors") or []
            if isinstance(raw_errs, list):
                # Filter to dict-shaped entries (defensive: walk_ref.js
                # always emits dicts, but a malformed walk could carry
                # other types; we don't want a non-dict to break
                # report.runtime_error_kinds enumeration).
                runtime_errors = [
                    dict(e) for e in raw_errs if isinstance(e, dict)
                ]

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
                    hint=(
                        f"@{eid} is classified as {ir_type} and is "
                        "Mode-1 eligible, but the render degraded to "
                        "FRAME. Likely the library component went "
                        "missing or the CKR lookup failed. Options: "
                        f"(a) `swap @{eid} with=-> <known-master>` "
                        "to a valid library component; (b) check the "
                        "CKR is populated (`component_key_registry` "
                        "table); (c) delete the node if its semantic "
                        "classification was wrong."
                    ),
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

            # Empty-text check — Defect 2 surfaces here.
            #
            # Sprint 2 C8: ``characters`` may now be either the raw
            # string (legacy walker) or the envelope shape
            # ``{"value": str, "source": "set"}`` (post-C8 walker per
            # docs/plan-sprint-2-station-parity.md §6). ``_rendered_value``
            # collapses both to the underlying string; the
            # falsy-empty test below is unchanged.
            expected_text = (element.get("props") or {}).get("text")
            if ir_type == "text" and expected_text:
                actual_text = _rendered_value(rendered, "characters", "")
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
            # A1.3 (Backlog #1, provenance plan): on a Mode-1 INSTANCE
            # head, fills is a snapshot unless _overrides says
            # otherwise. The narrow chip-1 token-gradient suppression
            # that lived here pre-A1.3 is subsumed by this gate — the
            # chip-1 case clears because chip-1 has no FILLS row in
            # instance_overrides.
            if _is_snapshot_skip(rendered.get("type"), "fills", element):
                pass  # snapshot — skip comparison
            elif isinstance(ir_fills, list) and isinstance(rendered_fills, list):
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
            # A1.3: same provenance gate as fills.
            ir_strokes = (element.get("visual") or {}).get("strokes")
            rendered_strokes = rendered.get("strokes")
            if _is_snapshot_skip(rendered.get("type"), "strokes", element):
                pass  # snapshot — skip comparison
            elif isinstance(ir_strokes, list) and isinstance(rendered_strokes, list):
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

            # ============================================================
            # P1c (forensic-audit-2): visual prop comparators that close
            # the verifier blind spots. P1a populated the IR side; P1b
            # populated the walker side. These compare them and emit a
            # structured error per drift class.
            # ============================================================
            ir_visual = element.get("visual") or {}

            # Opacity drift — numeric tolerance to absorb float jitter.
            # A1.3 provenance gate: skip on Mode-1 INSTANCE snapshot.
            ir_opacity = ir_visual.get("opacity")
            rd_opacity = rendered.get("opacity")
            if _is_snapshot_skip(rendered.get("type"), "opacity", element):
                pass  # snapshot — skip
            elif (
                isinstance(ir_opacity, (int, float))
                and isinstance(rd_opacity, (int, float))
            ):
                if abs(ir_opacity - rd_opacity) > _OPACITY_TOLERANCE:
                    errors.append(StructuredError(
                        kind=KIND_OPACITY_MISMATCH,
                        id=eid,
                        error=f"opacity: IR={ir_opacity}, rendered={rd_opacity}",
                        context={
                            "ir_opacity": ir_opacity,
                            "rendered_opacity": rd_opacity,
                        },
                    ))

            # Blend mode drift — exact-string compare.
            # A1.3 provenance gate.
            ir_blend = ir_visual.get("blendMode")
            rd_blend = rendered.get("blendMode")
            if _is_snapshot_skip(rendered.get("type"), "blendMode", element):
                pass  # snapshot — skip
            elif (
                isinstance(ir_blend, str)
                and isinstance(rd_blend, str)
                and ir_blend != rd_blend
            ):
                errors.append(StructuredError(
                    kind=KIND_BLENDMODE_MISMATCH,
                    id=eid,
                    error=f"blendMode: IR={ir_blend}, rendered={rd_blend}",
                    context={
                        "ir_blend_mode": ir_blend,
                        "rendered_blend_mode": rd_blend,
                    },
                ))

            # Rotation drift — radians, numeric tolerance.
            ir_rotation = ir_visual.get("rotation")
            rd_rotation = rendered.get("rotation")
            if (
                isinstance(ir_rotation, (int, float))
                and isinstance(rd_rotation, (int, float))
            ):
                if abs(ir_rotation - rd_rotation) > _ROTATION_TOLERANCE:
                    errors.append(StructuredError(
                        kind=KIND_ROTATION_MISMATCH,
                        id=eid,
                        error=(
                            f"rotation: IR={ir_rotation:.6f} rad, "
                            f"rendered={rd_rotation:.6f} rad"
                        ),
                        context={
                            "ir_rotation": ir_rotation,
                            "rendered_rotation": rd_rotation,
                        },
                    ))

            # isMask drift — boolean equality. Either direction is a
            # real visual difference.
            ir_mask = ir_visual.get("isMask")
            rd_mask = rendered.get("isMask")
            if (
                isinstance(ir_mask, bool)
                and isinstance(rd_mask, bool)
                and ir_mask != rd_mask
            ):
                errors.append(StructuredError(
                    kind=KIND_MASK_MISMATCH,
                    id=eid,
                    error=f"isMask: IR={ir_mask}, rendered={rd_mask}",
                    context={
                        "ir_is_mask": ir_mask,
                        "rendered_is_mask": rd_mask,
                    },
                ))

            # Corner radius drift — uniform-vs-uniform with tolerance,
            # plus mixed (per-corner) when the walker reports
            # cornerRadiusMixed=true. Skip-emit if IR has no
            # cornerRadius opinion.
            # A1.3 provenance gate.
            ir_cr = ir_visual.get("cornerRadius")
            rd_mixed = rendered.get("cornerRadiusMixed") is True
            rd_cr = rendered.get("cornerRadius")
            if _is_snapshot_skip(rendered.get("type"), "cornerRadius", element):
                pass  # snapshot — skip
            elif isinstance(ir_cr, (int, float)):
                if rd_mixed:
                    # IR uniform vs rendered per-corner: compare
                    # each side to the IR uniform value.
                    sides = (
                        rendered.get("topLeftRadius"),
                        rendered.get("topRightRadius"),
                        rendered.get("bottomRightRadius"),
                        rendered.get("bottomLeftRadius"),
                    )
                    drifted_sides = [
                        side for side in sides
                        if isinstance(side, (int, float))
                        and abs(side - ir_cr) > _CORNER_RADIUS_TOLERANCE
                    ]
                    if drifted_sides:
                        errors.append(StructuredError(
                            kind=KIND_CORNERRADIUS_MISMATCH,
                            id=eid,
                            error=(
                                f"cornerRadius: IR uniform={ir_cr}, "
                                f"rendered per-corner with "
                                f"{len(drifted_sides)} side(s) drifted"
                            ),
                            context={
                                "ir_corner_radius": ir_cr,
                                "rendered_per_corner": list(sides),
                            },
                        ))
                elif (
                    isinstance(rd_cr, (int, float))
                    and abs(ir_cr - rd_cr) > _CORNER_RADIUS_TOLERANCE
                ):
                    errors.append(StructuredError(
                        kind=KIND_CORNERRADIUS_MISMATCH,
                        id=eid,
                        error=f"cornerRadius: IR={ir_cr}, rendered={rd_cr}",
                        context={
                            "ir_corner_radius": ir_cr,
                            "rendered_corner_radius": rd_cr,
                        },
                    ))

            # A5 (forensic-audit-2 Pattern G): comparators for visual
            # props the IR carries but pre-A5 had no comparator.
            # Each gated by the A1.3 provenance gate.

            # strokeWeight: numeric tolerance for sub-pixel jitter.
            ir_sw = ir_visual.get("strokeWeight")
            rd_sw = rendered.get("strokeWeight")
            if _is_snapshot_skip(rendered.get("type"), "strokeWeight", element):
                pass
            elif (
                isinstance(ir_sw, (int, float))
                and isinstance(rd_sw, (int, float))
            ):
                if abs(ir_sw - rd_sw) > _CORNER_RADIUS_TOLERANCE:
                    errors.append(StructuredError(
                        kind=KIND_STROKE_WEIGHT_MISMATCH,
                        id=eid,
                        error=f"strokeWeight: IR={ir_sw}, rendered={rd_sw}",
                        context={
                            "ir_stroke_weight": ir_sw,
                            "rendered_stroke_weight": rd_sw,
                        },
                    ))

            # strokeAlign: exact-string compare (INSIDE / CENTER / OUTSIDE).
            ir_sa = ir_visual.get("strokeAlign")
            rd_sa = rendered.get("strokeAlign")
            if _is_snapshot_skip(rendered.get("type"), "strokeAlign", element):
                pass
            elif (
                isinstance(ir_sa, str)
                and isinstance(rd_sa, str)
                and ir_sa != rd_sa
            ):
                errors.append(StructuredError(
                    kind=KIND_STROKE_ALIGN_MISMATCH,
                    id=eid,
                    error=f"strokeAlign: IR={ir_sa}, rendered={rd_sa}",
                    context={
                        "ir_stroke_align": ir_sa,
                        "rendered_stroke_align": rd_sa,
                    },
                ))

            # dashPattern: array equality (sequence of numeric lengths).
            # Empty array (solid stroke) is a real value distinct from
            # absent.
            ir_dp = ir_visual.get("dashPattern")
            rd_dp = rendered.get("dashPattern")
            if _is_snapshot_skip(rendered.get("type"), "dashPattern", element):
                pass
            elif (
                isinstance(ir_dp, list)
                and isinstance(rd_dp, list)
                and ir_dp != rd_dp
            ):
                errors.append(StructuredError(
                    kind=KIND_DASH_PATTERN_MISMATCH,
                    id=eid,
                    error=f"dashPattern: IR={ir_dp}, rendered={rd_dp}",
                    context={
                        "ir_dash_pattern": ir_dp,
                        "rendered_dash_pattern": rd_dp,
                    },
                ))

            # clipsContent: boolean equality. Only meaningful on
            # container types (FRAME / COMPONENT / INSTANCE / SECTION);
            # other types may not even carry the value. Skip when
            # either side is None.
            ir_cc = ir_visual.get("clipsContent")
            rd_cc = rendered.get("clipsContent")
            if _is_snapshot_skip(rendered.get("type"), "clipsContent", element):
                pass
            elif (
                isinstance(ir_cc, bool)
                and isinstance(rd_cc, bool)
                and ir_cc != rd_cc
            ):
                errors.append(StructuredError(
                    kind=KIND_CLIPS_CONTENT_MISMATCH,
                    id=eid,
                    error=f"clipsContent: IR={ir_cc}, rendered={rd_cc}",
                    context={
                        "ir_clips_content": ir_cc,
                        "rendered_clips_content": rd_cc,
                    },
                ))

            # Sprint 2 C10 — registry-driven comparator dispatch for
            # the 3 graduated properties (characters,
            # layoutSizingHorizontal, layoutSizingVertical). Per plan
            # §10 R2 (paired walker emission + verifier dispatch):
            # this is where the cross-corpus bugs the user observed
            # surface as KIND_TEXT_CONTENT_MISMATCH /
            # KIND_LAYOUT_SIZING_*_MISMATCH errors. Hand-rolled
            # comparators above are NOT migrated — they keep their
            # paths to bound Sprint 2's scope (Codex round-9 lock).
            for prop in PROPERTIES:
                if prop.station_4 != StationDisposition.COMPARE_DISPATCH:
                    continue
                spec = prop.compare_figma
                if spec is None:
                    continue  # defensive — coverage test enforces this can't happen
                # A1.3 provenance gate
                if spec.skip_when_provenance_absent and _is_snapshot_skip(
                    rendered.get("type"), spec.walker_key, element,
                ):
                    continue
                ir_value = _ir_value_for(element, prop.figma_name)
                rendered_value = _rendered_value(rendered, spec.walker_key, None)
                # Skip only on None — empty strings/falsy values still compare
                # (Codex round-9: "" vs "Hello" is a real mismatch).
                if ir_value is None or rendered_value is None:
                    continue
                impl = _COMPARATOR_IMPLS.get(spec.comparator)
                if impl is None:
                    continue  # defensive; coverage test pins this
                err = impl(ir_value, rendered_value, element, spec=spec)
                if err is not None:
                    errors.append(err)

        return RenderReport(
            backend=self.backend,
            ir_node_count=ir_count,
            rendered_node_count=rendered_count,
            errors=errors,
            runtime_errors=runtime_errors,
        )
