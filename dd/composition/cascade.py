"""DTCG token cascade (ADR-008).

Resolves ``{color.brand.primary}``-style DTCG refs through a three-layer
ordered cascade: project > ingested > universal. First layer that
defines the path wins. Unresolved refs produce a
``KIND_TOKEN_UNRESOLVED`` structured error with a literal fallback so
render still proceeds.

Literal values (not wrapped in ``{}``) pass through unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dd.boundary import KIND_TOKEN_UNRESOLVED, StructuredError


_REF_PATTERN = re.compile(r"^\{([\w.]+)\}$")


@dataclass(frozen=True)
class TokenCascade:
    """Three-layer ordered DTCG cascade.

    Each layer is a flat ``{path: value}`` dict. Path keys are
    dotted (``color.brand.primary``). Values are strings (hex, px,
    weight, etc.) or other atomic DTCG shapes — we don't interpret
    the value at the cascade layer.
    """

    project: dict[str, Any] = field(default_factory=dict)
    ingested: dict[str, Any] = field(default_factory=dict)
    universal: dict[str, Any] = field(default_factory=dict)
    fallback_literal: str = "#000000"

    def _layers(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            ("project", self.project),
            ("ingested", self.ingested),
            ("universal", self.universal),
        ]

    def resolve(self, value: str) -> tuple[Any, list[StructuredError]]:
        """Resolve a value that may be a DTCG ref or a literal.

        Returns ``(value, errors)`` — ``errors`` is empty for literals
        and successful ref resolution; otherwise contains one
        ``KIND_TOKEN_UNRESOLVED`` entry and ``value`` is the literal
        fallback. Render downstream still proceeds.
        """
        if not isinstance(value, str):
            return value, []

        match = _REF_PATTERN.match(value)
        if not match:
            return value, []

        path = match.group(1)
        for _layer_name, layer in self._layers():
            if path in layer:
                return layer[path], []

        return self.fallback_literal, [
            StructuredError(
                kind=KIND_TOKEN_UNRESOLVED,
                id=path,
                error=f"token ref '{{{path}}}' not present in any cascade layer",
                context={"ref": path},
            ),
        ]

    def resolve_tree(
        self,
        tree: Any,
    ) -> tuple[Any, list[StructuredError]]:
        """Walk a nested dict/list resolving every ``{token}`` ref found.

        Returns ``(resolved_tree, errors)``. Errors accumulate across
        the whole walk. Non-string leaves pass through unchanged.
        """
        errors: list[StructuredError] = []

        def walk(node: Any) -> Any:
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v) for v in node]
            if isinstance(node, str):
                val, errs = self.resolve(node)
                errors.extend(errs)
                return val
            return node

        return walk(tree), errors
