"""M7.0.a disagreement report (Step 10).

After the full-corpus three-source cascade (Step 9) writes the per-
source verdicts, this script queries the DB and emits a markdown
report. Four sections:

1. **Summary stats** — total rows, flagged count, consensus-method
   histogram.
2. **Pair-disagreement matrix** — pairwise agree/disagree between
   LLM, vision PS, vision CS.
3. **Top N 3-way-disagreement rows** — full details (all three types
   + reasons + node name + screen name) for qualitative review.
4. **Pattern clusters** — group flags by the (llm, ps, cs) tuple so
   recurring disagreement patterns surface (e.g., "cross-screen
   says container; LLM + PS say X"). This is the input to rule-v2
   design (Step 12).

Usage (writes to stdout by default):

    .venv/bin/python3 -m scripts.m7_disagreement_report --db Dank-EXP-02.declarative.db > report.md

Or with an explicit output path:

    .venv/bin/python3 -m scripts.m7_disagreement_report --db ... --out render_batch/m7_disagreement_report.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from typing import Any


def count_by_consensus_method(conn: sqlite3.Connection) -> dict[str, int]:
    """Return a count per consensus_method value, NULLs included as
    'none'.
    """
    rows = conn.execute(
        "SELECT consensus_method, COUNT(*) "
        "FROM screen_component_instances "
        "GROUP BY consensus_method "
        "ORDER BY consensus_method"
    ).fetchall()
    return {
        (m if m is not None else "none"): c for m, c in rows
    }


def _null_coalesce(v: Any) -> str | None:
    return v if v is not None else None


def pair_disagreement_matrix(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], dict[str, int]]:
    """Pairwise agree/disagree counts for (LLM, PS, CS).

    A row contributes to a pair count only when BOTH sources in the
    pair produced a verdict — rows where a vision stage didn't run
    (NULL) are excluded from that pair's counts. Prevents "no vision
    data" from looking like "vision disagrees."
    """
    pairs = (
        ("llm_type", "vision_ps_type", "llm", "vision_ps"),
        ("llm_type", "vision_cs_type", "llm", "vision_cs"),
        ("vision_ps_type", "vision_cs_type", "vision_ps", "vision_cs"),
    )
    out: dict[tuple[str, str], dict[str, int]] = {}
    for col_a, col_b, label_a, label_b in pairs:
        row = conn.execute(
            f"""
            SELECT
              SUM(CASE WHEN {col_a} = {col_b} THEN 1 ELSE 0 END) AS agree,
              SUM(CASE WHEN {col_a} <> {col_b} THEN 1 ELSE 0 END) AS disagree
            FROM screen_component_instances
            WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL
            """
        ).fetchone()
        out[(label_a, label_b)] = {
            "agree": row[0] or 0,
            "disagree": row[1] or 0,
        }
    return out


def top_three_way_disagreements(
    conn: sqlite3.Connection, n: int = 50,
) -> list[dict[str, Any]]:
    """Return up to `n` 3-way-disagreement rows with all three types +
    reasons + node + screen metadata.
    """
    cursor = conn.execute(
        """
        SELECT
          sci.id AS sci_id,
          sci.screen_id,
          sci.node_id,
          sci.consensus_method,
          sci.llm_type, sci.llm_reason, sci.llm_confidence,
          sci.vision_ps_type, sci.vision_ps_reason, sci.vision_ps_confidence,
          sci.vision_cs_type, sci.vision_cs_reason, sci.vision_cs_confidence,
          n.figma_node_id, n.name AS node_name,
          s.name AS screen_name
        FROM screen_component_instances sci
        JOIN nodes n ON n.id = sci.node_id
        JOIN screens s ON s.id = sci.screen_id
        WHERE sci.consensus_method = 'three_way_disagreement'
        ORDER BY sci.screen_id, sci.id
        LIMIT ?
        """,
        (n,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def cluster_by_pattern(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    """Group flagged rows by their (llm, ps, cs) verdict tuple.

    Produces the top patterns of disagreement — the set that rule-v2
    will encode overrides against. Example: a popular pattern might
    be `llm=X / vision_ps=X / vision_cs=container` (cross-screen
    container drift).
    """
    rows = conn.execute(
        """
        SELECT llm_type, vision_ps_type, vision_cs_type
        FROM screen_component_instances
        WHERE flagged_for_review = 1
        """
    ).fetchall()
    counter: Counter[str] = Counter()
    for llm_type, ps_type, cs_type in rows:
        key = (
            f"llm={llm_type} / "
            f"vision_ps={ps_type} / "
            f"vision_cs={cs_type}"
        )
        counter[key] += 1
    return dict(counter.most_common())


def render_report(conn: sqlite3.Connection, *, top_n: int = 50) -> str:
    counts = count_by_consensus_method(conn)
    matrix = pair_disagreement_matrix(conn)
    top = top_three_way_disagreements(conn, n=top_n)
    clusters = cluster_by_pattern(conn)

    total = sum(counts.values())
    flagged_methods = {"any_unsure", "three_way_disagreement"}
    flagged = sum(c for m, c in counts.items() if m in flagged_methods)

    lines: list[str] = []
    lines.append("# M7.0.a disagreement report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total rows: {total}")
    lines.append(f"- Total flagged: {flagged}")
    lines.append("- Breakdown by `consensus_method`:")
    for method in sorted(counts.keys()):
        lines.append(f"  - `{method}`: {counts[method]}")
    lines.append("")

    lines.append("## Pair disagreement matrix")
    lines.append("")
    lines.append(
        "| pair | agree | disagree | disagree % |"
    )
    lines.append("|---|---:|---:|---:|")
    for (a, b), d in matrix.items():
        total_pair = d["agree"] + d["disagree"]
        pct = (
            f"{100.0 * d['disagree'] / total_pair:.1f}%"
            if total_pair else "n/a"
        )
        lines.append(
            f"| {a} × {b} | {d['agree']} | {d['disagree']} | {pct} |"
        )
    lines.append("")

    lines.append(f"## Top {top_n} three_way_disagreement rows")
    lines.append("")
    for r in top:
        lines.append(
            f"### sci_id={r['sci_id']} — screen {r['screen_id']} "
            f"({r['screen_name']!r}), node {r['figma_node_id']} "
            f"({r['node_name']!r})"
        )
        lines.append("")
        lines.append(
            f"- LLM ({r['llm_confidence'] or 0:.2f}): "
            f"`{r['llm_type']}` — {r['llm_reason'] or '(no reason)'}"
        )
        lines.append(
            f"- Vision PS ({r['vision_ps_confidence'] or 0:.2f}): "
            f"`{r['vision_ps_type']}` — "
            f"{r['vision_ps_reason'] or '(no reason)'}"
        )
        lines.append(
            f"- Vision CS ({r['vision_cs_confidence'] or 0:.2f}): "
            f"`{r['vision_cs_type']}` — "
            f"{r['vision_cs_reason'] or '(no reason)'}"
        )
        lines.append("")

    lines.append("## Pattern clusters (flagged rows only)")
    lines.append("")
    lines.append(
        "Grouped by the raw (LLM, PS, CS) triple. The top patterns "
        "are the candidates for rule-v2 bias overrides."
    )
    lines.append("")
    lines.append("| count | pattern |")
    lines.append("|---:|---|")
    for pattern, count in list(clusters.items())[:50]:
        lines.append(f"| {count} | {pattern} |")
    lines.append("")

    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", required=True, help="Path to the .declarative.db",
    )
    parser.add_argument(
        "--top-n", type=int, default=50,
        help="Top N three_way_disagreement rows to include (default 50)",
    )
    parser.add_argument(
        "--out", default=None,
        help=(
            "Output path. When omitted, prints to stdout."
        ),
    )
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    try:
        md = render_report(conn, top_n=args.top_n)
    finally:
        conn.close()

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote report: {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
