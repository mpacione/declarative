"""Slot-type validation (ADR-008).

Validates a child IR node against a template's :class:`SlotSpec`.
Returns a list of :class:`StructuredError` entries — empty on success,
populated with ``KIND_SLOT_TYPE_MISMATCH`` when the child's catalog
type isn't in the slot's ``allowed`` list.

The validator is non-blocking: even on mismatch the caller is expected
to splice the child anyway (with the warning recorded). Preventing
render on a slot-type error would silently cost content; the structured
error is the right granularity.
"""

from __future__ import annotations

from typing import Any

from dd.boundary import KIND_SLOT_TYPE_MISMATCH, StructuredError
from dd.composition.protocol import PresentationTemplate


def validate_slot_child(
    template: PresentationTemplate,
    slot_name: str,
    child: dict[str, Any],
) -> list[StructuredError]:
    """Validate that ``child``'s type is allowed in ``template.slots[slot_name]``.

    Returns a (possibly empty) list of ``StructuredError`` entries.
    Unknown slot names are ignored (they're caller-supplied and may be
    out-of-contract — the provider is free to accept any slot).
    """
    slot = template.slots.get(slot_name)
    if slot is None:
        return []

    child_type = child.get("type") or ""
    if not slot.allowed:
        return []
    if "any" in slot.allowed or child_type in slot.allowed:
        return []

    return [
        StructuredError(
            kind=KIND_SLOT_TYPE_MISMATCH,
            id=f"{template.catalog_type}/{slot_name}",
            error=(
                f"slot '{slot_name}' on '{template.catalog_type}' expects one "
                f"of {slot.allowed}, got '{child_type}'"
            ),
            context={
                "catalog_type": template.catalog_type,
                "slot_name": slot_name,
                "allowed": list(slot.allowed),
                "got": child_type,
            },
        ),
    ]
