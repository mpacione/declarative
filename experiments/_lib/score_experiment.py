"""Score an experiment's output with dual fidelity + VLM metrics.

Reads artefacts under ``experiments/<name>/artefacts/NN-slug/`` and
produces a ``fidelity_report.json`` + console table. Reusable across
00g, 00h, and forward iterations.

Usage:
    python3 experiments/_lib/score_experiment.py experiments/00g-mode3-v4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dd.archetype_library import load_skeleton
from dd.diagnostics.fidelity import (
    prompt_fidelity,
    render_fidelity_from_script,
)


def score_experiment(root: Path) -> dict:
    artefacts = root / "artefacts"
    sanity_path = root / "sanity_report.json"
    sanity = {}
    if sanity_path.exists():
        sanity = json.loads(sanity_path.read_text())

    per_prompt: dict[str, dict] = {}
    for d in sorted(artefacts.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        entry: dict = {"slug": slug}

        # Prompt fidelity — load classifier + components
        arch_name = None
        arch_path = d / "classified_archetype.txt"
        if arch_path.exists():
            text = arch_path.read_text().strip()
            arch_name = text if text and text != "none" else None
        entry["archetype"] = arch_name or "none"

        components_path = d / "component_list.json"
        components: list = []
        if components_path.exists():
            try:
                raw = json.loads(components_path.read_text())
                components = raw if isinstance(raw, list) else []
            except Exception:  # noqa: BLE001
                components = []
        entry["component_count"] = len(components)

        skeleton = None
        if arch_name:
            try:
                skeleton = load_skeleton(arch_name)
            except Exception:  # noqa: BLE001
                skeleton = None
        entry["prompt_fidelity"] = round(
            prompt_fidelity(skeleton, components), 4
        )

        # Render fidelity — load ir + script
        ir_path = d / "ir.json"
        script_path = d / "script.js"
        if ir_path.exists() and script_path.exists():
            ir = json.loads(ir_path.read_text())
            script = script_path.read_text()
            render_score = render_fidelity_from_script(ir, script)
            entry["render_fidelity"] = round(render_score.overall, 4)
            entry["render_by_type"] = {
                t: round(v["coverage"], 4)
                for t, v in render_score.by_type.items()
            }
        else:
            entry["render_fidelity"] = None
            entry["render_by_type"] = {}

        # VLM verdict
        vlm = sanity.get("per_prompt", {}).get(slug, {}).get("vlm") or {}
        entry["vlm_verdict"] = vlm.get("verdict", "—")
        entry["vlm_score"] = vlm.get("score", 0)

        # Combined verdict
        combined = sanity.get("per_prompt", {}).get(slug, {}).get("verdict")
        entry["combined_verdict"] = combined or "—"

        per_prompt[slug] = entry

    # Aggregates
    render_vals = [e["render_fidelity"] for e in per_prompt.values() if e["render_fidelity"] is not None]
    prompt_vals = [e["prompt_fidelity"] for e in per_prompt.values()]
    vlm_ok = sum(1 for e in per_prompt.values() if e["vlm_verdict"] == "ok")
    vlm_partial = sum(1 for e in per_prompt.values() if e["vlm_verdict"] == "partial")
    vlm_broken = sum(1 for e in per_prompt.values() if e["vlm_verdict"] == "broken")

    report = {
        "experiment": root.name,
        "aggregate": {
            "mean_render_fidelity": round(sum(render_vals) / len(render_vals), 4) if render_vals else 0.0,
            "mean_prompt_fidelity": round(sum(prompt_vals) / len(prompt_vals), 4) if prompt_vals else 0.0,
            "vlm_ok": vlm_ok,
            "vlm_partial": vlm_partial,
            "vlm_broken": vlm_broken,
            "n_prompts": len(per_prompt),
        },
        "per_prompt": per_prompt,
    }
    return report


def render_table(report: dict) -> str:
    lines: list[str] = []
    agg = report["aggregate"]
    lines.append(f"# Fidelity report — {report['experiment']}")
    lines.append("")
    lines.append(
        f"**Overall**: mean render-fidelity {agg['mean_render_fidelity']:.3f} · "
        f"mean prompt-fidelity {agg['mean_prompt_fidelity']:.3f} · "
        f"VLM {agg['vlm_ok']} ok / {agg['vlm_partial']} partial / {agg['vlm_broken']} broken"
    )
    lines.append("")
    lines.append(
        "| slug | archetype | comps | prompt-fid | render-fid | VLM | combined |"
    )
    lines.append("|---|---|---:|---:|---:|---|---|")
    for slug, e in report["per_prompt"].items():
        rf = f"{e['render_fidelity']:.3f}" if e['render_fidelity'] is not None else "—"
        pf = f"{e['prompt_fidelity']:.3f}"
        vlm = f"{e['vlm_verdict']}({e['vlm_score']})"
        lines.append(
            f"| {slug} | {e['archetype']} | {e['component_count']} | "
            f"{pf} | {rf} | {vlm} | {e['combined_verdict']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: score_experiment.py <experiment_dir>", file=sys.stderr)
        sys.exit(2)
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"not a dir: {root}", file=sys.stderr)
        sys.exit(1)
    report = score_experiment(root)
    (root / "fidelity_report.json").write_text(json.dumps(report, indent=2))
    md = render_table(report)
    (root / "fidelity_report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
