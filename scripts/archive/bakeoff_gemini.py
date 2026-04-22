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
    .venv/bin/python3 -m scripts.bakeoff_gemini \\
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
from typing import Optional

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
    """Reps are sci rows where the LLM actually ran. v2: JOIN with
    nodes for geometry + name/type, LEFT JOIN parent's sci row to
    populate ``parent_classified_as`` (matching Anthropic PS context).
    Also counts children for the ``total_children`` descriptor.
    """
    placeholders = ",".join("?" * len(screen_ids))
    rows = conn.execute(
        f"""
        SELECT sci.id, sci.screen_id, sci.node_id,
               n.name, n.node_type,
               n.x, n.y, n.width, n.height, n.text_content,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
               sci.canonical_type, sci.consensus_method,
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
        """,
        screen_ids,
    ).fetchall()
    cols = [
        "id", "screen_id", "node_id", "name", "node_type",
        "x", "y", "width", "height", "sample_text",
        "llm_type", "vision_ps_type", "vision_cs_type",
        "canonical_type", "consensus_method",
        "parent_classified_as", "total_children",
    ]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
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
    *,
    live_conn_for_few_shot: Optional[sqlite3.Connection] = None,
    use_schema: bool = True,
    batch_size: int = 8,
) -> dict[tuple[int, int], dict]:
    """Run Gemini over every rep. Returns dict[(sid, nid)] → verdict.

    When ``live_conn_for_few_shot`` is supplied, each batch gets a
    few-shot block derived from up to 6 reviewed examples (parity with
    Anthropic's PS/CS pass). Few-shot pool is drawn from the live DB's
    ``classification_reviews`` (the /tmp copy doesn't have the prior
    reviews because they're preserved separately).
    """
    from dd.classify_v2 import _build_crop
    from dd.classify_vision_gemini import classify_crops_gemini
    from dd.classify_few_shot import (
        format_few_shot_block, retrieve_few_shot,
    )

    # Pre-build crops on main thread (identical to Anthropic path).
    crops: dict[tuple[int, int], bytes] = {}
    for rep in reps:
        crop = _build_crop(conn, rep, screenshots)
        if crop is not None:
            crops[(rep["screen_id"], rep["node_id"])] = crop

    verdicts: dict[tuple[int, int], dict] = {}
    total_batches = (len(reps) + batch_size - 1) // batch_size
    for i in range(0, len(reps), batch_size):
        batch = reps[i:i + batch_size]
        few_shot_block = ""
        if live_conn_for_few_shot is not None:
            pooled: list[dict] = []
            seen_sci: set[int] = set()
            seen_parents: set[str] = set()
            for rep in batch:
                parent = rep.get("parent_classified_as") or ""
                if parent in seen_parents:
                    continue
                seen_parents.add(parent)
                for ex in retrieve_few_shot(
                    live_conn_for_few_shot, rep, k=2,
                ):
                    sid = ex.get("sci_id")
                    if sid in seen_sci:
                        continue
                    seen_sci.add(sid)
                    pooled.append(ex)
                if len(pooled) >= 6:
                    break
            few_shot_block = format_few_shot_block(pooled[:6])

        try:
            result = classify_crops_gemini(
                batch, crops, api_key=api_key, catalog=catalog,
                few_shot_block=few_shot_block,
                use_response_schema=use_schema,
            )
        except Exception as e:
            print(f"  Gemini batch {i}-{i+batch_size} failed: {e}",
                  file=sys.stderr, flush=True)
            continue
        for c in result:
            key = (c["screen_id"], c["node_id"])
            verdicts[key] = c
        print(
            f"  Gemini batch {i // batch_size + 1}/{total_batches}: "
            f"{len(result)} classifications "
            f"(few_shot={bool(few_shot_block)})",
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
    skeleton_skipped: int = 0,
) -> str:
    # Pair agreement: Gemini ↔ LLM and Gemini ↔ PS only.
    # CS dropped — Anthropic CS saw multi-crop context; Gemini only
    # sees the rep's crop, so comparing is unfair.
    pair_llm = []
    pair_ps = []
    for rep in reps:
        key = (rep["screen_id"], rep["node_id"])
        g = gemini.get(key)
        g_type = g.get("canonical_type") if g else None
        pair_llm.append((g_type, rep.get("llm_type")))
        pair_ps.append((g_type, rep.get("vision_ps_type")))

    a_llm, n_llm = _pair_agreement(pair_llm)
    a_ps, n_ps = _pair_agreement(pair_ps)

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

    # new_type proposals — the escape-hatch signal. Each unique label
    # with count tells us what the catalog is missing.
    new_types: dict[str, int] = {}
    new_type_nodes: list[tuple[str, str]] = []
    for key, v in gemini.items():
        if v.get("canonical_type") == "new_type":
            label = v.get("new_type_label") or "(no label)"
            new_types[label] = new_types.get(label, 0) + 1
            # Attach a node label for the detail table.
            rep = next(
                (r for r in reps
                 if r["screen_id"] == key[0]
                 and r["node_id"] == key[1]),
                None,
            )
            name = (rep.get("name") if rep else None) or "?"
            new_type_nodes.append(
                (f"{key[0]}:{key[1]}", f"{name} → {label}"),
            )

    # Pair-disagreement (Gemini vs Anthropic PS). Fairer than the v1
    # triple-disagreement because PS and Gemini both see a single crop.
    pair_disagree: list[tuple[str, str, str, str]] = []
    for rep in reps:
        key = (rep["screen_id"], rep["node_id"])
        g = gemini.get(key)
        g_type = g.get("canonical_type") if g else None
        ps = rep.get("vision_ps_type")
        if g_type and ps and g_type != ps:
            pair_disagree.append(
                (f"{rep['screen_id']}:{rep['node_id']}",
                 rep.get("name") or "?", g_type, ps)
            )

    lines = [
        "# Gemini 2.5 Flash vision bake-off report (v2)",
        "",
        f"- Screens: {screen_ids}",
        f"- Reps after skeleton-filter: {len(reps)} "
        f"(skipped {skeleton_skipped} skeleton reps)",
        f"- Gemini classifications returned: {len(gemini)}",
        f"- Anthropic wall time: {elapsed_anthropic:.1f}s",
        f"- Gemini wall time: {elapsed_gemini:.1f}s",
        "",
        "## Pair agreement (Gemini ↔ Anthropic, single-crop fair)",
        "",
        "| Pair | Agreement | Sample |",
        "|---|---:|---:|",
        f"| Gemini ↔ LLM (text) | {a_llm*100:.1f}% | {n_llm} |",
        f"| Gemini ↔ Vision PS | {a_ps*100:.1f}% | {n_ps} |",
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

    lines.append("## `new_type` proposals (catalog gap signal)")
    lines.append("")
    if new_types:
        lines.append("| Proposed label | Count |")
        lines.append("|---|---:|")
        for label, count in sorted(
            new_types.items(), key=lambda x: (-x[1], x[0]),
        ):
            lines.append(f"| `{label}` | {count} |")
        lines.append("")
        lines.append("### Example nodes")
        lines.append("")
        for nid, desc in new_type_nodes[:30]:
            lines.append(f"- `{nid}` — {desc}")
    else:
        lines.append("_(no `new_type` verdicts — catalog considered complete)_")
    lines.append("")

    lines.append("## Gemini ↔ Anthropic PS disagreements")
    lines.append("")
    lines.append(f"Count: {len(pair_disagree)} / {len(reps)} "
                 f"({len(pair_disagree) / len(reps) * 100:.1f}% of reps)")
    lines.append("")
    if pair_disagree:
        lines.append("| Node | Name | Gemini | Anthropic PS |")
        lines.append("|---|---|---|---|")
        for nid, name, gt, ps in pair_disagree[:40]:
            safe_name = name.replace("|", "\\|")[:40]
            lines.append(f"| {nid} | {safe_name} | {gt} | {ps} |")
        if len(pair_disagree) > 40:
            lines.append(
                f"| ... | ({len(pair_disagree) - 40} more) | | |"
            )
    lines.append("")

    lines.append("## Decision gate")
    lines.append("")
    lines.append(
        "Add Gemini as a 4th source if at least one holds:"
    )
    lines.append(
        "- Gemini ↔ user-review match rate ≥ Anthropic-PS match rate"
    )
    lines.append(
        "- Gemini ↔ PS disagreement stays ≥15% AND `new_type` "
        "proposals surface real catalog gaps"
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
    parser.add_argument(
        "--skip-anthropic", action="store_true",
        help=(
            "Reuse the existing Anthropic v2.1 results at --copy-path "
            "and run ONLY the Gemini pass. Saves ~$2 on bake-off iterations."
        ),
    )
    parser.add_argument(
        "--no-few-shot", action="store_true",
        help="Skip few-shot retrieval. Used to ablate whether review-"
        "based examples help or hurt Gemini's rep-level judgment.",
    )
    parser.add_argument(
        "--no-schema", action="store_true",
        help="Skip responseSchema enum constraint. Used to ablate "
        "whether Gemini's known-problematic large-enum handling "
        "(github googleapis/python-genai#950) is the regression "
        "driver.",
    )
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
    if not args.skip_anthropic:
        print(f"Copying {live_db} → {work_db}...", flush=True)
        _copy_db(live_db, work_db)
    else:
        print(f"Reusing existing {work_db} (--skip-anthropic).", flush=True)

    from dd.db import get_connection
    if not args.skip_anthropic:
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
    print(f"Loaded {len(reviews)} user reviews.", flush=True)

    # Run v2.1 (Anthropic LLM + PS + CS) unless we're reusing existing.
    from dd.catalog import get_catalog
    from dd.cli import make_figma_screenshot_fetcher

    fetch_screenshot = make_figma_screenshot_fetcher(scale=2)

    work_conn = get_connection(work_db)
    catalog = get_catalog(work_conn)
    print(f"Catalog size: {len(catalog)}", flush=True)

    if not args.skip_anthropic:
        import anthropic
        from dd.classify_v2 import run_classification_v2
        client = anthropic.Anthropic()
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
    else:
        elapsed_a = 0.0
        print("Skipped Anthropic re-run.", flush=True)

    all_reps = _fetch_anthropic_reps(work_conn, screen_ids)
    # Skeleton pre-filter: v2.1 already tagged skeleton placeholders
    # structurally. Asking Gemini to reclassify them is pure noise
    # (bake-off v1 saw multiple skeleton → dialog / drawer errors).
    reps = [r for r in all_reps if r.get("canonical_type") != "skeleton"]
    skeleton_skipped = len(all_reps) - len(reps)
    print(
        f"Found {len(all_reps)} reps; kept {len(reps)} "
        f"(filtered out {skeleton_skipped} skeletons).",
        flush=True,
    )

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

    variant = (
        f"few_shot={'off' if args.no_few_shot else 'on'}, "
        f"schema={'off' if args.no_schema else 'on'}"
    )
    print(
        f"Running Gemini 2.5 Flash on same reps ({variant})...",
        flush=True,
    )
    start_g = time.time()
    gemini_verdicts = _run_gemini_on_reps(
        work_conn, reps, screenshots, catalog, api_key,
        live_conn_for_few_shot=(
            None if args.no_few_shot else live_conn
        ),
        use_schema=not args.no_schema,
    )
    elapsed_g = time.time() - start_g
    print(f"Gemini complete in {elapsed_g:.1f}s.", flush=True)
    work_conn.close()
    live_conn.close()

    report = _render_report(
        screen_ids, reps, gemini_verdicts, reviews,
        elapsed_a, elapsed_g,
        skeleton_skipped=skeleton_skipped,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote report: {out_path}", flush=True)
    print("\n" + report, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
