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

# Parallel fetch workers. Default is 1 (sequential) — empirically,
# Figma's 429 rate limiter kicks in aggressively on moderate-size
# files and the resulting exponential backoff on each worker more
# than eats the parallelism gain:
#
# - sequential-1 on Dank Experimental (338 screens): 79s.
# - parallel-4: ~55s before 429s exhaust the retry budget (30 dropped).
# - parallel-2 with backoff retry: 81s — same as sequential because
#   every batch hits 429 and the jittered exponential backoff
#   effectively serializes the workers.
#
# The parallel code path is preserved because it helps on smaller
# files and when a user has a higher-tier API plan. Callers can
# opt in via the ``max_workers`` constructor arg.
_DEFAULT_MAX_WORKERS = 1


class FigmaIngestAdapter:
    """Null-safe ingest adapter for Figma file-local node ids.

    Batches are fetched in parallel (default 4 workers). Every
    invariant of the sequential implementation is preserved:

    - ``extracted`` is returned in the request-id order.
    - Each batch's failure mode (exception, malformed response,
      null entry) produces the same structured-error shape as the
      sequential path.
    - A single batch raising does not cascade into sibling batches.
    """

    backend: ClassVar[str] = "figma"

    def __init__(
        self,
        *,
        file_key: str,
        token: str,
        api_client: ApiClient | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ) -> None:
        self._file_key = file_key
        self._token = token
        self._api_client = api_client or _default_api_client()
        self._batch_size = batch_size
        self._max_workers = max(1, max_workers)

    def _fetch_one_batch(
        self,
        batch: list[str],
    ) -> tuple[list[dict[str, Any]], list[StructuredError]]:
        """Fetch a single batch, returning (extracted, errors).

        Pure per-batch work — no shared state. Safe to run from a
        worker thread. Structured errors match the sequential
        implementation 1:1.
        """
        extracted: list[dict[str, Any]] = []
        errors: list[StructuredError] = []

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
            return extracted, errors

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
            return extracted, errors

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

            # perf pt 6 improvement #2: capture the per-response
            # components map so downstream node processing can
            # resolve INSTANCE componentId -> component_key from
            # REST alone (supplement pass becomes optional for this
            # field). Falls back to an empty dict if absent.
            components = {}
            if isinstance(entry, dict):
                raw = entry.get("components")
                if isinstance(raw, dict):
                    components = raw

            extracted.append(
                {"id": nid, "document": document, "components": components}
            )

        return extracted, errors

    def extract_screens(self, ids: list[str]) -> IngestResult:
        batches = list(_batches(ids, self._batch_size))

        # Preserve request id ordering by indexing each batch. Threads
        # can complete out of order; we reorder by original position
        # before returning so the downstream for-loop sees a stable
        # sequence on every run.
        results: list[tuple[list[dict[str, Any]], list[StructuredError]] | None] = [
            None
        ] * len(batches)

        if self._max_workers <= 1 or len(batches) <= 1:
            for i, batch in enumerate(batches):
                results[i] = self._fetch_one_batch(batch)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = {
                    pool.submit(self._fetch_one_batch, batch): i
                    for i, batch in enumerate(batches)
                }
                for fut in as_completed(futures):
                    i = futures[fut]
                    try:
                        results[i] = fut.result()
                    except Exception as exc:
                        # _fetch_one_batch is defensive, but if something
                        # utterly unexpected slips through, surface it as
                        # structured errors rather than crashing.
                        batch = batches[i]
                        results[i] = (
                            [],
                            [
                                StructuredError(
                                    kind=KIND_API_ERROR,
                                    id=nid,
                                    error=str(exc),
                                    context={"batch_size": len(batch)},
                                )
                                for nid in batch
                            ],
                        )

        extracted: list[dict[str, Any]] = []
        errors: list[StructuredError] = []
        for pair in results:
            assert pair is not None, "every batch should have been processed"
            batch_extracted, batch_errors = pair
            extracted.extend(batch_extracted)
            errors.extend(batch_errors)

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
