"""Exp 00b — vanilla baseline v2 (re-run on fixed pipeline).

Runs each of the 12 prescribed prompts through:
  1. prompt_parser.parse_prompt (Claude Haiku)
  2. compose.generate_from_prompt (IR + script)
  3. render_test/run.js (bridge execution)
  4. render_test/walk_ref.js (rendered-subtree walk)

Produces artefacts/NN-slug/ per prompt plus activity.log + run_summary.json.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

from anthropic import Anthropic

from dd.db import get_connection
from dd.prompt_parser import (
    SYSTEM_PROMPT,
    build_project_vocabulary,
    parse_prompt,
)
from dd.compose import generate_from_prompt
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context
from dd.templates import build_component_key_registry, extract_templates

EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
RUN_SUMMARY = EXP_ROOT / "run_summary.json"
DB_PATH = Path(__file__).resolve().parents[2] / "Dank-EXP-02.declarative.db"
REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_JS = REPO_ROOT / "render_test" / "run.js"
WALK_JS = REPO_ROOT / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9231"

PROMPTS = [
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
]


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log(slug: str, stage: str, status: str, detail: str) -> None:
    line = f"{now()} | {slug} | {stage} | {status} | {detail}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def build_system_prompt(conn: sqlite3.Connection) -> str:
    """Build the exact system prompt the pipeline injects."""
    system = SYSTEM_PROMPT
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    if file_row:
        file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
        archetypes = extract_screen_archetypes(conn, file_id)
        archetype_context = get_archetype_prompt_context(archetypes)
        if archetype_context:
            system = system + "\n\n" + archetype_context
    vocabulary_context = build_project_vocabulary(conn)
    if vocabulary_context:
        system = system + "\n\n" + vocabulary_context
    return system


def raw_llm_call(prompt: str, client: Anthropic, system: str) -> tuple[str, dict]:
    """Raw call — returns (response_text, usage_dict)."""
    t0 = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    dt = time.time() - t0
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_s": dt,
        "stop_reason": response.stop_reason,
    }
    return response.content[0].text, usage


def run_node_cmd(cmd: list[str], timeout: int = 180) -> dict:
    """Run a node subprocess, capture result."""
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT))
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


def parse_run_result(stdout: str) -> dict | None:
    """run.js emits `[name] OK in Nms: { "__ok": true, ... }` on success."""
    for line in stdout.splitlines():
        idx = line.find("OK in")
        if idx == -1:
            continue
        jidx = line.find("{", idx)
        if jidx == -1:
            continue
        try:
            return json.loads(line[jidx:])
        except Exception:
            return None
    return None


def process_prompt(slug: str, prompt: str, client: Anthropic, conn: sqlite3.Connection, system: str) -> dict:
    """Drive a single prompt end-to-end. Returns per-prompt summary."""
    out_dir = ARTEFACTS / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict = {"slug": slug, "prompt": prompt, "stages": {}}

    # Save the prompt verbatim
    (out_dir / "prompt.txt").write_text(prompt + "\n")

    # Stage 1: LLM parse
    log(slug, "parse", "start", f"len={len(prompt)}")
    try:
        raw_text, usage = raw_llm_call(prompt, client, system)
        (out_dir / "llm_raw_response.txt").write_text(raw_text)
        summary["stages"]["parse"] = {"status": "ok", **usage}

        from dd.prompt_parser import extract_json
        components = extract_json(raw_text)
        (out_dir / "component_list.json").write_text(json.dumps(components, indent=2))
        summary["component_count"] = len(components)
        log(slug, "parse", "ok", f"components={len(components)} in_tokens={usage['input_tokens']} out_tokens={usage['output_tokens']}")
    except Exception as e:
        log(slug, "parse", "fail", str(e)[:200])
        summary["stages"]["parse"] = {"status": "fail", "error": str(e)}
        (out_dir / "FAILURE.md").write_text(f"# Failure at parse stage\n\n{e}\n")
        return summary

    # Stage 2: compose + generate script
    log(slug, "compose", "start", f"components={len(components)}")
    try:
        t0 = time.time()
        result = generate_from_prompt(conn, components, page_name=None)
        compose_ms = int((time.time() - t0) * 1000)
        spec = result["spec"]
        script = result["structure_script"]
        warnings = result.get("warnings", [])
        token_refs = result.get("token_refs", {})

        (out_dir / "ir.json").write_text(json.dumps(spec, indent=2))
        (out_dir / "script.js").write_text(script)
        (out_dir / "warnings.json").write_text(json.dumps(warnings, indent=2))
        (out_dir / "token_refs.json").write_text(json.dumps(token_refs, indent=2))

        summary["stages"]["compose"] = {
            "status": "ok",
            "elements": result["element_count"],
            "warnings": len(warnings),
            "token_refs": len(token_refs) if isinstance(token_refs, (list, dict)) else 0,
            "script_chars": len(script),
            "latency_ms": compose_ms,
        }
        log(slug, "compose", "ok",
            f"elements={result['element_count']} script_chars={len(script)} warnings={len(warnings)}")
    except Exception as e:
        log(slug, "compose", "fail", str(e)[:200])
        summary["stages"]["compose"] = {"status": "fail", "error": str(e)}
        (out_dir / "FAILURE.md").write_text(f"# Failure at compose stage\n\n{e}\n")
        return summary

    # Stage 3: render via run.js
    script_path = out_dir / "script.js"
    log(slug, "render", "start", "")
    render_proc = run_node_cmd(
        ["node", str(RUN_JS), str(script_path), BRIDGE_PORT],
        timeout=120,
    )
    render_data = parse_run_result(render_proc["stdout"])
    render_result = {
        "returncode": render_proc["returncode"],
        "latency_ms": int(render_proc["latency_s"] * 1000),
        "timeout": render_proc["timeout"],
        "stdout": render_proc["stdout"],
        "stderr": render_proc["stderr"][-2000:] if render_proc["stderr"] else "",
        "parsed": render_data,
    }
    (out_dir / "render_result.json").write_text(json.dumps(render_result, indent=2))

    render_errors = (render_data or {}).get("errors") or []
    render_ok = render_proc["returncode"] == 0 and render_data and render_data.get("__ok") is True
    summary["stages"]["render"] = {
        "status": "ok" if render_ok else "fail",
        "latency_ms": render_result["latency_ms"],
        "errors_count": len(render_errors),
        "error_kinds": sorted({(e.get("kind") if isinstance(e, dict) else "unknown") for e in render_errors}),
        "before": render_data.get("before") if render_data else None,
        "after": render_data.get("after") if render_data else None,
    }
    log(slug, "render", "ok" if render_ok else "fail",
        f"errors={len(render_errors)} kinds={summary['stages']['render']['error_kinds']}")

    if not render_ok:
        (out_dir / "FAILURE.md").write_text(
            "# Failure at render stage\n\n"
            f"returncode={render_proc['returncode']} timeout={render_proc['timeout']}\n\n"
            "## stderr tail\n```\n"
            f"{render_proc['stderr'][-2000:]}\n```\n\n"
            "## stdout tail\n```\n"
            f"{render_proc['stdout'][-2000:]}\n```\n"
            f"\n## parsed\n```json\n{json.dumps(render_data, indent=2)}\n```\n"
        )
        return summary

    # Stage 4: walk via walk_ref.js
    walk_path = out_dir / "walk.json"
    log(slug, "walk", "start", "")
    walk_proc = run_node_cmd(
        ["node", str(WALK_JS), str(script_path), str(walk_path), BRIDGE_PORT],
        timeout=240,
    )
    walk_ok = walk_proc["returncode"] == 0 and walk_path.exists()
    summary["stages"]["walk"] = {
        "status": "ok" if walk_ok else "fail",
        "latency_ms": int(walk_proc["latency_s"] * 1000),
    }
    if walk_ok:
        try:
            walk_data = json.loads(walk_path.read_text())
            eid_count = len(walk_data.get("eid_map", {}))
            rendered_root = walk_data.get("rendered_root") or ""
            (out_dir / "rendered_node_id.txt").write_text(rendered_root + "\n")
            summary["stages"]["walk"]["eid_count"] = eid_count
            summary["stages"]["walk"]["rendered_root"] = rendered_root
            # Vector-missing count mechanical pattern
            vec_missing = sum(
                1 for e in walk_data.get("eid_map", {}).values()
                if e.get("type") in ("VECTOR", "BOOLEAN_OPERATION")
                and (e.get("fillGeometryCount") or 0) == 0
                and (e.get("strokeGeometryCount") or 0) == 0
            )
            zero_dim = sum(
                1 for e in walk_data.get("eid_map", {}).values()
                if (e.get("width") or 0) == 0 or (e.get("height") or 0) == 0
            )
            summary["stages"]["walk"]["missing_vectors"] = vec_missing
            summary["stages"]["walk"]["zero_dim_nodes"] = zero_dim
            log(slug, "walk", "ok",
                f"eids={eid_count} missing_vectors={vec_missing} zero_dim={zero_dim}")
        except Exception as e:
            log(slug, "walk", "warn", f"post-parse failed: {e}")
    else:
        log(slug, "walk", "fail", f"rc={walk_proc['returncode']} stderr={walk_proc['stderr'][:200]}")

    # Per-prompt notes.md (mechanical observations only)
    notes_lines = [f"# Notes — {slug}\n"]
    notes_lines.append(f"Prompt: `{prompt}`\n")
    notes_lines.append(f"\n## Pipeline completion\n")
    for stage in ("parse", "compose", "render", "walk"):
        s = summary["stages"].get(stage, {})
        notes_lines.append(f"- {stage}: {s.get('status', 'not-run')}")
    notes_lines.append("")

    if render_data and render_errors:
        notes_lines.append(f"\n## Structured errors ({len(render_errors)})\n")
        for e in render_errors[:20]:
            kind = e.get("kind") if isinstance(e, dict) else None
            eid = e.get("eid") if isinstance(e, dict) else None
            msg = e.get("message") if isinstance(e, dict) else None
            notes_lines.append(f"- kind={kind} eid={eid} msg={str(msg)[:160]}")

    if walk_ok and walk_path.exists():
        walk_data = json.loads(walk_path.read_text())
        eids = walk_data.get("eid_map", {})
        notes_lines.append(f"\n## Walk summary\n- rendered_root: `{walk_data.get('rendered_root')}`\n- eid_count: {len(eids)}")
        # Type distribution
        from collections import Counter
        type_ct = Counter(e.get("type") for e in eids.values())
        notes_lines.append(f"- type distribution: {dict(type_ct)}")
        # Zero-dim
        zero_dim = [k for k, v in eids.items() if (v.get("width") or 0) == 0 or (v.get("height") or 0) == 0]
        if zero_dim:
            notes_lines.append(f"- **zero-dimension nodes:** {len(zero_dim)} — {zero_dim[:10]}")
        # Missing vector assets
        vec_miss = [k for k, v in eids.items() if v.get("type") in ("VECTOR", "BOOLEAN_OPERATION")
                    and (v.get("fillGeometryCount") or 0) == 0 and (v.get("strokeGeometryCount") or 0) == 0]
        if vec_miss:
            notes_lines.append(f"- **missing vector assets:** {len(vec_miss)} — {vec_miss[:10]}")
        # Tiny text detection: textAutoResize + 0 width
        tiny_text = [k for k, v in eids.items() if v.get("type") == "TEXT" and ((v.get("width") or 0) < 2)]
        if tiny_text:
            notes_lines.append(f"- tiny text nodes (<2px wide): {len(tiny_text)}")

    (out_dir / "notes.md").write_text("\n".join(notes_lines))

    return summary


def main() -> None:
    ACTIVITY_LOG.write_text("")  # fresh log
    ARTEFACTS.mkdir(exist_ok=True)

    # Build the system prompt once and persist for reproducibility
    conn = get_connection(str(DB_PATH))
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    if file_row:
        file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
        build_component_key_registry(conn)
        extract_templates(conn, file_id)
    system = build_system_prompt(conn)
    (EXP_ROOT / "system_prompt.txt").write_text(system)
    log("_", "setup", "ok", f"system_prompt_chars={len(system)} db={DB_PATH}")

    client = Anthropic()
    all_summaries = []
    for slug, prompt in PROMPTS:
        try:
            summary = process_prompt(slug, prompt, client, conn, system)
        except Exception as e:
            log(slug, "prompt_driver", "fail", str(e)[:200])
            summary = {"slug": slug, "prompt": prompt, "error": str(e)}
        all_summaries.append(summary)
        RUN_SUMMARY.write_text(json.dumps(all_summaries, indent=2))

    conn.close()
    log("_", "done", "ok", f"count={len(all_summaries)}")


if __name__ == "__main__":
    main()
