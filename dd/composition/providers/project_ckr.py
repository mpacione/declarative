"""Project CKR provider (ADR-008) — priority 100, backend ``project:ckr``.

Reads the user's own corpus:

- ``component_key_registry`` for known Mode-1 component keys (names +
  Figma node ids).
- ``variant_token_binding`` for per-(type, variant, slot) bindings
  learned by :mod:`dd.cluster_variants`.

Wins over every ingested system and the universal catalog. Returns
``None`` when the corpus has no binding for the requested pair — walk
proceeds to the ingested provider.

Emits ``KIND_VARIANT_BINDING_MISSING`` when a ``supports()``-true
match runs into an empty ``variant_token_binding`` row (e.g. the
inducer hasn't finished clustering this type yet); a fall-back
template still returns so render proceeds.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, ClassVar

from dd.boundary import KIND_VARIANT_BINDING_MISSING, StructuredError
from dd.composition.protocol import PresentationTemplate, SlotSpec


@dataclass
class ProjectCKRProvider:
    """Project-native provider backed by SQLite."""

    conn: sqlite3.Connection

    backend: ClassVar[str] = "project:ckr"
    priority: ClassVar[int] = 100

    def _bindings_for(
        self, catalog_type: str, variant: str | None,
    ) -> list[dict[str, Any]]:
        """Fetch variant_token_binding rows for a (type, variant) pair."""
        if variant is not None:
            rows = self.conn.execute(
                "SELECT slot, token_id, literal_value, confidence, source "
                "FROM variant_token_binding "
                "WHERE catalog_type = ? AND variant = ?",
                (catalog_type, variant),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT slot, token_id, literal_value, confidence, source "
                "FROM variant_token_binding "
                "WHERE catalog_type = ?",
                (catalog_type,),
            ).fetchall()
        return [
            {"slot": r[0], "token_id": r[1], "literal_value": r[2], "confidence": r[3], "source": r[4]}
            for r in rows
        ]

    def supports(self, catalog_type: str, variant: str | None) -> bool:
        """True when the corpus has any binding OR any CKR entry for the pair.

        We are intentionally permissive at the ``supports`` gate — the
        corpus is the authoritative design system, so if the user's
        extracted file mentions the type at all (either via a CKR
        component_key whose name starts with ``<type>/`` or via an
        existing variant_token_binding), we commit to returning a
        template. The ``resolve`` path may still fall back to a minimal
        shape plus a ``KIND_VARIANT_BINDING_MISSING`` entry when the
        binding isn't populated yet.
        """
        binding_count = self.conn.execute(
            "SELECT COUNT(*) FROM variant_token_binding "
            "WHERE catalog_type = ?",
            (catalog_type,),
        ).fetchone()[0]
        if binding_count > 0:
            return True

        # CKR entry whose name namespace matches the catalog type.
        ckr_count = self.conn.execute(
            "SELECT COUNT(*) FROM component_key_registry "
            "WHERE name LIKE ? OR name = ?",
            (f"{catalog_type}/%", catalog_type),
        ).fetchone()[0]
        return ckr_count > 0

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> PresentationTemplate | None:
        """Return a project-native template (or ``None`` if no match).

        Populates ``context["__errors__"]`` — when present — with a
        ``KIND_VARIANT_BINDING_MISSING`` entry if the pair has a
        ``supports()``-true claim but no binding row. Callers are
        expected to collect those errors from the context dict.
        """
        bindings = self._bindings_for(catalog_type, variant)
        errors_sink = context.setdefault("__errors__", []) if isinstance(context, dict) else []

        slots_style: dict[str, Any] = {}
        for binding in bindings:
            value = binding.get("literal_value")
            if value is not None:
                slots_style[binding["slot"]] = value

        if not bindings:
            errors_sink.append(
                StructuredError(
                    kind=KIND_VARIANT_BINDING_MISSING,
                    id=f"{catalog_type}/{variant or 'default'}",
                    error=(
                        f"no variant_token_binding row for "
                        f"('{catalog_type}', variant='{variant}')"
                    ),
                    context={
                        "catalog_type": catalog_type,
                        "variant": variant,
                    },
                )
            )

        return PresentationTemplate(
            catalog_type=catalog_type,
            variant=variant,
            provider="project:ckr",
            layout={},
            slots={
                "label": SlotSpec(allowed=["text"], required=False, position="fill"),
            },
            style=slots_style or {"fill": "{color.surface.default}"},
        )
