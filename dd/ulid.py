"""Crockford-encoded ULID generator (zero-dep, ~10 LOC of logic).

Stage 3.1 — Codex+Sonnet 2026-04-23 audit confirmed: no python-ulid
dep in pyproject; lean-dep convention favors roll-your-own. ULIDs
serve two needs Stage 3+ depends on:

- **Lexicographic sort by time** — variants ORDER BY id is
  chronological without needing a separate created_at index.
- **Externally shareable IDs** — Stage 4's per-designer DPO and
  share-able variant URLs ("/design/01HXY.../v/01HXZ...") want
  globally-unique IDs that don't leak monotonic counts.

Format: 26 chars, Crockford base32 alphabet (no I/L/O/U). The first
10 chars encode the 48-bit timestamp (ms since epoch); the trailing
16 chars encode 80 bits of randomness from ``secrets.token_bytes``.
"""

from __future__ import annotations

import secrets
import time

# Crockford base32 alphabet — explicitly excludes I, L, O, U so
# ULIDs are unambiguous when read aloud or copy-pasted.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _b32encode(value: int, length: int) -> str:
    """Encode ``value`` as a fixed-``length`` Crockford base32 string."""
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def ulid() -> str:
    """Return a fresh 26-char Crockford-encoded ULID.

    Time prefix (10 chars) ensures lexicographic order by creation
    time. Random suffix (16 chars / 80 bits) gives collision
    resistance well beyond the codebase's plausible scale.
    """
    ts_ms = time.time_ns() // 1_000_000
    rand_bytes = secrets.token_bytes(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    return _b32encode(ts_ms, 10) + _b32encode(rand_int, 16)
