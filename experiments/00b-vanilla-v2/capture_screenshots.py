"""Capture a screenshot per prompt by re-rendering through walk_ref.js.

walk_ref.js clears the Generated Test page, renders the script, and walks —
so after each call the rendered root is the only node on the page and
still accessible by the id in rendered_node_id.txt.

Capture via the figma_capture_screenshot MCP by writing a helper script
the main session can call. We just orchestrate the render here and save
node ids to a manifest the main session picks up.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
REPO_ROOT = Path(__file__).resolve().parents[2]
WALK_JS = REPO_ROOT / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9231"
SCREENSHOT_MANIFEST = EXP_ROOT / "screenshot_manifest.json"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log(slug: str, stage: str, status: str, detail: str) -> None:
    line = f"{now()} | {slug} | {stage} | {status} | {detail}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def main() -> None:
    manifest = []
    slugs = sorted(d.name for d in ARTEFACTS.iterdir() if d.is_dir())
    for slug in slugs:
        out_dir = ARTEFACTS / slug
        script = out_dir / "script.js"
        walk_path = out_dir / "walk.json"
        if not script.exists():
            continue
        log(slug, "prerender", "start", "")
        t0 = time.time()
        proc = subprocess.run(
            ["node", str(WALK_JS), str(script), str(walk_path), BRIDGE_PORT],
            capture_output=True, text=True, timeout=240, cwd=str(REPO_ROOT),
        )
        dt = int((time.time() - t0) * 1000)
        if proc.returncode != 0:
            log(slug, "prerender", "fail", proc.stderr[:200])
            manifest.append({"slug": slug, "status": "fail", "stderr": proc.stderr[:200]})
            continue

        walk_data = json.loads(walk_path.read_text())
        node_id = walk_data.get("rendered_root") or ""
        (out_dir / "rendered_node_id.txt").write_text(node_id + "\n")
        manifest.append({
            "slug": slug,
            "status": "ok",
            "node_id": node_id,
            "screenshot_path": str((out_dir / "screenshot.png").resolve()),
            "latency_ms": dt,
        })
        log(slug, "prerender", "ok", f"node_id={node_id} ms={dt}")
        SCREENSHOT_MANIFEST.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
