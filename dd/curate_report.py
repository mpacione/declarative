"""Generate a structured curation report identifying token issues for agent review."""

import re
import sqlite3

from dd.color import hex_to_oklch, oklch_delta_e

NUMERIC_SEGMENT = re.compile(r'\.\d+($|\.)')
LOW_USE_THRESHOLD = 5
DELTA_E_THRESHOLD = 3.0


def generate_curation_report(conn: sqlite3.Connection, file_id: int) -> dict:
    numeric_names = _find_numeric_names(conn, file_id)
    near_duplicates = _find_near_duplicate_colors(conn, file_id)
    low_use = _find_low_use_tokens(conn, file_id)
    semantic_layer = _check_semantic_layer(conn, file_id)
    fractional_sizes = _find_fractional_font_sizes(conn, file_id)

    total_actions = (
        len(numeric_names)
        + len(near_duplicates)
        + len(low_use)
        + len(fractional_sizes)
        + (0 if semantic_layer["has_semantic_layer"] else 1)
    )

    return {
        "numeric_names": numeric_names,
        "near_duplicates": near_duplicates,
        "low_use": low_use,
        "semantic_layer": semantic_layer,
        "fractional_sizes": fractional_sizes,
        "summary": {
            "total_actions": total_actions,
            "numeric_names": len(numeric_names),
            "near_duplicates": len(near_duplicates),
            "low_use": len(low_use),
            "fractional_sizes": len(fractional_sizes),
            "missing_semantic_layer": not semantic_layer["has_semantic_layer"],
        },
    }


def _find_numeric_names(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    tokens = conn.execute(
        """SELECT t.id, t.name, t.type
           FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           WHERE tc.file_id = ?
           ORDER BY t.name""",
        (file_id,),
    ).fetchall()

    return [
        {"id": r["id"], "name": r["name"], "type": r["type"]}
        for r in tokens
        if NUMERIC_SEGMENT.search(r["name"])
    ]


def _find_near_duplicate_colors(
    conn: sqlite3.Connection, file_id: int
) -> list[dict]:
    colors = conn.execute(
        """SELECT t.id, t.name, tv.resolved_value
           FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           JOIN token_values tv ON t.id = tv.token_id
           WHERE t.type = 'color' AND tv.resolved_value LIKE '#%'
             AND tc.file_id = ?""",
        (file_id,),
    ).fetchall()

    pairs = []
    for i, a in enumerate(colors):
        for b in colors[i + 1 :]:
            try:
                de = oklch_delta_e(
                    hex_to_oklch(a["resolved_value"]),
                    hex_to_oklch(b["resolved_value"]),
                )
                if de < DELTA_E_THRESHOLD:
                    pairs.append(
                        {
                            "token_a": a["name"],
                            "value_a": a["resolved_value"],
                            "token_b": b["name"],
                            "value_b": b["resolved_value"],
                            "delta_e": round(de, 1),
                        }
                    )
            except (ValueError, KeyError):
                pass

    return sorted(pairs, key=lambda p: p["delta_e"])


def _find_low_use_tokens(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.name, t.type, COUNT(ntb.id) as binding_count
           FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           LEFT JOIN node_token_bindings ntb
             ON ntb.token_id = t.id AND ntb.binding_status = 'bound'
           WHERE tc.file_id = ?
           GROUP BY t.id
           HAVING binding_count <= ?
           ORDER BY binding_count, t.name""",
        (file_id, LOW_USE_THRESHOLD),
    ).fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "binding_count": r["binding_count"],
        }
        for r in rows
    ]


def _check_semantic_layer(conn: sqlite3.Connection, file_id: int) -> dict:
    alias_count = conn.execute(
        """SELECT COUNT(*) FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           WHERE t.tier = 'aliased' AND tc.file_id = ?""",
        (file_id,),
    ).fetchone()[0]

    return {
        "alias_count": alias_count,
        "has_semantic_layer": alias_count > 0,
    }


def _find_fractional_font_sizes(
    conn: sqlite3.Connection, file_id: int
) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.name, tv.resolved_value
           FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           JOIN token_values tv ON t.id = tv.token_id
           WHERE t.name LIKE '%.fontSize' AND tc.file_id = ?""",
        (file_id,),
    ).fetchall()

    result = []
    for r in rows:
        try:
            v = float(r["resolved_value"])
            if v != round(v):
                result.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "value": v,
                        "suggested": round(v),
                    }
                )
        except (ValueError, TypeError):
            pass

    return result
