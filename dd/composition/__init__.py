"""Mode 3 composition — ADR-008.

Synthesise UI subtrees from a catalog type + variant + context when the
user's corpus (Mode 1) and the DB's L0 visual properties (Mode 2) both
fall through. Three sub-modules:

- :mod:`dd.composition.protocol` — ``ComponentProvider`` Protocol +
  data classes (``PresentationTemplate``, ``SlotSpec``, ``CompoundOverride``).
- :mod:`dd.composition.registry` — ordered provider registry with
  priority walk, alphabetical tie-break, structured-error emission.
- :mod:`dd.composition.cascade` — DTCG token cascade
  (project > ingested > universal).
- :mod:`dd.composition.slots` — slot-type validation.
- :mod:`dd.composition.variants` — compound-variant application (cva-style).
- :mod:`dd.composition.providers.*` — built-in providers.

See ADR-008 in ``docs/architecture-decisions.md`` for the full
specification.
"""

from dd.composition.protocol import (
    ComponentProvider,
    CompoundOverride,
    PresentationTemplate,
    SlotSpec,
)
from dd.composition.registry import ProviderRegistry

__all__ = [
    "ComponentProvider",
    "CompoundOverride",
    "PresentationTemplate",
    "ProviderRegistry",
    "SlotSpec",
]
