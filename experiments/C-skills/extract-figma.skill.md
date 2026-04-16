---
name: extract-figma
description: Ingest a Figma file into a local SQLite database in the declarative-build IR format. Use when a user wants to analyse, re-render, transform, or generate from an existing Figma design. Requires a Figma personal access token in the environment. Plugin-API-only fields (transforms, vector paths, OpenType features, instance overrides) need the optional Figma Desktop bridge; without it the extraction is still complete but missing the ~25% of properties that REST doesn't expose.
when_to_use: User mentions a Figma URL, or wants to "pull in" or "ingest" a Figma file, or wants to work with a design system that lives in Figma. Also when chaining with verify-parity or generate-screen and the IR doesn't yet exist.
requires:
  - python3.11+
  - node18+
  - FIGMA_ACCESS_TOKEN env variable
  - (optional) Figma Desktop + figma-console-mcp bridge plugin for Plugin-API pass
---

# extract-figma

Extracts a Figma file into a SQLite database representing the
multi-level intermediate representation (L0 scene graph + L1
classification annotations + L2 token bindings).

## Inputs

Required:
- `figma_url` — the Figma URL (e.g. `https://www.figma.com/design/<FILE_KEY>/<Name>`).

Optional:
- `out_db` — output database path. Default: `<FILE_KEY>.declarative.db`.
- `page_id` — restrict extraction to a single page.
- `plugin_api_port` — port of the Figma Desktop bridge. Default: 9231.
  If omitted, the extraction runs REST-only (faster, but misses ~25% of
  properties).
- `skip_plugin_api` — boolean. Set to true if the bridge isn't running
  and the user wants to proceed anyway.

## Behaviour

1. Call `dd extract <figma_url> --db <out_db>`. REST path — fast, covers
   ~75% of properties.
2. If `skip_plugin_api` is false and a bridge port is reachable, call
   `dd extract-plugin --db <out_db> --port <port>`. This populates
   Plugin-API-only fields: `relative_transform` (for rotated nodes),
   `vector_paths` (authoring path data), `opentype_features`, instance
   overrides.
3. Rebuild the component-key registry (CKR). Handled inside
   `dd extract` already — CKR enables Mode 1 component instantiation
   downstream.
4. Report a completion summary: nodes extracted, screens, CKR size,
   plugin-API pass status, wall-clock time.

## Outputs

- `<out_db>` — the SQLite database with the full IR.
- A human-readable summary of what landed:
  - Total nodes, screens by type (`app_screen`, `icon_def`,
    `component_def`, `design_canvas`).
  - CKR size (how many components have resolvable masters).
  - Any structured errors (file inaccessible, Figma 5xx, Plugin-API
    pass skipped, etc.).

## Error handling

Per the ADR-006 boundary contract: network errors, Figma API errors,
plugin bridge disconnection, and malformed responses never raise. They
produce structured errors surfaced in the completion summary. Partial
success is a first-class outcome — if one screen fails the others still
extract.

## What this skill does NOT do

- Does not classify components (that's a separate pipeline step in
  `dd classify`).
- Does not cluster tokens (that's `dd cluster` + `dd accept-all`).
- Does not generate design.md (that's the `generate-design-md` skill).
- Does not verify anything against Figma (that's the `verify-parity` skill).

## Example usage

```
User: "Extract my Figma file https://www.figma.com/design/abc123/my-app"

Assistant runs:
  dd extract https://www.figma.com/design/abc123/my-app --db abc123.declarative.db
  dd extract-plugin --db abc123.declarative.db --port 9231

Then reports:
  ✓ Extracted 47,294 nodes across 186 screens (143 app_screens, 31
    component_defs, 12 design_canvases).
  ✓ CKR built: 89 components.
  ✓ Plugin-API pass: 21,847 nodes updated.
  ✓ Wall-clock: 146 s.
```
