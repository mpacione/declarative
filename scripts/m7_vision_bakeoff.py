"""M7.0.a vision stage bake-off — per-screen (N=1) vs cross-screen
(N=5, grouped by skeleton_type + device_class).

Runs the batched vision classifier twice on the same 10 dry-run
screens (the same set that ``scripts/m7_dry_run_10.py`` used):

1. **Per-screen mode (N=1):** one call per screen, no cross-screen
   signal. Reference baseline.
2. **Cross-screen mode (N=5, auto-grouped):** batches grouped by
   (device_class, skeleton_type). Cross-screen reasoning enabled
   in the prompt.

For every node that both modes classified, compares the
canonical_type + confidence. Emits a markdown report with:

- Overall agreement rate
- Per-canonical-type agreement + disagreement breakdown
- Side-by-side rows for divergences (with both reasons visible)
- Confidence deltas (does cross-screen confidence track per-screen?)

Does NOT write to ``screen_component_instances``. In-memory
comparison only. The winner (N=1 or N=5) gets wired into the
orchestrator in a follow-up commit.

Usage:

    .venv/bin/python3 scripts/m7_vision_bakeoff.py [--port 9228]

Requires ``ANTHROPIC_API_KEY`` + ``FIGMA_ACCESS_TOKEN`` in .env.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dd.classify_vision_batched import (  # noqa: E402
    classify_batch,
    group_screens_by_skeleton_and_device,
)


DB_PATH = ROOT / "Dank-EXP-02.declarative.db"
ENV_PATH = ROOT / ".env"


# 10 iPad Pro 11"/standard screens — fresh (not already LLM-
# classified). Same (device_class, skeleton_type) group so the
# cross-screen mode builds two batches of 5 with consistent
# design-system context.
DEFAULT_SCREEN_IDS = [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    with ENV_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ[k.strip()] = v.strip()


def _key(c: dict) -> tuple[int, int]:
    return (c["screen_id"], c["node_id"])


def _run_per_screen(
    conn, client, file_key, fetch_screenshot, screen_ids,
) -> list[dict]:
    """N=1 mode: one classification batch per screen."""
    all_results: list[dict] = []
    for sid in screen_ids:
        t0 = time.time()
        batch_results = classify_batch(
            conn, [sid], client, file_key, fetch_screenshot,
        )
        elapsed = time.time() - t0
        print(
            f"  [per-screen] sid={sid} n={len(batch_results)} t={elapsed:.1f}s",
            flush=True,
        )
        all_results.extend(batch_results)
    return all_results


def _run_cross_screen(
    conn, client, file_key, fetch_screenshot, screen_ids,
) -> tuple[list[dict], list[list[int]]]:
    """N=5 mode: batches grouped by (device_class, skeleton_type)."""
    batches = group_screens_by_skeleton_and_device(
        conn, screen_ids, target_batch_size=5,
    )
    all_results: list[dict] = []
    for batch in batches:
        t0 = time.time()
        batch_results = classify_batch(
            conn, batch, client, file_key, fetch_screenshot,
        )
        elapsed = time.time() - t0
        print(
            f"  [cross-screen] batch={batch} n={len(batch_results)} t={elapsed:.1f}s",
            flush=True,
        )
        all_results.extend(batch_results)
    return all_results, batches


def _compare(per_screen: list[dict], cross_screen: list[dict]) -> dict:
    """Compute agreement stats + divergences."""
    ps_map = {_key(c): c for c in per_screen}
    cs_map = {_key(c): c for c in cross_screen}
    common = sorted(set(ps_map.keys()) & set(cs_map.keys()))

    stats = {
        "total_per_screen": len(per_screen),
        "total_cross_screen": len(cross_screen),
        "common_keys": len(common),
        "ps_only_keys": sorted(set(ps_map) - set(cs_map)),
        "cs_only_keys": sorted(set(cs_map) - set(ps_map)),
        "agreements": 0,
        "disagreements": 0,
        "by_type_ps": {},  # per-screen distribution
        "by_type_cs": {},  # cross-screen distribution
        "disagreement_rows": [],
        "cross_screen_evidence_rows": [],
        "confidence_deltas": [],  # (key, ps_conf, cs_conf, same_type)
    }
    for k in common:
        ps = ps_map[k]
        cs = cs_map[k]
        ps_type = ps.get("canonical_type")
        cs_type = cs.get("canonical_type")
        stats["by_type_ps"][ps_type] = stats["by_type_ps"].get(ps_type, 0) + 1
        stats["by_type_cs"][cs_type] = stats["by_type_cs"].get(cs_type, 0) + 1
        same = ps_type == cs_type
        if same:
            stats["agreements"] += 1
        else:
            stats["disagreements"] += 1
            stats["disagreement_rows"].append((k, ps, cs))
        stats["confidence_deltas"].append((
            k, ps.get("confidence"), cs.get("confidence"), same,
        ))
        if cs.get("cross_screen_evidence"):
            stats["cross_screen_evidence_rows"].append((k, cs))
    stats["agreement_rate"] = (
        stats["agreements"] / stats["common_keys"]
        if stats["common_keys"] else 0.0
    )
    return stats


def _emit_report(
    stats: dict, batches: list[list[int]], out_path: Path,
) -> None:
    lines: list[str] = [
        "# M7.0.a Vision Stage Bake-Off — Per-Screen vs Cross-Screen",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"**Cross-screen batches** (grouped by device_class + skeleton_type):",
        "",
    ]
    for b in batches:
        lines.append(f"- {b}")
    lines.extend([
        "",
        "## Summary",
        "",
        f"- Per-screen total classifications: **{stats['total_per_screen']}**",
        f"- Cross-screen total classifications: **{stats['total_cross_screen']}**",
        f"- Common keys (scored for agreement): **{stats['common_keys']}**",
        f"- Agreements: **{stats['agreements']}**",
        f"- Disagreements: **{stats['disagreements']}**",
        f"- **Agreement rate: {stats['agreement_rate']:.1%}**",
        "",
    ])
    if stats["ps_only_keys"]:
        lines.append(
            f"Per-screen classified {len(stats['ps_only_keys'])} nodes "
            f"that cross-screen missed."
        )
    if stats["cs_only_keys"]:
        lines.append(
            f"Cross-screen classified {len(stats['cs_only_keys'])} nodes "
            f"that per-screen missed."
        )
    lines.append("")

    lines.append("## Type distribution (common keys only)")
    lines.append("")
    lines.append("| canonical_type | per-screen | cross-screen |")
    lines.append("|---|---:|---:|")
    all_types = sorted(
        set(stats["by_type_ps"]) | set(stats["by_type_cs"])
    )
    for t in all_types:
        p = stats["by_type_ps"].get(t, 0)
        c = stats["by_type_cs"].get(t, 0)
        lines.append(f"| `{t}` | {p} | {c} |")
    lines.append("")

    if stats["disagreement_rows"]:
        lines.append("## Disagreements")
        lines.append("")
        lines.append("| screen | node | per-screen | conf | cross-screen | conf | ps reason / cs reason |")
        lines.append("|---|---|---|---:|---|---:|---|")
        for (sid, nid), ps, cs in stats["disagreement_rows"][:50]:
            ps_type = ps.get("canonical_type")
            cs_type = cs.get("canonical_type")
            ps_conf = ps.get("confidence", 0)
            cs_conf = cs.get("confidence", 0)
            ps_reason = (ps.get("reason") or "")[:80]
            cs_reason = (cs.get("reason") or "")[:80]
            lines.append(
                f"| {sid} | {nid} | `{ps_type}` | {ps_conf:.2f} | "
                f"`{cs_type}` | {cs_conf:.2f} | "
                f"_ps:_ {ps_reason} <br>_cs:_ {cs_reason} |"
            )
        if len(stats["disagreement_rows"]) > 50:
            lines.append("")
            lines.append(f"_(... {len(stats['disagreement_rows']) - 50} more disagreements omitted)_")
        lines.append("")

    if stats["cross_screen_evidence_rows"]:
        lines.append("## Cross-screen evidence cited (sample)")
        lines.append("")
        lines.append("When cross-screen mode references other screens' nodes as supporting/contrasting evidence.")
        lines.append("")
        lines.append("| screen | node | type | evidence |")
        lines.append("|---|---|---|---|")
        for (sid, nid), cs in stats["cross_screen_evidence_rows"][:25]:
            ctype = cs.get("canonical_type")
            ev = cs.get("cross_screen_evidence") or []
            ev_str = "; ".join(
                f"s{e.get('other_screen_id')}/n{e.get('other_node_id')}:"
                f"{e.get('relation')}"
                for e in ev[:4]
            )
            lines.append(f"| {sid} | {nid} | `{ctype}` | {ev_str} |")
        lines.append("")

    if stats["confidence_deltas"]:
        agree_conf = [(p or 0, c or 0) for _, p, c, s in stats["confidence_deltas"] if s]
        if agree_conf:
            avg_ps = sum(p for p, _ in agree_conf) / len(agree_conf)
            avg_cs = sum(c for _, c in agree_conf) / len(agree_conf)
            lines.append("## Confidence calibration (on agreements)")
            lines.append("")
            lines.append(f"- Avg per-screen confidence (agreements): {avg_ps:.3f}")
            lines.append(f"- Avg cross-screen confidence (agreements): {avg_cs:.3f}")
            lines.append(f"- Delta: {avg_cs - avg_ps:+.3f}")
            lines.append("")

    lines.append("## Decision gate")
    lines.append("")
    rate = stats["agreement_rate"]
    if rate >= 0.95:
        lines.append(
            f"- Agreement rate **{rate:.1%} ≥ 95%**: cross-screen preserves the "
            f"per-screen signal. Commit to cross-screen for the full corpus "
            f"(better per-call reasoning at the same cost)."
        )
    elif rate >= 0.85:
        lines.append(
            f"- Agreement rate **{rate:.1%}**: cross-screen mostly agrees with "
            f"per-screen but 15%+ divergence is meaningful. Manually review "
            f"the disagreement rows above — some will be legitimate cross-screen "
            f"improvements; others will be node-tracking drift. Decide."
        )
    else:
        lines.append(
            f"- Agreement rate **{rate:.1%} < 85%**: cross-screen is diverging "
            f"substantially from per-screen. Node tracking across images may be "
            f"breaking down at this batch size. Fall back to per-screen (N=1) "
            f"for the full corpus — it costs the same at Sonnet rates anyway."
        )
    out_path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=str,
                    default="render_batch/m7_vision_bakeoff_report.md")
    ap.add_argument(
        "--model", type=str, default="claude-sonnet-4-6",
        help="Anthropic model id (default: claude-sonnet-4-6)",
    )
    args = ap.parse_args()

    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1
    if not os.environ.get("FIGMA_ACCESS_TOKEN"):
        print("ERROR: FIGMA_ACCESS_TOKEN not set", file=sys.stderr)
        return 1

    from dd.cli import make_figma_screenshot_fetcher
    import anthropic
    client = anthropic.Anthropic()
    fetch_screenshot = make_figma_screenshot_fetcher()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # `get_catalog` requires dict-convertible rows
    file_key = conn.execute(
        "SELECT file_key FROM files LIMIT 1"
    ).fetchone()[0]

    screen_ids = DEFAULT_SCREEN_IDS

    print("=== Cross-screen mode (N=5, grouped) ===")
    cross_screen, batches = _run_cross_screen(
        conn, client, file_key, fetch_screenshot, screen_ids,
    )

    print("\n=== Per-screen mode (N=1) ===")
    per_screen = _run_per_screen(
        conn, client, file_key, fetch_screenshot, screen_ids,
    )

    print("\n=== Comparing ===")
    stats = _compare(per_screen, cross_screen)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _emit_report(stats, batches, out_path)
    print(f"\nReport: {out_path}")
    print(f"Agreement rate: {stats['agreement_rate']:.1%}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
