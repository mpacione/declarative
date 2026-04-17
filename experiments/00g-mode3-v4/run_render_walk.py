"""Exp 00g-mode3-v4 — render + walk pass (picks up where parse+compose left off).

Reads each ``artefacts/NN-slug/component_list.json`` (already generated
by ``run_parse_compose.py``), re-runs ``generate_from_prompt`` to emit
``script.js``, then drives ``render_test/run.js`` + ``walk_ref.js``
against the Figma bridge on port 9231 to produce ``render_result.json``,
``rendered_node_id.txt``, and ``walk.json``.

This is the second half of Step 5 — the Haiku-observable part already
landed in ``run_parse_compose.py``; this script needs the Figma
bridge. Same subprocess pattern as ``experiments/00f-mode3-v3/
run_experiment.py``.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

from dd.compose import generate_from_prompt
from dd.db import get_connection


EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
SUMMARY = EXP_ROOT / "render_walk_summary.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"
RUN_JS = REPO_ROOT / "render_test" / "run.js"
WALK_JS = REPO_ROOT / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9231"

SLUGS = (
    "01-login", "02-profile-settings", "03-meme-feed", "04-dashboard",
    "05-paywall", "06-spa-minimal", "07-search", "08-explicit-structure",
    "09-drawer-nav", "10-onboarding-carousel", "11-vague", "12-round-trip-test",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _log(slug: str, stage: str, status: str, detail: str) -> None:
    line = f"{_now()} | {slug} | {stage} | {status} | {detail}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def _run_node(cmd: list[str], timeout: int = 180) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "latency_s": time.time() - t0,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "latency_s": time.time() - t0,
            "timeout": True,
        }


def _parse_run_result(stdout: str) -> dict | None:
    """run.js emits `[name] OK in Nms: {"type":"PROXY_EXECUTE_RESULT",
    ...,"result":{"success":true,"result":{"__ok":true, ...}}}`.

    00f hit this same parse-too-shallow bug (see
    ``experiments/00f-mode3-v3/run_walks_and_finalize.py`` header) —
    fix here at source: unwrap to the inner ``result.result`` payload
    where ``__ok`` / ``errors`` actually live.
    """
    for line in stdout.splitlines():
        idx = line.find("OK in")
        if idx == -1:
            continue
        jidx = line.find("{", idx)
        if jidx == -1:
            continue
        try:
            outer = json.loads(line[jidx:])
        except Exception:  # noqa: BLE001
            return None
        if (
            isinstance(outer, dict)
            and outer.get("type") == "PROXY_EXECUTE_RESULT"
            and isinstance(outer.get("result"), dict)
            and isinstance(outer["result"].get("result"), dict)
        ):
            return outer["result"]["result"]
        return outer
    return None


def process_slug(slug: str, conn) -> dict:
    out = ARTEFACTS / slug
    cl_path = out / "component_list.json"
    if not cl_path.exists():
        _log(slug, "driver", "skip", "no component_list.json")
        return {"slug": slug, "status": "no_component_list"}

    cl = json.loads(cl_path.read_text())
    summary: dict = {"slug": slug}

    # Handle the clarification-refusal case
    if isinstance(cl, dict):
        _log(slug, "render", "skip", "clarification_refusal")
        summary["status"] = "clarification_refusal"
        return summary

    # If component_list is empty, nothing to render
    if not cl:
        _log(slug, "render", "skip", "empty component list")
        summary["status"] = "empty"
        return summary

    # Step 1: re-compose to get script.js (deterministic given same
    # component_list + DB state)
    try:
        t0 = time.time()
        result = generate_from_prompt(conn, cl, page_name=None)
        script = result["structure_script"]
        (out / "script.js").write_text(script)
        (out / "warnings.json").write_text(
            json.dumps(result.get("warnings", []), indent=2)
        )
        summary["compose"] = {
            "element_count": result.get("element_count", 0),
            "warnings": len(result.get("warnings", [])),
            "latency_ms": int((time.time() - t0) * 1000),
        }
        _log(slug, "compose", "ok", f"elements={summary['compose']['element_count']}")
    except Exception as e:  # noqa: BLE001
        _log(slug, "compose", "fail", str(e)[:200])
        summary["compose_error"] = str(e)
        return summary

    # Step 2: render
    script_path = out / "script.js"
    _log(slug, "render", "start", "")
    render_proc = _run_node(
        ["node", str(RUN_JS), str(script_path), BRIDGE_PORT],
        timeout=120,
    )
    render_data = _parse_run_result(render_proc["stdout"])
    render_result = {
        "returncode": render_proc["returncode"],
        "latency_ms": int(render_proc["latency_s"] * 1000),
        "timeout": render_proc["timeout"],
        "stdout": render_proc["stdout"][-2000:],
        "stderr": render_proc["stderr"][-2000:],
        "parsed": render_data,
    }
    (out / "render_result.json").write_text(json.dumps(render_result, indent=2))

    render_errors = (render_data or {}).get("errors") or []
    render_ok = (
        render_proc["returncode"] == 0
        and render_data
        and render_data.get("__ok") is True
    )
    summary["render"] = {
        "status": "ok" if render_ok else "fail",
        "latency_ms": render_result["latency_ms"],
        "errors_count": len(render_errors),
        "error_kinds": sorted({
            (e.get("kind") if isinstance(e, dict) else "unknown")
            for e in render_errors
        }),
    }
    _log(
        slug, "render", "ok" if render_ok else "fail",
        f"errors={len(render_errors)} kinds={summary['render']['error_kinds']}",
    )

    if not render_ok:
        (out / "FAILURE.md").write_text(
            "# Failure at render stage\n\n"
            f"returncode={render_proc['returncode']} "
            f"timeout={render_proc['timeout']}\n\n"
            "## stderr tail\n```\n"
            f"{render_proc['stderr'][-2000:]}\n```\n\n"
            "## stdout tail\n```\n"
            f"{render_proc['stdout'][-2000:]}\n```\n"
            f"\n## parsed\n```json\n{json.dumps(render_data, indent=2)}\n```\n"
        )
        return summary

    # Step 3: walk
    walk_path = out / "walk.json"
    _log(slug, "walk", "start", "")
    walk_proc = _run_node(
        ["node", str(WALK_JS), str(script_path), str(walk_path), BRIDGE_PORT],
        timeout=240,
    )
    walk_ok = walk_proc["returncode"] == 0 and walk_path.exists()
    summary["walk"] = {
        "status": "ok" if walk_ok else "fail",
        "latency_ms": int(walk_proc["latency_s"] * 1000),
    }
    if walk_ok:
        try:
            walk_data = json.loads(walk_path.read_text())
            eid_count = len(walk_data.get("eid_map", {}))
            rendered_root = walk_data.get("rendered_root") or ""
            (out / "rendered_node_id.txt").write_text(rendered_root + "\n")
            summary["walk"]["eid_count"] = eid_count
            summary["walk"]["rendered_root"] = rendered_root
            _log(slug, "walk", "ok", f"eids={eid_count} root={rendered_root}")
        except Exception as e:  # noqa: BLE001
            _log(slug, "walk", "warn", f"post-parse failed: {e}")
    else:
        _log(
            slug, "walk", "fail",
            f"rc={walk_proc['returncode']} stderr={walk_proc['stderr'][:200]}",
        )

    return summary


def main() -> None:
    with open(ACTIVITY_LOG, "a") as f:
        f.write(f"\n{_now()} | _ | render_walk | start | \n")

    conn = get_connection(str(DB_PATH))
    summaries: list[dict] = []
    t_start = time.time()
    for slug in SLUGS:
        try:
            s = process_slug(slug, conn)
        except Exception as e:  # noqa: BLE001
            _log(slug, "driver", "fail", str(e)[:200])
            s = {"slug": slug, "driver_error": str(e)}
        summaries.append(s)
        SUMMARY.write_text(json.dumps(summaries, indent=2))
    conn.close()

    ok = sum(1 for s in summaries if s.get("render", {}).get("status") == "ok")
    elapsed = time.time() - t_start
    _log("_", "done", "ok", f"render_ok={ok}/{len(SLUGS)} elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    main()
