"""Ingested-system provider (ADR-008) — priority 50.

Generic provider shell for external design-system libraries imported
through the ADR-006 ``IngestAdapter`` surface. The concrete shadcn /
Material-3 / Carbon adapters populate a lookup table keyed by
(catalog_type, variant); this provider walks the same table at
resolution time.

v0.1 ships the contract and an empty default table. Populating the
table with real shadcn templates lands as the shadcn ingest adapter
(separate PR under ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from dd.composition.protocol import PresentationTemplate


@dataclass
class IngestedSystemProvider:
    """Ingested external design-system provider.

    ``backend`` encodes the origin system: ``ingested:shadcn``,
    ``ingested:material-3``, etc. ``templates`` is a lookup table keyed
    by ``(catalog_type, variant)`` → :class:`PresentationTemplate`.
    """

    backend_key: str  # e.g. "shadcn"
    templates: dict[tuple[str, str | None], PresentationTemplate] = field(default_factory=dict)

    priority: ClassVar[int] = 50

    @property
    def backend(self) -> str:
        return f"ingested:{self.backend_key}"

    def supports(self, catalog_type: str, variant: str | None) -> bool:
        # Strict match on the exact pair; fall through otherwise so the
        # registry can continue the walk. Variant=None as a query means
        # "default variant" — providers that only have a "primary"
        # template do NOT claim support for (type, None).
        return (catalog_type, variant) in self.templates

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> PresentationTemplate | None:
        return self.templates.get((catalog_type, variant))
