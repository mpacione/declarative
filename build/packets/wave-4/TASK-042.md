---
taskId: TASK-042
title: "Implement curation progress reporting"
wave: wave-4
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/status.py
verify:
  - type: typecheck
    command: 'python -c "from dd.status import get_curation_progress, get_token_coverage, get_unbound_summary, get_export_readiness, format_status_report"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_curation.py -k status -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-042: Implement curation progress reporting

## Spec Context

### From Task Decomposition Guide -- Wave 4

> TASK-042: Implement curation progress reporting -- query v_curation_progress, v_token_coverage, v_unbound, v_export_readiness; format as structured report.

### From User Requirements Spec -- FR-5: Query Interface

> FR-5.8: Export readiness view (`v_export_readiness`) -- aggregated pre-export validation results grouped by check name and severity.
> FR-5.9: Curation progress view (`v_curation_progress`) -- aggregate breakdown of unbound/proposed/bound/overridden bindings as counts and percentages for tracking overall workflow completion.

### From Technical Design Spec -- Agent Cookbook Query #6

> ```sql
> SELECT * FROM v_curation_progress;
> -- Returns: bound 72.3%, proposed 18.1%, overridden 0.4%, unbound 9.2%
> ```

### From Technical Design Spec -- Agent Cookbook Query #5

> ```sql
> SELECT * FROM v_token_coverage WHERE binding_count > 0;
> ```

### From Technical Design Spec -- Agent Cookbook Query #10

> ```sql
> SELECT * FROM v_export_readiness;
> -- Shows: mode_completeness: 0 errors, name_dtcg_compliant: 0 errors, orphan_tokens: 2 warnings
> ```

### From schema.sql -- Relevant views

> ```sql
> CREATE VIEW v_curation_progress AS
> SELECT
>     binding_status,
>     COUNT(*) AS binding_count,
>     ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings
> GROUP BY binding_status
> ORDER BY CASE binding_status WHEN 'bound' THEN 1 WHEN 'proposed' THEN 2
>          WHEN 'overridden' THEN 3 WHEN 'unbound' THEN 4 END;
>
> CREATE VIEW v_token_coverage AS
> SELECT
>     t.name AS token_name, t.type AS token_type, t.tier, t.collection_id,
>     COUNT(ntb.id) AS binding_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>     COUNT(DISTINCT n.screen_id) AS screen_count
> FROM tokens t
> LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
> LEFT JOIN nodes n ON ntb.node_id = n.id
> GROUP BY t.id ORDER BY binding_count DESC;
>
> CREATE VIEW v_unbound AS
> SELECT
>     ntb.id AS binding_id, s.name AS screen_name, s.file_id,
>     n.name AS node_name, n.node_type, ntb.property, ntb.resolved_value
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id
> JOIN screens s ON n.screen_id = s.id
> WHERE ntb.token_id IS NULL ORDER BY ntb.resolved_value;
>
> CREATE VIEW v_export_readiness AS
> SELECT
>     check_name, severity, COUNT(*) AS issue_count, SUM(resolved) AS resolved_count
> FROM export_validations
> WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
> GROUP BY check_name, severity
> ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;
> ```

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `dd/status.py` implementing curation progress and export readiness reporting. This module queries the DB views and formats structured reports for agent consumption.

1. **`get_curation_progress(conn) -> list[dict]`**:
   - Query `v_curation_progress`.
   - Return list of dicts: `[{"status": str, "count": int, "pct": float}, ...]`.
   - Handle empty table (no bindings): return empty list.

2. **`get_token_coverage(conn, file_id: int | None = None) -> list[dict]`**:
   - Query `v_token_coverage`.
   - If `file_id` is provided, add a JOIN to filter by file_id through the collection.
   - Return list of dicts: `[{"token_name": str, "token_type": str, "tier": str, "binding_count": int, "node_count": int, "screen_count": int}, ...]`.
   - Sort by binding_count descending.

3. **`get_unbound_summary(conn, file_id: int | None = None, limit: int = 50) -> list[dict]`**:
   - Query `v_unbound`.
   - If `file_id` is provided, filter by `s.file_id = ?`.
   - Limit results to `limit` rows.
   - Return list of dicts: `[{"binding_id": int, "screen_name": str, "node_name": str, "node_type": str, "property": str, "resolved_value": str}, ...]`.

4. **`get_export_readiness(conn) -> list[dict]`**:
   - Query `v_export_readiness`.
   - Return list of dicts: `[{"check_name": str, "severity": str, "issue_count": int, "resolved_count": int}, ...]`.
   - If no validation has been run (empty result), return empty list.

5. **`format_status_report(conn, file_id: int | None = None) -> str`**:
   - Build a human-readable text report combining all status queries:
     ```
     === Curation Progress ===
     bound:      N bindings (XX.X%)
     proposed:   N bindings (XX.X%)
     overridden: N bindings (XX.X%)
     unbound:    N bindings (XX.X%)

     === Token Coverage ===
     Total tokens: N
     Top tokens by usage:
       color.surface.primary  (color)  - 45 bindings across 12 screens
       space.4                (dimension) - 30 bindings across 8 screens
       ...

     === Unbound Bindings ===
     N bindings remain unbound
     Top values: #ABC123 (5x), 24px (3x), ...

     === Export Readiness ===
     [not yet validated]
     -- or --
     PASS: 0 errors, 2 warnings
     Warnings:
       orphan_tokens: 2 issues
     ```
   - Return the formatted string.

6. **`get_status_dict(conn, file_id: int | None = None) -> dict`**:
   - Return a structured dict combining all status data:
     ```python
     {
         "curation_progress": list[dict],
         "token_count": int,
         "token_coverage": list[dict],  # top 10 only
         "unbound_count": int,
         "export_readiness": list[dict],
         "is_ready": bool  # True if no error-severity issues
     }
     ```
   - This is the machine-readable version of `format_status_report`.

## Acceptance Criteria

- [ ] `python -c "from dd.status import get_curation_progress, get_token_coverage, get_unbound_summary, get_export_readiness, format_status_report, get_status_dict"` exits 0
- [ ] `get_curation_progress` returns list of dicts with status, count, pct keys
- [ ] `get_curation_progress` returns empty list for DB with no bindings
- [ ] `get_token_coverage` returns list with token_name, binding_count, etc.
- [ ] `get_token_coverage` with file_id filters to that file's tokens
- [ ] `get_unbound_summary` returns at most `limit` rows
- [ ] `get_export_readiness` returns empty list when no validation has been run
- [ ] `format_status_report` returns a non-empty string with section headers
- [ ] `get_status_dict` returns a dict with all required keys
- [ ] `get_status_dict` `is_ready` is False when no validation has been run
- [ ] All functions handle empty DB gracefully (no crashes, return empty/default values)

## Notes

- This module is read-only -- it queries views and tables but never modifies data.
- The `format_status_report` function produces human-readable output for the agent to present to the user. The `get_status_dict` function produces machine-readable output for programmatic use.
- The `v_curation_progress` view can fail with a division-by-zero if `node_token_bindings` is empty. The function should handle this gracefully.
- For `get_token_coverage`, the view already does a GROUP BY on `t.id`. To filter by `file_id`, join through `token_collections`.