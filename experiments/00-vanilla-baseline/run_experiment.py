"""Experiment 0 driver — vanilla baseline.

Runs the existing dd generate-prompt pipeline against 12 deliberately
varied prompts, collecting raw artefacts (component list, IR, script,
render result, rendered walk) per prompt. No quality rating — that's
for Wave 2.

Serialises renders through the Figma bridge (one at a time).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Make sure we can import dd
_REPO = Path("/Users/mattpacione/declarative-build")
sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv
load_dotenv(_REPO / ".env", override=True)

from dd.db import get_connection
from dd.prompt_parser import (
    SYSTEM_PROMPT,
    build_project_vocabulary,
    extract_json,
)
from dd.screen_patterns import (
    extract_screen_archetypes,
    get_archetype_prompt_context,
)
from dd.compose import generate_from_prompt
from dd.templates import build_component_key_registry, extract_templates

DB_PATH = _REPO / "Dank-EXP-02.declarative.db"
EXP_DIR = _REPO / "experiments" / "00-vanilla-baseline"
ARTEFACTS = EXP_DIR / "artefacts"
LOG = EXP_DIR / "activity.log"
BRIDGE_PORT = 9231
RUN_JS = _REPO / "render_test" / "run.js"
WALK_JS = _REPO / "render_test" / "walk_ref.js"

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


def log(slug: str, stage: str, status: str, detail: str = "") -> None:
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    line = f"{ts} | {slug} | {stage} | {status} | {detail}\n"
    with open(LOG, "a") as f:
        f.write(line)
    print(line.rstrip())


def find_node() -> str:
    import shutil
    n = shutil.which("node")
    if n:
        return n
    import glob as _g
    cands = _g.glob(str(Path.home() / ".nvm/versions/node/*/bin/node"))
    if cands:
        return sorted(cands)[-1]
    raise FileNotFoundError("node")


def parse_prompt_once(prompt_text: str, conn, client=None) -> tuple[list, str, int, str]:
    """Parser step.

    The original pipeline calls Claude Haiku 4.5 via the Anthropic SDK.
    On this machine the API key has 0 credits, so SDK calls fail
    hard. We fall back to a pre-baked parse from
    experiments/00-vanilla-baseline/parses/<slug>.json.

    The parses were produced offline by the experiment-driver agent
    using the SAME system prompt the pipeline builds. This is
    documented in the memo — parser behavior is substituted; compose,
    lowering, renderer, and verifier run unchanged.
    """
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    file_id = file_row[0] if file_row else None

    archetype_context = ""
    if file_id:
        archetypes = extract_screen_archetypes(conn, file_id)
        archetype_context = get_archetype_prompt_context(archetypes)

    vocabulary_context = build_project_vocabulary(conn)
    system = SYSTEM_PROMPT
    if archetype_context:
        system = system + "\n\n" + archetype_context
    if vocabulary_context:
        system = system + "\n\n" + vocabulary_context

    # Substituted parse: the driver (acting as LLM) populates this file
    # per slug; run_one() passes prompt_text through but we actually
    # key on slug. See parse_from_disk().
    raise NotImplementedError("use parse_from_disk() instead")


def parse_from_disk(slug: str) -> tuple[list, int, str]:
    """Read a pre-baked component list from the parses/ directory.

    Returns (components, parse_ms_substitute, raw_text). parse_ms is a
    synthetic wall-clock — the real Haiku call would add ~600ms;
    we record 0 to make the substitution obvious in the data.
    """
    p = EXP_DIR / "parses" / f"{slug}.json"
    if not p.exists():
        raise FileNotFoundError(f"no pre-baked parse for {slug} at {p}")
    text = p.read_text()
    components = json.loads(text)
    return components, 0, text


def run_render(script_path: Path, timeout: int = 120) -> dict:
    """Invoke render_test/run.js against the generated script. Returns
    the parsed JSON status line from stdout, plus raw stdout/stderr.
    """
    node = find_node()
    t0 = time.monotonic()
    proc = subprocess.run(
        [node, str(RUN_JS), str(script_path), str(BRIDGE_PORT)],
        capture_output=True, text=True, timeout=timeout,
    )
    dt_ms = int((time.monotonic() - t0) * 1000)

    result_line = None
    for line in proc.stdout.splitlines():
        # run.js prints `[name] OK in Nms: <json>` on success.
        # We want the JSON tail.
        if "] OK in" in line and ": " in line:
            _, _, tail = line.partition(": ")
            try:
                result_line = json.loads(tail.strip())
            except Exception:
                pass
        elif "] FAIL in" in line:
            result_line = {"__ok": False, "line": line}

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "parsed": result_line,
        "elapsed_ms": dt_ms,
    }


def run_walk(script_path: Path, out_path: Path, timeout: int = 200) -> dict:
    """Invoke render_test/walk_ref.js → writes walk.json and prints a
    status line. Note walk_ref.js CLEARS the page before running, so
    this replaces the render_test payload on the page.
    """
    node = find_node()
    t0 = time.monotonic()
    proc = subprocess.run(
        [node, str(WALK_JS), str(script_path), str(out_path), str(BRIDGE_PORT)],
        capture_output=True, text=True, timeout=timeout,
    )
    dt_ms = int((time.monotonic() - t0) * 1000)
    return {
        "ok": proc.returncode == 0 and out_path.exists(),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_ms": dt_ms,
    }


def derive_rendered_node_id(walk_payload: dict) -> str | None:
    if not isinstance(walk_payload, dict):
        return None
    return walk_payload.get("rendered_root")


def write_notes_md(
    out_dir: Path,
    slug: str,
    prompt: str,
    components: list,
    spec: dict,
    render: dict,
    walk: dict,
    walk_payload: dict | None,
    timings: dict,
) -> None:
    # Factual summary only, no quality rating.
    types_emitted: dict[str, int] = {}
    for el in (spec.get("elements") or {}).values():
        types_emitted[el.get("type", "?")] = types_emitted.get(el.get("type", "?"), 0) + 1

    # Extract the inner wrapper result from run.js. Shape is either
    # {__ok: true, before, after, moved, errors} on success or
    # {__phase: 'script_error', error, before, after} on failure.
    inner = (((render.get("parsed") or {}).get("result") or {}).get("result") or {})
    render_completed = isinstance(inner, dict) and inner.get("__ok") is True
    render_error = None if render_completed else (inner.get("error") if isinstance(inner, dict) else None)
    err_channel = []
    if isinstance(inner, dict):
        err_channel = inner.get("errors") or []

    kind_counts: dict[str, int] = {}
    for e in err_channel:
        k = (e or {}).get("kind", "?")
        kind_counts[k] = kind_counts.get(k, 0) + 1

    walk_errs = []
    walk_eid_count = 0
    vec_missing = 0
    if isinstance(walk_payload, dict):
        walk_errs = walk_payload.get("errors") or []
        walk_eid_count = len(walk_payload.get("eid_map") or {})
        for e in (walk_payload.get("eid_map") or {}).values():
            if e.get("type") in ("VECTOR", "BOOLEAN_OPERATION"):
                if not e.get("fillGeometryCount") and not e.get("strokeGeometryCount"):
                    vec_missing += 1

    lines = [
        f"# {slug} — automated notes",
        "",
        f"**Prompt:** {prompt}",
        "",
        f"- Components parsed from LLM: {len(components)}",
        f"- IR elements emitted: {len(spec.get('elements') or {})}",
        f"- Subprocess returncode: {render.get('returncode')} (this only tells us the Node harness exited cleanly)",
        f"- Render completed to end of script: {render_completed}",
        f"- Render top-level error: {render_error!r}",
        f"- Walk ok: {walk.get('ok')}",
        f"- Walk eid_map size: {walk_eid_count}",
        f"- Render-channel __errors count: {len(err_channel)}",
        f"- Walk-channel errors count: {len(walk_errs)}",
        f"- Vector assets with 0 fill+stroke geometry: {vec_missing}",
        f"- KIND_* counts (render): {json.dumps(kind_counts)}",
        "",
        "### Type frequency (from IR spec)",
    ]
    for t, n in sorted(types_emitted.items(), key=lambda x: -x[1]):
        lines.append(f"- {t}: {n}")

    lines += [
        "",
        "### Timings (ms)",
        f"- parse: {timings.get('parse_ms')}  (substituted — real Haiku call is bypassed; see memo.md)",
        f"- compose (build IR + script): {timings.get('compose_ms')}",
        f"- render: {timings.get('render_ms')}",
        f"- walk: {timings.get('walk_ms')}",
    ]

    (out_dir / "notes.md").write_text("\n".join(lines) + "\n")


def run_one(slug: str, prompt: str, conn, client) -> dict:
    out_dir = ARTEFACTS / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.txt").write_text(prompt + "\n")
    log(slug, "start", "begin", f"out_dir={out_dir}")

    timings = {"parse_ms": None, "compose_ms": None, "render_ms": None, "walk_ms": None}
    components: list = []
    spec: dict = {}
    script_path = out_dir / "script.js"
    render_res: dict = {"ok": False}
    walk_res: dict = {"ok": False}
    walk_payload: dict | None = None
    rendered_node_id: str | None = None

    # Step 1: parse prompt → component list (pre-baked on disk)
    try:
        components, parse_ms, raw_text = parse_from_disk(slug)
        timings["parse_ms"] = parse_ms
        (out_dir / "component_list.json").write_text(json.dumps(components, indent=2) + "\n")
        (out_dir / "llm_raw_response.txt").write_text(raw_text)
        log(slug, "parse", "ok", f"components={len(components)} parse_ms={parse_ms} [substituted]")
    except Exception as e:
        (out_dir / "FAILURE.md").write_text(f"# Parse failure\n\n{e!r}\n")
        log(slug, "parse", "fail", str(e)[:160])
        return {"slug": slug, "stage_failed": "parse", "error": str(e)}

    # Step 2: compose (IR + script)
    try:
        t0 = time.monotonic()
        result = generate_from_prompt(conn, components, page_name=None)
        timings["compose_ms"] = int((time.monotonic() - t0) * 1000)
        spec = result.get("spec") or {}
        script = result.get("structure_script", "")
        (out_dir / "ir.json").write_text(json.dumps(spec, indent=2) + "\n")
        script_path.write_text(script)
        (out_dir / "token_refs.json").write_text(json.dumps(result.get("token_refs") or [], indent=2) + "\n")
        (out_dir / "warnings.json").write_text(json.dumps(result.get("warnings") or [], indent=2) + "\n")
        log(slug, "compose", "ok",
            f"elements={len(spec.get('elements') or {})} "
            f"tokens={len(result.get('token_refs') or [])} "
            f"warnings={len(result.get('warnings') or [])}")
    except Exception as e:
        (out_dir / "FAILURE.md").write_text(f"# Compose failure\n\n{e!r}\n")
        log(slug, "compose", "fail", str(e)[:160])
        return {"slug": slug, "stage_failed": "compose", "error": str(e)}

    # Step 3: render. The walk_ref.js already renders + walks in one go
    # (it re-executes the script), so we do TWO separate bridge calls:
    # first a plain render via run.js (to capture __errors channel),
    # then a walk via walk_ref.js (which also renders, clearing the
    # page first). That matches the experiment brief's artefact list
    # (render_result.json, walk.json).
    try:
        render_res = run_render(script_path)
        timings["render_ms"] = render_res["elapsed_ms"]
        (out_dir / "render_result.json").write_text(json.dumps({
            "ok": render_res["ok"],
            "returncode": render_res["returncode"],
            "parsed": render_res.get("parsed"),
            "stdout": render_res["stdout"],
            "stderr": render_res["stderr"],
            "elapsed_ms": render_res["elapsed_ms"],
        }, indent=2) + "\n")
        parsed = render_res.get("parsed") or {}
        log(slug, "render",
            "ok" if render_res["ok"] and (parsed.get("__ok") or parsed.get("after") is not None) else "fail",
            f"after={parsed.get('after')} errors={len(parsed.get('errors') or [])} "
            f"rc={render_res['returncode']} elapsed_ms={render_res['elapsed_ms']}")
    except subprocess.TimeoutExpired as e:
        (out_dir / "FAILURE.md").write_text(f"# Render timeout\n\n{e!r}\n")
        log(slug, "render", "fail", "timeout")
        return {"slug": slug, "stage_failed": "render", "error": "timeout"}
    except Exception as e:
        (out_dir / "FAILURE.md").write_text(f"# Render failure\n\n{e!r}\n")
        log(slug, "render", "fail", str(e)[:160])
        return {"slug": slug, "stage_failed": "render", "error": str(e)}

    # Step 4: walk. walk_ref.js clears the page, re-renders, then walks.
    walk_json = out_dir / "walk.json"
    try:
        walk_res = run_walk(script_path, walk_json)
        timings["walk_ms"] = walk_res["elapsed_ms"]
        log(slug, "walk",
            "ok" if walk_res["ok"] else "fail",
            f"rc={walk_res['returncode']} elapsed_ms={walk_res['elapsed_ms']} "
            f"stderr_tail={walk_res['stderr'][-120:]!r}")
        if walk_res["ok"] and walk_json.exists():
            walk_payload = json.loads(walk_json.read_text())
            rendered_node_id = derive_rendered_node_id(walk_payload)
            if rendered_node_id:
                (out_dir / "rendered_node_id.txt").write_text(rendered_node_id + "\n")
    except subprocess.TimeoutExpired as e:
        (out_dir / "FAILURE.md").write_text(f"# Walk timeout\n\n{e!r}\n")
        log(slug, "walk", "fail", "timeout")
    except Exception as e:
        (out_dir / "FAILURE.md").write_text(f"# Walk failure\n\n{e!r}\n")
        log(slug, "walk", "fail", str(e)[:160])

    write_notes_md(
        out_dir, slug, prompt,
        components, spec, render_res, walk_res, walk_payload,
        timings,
    )
    log(slug, "done", "ok", f"timings={json.dumps(timings)}")

    # render_ok here means "script reached __phase=done inside the
    # wrapper," not just "node subprocess exit 0". The subprocess
    # exits 0 even when the script throws, because run.js catches
    # and returns a diagnostic payload.
    inner = ((render_res.get("parsed") or {}).get("result") or {}).get("result") or {}
    render_completed = isinstance(inner, dict) and inner.get("__phase") == "done"
    return {
        "slug": slug,
        "components": len(components),
        "elements": len(spec.get("elements") or {}),
        "subprocess_ok": render_res.get("ok"),
        "render_completed": render_completed,
        "render_error": None if render_completed else inner.get("error") or "unknown",
        "walk_ok": walk_res.get("ok"),
        "rendered_node_id": rendered_node_id,
        "timings": timings,
    }


def main(only: list[str] | None = None) -> None:
    # Make sure templates + CKR are built (same as dd generate-prompt)
    conn = get_connection(str(DB_PATH))
    try:
        file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
        if file_row:
            file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
            build_component_key_registry(conn)
            extract_templates(conn, file_id)
    finally:
        conn.close()

    summary = []
    for slug, prompt in PROMPTS:
        if only and slug not in only:
            continue
        conn = get_connection(str(DB_PATH))
        try:
            res = run_one(slug, prompt, conn, None)
            summary.append(res)
        finally:
            conn.close()

    (EXP_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    only = sys.argv[1:] or None
    main(only)
