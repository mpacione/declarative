"""Set-of-Marks bake-off vs Anthropic per-crop vision (PS).

Runs SoM (one call per screen, all nodes in one shot) alongside the
existing PS path (one crop per rep) on screens 150-159. Reports:

- Pair agreement: SoM ↔ PS, SoM ↔ LLM
- Confidence distribution
- Per-type divergence table
- Optional: match rate vs user reviews (when present)

SoM runs on a DB copy so it doesn't mutate the live classifications.
The PS / LLM / CS verdicts already in the DB from v2.5 are read as-is
— we don't re-classify those.

Usage::

    .venv/bin/python3 -m scripts.m7_bakeoff_som \\
        --db Dank-EXP-02.declarative.db \\
        [--out render_batch/m7_bakeoff_som_report.md] \\
        [--screens 150,151,152] [--workers 4]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_SCREEN_IDS = list(range(150, 160))


def _copy_db(src: str, dest: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        src_p = Path(src + suffix)
        dest_p = Path(dest + suffix)
        if src_p.exists():
            shutil.copy2(src_p, dest_p)
        elif dest_p.exists():
            dest_p.unlink()


def _fetch_reps(
    conn: sqlite3.Connection, screen_ids: list[int],
) -> list[dict]:
    """LLM-classified reps (those with per-source verdicts) on the
    target screens. We compare SoM's output against these reps'
    existing PS / LLM / CS verdicts.
    """
    placeholders = ",".join("?" * len(screen_ids))
    rows = conn.execute(
        f"""
        SELECT sci.id, sci.screen_id, sci.node_id,
               n.name, n.node_type, n.x, n.y, n.width, n.height,
               n.rotation, n.text_content,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
               sci.canonical_type,
               parent_sci.canonical_type AS parent_classified_as,
               (SELECT COUNT(*) FROM nodes c WHERE c.parent_id = n.id)
                 AS total_children
        FROM screen_component_instances sci
        JOIN nodes n ON n.id = sci.node_id
        LEFT JOIN nodes parent_n ON parent_n.id = n.parent_id
        LEFT JOIN screen_component_instances parent_sci
          ON parent_sci.node_id = parent_n.id
          AND parent_sci.screen_id = n.screen_id
        WHERE sci.screen_id IN ({placeholders})
          AND sci.classification_source = 'llm'
        ORDER BY sci.screen_id, n.sort_order
        """,
        screen_ids,
    ).fetchall()
    cols = [
        "sci_id", "screen_id", "node_id", "name", "node_type",
        "x", "y", "width", "height", "rotation", "sample_text",
        "llm_type", "vision_ps_type", "vision_cs_type",
        "canonical_type", "parent_classified_as", "total_children",
    ]
    return [dict(zip(cols, r)) for r in rows]


def _build_screen_annotations(
    reps_on_screen: list[dict], root_x: float, root_y: float,
) -> list[dict]:
    """Convert rep rows → SoM annotation dicts (one per mark).
    Uses (1..N) ids scoped per screen so the model's mark labels stay
    short.
    """
    annotations = []
    for i, r in enumerate(reps_on_screen, 1):
        annotations.append({
            "id": i,
            "sci_id": r["sci_id"],
            "node_id": r["node_id"],
            "x": float(r["x"] or 0) - root_x,
            "y": float(r["y"] or 0) - root_y,
            "w": float(r["width"] or 0),
            "h": float(r["height"] or 0),
            "rotation": float(r["rotation"] or 0),
            "name": r["name"],
            "node_type": r["node_type"],
            "sample_text": r["sample_text"],
            "parent_classified_as": r["parent_classified_as"],
            "total_children": r["total_children"],
        })
    return annotations


def _run_som_prepared(
    *,
    screen_id: int,
    annotations: list[dict],
    screen_png: bytes,
    screen_width: float,
    screen_height: float,
    client,
    catalog: list[dict],
) -> dict[int, dict]:
    """Pure-function SoM worker. All DB / screenshot fetching is done
    BEFORE this is called (main thread). Safe to dispatch via
    ThreadPoolExecutor.
    """
    from dd.classify_vision_som import classify_screen_som

    if not annotations or not screen_png:
        return {}

    try:
        som_out = classify_screen_som(
            screen_png=screen_png,
            annotations=annotations,
            client=client,
            catalog=catalog,
            screen_width=screen_width, screen_height=screen_height,
        )
    except Exception as e:
        print(f"  screen {screen_id}: SoM call failed: {e}",
              file=sys.stderr, flush=True)
        return {}

    by_mark = {a["id"]: a for a in annotations}
    out: dict[int, dict] = {}
    for c in som_out:
        ann = by_mark.get(c["mark_id"])
        if ann is None:
            continue
        out[ann["sci_id"]] = {
            "canonical_type": c["canonical_type"],
            "confidence": c["confidence"],
            "reason": c["reason"],
        }
    return out


def _prepare_screen_bundle(
    conn: sqlite3.Connection,
    screen_id: int,
    reps_on_screen: list[dict],
    file_key: str,
    fetch_screenshot,
) -> dict | None:
    """Pre-fetch everything the SoM worker needs. Called on the main
    thread before dispatch. Returns None if the screen is unusable.
    """
    row = conn.execute(
        "SELECT figma_node_id, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    if row is None:
        return None
    fig_id, sw, sh = row[0], float(row[1] or 0), float(row[2] or 0)

    root = conn.execute(
        "SELECT x, y FROM nodes WHERE screen_id = ? AND parent_id IS NULL",
        (screen_id,),
    ).fetchone()
    rx = float(root[0] or 0) if root else 0.0
    ry = float(root[1] or 0) if root else 0.0

    annotations = _build_screen_annotations(reps_on_screen, rx, ry)
    try:
        screen_png = fetch_screenshot(file_key, fig_id)
    except Exception as e:
        print(f"  screen {screen_id}: screenshot fetch failed: {e}",
              file=sys.stderr, flush=True)
        return None
    if not screen_png:
        return None

    return {
        "screen_id": screen_id,
        "annotations": annotations,
        "screen_png": screen_png,
        "screen_width": sw,
        "screen_height": sh,
    }


def _render_report(
    reps: list[dict],
    som_by_sci: dict[int, dict],
    screen_ids: list[int],
    elapsed_s: float,
) -> str:
    # Pair-agreement helpers.
    def agree(pairs):
        valid = [(a, b) for a, b in pairs if a and b]
        if not valid:
            return (0.0, 0)
        matches = sum(1 for a, b in valid if a == b)
        return (matches / len(valid), len(valid))

    pair_llm = [
        (som_by_sci.get(r["sci_id"], {}).get("canonical_type"),
         r.get("llm_type"))
        for r in reps
    ]
    pair_ps = [
        (som_by_sci.get(r["sci_id"], {}).get("canonical_type"),
         r.get("vision_ps_type"))
        for r in reps
    ]
    pair_cs = [
        (som_by_sci.get(r["sci_id"], {}).get("canonical_type"),
         r.get("vision_cs_type"))
        for r in reps
    ]

    a_llm, n_llm = agree(pair_llm)
    a_ps, n_ps = agree(pair_ps)
    a_cs, n_cs = agree(pair_cs)

    # Confidence distribution.
    conf_bins = {"0.95+": 0, "0.85-0.94": 0, "0.75-0.84": 0, "<0.75": 0}
    for v in som_by_sci.values():
        c = v.get("confidence", 0.0)
        if c >= 0.95:
            conf_bins["0.95+"] += 1
        elif c >= 0.85:
            conf_bins["0.85-0.94"] += 1
        elif c >= 0.75:
            conf_bins["0.75-0.84"] += 1
        else:
            conf_bins["<0.75"] += 1

    # Cases where SoM disagrees with ANTHROPIC PS (most direct
    # replacement target).
    disagree: list[tuple[str, str, str, str]] = []
    for r in reps:
        som_t = som_by_sci.get(r["sci_id"], {}).get("canonical_type")
        ps = r.get("vision_ps_type")
        if som_t and ps and som_t != ps:
            disagree.append((
                f"{r['screen_id']}:{r['node_id']}",
                (r.get("name") or "?")[:40],
                som_t, ps,
            ))

    lines = [
        "# Set-of-Marks bake-off report",
        "",
        f"- Screens: {screen_ids}",
        f"- Reps (LLM-classified): {len(reps)}",
        f"- SoM classifications returned: {len(som_by_sci)}",
        f"  - Coverage: {len(som_by_sci) / max(len(reps), 1) * 100:.1f}%",
        f"- Wall time: {elapsed_s:.1f}s",
        "",
        "## Pair agreement",
        "",
        "| Pair | Agreement | Sample |",
        "|---|---:|---:|",
        f"| SoM ↔ LLM | {a_llm*100:.1f}% | {n_llm} |",
        f"| SoM ↔ Vision PS | {a_ps*100:.1f}% | {n_ps} |",
        f"| SoM ↔ Vision CS | {a_cs*100:.1f}% | {n_cs} |",
        "",
        "## SoM confidence distribution",
        "",
    ]
    for band, count in conf_bins.items():
        lines.append(f"- {band}: {count}")
    lines.append("")

    lines.append("## SoM ↔ Vision PS disagreements")
    lines.append("")
    lines.append(
        f"Count: {len(disagree)} / {len(reps)} "
        f"({len(disagree) / max(len(reps), 1) * 100:.1f}% of reps)"
    )
    lines.append("")
    if disagree:
        lines.append("| Node | Name | SoM | PS |")
        lines.append("|---|---|---|---|")
        for nid, name, som, ps in disagree[:50]:
            safe = name.replace("|", "\\|")
            lines.append(f"| {nid} | {safe} | {som} | {ps} |")
        if len(disagree) > 50:
            lines.append(f"| ... | ({len(disagree) - 50} more) | | |")
    lines.append("")

    lines.append("## Takeaway")
    lines.append("")
    lines.append(
        "SoM strengths are cross-screen vision with shared context; "
        "a high SoM↔PS agreement (≥85%) means SoM is ready to replace "
        "PS; a moderate agreement (60-85%) plus a confidence lift "
        "means SoM is additive as a new source; low agreement (<60%) "
        "plus low confidence means the overlay isn't working yet."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--out", default="render_batch/m7_bakeoff_som_report.md",
    )
    parser.add_argument(
        "--screens", type=str, default=None,
        help="Comma-separated screen IDs. Default: 150-159.",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--copy-path", default="/tmp/dank_som_bakeoff.db",
    )
    args = parser.parse_args(argv)

    screen_ids = (
        [int(s) for s in args.screens.split(",")]
        if args.screens else DEFAULT_SCREEN_IDS
    )

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set (check .env).", file=sys.stderr)
        return 1

    # Copy DB (so we don't mutate live).
    print(f"Copying {args.db} → {args.copy_path}...", flush=True)
    _copy_db(args.db, args.copy_path)

    from dd.db import get_connection
    from dd.catalog import get_catalog
    from dd.cli import make_figma_screenshot_fetcher

    live_conn = get_connection(args.db)
    file_row = live_conn.execute(
        "SELECT file_key FROM files LIMIT 1"
    ).fetchone()
    file_key = file_row[0] if file_row else ""
    live_conn.close()

    work_conn = get_connection(args.copy_path)
    catalog = get_catalog(work_conn)
    reps = _fetch_reps(work_conn, screen_ids)
    print(f"Loaded {len(reps)} reps across {len(screen_ids)} screens.",
          flush=True)

    # Group reps by screen.
    reps_by_screen: dict[int, list[dict]] = {}
    for r in reps:
        reps_by_screen.setdefault(r["screen_id"], []).append(r)

    import anthropic
    client = anthropic.Anthropic()
    fetch_screenshot = make_figma_screenshot_fetcher(scale=2)

    # Pre-fetch all per-screen data (DB reads + Figma screenshots) on
    # the MAIN thread. Worker threads only get the bundle + client.
    print(
        f"Pre-fetching screenshots for {len(reps_by_screen)} screens...",
        flush=True,
    )
    bundles: list[dict] = []
    for sid, ra in reps_by_screen.items():
        bundle = _prepare_screen_bundle(
            work_conn, sid, ra, file_key, fetch_screenshot,
        )
        if bundle is not None:
            bundles.append(bundle)
    print(f"Prepared {len(bundles)} bundles.", flush=True)

    print(f"Running SoM on {len(bundles)} screens "
          f"(workers={args.workers})...", flush=True)
    start = time.time()
    som_by_sci: dict[int, dict] = {}

    if args.workers > 1 and len(bundles) > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    _run_som_prepared,
                    screen_id=b["screen_id"],
                    annotations=b["annotations"],
                    screen_png=b["screen_png"],
                    screen_width=b["screen_width"],
                    screen_height=b["screen_height"],
                    client=client,
                    catalog=catalog,
                ): b["screen_id"]
                for b in bundles
            }
            done = 0
            for fut in as_completed(futures):
                sid = futures[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    print(f"  screen {sid} failed: {e}",
                          file=sys.stderr, flush=True)
                    result = {}
                som_by_sci.update(result)
                done += 1
                print(f"  screen {sid}: {len(result)} marks "
                      f"({done}/{len(bundles)})", flush=True)
    else:
        for b in bundles:
            result = _run_som_prepared(
                screen_id=b["screen_id"],
                annotations=b["annotations"],
                screen_png=b["screen_png"],
                screen_width=b["screen_width"],
                screen_height=b["screen_height"],
                client=client,
                catalog=catalog,
            )
            som_by_sci.update(result)
            print(f"  screen {b['screen_id']}: {len(result)} marks",
                  flush=True)

    elapsed = time.time() - start
    print(f"\nSoM complete in {elapsed:.1f}s. Got {len(som_by_sci)} "
          f"classifications.", flush=True)

    report = _render_report(reps, som_by_sci, screen_ids, elapsed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote report: {out_path}", flush=True)
    print("\n" + report, flush=True)

    work_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
