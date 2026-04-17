"""Serially capture all sample screens via the Figma bridge.

Reads sample.csv, invokes capture.js per row with a small inter-call
delay to avoid hammering the bridge (Wave 1.5 may also be using it).
"""

import csv
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

EXP = Path("/Users/mattpacione/declarative-build/experiments/E-principles-induction")
SAMPLE_CSV = EXP / "sample.csv"
LOG = EXP / "activity.log"
CAPTURE_JS = EXP / "capture.js"
BRIDGE_PORT = 9231

INTER_CALL_SLEEP = 0.4  # seconds between captures; stay polite on shared bridge


def log(stage: str, status: str, detail: str = "") -> None:
    ts = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{ts} | {stage} | {status} | {detail}\n"
    LOG.open("a").write(line)
    print(line.rstrip())


def main() -> None:
    rows = list(csv.DictReader(SAMPLE_CSV.open()))
    log("capture", "begin", f"{len(rows)} screens via bridge port {BRIDGE_PORT}")

    for i, row in enumerate(rows, 1):
        sid = row["screen_id"]
        fnid = row["figma_node_id"]
        fpath = EXP / row["file_path"]
        if fpath.exists() and fpath.stat().st_size > 1000:
            log("capture", "skip", f"[{i}/{len(rows)}] screen_id={sid} already exists ({fpath.stat().st_size} bytes)")
            continue
        t0 = time.monotonic()
        proc = subprocess.run(
            ["node", str(CAPTURE_JS), fnid, str(fpath), str(BRIDGE_PORT)],
            capture_output=True, text=True, timeout=90,
        )
        dt_ms = int((time.monotonic() - t0) * 1000)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        status = "ok" if proc.returncode == 0 else "fail"
        try:
            blob = json.loads(stdout or stderr or "{}")
        except json.JSONDecodeError:
            blob = {"raw": stdout[-200:]}
        detail = f"[{i}/{len(rows)}] screen_id={sid} node={fnid} ms={dt_ms} size={fpath.stat().st_size if fpath.exists() else 0} " + json.dumps({"w": blob.get("width"), "h": blob.get("height"), "err": blob.get("error")})
        log("capture", status, detail)
        if proc.returncode != 0:
            # Try once more after brief cooldown; bridge hiccups are common
            time.sleep(1.5)
            proc2 = subprocess.run(
                ["node", str(CAPTURE_JS), fnid, str(fpath), str(BRIDGE_PORT)],
                capture_output=True, text=True, timeout=90,
            )
            if proc2.returncode == 0:
                log("capture", "ok-retry", f"screen_id={sid}")
            else:
                log("capture", "fail-final", f"screen_id={sid} stderr={proc2.stderr[-200:]}")
        time.sleep(INTER_CALL_SLEEP)

    log("capture", "end", "")


if __name__ == "__main__":
    main()
