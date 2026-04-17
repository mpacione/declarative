"""Exp 00i-breadth-v1 — generalisation test beyond the canonical 12.

Goal: after v0.1.5's R3 hit 12/12 VLM-ok on the canonical 00g
prompts, confirm the same pipeline holds on 20 new, diverse prompts
that the team has NOT curated. If R3 overfits to the canonical 12,
this is where we find out.

Prompts span domains the canonical set misses:
- E-commerce (cart, product detail, pricing comparison)
- Messaging (chat, contacts)
- Productivity (calendar, multi-step form, filter panel)
- Media (video player, photo gallery)
- Location (map)
- Auth (signup, password reset, 2FA)
- System states (error, success, notifications, activity)

Same driver shape as experiments/00h-mode3-v5/run_experiment.py —
A1 archetype injection + A2 plan-then-fill flag OFF.
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

# 20 prompts across domains not covered by the canonical 12.
PROMPTS: tuple[tuple[str, str], ...] = (
    # E-commerce (3)
    ("01-shopping-cart", "a shopping cart with 3 items showing product image, name, price, quantity selector, and a checkout button"),
    ("02-product-detail", "an e-commerce product detail page with image gallery, title, price, size selector, add to cart button, and reviews"),
    ("03-pricing-compare", "a pricing comparison table with 4 columns (Free, Pro, Team, Enterprise) and feature rows"),
    # Messaging (2)
    ("04-chat-thread", "a chat conversation with message bubbles alternating between me and a contact, plus a composer at the bottom"),
    ("05-contact-list", "a contact list with avatars, names, last seen time, and an online status indicator"),
    # Productivity (3)
    ("06-calendar-day", "a calendar day view with hourly time slots and 3 colored event blocks"),
    ("07-event-detail", "an event detail page with title, date, location, description, attendees, and RSVP buttons"),
    ("08-multi-step-form", "a multi-step signup form with progress indicator, current step fields, and next and back buttons"),
    # System (3)
    ("09-filter-panel", "a filter panel with category checkboxes, price range slider, and a clear filters button"),
    ("10-notifications", "a notification center with grouped alerts each showing icon, title, and timestamp"),
    ("11-activity-history", "an activity history list grouped by date, each activity showing icon, description, and time"),
    # Auth flow (3)
    ("12-signup-form", "a signup form with name, email, password, confirm password, and terms checkbox"),
    ("13-password-reset", "a password reset screen with email input and a send reset link button"),
    ("14-2fa-verify", "a 2FA verification screen with a 6-digit code input and a resend link"),
    # Media (2)
    ("15-video-player", "a video player screen with play controls, progress bar, and a related videos list below"),
    ("16-photo-gallery", "a photo gallery grid with thumbnails and a floating action button"),
    # Location (1)
    ("17-map-screen", "a map screen with a search bar at the top and location cards at the bottom"),
    # Status screens (3)
    ("18-error-state", "an error state screen with illustration, apology message, and a retry button"),
    ("19-success-confirm", "a success confirmation screen with checkmark, message, and continue button"),
    ("20-file-upload", "a file upload page with drag-and-drop area, file list with progress bars, and upload all button"),
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
    """Unwrap PROXY_EXECUTE_RESULT — feedback_proxy_execute_parse_depth."""
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

    # Stage 1: parse + compose via prompt_to_figma (A1 live, A2 flag off)
    from dd.prompt_parser import prompt_to_figma
    t0 = time.time()
    try:
        result = prompt_to_figma(prompt, conn, client, page_name=None)
    except Exception as e:  # noqa: BLE001
        _log(slug, "prompt_to_figma", "fail", str(e)[:200])
        summary["error"] = str(e)
        return summary
    summary["prompt_to_figma_latency_s"] = round(time.time() - t0, 2)

    # Persist the archetype classifier picked
    from dd.composition.archetype_classifier import classify_archetype
    matched = classify_archetype(prompt, client=client)
    (out / "classified_archetype.txt").write_text(f"{matched or 'none'}\n")
    summary["archetype"] = matched or "none"

    components = result.get("components") or []
    (out / "component_list.json").write_text(json.dumps(components, indent=2))
    summary["component_count"] = len(components) if isinstance(components, list) else 0

    if result.get("clarification_refusal"):
        _log(slug, "parse", "refusal", result["clarification_refusal"][:80])
        summary["kind"] = "KIND_PROMPT_UNDERSPECIFIED"
        return summary

    script = result.get("structure_script")
    if not script:
        _log(slug, "compose", "fail", "no structure_script")
        summary["error"] = "no structure_script"
        return summary

    (out / "script.js").write_text(script)
    (out / "ir.json").write_text(json.dumps(result.get("spec") or {}, indent=2))
    (out / "warnings.json").write_text(json.dumps(result.get("warnings", []), indent=2))
    summary["element_count"] = result.get("element_count", 0)
    summary["warnings"] = len(result.get("warnings", []))
    _log(
        slug, "parse_compose", "ok",
        f"archetype={matched} components={summary['component_count']} elements={summary['element_count']}",
    )

    # Stage 2: render
    script_path = out / "script.js"
    render_proc = _run_node(
        ["node", str(RUN_JS), str(script_path), BRIDGE_PORT],
        timeout=90,
    )
    render_data = _parse_run_result(render_proc["stdout"])
    render_ok = (
        render_proc["returncode"] == 0
        and render_data
        and render_data.get("__ok") is True
    )
    (out / "render_result.json").write_text(json.dumps({
        "returncode": render_proc["returncode"],
        "latency_ms": int(render_proc["latency_s"] * 1000),
        "timeout": render_proc["timeout"],
        "stdout": render_proc["stdout"][-2000:],
        "stderr": render_proc["stderr"][-2000:],
        "parsed": render_data,
    }, indent=2))
    render_errors = (render_data or {}).get("errors") or []
    summary["render"] = {
        "status": "ok" if render_ok else "fail",
        "latency_ms": int(render_proc["latency_s"] * 1000),
        "errors_count": len(render_errors),
    }
    _log(
        slug, "render", "ok" if render_ok else "fail",
        f"errors={len(render_errors)} latency={summary['render']['latency_ms']}ms",
    )
    if not render_ok:
        return summary

    # Stage 3: walk
    walk_path = out / "walk.json"
    walk_proc = _run_node(
        ["node", str(WALK_JS), str(script_path), str(walk_path), BRIDGE_PORT],
        timeout=180,
    )
    walk_ok = walk_proc["returncode"] == 0 and walk_path.exists()
    summary["walk"] = {
        "status": "ok" if walk_ok else "fail",
        "latency_ms": int(walk_proc["latency_s"] * 1000),
    }
    if walk_ok:
        walk_data = json.loads(walk_path.read_text())
        (out / "rendered_node_id.txt").write_text((walk_data.get("rendered_root") or "") + "\n")
        summary["walk"]["eid_count"] = len(walk_data.get("eid_map", {}))
        _log(slug, "walk", "ok", f"eids={summary['walk']['eid_count']}")
    else:
        _log(slug, "walk", "fail", "")
    return summary


def main() -> None:
    ACTIVITY_LOG.write_text("")
    ARTEFACTS.mkdir(exist_ok=True)
    _log("_", "setup", "ok", f"db={DB_PATH} n_prompts={len(PROMPTS)}")

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
    errored = sum(1 for s in summaries if s.get("error"))
    elapsed = time.time() - t_start
    _log(
        "_", "done", "ok",
        f"render_ok={ok}/{len(PROMPTS)} refused={refused} errored={errored} "
        f"elapsed={elapsed:.1f}s",
    )


if __name__ == "__main__":
    main()
