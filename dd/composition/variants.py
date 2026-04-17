"""Compound-variant application (ADR-008).

cva-style layering inside a single :class:`PresentationTemplate`: the
template carries base ``layout``/``style``/``slots`` fields plus a list
of :class:`CompoundOverride`s that apply shallow-merge patches when all
their ``match`` axes align with the resolution context.

This is *intra*-template layering — not cross-library merging. Two
providers contributing different compound overrides for the same type
is a registry / precedence concern (``registry.py``), not a variants
concern.
"""

from __future__ import annotations

from typing import Any

from dd.composition.protocol import PresentationTemplate


def _shallow_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge ``patch`` onto ``base`` (patch wins on key collision)."""
    out = dict(base)
    for k, v in patch.items():
        out[k] = v
    return out


def apply_variants(
    template: PresentationTemplate,
    axes: dict[str, str],
) -> dict[str, Any]:
    """Resolve a template against a specific axis-value context.

    Walks each :class:`CompoundOverride` on the template; for every
    override whose ``match`` axes ALL appear in ``axes`` with matching
    values, layers its ``overrides`` onto the accumulating result via
    shallow-merge (later overrides win on collision).

    Returns a plain dict with ``layout``, ``slots``, ``style``,
    ``catalog_type``, ``variant``, ``provider``. The compound_variants
    list is NOT returned — it has been applied.
    """
    result: dict[str, Any] = {
        "catalog_type": template.catalog_type,
        "variant": template.variant,
        "provider": template.provider,
        "layout": dict(template.layout),
        "slots": dict(template.slots),
        "style": dict(template.style),
    }

    for override in template.compound_variants:
        if all(axes.get(k) == v for k, v in override.match.items()):
            for field_name, patch in override.overrides.items():
                base = result.get(field_name, {})
                if isinstance(base, dict) and isinstance(patch, dict):
                    result[field_name] = _shallow_merge(base, patch)
                else:
                    result[field_name] = patch

    return result
