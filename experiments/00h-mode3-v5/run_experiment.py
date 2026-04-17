"""Exp 00h-mode3-v5 — A2 plan-then-fill LIVE, full pipeline.

v0.1.5 Week 2 Step 6e. 12 canonical prompts → plan-then-fill (A2) →
compose → render (bridge :9231) → walk → screenshot → VLM gate.
Compare vs 00g baseline (A1-only, 6/12 VLM-ok).

Sets ``DD_ENABLE_PLAN_THEN_FILL=1`` before driving ``prompt_to_figma``
so the full wiring exercises in-band exactly as production will see it.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from anthropic import Anthropic


EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
SUMMARY = EXP_ROOT / "run_summary.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"
RUN_JS = REPO_ROOT / "render_test" / "run.js"
WALK_JS = REPO_ROOT / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9231"

PROMPTS = (
    ("01-login", "a login screen with email, password, and a sign-in button"),
    ("02-profile-settings", "a profile settings page with avatar, name, email, notification toggles, and a save button"),
    ("03-meme-feed", "a feed of memes with upvote and share buttons under each"),
    ("04-dashboard", "a data dashboard with a line chart and a table of recent transactions"),
    ("05-paywall", "a paywall screen with three pricing tiers and a testimonial"),
    ("06-spa-minimal", "make something minimal and luxurious for a spa app"),
    ("07-search", "a search screen"),
    ("08-explicit-structure", "header with back button, title, share button. Then a card with a heading, 3 lines of body text, and a primary button. Then a secondary button below."),
    ("09-drawer-nav", "a drawer menu with 6 nav items"),
    ("10-onboarding-carousel", "an onboarding carousel with 3 slides, each with an illustration, headline, and subtext"),
    ("11-vague", "something cool"),
    ("12-round-trip-test", "rebuild iPhone 13 Pro Max - 109 from scratch"),
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
    """Unwrap PROXY_EXECUTE_RESULT — see feedback_proxy_execute_parse_depth."""
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


def process_prompt(slug: str, prompt: str, client: Anthropic, conn) -> dict:
    out = ARTEFACTS / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt + "\n")

    summary: dict = {"slug": slug, "prompt": prompt}

    # Stage 1 — plan + fill via prompt_to_figma
    from dd.prompt_parser import prompt_to_figma
    t0 = time.time()
    try:
        result = prompt_to_figma(prompt, conn, client, page_name=None)
    except Exception as e:  # noqa: BLE001
        _log(slug, "prompt_to_figma", "fail", str(e)[:200])
        summary["error"] = str(e)
        return summary
    summary["prompt_to_figma_latency_s"] = time.time() - t0

    # Persist key fields
    if result.get("plan") is not None:
        (out / "plan.json").write_text(json.dumps(result["plan"], indent=2))
    if "components" in result:
        (out / "component_list.json").write_text(
            json.dumps(result["components"], indent=2)
        )
    summary["component_count"] = len(result.get("components") or [])
    summary["plan_retried"] = result.get("plan_retried", False)

    if result.get("kind") == "KIND_PLAN_INVALID":
        _log(slug, "plan", "fail", f"KIND_PLAN_INVALID: {result.get('detail')}")
        summary["kind"] = "KIND_PLAN_INVALID"
        summary["detail"] = result.get("detail")
        return summary

    if result.get("clarification_refusal"):
        _log(slug, "plan", "refusal", result["clarification_refusal"][:80])
        summary["kind"] = "KIND_PROMPT_UNDERSPECIFIED"
        summary["refusal"] = result["clarification_refusal"][:2000]
        return summary

    script = result.get("structure_script")
    if not script:
        _log(slug, "compose", "fail", "no structure_script on result")
        summary["error"] = "no structure_script"
        return summary

    (out / "script.js").write_text(script)
    (out / "ir.json").write_text(json.dumps(result.get("spec") or {}, indent=2))
    (out / "warnings.json").write_text(json.dumps(result.get("warnings", []), indent=2))
    summary["element_count"] = result.get("element_count", 0)
    summary["warnings"] = len(result.get("warnings", []))

    _log(
        slug, "plan_fill_compose", "ok",
        f"components={summary['component_count']} "
        f"elements={summary['element_count']} "
        f"retried={summary['plan_retried']}",
    )

    # Stage 2 — render
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
    }
    _log(slug, "render", "ok" if render_ok else "fail", f"errors={len(render_errors)}")
    if not render_ok:
        return summary

    # Stage 3 — walk
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
            _log(slug, "walk", "ok", f"eids={eid_count}")
        except Exception as e:  # noqa: BLE001
            _log(slug, "walk", "warn", f"post-parse failed: {e}")
    return summary


def main() -> None:
    # v0.1.5 Week 2 — A2 plan-then-fill ON for this whole experiment
    os.environ["DD_ENABLE_PLAN_THEN_FILL"] = "1"

    ACTIVITY_LOG.write_text("")
    ARTEFACTS.mkdir(exist_ok=True)
    _log("_", "setup", "ok", f"DD_ENABLE_PLAN_THEN_FILL=1 db={DB_PATH}")

    from dd.db import get_connection
    conn = get_connection(str(DB_PATH))
    client = Anthropic()

    summaries: list[dict] = []
    t_start = time.time()
    for slug, prompt in PROMPTS:
        try:
            s = process_prompt(slug, prompt, client, conn)
        except Exception as e:  # noqa: BLE001
            _log(slug, "driver", "fail", str(e)[:200])
            s = {"slug": slug, "prompt": prompt, "driver_error": str(e)}
        summaries.append(s)
        SUMMARY.write_text(json.dumps(summaries, indent=2))

    conn.close()
    ok = sum(1 for s in summaries if s.get("render", {}).get("status") == "ok")
    refused = sum(1 for s in summaries if s.get("kind") == "KIND_PROMPT_UNDERSPECIFIED")
    invalid = sum(1 for s in summaries if s.get("kind") == "KIND_PLAN_INVALID")
    retried = sum(1 for s in summaries if s.get("plan_retried"))
    elapsed = time.time() - t_start
    _log(
        "_", "done", "ok",
        f"render_ok={ok}/12 refused={refused} plan_invalid={invalid} "
        f"fill_retried={retried} elapsed={elapsed:.1f}s",
    )


if __name__ == "__main__":
    main()
