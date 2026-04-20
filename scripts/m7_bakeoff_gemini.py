"""Gemini 2.5 Flash vision bake-off vs Anthropic PS/CS.

Runs v2.1 (full LLM + vision PS + vision CS via Anthropic) on a COPY
of the live DB, then runs Gemini 2.5 Flash over the SAME dedup-group
representatives using the SAME crops. Compares:

- Gemini ↔ Anthropic LLM pair agreement
- Gemini ↔ Anthropic PS pair agreement
- Gemini ↔ Anthropic CS pair agreement
- Gemini ↔ user `accept_source` reviews (direct ground truth)
- Per-type divergences (where do the two providers disagree most?)

No main-pipeline changes. Gemini is a pure side-channel; its verdicts
are never written to sci rows. If results are strong, a follow-up can
add vision_gemini_* columns and extend the consensus rule.

Usage:

    export GOOGLE_API_KEY=...   # already in .env
    .venv/bin/python3 -m scripts.m7_bakeoff_gemini \\
        --db Dank-EXP-02.declarative.db \\
        [--out render_batch/m7_bakeoff_gemini_report.md]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_SCREEN_IDS = list(range(150, 160))


def _copy_db(src: str, dest: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        src_path = Path(src + suffix)
        dest_path = Path(dest + suffix)
        if src_path.exists():
            shutil.copy2(src_path, dest_path)
        elif dest_path.exists():
            dest_path.unlink()


def _truncate_sci_and_skeletons(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM screen_component_instances")
    conn.execute("DELETE FROM screen_skeletons")
    conn.commit()


def _fetch_anthropic_reps(
    conn: sqlite3.Connection, screen_ids: list[int],
) -> list[dict]:
    """Reps are sci rows where the LLM actually ran. Their llm_type /
    vision_ps_type / vision_cs_type columns hold the Anthropic
    verdicts we'll compare Gemini against.
    """
    placeholders = ",".join("?" * len(screen_ids))
    rows = conn.execute(
        f"""
        SELECT sci.id, sci.screen_id, sci.node_id,
               sci.name, sci.node_type,
               sci.x, sci.y, sci.width, sci.height,
               sci.sample_text, sci.parent_classified_as,
               sci.total_children, sci.child_type_dist,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
               sci.canonical_type, sci.consensus_method
        FROM screen_component_instances sci
        WHERE sci.screen_id IN ({placeholders})
          AND sci.classification_source = 'llm'
        """,
        screen_ids,
    ).fetchall()
    cols = [
        "id", "screen_id", "node_id", "name", "node_type",
        "x", "y", "width", "height", "sample_text",
        "parent_classified_as", "total_children", "child_type_dist",
        "llm_type", "vision_ps_type", "vision_cs_type",
        "canonical_type", "consensus_method",
    ]
    import json as _json
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        ctd = d.get("child_type_dist")
        if isinstance(ctd, str) and ctd:
            try:
                d["child_type_dist"] = _json.loads(ctd)
            except Exception:
                d["child_type_dist"] = {}
        elif ctd is None:
            d["child_type_dist"] = {}
        out.append(d)
    return out


def _fetch_user_reviews(
    live_conn: sqlite3.Connection, screen_ids: list[int],
) -> dict[tuple[int, int], dict]:
    placeholders = ",".join("?" * len(screen_ids))
    rows = live_conn.execute(
        f"""
        SELECT sci.screen_id, sci.node_id,
               r.decision_type, r.source_accepted,
               r.decision_canonical_type
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        WHERE sci.screen_id IN ({placeholders})
        """,
        screen_ids,
    ).fetchall()
    return {
        (r[0], r[1]): {
            "decision_type": r[2],
            "source_accepted": r[3],
            "decision_canonical_type": r[4],
        }
        for r in rows
    }


def _pair_agreement(pairs: list[tuple[str | None, str | None]]) -> tuple[float, int]:
    valid = [(a, b) for a, b in pairs if a and b]
    if not valid:
        return (0.0, 0)
    matches = sum(1 for a, b in valid if a == b)
    return (matches / len(valid), len(valid))


def _match_user_reviews(
    reps: list[dict],
    gemini: dict[tuple[int, int], dict],
    reviews: dict[tuple[int, int], dict],
) -> tuple[int, int]:
    """For each rep with a user `accept_source` review on its screen,
    check whether Gemini's canonical_type matches the source the user
    picked. Returns (match_count, total).
    """
    matches = 0
    total = 0
    for row in reps:
        key = (row["screen_id"], row["node_id"])
        review = reviews.get(key)
        if not review or review["decision_type"] != "accept_source":
            continue
        g = gemini.get(key)
        if not g:
            continue
        total += 1
        src = review["source_accepted"]
        picked_type = {
            "llm": row.get("llm_type"),
            "vision_ps": row.get("vision_ps_type"),
            "vision_cs": row.get("vision_cs_type"),
        }.get(src)
        if g.get("canonical_type") == picked_type:
            matches += 1
    return matches, total


def _run_gemini_on_reps(
    conn: sqlite3.Connection,
    reps: list[dict],
    screenshots: dict[str, bytes],
    catalog: list[dict],
    api_key: str,
    batch_size: int = 8,
) -> dict[tuple[int, int], dict]:
    """Run Gemini over every rep. Returns dict[(sid, nid)] → verdict."""
    from dd.classify_v2 import _build_crop
    from dd.classify_vision_gemini import classify_crops_gemini

    # Pre-build crops on main thread (identical to Anthropic path).
    crops: dict[tuple[int, int], bytes] = {}
    for rep in reps:
        crop = _build_crop(conn, rep, screenshots)
        if crop is not None:
            crops[(rep["screen_id"], rep["node_id"])] = crop

    verdicts: dict[tuple[int, int], dict] = {}
    for i in range(0, len(reps), batch_size):
        batch = reps[i:i + batch_size]
        try:
            result = classify_crops_gemini(
                batch, crops, api_key=api_key, catalog=catalog,
            )
        except Exception as e:
            print(f"  Gemini batch {i}-{i+batch_size} failed: {e}",
                  file=sys.stderr, flush=True)
            continue
        for c in result:
            key = (c["screen_id"], c["node_id"])
            verdicts[key] = c
        print(
            f"  Gemini batch {i // batch_size + 1}/"
            f"{(len(reps) + batch_size - 1) // batch_size}: "
            f"{len(result)} classifications",
            flush=True,
        )
    return verdicts


def _render_report(
    screen_ids: list[int],
    reps: list[dict],
    gemini: dict[tuple[int, int], dict],
    reviews: dict[tuple[int, int], dict],
    elapsed_anthropic: float,
    elapsed_gemini: float,
) -> str:
    # Pair agreement: Gemini ↔ each Anthropic source.
    pair_llm = []
    pair_ps = []
    pair_cs = []
    for rep in reps:
        key = (rep["screen_id"], rep["node_id"])
        g = gemini.get(key)
        g_type = g.get("canonical_type") if g else None
        pair_llm.append((g_type, rep.get("llm_type")))
        pair_ps.append((g_type, rep.get("vision_ps_type")))
        pair_cs.append((g_type, rep.get("vision_cs_type")))

    a_llm, n_llm = _pair_agreement(pair_llm)
    a_ps, n_ps = _pair_agreement(pair_ps)
    a_cs, n_cs = _pair_agreement(pair_cs)

    matches, total = _match_user_reviews(reps, gemini, reviews)
    match_pct = (matches / total * 100.0) if total else 0.0

    # Gemini's own confidence distribution.
    conf_hist = {"0.95+": 0, "0.85-0.94": 0, "0.75-0.84": 0, "<0.75": 0}
    for _, v in gemini.items():
        c = v.get("confidence", 0.0)
        if c >= 0.95:
            conf_hist["0.95+"] += 1
        elif c >= 0.85:
            conf_hist["0.85-0.94"] += 1
        elif c >= 0.75:
            conf_hist["0.75-0.84"] += 1
        else:
            conf_hist["<0.75"] += 1

    # Three-way divergences (Gemini disagrees with BOTH Anthropic vision passes).
    triple_disagree: list[tuple[str, str, str, str]] = []
    for rep in reps:
        key = (rep["screen_id"], rep["node_id"])
        g = gemini.get(key)
        g_type = g.get("canonical_type") if g else None
        ps = rep.get("vision_ps_type")
        cs = rep.get("vision_cs_type")
        if g_type and ps and cs and g_type != ps and g_type != cs:
            triple_disagree.append(
                (f"{rep['screen_id']}:{rep['node_id']}",
                 rep.get("name") or "?", g_type, f"PS={ps}, CS={cs}")
            )

    lines = [
        "# Gemini 2.5 Flash vision bake-off report",
        "",
        f"- Screens: {screen_ids}",
        f"- Reps (dedup groups w/ crops): {len(reps)}",
        f"- Gemini classifications returned: {len(gemini)}",
        f"- Anthropic wall time: {elapsed_anthropic:.1f}s",
        f"- Gemini wall time: {elapsed_gemini:.1f}s",
        "",
        "## Pair agreement (Gemini ↔ Anthropic)",
        "",
        "| Pair | Agreement | Sample |",
        "|---|---:|---:|",
        f"| Gemini ↔ LLM | {a_llm*100:.1f}% | {n_llm} |",
        f"| Gemini ↔ Vision PS | {a_ps*100:.1f}% | {n_ps} |",
        f"| Gemini ↔ Vision CS | {a_cs*100:.1f}% | {n_cs} |",
        "",
        "## Ground-truth match against user reviews",
        "",
    ]
    if total:
        lines.append(
            f"- User `accept_source` decisions on these screens: {total}"
        )
        lines.append(
            f"- Gemini canonical_type matched user's picked source: "
            f"{matches} ({match_pct:.1f}%)"
        )
    else:
        lines.append(
            "- No user `accept_source` decisions with Gemini coverage. "
            "No ground-truth validation possible."
        )
    lines.append("")

    lines.append("## Gemini confidence distribution")
    lines.append("")
    for band, count in conf_hist.items():
        lines.append(f"- {band}: {count}")
    lines.append("")

    lines.append("## Gemini disagrees with BOTH Anthropic vision passes")
    lines.append("")
    if triple_disagree:
        lines.append("| Node | Name | Gemini | Anthropic |")
        lines.append("|---|---|---|---|")
        for nid, name, gt, atyp in triple_disagree[:40]:
            safe_name = name.replace("|", "\\|")[:40]
            lines.append(f"| {nid} | {safe_name} | {gt} | {atyp} |")
        if len(triple_disagree) > 40:
            lines.append(f"| ... | ({len(triple_disagree) - 40} more) | | |")
    else:
        lines.append("_(none — Gemini always agrees with PS or CS)_")
    lines.append("")

    lines.append("## Decision gate")
    lines.append("")
    lines.append(
        "Add Gemini as a 4th source if at least one holds:"
    )
    lines.append(
        "- Gemini ↔ user-review match ≥ Anthropic-PS or -CS match"
    )
    lines.append(
        "- Gemini disagrees with Anthropic vision on ≥15% of reps "
        "(de-correlated failure modes)"
    )
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--out", default="render_batch/m7_bakeoff_gemini_report.md",
    )
    parser.add_argument("--screens", type=str, default=None)
    parser.add_argument(
        "--copy-path", default="/tmp/dank_gemini_bakeoff.db",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY not set (check .env).", file=sys.stderr)
        return 1

    screen_ids = (
        [int(s) for s in args.screens.split(",")]
        if args.screens else DEFAULT_SCREEN_IDS
    )

    live_db = args.db
    work_db = args.copy_path
    print(f"Copying {live_db} → {work_db}...", flush=True)
    _copy_db(live_db, work_db)

    from dd.db import get_connection
    work_conn = get_connection(work_db)
    _truncate_sci_and_skeletons(work_conn)
    work_conn.close()

    live_conn = get_connection(live_db)
    file_row = live_conn.execute(
        "SELECT id, file_key FROM files LIMIT 1"
    ).fetchone()
    if file_row is None:
        print("No file in live DB.", file=sys.stderr)
        return 1
    file_id, file_key = file_row[0], file_row[1]
    reviews = _fetch_user_reviews(live_conn, screen_ids)
    live_conn.close()
    print(f"Loaded {len(reviews)} user reviews.", flush=True)

    # Run v2.1 (Anthropic LLM + PS + CS).
    import anthropic
    from dd.catalog import get_catalog
    from dd.cli import make_figma_screenshot_fetcher
    from dd.classify_v2 import run_classification_v2

    client = anthropic.Anthropic()
    fetch_screenshot = make_figma_screenshot_fetcher(scale=2)

    work_conn = get_connection(work_db)
    catalog = get_catalog(work_conn)
    print(f"Catalog size: {len(catalog)}", flush=True)

    print("Running Anthropic v2.1 (LLM + PS + CS)...", flush=True)
    start_a = time.time()
    run_classification_v2(
        work_conn, file_id, client, file_key, fetch_screenshot,
        since_screen_id=min(screen_ids),
        limit=len(screen_ids),
        workers=args.workers,
    )
    elapsed_a = time.time() - start_a
    print(f"Anthropic complete in {elapsed_a:.1f}s.", flush=True)

    reps = _fetch_anthropic_reps(work_conn, screen_ids)
    print(f"Found {len(reps)} Anthropic reps.", flush=True)

    # Refetch screenshots for Gemini crop building (main-thread safe).
    screenshots: dict[str, bytes] = {}
    screen_rows = work_conn.execute(
        f"""
        SELECT figma_node_id FROM screens
        WHERE id IN ({','.join('?' * len(screen_ids))})
        """,
        screen_ids,
    ).fetchall()
    for (fig_id,) in screen_rows:
        if fig_id:
            screenshots[fig_id] = fetch_screenshot(file_key, fig_id)

    print("Running Gemini 2.5 Flash on same reps...", flush=True)
    start_g = time.time()
    gemini_verdicts = _run_gemini_on_reps(
        work_conn, reps, screenshots, catalog, api_key,
    )
    elapsed_g = time.time() - start_g
    print(f"Gemini complete in {elapsed_g:.1f}s.", flush=True)
    work_conn.close()

    report = _render_report(
        screen_ids, reps, gemini_verdicts, reviews,
        elapsed_a, elapsed_g,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote report: {out_path}", flush=True)
    print("\n" + report, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
