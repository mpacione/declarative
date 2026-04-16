---
name: verify-parity
description: Check whether a rendered Figma subtree matches the IR it was supposed to come from. Emits a structured RenderReport with per-node parity, a parity_ratio, and structured KIND_* errors for every mismatch. Use when debugging whether a generated or re-rendered screen actually matches its declarative specification.
when_to_use: After a user renders an IR (either via the existing renderer or generate-screen). Also useful as a regression check after the renderer changes. User phrases like "did this render correctly", "is it pixel-perfect", "verify the parity", "check the round-trip".
requires:
  - An existing declarative-build SQLite database with the IR
  - A rendered Figma subtree to check against (either on-canvas or as a walk_ref.json payload)
  - Figma Desktop bridge running (for walking the rendered subtree)
---

# verify-parity

Implements ADR-007 Position 3: the post-render RenderVerifier. Walks
the rendered subtree, compares to the IR node-by-node, and raises
structured errors with named `KIND_*` for every mismatch.

## Inputs

Required:
- `db` — path to the SQLite database with the IR.
- `screen_id` — the IR screen's database id.
- Either:
  - `rendered_node_id` + `plugin_port` — the Figma node id and bridge
    port, and we'll walk the subtree fresh; OR
  - `walk_ref_path` — path to an existing `walk_ref.json` payload.

Optional:
- `json` — boolean. Emit the full `RenderReport` as JSON instead of a
  human-readable summary.

## Behaviour

1. Load the IR for the screen from the database.
2. If `walk_ref_path` not given, run `node render_test/walk_ref.js
   <script_or_node_id> <tmp_json_path> <plugin_port>` to produce the
   rendered-ref JSON.
3. Call `dd verify --db <db> --screen <screen_id> --rendered-ref
   <walk_ref_path> [--json]`.
4. Report: `ir_node_count`, `rendered_node_count`, `is_parity` (true/false),
   `parity_ratio` (0.0-1.0), `errors` list with `kind`, `id`, `error`
   text for each.

## Outputs

Human summary:
```
RenderReport (screen 324, backend=figma):
  ir_node_count:       91
  rendered_node_count: 91
  is_parity:           True
  parity_ratio:        1.0000
  errors:              0
```

JSON (with `--json`):
```json
{
  "backend": "figma",
  "ir_node_count": 91,
  "rendered_node_count": 91,
  "is_parity": true,
  "parity_ratio": 1.0,
  "errors": []
}
```

Non-parity failures show per-node `KIND_*` entries:
```
  errors:              3
    kind=bounds_mismatch  id=card-7    Text wrapped; rendered height 84px vs IR 48px
    kind=fill_mismatch    id=btn-2     Rendered #09090B differs from IR #000000
    kind=missing_asset    id=vec-12    VECTOR rendered without path geometry
```

## Exit code

Non-zero when `is_parity` is false. Scripts can chain on this.

## What this skill does NOT do

- Does not render. Assumes the user already ran the script (manually
  or via `generate-screen`).
- Does not suggest fixes. Structured errors diagnose; they don't repair.
- Does not critique aesthetics. Visual critique is (future) a separate
  skill.

## Example usage

```
User: "Did the generated screen match the IR?"

Assistant runs:
  node render_test/walk_ref.js <script_path> /tmp/walk.json 9231
  dd verify --db app.db --screen 324 --rendered-ref /tmp/walk.json

Reports: is_parity=True, 91/91 nodes, 0 errors.
```

## Typical chain

Use after `generate-screen` to confirm the synthetic output actually
rendered as specified. If parity fails, the `KIND_*` entries tell you
where to investigate.
