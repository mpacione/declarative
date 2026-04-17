"""Provider registry (ADR-008).

Ordered registry of :class:`ComponentProvider` instances. ``resolve``
walks providers by descending priority (alphabetical tie-break on
``backend`` for determinism) and returns the first
``supports()``-true match.

Failure modes on registry exhaustion or partial-match produce
``StructuredError`` entries through the ADR-006/007 channel using the
``KIND_NO_PROVIDER_MATCH`` / ``KIND_VARIANT_NOT_FOUND`` vocabulary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from dd.boundary import (
    KIND_NO_PROVIDER_MATCH,
    KIND_VARIANT_NOT_FOUND,
    StructuredError,
)
from dd.composition.protocol import ComponentProvider, PresentationTemplate


@dataclass(frozen=True)
class ProviderRegistry:
    """Immutable ordered provider registry.

    Construct once from a list of providers; ``resolve`` is a pure
    function over ``(type, variant, context)``.
    """

    providers: list[ComponentProvider] = field(default_factory=list)

    def _ordered(self) -> list[ComponentProvider]:
        """Return providers sorted by priority desc, backend name asc."""
        return sorted(
            self.providers,
            key=lambda p: (-p.priority, p.backend),
        )

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> tuple[PresentationTemplate | None, list[StructuredError]]:
        """Walk providers; return (template, errors).

        First provider whose ``supports(type, variant)`` is True AND
        whose ``resolve`` returns a non-None template wins. Providers
        that claim support but return None are a protocol violation
        (silently skipped; the registry does not second-guess them).

        Exhausting the registry without a match yields ``None`` for the
        template plus a terminal ``KIND_NO_PROVIDER_MATCH`` error. Along
        the way, any provider that would not accept the variant emits
        an informational ``KIND_VARIANT_NOT_FOUND`` so the walk history
        is auditable downstream.
        """
        errors: list[StructuredError] = []
        disabled = _disabled_backends()

        for provider in self._ordered():
            if provider.backend in disabled:
                continue
            if not provider.supports(catalog_type, variant):
                errors.append(
                    StructuredError(
                        kind=KIND_VARIANT_NOT_FOUND,
                        id=f"{catalog_type}/{variant or 'default'}",
                        error=(
                            f"provider '{provider.backend}' does not support "
                            f"('{catalog_type}', variant='{variant}')"
                        ),
                        context={
                            "provider": provider.backend,
                            "catalog_type": catalog_type,
                            "variant": variant,
                        },
                    ),
                )
                continue
            template = provider.resolve(catalog_type, variant, context)
            if template is not None:
                return template, errors

        errors.append(
            StructuredError(
                kind=KIND_NO_PROVIDER_MATCH,
                id=f"{catalog_type}/{variant or 'default'}",
                error=(
                    f"no provider matched ('{catalog_type}', "
                    f"variant='{variant}')"
                ),
                context={
                    "catalog_type": catalog_type,
                    "variant": variant,
                    "providers_tried": [
                        p.backend for p in self._ordered()
                        if p.backend not in disabled
                    ],
                },
            ),
        )
        return None, errors


def _disabled_backends() -> frozenset[str]:
    """Read ``DD_DISABLE_PROVIDER`` (comma-separated) from the env.

    Used by the registry to surgically drop a provider without
    requiring code changes. Empty env var = no disables.
    """
    raw = os.environ.get("DD_DISABLE_PROVIDER", "")
    return frozenset(
        token.strip() for token in raw.split(",") if token.strip()
    )


def build_registry_from_env(
    providers: list[ComponentProvider] | None = None,
) -> ProviderRegistry:
    """Build a ProviderRegistry honoring ``DD_DISABLE_PROVIDER``.

    If ``providers`` is None, returns a registry with the built-in
    default provider set (which PR #1 wires up incrementally — for
    now, an empty registry). Callers supplying explicit providers use
    the env var only to filter.
    """
    disabled = _disabled_backends()
    if providers is None:
        providers = []
    filtered = [p for p in providers if p.backend not in disabled]
    return ProviderRegistry(providers=filtered)
