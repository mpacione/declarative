"""P5c (Phase E Pattern 3 fix) — Axis registry + convention.

Phase E Pattern 3 traced 7 binding_token_consistency validator
warnings to a chronic class: every cluster module invented its own
contract for "round the value, store the token, bind the binding."
``cluster_colors`` got it right (snap-on-UPDATE — `dd/cluster_colors.py:289-295`).
``cluster_radius`` and ``cluster_opacity`` got it right by accident
(identity rounding). ``cluster_letter_spacing``, ``cluster_spacing``,
``cluster_effects``, and the dormant ``cluster_stroke_weight``/
``cluster_paragraph_spacing`` all needed fixes (P3c, P5a, P5b, P3b).

Sonnet's recommended structural fix was ``(A)+(D) hybrid``: a
``Cluster`` protocol that requires every module to canonicalize the
binding's ``resolved_value`` to match the token's, plus per-axis
``Axis`` spec (dtype, rounding rule, bind-key fields).

Codex Phase E review (2026-04-25, gpt-5.5) chose the leaner shape:
"AxisSpec plan is acceptable for P5 if you keep it narrow and
enforceable. The useful contract is not 'all clusters share an
interface'; it is 'UPDATE canonicalizes binding values when
clustering changes value shape.' A registry plus convention test
catches that cheaply."

The contract:

- Every cluster_* function in `dd/cluster*.py` has a paired
  ``AxisSpec`` exported from the same module (or from this file
  for cross-module axes).
- The AxisSpec's ``snap_on_update`` field declares whether the
  clusterer is required to rewrite ``binding.resolved_value`` to
  match ``token.resolved_value`` on UPDATE. ``True`` for numeric
  axes that go through any rounding; ``False`` is allowed only when
  the axis is identity-preserving (e.g. an enum like fontWeight).
- The convention test in ``tests/test_p5c_axis_spec.py`` walks the
  cluster modules, asserts every cluster_* function has a matching
  AxisSpec, and validates each spec's contract claims against
  observed behavior on a fixture.

This module is **documentation + registry**, not refactor. The
clusters keep their existing shapes; AxisSpec just pins the
contract so a new clusterer added without snap-on-UPDATE will fail
CI before it can produce silent validator drift on a real corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AxisDtype = Literal[
    "scalar",          # plain numeric: padding, itemSpacing, radius, opacity, strokeWeight
    "json_value_unit", # {"value": <num>, "unit": <str>}: letterSpacing
    "color_hex",       # "#RRGGBB[AA]": colors, effect.color
    "effect_composite", # composite shadow keyed on (node_id, effect_idx)
    "typography_combo", # combined family/weight/size — clustered by exact match
    "enum",            # discrete enum (font weights as named values)
]


@dataclass(frozen=True)
class AxisSpec:
    """Per-axis contract for a cluster_* function.

    Attributes:
        name: Logical axis name (e.g. ``"radius"``,
            ``"letterSpacing"``). Matches the cluster_* function's
            tail name — ``cluster_radius`` ↔ ``name="radius"``.
        dtype: Value shape — drives the rounding strategy and the
            convention test's fixture.
        properties: The ``node_token_bindings.property`` values this
            axis owns (e.g. ``("padding.top", "padding.right",
            "padding.bottom", "padding.left", "itemSpacing",
            "counterAxisSpacing")`` for spacing). Used by the
            convention test to discover which bindings should be
            covered post-cluster.
        bind_key_fields: The columns/derived-keys the binding
            UPDATE step must use. ``("resolved_value",)`` is the
            common case; ``("node_id", "effect_idx")`` for effects
            (P5b). Documents the contract; any clusterer that
            updates by a less-specific key risks the
            cross-attribution bug class.
        snap_on_update: Whether the clusterer must rewrite
            ``binding.resolved_value`` to match
            ``token.resolved_value`` on UPDATE. ``True`` for any
            axis that does ANY rounding/canonicalization that could
            cause a downstream
            validator drift. The convention test fails CI if a
            clusterer marked ``snap_on_update=True`` produces
            bindings whose resolved_value doesn't match the token
            on a representative fixture.
        notes: Free-text rationale for the spec's choices. Empty
            strings are fine; non-empty makes the test report more
            useful when something fails.
    """

    name: str
    dtype: AxisDtype
    properties: tuple[str, ...]
    bind_key_fields: tuple[str, ...]
    snap_on_update: bool
    notes: str = ""


# The registry. Add a new entry when a new cluster_* function lands.
# Convention test in tests/test_p5c_axis_spec.py walks dd/cluster*.py
# for cluster_* functions and asserts every one has a matching entry.
AXIS_REGISTRY: dict[str, AxisSpec] = {
    "colors": AxisSpec(
        name="colors",
        dtype="color_hex",
        properties=(
            "fills.0.color", "fills.1.color",
            "strokes.0.color", "strokes.1.color",
        ),
        bind_key_fields=("resolved_value",),
        snap_on_update=True,
        notes=(
            "The reference implementation. cluster_colors:289-295 "
            "snaps binding.resolved_value to the delta-E "
            "representative on UPDATE. Pattern P3c/P5a/P5b/P3b "
            "ported into the rest of the cluster zoo."
        ),
    ),
    "radius": AxisSpec(
        name="radius",
        dtype="scalar",
        properties=(
            "cornerRadius",
            "topLeftRadius", "topRightRadius",
            "bottomRightRadius", "bottomLeftRadius",
        ),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "Identity-preserving today (cluster_misc.py:174-300 "
            "uses str(original_value) for both token resolved_value "
            "and the binding-lookup predicate). If radius ever "
            "starts rounding, flip snap_on_update=True."
        ),
    ),
    "spacing": AxisSpec(
        name="spacing",
        dtype="scalar",
        properties=(
            "padding.top", "padding.right",
            "padding.bottom", "padding.left",
            "itemSpacing", "counterAxisSpacing",
        ),
        bind_key_fields=("resolved_value",),
        snap_on_update=True,
        notes=(
            "P5a fix. Sub-pixel float bindings (14.5697...) round "
            "to integer tokens (15); without snap-on-UPDATE the "
            "validator's _normalize_numeric (0.001 epsilon) cannot "
            "bridge the gap and emits binding_token_consistency."
        ),
    ),
    "typography": AxisSpec(
        name="typography",
        dtype="typography_combo",
        properties=(
            "fontFamily", "fontSize", "fontWeight",
        ),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "Identity-preserving (cluster_typography.py:239-464 "
            "tiers by exact family/weight/size; no rounding)."
        ),
    ),
    "letter_spacing": AxisSpec(
        name="letter_spacing",
        dtype="json_value_unit",
        properties=("letterSpacing",),
        bind_key_fields=("resolved_value",),
        snap_on_update=True,
        notes=(
            "P3c fix. JSON {value, unit} bindings rounded to 2dp "
            "tokens; pre-P3c the binding-resolved_value column "
            "kept the raw float JSON, validator warned. Post-P3c "
            "snap-on-UPDATE writes canonical JSON to both."
        ),
    ),
    "line_height": AxisSpec(
        name="line_height",
        dtype="json_value_unit",
        properties=("lineHeight",),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "Identity-preserving today (no rounding). If line_height "
            "ever starts bucketing similar values, flip to True."
        ),
    ),
    "opacity": AxisSpec(
        name="opacity",
        dtype="scalar",
        properties=("opacity",),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "Token resolved_value = str(raw_value) exact "
            "(cluster_misc.py:788-861). Round only the NAME "
            "(0.5 -> '50'), preserve the value column."
        ),
    ),
    "effects": AxisSpec(
        name="effects",
        dtype="effect_composite",
        properties=(
            "effect.0.color", "effect.0.radius",
            "effect.0.offsetX", "effect.0.offsetY", "effect.0.spread",
            "effect.1.color", "effect.1.radius",
            "effect.1.offsetX", "effect.1.offsetY", "effect.1.spread",
        ),
        bind_key_fields=("node_id", "property"),
        snap_on_update=False,
        notes=(
            "P5b fix. The bug class is occurrence-key, not value-snap "
            "— multi-shadow nodes attributed every effect.*.field "
            "binding to the LAST composite. Fixed by carrying "
            "(node_id, effect_idx) in effect_refs and updating by "
            "exact `effect.{idx}.{field}` row. snap_on_update=False "
            "because composite-key identity already pins the field "
            "tuple; snapping value would be defensive but redundant."
        ),
    ),
    "stroke_weight": AxisSpec(
        name="stroke_weight",
        dtype="scalar",
        properties=("strokeWeight",),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "P3b wired the dormant clusterer. _cluster_simple_dimension "
            "(cluster_misc.py:864-963) uses identity rounding (val_str "
            "passes through), so snap-on-UPDATE is a no-op. If the "
            "function ever rounds, flip True."
        ),
    ),
    "paragraph_spacing": AxisSpec(
        name="paragraph_spacing",
        dtype="scalar",
        properties=("paragraphSpacing",),
        bind_key_fields=("resolved_value",),
        snap_on_update=False,
        notes=(
            "Same shape as stroke_weight — _cluster_simple_dimension "
            "identity. P3b wired the orchestrator dispatch."
        ),
    ),
}


# Logical AxisSpec name → expected cluster function name. The
# convention test uses this to match cluster_* functions discovered
# in the source against AXIS_REGISTRY entries. Most map by direct
# name (cluster_radius ↔ "radius"), but a few have name irregularities
# we document explicitly here.
CLUSTER_FN_TO_AXIS_NAME: dict[str, str] = {
    "cluster_colors": "colors",
    "cluster_radius": "radius",
    "cluster_spacing": "spacing",
    "cluster_typography": "typography",
    "cluster_letter_spacing": "letter_spacing",
    # cluster_line_height isn't a top-level dispatched function today
    # (line height is folded into cluster_typography), so no entry.
    "cluster_opacity": "opacity",
    "cluster_effects": "effects",
    "cluster_stroke_weight": "stroke_weight",
    "cluster_paragraph_spacing": "paragraph_spacing",
}
