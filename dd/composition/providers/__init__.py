"""Built-in Mode-3 composition providers (ADR-008).

Each provider implements the :class:`~dd.composition.protocol.ComponentProvider`
protocol. Ordered at registration by priority; tie-breaks alphabetical
on ``backend``.

- :mod:`~dd.composition.providers.universal` — hand-authored defaults
  for the 22-type universal backbone (structure from Stream A, values
  ported from shadcn). Priority 10.
- :mod:`~dd.composition.providers.project_ckr` — reads the user's own
  corpus via ``component_key_registry`` + ``variant_token_binding``.
  Priority 100 (always wins if it has a match).
- :mod:`~dd.composition.providers.ingested` — ingested external design
  systems (shadcn, Material 3, ...) fed by ``ADR-006`` adapters.
  Priority 50.
"""
