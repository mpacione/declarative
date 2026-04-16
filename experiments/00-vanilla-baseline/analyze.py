"""Aggregate stats across the 12 prompt artefacts.

Produces the inputs the memo needs:
- per-prompt completion status
- component usage frequencies
- token reference counts
- error channel counts
- render timings
- canonical-type coverage (how many of the 48 catalog types were used?)
"""
from pathlib import Path
import json
from collections import Counter, defaultdict

ROOT = Path("/Users/mattpacione/declarative-build/experiments/00-vanilla-baseline")
ART = ROOT / "artefacts"

CANONICAL_TYPES = {
    # Actions
    "button", "icon_button", "fab", "button_group", "menu", "context_menu",
    # Selection & Input
    "checkbox", "radio", "toggle", "toggle_group", "select", "combobox",
    "date_picker", "slider", "segmented_control", "text_input", "textarea",
    "search_input", "stepper",
    # Content & Display
    "text", "heading", "link", "image", "icon", "avatar", "badge",
    "list", "list_item", "table", "skeleton",
    # Navigation
    "navigation_row", "tabs", "breadcrumbs", "pagination", "bottom_nav",
    "drawer", "header",
    # Feedback & Status
    "alert", "toast", "popover", "tooltip", "empty_state", "file_upload",
    # Containment & Overlay
    "card", "dialog", "sheet", "accordion",
    # Frame meta
    "screen",
}


def collect():
    per_prompt = []
    type_counter_per_prompt = defaultdict(Counter)
    global_type_counter = Counter()
    tokens_by_prompt = {}
    mode1_instances_by_prompt = {}

    for d in sorted(ART.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        prompt = (d / "prompt.txt").read_text().strip() if (d / "prompt.txt").exists() else ""
        components = []
        ir = {}
        render = {}
        walk = None

        if (d / "component_list.json").exists():
            components = json.loads((d / "component_list.json").read_text())
        if (d / "ir.json").exists():
            ir = json.loads((d / "ir.json").read_text())
        if (d / "render_result.json").exists():
            render = json.loads((d / "render_result.json").read_text())
        if (d / "walk.json").exists():
            walk = json.loads((d / "walk.json").read_text())

        token_refs = []
        if (d / "token_refs.json").exists():
            token_refs = json.loads((d / "token_refs.json").read_text())

        warnings = []
        if (d / "warnings.json").exists():
            warnings = json.loads((d / "warnings.json").read_text())

        elements = ir.get("elements") or {}
        for el in elements.values():
            t = el.get("type") or "?"
            type_counter_per_prompt[slug][t] += 1
            global_type_counter[t] += 1

        # Mode 1 vs Mode 2: if any element has component_key, it's Mode 1
        mode1 = sum(1 for el in elements.values() if el.get("component_key"))
        mode1_instances_by_prompt[slug] = mode1

        # Render status
        inner = (render.get("parsed") or {}).get("result", {}).get("result", {})
        render_ok = inner.get("__phase") == "done" if isinstance(inner, dict) else False
        render_errors = []
        if isinstance(inner, dict) and isinstance(inner.get("errors"), list):
            render_errors = inner["errors"]
        elif render.get("parsed", {}).get("errors"):
            render_errors = render["parsed"]["errors"]
        # fall-through: if top-level parsed has `ok`, inspect shape further
        if render.get("parsed") and isinstance(render["parsed"], dict) and render["parsed"].get("result"):
            outer_result = render["parsed"]["result"].get("result") or {}
            if isinstance(outer_result, dict):
                render_ok = outer_result.get("__phase") == "done"
                render_errors = outer_result.get("errors") or render_errors

        walk_ok = False
        walk_eid_count = 0
        walk_errors = []
        vec_missing = 0
        if walk:
            walk_ok = bool(walk.get("__ok"))
            walk_errors = walk.get("errors") or []
            walk_eid_count = len(walk.get("eid_map") or {})
            for e in (walk.get("eid_map") or {}).values():
                if e.get("type") in ("VECTOR", "BOOLEAN_OPERATION"):
                    if not e.get("fillGeometryCount") and not e.get("strokeGeometryCount"):
                        vec_missing += 1

        kind_counts = Counter()
        for err in render_errors or []:
            kind_counts[(err or {}).get("kind") or "?"] += 1

        per_prompt.append({
            "slug": slug,
            "prompt": prompt,
            "top_level_components": len(components),
            "ir_elements": len(elements),
            "mode1_instances": mode1,
            "render_ok": render_ok,
            "render_errors": len(render_errors or []),
            "render_kind_counts": dict(kind_counts),
            "render_error_kind": None if render_ok else "object_not_extensible",
            "walk_ok": walk_ok,
            "walk_eid_count": walk_eid_count,
            "walk_errors": len(walk_errors),
            "walk_vector_missing": vec_missing,
            "token_refs_count": len(token_refs),
            "warnings_count": len(warnings),
        })
        tokens_by_prompt[slug] = token_refs

    used = {t for c in type_counter_per_prompt.values() for t in c}
    unused = CANONICAL_TYPES - used
    spec_used_outside_canonical = used - CANONICAL_TYPES  # sanity: IR may have `frame` or `screen`

    return {
        "per_prompt": per_prompt,
        "global_type_counter": dict(global_type_counter),
        "types_used": sorted(used),
        "types_unused_in_catalog_of_48": sorted(unused - {"screen"}),
        "types_in_spec_outside_catalog": sorted(spec_used_outside_canonical),
        "mode1_instances_by_prompt": mode1_instances_by_prompt,
        "tokens_by_prompt": tokens_by_prompt,
    }


def main() -> None:
    data = collect()
    (ROOT / "analysis.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
