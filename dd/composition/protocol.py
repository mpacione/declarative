"""Composition protocol — provider contract + data classes (ADR-008).

Mirrors ``dd/boundary.py``'s ``IngestAdapter`` shape on the egress side:
every provider implements ``supports(type, variant) -> bool`` and
``resolve(type, variant, context) -> PresentationTemplate | None``, and
partial matches surface through ``StructuredError`` rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable


@dataclass(frozen=True)
class SlotSpec:
    """Typed slot contract for a :class:`PresentationTemplate`.

    ``allowed`` is a list of catalog type names that may fill this slot.
    ``required`` gates whether a missing child emits a structured error.
    ``position`` and ``quantity`` mirror the catalog's slot_definitions.
    ``default_child`` is an optional IR-child dict the provider supplies
    when no caller-provided child exists for this slot.
    """

    allowed: list[str]
    required: bool = False
    position: str | None = None
    quantity: str = "single"
    default_child: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompoundOverride:
    """A cva-style compound-variant override.

    ``match`` is a dict of axis->value pairs; ALL axes must match the
    resolution context for the override to apply. ``overrides`` is a
    shallow-merge patch applied to the base template's fields.
    """

    match: dict[str, str]
    overrides: dict[str, Any]


@dataclass(frozen=True)
class PresentationTemplate:
    """A resolved presentation template for a (type, variant) pair.

    Lives in memory at resolution time; never persisted. The template's
    fields carry unresolved DTCG token refs (``{color.brand.primary}``)
    which the :class:`TokenCascade` resolves after registry lookup.

    ``corpus_subtree`` is the v0.2 retrieval extension: when populated by
    ``CorpusRetrievalProvider``, it carries a real IR subtree extracted
    from the DB corpus. Compose splices the subtree in place of
    synthesising from layout/style/slots. Shape:
    ``{source_screen_id, source_node_id, root: eid, elements: {eid: {...}}}``.
    """

    catalog_type: str
    variant: str | None
    provider: str
    layout: dict[str, Any] = field(default_factory=dict)
    slots: dict[str, SlotSpec] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    compound_variants: list[CompoundOverride] = field(default_factory=list)
    corpus_subtree: dict[str, Any] | None = None


@runtime_checkable
class ComponentProvider(Protocol):
    """Egress-side twin of ``IngestAdapter``.

    Implementations declare an integer ``priority`` (higher wins) and a
    ``backend`` string (alphabetical tie-break at equal priority).
    ``supports`` is the honesty gate: a provider that returns True here
    must return a non-None template from ``resolve``.
    """

    backend: ClassVar[str]
    priority: ClassVar[int]

    def supports(self, catalog_type: str, variant: str | None) -> bool: ...

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> PresentationTemplate | None: ...
