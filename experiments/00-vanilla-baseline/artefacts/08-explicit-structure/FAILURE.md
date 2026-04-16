# Render failure — layoutMode assigned to TEXT node

The prompt parsed and composed into an IR with 9 elements.
The generator emitted a Figma Plugin API script, but the script errored
during execution on the bridge with:

    TypeError: object is not extensible

### Root cause (from script inspection)

`dd.renderers.figma.generate_figma_script` emits `n.layoutMode =
"VERTICAL"` for **every** element in Phase 1 (Materialize), including
elements whose Figma type is TEXT. Figma's Plugin API does not expose
a writable `layoutMode` on TEXT nodes, so assigning it throws the
"object is not extensible" error.

In this script, 4 `figma.createText()` calls are
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
