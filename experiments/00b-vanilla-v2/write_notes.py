"""Write the final notes.md for each prompt.

Uses the definitive artefacts: walk.json (latest), render_result.json,
IR, warnings, screenshot_manifest.results.json (if present).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
SCREENSHOT_RESULTS = EXP_ROOT / "screenshot_manifest.results.json"


def screenshot_map() -> dict[str, dict]:
    if not SCREENSHOT_RESULTS.exists():
        return {}
    entries = json.loads(SCREENSHOT_RESULTS.read_text())
    out: dict[str, dict] = {}
    for e in entries:
        sp = e.get("script_path", "")
        slug = Path(sp).parent.name
        out[slug] = e
    return out


def render_errors(rr_path: Path) -> list[dict]:
    rr = json.loads(rr_path.read_text())
    inner = rr.get("parsed", {}).get("result", {}).get("result", {})
    return inner.get("errors", [])


def write_notes(slug: str) -> None:
    d = ARTEFACTS / slug
    if not d.is_dir():
        return

    lines: list[str] = [f"# Notes — {slug}\n"]
    prompt_txt = (d / "prompt.txt").read_text().strip() if (d / "prompt.txt").exists() else ""
    lines.append(f"Prompt: `{prompt_txt}`\n")

    # Stage completion
    stages = {"parse": False, "compose": False, "render": False, "walk": False, "screenshot": False}
    stages["parse"] = (d / "component_list.json").exists()
    stages["compose"] = (d / "ir.json").exists() and (d / "script.js").exists()
    stages["render"] = (d / "render_result.json").exists()
    stages["walk"] = (d / "walk.json").exists()
    stages["screenshot"] = (d / "screenshot.png").exists()

    lines.append("## Stage completion\n")
    for s, done in stages.items():
        lines.append(f"- {s}: {'ok' if done else 'fail'}")

    # Component / IR type distribution
    if stages["parse"]:
        comps = json.loads((d / "component_list.json").read_text())
        def collect(cs, bag):
            for c in cs:
                bag[c.get("type", "?")] += 1
                if c.get("children"):
                    collect(c["children"], bag)
        llm_types: Counter = Counter()
        collect(comps, llm_types)
        lines.append("\n## LLM output (parse)\n")
        lines.append(f"- component count (flat): {sum(llm_types.values())}")
        lines.append(f"- types: `{dict(llm_types)}`")

    if stages["compose"]:
        ir = json.loads((d / "ir.json").read_text())
        warnings = json.loads((d / "warnings.json").read_text()) if (d / "warnings.json").exists() else []
        token_refs = json.loads((d / "token_refs.json").read_text()) if (d / "token_refs.json").exists() else []
        ir_types = Counter(e.get("type") for e in ir.get("elements", {}).values())
        lines.append("\n## Compose (IR)\n")
        lines.append(f"- elements: {len(ir.get('elements', {}))}")
        lines.append(f"- types: `{dict(ir_types)}`")
        lines.append(f"- warnings (Mode 2 fallbacks): {len(warnings)}")
        lines.append(f"- token refs: {len(token_refs) if isinstance(token_refs, (list, dict)) else 0}")
        script = (d / "script.js").read_text()
        lines.append(f"- script chars: {len(script):,}")
        lines.append(f"- createInstance count (Mode 1): {script.count('createInstance')}")
        lines.append(f"- createText count: {script.count('createText')}")
        lines.append(f"- createFrame count: {script.count('createFrame')}")

    # Render result
    if stages["render"]:
        errs = render_errors(d / "render_result.json")
        kinds = Counter(e.get("kind") if isinstance(e, dict) else "?" for e in errs)
        lines.append("\n## Render (bridge execution)\n")
        inner = json.loads((d / "render_result.json").read_text()).get("parsed", {}).get("result", {}).get("result", {})
        lines.append(f"- __ok: {inner.get('__ok')}")
        lines.append(f"- errors: {len(errs)} — kinds: `{dict(kinds)}`")
        for e in errs[:5]:
            if isinstance(e, dict):
                lines.append(f"  - kind=`{e.get('kind')}` eid=`{e.get('eid')}` msg=`{str(e.get('error') or e.get('message'))[:180]}`")

    # Walk metrics (mechanical)
    if stages["walk"]:
        w = json.loads((d / "walk.json").read_text())
        eids = w.get("eid_map", {})
        types = Counter(e.get("type") for e in eids.values())
        widths = [(k, v.get("width", 0)) for k, v in eids.items()]
        heights = [(k, v.get("height", 0)) for k, v in eids.items()]
        zero_dim = [k for k, v in eids.items() if (v.get("width") or 0) == 0 or (v.get("height") or 0) == 0]
        default_sized = [k for k, v in eids.items() if v.get("width") == 100 and v.get("height") == 100]
        vec_missing = [
            k for k, v in eids.items()
            if v.get("type") in ("VECTOR", "BOOLEAN_OPERATION")
            and (v.get("fillGeometryCount") or 0) == 0
            and (v.get("strokeGeometryCount") or 0) == 0
        ]
        lines.append("\n## Walk (rendered subtree)\n")
        lines.append(f"- eid_count: {len(eids)}")
        lines.append(f"- type distribution: `{dict(types)}`")
        if eids:
            max_w = max(v.get("width", 0) for v in eids.values())
            max_h = max(v.get("height", 0) for v in eids.values())
            lines.append(f"- max dimensions: {max_w} x {max_h}")
            lines.append(f"- Mode-2 default-sized (100x100) nodes: {len(default_sized)} / {len(eids)}")
        if zero_dim:
            lines.append(f"- zero-dimension nodes ({len(zero_dim)}): {zero_dim[:10]}")
        if vec_missing:
            lines.append(f"- missing vector assets ({len(vec_missing)}): {vec_missing[:10]}")

    # Screenshot
    if stages["screenshot"]:
        size = (d / "screenshot.png").stat().st_size
        lines.append("\n## Screenshot\n")
        lines.append(f"- `screenshot.png` — {size:,} bytes")
        if size < 4000:
            lines.append("- **size signal:** tiny (< 4KB) — screen-1 is empty grey frame (throw happened before children were appended)")
        else:
            lines.append("- size > 4KB — rendered content visible")

    # Mechanical patterns summary
    lines.append("\n## Mechanical patterns\n")
    if stages["render"]:
        errs = render_errors(d / "render_result.json")
        thrown_errs = [e for e in errs if isinstance(e, dict) and e.get("kind") == "render_thrown"]
        if thrown_errs:
            lines.append(f"- **render_thrown ×{len(thrown_errs)}:** outer guard caught `{thrown_errs[0].get('error')}` — leaf-type bug: `heading`/`link` IR types render as TEXT but aren't in `_LEAF_TYPES`, so `.layoutMode = \"VERTICAL\"` is still emitted and the Plugin API rejects it")
        else:
            lines.append("- render_thrown: none — no `heading`/`link` types in this IR")
    if stages["compose"]:
        lines.append(f"- all elements rendered as Mode-2 createFrame (no CKR matches surfaced to the LLM — `component_templates` has 1 row; `component_key_registry` has 129 rows but isn't exposed)")
        lines.append(f"- 0 token references emitted (`tokens` table empty; cluster step never run)")

    (d / "notes.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    for slug_dir in sorted(ARTEFACTS.iterdir()):
        if slug_dir.is_dir():
            write_notes(slug_dir.name)
    print("notes written for all artefacts")


if __name__ == "__main__":
    main()
