"""Calibrate rule-v3 weights from live reviews + re-apply consensus.

One-shot helper: (1) read every ``accept_source`` review row from the
DB, (2) compute per-(source, type) weights via
``build_calibrated_weights``, (3) re-apply consensus using rule v3,
and (4) print a summary of the new consensus breakdown + per-source
accept rates that feed back into the weights.

No API calls. Safe to run repeatedly — it recomputes and rewrites
``canonical_type`` / ``consensus_method`` / ``flagged_for_review``
based on the persisted source verdicts. Your manual review overrides
(non-accept_source decisions) are not affected because
``apply_reviews_to_sci`` is unchanged and can be run independently.

Usage::

    .venv/bin/python3 -m scripts.m7_calibrate_consensus \\
        --db Dank-EXP-02.declarative.db

    # Inspect the weights without committing:
    .venv/bin/python3 -m scripts.m7_calibrate_consensus \\
        --db Dank-EXP-02.declarative.db --dry-run

    # Write the weights to JSON:
    .venv/bin/python3 -m scripts.m7_calibrate_consensus \\
        --db Dank-EXP-02.declarative.db \\
        --weights-out render_batch/consensus_v3_weights.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dd.classify import apply_consensus_to_screen
from dd.classify_consensus import build_calibrated_weights
from dd.db import get_connection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute + print the weights but don't re-apply consensus.",
    )
    parser.add_argument(
        "--weights-out", default=None,
        help="Optional JSON path to dump the computed weights.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    conn = get_connection(args.db)
    review_rows = conn.execute(
        """
        SELECT r.decision_type, r.source_accepted,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        WHERE r.decision_type = 'accept_source'
        """
    ).fetchall()
    reviews = [
        {
            "decision_type": r["decision_type"],
            "source_accepted": r["source_accepted"],
            "llm_type": r["llm_type"],
            "vision_ps_type": r["vision_ps_type"],
            "vision_cs_type": r["vision_cs_type"],
        }
        for r in review_rows
    ]
    print(f"Collected {len(reviews)} accept_source reviews.")

    if not reviews:
        print(
            "No accept_source reviews yet — rule v3 with empty weights "
            "degrades to rule v1 (uniform default 0.5 per source). "
            "Re-run this script once you've reviewed ~100+ rows.",
            file=sys.stderr,
        )
        # Still emit empty weights for completeness.

    weights = build_calibrated_weights(reviews)

    # Summarise the top + bottom weights per source for a quick eyeball.
    if weights:
        by_source: dict[str, list[tuple[str, float]]] = {
            "llm": [], "vision_ps": [], "vision_cs": [],
        }
        for (src, t), w in weights.items():
            by_source.setdefault(src, []).append((t, w))
        print("\nTop 5 most-trusted (source, type) pairs:")
        all_sorted = sorted(weights.items(), key=lambda x: -x[1])
        for (src, t), w in all_sorted[:5]:
            print(f"  {src:<12} {t:<22} {w:.3f}")
        print("\nBottom 5 least-trusted (source, type) pairs:")
        for (src, t), w in all_sorted[-5:]:
            print(f"  {src:<12} {t:<22} {w:.3f}")

    if args.weights_out:
        # JSON can't have tuple keys — serialize as a list of triples.
        payload = [
            {"source": src, "predicted_type": t, "weight": w}
            for (src, t), w in sorted(weights.items())
        ]
        Path(args.weights_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.weights_out).write_text(json.dumps(payload, indent=2))
        print(f"\nWrote weights: {args.weights_out}")

    if args.dry_run:
        print("\nDry-run: skipping consensus re-apply.")
        conn.close()
        return 0

    # Re-apply consensus using rule v3 + computed weights.
    screen_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM screens "
            "WHERE device_class IS NULL OR device_class != 'component_sheet' "
            "ORDER BY id"
        ).fetchall()
    ]
    print(
        f"\nRe-applying rule v3 consensus across {len(screen_ids)} screens..."
    )
    total: dict[str, int] = {}
    for sid in screen_ids:
        counts = apply_consensus_to_screen(
            conn, screen_id=sid, rule="v3", weights=weights,
        )
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v

    print("\nConsensus method breakdown:")
    for k in sorted(total):
        print(f"  {k:<30} {total[k]:>6}")

    flagged_count = conn.execute(
        "SELECT COUNT(*) FROM screen_component_instances "
        "WHERE flagged_for_review = 1"
    ).fetchone()[0]
    print(f"\nFlagged rows: {flagged_count}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
