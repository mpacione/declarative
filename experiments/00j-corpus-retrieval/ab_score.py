"""A/B compare render fidelity: hand-authored catalog vs corpus retrieval.

Reuses the cached LLM outputs from ``experiments/00g-mode3-v4/`` —
component_list.json is deterministic given the same prompt + T=0.3, so
we don't need to re-spend Haiku calls. For each prompt:

  A: run compose + generate_figma_script with DD_ENABLE_CORPUS_RETRIEVAL unset
     → baseline (v0.1.5 hand-authored path)
  B: same inputs with DD_ENABLE_CORPUS_RETRIEVAL=1
     → corpus retrieval path

Scores both via ``dd.diagnostics.fidelity.render_fidelity_from_script``
and emits a delta table.

Usage:
    PYTHONPATH=$(pwd) python3 experiments/00j-corpus-retrieval/ab_score.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dd.compose import generate_from_prompt
from dd.db import get_connection
from dd.diagnostics.fidelity import render_fidelity_from_script


REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"
# Allow override: `python3 ab_score.py <experiment_dir>`
# Defaults to 00g (canonical 12). 00i is the 20-prompt breadth test.
import sys as _sys
if len(_sys.argv) > 1:
    SOURCE_EXP = Path(_sys.argv[1]).resolve()
else:
    SOURCE_EXP = REPO_ROOT / "experiments" / "00g-mode3-v4"


def load_components(slug_dir: Path) -> list[dict] | None:
    cp = slug_dir / "component_list.json"
    if not cp.exists():
        return None
    try:
        raw = json.loads(cp.read_text())
    except Exception:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    return raw


def compose_and_score(conn, components: list[dict], flag_on: bool) -> dict:
    if flag_on:
        os.environ["DD_ENABLE_CORPUS_RETRIEVAL"] = "1"
    else:
        os.environ.pop("DD_ENABLE_CORPUS_RETRIEVAL", None)

    result = generate_from_prompt(conn, components)
    spec = result["spec"]
    script = result["structure_script"]
    score = render_fidelity_from_script(spec, script)

    spliced = sum(
        1 for e in spec["elements"].values()
        if isinstance(e, dict) and "_corpus_source_node_id" in e
    )

    return {
        "elements_total": len(spec["elements"]),
        "elements_spliced": spliced,
        "render_fidelity": round(score.overall, 4),
        "script_chars": len(script),
        "script_lines": script.count("\n"),
    }


def main() -> None:
    conn = get_connection(str(DB_PATH))

    slugs = sorted(
        d.name for d in (SOURCE_EXP / "artefacts").iterdir() if d.is_dir()
    )

    rows: list[dict] = []
    for slug in slugs:
        slug_dir = SOURCE_EXP / "artefacts" / slug
        components = load_components(slug_dir)
        if components is None:
            rows.append({"slug": slug, "error": "no component_list"})
            continue

        try:
            a = compose_and_score(conn, components, flag_on=False)
            b = compose_and_score(conn, components, flag_on=True)
            rows.append({
                "slug": slug,
                "comps": len(components),
                "A_fid": a["render_fidelity"],
                "B_fid": b["render_fidelity"],
                "delta": round(b["render_fidelity"] - a["render_fidelity"], 4),
                "A_elements": a["elements_total"],
                "B_elements": b["elements_total"],
                "B_spliced": b["elements_spliced"],
                "A_script_lines": a["script_lines"],
                "B_script_lines": b["script_lines"],
            })
        except Exception as exc:
            rows.append({"slug": slug, "error": str(exc)[:200]})

    conn.close()

    # Print table
    print(f"{'slug':<25} {'comps':>5} {'A_fid':>7} {'B_fid':>7} {'Δfid':>7} {'A_el':>5} {'B_el':>5} {'splice':>6}")
    print("-" * 90)
    valid_rows = [r for r in rows if "error" not in r]
    for r in rows:
        if "error" in r:
            print(f"{r['slug']:<25} ERROR: {r['error'][:60]}")
            continue
        d = r["delta"]
        arrow = "↑" if d > 0.02 else ("↓" if d < -0.02 else "·")
        print(
            f"{r['slug']:<25} {r['comps']:>5} {r['A_fid']:>7.3f} "
            f"{r['B_fid']:>7.3f} {d:>+7.3f} {arrow}  "
            f"{r['A_elements']:>5} {r['B_elements']:>5} {r['B_spliced']:>6}"
        )

    if valid_rows:
        mean_a = sum(r["A_fid"] for r in valid_rows) / len(valid_rows)
        mean_b = sum(r["B_fid"] for r in valid_rows) / len(valid_rows)
        print("-" * 90)
        print(
            f"{'MEAN':<25} {'':>5} {mean_a:>7.3f} {mean_b:>7.3f} "
            f"{mean_b - mean_a:>+7.3f}"
        )

    # Write JSON
    out = Path(__file__).parent / "ab_report.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote: {out}")


if __name__ == "__main__":
    main()
