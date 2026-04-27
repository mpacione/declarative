"""Rule v2 (weighted) consensus analysis — no re-classification.

Rule v1 (current) is plain majority:
    3-way-agree → commit / 2-of-3 → majority / 3-way-disagree → flag.

Rule v2 (weighted) assigns integer votes by source accuracy:
    LLM = 1
    Vision PS = 1
    Vision CS = 2  (67.6% on user's `accept_source` review corpus
                    vs 55.7% LLM and 51.0% PS)

A verdict wins if its weighted-vote total strictly exceeds the next
highest. Ties (LLM+PS = 2 vs CS = 2) still flag, matching rule v1's
posture that "no clear majority" deserves review.

Usage:

    .venv/bin/python3 -m scripts.consensus_weighted_analysis \\
        --db Dank-EXP-02.declarative.db
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


UNSURE = "unsure"
WEIGHTS = {"llm": 1, "vision_ps": 1, "vision_cs": 2}


def weighted_consensus(
    llm: str | None, ps: str | None, cs: str | None,
) -> tuple[str | None, str, bool]:
    """Apply weighted rule. Returns (canonical_type, method, flagged)."""
    verdicts = {"llm": llm, "vision_ps": ps, "vision_cs": cs}
    present = {k: v for k, v in verdicts.items() if v is not None}

    if not present:
        return (None, "no_sources", True)

    # Unsure short-circuit — matches rule v1's "any unsure flags it."
    if any(v == UNSURE for v in present.values()):
        return (UNSURE, "any_unsure", True)

    votes: Counter[str] = Counter()
    for source, ctype in present.items():
        votes[ctype] += WEIGHTS[source]

    top = votes.most_common()
    winner_type, winner_votes = top[0]

    if len(top) == 1:
        # Everyone agrees.
        method = "unanimous" if len(present) == 3 else "two_source_unanimous"
        return (winner_type, method, False)

    runner_up_votes = top[1][1]
    if winner_votes > runner_up_votes:
        method = "weighted_majority"
        return (winner_type, method, False)
    # Tie — explicit flag for review.
    return (UNSURE, "weighted_tie", True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    conn = get_connection(args.db)

    rows = conn.execute(
        """
        SELECT r.source_accepted,
               sci.canonical_type AS current_consensus,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
               sci.consensus_method
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        WHERE r.decision_type = 'accept_source'
        """
    ).fetchall()

    total = 0
    v1_matches = 0
    v2_matches = 0
    per_source_v1: dict[str, list[int]] = {
        "llm": [0, 0], "vision_ps": [0, 0], "vision_cs": [0, 0],
    }
    per_source_v2: dict[str, list[int]] = {
        "llm": [0, 0], "vision_ps": [0, 0], "vision_cs": [0, 0],
    }
    method_breakdown_v1: Counter[str] = Counter()
    method_breakdown_v2: Counter[str] = Counter()
    flip_examples: list[tuple[str, str, str, str, str]] = []

    for row in rows:
        src = row["source_accepted"]
        current = row["current_consensus"]
        llm = row["llm_type"]
        ps = row["vision_ps_type"]
        cs = row["vision_cs_type"]
        cur_method = row["consensus_method"]

        picked_type = {"llm": llm, "vision_ps": ps, "vision_cs": cs}.get(src)
        if picked_type is None:
            continue

        total += 1
        method_breakdown_v1[cur_method or "none"] += 1

        v1_match = current == picked_type
        if v1_match:
            v1_matches += 1
            per_source_v1[src][0] += 1
        per_source_v1[src][1] += 1

        new_type, new_method, _ = weighted_consensus(llm, ps, cs)
        method_breakdown_v2[new_method] += 1
        v2_match = new_type == picked_type
        if v2_match:
            v2_matches += 1
            per_source_v2[src][0] += 1
        per_source_v2[src][1] += 1

        # Track cases where v2 flips a v1 miss into a win or vice versa.
        if v1_match != v2_match and len(flip_examples) < 40:
            flip_examples.append((
                src, picked_type, current, new_type,
                f"LLM={llm}, PS={ps}, CS={cs}",
            ))

    conn.close()

    pct1 = (v1_matches / total * 100.0) if total else 0.0
    pct2 = (v2_matches / total * 100.0) if total else 0.0

    print(f"Total accept_source reviews with all 3 sources: {total}\n")
    print(f"Rule v1 (plain majority):  {v1_matches}/{total} = {pct1:.1f}%")
    print(f"Rule v2 (weighted, CS=2x): {v2_matches}/{total} = {pct2:.1f}%")
    print(f"Delta: {v2_matches - v1_matches:+d} "
          f"({pct2 - pct1:+.1f} pts)\n")

    print("Per-source match (rule v1 → rule v2):")
    print(f"{'source':<12} {'v1 matched':>12} {'v2 matched':>12} {'delta':>8}")
    for src in ("llm", "vision_ps", "vision_cs"):
        m1, t1 = per_source_v1[src]
        m2, t2 = per_source_v2[src]
        p1 = (m1 / t1 * 100.0) if t1 else 0.0
        p2 = (m2 / t2 * 100.0) if t2 else 0.0
        print(
            f"{src:<12} {m1}/{t1} ({p1:.1f}%)".ljust(25)
            + f"  {m2}/{t2} ({p2:.1f}%)".ljust(18)
            + f"  {m2 - m1:+d}"
        )
    print()

    print("Consensus method breakdown (v1 → v2):")
    all_methods = sorted(set(method_breakdown_v1) | set(method_breakdown_v2))
    for m in all_methods:
        print(
            f"  {m:<25} v1: {method_breakdown_v1.get(m, 0):>4}   "
            f"v2: {method_breakdown_v2.get(m, 0):>4}"
        )
    print()

    print("Sample cases where v1 and v2 differ:")
    print(f"{'src':<11} {'truth':<18} {'v1_pick':<18} {'v2_pick':<18} sources")
    for src, truth, v1, v2, sources in flip_examples[:20]:
        print(
            f"  {src:<9} {str(truth)[:16]:<18} "
            f"{str(v1)[:16]:<18} {str(v2)[:16]:<18} {sources}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
