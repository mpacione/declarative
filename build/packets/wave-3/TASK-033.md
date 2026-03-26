---
taskId: TASK-033
title: "Implement radius + effect clustering"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-002, TASK-004]
produces:
  - dd/cluster_misc.py
verify:
  - type: typecheck
    command: 'python -c "from dd.cluster_misc import cluster_radius, cluster_effects, propose_radius_name, propose_effect_name"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_clustering.py -k "radius or effect" -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-033: Implement radius + effect clustering

## Spec Context

### From Technical Design Spec -- Phase 5: Clustering + Token Proposal

> **Radius clustering:**
> 1. Query `v_radius_census WHERE file_id = ?`.
> 2. Typically 3-5 unique values.
> 3. Propose names: `radius.sm`, `radius.md`, `radius.lg`, `radius.full`.
>
> **Effect clustering:**
> 1. Query `v_effect_census WHERE file_id = ?` -- unique shadow/blur values.
> 2. Group by composite similarity (same color + similar radius + similar offset = one shadow token).
> 3. Propose names: `shadow.sm`, `shadow.md`, `shadow.lg`.

### From schema.sql -- v_radius_census view

> ```sql
> CREATE VIEW v_radius_census AS
> SELECT
>     ntb.resolved_value,
>     COUNT(*) AS usage_count,
>     s.file_id
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id
> JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'cornerRadius%' OR ntb.property LIKE '%Radius'
> GROUP BY ntb.resolved_value, s.file_id
> ORDER BY CAST(ntb.resolved_value AS REAL);
> ```

### From schema.sql -- v_effect_census view

> ```sql
> CREATE VIEW v_effect_census AS
> SELECT
>     ntb.resolved_value,
>     ntb.property,
>     COUNT(*) AS usage_count,
>     s.file_id
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id
> JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'effect%'
> GROUP BY ntb.resolved_value, ntb.property, s.file_id
> ORDER BY usage_count DESC;
> ```

### From schema.sql -- tokens, token_values, node_token_bindings tables

> (Same as in TASK-030 and TASK-032)

### From TDS -- Effect decomposition

> Each effect property gets its own binding row. A single DROP_SHADOW produces 5 bindings: `effect.0.color`, `effect.0.radius`, `effect.0.offsetX`, `effect.0.offsetY`, `effect.0.spread`. This maps 1:1 to Figma's `setBoundVariableForEffect` API which binds each field independently.

### From TDS -- Key Design Decision

> **Composite tokens (typography, shadow, border)** are stored as individual atomic tokens in the DB. DTCG composite types are assembled at export time.

### From dd/color.py (produced by TASK-004)

> Exports:
> - `hex_to_oklch(hex_color: str) -> tuple[float, float, float]`
> - `oklch_delta_e(color1: tuple, color2: tuple) -> float`

## Task

Create `dd/cluster_misc.py` implementing radius and effect clustering from Phase 5. Effects are stored as individual atomic tokens (shadow.sm.color, shadow.sm.radius, etc.) matching the binding decomposition from extraction.

1. **`query_radius_census(conn, file_id: int) -> list[dict]`**:
   - Query radius bindings filtering by unbound status:
     ```sql
     SELECT ntb.resolved_value, COUNT(*) AS usage_count
     FROM node_token_bindings ntb
     JOIN nodes n ON ntb.node_id = n.id
     JOIN screens s ON n.screen_id = s.id
     WHERE (ntb.property LIKE 'cornerRadius%' OR ntb.property LIKE '%Radius')
       AND ntb.binding_status = 'unbound'
       AND s.file_id = ?
     GROUP BY ntb.resolved_value
     ORDER BY CAST(ntb.resolved_value AS REAL)
     ```
   - Return list of dicts: `{"resolved_value": str, "usage_count": int}`.

2. **`propose_radius_name(value: float, index: int, total: int) -> str`**:
   - If value >= 9999 or value == 0: return `"radius.full"` (for fully-rounded / pill shapes, though 0 shouldn't normally appear).
   - Map to t-shirt sizes based on total count and position:
     - For 1-3 values: ["sm", "md", "lg"]
     - For 4-5 values: ["xs", "sm", "md", "lg", "xl"]
     - For 6+: ["xs", "sm", "md", "lg", "xl", "2xl", ...]
   - Return `f"radius.{size}"`.

3. **`cluster_radius(conn, file_id: int, collection_id: int, mode_id: int) -> dict`**:
   - Call `query_radius_census(conn, file_id)`.
   - Deduplicate values (convert to float, round to nearest int for grouping).
   - Sort by value ascending.
   - For each unique value, propose a name.
   - INSERT tokens (type="dimension", tier="extracted").
   - INSERT token_values.
   - UPDATE bindings: all radius bindings with matching resolved_value -> proposed, confidence=1.0.
   - Return: `{"tokens_created": int, "bindings_updated": int}`.

4. **`query_effect_census(conn, file_id: int) -> list[dict]`**:
   - Query effect bindings grouped by their effect index (the `effect.N` prefix):
     ```sql
     SELECT ntb.resolved_value, ntb.property, COUNT(*) AS usage_count
     FROM node_token_bindings ntb
     JOIN nodes n ON ntb.node_id = n.id
     JOIN screens s ON n.screen_id = s.id
     WHERE ntb.property LIKE 'effect%'
       AND ntb.binding_status = 'unbound'
       AND s.file_id = ?
     GROUP BY ntb.resolved_value, ntb.property
     ORDER BY usage_count DESC
     ```
   - Return list of dicts: `{"resolved_value": str, "property": str, "usage_count": int}`.

5. **`group_effects_by_composite(census: list[dict]) -> list[dict]`**:
   - Group effect bindings into composite shadows by matching their effect index across nodes.
   - Strategy: For each node_id with effect bindings, collect all `effect.N.*` properties. A composite shadow is defined by its (color, radius, offsetX, offsetY, spread) tuple.
   - Actually, since we're grouping from the census (aggregated), a simpler approach:
     - Collect unique effect indices by looking at the property prefix (e.g., `effect.0`).
     - For each unique combination of (color hex, radius value, offsetX, offsetY, spread), create one composite group.
     - Requires joining back to the raw bindings per-node to find co-occurring effect values.
   - **Simplified approach**: Query effect bindings grouped by node_id and effect index. Build composite tuples. Group identical composites.
   - Return list of composite dicts: `{"color": str, "radius": str, "offsetX": str, "offsetY": str, "spread": str, "usage_count": int, "binding_ids_by_field": dict}`.

6. **`propose_effect_name(index: int, total: int) -> str`**:
   - Map to t-shirt sizes: ["sm", "md", "lg"] or more as needed.
   - Return `f"shadow.{size}"`.

7. **`cluster_effects(conn, file_id: int, collection_id: int, mode_id: int) -> dict`**:
   - Main entry point for effect clustering.
   - Call `query_effect_census(conn, file_id)`.
   - Group into composites via `group_effects_by_composite`.
   - For each composite shadow group, sorted by radius ascending (smaller shadow = "sm"):
     - Create INDIVIDUAL atomic tokens for each field:
       - `shadow.{size}.color` -- type="color"
       - `shadow.{size}.radius` -- type="dimension"
       - `shadow.{size}.offsetX` -- type="dimension"
       - `shadow.{size}.offsetY` -- type="dimension"
       - `shadow.{size}.spread` -- type="dimension"
     - INSERT tokens and token_values.
     - UPDATE matching effect bindings: set token_id, binding_status='proposed', confidence=1.0 for exact matches.
   - For color fields that are similar (delta_e < 2.0) but not identical, merge and set confidence 0.8-0.99.
   - Return: `{"tokens_created": int, "bindings_updated": int, "shadow_groups": int}`.

8. **`ensure_radius_collection(conn, file_id: int) -> tuple[int, int]`** and **`ensure_effects_collection(conn, file_id: int) -> tuple[int, int]`**:
   - Create or retrieve "Radius" / "Effects" collections and default modes.
   - Return (collection_id, mode_id).

## Acceptance Criteria

- [ ] `python -c "from dd.cluster_misc import cluster_radius, cluster_effects, propose_radius_name, propose_effect_name, group_effects_by_composite, query_radius_census, query_effect_census"` exits 0
- [ ] `propose_radius_name(8, 0, 3)` returns `"radius.sm"`
- [ ] `propose_radius_name(12, 1, 3)` returns `"radius.md"`
- [ ] `propose_radius_name(16, 2, 3)` returns `"radius.lg"`
- [ ] `propose_effect_name(0, 3)` returns `"shadow.sm"`
- [ ] `cluster_radius` creates tokens with type="dimension" and tier="extracted"
- [ ] `cluster_radius` updates radius bindings to proposed
- [ ] `cluster_effects` creates individual atomic tokens per effect field (color, radius, offsetX, offsetY, spread)
- [ ] `cluster_effects` groups composite shadows by their co-occurring effect field values
- [ ] Effect color tokens have type="color", other effect tokens have type="dimension"
- [ ] No orphan tokens created
- [ ] Token names are unique within their collection

## Notes

- Effects are complex because each shadow is decomposed into 5 bindings at extraction time. Clustering must group these back into composites, then store them as individual atomic tokens (matching the extraction decomposition). The DTCG composite `shadow` type is assembled at export time.
- The `group_effects_by_composite` function is the most complex part. A pragmatic approach: query all effect bindings per node, pivot by effect index to reconstruct composites, then group identical composites across nodes.
- For radius clustering, the values are typically few (3-5 unique values) so the logic is straightforward.
- Effect color merging via delta_e reuses the same logic from color clustering.