"""Figma instantiation of the ADR-006 boundary contract.

Wraps the thin REST client in ``dd/figma_api.py`` with two adapter
classes that satisfy the backend-neutral protocols in ``dd/boundary.py``:

- ``FigmaIngestAdapter.extract_screens(ids)`` returns an ``IngestResult``,
  converting every null response or batch-level exception into a
  structured error rather than crashing the extraction.
- ``FigmaResourceProbe.probe(ids)`` returns a ``FreshnessReport`` that
  classifies ids as valid / missing / unknown.

Both accept an injected ``api_client`` callable with the same signature
as ``dd.figma_api.get_screen_nodes`` so that tests can supply a fake.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from dd.boundary import (
    FreshnessReport,
    IngestResult,
    IngestSummary,
    KIND_API_ERROR,
    KIND_MALFORMED_RESPONSE,
    KIND_NODE_NOT_FOUND,
    StructuredError,
)

ApiClient = Callable[[str, str, list[str]], dict[str, Any]]


def _default_api_client() -> ApiClient:
    """Lazy import of the real Figma client so tests don't pull requests."""
    from dd.figma_api import get_screen_nodes
    return get_screen_nodes


# Figma hard-caps /v1/files/{key}/nodes at ~50 ids per request; keep
# batches small enough that rate-limit retries don't blow the timeout.
_DEFAULT_BATCH_SIZE = 10


class FigmaIngestAdapter:
    """Null-safe ingest adapter for Figma file-local node ids."""

    backend: ClassVar[str] = "figma"

    def __init__(
        self,
        *,
        file_key: str,
        token: str,
        api_client: ApiClient | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self._file_key = file_key
        self._token = token
        self._api_client = api_client or _default_api_client()
        self._batch_size = batch_size

    def extract_screens(self, ids: list[str]) -> IngestResult:
        extracted: list[dict[str, Any]] = []
        errors: list[StructuredError] = []

        for batch in _batches(ids, self._batch_size):
            try:
                resp = self._api_client(self._file_key, self._token, batch)
            except Exception as exc:
                for nid in batch:
                    errors.append(
                        StructuredError(
                            kind=KIND_API_ERROR,
                            id=nid,
                            error=str(exc),
                            context={"batch_size": len(batch)},
                        )
                    )
                continue

            nodes = resp.get("nodes") if isinstance(resp, dict) else None
            if not isinstance(nodes, dict):
                for nid in batch:
                    errors.append(
                        StructuredError(
                            kind=KIND_MALFORMED_RESPONSE,
                            id=nid,
                            error="missing 'nodes' key in response",
                        )
                    )
                continue

            for nid in batch:
                entry = nodes.get(nid)
                if entry is None:
                    errors.append(
                        StructuredError(
                            kind=KIND_NODE_NOT_FOUND,
                            id=nid,
                            error="Figma API returned null for this id",
                        )
                    )
                    continue

                document = entry.get("document") if isinstance(entry, dict) else None
                if document is None:
                    errors.append(
                        StructuredError(
                            kind=KIND_MALFORMED_RESPONSE,
                            id=nid,
                            error="entry missing 'document'",
                        )
                    )
                    continue

                extracted.append({"id": nid, "document": document})

        summary = IngestSummary(
            requested=len(ids),
            succeeded=len(extracted),
            failed=len(errors),
        )
        return IngestResult(extracted=extracted, errors=errors, summary=summary)


class FigmaResourceProbe:
    """Figma resource-freshness probe.

    Classifies ids as valid (found), missing (API explicitly returned
    null — source drift), or unknown (transient error, couldn't decide).
    """

    backend: ClassVar[str] = "figma"

    def __init__(
        self,
        *,
        file_key: str,
        token: str,
        api_client: ApiClient | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self._file_key = file_key
        self._token = token
        self._api_client = api_client or _default_api_client()
        self._batch_size = batch_size

    def probe(self, ids: Iterable[str]) -> FreshnessReport:
        id_list = list(ids)
        valid: set[str] = set()
        missing: set[str] = set()
        unknown: set[str] = set()
        errors: list[StructuredError] = []

        for batch in _batches(id_list, self._batch_size):
            try:
                resp = self._api_client(self._file_key, self._token, batch)
            except Exception as exc:
                for nid in batch:
                    unknown.add(nid)
                    errors.append(
                        StructuredError(
                            kind=KIND_API_ERROR,
                            id=nid,
                            error=str(exc),
                            context={"batch_size": len(batch)},
                        )
                    )
                continue

            nodes = resp.get("nodes") if isinstance(resp, dict) else None
            if not isinstance(nodes, dict):
                for nid in batch:
                    unknown.add(nid)
                    errors.append(
                        StructuredError(
                            kind=KIND_MALFORMED_RESPONSE,
                            id=nid,
                            error="missing 'nodes' key in response",
                        )
                    )
                continue

            for nid in batch:
                entry = nodes.get(nid)
                if entry is None:
                    missing.add(nid)
                else:
                    valid.add(nid)

        return FreshnessReport(
            backend=self.backend,
            checked=len(id_list),
            valid_ids=frozenset(valid),
            missing_ids=frozenset(missing),
            unknown_ids=frozenset(unknown),
            errors=errors,
        )


def _batches(xs: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(xs), size):
        yield xs[i : i + size]
