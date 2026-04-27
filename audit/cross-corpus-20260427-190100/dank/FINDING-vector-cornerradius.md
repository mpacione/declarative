# Finding: VECTOR cornerRadius capability gap

**Discovered**: cross-corpus Dank sweep, 2026-04-27 19:13
**DB**: `/tmp/dank-fresh-20260427.db` (fresh REST + extract-plugin)
**Sweep summary**: `audit/cross-corpus-20260427-190100/dank/summary.json`
**Status**: NOT FIXED — noted for follow-up per user directive

## Symptom

23 of 200 Dank app_screens drift. All 23 are single-error
`cornerradius_mismatch`, all on VECTOR nodes:

```
screen 62  : id='vector-1'   IR=2.0, rendered=0
screen 89  : id='vector-52'  IR=2.0, rendered=0
screen 107 : id='vector-45'  IR=2.0, rendered=0
... 23 total, identical pattern
```

## Root cause

`dd/property_registry.py:51`:

```python
_FIGMA_CORNER_CAPABLE = _FIGMA_CONTAINERS | _FIGMA_BASIC_SHAPES
# = {FRAME, COMPONENT, INSTANCE, SECTION} ∪ {RECTANGLE, ELLIPSE, POLYGON, STAR}
# VECTOR is missing.
```

The renderer's emission gate calls `is_capable("cornerRadius",
"VECTOR") -> False` and silently skips the property. The IR
correctly carries `cornerRadius=2.0`, the verifier correctly
flags the missing emission as drift. The capability table is
the only thing wrong.

## Codex 5.5 verdict (verbatim)

> Call: **(A) is correct**.
>
> Current Figma Plugin API docs explicitly list `cornerRadius`
> as supported on `VectorNode` and `BooleanOperationNode`, and
> the `VectorNode` page includes `cornerRadius` under
> "Corner-related properties." The shared property docs also
> say vector nodes can have individual corner radii on vertices.
>
> Sources:
> - https://developers.figma.com/docs/plugins/api/properties/nodes-cornerradius/
> - https://developers.figma.com/docs/plugins/api/VectorNode/
>
> So the bug is the capability table, not the IR or verifier.

## Recommended fix (NOT applied)

```python
_FIGMA_CORNER_CAPABLE = (
    _FIGMA_CONTAINERS
    | _FIGMA_BASIC_SHAPES
    | {"VECTOR", "BOOLEAN_OPERATION"}
)
```

Plus: audit whether the corner-capable universe should also
include COMPONENT_SET, SLIDE, HIGHLIGHT, SLOT etc. (Codex flag).

Test plan: a failing test that asserts `is_capable("cornerRadius",
"VECTOR")` is True, then green by the one-line table fix, then
re-sweep Dank and confirm 23 → 0.

## Observation: architectural sprint working as designed

This is the third bug class A5 has surfaced (after the original
26 cornerradius_mismatch on FRAME nodes that traced to the
`int()` truncation bug, fixed at `9037a05`). The new
comparators-on-by-default architecture is paying its way:
real bugs that were silently passing are now visible.

The fact that the bug only shows on Dank and not on Nouns is
exactly what cross-corpus validation is for — Dank has VECTORs
with rounded corners; Nouns doesn't.
