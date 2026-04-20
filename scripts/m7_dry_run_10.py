"""M7.0.a 10-screen dry-run driver.

Picks 10 screens spread across the Dank corpus, runs the LLM
classifier on each, then:

1. Emits a markdown report listing every LLM classification per
   screen with its reason + confidence (so the user can spot-check
   the vocabulary + calibration).
2. Renders the same 10 screens on a dedicated page in the Dank
   Experimental Figma file via ``render_batch/grid_render.py``.
   The page lets the user visually cross-reference classifications
   against the rendered output.

Usage:

    .venv/bin/python3 scripts/m7_dry_run_10.py [--port 9228] [--skip-render]

Requires:
- ``ANTHROPIC_API_KEY`` in ``.env`` (auto-loaded).
- Figma Desktop Bridge running on the specified port for the
  render step (skip with ``--skip-render`` to do classification
  only).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "Dank-EXP-02.declarative.db"
ENV_PATH = ROOT / ".env"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"


# Spread across the corpus: iPhones, iPad 11", iPad Pro 12.9",
# roughly every ~22nd screen. Picked manually for variety.
DEFAULT_SCREEN_IDS = [118, 139, 169, 191, 213, 235, 257, 281, 303, 326]


def _load_env() -> None:
    if not ENV_PATH.exists():
        print(f"warning: {ENV_PATH} not found; ANTHROPIC_API_KEY must be set in environment", file=sys.stderr)
        return
    with ENV_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                # Use direct assignment rather than setdefault so a
                # pre-existing empty value in the shell gets overridden.
                os.environ[k.strip()] = v.strip()


def _classify_screen(screen_id: int) -> None:
    """Run `dd classify --llm --since <id> --limit 1` via the venv
    python. Inherits env (incl. ANTHROPIC_API_KEY) from the
    parent process.
    """
    subprocess.run(
        [str(VENV_PYTHON), "-m", "dd", "classify", "--llm",
         "--since", str(screen_id), "--limit", "1"],
        check=True,
        cwd=str(ROOT),
    )


def _render_screens(screen_ids: list[int], port: str) -> None:
    """Render the 10 screens onto the Option-B-Grid page in Dank."""
    subprocess.run(
        [str(VENV_PYTHON), "render_batch/grid_render.py",
         "--screen-ids", ",".join(str(s) for s in screen_ids),
         "--cols", "5",
         "--port", port],
        check=True,
        cwd=str(ROOT),
    )


def _emit_report(screen_ids: list[int], out_path: Path) -> None:
    """Write a per-screen markdown report listing every LLM
    classification produced in this run (or any prior run).
    """
    conn = sqlite3.connect(str(DB_PATH))
    lines: list[str] = [
        "# M7.0.a 10-Screen Dry-Run Report",
        "",
        f"Screens: {screen_ids}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for sid in screen_ids:
        screen = conn.execute(
            "SELECT name, width, height FROM screens WHERE id = ?",
            (sid,),
        ).fetchone()
        if not screen:
            lines.append(f"## Screen {sid} — NOT FOUND")
            continue
        name, width, height = screen
        lines.append(f"## Screen {sid} — {name} ({int(width)}×{int(height)})")
        lines.append("")
        rows = conn.execute(
            """
            SELECT n.name, sci.canonical_type, sci.confidence,
                   sci.classification_reason
            FROM screen_component_instances sci
            JOIN nodes n ON sci.node_id = n.id
            WHERE sci.screen_id = ?
              AND sci.classification_source = 'llm'
            ORDER BY sci.confidence DESC, n.name
            """,
            (sid,),
        ).fetchall()
        if not rows:
            lines.append("_(no LLM classifications — all nodes hit formal/heuristic or no unclassified candidates)_")
            lines.append("")
            continue
        lines.append("| Node | → | Type | Conf | Reason |")
        lines.append("|---|---|---|---|---|")
        for nname, ctype, conf, reason in rows:
            reason_str = (reason or "")[:120]
            lines.append(
                f"| `{nname}` | → | `{ctype}` | {conf:.2f} | {reason_str} |"
            )
        lines.append("")
    conn.close()
    out_path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="9228",
                    help="Figma Desktop Bridge port (default 9228)")
    ap.add_argument("--skip-classify", action="store_true",
                    help="Skip the LLM classification step "
                         "(useful when re-running the report or render)")
    ap.add_argument("--skip-render", action="store_true",
                    help="Skip the Figma render step (classification + report only)")
    ap.add_argument("--out", type=str,
                    default="render_batch/m7_dry_run_report.md",
                    help="Report output path")
    args = ap.parse_args()

    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env or export it.", file=sys.stderr)
        return 1

    screen_ids = DEFAULT_SCREEN_IDS

    if not args.skip_classify:
        print(f"=== Classifying {len(screen_ids)} screens via LLM ===")
        t0 = time.time()
        for sid in screen_ids:
            print(f"\n--- screen {sid} ---", flush=True)
            _classify_screen(sid)
        elapsed = time.time() - t0
        print(f"\n=== Classification done in {elapsed:.1f}s ===")

    print(f"\n=== Emitting report to {args.out} ===")
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _emit_report(screen_ids, out_path)
    print(f"Report: {out_path}")

    if not args.skip_render:
        print(f"\n=== Rendering {len(screen_ids)} screens on Option-B-Grid page (port {args.port}) ===")
        _render_screens(screen_ids, args.port)

    print("\n=== Dry-run complete ===")
    print(f"Report: {out_path}")
    print("Figma page: 'Option-B-Grid' in the Dank Experimental file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
