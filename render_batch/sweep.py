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
# Python-side subprocess timeout for node walk_ref.js. Matched to
# walk_ref.js's watchdog (BRIDGE_TIMEOUT_MS default 300s + 10s
# connect tail + 10s Python-subprocess slack). Bumped 180 → 320 on
# 2026-04-22 alongside walk_ref.js's 170 → 300 raise — the 170s
# bridge timeout was OURS, not Figma's; Phase 1 perf + slot-inlined
# renders on iPad-sized screens legitimately need more headroom.
WALK_TIMEOUT = 320
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
    sid: int, name: str, skip_existing: bool, port: str, db_path: Path = None,
    *,
    grid: tuple[int, int] | None = None,
) -> dict:
    """Render + walk + verify one screen.

    `grid`: optional (row, col) tuple to lay the rendered root at a
    fixed grid cell on the Generated Test page. Pairs with
    `--keep-existing` so multiple sweep runs can share the page
    without overlapping. None means single-screen mode (clears the
    page on each render — the legacy default).
    """
    # Post-M6 canonical path: Option B markup-native renderer.
    if db_path is None:
        db_path = DB_PATH
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
        # F12a: walk-side runtime errors recorded by the render
        # script's per-op try/catch handlers (text_set_failed,
        # font_load_failed, component_missing, etc.). The structural
        # verifier's `error_count` only sees missing_child / extra_child
        # / shape drift — runtime visual-fidelity failures live here.
        # Kept separate so callers can distinguish "structurally clean
        # render" (error_count=0 + runtime_error_count=0) from "renders
        # but with visual gaps" (error_count=0 + runtime_error_count>0).
        "runtime_error_count": 0,
        "runtime_error_kinds": {},
        "failure": None,
    }

    # Generate
    if skip_existing and script_p.exists() and script_p.stat().st_size > 0:
        row["generate_ok"] = True
    else:
        gen_cmd = [
            "python3", "-m", "dd", "generate",
            "--db", str(db_path), "--screen", str(sid),
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
        # F12d: when grid is set, ask walk_ref.js to keep existing
        # children on the Generated Test page and tile this render
        # into the requested cell. Otherwise default behavior (clear
        # then render) — single-screen probe / non-sweep callers.
        walk_cmd = [
            "node", str(WALK_WRAPPER),
            str(script_p), str(walk_p), port,
        ]
        if grid is not None:
            walk_cmd.extend([
                "--keep-existing",
                f"--grid-pos={grid[0]},{grid[1]}",
            ])
        code, out, err = run_step(
            walk_cmd,
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
            "--db", str(db_path), "--screen", str(sid),
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
    # F12a: pull walk-side runtime error counts that the verifier now
    # surfaces in its --json payload. Older verifier versions lacked
    # these keys; default to 0/{} when absent so existing artefact
    # readers don't break.
    row["runtime_error_count"] = report.get("runtime_error_count", 0)
    row["runtime_error_kinds"] = report.get("runtime_error_kinds", {})
    return row


def process_screen_with_retry(
    sid: int, name: str, skip_existing: bool, port: str,
    max_retries: int = 2, retry_backoff: float = 1.0, db_path: Path = None,
    *,
    grid: tuple[int, int] | None = None,
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
        row = process_screen(sid, name, skip, port, db_path=db_path, grid=grid)
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

    # F12a: aggregate walk-side runtime errors across screens. These are
    # visual-fidelity failures (text_set_failed, font_load_failed,
    # component_missing, etc.) that the structural verifier doesn't see.
    # The "screens with runtime errors" count is the load-bearing visual-
    # fidelity headline — if it's >0 you have visual gaps even when
    # is_parity_true == total.
    runtime_kinds = Counter()
    screens_with_runtime_errors = 0
    total_runtime_errors = 0
    for r in rows:
        rk = r.get("runtime_error_kinds") or {}
        if rk:
            screens_with_runtime_errors += 1
        for k, v in rk.items():
            runtime_kinds[k] += v
        total_runtime_errors += r.get("runtime_error_count", 0)

    total = len(rows)
    parity_true = sum(1 for r in rows if r.get("is_parity") is True)
    parity_true_clean = sum(
        1 for r in rows
        if r.get("is_parity") is True and not (r.get("runtime_error_kinds") or {})
    )
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
        # F12a: subset of is_parity_true with zero runtime errors —
        # the "no visual fidelity gap detected" count.
        "is_parity_true_clean": parity_true_clean,
        "is_parity_false": total - parity_true - walk_failed - generate_failed,
        "generate_failed": generate_failed,
        "walk_failed": walk_failed,
        "retried": retried,
        "retried_recovered": retried_recovered,
        "error_kinds": dict(kinds.most_common()),
        # F12a: walk-side runtime errors, aggregated across screens.
        "screens_with_runtime_errors": screens_with_runtime_errors,
        "total_runtime_errors": total_runtime_errors,
        "runtime_error_kinds": dict(runtime_kinds.most_common()),
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
    ap.add_argument("--db", default=None,
                    help=f"Path to SQLite database. Default: {DB_PATH}")
    ap.add_argument("--out-dir", default=None,
                    help=f"Output dir for scripts/walks/reports/summary.json. "
                    f"Default: {ROOT}")
    ap.add_argument("--grid", action="store_true",
                    help="F12d sweep mode: lay rendered screens out in a "
                    "grid on the Generated Test page (don't clear between "
                    "renders). Each screen goes to a fixed cell so multiple "
                    "screens persist for visual review. Width determined "
                    "by --grid-cols.")
    ap.add_argument("--grid-cols", type=int, default=6,
                    help="Number of columns in --grid mode. Default 6 "
                    "(comfortable for 1440-wide desktop screens).")
    args = ap.parse_args()

    # Resolve db_path with default fallback (backward compatible)
    db_path = Path(args.db).resolve() if args.db else DB_PATH
    if not db_path.exists():
        print(f"Error: DB not found at {db_path}", file=sys.stderr)
        return 1

    # Resolve output dir; allows running multiple sweeps against different DBs
    # without overwriting artefacts. Defaults preserve existing behavior.
    out_root = Path(args.out_dir).resolve() if args.out_dir else ROOT
    scripts_dir = out_root / "scripts"
    walks_dir = out_root / "walks"
    reports_dir = out_root / "reports"

    # Override module-level constants for this run so process_screen uses them.
    # (process_screen reads SCRIPTS/WALKS/REPORTS by module reference; this
    # is the smallest backwards-compatible way to redirect output.)
    global SCRIPTS, WALKS, REPORTS
    SCRIPTS = scripts_dir
    WALKS = walks_dir
    REPORTS = reports_dir

    # Post-M6: single render path; single artefact layout.
    for p in (SCRIPTS, WALKS, REPORTS):
        p.mkdir(parents=True, exist_ok=True)

    screens = list_app_screens(db_path)
    if args.since:
        screens = [(sid, n) for sid, n in screens if sid >= args.since]
    if args.limit:
        screens = screens[: args.limit]

    grid_msg = (
        f", grid={args.grid_cols}-cols (renders persist for visual review)"
        if args.grid else ""
    )
    print(
        f"Sweeping {len(screens)} app_screens from {db_path.name} "
        f"(skip_existing={args.skip_existing}, port={args.port}, "
        f"out={out_root}{grid_msg})",
        flush=True,
    )
    rows: list[dict] = []
    t0 = time.time()
    for i, (sid, name) in enumerate(screens, 1):
        t1 = time.time()
        # F12d: compute (row, col) for this screen if --grid is set.
        # Sweep order is the iteration index (i-1), so grid layout
        # mirrors the screen-id order: row = i // cols, col = i % cols.
        grid: tuple[int, int] | None = None
        if args.grid:
            grid_idx = i - 1
            grid = (grid_idx // args.grid_cols, grid_idx % args.grid_cols)
        row = process_screen_with_retry(
            sid, name, args.skip_existing, args.port,
            max_retries=args.max_retries,
            retry_backoff=args.retry_backoff,
            db_path=db_path,
            grid=grid,
        )
        elapsed = time.time() - t1
        # F12a: PARITY+ marker means structural parity but with
        # walk-side runtime errors (visual fidelity gap). Distinguishes
        # "clean" from "structurally clean / visually degraded".
        if row["is_parity"] is True:
            status = "PARITY+" if row.get("runtime_error_count", 0) > 0 else "PARITY"
        elif row.get("failure"):
            status = "FAIL"
        else:
            status = "DRIFT"
        attempt_marker = (
            f" (try {row.get('attempt', 1)})" if row.get("attempt", 1) > 1 else ""
        )
        rt_count = row.get("runtime_error_count", 0)
        rt_part = f" rt={rt_count}" if rt_count else ""
        print(
            f"[{i}/{len(screens)}] screen={sid:3d} {status:7s}{attempt_marker} "
            f"t={elapsed:5.1f}s "
            f"parity={row.get('parity_ratio')} "
            f"errs={row.get('error_count')}{rt_part} "
            f"{'kinds=' + ','.join(row['error_kinds'][:3]) if row['error_kinds'] else ''} "
            f"{('FAIL=' + row['failure'][:120]) if row.get('failure') else ''}",
            flush=True,
        )
        rows.append(row)

    summary = summarize(rows)
    summary["elapsed_s"] = round(time.time() - t0, 1)
    summary["db_path"] = str(db_path)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY ===")
    print(f"total:            {summary['total']}")
    print(f"is_parity=True:   {summary['is_parity_true']}")
    # F12a: surface "structurally clean / visually degraded" so the
    # headline parity number isn't misread.
    print(
        f"  ├─ clean (no runtime errs):   {summary.get('is_parity_true_clean', summary['is_parity_true'])}"
    )
    print(
        f"  └─ structurally OK / visually degraded: "
        f"{summary['is_parity_true'] - summary.get('is_parity_true_clean', summary['is_parity_true'])}"
    )
    print(f"is_parity=False:  {summary['is_parity_false']}")
    print(f"generate_failed:  {summary['generate_failed']}")
    print(f"walk_failed:      {summary['walk_failed']}")
    print(
        f"retried:          {summary['retried']} "
        f"(recovered to PARITY: {summary['retried_recovered']})"
    )
    print(f"elapsed:          {summary['elapsed_s']}s")
    print("\nerror_kinds (structural — verifier-reported):")
    if summary["error_kinds"]:
        for kind, ct in summary["error_kinds"].items():
            print(f"  {kind:30s}  {ct}")
    else:
        print("  (none)")
    # F12a: walk-side runtime errors aggregated. "0 in N screens" means
    # the renderer never had to record-and-continue; that's the cleanest
    # visual-fidelity headline.
    print(
        f"\nruntime_errors:   {summary.get('total_runtime_errors', 0)} "
        f"across {summary.get('screens_with_runtime_errors', 0)} screens "
        f"(visual-fidelity channel — F11.1 catch-and-continue)"
    )
    rt_kinds = summary.get("runtime_error_kinds") or {}
    if rt_kinds:
        for kind, ct in rt_kinds.items():
            print(f"  {kind:30s}  {ct}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
