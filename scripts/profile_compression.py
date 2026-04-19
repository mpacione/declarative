"""Compression + efficiency analysis across the Dank corpus.

Measures byte sizes at each stage of the v0.3 compiler pipeline:

  DB rows  →  dict IR (spec)  →  L3 markup AST  →  Figma script

Plus:
  - element / node counts at each stage
  - Figma Plugin API ops per screen (proxy: createCall + appendChild
    + setProperty line counts)
  - compression ratios between stages
  - largest-screen ceilings vs Figma's known script size limits

Outputs an aggregate + per-screen CSV for inspection. Intended to
answer: where does the pipeline spend bytes, and where are the
cheapest optimisation wins before M5/M6?

Usage:
    python3 scripts/profile_compression.py            # full corpus
    python3 scripts/profile_compression.py --limit 30 # subset
    python3 scripts/profile_compression.py --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "Dank-EXP-02.declarative.db"
sys.path.insert(0, str(ROOT))


def screen_db_bytes(conn: sqlite3.Connection, sid: int) -> int:
    """Approximate raw DB footprint for a screen — sum of every row's
    serialized length across the primary tables. Rows joined to the
    screen by node_id when the table has no direct screen_id column
    (instance_overrides, node_token_bindings).

    Serialized via str(v) per field — a rough-but-deterministic proxy
    for "bytes this screen occupies" with minimal undercounting of
    NULLs and nested JSON blobs.
    """
    total = 0
    # Direct screen_id join
    for table in ("nodes", "screen_component_instances"):
        cols_check = conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
        if not cols_check:
            continue
        cursor = conn.execute(
            f"SELECT * FROM {table} WHERE screen_id = ?", (sid,),
        )
        for row in cursor.fetchall():
            total += sum(
                len(str(v)) if v is not None else 0 for v in row
            )
    # Via-node_id tables
    for table in ("instance_overrides", "node_token_bindings"):
        cols_check = conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
        if not cols_check:
            continue
        cursor = conn.execute(
            f"SELECT * FROM {table} "
            f"WHERE node_id IN (SELECT id FROM nodes WHERE screen_id = ?)",
            (sid,),
        )
        for row in cursor.fetchall():
            total += sum(
                len(str(v)) if v is not None else 0 for v in row
            )
    # Add screens row itself
    row = conn.execute(
        "SELECT * FROM screens WHERE id = ?", (sid,),
    ).fetchone()
    if row:
        total += sum(len(str(v)) if v is not None else 0 for v in row)
    return total


def count_figma_ops(script: str) -> dict[str, int]:
    """Count Plugin API operation categories in an emitted script.
    These cap the number of round-trips Figma's renderer must do;
    Figma has documented limits on the number of operations per
    script execution.
    """
    return {
        "createFrame": len(re.findall(r"figma\.createFrame\(", script)),
        "createRectangle": len(
            re.findall(r"figma\.createRectangle\(", script),
        ),
        "createText": len(re.findall(r"figma\.createText\(", script)),
        "createVector": len(re.findall(r"figma\.createVector\(", script)),
        "createEllipse": len(
            re.findall(r"figma\.createEllipse\(", script),
        ),
        "createLine": len(re.findall(r"figma\.createLine\(", script)),
        "createBooleanOperation": len(
            re.findall(r"figma\.createBooleanOperation\(", script),
        ),
        "createInstance": script.count(".createInstance()"),
        "appendChild": len(re.findall(r"\.appendChild\(", script)),
        "getNodeByIdAsync": script.count("getNodeByIdAsync"),
        "setPluginData": script.count(".setPluginData"),
        "loadFontAsync": script.count("loadFontAsync"),
    }


def profile_screen(
    conn: sqlite3.Connection, sid: int,
) -> dict:
    """Measure byte sizes + counts at each pipeline stage."""
    from dd.compress_l3 import compress_to_l3_with_maps
    from dd.ir import generate_ir, query_screen_visuals
    from dd.markup_l3 import emit_l3
    from dd.renderers.figma import collect_fonts, generate_figma_script
    from dd.render_figma_ast import render_figma

    ir = generate_ir(conn, sid, semantic=True, filter_chrome=False)
    visuals = query_screen_visuals(conn, sid)
    spec = ir["spec"]
    spec_json = json.dumps(spec, separators=(",", ":"))

    doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
        compress_to_l3_with_maps(
            spec, conn, screen_id=sid, collapse_wrapper=False,
        )
    )
    markup = emit_l3(doc)

    fonts = collect_fonts(spec, db_visuals=visuals)
    script_a, _ = generate_figma_script(
        spec, db_visuals=visuals, ckr_built=True,
    )
    script_b, _ = render_figma(
        doc, conn, nid_map,
        fonts=fonts,
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=visuals, ckr_built=True,
        _spec_elements=spec["elements"],
        _spec_tokens=spec.get("tokens", {}),
    )

    db_b = screen_db_bytes(conn, sid)
    spec_b = len(spec_json)
    markup_b = len(markup)
    script_a_b = len(script_a)
    script_b_b = len(script_b)

    ir_elem_count = len(spec.get("elements", {}))
    ast_eid_count = _walk_eid_count(doc)
    ops_a = count_figma_ops(script_a)
    ops_b = count_figma_ops(script_b)

    return {
        "sid": sid,
        "db_bytes": db_b,
        "spec_bytes": spec_b,
        "markup_bytes": markup_b,
        "script_a_bytes": script_a_b,
        "script_b_bytes": script_b_b,
        "ir_elements": ir_elem_count,
        "ast_eids": ast_eid_count,
        "ops_a_createCalls": sum(
            v for k, v in ops_a.items() if k.startswith("create")
        ),
        "ops_a_appendChild": ops_a["appendChild"],
        "ops_a_getNodeByIdAsync": ops_a["getNodeByIdAsync"],
        "ops_a_loadFontAsync": ops_a["loadFontAsync"],
        "ops_b_createCalls": sum(
            v for k, v in ops_b.items() if k.startswith("create")
        ),
        "ops_b_appendChild": ops_b["appendChild"],
        "ops_b_getNodeByIdAsync": ops_b["getNodeByIdAsync"],
        # compression ratios
        "spec_over_db": (
            round(spec_b / db_b, 3) if db_b else 0.0
        ),
        "markup_over_spec": (
            round(markup_b / spec_b, 3) if spec_b else 0.0
        ),
        "script_over_markup": (
            round(script_a_b / markup_b, 3) if markup_b else 0.0
        ),
        "script_over_spec": (
            round(script_a_b / spec_b, 3) if spec_b else 0.0
        ),
        "ratio_b_a": (
            round(script_b_b / script_a_b, 3) if script_a_b else 0.0
        ),
    }


def _walk_eid_count(doc) -> int:
    out = 0
    queue = list(doc.top_level)
    while queue:
        n = queue.pop(0)
        out += 1
        if getattr(n, "block", None) is not None:
            for s in n.block.statements:
                if hasattr(s, "head"):
                    queue.append(s)
    return out


def print_aggregate(rows: list[dict]) -> None:
    def sums(key):
        return sum(r[key] for r in rows)

    def means(key):
        return statistics.mean(r[key] for r in rows)

    def medians(key):
        return statistics.median(r[key] for r in rows)

    n = len(rows)
    print(f"\n=== AGGREGATE ({n} screens) ===\n")
    print("Byte sizes:")
    for key, label in (
        ("db_bytes", "DB (raw row data)"),
        ("spec_bytes", "dict IR (spec JSON)"),
        ("markup_bytes", "L3 markup AST (emit_l3)"),
        ("script_a_bytes", "Figma script (baseline)"),
        ("script_b_bytes", "Figma script (Option B)"),
    ):
        tot = sums(key)
        avg = means(key)
        med = medians(key)
        mx = max(r[key] for r in rows)
        print(
            f"  {label:32s}  total={tot:>12,}  mean={avg:>10,.0f}  "
            f"median={med:>10,.0f}  max={mx:>10,}"
        )

    print("\nElement / op counts:")
    for key, label in (
        ("ir_elements", "dict IR elements"),
        ("ast_eids", "L3 AST emitted eids"),
        ("ops_a_createCalls", "baseline createNode calls"),
        ("ops_a_appendChild", "baseline appendChild calls"),
        ("ops_a_loadFontAsync", "baseline loadFontAsync calls"),
        ("ops_b_createCalls", "Option B createNode calls"),
    ):
        avg = means(key)
        med = medians(key)
        mx = max(r[key] for r in rows)
        print(
            f"  {label:32s}  mean={avg:>8,.1f}  median={med:>8,.1f}  "
            f"max={mx:>6,}"
        )

    print("\nCompression ratios (output / input by stage):")
    for key, label in (
        ("spec_over_db", "spec / db_bytes"),
        ("markup_over_spec", "markup / spec (L3 vs dict IR)"),
        ("script_over_markup", "baseline-script / markup"),
        ("script_over_spec", "baseline-script / spec"),
        ("ratio_b_a", "option_b / baseline script"),
    ):
        avg = means(key)
        med = medians(key)
        mn = min(r[key] for r in rows)
        mx = max(r[key] for r in rows)
        print(
            f"  {label:32s}  mean={avg:>6.3f}  median={med:>6.3f}  "
            f"min={mn:>6.3f}  max={mx:>6.3f}"
        )

    # Ceilings
    max_script = max(r["script_a_bytes"] for r in rows)
    max_ops = max(r["ops_a_createCalls"] for r in rows)
    print(
        f"\nLargest-screen ceilings:\n"
        f"  max script size:   {max_script:>10,} bytes "
        f"(~{max_script/1024:.1f} KB)\n"
        f"  max create calls:  {max_ops:>10,}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="Profile only the first N screens")
    ap.add_argument("--csv", default=None,
                    help="Write per-screen CSV to this path")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    screens = [
        r[0] for r in conn.execute(
            "SELECT id FROM screens WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    if args.limit:
        screens = screens[: args.limit]

    rows = []
    for i, sid in enumerate(screens, 1):
        try:
            row = profile_screen(conn, sid)
            rows.append(row)
            if i % 20 == 0 or i == len(screens):
                print(f"  [{i}/{len(screens)}] sid={sid}", flush=True)
        except Exception as e:
            print(
                f"  [{i}/{len(screens)}] sid={sid} FAIL: "
                f"{type(e).__name__}: {e}",
                flush=True, file=sys.stderr,
            )

    if not rows:
        print("No rows profiled.", file=sys.stderr)
        return 1

    print_aggregate(rows)

    if args.csv:
        p = Path(args.csv)
        with p.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"\nCSV written to {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
