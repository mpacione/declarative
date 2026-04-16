"""Write FAILURE.md for every prompt that didn't complete end-to-end.

The render failure is systemic: generate.py emits `n.layoutMode =
"VERTICAL"` for every element in the IR, but TEXT nodes in Figma's
Plugin API don't have layoutMode and raise "object is not extensible"
when it's assigned. 11/12 prompts emit at least one TEXT element, so
11/12 prompts hit the same bug.
"""
from pathlib import Path
import json

ROOT = Path("/Users/mattpacione/declarative-build/experiments/00-vanilla-baseline/artefacts")

FAILURE_TEMPLATE = """# Render failure — layoutMode assigned to TEXT node

The prompt parsed and composed into an IR with {elements} elements.
The generator emitted a Figma Plugin API script, but the script errored
during execution on the bridge with:

    TypeError: object is not extensible

### Root cause (from script inspection)

`dd.renderers.figma.generate_figma_script` emits `n.layoutMode =
"VERTICAL"` for **every** element in Phase 1 (Materialize), including
elements whose Figma type is TEXT. Figma's Plugin API does not expose
a writable `layoutMode` on TEXT nodes, so assigning it throws the
"object is not extensible" error.

In this script, {create_text_count} `figma.createText()` calls are
made, and each has a `layoutMode = "VERTICAL"` assignment on the
following line. The first such assignment aborts the script.

### Script state at failure

- Nodes created on page before throw: `before -> after` (see
  `render_result.json`, `parsed.result`)
- No eids added to `__errors` channel for this failure — it happens
  BEFORE the M["__errors"] = __errors line at script end. The wrapper
  in render_test/run.js catches the exception and records
  `__phase: script_error`.

### Why the walk also failed

`render_test/walk_ref.js` re-executes the same script before walking
(it clears the page first, then runs the user code). Same bug, same
exception, no walk payload.

### Implication

This is NOT a one-off per-prompt failure: it's a generator-side bug
that affects every prompt containing at least one TEXT-producing
element (any `text`, `heading`, `link`, or text-label-bearing
component whose lowering decomposes to a TEXT node).

09-drawer-nav is the only prompt in this experiment that completes
end-to-end, and only because its IR happens to contain no TEXT nodes
(the `drawer` and `navigation_row` types lower to frame-only
subtrees with default labels stubbed out).

See `memo.md` for cross-prompt counts.
"""


def main() -> None:
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        render_path = d / "render_result.json"
        if not render_path.exists():
            continue
        parsed = json.loads(render_path.read_text())
        inner = (parsed.get("parsed") or {}).get("result", {}).get("result", {})
        if inner.get("__phase") == "script_error" and inner.get("error") == "object is not extensible":
            # Count createText occurrences in the script
            script = (d / "script.js").read_text()
            ct = script.count("figma.createText()")
            elements = len(json.loads((d / "ir.json").read_text()).get("elements") or {})
            (d / "FAILURE.md").write_text(FAILURE_TEMPLATE.format(
                elements=elements, create_text_count=ct,
            ))
            print(f"wrote {d.name}/FAILURE.md (createText={ct}, elements={elements})")


if __name__ == "__main__":
    main()
