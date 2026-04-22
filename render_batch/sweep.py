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
# Default port; override via --port. The Desktop Bridge picks between
# 9223-9231 on startup depending on what's already bound.
BRIDGE_PORT_DEFAULT = "9228"
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


def process_screen(
    sid: int, name: str, skip_existing: bool, port: str,
) -> dict:
    # Post-M6 canonical path: Option B markup-native renderer.
    scripts_dir = SCRIPTS
    walks_dir = WALKS
    reports_dir = REPORTS
    script_p = scripts_dir / f"{sid}.js"
    walk_p = walks_dir / f"{sid}.json"
    report_p = reports_dir / f"{sid}.json"

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
        gen_cmd = [
            "python3", "-m", "dd", "generate",
            "--db", str(DB_PATH), "--screen", str(sid),
        ]
        code, out, err = run_step(
            gen_cmd,
            GENERATE_TIMEOUT,
            "generate",
        )
        if code != 0 or not out.strip():
            (scripts_dir / f"{sid}.stderr").write_text(err)
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
                str(script_p), str(walk_p), port,
            ],
            WALK_TIMEOUT,
            "walk",
        )
        if code != 0 or not walk_p.exists():
            (walks_dir / f"{sid}.err").write_text((err or out)[:4000])
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


def process_screen_with_retry(
    sid: int, name: str, skip_existing: bool, port: str,
    max_retries: int = 2, retry_backoff: float = 1.0,
) -> dict:
    """Wrap ``process_screen`` with per-screen retry on transient failures.

    Per ``feedback_sweep_transient_timeouts.md``: the bridge accumulates
    load during a sweep; mid-sweep `getNodeByIdAsync` calls can silently
    return null, producing missing_component_node + component_missing
    errors that resolve cleanly on a fresh retry. Same for outright walk
    timeouts on iPad-sized screens.

    Retry policy:
    - Generate failures NEVER retry (deterministic; usually a real bug).
    - Walk-failure (script timeout, bridge error) DOES retry — these are
      pure transients on the bridge side.
    - Verify success but is_parity=False with errors DOES retry — most
      likely the prefetch-returned-null class.
    - is_parity=True is the success case; return immediately.

    Backoff is exponential capped at 10s: 1s, 2s, 4s.
    """
    last_row: dict = {}
    for attempt in range(max_retries + 1):
        if attempt > 0:
            sleep_s = min(retry_backoff * (2 ** (attempt - 1)), 10.0)
            time.sleep(sleep_s)
        # Don't reuse failed artefacts on retry — regenerate everything.
        skip = skip_existing if attempt == 0 else False
        row = process_screen(sid, name, skip, port)
        row["attempt"] = attempt + 1
        last_row = row
        if row.get("is_parity") is True:
            return row
        # Don't retry generate failures
        if row.get("generate_ok") is False:
            return row
    return last_row


def summarize(rows: list[dict]) -> dict:
    kinds = Counter()
    for r in rows:
        kinds.update(r.get("error_kinds") or [])

    total = len(rows)
    parity_true = sum(1 for r in rows if r.get("is_parity") is True)
    walk_failed = sum(1 for r in rows if r.get("walk_ok") is False and r.get("generate_ok"))
    generate_failed = sum(1 for r in rows if r.get("generate_ok") is False)

    retried = sum(1 for r in rows if r.get("attempt", 1) > 1)
    retried_recovered = sum(
        1 for r in rows
        if r.get("attempt", 1) > 1 and r.get("is_parity") is True
    )

    return {
        "total": total,
        "is_parity_true": parity_true,
        "is_parity_false": total - parity_true - walk_failed - generate_failed,
        "generate_failed": generate_failed,
        "walk_failed": walk_failed,
        "retried": retried,
        "retried_recovered": retried_recovered,
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
    ap.add_argument("--port", default=BRIDGE_PORT_DEFAULT,
                    help="Desktop Bridge WebSocket port")
    ap.add_argument("--max-retries", type=int, default=2,
                    help="Per-screen retry count on transient failures "
                    "(walk timeout, missing-component drift). "
                    "Default 2 (3 attempts total). Set 0 to disable.")
    ap.add_argument("--retry-backoff", type=float, default=1.0,
                    help="Initial backoff seconds before retry "
                    "(doubles each attempt, capped at 10s).")
    args = ap.parse_args()

    # Post-M6: single render path; single artefact layout.
    for p in (SCRIPTS, WALKS, REPORTS):
        p.mkdir(parents=True, exist_ok=True)

    screens = list_app_screens(DB_PATH)
    if args.since:
        screens = [(sid, n) for sid, n in screens if sid >= args.since]
    if args.limit:
        screens = screens[: args.limit]

    print(
        f"Sweeping {len(screens)} app_screens "
        f"(skip_existing={args.skip_existing}, port={args.port})",
        flush=True,
    )
    rows: list[dict] = []
    t0 = time.time()
    for i, (sid, name) in enumerate(screens, 1):
        t1 = time.time()
        row = process_screen_with_retry(
            sid, name, args.skip_existing, args.port,
            max_retries=args.max_retries,
            retry_backoff=args.retry_backoff,
        )
        elapsed = time.time() - t1
        status = (
            "PARITY" if row["is_parity"] is True
            else "FAIL" if row.get("failure")
            else "DRIFT"
        )
        attempt_marker = (
            f" (try {row.get('attempt', 1)})" if row.get("attempt", 1) > 1 else ""
        )
        print(
            f"[{i}/{len(screens)}] screen={sid:3d} {status:6s}{attempt_marker} "
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
    print(
        f"retried:          {summary['retried']} "
        f"(recovered to PARITY: {summary['retried_recovered']})"
    )
    print(f"elapsed:          {summary['elapsed_s']}s")
    print("\nerror_kinds:")
    for kind, ct in summary["error_kinds"].items():
        print(f"  {kind:30s}  {ct}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
