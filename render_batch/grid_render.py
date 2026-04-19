"""Grid-render a sample of the Dank corpus onto the current Figma page.

Usage:
    python3 render_batch/grid_render.py --port 9228 --fraction 0.3
    python3 render_batch/grid_render.py --port 9228 --limit 61 --cols 8

Renders each screen via the Option B markup-native walker at a
deterministic canvas position so the frames persist on the current
Figma page in a grid. Walks each after render (to validate it)
then moves on. Does NOT verify — walk output is discarded.
"""

from __future__ import annotations

import argparse
import math
import random
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT.parent / "Dank-EXP-02.declarative.db"
# Use the non-wiping grid executor — walk_ref.js wipes the current
# page on every invocation, which defeats the purpose of a
# side-by-side grid. grid_exec.js persists all frames on a dedicated
# "Option-B-Grid" page.
GRID_EXECUTOR = ROOT.parent / "render_test" / "grid_exec.js"
SCRIPTS_DIR = ROOT / "scripts-grid"
WALKS_DIR = ROOT / "walks-grid"

# Column width / row height — large enough to fit the widest Dank
# screens (iPad Pro 12.9" at 1024 px wide, iPad-portrait screens at
# 1366 px tall) with comfortable padding for visual inspection.
COL_STRIDE = 1400
ROW_STRIDE = 1500
GENERATE_TIMEOUT = 60
WALK_TIMEOUT = 180


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="9228")
    ap.add_argument("--fraction", type=float, default=0.30,
                    help="Fraction of app_screens to render (default 0.30)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Absolute screen count (overrides --fraction)")
    ap.add_argument("--cols", type=int, default=10,
                    help="Screens per row (default 10)")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for the screen sample (default 42)")
    ap.add_argument("--sequential", action="store_true",
                    help="Take the first N screens in id order "
                         "instead of a random sample")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Skip screens that already have a walk-grid "
                         "output (successful previous render). Used to "
                         "retry only the failures from an earlier sweep.")
    args = ap.parse_args()

    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    WALKS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    all_screens = [
        (r[0], r[1]) for r in conn.execute(
            "SELECT id, name FROM screens "
            "WHERE screen_type='app_screen' ORDER BY id"
        ).fetchall()
    ]
    conn.close()

    count = args.limit or max(1, int(round(len(all_screens) * args.fraction)))
    if args.sequential:
        sample = all_screens[:count]
    else:
        rng = random.Random(args.seed)
        sample = sorted(rng.sample(all_screens, count), key=lambda s: s[0])

    print(
        f"Grid-rendering {len(sample)}/{len(all_screens)} app_screens "
        f"(cols={args.cols}, col_stride={COL_STRIDE}, "
        f"row_stride={ROW_STRIDE}, port={args.port})",
        flush=True,
    )

    ok = 0
    walk_fails = 0
    gen_fails = 0
    t0 = time.time()

    for i, (sid, name) in enumerate(sample, 1):
        col = (i - 1) % args.cols
        row = (i - 1) // args.cols
        cx = col * COL_STRIDE
        cy = row * ROW_STRIDE

        script_p = SCRIPTS_DIR / f"{sid}.js"
        walk_p = WALKS_DIR / f"{sid}.json"

        if args.skip_existing and walk_p.exists() and walk_p.stat().st_size > 0:
            ok += 1
            print(
                f"[{i}/{len(sample)}] sid={sid:3d} SKIP       "
                f"@({cx},{cy})  (already rendered)",
                flush=True,
            )
            continue

        t1 = time.time()

        # Generate (Option B is the default post-M5b)
        gen = subprocess.run(
            [
                "python3", "-m", "dd", "generate",
                "--db", str(DB_PATH), "--screen", str(sid),
                "--canvas-x", str(cx),
                "--canvas-y", str(cy),
            ],
            capture_output=True, text=True, timeout=GENERATE_TIMEOUT,
        )
        if gen.returncode != 0 or not gen.stdout.strip():
            gen_fails += 1
            print(
                f"[{i}/{len(sample)}] sid={sid:3d} GEN-FAIL "
                f"{gen.stderr[:160]!r}",
                flush=True,
            )
            continue
        script_p.write_text(gen.stdout)

        # Execute via non-wiping grid wrapper — frames persist on
        # the "Option-B-Grid" page at the (cx, cy) the script
        # encoded.
        walk = subprocess.run(
            [
                "node", str(GRID_EXECUTOR),
                str(script_p), str(walk_p), args.port,
            ],
            capture_output=True, text=True, timeout=WALK_TIMEOUT,
        )
        elapsed = time.time() - t1
        status = "OK" if walk.returncode == 0 else "WALK-FAIL"
        if walk.returncode != 0:
            walk_fails += 1
        else:
            ok += 1
        print(
            f"[{i}/{len(sample)}] sid={sid:3d} {status:9s} "
            f"t={elapsed:5.1f}s  @({cx},{cy})  {name[:40]}",
            flush=True,
        )

    total_elapsed = time.time() - t0
    print(f"\n=== SUMMARY ===")
    print(f"Rendered:   {ok}/{len(sample)}")
    print(f"Walk-fail:  {walk_fails}")
    print(f"Gen-fail:   {gen_fails}")
    print(f"Elapsed:    {total_elapsed:.1f}s")
    print(f"\nInspect the current Figma page — frames are laid out "
          f"in a {args.cols}-wide grid starting at (0, 0).")
    return 0 if (walk_fails == 0 and gen_fails == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
