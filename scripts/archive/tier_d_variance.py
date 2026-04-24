"""Tier D re-gate variance measurement (D5 per
docs/research/scorer-calibration-and-som-fidelity.md).

Runs the re-gate N times over the same 3 prompts and compares the
per-metric variance of:

- structural score (0-10)
- SoM precision (0-1)
- SoM recall (0-1)
- Gemini 1-10 rating (discretised to 0-10)

The purpose is to quantify whether SoM-coverage is less noisy than
the 1-10 VLM, given the research finding that 0-10 scales show the
worst human-LLM agreement (arXiv:2601.03444).

Writes per-run artefacts under ``tmp/tier_d_variance/runN/`` and a
summary report to ``tmp/tier_d_variance/variance_report.md``.

Usage::

    .venv/bin/python3 -m scripts.tier_d_variance \\
        --runs 3 --ws-port 9223
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)


def _run_regate(run_dir: Path, ws_port: int) -> list[dict[str, Any]]:
    """Invoke m7_tier_d_regate in a subprocess; return parsed report."""
    cmd = [
        sys.executable, "-m", "scripts.tier_d_regate",
        "--ws-port", str(ws_port),
        "--out-dir", str(run_dir),
    ]
    result = subprocess.run(
        cmd, cwd=str(Path(__file__).parent.parent),
        capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        print(f"[run] rc={result.returncode}")
        print(f"stderr: {result.stderr[-500:]}")
        return []
    report_path = run_dir / "report.json"
    if not report_path.exists():
        print(f"[run] missing report: {report_path}")
        return []
    return json.loads(report_path.read_text())


def _summarise(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Per prompt × per metric: mean, stdev, min, max across runs."""
    # Flatten: {scope: [run_result, ...]}
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        for r in run:
            by_scope.setdefault(r["scope"], []).append(r)

    out: dict[str, Any] = {"prompts": {}}
    metrics = [
        ("struct_score", "struct"),
        ("som_precision", "SoM-P"),
        ("som_recall", "SoM-R"),
        ("vlm_score", "VLM"),
    ]
    for scope, results in by_scope.items():
        metric_summary: dict[str, dict[str, float]] = {}
        for field, label in metrics:
            values = [r.get(field, 0) or 0 for r in results]
            if not values:
                continue
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0.0
            metric_summary[label] = {
                "mean": round(mean, 3),
                "stdev": round(stdev, 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "values": [round(v, 3) for v in values],
            }
        out["prompts"][scope] = metric_summary
    return out


def _write_report(summary: dict[str, Any], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Tier D re-gate variance (D5 measurement)\n")
    lines.append(f"_Generated: {time.strftime('%Y-%m-%d %H:%M')}_\n")
    lines.append(
        "Measures per-metric variance across identical runs. "
        "Lower stdev = more reliable signal. Research baseline: "
        "arXiv:2601.03444 shows 0-10 scales have worst human-LLM "
        "agreement; expect Gemini 1-10 to show the most noise.\n"
    )

    for scope, metrics in summary["prompts"].items():
        lines.append(f"\n## {scope}\n")
        lines.append("| metric | mean | stdev | min | max | per-run |")
        lines.append("|---|---|---|---|---|---|")
        for label, stats in metrics.items():
            lines.append(
                f"| {label} | {stats['mean']:.2f} | **{stats['stdev']:.2f}** "
                f"| {stats['min']:.2f} | {stats['max']:.2f} | "
                f"{stats['values']} |"
            )

    # Comparative summary across metrics
    lines.append("\n## Cross-metric comparison\n")
    lines.append("stdev is the key column — lower = more reliable.\n")
    lines.append("| prompt | struct stdev | SoM-P stdev | SoM-R stdev | VLM stdev |")
    lines.append("|---|---|---|---|---|")
    for scope, metrics in summary["prompts"].items():
        s = metrics.get("struct", {}).get("stdev", 0)
        p = metrics.get("SoM-P", {}).get("stdev", 0)
        r = metrics.get("SoM-R", {}).get("stdev", 0)
        v = metrics.get("VLM", {}).get("stdev", 0)
        lines.append(
            f"| {scope} | {s:.2f} | {p:.2f} | {r:.2f} | {v:.2f} |"
        )

    lines.append(
        "\n## Interpretation\n"
        "- If VLM stdev > SoM stdev on most prompts, the lit review's "
        "finding holds for us and SoM should replace the 1-10 rating.\n"
        "- If SoM stdev is similar to VLM, the gain is structural "
        "(enum-constrained, per-component attribution) not variance. "
        "Still keep SoM because of diagnostic value.\n"
    )
    out_path.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--ws-port", type=int, default=9223)
    parser.add_argument(
        "--out-dir", default="tmp/tier_d_variance",
    )
    args = parser.parse_args(argv)

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    all_runs: list[list[dict[str, Any]]] = []
    for i in range(1, args.runs + 1):
        run_dir = out_root / f"run{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{'='*60}\nRUN {i}/{args.runs} → {run_dir}\n{'='*60}")
        t0 = time.monotonic()
        report = _run_regate(run_dir, args.ws_port)
        elapsed = time.monotonic() - t0
        print(f"  run {i} finished in {elapsed:.1f}s; "
              f"prompts={len(report)}")
        all_runs.append(report)

    summary = _summarise(all_runs)
    # Write summary JSON
    (out_root / "variance.json").write_text(
        json.dumps(summary, indent=2),
    )
    # Write markdown report
    report_path = out_root / "variance_report.md"
    _write_report(summary, report_path)
    print(f"\nReport: {report_path}")
    print(f"JSON:   {out_root / 'variance.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
