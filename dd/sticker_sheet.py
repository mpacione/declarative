"""M7.0.f — sticker-sheet authoritative tagging.

A sticker sheet is a dedicated canvas (typically ``screen_type =
'design_canvas'``) where the design system's components are
instantiated in their canonical form. Dank has two such canvases
("Frame 429" / "Frame 430"). A component's presence on a sticker
sheet is a strong signal that the component is intentional
(not drift) and that its instance there is the canonical variant.

This module tags each ``components`` row whose component_key
appears as an INSTANCE node on at least one sticker-sheet screen.
The tag is a flat string (``authoritative_source = 'sticker_sheet'``);
M7.6 S4 composition is expected to prefer tagged components as
donor candidates.

Reconciliation of the sticker-sheet's slot/variant structure vs
the M7.0.b/c heuristic output is deferred — this shipment only
persists the tag. The tagging is idempotent and incremental:
re-runs don't overwrite existing tags.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


_DEFAULT_STICKER_SHEET_SCREEN_TYPES: tuple[str, ...] = (
    "design_canvas",
)


@dataclass
class StickerSheetSummary:
    sticker_sheet_screens: int = 0
    candidate_keys: int = 0
    tagged: int = 0
    already_tagged: int = 0
    # Two distinct "not found" kinds; previously squashed into one
    # counter. ``unknown_component_keys`` is the CKR miss
    # (component_key not in component_key_registry); the newer
    # ``unregistered_components`` is the CKR hit, components miss
    # (CKR has the key but `components` doesn't have a matching
    # figma_node_id row). Downstream callers use the split to tell
    # "remote-library usage" from "extraction missed a masters row".
    unknown_component_keys: int = 0
    unregistered_components: int = 0


def find_sticker_sheet_screens(
    conn: sqlite3.Connection, *,
    screen_types: Optional[list[str]] = None,
) -> list[sqlite3.Row]:
    """Return every screen whose ``screen_type`` matches the given
    set (defaults to ``('design_canvas',)``)."""
    types = tuple(screen_types or _DEFAULT_STICKER_SHEET_SCREEN_TYPES)
    if not types:
        return []
    placeholders = ",".join("?" * len(types))
    return conn.execute(
        f"""
        SELECT id, name, screen_type
          FROM screens
         WHERE screen_type IN ({placeholders})
         ORDER BY id
        """,
        types,
    ).fetchall()


def tag_authoritative_components(
    conn: sqlite3.Connection, *,
    screen_types: Optional[list[str]] = None,
    source_label: str = "sticker_sheet",
) -> StickerSheetSummary:
    """Tag every ``components`` row whose ``component_key`` has at
    least one INSTANCE node on a sticker-sheet screen.

    Idempotent — rows with a non-null ``authoritative_source``
    are skipped (counted as ``already_tagged``). Rows whose
    component_key isn't present in the ``components`` table at
    all (remote-library instances that never populated a registry
    entry) are counted as ``unknown_component_keys`` for
    diagnostics.
    """
    summary = StickerSheetSummary()
    screens = find_sticker_sheet_screens(conn, screen_types=screen_types)
    summary.sticker_sheet_screens = len(screens)
    if not screens:
        return summary

    screen_ids = [s["id"] for s in screens]
    placeholders = ",".join("?" * len(screen_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT component_key
          FROM nodes
         WHERE screen_id IN ({placeholders})
           AND node_type = 'INSTANCE'
           AND component_key IS NOT NULL
        """,
        screen_ids,
    ).fetchall()
    candidate_keys = [r["component_key"] for r in rows]
    summary.candidate_keys = len(candidate_keys)
    if not candidate_keys:
        return summary

    # The `components` table is keyed on ``figma_node_id`` (not
    # ``component_key``) — resolve component_key → figma_node_id
    # via ``component_key_registry`` when the registry exists. Tests
    # can set up a simpler schema where `components.component_key`
    # is a real column; auto-detect which we're in.
    has_ck_col = any(
        row[1] == "component_key" for row in conn.execute(
            "PRAGMA table_info(components)"
        ).fetchall()
    )

    for ck in candidate_keys:
        if has_ck_col:
            current = conn.execute(
                "SELECT authoritative_source FROM components "
                "WHERE component_key = ?",
                (ck,),
            ).fetchone()
            update_sql = (
                "UPDATE components SET authoritative_source = ? "
                "WHERE component_key = ?"
            )
            update_args: tuple[Any, ...] = (source_label, ck)
        else:
            fk = conn.execute(
                "SELECT figma_node_id FROM component_key_registry "
                "WHERE component_key = ?",
                (ck,),
            ).fetchone()
            if fk is None:
                # CKR doesn't know the component_key — usually a
                # remote-library reference the project never
                # ingested.
                summary.unknown_component_keys += 1
                continue
            figma_node_id = fk["figma_node_id"]
            current = conn.execute(
                "SELECT authoritative_source FROM components "
                "WHERE figma_node_id = ?",
                (figma_node_id,),
            ).fetchone()
            update_sql = (
                "UPDATE components SET authoritative_source = ? "
                "WHERE figma_node_id = ?"
            )
            update_args = (source_label, figma_node_id)
            if current is None:
                # CKR has the key but the components table lacks
                # a matching row. Usually "extraction missed the
                # master" — a follow-up could file it as a
                # components backfill target.
                summary.unregistered_components += 1
                continue
        if current is None:
            # has_ck_col path: `components.component_key = ck` row
            # doesn't exist.
            summary.unknown_component_keys += 1
            continue
        if current["authoritative_source"] is not None:
            summary.already_tagged += 1
            continue
        conn.execute(update_sql, update_args)
        summary.tagged += 1
    conn.commit()
    return summary
