"""Sweep driver: for each app_screen, generate → walk → verify → collect.

Outputs:
  render_batch/scripts/<id>.js      Figma script
  render_batch/scripts/<id>.stderr  generate stderr (diagnostic)
  render_batch/walks/<id>.json      rendered-ref walk payload
  render_batch/walks/<id>.err       walk stderr on failure
  render_batch/reports/<id>.json    dd verify --json output
  render_batch/summary.json         aggregate (kinds, parity distribution, failures)

Usage: python3 render_batch/sweep.py [--limit N] [--skip-existing]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
WALKS = ROOT / "walks"
REPORTS = ROOT / "reports"
DB_PATH = ROOT.parent / "Dank-EXP-02.declarative.db"
WALK_WRAPPER = ROOT.parent / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9228"
GENERATE_TIMEOUT = 60
WALK_TIMEOUT = 180
VERIFY_TIMEOUT = 30


def list_app_screens(db: Path) -> list[tuple[int, str]]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT id, name FROM screens WHERE screen_type='app_screen' ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return rows


def run_step(cmd: list[str], timeout: int, label: str) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT after {timeout}s in {label}"
    except Exception as e:  # noqa: BLE001
        return 125, "", f"EXCEPTION in {label}: {e!r}"


def process_screen(sid: int, name: str, skip_existing: bool) -> dict:
    script_p = SCRIPTS / f"{sid}.js"
    walk_p = WALKS / f"{sid}.json"
    report_p = REPORTS / f"{sid}.json"

    row = {
        "screen_id": sid,
        "name": name,
        "stage": "generate",
        "generate_ok": False,
        "walk_ok": False,
        "verify_ok": False,
        "is_parity": None,
        "parity_ratio": None,
        "error_kinds": [],
        "error_count": 0,
        "ir_node_count": None,
        "rendered_node_count": None,
        "failure": None,
    }

    # Generate
    if skip_existing and script_p.exists() and script_p.stat().st_size > 0:
        row["generate_ok"] = True
    else:
        code, out, err = run_step(
            [
                "python3", "-m", "dd", "generate",
                "--db", str(DB_PATH), "--screen", str(sid),
            ],
            GENERATE_TIMEOUT,
            "generate",
        )
        if code != 0 or not out.strip():
            (SCRIPTS / f"{sid}.stderr").write_text(err)
            row["failure"] = f"generate exit={code}: {err[:300]}"
            return row
        script_p.write_text(out)
        row["generate_ok"] = True

    # Walk
    row["stage"] = "walk"
    if skip_existing and walk_p.exists() and walk_p.stat().st_size > 0:
        row["walk_ok"] = True
    else:
        code, out, err = run_step(
            [
                "node", str(WALK_WRAPPER),
                str(script_p), str(walk_p), BRIDGE_PORT,
            ],
            WALK_TIMEOUT,
            "walk",
        )
        if code != 0 or not walk_p.exists():
            (WALKS / f"{sid}.err").write_text((err or out)[:4000])
            row["failure"] = f"walk exit={code}: {(err or out)[:300]}"
            return row
        row["walk_ok"] = True

    # Verify
    row["stage"] = "verify"
    code, out, err = run_step(
        [
            "python3", "-m", "dd", "verify",
            "--db", str(DB_PATH), "--screen", str(sid),
            "--rendered-ref", str(walk_p), "--json",
        ],
        VERIFY_TIMEOUT,
        "verify",
    )
    # Verify returns 0 when parity, 1 when not — but we want the JSON either way.
    if code not in (0, 1) or not out.strip():
        row["failure"] = f"verify exit={code}: {err[:300]}"
        return row

    try:
        report = json.loads(out)
    except json.JSONDecodeError as e:
        row["failure"] = f"verify json decode: {e!r}"
        return row

    report_p.write_text(json.dumps(report, indent=2))

    row["verify_ok"] = True
    row["is_parity"] = report["is_parity"]
    row["parity_ratio"] = report["parity_ratio"]
    row["ir_node_count"] = report["ir_node_count"]
    row["rendered_node_count"] = report["rendered_node_count"]
    row["error_kinds"] = [e["kind"] for e in report["errors"]]
    row["error_count"] = len(report["errors"])
    return row


def summarize(rows: list[dict]) -> dict:
    kinds = Counter()
    for r in rows:
        kinds.update(r.get("error_kinds") or [])

    total = len(rows)
    parity_true = sum(1 for r in rows if r.get("is_parity") is True)
    walk_failed = sum(1 for r in rows if r.get("walk_ok") is False and r.get("generate_ok"))
    generate_failed = sum(1 for r in rows if r.get("generate_ok") is False)

    return {
        "total": total,
        "is_parity_true": parity_true,
        "is_parity_false": total - parity_true - walk_failed - generate_failed,
        "generate_failed": generate_failed,
        "walk_failed": walk_failed,
        "error_kinds": dict(kinds.most_common()),
        "per_screen": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-existing", action="store_true",
                    help="Reuse existing scripts/walks if present")
    ap.add_argument("--since", type=int, default=None,
                    help="Start at this screen id (for resume)")
    args = ap.parse_args()

    for p in (SCRIPTS, WALKS, REPORTS):
        p.mkdir(parents=True, exist_ok=True)

    screens = list_app_screens(DB_PATH)
    if args.since:
        screens = [(sid, n) for sid, n in screens if sid >= args.since]
    if args.limit:
        screens = screens[: args.limit]

    print(f"Sweeping {len(screens)} app_screens (skip_existing={args.skip_existing})", flush=True)
    rows: list[dict] = []
    t0 = time.time()
    for i, (sid, name) in enumerate(screens, 1):
        t1 = time.time()
        row = process_screen(sid, name, args.skip_existing)
        elapsed = time.time() - t1
        status = (
            "PARITY" if row["is_parity"] is True
            else "FAIL" if row.get("failure")
            else "DRIFT"
        )
        print(
            f"[{i}/{len(screens)}] screen={sid:3d} {status:6s} "
            f"t={elapsed:5.1f}s "
            f"parity={row.get('parity_ratio')} "
            f"errs={row.get('error_count')} "
            f"{'kinds=' + ','.join(row['error_kinds'][:3]) if row['error_kinds'] else ''} "
            f"{('FAIL=' + row['failure'][:120]) if row.get('failure') else ''}",
            flush=True,
        )
        rows.append(row)

    summary = summarize(rows)
    summary["elapsed_s"] = round(time.time() - t0, 1)
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY ===")
    print(f"total:            {summary['total']}")
    print(f"is_parity=True:   {summary['is_parity_true']}")
    print(f"is_parity=False:  {summary['is_parity_false']}")
    print(f"generate_failed:  {summary['generate_failed']}")
    print(f"walk_failed:      {summary['walk_failed']}")
    print(f"elapsed:          {summary['elapsed_s']}s")
    print("\nerror_kinds:")
    for kind, ct in summary["error_kinds"].items():
        print(f"  {kind:30s}  {ct}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
