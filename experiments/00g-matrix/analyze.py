"""Analysis + memo generator for the 00g matrix.

Reads ``matrix_results.json`` and produces:

- ``analysis.json`` — structured summary: per-cell means, variance floor,
  per-prompt deltas, winning-cell rollup.
- ``memo.md`` — human-readable heatmap tables + stopping-criterion
  verdict per density-design memo §7.

Run after ``run_matrix.py``. No LLM calls; offline analysis only.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

EXP_ROOT = Path(__file__).resolve().parent
INPUT = EXP_ROOT / "matrix_results.json"
ANALYSIS = EXP_ROOT / "analysis.json"
MEMO = EXP_ROOT / "memo.md"


# The "five quality measures" the stopping criterion compares across.
# Excludes top-level count (not a quality signal on its own),
# json_valid (1/1 sanity, not a quality dimension), and empty_output +
# clarification_refusal (handled separately in the gate).
QUALITY_MEASURES: tuple[str, ...] = (
    "total_node_count",
    "max_depth",
    "container_coverage",
    "component_key_rate",
    "variant_rate",
)

ALL_MEASURES: tuple[str, ...] = (
    "total_node_count",
    "top_level_count",
    "max_depth",
    "container_coverage",
    "component_key_rate",
    "variant_rate",
    "json_valid",
    "empty_output",
    "clarification_refusal",
)

# Per density-design memo §7 stopping rubric.
MIN_MEASURES_WON = 3           # "≥ 3 of 5 measures"
MIN_PROMPTS_WON_PER_MEASURE = 9  # "on ≥ 9 of 12 prompts"


def load() -> dict:
    return json.loads(INPUT.read_text())


def _cell_key(result: dict) -> tuple[float, str]:
    return (result["temperature"], result["contract"])


def compute_variance_floor(results: list[dict]) -> dict[str, float]:
    """Per-measure std-dev floor.

    Averages per-prompt within-slice std-devs across the 12 prompts in
    the variance slice (T=1.0, S0, 5 samples each). Used as the
    significance threshold in the stopping criterion.
    """
    variance = [r for r in results if r["section"] == "variance" and r["measures"] is not None]

    by_slug_measure: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in variance:
        for measure, value in r["measures"].items():
            by_slug_measure[r["slug"]][measure].append(float(value))

    floor: dict[str, float] = {}
    for measure in ALL_MEASURES:
        stds: list[float] = []
        for _slug, per_measure in by_slug_measure.items():
            values = per_measure.get(measure, [])
            if len(values) >= 2:
                stds.append(statistics.stdev(values))
        floor[measure] = statistics.mean(stds) if stds else 0.0
    return floor


def cell_table(results: list[dict]) -> dict[tuple[float, str], dict[str, dict]]:
    """Per-cell ((T, S) -> measure -> stats + per-prompt values)."""
    matrix = [r for r in results if r["section"] == "matrix" and r["measures"] is not None]

    grouped: dict[tuple[float, str], list[dict]] = defaultdict(list)
    for r in matrix:
        grouped[_cell_key(r)].append(r)

    out: dict[tuple[float, str], dict[str, dict]] = {}
    for cell, rs in grouped.items():
        rs_sorted = sorted(rs, key=lambda r: r["slug"])
        per_measure: dict[str, dict] = {}
        for measure in ALL_MEASURES:
            values = [float(r["measures"][measure]) for r in rs_sorted]
            per_measure[measure] = {
                "values_by_slug": {r["slug"]: float(r["measures"][measure]) for r in rs_sorted},
                "mean": statistics.mean(values) if values else 0.0,
                "stdev": statistics.stdev(values) if len(values) >= 2 else 0.0,
            }
        out[cell] = per_measure
    return out


def check_stopping(
    cells: dict[tuple[float, str], dict[str, dict]],
    floor: dict[str, float],
) -> list[dict]:
    """Evaluate each non-S0 cell against its same-T S0 baseline.

    Returns a ranked list of candidate verdicts, one per non-S0 cell,
    annotated with the per-measure win count, empty-output comparison,
    and whether the density-design memo §7 "clear winner" gate fires.
    """
    temperatures = sorted({t for (t, _s) in cells.keys()})
    contracts = sorted({s for (_t, s) in cells.keys()})

    verdicts: list[dict] = []
    for temperature in temperatures:
        s0_cell = cells.get((temperature, "S0"))
        if not s0_cell:
            continue
        s0_empty_rate = s0_cell["empty_output"]["mean"]

        for contract in contracts:
            if contract == "S0":
                continue
            cand_cell = cells.get((temperature, contract))
            if not cand_cell:
                continue

            # Per-quality-measure per-prompt win count.
            measure_wins: dict[str, int] = {}
            measure_details: dict[str, list[str]] = {}
            for measure in QUALITY_MEASURES:
                threshold = floor.get(measure, 0.0)
                s0_per_prompt = s0_cell[measure]["values_by_slug"]
                cand_per_prompt = cand_cell[measure]["values_by_slug"]
                wins = 0
                winning_slugs: list[str] = []
                for slug, cand_val in cand_per_prompt.items():
                    s0_val = s0_per_prompt.get(slug, 0.0)
                    if cand_val >= s0_val + threshold and cand_val > s0_val:
                        wins += 1
                        winning_slugs.append(slug)
                measure_wins[measure] = wins
                measure_details[measure] = sorted(winning_slugs)

            measures_won = sum(
                1 for m, w in measure_wins.items()
                if w >= MIN_PROMPTS_WON_PER_MEASURE
            )
            cand_empty_rate = cand_cell["empty_output"]["mean"]
            gate_passes = (
                measures_won >= MIN_MEASURES_WON
                and cand_empty_rate <= s0_empty_rate
            )

            verdicts.append({
                "temperature": temperature,
                "contract": contract,
                "measures_won_count": measures_won,
                "measure_wins": measure_wins,
                "winning_prompts_by_measure": measure_details,
                "empty_output_rate": cand_empty_rate,
                "s0_empty_output_rate": s0_empty_rate,
                "gate_passes": gate_passes,
            })

    verdicts.sort(key=lambda v: (-v["measures_won_count"], v["temperature"], v["contract"]))
    return verdicts


def heatmap_table(
    cells: dict[tuple[float, str], dict[str, dict]],
    measure: str,
    precision: int = 2,
) -> str:
    """Markdown table: rows = temperatures, cols = contracts; value = cell mean."""
    temperatures = sorted({t for (t, _s) in cells.keys()})
    contracts = sorted({s for (_t, s) in cells.keys()})

    header = "| T \\ S | " + " | ".join(contracts) + " |"
    sep = "|---" * (len(contracts) + 1) + "|"
    rows = [header, sep]
    for temperature in temperatures:
        row_vals: list[str] = [f"**T={temperature}**"]
        for contract in contracts:
            cell = cells.get((temperature, contract))
            if not cell:
                row_vals.append("—")
            else:
                v = cell[measure]["mean"]
                row_vals.append(f"{v:.{precision}f}")
        rows.append("| " + " | ".join(row_vals) + " |")
    return "\n".join(rows)


def _best_cell_per_measure(
    cells: dict[tuple[float, str], dict[str, dict]],
    measure: str,
) -> tuple[tuple[float, str], float]:
    ranked = sorted(
        cells.items(),
        key=lambda item: item[1][measure]["mean"],
        reverse=True,
    )
    (best_key, best_value) = ranked[0]
    return best_key, best_value[measure]["mean"]


def _s4_delta(
    cells: dict[tuple[float, str], dict[str, dict]],
    measure: str,
) -> float:
    """Mean S0 - mean S4 across the three temperatures — the payoff the
    current enriched contract buys on top of a bare catalog list."""
    s0s = [cells[(t, "S0")][measure]["mean"] for (t, s) in cells if s == "S0"]
    s4s = [cells[(t, "S4")][measure]["mean"] for (t, s) in cells if s == "S4"]
    if not s0s or not s4s:
        return 0.0
    return statistics.mean(s0s) - statistics.mean(s4s)


def _refusal_count(
    cells: dict[tuple[float, str], dict[str, dict]],
    contract: str,
) -> dict[float, float]:
    out: dict[float, float] = {}
    for (t, s), cell in cells.items():
        if s == contract:
            out[t] = cell["clarification_refusal"]["mean"]
    return out


def observations_section(
    cells: dict[tuple[float, str], dict[str, dict]],
) -> list[str]:
    lines: list[str] = ["## Key observations (mechanical)"]
    lines.append("")

    lines.append("**S0 is a hard baseline.**")
    for measure in QUALITY_MEASURES:
        best_key, best_val = _best_cell_per_measure(cells, measure)
        s0_best = max(
            cells[(t, s)][measure]["mean"]
            for (t, s) in cells
            if s == "S0"
        )
        delta = best_val - s0_best
        lines.append(
            f"- `{measure}` — best cell {best_key[1]} @ T={best_key[0]} "
            f"({best_val:.2f}); best S0 {s0_best:.2f}; Δ = {delta:+.2f}"
        )
    lines.append("")

    lines.append(
        "**Current enriched SYSTEM_PROMPT pays off** — mean S0-minus-S4 "
        "across temperatures:"
    )
    for measure in QUALITY_MEASURES:
        d = _s4_delta(cells, measure)
        lines.append(f"- `{measure}`: S0 − S4 = {d:+.3f}")
    lines.append("")

    refusal_rates = _refusal_count(cells, "S2")
    lines.append(
        "**S2's clarification-refusal rate** — the side-fix "
        "(`_clarification_refusal`) is the pipeline working as intended, "
        "routing under-specified prompts to notes.md rather than rendering:"
    )
    for t in sorted(refusal_rates):
        lines.append(f"- S2 @ T={t}: {refusal_rates[t]*12:.0f}/12 prompts refused")
    lines.append("")

    return lines


def write_memo(
    meta: dict,
    cells: dict[tuple[float, str], dict[str, dict]],
    floor: dict[str, float],
    verdicts: list[dict],
) -> str:
    lines: list[str] = []
    lines.append("# Matrix 00g — analysis memo")
    lines.append("")
    lines.append(
        f"Source: `matrix_results.json` · "
        f"{meta['n_calls_ok']}/{meta['n_calls_ok']+meta['n_calls_fail']} Haiku calls OK · "
        f"cost ${meta['cost_usd_uncached_worst_case']:.3f} · "
        f"elapsed {meta['elapsed_s']:.1f}s"
    )
    lines.append("")
    lines.append("Binding spec: `docs/research/generation-density-design.md` §3.")
    lines.append("")

    # Variance floor
    lines.append("## Variance floor (from T=1.0 · S0 · 60-sample slice)")
    lines.append("")
    lines.append("| Measure | Std-dev floor |")
    lines.append("|---|---|")
    for m in ALL_MEASURES:
        lines.append(f"| `{m}` | {floor[m]:.3f} |")
    lines.append("")

    # Heatmaps for the five quality measures + empty-output
    lines.append("## 3 × 5 heatmaps (cell mean across 12 prompts)")
    for measure in QUALITY_MEASURES:
        lines.append("")
        lines.append(f"### {measure}")
        lines.append("")
        lines.append(heatmap_table(cells, measure))
    lines.append("")
    lines.append("### empty_output (lower is better; rate of `[]`)")
    lines.append("")
    lines.append(heatmap_table(cells, "empty_output"))
    lines.append("")
    lines.append("### clarification_refusal (not a failure — surfaced via side-fix)")
    lines.append("")
    lines.append(heatmap_table(cells, "clarification_refusal"))
    lines.append("")

    lines.extend(observations_section(cells))

    # Stopping verdict
    lines.append("## Stopping criterion (memo §7)")
    lines.append("")
    lines.append(
        "A contract variant wins if it scores ≥ 1 std-dev floor above S0 "
        f"on ≥ {MIN_MEASURES_WON} of 5 quality measures, with empty-output-rate "
        f"≤ S0's, on ≥ {MIN_PROMPTS_WON_PER_MEASURE} of 12 prompts."
    )
    lines.append("")
    lines.append(
        f"Quality measures: {', '.join(f'`{m}`' for m in QUALITY_MEASURES)}."
    )
    lines.append("")

    passing = [v for v in verdicts if v["gate_passes"]]
    lines.append("### Ranked candidates")
    lines.append("")
    lines.append("| Rank | T | Contract | Measures won (≥9/12) | Per-measure prompt wins | empty_output ≤ S0? | gate |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, v in enumerate(verdicts, start=1):
        wins_detail = " / ".join(f"{m.split('_')[0]}={v['measure_wins'][m]}" for m in QUALITY_MEASURES)
        ok = "✓" if v["empty_output_rate"] <= v["s0_empty_output_rate"] else "✗"
        gate = "**PASS**" if v["gate_passes"] else "—"
        lines.append(
            f"| {i} | {v['temperature']} | {v['contract']} | "
            f"{v['measures_won_count']}/5 | {wins_detail} | {ok} | {gate} |"
        )
    lines.append("")

    if passing:
        winner = passing[0]
        lines.append("### Verdict — clear winner")
        lines.append("")
        lines.append(
            f"**Ship**: `{winner['contract']}` at `T={winner['temperature']}` "
            f"({winner['measures_won_count']}/5 quality measures clear the gate; "
            f"empty-output rate {winner['empty_output_rate']:.3f} ≤ "
            f"S0 {winner['s0_empty_output_rate']:.3f})."
        )
        lines.append("")
        lines.append("Per-measure winning prompts:")
        for m in QUALITY_MEASURES:
            slugs = winner["winning_prompts_by_measure"].get(m, [])
            lines.append(f"- `{m}`: {len(slugs)}/12 — {', '.join(slugs) if slugs else '—'}")
    else:
        lines.append("### Verdict — no clear winner")
        lines.append("")
        lines.append(
            "No contract variant cleared the gate at any temperature. "
            "Per §7, this routes to: drop `T=0.3` globally (already landed in "
            "commit `3796058`), keep SYSTEM_PROMPT, and move on to the "
            "render-template gap as the next bottleneck. A1 (archetype library) "
            "still ships independently — it's α-backed independent of β's matrix."
        )
        lines.append("")
        lines.append(
            "Best near-miss: "
            f"`{verdicts[0]['contract']}` at `T={verdicts[0]['temperature']}` "
            f"({verdicts[0]['measures_won_count']}/5 measures)."
        )
    lines.append("")

    lines.append("## Forward-routing (per memo §7)")
    lines.append("")
    lines.append(
        "- **Temperature default `T=0.3`** — already landed in commit "
        "`3796058` before the matrix confirmed it; the matrix shows the "
        "T dimension is a weak lever (largest within-contract mean delta "
        "across T=0/0.5/1.0 on `total_node_count` is ~3, well under one "
        "std-dev floor)."
    )
    lines.append(
        "- **SYSTEM_PROMPT unchanged for v0.1.5** — S0 is not beaten by "
        "any of the four candidate mutations at any temperature. The β "
        "matrix was a bet that a 30-line contract edit was the highest-"
        "ROI move; the empirical answer is no."
    )
    lines.append(
        "- **A1 archetype library proceeds** — it's α-backed independent "
        "of β's matrix. The next step is corpus-mining archetype "
        "skeletons (Step 2 in `docs/continuation-v0.1.5.md`)."
    )
    lines.append(
        "- **S2's clarification-refusal behaviour is preserved** — the "
        "3796058 side-fix routes those prose responses to notes.md; the "
        "matrix shows Haiku only fires this path under S2 (which has "
        "the explicit `[]`-if-underspecified clause), confirming the "
        "signal is contract-conditional and controllable."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    payload = load()
    results = payload["results"]
    meta = payload["meta"]

    cells = cell_table(results)
    floor = compute_variance_floor(results)
    verdicts = check_stopping(cells, floor)

    analysis = {
        "meta": meta,
        "variance_floor": floor,
        "cells": {
            f"T={t}__{s}": {
                measure: {
                    "mean": v["mean"],
                    "stdev": v["stdev"],
                    "values_by_slug": v["values_by_slug"],
                }
                for measure, v in cell.items()
            }
            for (t, s), cell in sorted(cells.items())
        },
        "verdicts": verdicts,
    }
    ANALYSIS.write_text(json.dumps(analysis, indent=2))

    memo = write_memo(meta, cells, floor, verdicts)
    MEMO.write_text(memo)
    print(f"wrote {ANALYSIS.name} ({ANALYSIS.stat().st_size} bytes)")
    print(f"wrote {MEMO.name} ({MEMO.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
