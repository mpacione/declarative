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
- :mod:`~dd.composition.providers.corpus_retrieval` — full-subtree
  splice from a donor screen. Priority 150 (highest).

Plan §4.1 Stage-2 cleanup: the prior ``IngestedSystemProvider``
shell (priority 50) was deleted as dead code (zero callers; the
audit 2026-04-23 confirmed it was a phantom placeholder). When
external-system ingest comes back as a real ADR-006 effort, it
should be a fresh provider with concrete data, not the empty
shell that was here.
"""
