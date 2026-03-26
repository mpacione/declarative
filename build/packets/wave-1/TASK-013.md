---
taskId: TASK-013
title: "Implement materialized path computation"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-011]
produces:
  - dd/paths.py
verify:
  - type: typecheck
    command: 'python -c "from dd.paths import compute_paths, is_node_semantic"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.paths import compute_paths; from dd.db import init_db; conn = init_db(\":memory:\"); conn.execute(\"INSERT INTO files (id, file_key, name) VALUES (1, ''k'', ''f'')\"); conn.execute(\"INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, ''s1'', ''Screen'', 428, 926)\"); conn.execute(\"INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order) VALUES (1, 1, ''n1'', ''Root'', ''FRAME'', 0, 0)\"); conn.execute(\"INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, parent_id) VALUES (2, 1, ''n2'', ''Child'', ''TEXT'', 1, 0, 1)\"); conn.commit(); compute_paths(conn, 1); row = conn.execute(\"SELECT path FROM nodes WHERE id=2\").fetchone(); print(row[0]); assert row[0] == \"0.0\""'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-013: Implement materialized path computation

## Spec Context

### From Technical Design Spec -- Materialized path computation

> Each node gets a `path` string computed from its position in the tree. Root nodes get path `"0"`, `"1"`, etc. (by sort_order). Children append `.{sort_order}`: `"0.2.1"` means first root child -> third child -> second child. Computed bottom-up after the full tree is written, since parent IDs must resolve first.
>
> This enables efficient subtree queries without recursive CTEs:
> ```sql
> -- All descendants of the node with path '0.3'
> SELECT * FROM nodes WHERE path LIKE '0.3.%' AND screen_id = ?;
> ```

### From Technical Design Spec -- is_semantic computation

> A node is flagged `is_semantic = 1` if ANY of these are true:
> 1. `node_type` is TEXT, INSTANCE, or COMPONENT.
> 2. `node_type` is FRAME and `layout_mode` is not NULL (auto-layout container).
> 3. Node `name` does not start with "Frame", "Group", "Rectangle", or "Vector" (user-renamed = intentional).
> 4. Node has >= 2 children and at least one child is `is_semantic` (meaningful parent).
>
> Everything else gets `is_semantic = 0`.

### From schema.sql -- nodes table (path and is_semantic columns)

> ```sql
> CREATE TABLE IF NOT EXISTS nodes (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     parent_id       INTEGER REFERENCES nodes(id),
>     path            TEXT,
>     name            TEXT NOT NULL,
>     node_type       TEXT NOT NULL,
>     depth           INTEGER NOT NULL DEFAULT 0,
>     sort_order      INTEGER NOT NULL DEFAULT 0,
>     is_semantic     INTEGER NOT NULL DEFAULT 0,
>     ...
>     layout_mode     TEXT,
>     ...
>     UNIQUE(screen_id, figma_node_id)
> );
> ```

### From dd/types.py (produced by TASK-003)

> Exports:
> - `SEMANTIC_NODE_TYPES: frozenset[str]` = frozenset({"TEXT", "INSTANCE", "COMPONENT"})
> - `NON_SEMANTIC_PREFIXES: tuple[str, ...]` = ("Frame", "Group", "Rectangle", "Vector")

## Task

Create `dd/paths.py` with functions to compute materialized paths and update `is_semantic` flags for nodes in a screen. These are run after `insert_nodes` (TASK-011) has populated the nodes table.

1. **`compute_paths(conn, screen_id: int) -> None`**:
   - Query all nodes for the given `screen_id`, ordered by `depth ASC, sort_order ASC`.
   - Build an in-memory dict: `node_id -> { parent_id, sort_order, path }`.
   - **Root nodes** (parent_id is NULL): assign path = `str(sort_order)`. Among root nodes, sort by `sort_order` and assign paths "0", "1", "2", etc. based on their sort_order position index (not the raw sort_order value -- use the index in the sorted list).
   - Actually, use `sort_order` directly as the path component for simplicity since sort_order already represents position among siblings. Root nodes get path = `str(sort_order)`.
   - **Child nodes**: path = `parent_path + "." + str(sort_order)`.
   - Process nodes in depth order (depth 0 first, then depth 1, etc.) so parents always have paths before children.
   - After computing all paths, batch UPDATE the `nodes` table: `UPDATE nodes SET path = ? WHERE id = ?`.
   - Commit.

2. **`compute_is_semantic(conn, screen_id: int) -> None`**:
   - Query all nodes for the given `screen_id`.
   - Build a tree structure in memory (parent_id -> list of children).
   - **First pass** (forward/top-down -- apply rules 1-3):
     - Rule 1: If `node_type` in SEMANTIC_NODE_TYPES, set is_semantic = 1.
     - Rule 2: If `node_type == "FRAME"` and `layout_mode` is not None, set is_semantic = 1.
     - Rule 3: If `name` does not start with any prefix in NON_SEMANTIC_PREFIXES, set is_semantic = 1.
   - **Second pass** (bottom-up -- apply rule 4):
     - Process nodes from deepest to shallowest (sort by depth DESC).
     - For each node: count its children, count how many children are is_semantic.
     - If a node has >= 2 children and at least 1 child is_semantic, set is_semantic = 1.
   - Batch UPDATE the `nodes` table: `UPDATE nodes SET is_semantic = ? WHERE id = ?`.
   - Commit.

3. **`compute_paths_and_semantics(conn, screen_id: int) -> None`**:
   - Convenience function that calls `compute_paths(conn, screen_id)` then `compute_is_semantic(conn, screen_id)`.
   - This is the function the orchestrator (TASK-014) will call.

## Acceptance Criteria

- [ ] `python -c "from dd.paths import compute_paths, compute_is_semantic, compute_paths_and_semantics"` exits 0
- [ ] Root node with sort_order=0 gets path "0"
- [ ] Child node with sort_order=2 under root path "0" gets path "0.2"
- [ ] Grandchild with sort_order=1 under path "0.2" gets path "0.2.1"
- [ ] Multiple root nodes get paths "0", "1", "2" etc. by sort_order
- [ ] TEXT node is marked is_semantic = 1
- [ ] INSTANCE node is marked is_semantic = 1
- [ ] FRAME with layout_mode="HORIZONTAL" is marked is_semantic = 1
- [ ] FRAME with layout_mode=NULL and name="Frame 1" is marked is_semantic = 0
- [ ] Node named "MyCustomName" (no default prefix) is marked is_semantic = 1
- [ ] Parent with 2+ children where one is semantic is marked is_semantic = 1
- [ ] Parent with 1 child that is semantic is NOT promoted by rule 4 (need >= 2 children)
- [ ] All paths are valid strings matching pattern `^\d+(\.\d+)*$`
- [ ] `compute_paths_and_semantics` runs both operations without error

## Notes

- The `sort_order` value comes from Figma's children array index. It's 0-based and represents sibling position.
- Path computation is straightforward because we process by depth level. All parents at depth N are processed before children at depth N+1.
- The `is_semantic` computation's rule 4 (bottom-up parent promotion) requires processing deepest nodes first. This is the only rule that depends on children's semantic status.
- Performance: For a screen with ~200 nodes, this is trivial. The batch UPDATE is the only DB operation.