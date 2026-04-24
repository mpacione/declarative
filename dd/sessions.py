"""Stage 3.2 — sessions persistence layer.

CRUD wrapping the migration-023 shape. Per Codex+Sonnet 2026-04-23
unanimous picks: Option 3 (gzipped TEXT snapshots, no sibling blob
store) + B (keep move_log).

Provides the building blocks Stage 3.3's loop + Stage 3.4's CLI
both consume:

- ``create_session(conn, brief) -> session_id``
- ``create_variant(conn, session_id, parent_id, primitive,
    edit_script, doc, scores=None, notes=None) -> variant_id``
- ``load_variant(conn, variant_id) -> VariantRow | None``
- ``list_variants(conn, session_id) -> list[VariantRow]``
- ``append_move_log_entry(conn, session_id, variant_id, entry)``
- ``list_move_log(conn, session_id) -> list[MoveLogEntry]``
- ``list_sessions(conn, status_filter=None) -> list[SessionRow]``

Stage-3 read paths return decoded markup as L3Document — caller
doesn't need to know about the gzip+base64 storage detail.
"""

from __future__ import annotations

import base64
import gzip
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from dd.focus import MoveLogEntry
from dd.markup_l3 import L3Document, emit_l3, parse_l3
from dd.ulid import ulid


# --------------------------------------------------------------------------- #
# Row shapes                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SessionRow:
    id: str
    brief: str
    status: str
    created_at: str


@dataclass(frozen=True)
class VariantRow:
    id: str
    session_id: str
    parent_id: Optional[str]
    primitive: Optional[str]
    edit_script: Optional[str]
    doc: L3Document
    scores: Optional[dict[str, Any]]
    status: str
    notes: Optional[str]
    created_at: str


# --------------------------------------------------------------------------- #
# Markup snapshot encoding                                                    #
# --------------------------------------------------------------------------- #

def _encode_doc(doc: L3Document) -> str:
    """Compress an L3Document to gzip + base64 text for the variants
    .markup_blob TEXT column. Per Option 3: no sibling
    session_blobs table; gzipped TEXT inline is enough at 10
    iters/session scale."""
    raw = emit_l3(doc).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def _decode_doc(blob: str) -> L3Document:
    raw = gzip.decompress(base64.b64decode(blob.encode("ascii")))
    return parse_l3(raw.decode("utf-8"))


# --------------------------------------------------------------------------- #
# Sessions                                                                    #
# --------------------------------------------------------------------------- #

def create_session(conn: sqlite3.Connection, *, brief: str) -> str:
    """Insert a new session row and return its ULID."""
    if not brief or not brief.strip():
        raise ValueError("brief must not be blank")
    sid = ulid()
    conn.execute(
        "INSERT INTO design_sessions (id, brief) VALUES (?, ?)",
        (sid, brief),
    )
    conn.commit()
    return sid


def list_sessions(
    conn: sqlite3.Connection,
    *,
    status_filter: Optional[str] = None,
) -> list[SessionRow]:
    """Return sessions chronologically (ULID prefix sort matches
    creation time). Optional status filter."""
    if status_filter is not None:
        rows = conn.execute(
            "SELECT id, brief, status, created_at "
            "FROM design_sessions WHERE status=? "
            "ORDER BY id",
            (status_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, brief, status, created_at "
            "FROM design_sessions ORDER BY id"
        ).fetchall()
    return [
        SessionRow(
            id=r["id"], brief=r["brief"],
            status=r["status"], created_at=r["created_at"],
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Variants                                                                    #
# --------------------------------------------------------------------------- #

def create_variant(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    parent_id: Optional[str],
    primitive: Optional[str],
    edit_script: Optional[str],
    doc: L3Document,
    scores: Optional[dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> str:
    """Insert a new variant row. Returns the new ULID."""
    vid = ulid()
    conn.execute(
        "INSERT INTO variants "
        "(id, session_id, parent_id, primitive, edit_script, "
        " markup_blob, scores, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            vid, session_id, parent_id, primitive, edit_script,
            _encode_doc(doc),
            json.dumps(scores) if scores is not None else None,
            notes,
        ),
    )
    conn.commit()
    return vid


def load_variant(
    conn: sqlite3.Connection, variant_id: str,
) -> Optional[VariantRow]:
    """Fetch + decode one variant. Returns None if not found."""
    row = conn.execute(
        "SELECT id, session_id, parent_id, primitive, edit_script, "
        "       markup_blob, scores, status, notes, created_at "
        "FROM variants WHERE id=?",
        (variant_id,),
    ).fetchone()
    if row is None:
        return None
    return VariantRow(
        id=row["id"],
        session_id=row["session_id"],
        parent_id=row["parent_id"],
        primitive=row["primitive"],
        edit_script=row["edit_script"],
        doc=_decode_doc(row["markup_blob"]) if row["markup_blob"] else None,
        scores=json.loads(row["scores"]) if row["scores"] else None,
        status=row["status"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def iter_edits_on_path(
    conn: sqlite3.Connection, variant_id: str,
) -> list[object]:
    """Walk ``parent_id`` from ROOT → ``variant_id`` and return the
    concatenated L3 edit statements in root-to-leaf order.

    Each variant's ``edit_script`` is the raw L3 markup that was
    applied at that step (e.g. ``"delete @rectangle-22280"``). NAME /
    DRILL / CLIMB / ROOT variants carry ``edit_script=NULL`` and
    contribute nothing. The returned list is flat and suitable to
    feed :func:`dd.markup_l3.apply_edits` or
    :func:`dd.apply_render.render_applied_doc`.

    M1 of the authoring-loop Figma round-trip uses this to reconstruct
    the cumulative edit sequence that turned the starting screen into
    the session's final variant — the renderer's nid/spec-key maps
    need the original AST + the full edit list to stay aligned through
    ``rebuild_maps_after_edits``. Stage 4+ MCTS will use the same
    walker to reconstruct any point in the variant DAG.

    Raises ``ValueError`` when ``variant_id`` is absent, an
    intermediate variant references a missing parent, or the
    parent_id chain contains a cycle (per Codex risk note on corrupt
    parent pointers).
    """
    from dd.markup_l3 import parse_l3

    # Walk leaf-to-root first, collecting variants as we go.
    chain: list[VariantRow] = []
    visited: set[str] = set()
    cursor: Optional[str] = variant_id

    while cursor is not None:
        if cursor in visited:
            raise ValueError(
                f"parent_id cycle detected at variant {cursor!r}"
            )
        visited.add(cursor)
        row = conn.execute(
            "SELECT id, parent_id, edit_script FROM variants WHERE id=?",
            (cursor,),
        ).fetchone()
        if row is None:
            if not chain:
                raise ValueError(
                    f"variant {variant_id!r} not found"
                )
            raise ValueError(
                f"variant {cursor!r} referenced as parent but not "
                "found (corrupt parent chain)"
            )
        chain.append(row)
        cursor = row["parent_id"]

    # Reverse to root-to-leaf, concat edits.
    edits: list[object] = []
    for row in reversed(chain):
        src = row["edit_script"]
        if not src:
            continue
        parsed = parse_l3(src)
        edits.extend(parsed.edits)
    return edits


def list_variants(
    conn: sqlite3.Connection, session_id: str,
) -> list[VariantRow]:
    """All variants for a session, chronologically (ULID sort).
    Decodes the markup blob for each row — caller can use VariantRow
    directly."""
    rows = conn.execute(
        "SELECT id, session_id, parent_id, primitive, edit_script, "
        "       markup_blob, scores, status, notes, created_at "
        "FROM variants WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [
        VariantRow(
            id=r["id"],
            session_id=r["session_id"],
            parent_id=r["parent_id"],
            primitive=r["primitive"],
            edit_script=r["edit_script"],
            doc=_decode_doc(r["markup_blob"]) if r["markup_blob"] else None,
            scores=json.loads(r["scores"]) if r["scores"] else None,
            status=r["status"],
            notes=r["notes"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# move_log                                                                    #
# --------------------------------------------------------------------------- #

def append_move_log_entry(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    variant_id: Optional[str],
    entry: MoveLogEntry,
) -> None:
    """Persist a Stage-2 MoveLogEntry as a move_log row.

    Stage 2's MoveLogEntry.to_dict() shape (commit fd5c5c5) is the
    payload column verbatim — round-trip lossless.
    """
    conn.execute(
        "INSERT INTO move_log "
        "(session_id, variant_id, primitive, payload) "
        "VALUES (?, ?, ?, ?)",
        (session_id, variant_id, entry.primitive, json.dumps(entry.to_dict())),
    )
    conn.commit()


def list_move_log(
    conn: sqlite3.Connection, session_id: str,
) -> list[MoveLogEntry]:
    """Return every move-log entry for a session, chronologically.
    Reconstructs MoveLogEntry instances from the JSON payload."""
    rows = conn.execute(
        "SELECT payload FROM move_log "
        "WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    out: list[MoveLogEntry] = []
    for r in rows:
        d = json.loads(r["payload"])
        out.append(MoveLogEntry(
            primitive=d["primitive"],
            scope_eid=d.get("scope_eid"),
            payload=d.get("payload") or {},
            rationale=d.get("rationale"),
            ts=d.get("ts", 0.0),
        ))
    return out
