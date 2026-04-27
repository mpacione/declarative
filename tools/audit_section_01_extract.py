"""Canonical Section 1 (extraction) for Phase B audit re-runs.

Encodes the workflow change from F4 (2026-04-25): Section 1 must use
``dd extract-plugin``, NOT ``dd extract-supplement``. The original
audit (audit/20260425-1042/sections/01-extract/) ran extract-supplement
and reported `vector-geometry: 0`, leaving the `assets` table empty.
That gap surfaced downstream in Section 7 (round-trip render) as 5
`missing_asset` errors and a parity ratio of 0.583 on a single-screen
verify.

`dd extract-plugin` is the unified Plugin-API extraction (perf pt 6
#3): supplement + properties + sizing + transforms + vector-geometry
in one walk. After the heavy slice writes `vector_paths` /
`fill_geometry` / `stroke_geometry` columns, the post-processing step
(``dd.extract_assets.process_vector_geometry``) materialises content-
addressed entries in ``assets`` and ``node_asset_refs`` — the very
tables the renderer reads from.

Verification (source-code, see dd/extract_plugin.py:525-528):

    from dd.extract_assets import process_vector_geometry
    asset_count = process_vector_geometry(conn)
    totals["vector_assets_built"] = asset_count

So a Phase B re-audit calling ``run_section_01_extract`` instead of
the old extract-supplement command will populate the asset store and
remove the vector-geometry blind spot.

Use:

    from tools.audit_section_01_extract import run_section_01_extract

    run_section_01_extract(
        file_key="PsYyNUTuIE1IPifyoDIesy",
        db_path="audit/2026MMDD-XXXX/audit-fresh.declarative.db",
        bridge_port="9225",  # whatever figma_get_status reports
    )

The function calls ``tools.audit_runner.run_step`` for each substep so
the Phase B harness records command + stdout + stderr + exit + DB
deltas exactly as the original audit did. Substeps: ``dd extract``
(REST → DB), ``dd extract-plugin`` (Plugin-API unified walk +
vector-asset post-processing), ``dd status`` (read-only sanity).

The script does NOT run ``dd extract-supplement`` — that is exactly
what F4 replaces.
"""

from __future__ import annotations

from pathlib import Path

from tools.audit_runner import run_step


def run_section_01_extract(
    *,
    file_key: str,
    db_path: str,
    bridge_port: str = "9225",
    python_bin: str = ".venv/bin/python",
    extract_timeout_s: int = 900,
    plugin_timeout_s: int = 1800,
    status_timeout_s: int = 60,
) -> dict[str, dict]:
    """Run the canonical Phase-B Section 1 extraction.

    Returns a dict mapping step name -> the run_step record. Caller
    is responsible for writing the verdict.md afterwards.

    The substeps:

    1. ``dd extract <file_key> --db <db>`` — REST file fetch into
       the SQLite schema (screens, nodes, raw bindings, components
       map, CKR seed).
    2. ``dd extract-plugin --db <db> --port <port>`` — Plugin-API
       unified walk (supplement + properties + sizing + transforms
       + vector-geometry) plus the post-collection vector-asset
       store materialisation. THIS IS THE F4 WORKFLOW CHANGE.
    3. ``dd status --db <db>`` — read-only sanity, exit 0 expected.
    """
    db = Path(db_path)
    watch = [str(db.parent)] if db.parent != Path(".") else None

    extract_record = run_step(
        section="01-extract",
        name="dd-extract",
        cmd=[python_bin, "-m", "dd", "extract", file_key, "--db", db_path],
        timeout_s=extract_timeout_s,
        post_state_db=db_path,
        watch_dirs=watch,
    )

    plugin_record = run_step(
        section="01-extract",
        name="dd-extract-plugin",
        cmd=[
            python_bin, "-m", "dd", "extract-plugin",
            "--db", db_path, "--port", bridge_port,
        ],
        timeout_s=plugin_timeout_s,
        pre_state_db=db_path,
        post_state_db=db_path,
        watch_dirs=watch,
    )

    status_record = run_step(
        section="01-extract",
        name="dd-status",
        cmd=[python_bin, "-m", "dd", "status", "--db", db_path],
        timeout_s=status_timeout_s,
    )

    return {
        "dd-extract": extract_record,
        "dd-extract-plugin": plugin_record,
        "dd-status": status_record,
    }


def assert_assets_populated(db_path: str) -> dict[str, int]:
    """Post-extract verification: confirm the assets table + node_asset_refs
    are non-empty. Raises AssertionError otherwise.

    Returns the counts so the caller can include them in the verdict.

    This is the assertion the original Section 1 verdict could NOT make
    because extract-supplement doesn't run process_vector_geometry. A
    fresh `audit-fresh.declarative.db` after run_section_01_extract
    should have:
      - assets: > 0  (content-addressed SVG paths)
      - node_asset_refs: > 0  (one row per node referencing an asset)
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        refs = conn.execute("SELECT COUNT(*) FROM node_asset_refs").fetchone()[0]
    finally:
        conn.close()

    counts = {"assets": assets, "node_asset_refs": refs}

    if assets == 0:
        raise AssertionError(
            f"assets table is empty after extract-plugin. Expected >0 vector "
            f"assets to be materialised by process_vector_geometry. Counts: "
            f"{counts}. This usually means the heavy slice failed silently — "
            f"check stderr from dd-extract-plugin."
        )
    if refs == 0:
        raise AssertionError(
            f"node_asset_refs is empty after extract-plugin. assets={assets} "
            f"but no node references them. Counts: {counts}. Probable cause: "
            f"a SQL change to the assets schema; see "
            f"dd/extract_assets.py:198-202."
        )

    return counts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-key", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", default="9225")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After extraction, assert assets + node_asset_refs are non-empty.",
    )
    args = parser.parse_args()

    records = run_section_01_extract(
        file_key=args.file_key,
        db_path=args.db,
        bridge_port=args.port,
    )
    for name, rec in records.items():
        print(f"{name}: exit={rec['exit_code']} elapsed_ms={rec['elapsed_ms']}")

    if args.verify:
        counts = assert_assets_populated(args.db)
        print(f"verify: assets={counts['assets']} node_asset_refs={counts['node_asset_refs']}")
