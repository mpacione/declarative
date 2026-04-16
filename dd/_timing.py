"""Lightweight stage timing + throughput instrumentation.

Used by the extract pipeline to attribute time across stages so we can
find bottlenecks. Zero-dependency; writes a summary table to stderr
and optionally appends per-run data to a JSON log for longitudinal
analysis.

Usage:

    from dd._timing import StageTimer

    timer = StageTimer()
    with timer.stage("inventory"):
        ...
    with timer.stage("rest_extraction", items=len(screens), unit="screens"):
        ...
    timer.print_summary()
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageRecord:
    """One completed stage."""
    name: str
    duration_s: float
    items: int | None = None
    unit: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def throughput(self) -> float | None:
        if not self.items or self.duration_s <= 0:
            return None
        return self.items / self.duration_s

    def fmt(self) -> str:
        dur = f"{self.duration_s:7.2f}s"
        if self.items is not None:
            thr = f"{self.throughput:>6.1f} {self.unit or 'items'}/s" if self.throughput else ""
            return f"{self.name:36s} {dur}   {self.items:6d} {self.unit or 'items':10s}  {thr}"
        return f"{self.name:36s} {dur}"


class StageTimer:
    """Collect per-stage durations + throughput. One instance per pipeline run."""

    def __init__(self, log_path: str | None = None) -> None:
        self._records: list[StageRecord] = []
        self._stack: list[tuple[str, float]] = []
        # Default log path: ~/.cache/dd/extract_timings.jsonl — append-only
        # longitudinal log so we can see trends across runs.
        if log_path is None:
            cache = os.path.expanduser("~/.cache/dd")
            os.makedirs(cache, exist_ok=True)
            log_path = os.path.join(cache, "extract_timings.jsonl")
        self._log_path = log_path
        self._run_start = time.monotonic()
        self._run_meta: dict[str, Any] = {}

    def meta(self, **kwargs: Any) -> None:
        """Record top-level metadata (file_key, screen_count, etc.) for the log."""
        self._run_meta.update(kwargs)

    @contextmanager
    def stage(
        self,
        name: str,
        items: int | None = None,
        unit: str | None = None,
        **extra: Any,
    ):
        """Context manager that times a block and records a StageRecord.

        Supports nesting (inner stages are recorded too). The `items` arg
        enables throughput reporting (items/sec). `extra` captures
        stage-specific details (batch_count, failed_count, etc.).
        """
        self._stack.append((name, time.monotonic()))
        print(f"[timing] ▶ {name}", file=sys.stderr, flush=True)
        try:
            yield
        finally:
            started_name, t0 = self._stack.pop()
            dur = time.monotonic() - t0
            rec = StageRecord(
                name=started_name,
                duration_s=dur,
                items=items,
                unit=unit,
                extra=dict(extra),
            )
            self._records.append(rec)
            print(f"[timing] ✓ {rec.fmt()}", file=sys.stderr, flush=True)

    def record(
        self,
        name: str,
        duration_s: float,
        items: int | None = None,
        unit: str | None = None,
        **extra: Any,
    ) -> None:
        """Record a stage without using the context manager (e.g. from async callers)."""
        self._records.append(StageRecord(
            name=name, duration_s=duration_s, items=items, unit=unit, extra=dict(extra),
        ))

    def print_summary(self) -> None:
        """Print a summary table + append to the longitudinal log."""
        total = time.monotonic() - self._run_start
        print("", file=sys.stderr)
        print("=" * 88, file=sys.stderr)
        print(
            f"{'stage':36s} {'duration':>9s}   {'items':>6s} {'unit':10s}  {'throughput'}",
            file=sys.stderr,
        )
        print("-" * 88, file=sys.stderr)
        for rec in self._records:
            print(rec.fmt(), file=sys.stderr)
        print("-" * 88, file=sys.stderr)
        tracked = sum(r.duration_s for r in self._records)
        overhead = max(0.0, total - tracked)
        print(
            f"{'TOTAL (tracked)':36s} {tracked:7.2f}s",
            file=sys.stderr,
        )
        print(
            f"{'TOTAL (wall)':36s} {total:7.2f}s    "
            f"(untracked/overhead: {overhead:.2f}s)",
            file=sys.stderr,
        )
        print("=" * 88, file=sys.stderr)

        # Longitudinal log — one JSONL record per run
        try:
            entry = {
                "timestamp": time.time(),
                "total_wall_s": round(total, 3),
                "total_tracked_s": round(tracked, 3),
                "meta": self._run_meta,
                "stages": [
                    {
                        "name": r.name,
                        "duration_s": round(r.duration_s, 3),
                        "items": r.items,
                        "unit": r.unit,
                        **r.extra,
                    }
                    for r in self._records
                ],
            }
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Log writing is best-effort; don't let it break extraction.
            pass

    @property
    def records(self) -> list[StageRecord]:
        return list(self._records)
