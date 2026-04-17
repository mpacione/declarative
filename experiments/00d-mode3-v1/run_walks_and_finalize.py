"""Stage 2: run walks, produce proper summaries.

The initial run_experiment.py mis-parsed the render result (one level too
shallow). All 12 prompts actually rendered successfully end-to-end and
the outer KIND_RENDER_THROWN guard caught the leaf-type bug in 11/12. This
script:
  1. Reads render_result.json for each prompt, extracting the inner payload.
  2. Runs walk_ref.js (which also clears the page, then re-renders) for
     each script so we have a rendered-subtree walk.
  3. Re-derives notes.md with accurate stage-status and mechanical metrics.
  4. Rebuilds run_summary.json with correct status per prompt.
  5. Removes the stale FAILURE.md files created by the first driver for
     prompts that actually completed.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
RUN_SUMMARY = EXP_ROOT / "run_summary.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
WALK_JS = REPO_ROOT / "render_test" / "walk_ref.js"
BRIDGE_PORT = "9231"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log(slug: str, stage: str, status: str, detail: str) -> None:
    line = f"{now()} | {slug} | {stage} | {status} | {detail}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def run_node_cmd(cmd: list[str], timeout: int = 180) -> dict:
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


def inner_render_payload(rr_path: Path) -> dict | None:
    """The run.js output is nested: {parsed:{result:{result:INNER}}}."""
    data = json.loads(rr_path.read_text())
    parsed = data.get("parsed") or {}
    outer = parsed.get("result") or {}
    return outer.get("result")


def walk_mechanical_metrics(walk_data: dict) -> dict:
    eids = walk_data.get("eid_map", {})
    type_ct = Counter(e.get("type") for e in eids.values())
    zero_dim = [k for k, v in eids.items() if (v.get("width") or 0) == 0 or (v.get("height") or 0) == 0]
    vec_missing = [
        k for k, v in eids.items()
        if v.get("type") in ("VECTOR", "BOOLEAN_OPERATION")
        and (v.get("fillGeometryCount") or 0) == 0
        and (v.get("strokeGeometryCount") or 0) == 0
    ]
    tiny_text = [k for k, v in eids.items() if v.get("type") == "TEXT" and ((v.get("width") or 0) < 2)]
    # bounding-box overlap detection would require x/y too — only width/height here
    widths = [v.get("width", 0) for v in eids.values()]
    heights = [v.get("height", 0) for v in eids.values()]
    return {
        "eid_count": len(eids),
        "types": dict(type_ct),
        "zero_dim_nodes": zero_dim,
        "missing_vectors": vec_missing,
        "tiny_text_nodes": tiny_text,
        "max_width": max(widths) if widths else 0,
        "max_height": max(heights) if heights else 0,
    }


def process(slug: str) -> dict:
    out_dir = ARTEFACTS / slug
    if not out_dir.exists():
        return {"slug": slug, "skipped": "no dir"}

    summary: dict = {"slug": slug, "stages": {}}
    prompt = (out_dir / "prompt.txt").read_text().strip()
    summary["prompt"] = prompt

    # Parse stage
    comp_file = out_dir / "component_list.json"
    if comp_file.exists():
        try:
            components = json.loads(comp_file.read_text())
            summary["stages"]["parse"] = {"status": "ok", "components": len(components)}
        except Exception:
            summary["stages"]["parse"] = {"status": "fail"}
    else:
        summary["stages"]["parse"] = {"status": "fail"}

    # Compose stage
    ir_file = out_dir / "ir.json"
    warnings_file = out_dir / "warnings.json"
    script_file = out_dir / "script.js"
    if ir_file.exists() and script_file.exists():
        ir = json.loads(ir_file.read_text())
        warnings_list = json.loads(warnings_file.read_text()) if warnings_file.exists() else []
        element_types = Counter(e.get("type") for e in ir.get("elements", {}).values())
        summary["stages"]["compose"] = {
            "status": "ok",
            "elements": len(ir.get("elements", {})),
            "warnings": len(warnings_list),
            "element_types": dict(element_types),
            "script_chars": script_file.stat().st_size,
        }
    else:
        summary["stages"]["compose"] = {"status": "fail"}

    # Render stage — re-read render_result correctly
    rr_file = out_dir / "render_result.json"
    if rr_file.exists():
        inner = inner_render_payload(rr_file)
        if inner:
            errs = inner.get("errors", [])
            kinds = Counter(e.get("kind") if isinstance(e, dict) else "unknown" for e in errs)
            summary["stages"]["render"] = {
                "status": "ok" if inner.get("__ok") else "fail",
                "errors_count": len(errs),
                "error_kinds": dict(kinds),
                "before": inner.get("before"),
                "after": inner.get("after"),
                "nodes_created": (inner.get("after") or 0) - (inner.get("before") or 0),
            }
        else:
            summary["stages"]["render"] = {"status": "fail", "error": "no inner payload"}
    else:
        summary["stages"]["render"] = {"status": "fail"}

    # Walk stage — run it now
    if script_file.exists():
        walk_path = out_dir / "walk.json"
        log(slug, "walk", "start", "")
        walk_proc = run_node_cmd(
            ["node", str(WALK_JS), str(script_file), str(walk_path), BRIDGE_PORT],
            timeout=240,
        )
        walk_ok = walk_proc["returncode"] == 0 and walk_path.exists()
        if walk_ok:
            walk_data = json.loads(walk_path.read_text())
            metrics = walk_mechanical_metrics(walk_data)
            rendered_root = walk_data.get("rendered_root") or ""
            (out_dir / "rendered_node_id.txt").write_text(rendered_root + "\n")
            summary["stages"]["walk"] = {
                "status": "ok",
                "latency_ms": int(walk_proc["latency_s"] * 1000),
                "rendered_root": rendered_root,
                **metrics,
            }
            log(slug, "walk", "ok",
                f"eids={metrics['eid_count']} root={rendered_root[:20]}")
        else:
            summary["stages"]["walk"] = {
                "status": "fail",
                "latency_ms": int(walk_proc["latency_s"] * 1000),
                "stderr": walk_proc["stderr"][-500:],
            }
            log(slug, "walk", "fail", walk_proc["stderr"][:200])

    # Regenerate notes.md
    notes = [f"# Notes — {slug}\n", f"Prompt: `{prompt}`\n\n## Stage completion\n"]
    for stage_name in ("parse", "compose", "render", "walk"):
        s = summary["stages"].get(stage_name, {})
        notes.append(f"- {stage_name}: {s.get('status', 'not-run')}")

    render_s = summary["stages"].get("render", {})
    if render_s.get("errors_count"):
        notes.append(f"\n## Structured errors ({render_s['errors_count']})\n")
        inner = inner_render_payload(rr_file)
        for e in inner.get("errors", [])[:20]:
            kind = e.get("kind") if isinstance(e, dict) else None
            eid = e.get("eid") if isinstance(e, dict) else None
            msg = e.get("error") or e.get("message") if isinstance(e, dict) else None
            notes.append(f"- kind={kind} eid={eid} msg={str(msg)[:180]}")

    walk_s = summary["stages"].get("walk", {})
    if walk_s.get("status") == "ok":
        notes.append(f"\n## Walk summary\n")
        notes.append(f"- rendered_root: `{walk_s.get('rendered_root')}`")
        notes.append(f"- eid_count: {walk_s.get('eid_count')}")
        notes.append(f"- type distribution: `{walk_s.get('types')}`")
        notes.append(f"- max dimensions: {walk_s.get('max_width')} x {walk_s.get('max_height')}")
        if walk_s.get("zero_dim_nodes"):
            notes.append(f"- zero-dim nodes ({len(walk_s['zero_dim_nodes'])}): {walk_s['zero_dim_nodes'][:10]}")
        if walk_s.get("missing_vectors"):
            notes.append(f"- missing vector assets ({len(walk_s['missing_vectors'])}): {walk_s['missing_vectors'][:10]}")
        if walk_s.get("tiny_text_nodes"):
            notes.append(f"- tiny text nodes ({len(walk_s['tiny_text_nodes'])}): {walk_s['tiny_text_nodes'][:10]}")

    compose_s = summary["stages"].get("compose", {})
    if compose_s.get("element_types"):
        notes.append(f"\n## IR type distribution\n- `{compose_s['element_types']}`")
    if compose_s.get("warnings"):
        notes.append(f"- warnings: {compose_s['warnings']}")

    (out_dir / "notes.md").write_text("\n".join(notes) + "\n")

    # Remove stale FAILURE.md if render actually succeeded
    failure_file = out_dir / "FAILURE.md"
    if failure_file.exists() and render_s.get("status") == "ok":
        failure_file.unlink()

    return summary


def main() -> None:
    ACTIVITY_LOG.open("a").close()  # ensure exists
    summaries = []
    slugs = sorted(d.name for d in ARTEFACTS.iterdir() if d.is_dir())
    for slug in slugs:
        try:
            summary = process(slug)
        except Exception as e:
            summary = {"slug": slug, "error": str(e)}
            log(slug, "process", "fail", str(e)[:200])
        summaries.append(summary)
        RUN_SUMMARY.write_text(json.dumps(summaries, indent=2))
    log("_", "finalize", "ok", f"count={len(summaries)}")


if __name__ == "__main__":
    main()
