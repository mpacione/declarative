---
taskId: TASK-034
title: "Implement clustering orchestrator"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-030, TASK-031, TASK-032, TASK-033]
produces:
  - dd/cluster.py
verify:
  - type: typecheck
    command: 'python -c "from dd.cluster import run_clustering"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_clustering.py -k orchestrator -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-034: Implement clustering orchestrator

## Spec Context

### From Task Decomposition Guide -- Wave 3

> TASK-034: Implement clustering orchestrator -- run all clustering in sequence; create default token_collection + token_mode; summary report: N tokens proposed, M bindings assigned, L flagged.

### From Technical Design Spec -- Phase 5: Clustering + Token Proposal

> **Output:**
> - New rows in `tokens` (tier = `extracted`).
> - New rows in `token_values` (one per mode -- default mode initially, additional modes when added).
> - Updated `node_token_bindings` -- `token_id` set, `binding_status` flipped to `proposed`, `confidence` set (1.0 for exact match, 0.8-0.99 for delta-E-merged).

### From User Requirements Spec -- UC-2: Cluster

> - System produces a clear summary: N tokens proposed across K types, M bindings assigned, L bindings flagged for review.
> - No token is created with 0 bindings (orphan tokens).
> - >= 90% of `unbound` bindings are assigned a proposed token.

### From schema.sql -- v_curation_progress view

> ```sql
> CREATE VIEW v_curation_progress AS
> SELECT
>     binding_status,
>     COUNT(*) AS binding_count,
>     ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings
> GROUP BY binding_status
> ORDER BY
>     CASE binding_status
>         WHEN 'bound' THEN 1
>         WHEN 'proposed' THEN 2
>         WHEN 'overridden' THEN 3
>         WHEN 'unbound' THEN 4
>     END;
> ```

### From schema.sql -- extraction_locks table

> ```sql
> CREATE TABLE IF NOT EXISTS extraction_locks (
>     id              INTEGER PRIMARY KEY,
>     resource        TEXT NOT NULL UNIQUE,
>     agent_id        TEXT NOT NULL,
>     acquired_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     expires_at      TEXT NOT NULL
> );
> ```

### From dd/cluster_colors.py (produced by TASK-030)

> Exports:
> - `cluster_colors(conn, file_id, collection_id, mode_id, threshold) -> dict`
> - `ensure_collection_and_mode(conn, file_id, collection_name) -> tuple[int, int]`

### From dd/cluster_typography.py (produced by TASK-031)

> Exports:
> - `cluster_typography(conn, file_id, collection_id, mode_id) -> dict`
> - `ensure_typography_collection(conn, file_id) -> tuple[int, int]`

### From dd/cluster_spacing.py (produced by TASK-032)

> Exports:
> - `cluster_spacing(conn, file_id, collection_id, mode_id) -> dict`
> - `ensure_spacing_collection(conn, file_id) -> tuple[int, int]`

### From dd/cluster_misc.py (produced by TASK-033)

> Exports:
> - `cluster_radius(conn, file_id, collection_id, mode_id) -> dict`
> - `cluster_effects(conn, file_id, collection_id, mode_id) -> dict`
> - `ensure_radius_collection(conn, file_id) -> tuple[int, int]`
> - `ensure_effects_collection(conn, file_id) -> tuple[int, int]`

## Task

Create `dd/cluster.py` -- the clustering orchestrator that runs all clustering modules in sequence for a given file. This is the main entry point for Phase 5.

1. **`run_clustering(conn, file_id: int, color_threshold: float = 2.0, agent_id: str = "clustering") -> dict`**:
   - Main entry point. Runs all clustering phases in order:
     a. Acquire advisory lock: INSERT into `extraction_locks` with resource="clustering", agent_id, expires_at = now + 10 minutes. If lock already exists and not expired, raise an error or wait.
     b. Create collections and modes:
        - `ensure_collection_and_mode(conn, file_id, "Colors")` -> (color_coll_id, color_mode_id)
        - `ensure_typography_collection(conn, file_id)` -> (type_coll_id, type_mode_id)
        - `ensure_spacing_collection(conn, file_id)` -> (spacing_coll_id, spacing_mode_id)
        - `ensure_radius_collection(conn, file_id)` -> (radius_coll_id, radius_mode_id)
        - `ensure_effects_collection(conn, file_id)` -> (effects_coll_id, effects_mode_id)
     c. Run clustering in sequence:
        - `color_result = cluster_colors(conn, file_id, color_coll_id, color_mode_id, color_threshold)`
        - `type_result = cluster_typography(conn, file_id, type_coll_id, type_mode_id)`
        - `spacing_result = cluster_spacing(conn, file_id, spacing_coll_id, spacing_mode_id)`
        - `radius_result = cluster_radius(conn, file_id, radius_coll_id, radius_mode_id)`
        - `effects_result = cluster_effects(conn, file_id, effects_coll_id, effects_mode_id)`
     d. Release advisory lock: DELETE from `extraction_locks` WHERE resource="clustering".
     e. Generate summary report.
   - Print progress to stdout:
     ```
     [Clustering] Colors: N tokens, M bindings
     [Clustering] Typography: N tokens, M bindings
     [Clustering] Spacing: N tokens, M bindings
     [Clustering] Radius: N tokens, M bindings
     [Clustering] Effects: N tokens, M bindings
     ```

2. **`generate_summary(conn, file_id: int, results: dict) -> dict`**:
   - Query `v_curation_progress` to get overall binding status breakdown.
   - Count total tokens: `SELECT COUNT(*) FROM tokens t JOIN token_collections tc ON t.collection_id = tc.id WHERE tc.file_id = ?`.
   - Count total bindings updated: sum of all bindings_updated from individual results.
   - Count remaining unbound: from curation_progress view.
   - Calculate coverage: proposed_pct = (proposed + bound) / total * 100.
   - Return summary dict:
     ```python
     {
         "total_tokens": int,
         "total_bindings_updated": int,
         "remaining_unbound": int,
         "coverage_pct": float,
         "by_type": {
             "color": {"tokens": int, "bindings": int},
             "typography": {"tokens": int, "bindings": int},
             "spacing": {"tokens": int, "bindings": int},
             "radius": {"tokens": int, "bindings": int},
             "effects": {"tokens": int, "bindings": int},
         },
         "curation_progress": [{"status": str, "count": int, "pct": float}, ...]
     }
     ```

3. **`validate_no_orphan_tokens(conn, file_id: int) -> list[int]`**:
   - Query tokens that have zero bindings:
     ```sql
     SELECT t.id FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
     WHERE tc.file_id = ? AND ntb.id IS NULL
     ```
   - If any orphan tokens found, DELETE them and return the list of deleted IDs.
   - This cleanup runs at the end of clustering to enforce UC-2's no-orphan requirement.

4. **Error handling**:
   - If any individual clustering step fails, catch the exception, log it, and continue with remaining steps. The orchestrator should not abort on a single clustering failure.
   - Release the advisory lock in a `finally` block to prevent lock leaks.
   - Return partial results with an `errors` key listing which steps failed.

5. **Print final summary to stdout**:
   ```
   === Clustering Summary ===
   Total tokens proposed: N across K types
   Bindings assigned: M
   Bindings flagged (unbound): L
   Coverage: XX.X%
   ```

## Acceptance Criteria

- [ ] `python -c "from dd.cluster import run_clustering, generate_summary, validate_no_orphan_tokens"` exits 0
- [ ] `run_clustering` calls all 5 clustering modules in sequence
- [ ] `run_clustering` acquires and releases advisory lock
- [ ] `run_clustering` returns summary dict with total_tokens, total_bindings_updated, coverage_pct
- [ ] `generate_summary` queries v_curation_progress and returns correct breakdown
- [ ] `validate_no_orphan_tokens` finds and deletes tokens with zero bindings
- [ ] If one clustering step fails, others still run (partial failure handling)
- [ ] Advisory lock is released even if clustering fails (finally block)
- [ ] Summary printed to stdout shows per-type and overall statistics
- [ ] Collections and modes are created idempotently (re-running is safe)
- [ ] `run_clustering` is idempotent -- running twice produces same results (existing proposed bindings are skipped by census queries filtering on unbound status)

## Notes

- The orchestrator is the main entry point an agent calls after extraction completes. It's a simple sequence runner -- the individual clustering modules do the heavy lifting.
- The advisory lock prevents concurrent clustering on the same DB. The `resource = "clustering"` lock is exclusive.
- Idempotency is ensured by: (1) each census query filters for `binding_status = 'unbound'`, so already-proposed bindings are skipped; (2) collection/mode creation uses INSERT OR IGNORE; (3) token creation uses UPSERT on (collection_id, name).
- The `validate_no_orphan_tokens` cleanup is a safety net. In normal operation, tokens without bindings shouldn't be created, but race conditions or partial failures could leave orphans.