"""Tier E.4 — human-reject UX spike for synthesis review.

Per docs/plan-burndown.md §Tier E.4: how does a designer say "no,
not that" when they see a synthesis proposal? This is a SPIKE —
minimal CLI, local-file-only, no UI framework. The learnings
feed a real product-layer UX later.

Workflow:
  1. Run a synthesis (via Tier D's eval harness or manually) and
     save the script + optional walk + fidelity report to an
     artefact directory.
  2. Run `m7_review_synth list` to see pending proposals.
  3. Run `m7_review_synth show <id>` to inspect one: IR summary,
     Tier C scores, rendered screenshot path if available.
  4. Run `m7_review_synth reject <id> --reason "..."` or
     `m7_review_synth accept <id>` to record the decision. Rejections
     write a structured JSON log.
  5. Rejection reasons feed back into prompt tuning + catalog gaps.

The spike's purpose: prove the WORKFLOW shape, not build a real UI.
Designers can pipe this through tooling of their choice (Slack/
Linear/spreadsheet) once the schema is stable.

Usage::

    # after a synthesis run that produced an artefact:
    python3 -m scripts.review_synth list
    python3 -m scripts.review_synth show tier_d_report-20260421-001
    python3 -m scripts.review_synth reject tier_d_report-20260421-001 \\
        --reason "button variant should be destructive, not secondary"
    python3 -m scripts.review_synth decisions  # show log
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Artefact layout convention — kept minimal, local only.
_DEFAULT_ROOT = Path("render_batch/synth_proposals")
_DECISIONS_FILE = _DEFAULT_ROOT / "decisions.jsonl"


def _load_proposal(root: Path, pid: str) -> dict | None:
    """Proposals are directories under ``root/<pid>/`` with at
    least ``meta.json``. Optional sidecars: ``ir.json``,
    ``script.js``, ``walk.json``, ``report.json``,
    ``screenshot.png``."""
    pdir = root / pid
    meta_path = pdir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    meta["_id"] = pid
    meta["_dir"] = str(pdir)
    meta["_artefacts"] = sorted(
        p.name for p in pdir.iterdir() if p.is_file()
    )
    return meta


def _iter_proposals(root: Path):
    if not root.exists():
        return
    for pdir in sorted(root.iterdir()):
        if not pdir.is_dir():
            continue
        pid = pdir.name
        meta = _load_proposal(root, pid)
        if meta is not None:
            yield meta


def _existing_decisions(root: Path) -> dict[str, dict]:
    """Last decision wins — rejections can be overturned by a
    later accept, and vice versa."""
    log = _DECISIONS_FILE_for(root)
    if not log.exists():
        return {}
    out: dict[str, dict] = {}
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" in d:
            out[d["id"]] = d
    return out


def _DECISIONS_FILE_for(root: Path) -> Path:
    return root / "decisions.jsonl"


def _append_decision(root: Path, entry: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    log = _DECISIONS_FILE_for(root)
    with log.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def cmd_list(args) -> int:
    root = Path(args.root)
    decisions = _existing_decisions(root)
    rows = list(_iter_proposals(root))
    if not rows:
        print(f"No proposals under {root}/")
        return 0
    print(f"{'id':40s}  {'score':>6s}  {'decision':12s}  summary")
    print("-" * 80)
    for m in rows:
        score = m.get("score_ten", "?")
        score_str = f"{score:.1f}" if isinstance(score, (int, float)) else str(score)
        d = decisions.get(m["_id"], {}).get("decision", "—")
        summary = (m.get("prompt") or m.get("scope") or "")[:40]
        print(f"{m['_id']:40s}  {score_str:>6s}  {d:12s}  {summary}")
    return 0


def cmd_show(args) -> int:
    root = Path(args.root)
    meta = _load_proposal(root, args.pid)
    if meta is None:
        print(f"Proposal {args.pid} not found under {root}/", file=sys.stderr)
        return 1
    print(f"Proposal: {meta['_id']}")
    print(f"  dir:       {meta['_dir']}")
    print(f"  artefacts: {', '.join(meta['_artefacts'])}")
    for k, v in meta.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (dict, list)):
            v_str = json.dumps(v, indent=2)[:400]
        else:
            v_str = str(v)[:200]
        print(f"  {k}: {v_str}")
    # Surface the prior decision if any.
    dec = _existing_decisions(root).get(args.pid)
    if dec:
        print(f"\n  PRIOR DECISION: {dec['decision']}"
              f" ({dec.get('decided_at')})")
        if dec.get("reason"):
            print(f"    reason: {dec['reason']}")
    return 0


def cmd_reject(args) -> int:
    root = Path(args.root)
    meta = _load_proposal(root, args.pid)
    if meta is None:
        print(f"Proposal {args.pid} not found", file=sys.stderr)
        return 1
    entry = {
        "id": args.pid,
        "decision": "reject",
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": args.reason,
        "categories": args.category or [],
    }
    _append_decision(root, entry)
    print(
        f"Recorded reject for {args.pid} — reason: {args.reason!r}"
    )
    return 0


def cmd_accept(args) -> int:
    root = Path(args.root)
    meta = _load_proposal(root, args.pid)
    if meta is None:
        print(f"Proposal {args.pid} not found", file=sys.stderr)
        return 1
    entry = {
        "id": args.pid,
        "decision": "accept",
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _append_decision(root, entry)
    print(f"Recorded accept for {args.pid}")
    return 0


def cmd_decisions(args) -> int:
    root = Path(args.root)
    decisions = _existing_decisions(root)
    if not decisions:
        print("No decisions recorded.")
        return 0
    print(f"{'id':40s}  {'decision':10s}  {'decided_at':22s}  reason")
    print("-" * 110)
    for pid, d in sorted(
        decisions.items(), key=lambda p: p[1].get("decided_at", ""),
    ):
        reason = (d.get("reason") or "")[:40]
        print(
            f"{pid:40s}  "
            f"{d.get('decision', '?'):10s}  "
            f"{d.get('decided_at', '?'):22s}  "
            f"{reason}"
        )
    return 0


def cmd_stash(args) -> int:
    """Create a minimal proposal stub from the command line (for
    manual entry or pipeline wiring)."""
    root = Path(args.root)
    pid = args.pid or time.strftime("proposal-%Y%m%d-%H%M%S", time.gmtime())
    pdir = root / pid
    pdir.mkdir(parents=True, exist_ok=True)
    meta = {
        "prompt": args.prompt or "",
        "scope": args.scope or "",
        "score_ten": args.score,
    }
    (pdir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Stashed proposal at {pdir}/meta.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root", default=str(_DEFAULT_ROOT),
        help="Directory holding proposal artefacts.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_list = sub.add_parser("list", help="Show pending proposals.")
    sp_list.set_defaults(func=cmd_list)

    sp_show = sub.add_parser("show", help="Inspect one proposal.")
    sp_show.add_argument("pid")
    sp_show.set_defaults(func=cmd_show)

    sp_rej = sub.add_parser("reject", help="Reject with reason.")
    sp_rej.add_argument("pid")
    sp_rej.add_argument("--reason", required=True)
    sp_rej.add_argument(
        "--category", action="append",
        help="Tag for aggregation (e.g. 'variant', 'missing_font', 'layout').",
    )
    sp_rej.set_defaults(func=cmd_reject)

    sp_acc = sub.add_parser("accept", help="Accept a proposal.")
    sp_acc.add_argument("pid")
    sp_acc.set_defaults(func=cmd_accept)

    sp_dec = sub.add_parser("decisions", help="Show decision log.")
    sp_dec.set_defaults(func=cmd_decisions)

    sp_st = sub.add_parser("stash", help="Create a proposal stub.")
    sp_st.add_argument("--pid")
    sp_st.add_argument("--prompt")
    sp_st.add_argument("--scope")
    sp_st.add_argument("--score", type=float, default=0.0)
    sp_st.set_defaults(func=cmd_stash)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
