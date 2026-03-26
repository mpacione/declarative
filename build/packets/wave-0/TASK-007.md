---
taskId: TASK-007
title: "Create shared test infrastructure"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - tests/conftest.py
  - tests/fixtures.py
verify:
  - type: typecheck
    command: 'python -c "from tests.fixtures import seed_post_extraction, seed_post_clustering, seed_post_curation, seed_post_validation, make_mock_figma_response"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_fixtures_smoke.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-007: Create shared test infrastructure

## Spec Context

### From Task Decomposition Guide -- Testing Strategy

> **Fixture DB seeding pattern:** The `tests/fixtures.py` module provides factory functions:
> - `seed_post_extraction(db)` -- inserts files, screens, nodes, bindings matching mock Figma data
> - `seed_post_clustering(db)` -- above + tokens, token_values, updated bindings
> - `seed_post_curation(db)` -- above + accepted/merged tokens, all tiers set
> - `seed_post_validation(db)` -- above + export_validations rows, all checks passing
> Each factory uses deterministic data (fixed node IDs, predictable color values) so assertions are exact, not heuristic.

> **Pytest configuration:**
> - Use `pytest-xdist` for parallel execution within a test level (`-n auto`)
> - Use `pytest-timeout` with 30s default to catch infinite loops or deadlocks in clustering
> - Use `pytest-cov` to track coverage -- target 80%+ on `dd/` module
> - Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e` for selective runs
> - E2e tests should be marked `@pytest.mark.slow` for optional exclusion during development

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

### From dd/types.py (produced by TASK-003)

> Exports: `DeviceClass`, `BindingStatus`, `Tier`, `SyncStatus`, `RunStatus`, `ScreenExtractionStatus`, `Severity`, `DTCGType`, `classify_device`, `is_component_sheet_name`

### From schema.sql -- Key Tables

> ```sql
> CREATE TABLE files (
>     id INTEGER PRIMARY KEY, file_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
>     last_modified TEXT, extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     node_count INTEGER, screen_count INTEGER, metadata TEXT
> );
>
> CREATE TABLE screens (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_node_id TEXT NOT NULL, name TEXT NOT NULL,
>     width REAL NOT NULL, height REAL NOT NULL, device_class TEXT,
>     node_count INTEGER, extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(file_id, figma_node_id)
> );
>
> CREATE TABLE nodes (
>     id INTEGER PRIMARY KEY, screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id TEXT NOT NULL, parent_id INTEGER REFERENCES nodes(id),
>     path TEXT, name TEXT NOT NULL, node_type TEXT NOT NULL,
>     depth INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
>     is_semantic INTEGER NOT NULL DEFAULT 0, component_id INTEGER REFERENCES components(id),
>     x REAL, y REAL, width REAL, height REAL,
>     layout_mode TEXT, padding_top REAL, padding_right REAL, padding_bottom REAL, padding_left REAL,
>     item_spacing REAL, counter_axis_spacing REAL, primary_align TEXT, counter_align TEXT,
>     layout_sizing_h TEXT, layout_sizing_v TEXT,
>     fills TEXT, strokes TEXT, effects TEXT, corner_radius TEXT,
>     opacity REAL DEFAULT 1.0, blend_mode TEXT DEFAULT 'NORMAL', visible INTEGER NOT NULL DEFAULT 1,
>     font_family TEXT, font_weight INTEGER, font_size REAL,
>     line_height TEXT, letter_spacing TEXT, text_align TEXT, text_content TEXT,
>     extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(screen_id, figma_node_id)
> );
>
> CREATE TABLE node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL,
>     confidence REAL, binding_status TEXT NOT NULL DEFAULT 'unbound'
>     CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden')),
>     UNIQUE(node_id, property)
> );
>
> CREATE TABLE token_collections (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_id TEXT, name TEXT NOT NULL, description TEXT,
>     created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
>
> CREATE TABLE token_modes (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id TEXT, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted' CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of INTEGER REFERENCES tokens(id), description TEXT,
>     figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending' CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL,
>     extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
>
> CREATE TABLE extraction_runs (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     completed_at TEXT, agent_id TEXT, total_screens INTEGER,
>     extracted_screens INTEGER DEFAULT 0,
>     status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed', 'cancelled'))
> );
>
> CREATE TABLE screen_extraction_status (
>     id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
>     screen_id INTEGER NOT NULL REFERENCES screens(id),
>     status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
>     started_at TEXT, completed_at TEXT, node_count INTEGER, binding_count INTEGER, error TEXT,
>     UNIQUE(run_id, screen_id)
> );
>
> CREATE TABLE export_validations (
>     id INTEGER PRIMARY KEY, run_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     check_name TEXT NOT NULL, severity TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
>     message TEXT NOT NULL, affected_ids TEXT, resolved INTEGER NOT NULL DEFAULT 0
> );
> ```

## Task

Create the shared test infrastructure that all subsequent test tasks depend on. This includes the pytest configuration, shared fixtures, and DB seeding factories.

### 1. `tests/conftest.py`

Create a pytest conftest with:

- **Custom markers registration**: Register `unit`, `integration`, `e2e`, and `slow` markers.
- **`@pytest.fixture` `db`**: Returns an in-memory SQLite connection with the full schema initialized via `dd.db.init_db(":memory:")`. Auto-closes after each test.
- **`@pytest.fixture` `db_with_file`**: Calls `db` fixture, then inserts a default file row: `INSERT INTO files (id, file_key, name, node_count, screen_count) VALUES (1, 'test_file_key_abc123', 'Test File', 100, 5)`. Returns the connection.
- **Timeout configuration**: Set `@pytest.fixture(autouse=True)` to apply a 30-second timeout to all tests (or configure via `pytest.ini`-style config in conftest using `pytest_configure`).

### 2. `tests/fixtures.py`

Create factory functions that seed a DB at progressive pipeline stages. Each function accepts a `sqlite3.Connection` and returns it after seeding. Use **deterministic** data throughout -- fixed IDs, predictable values.

**`seed_post_extraction(db) -> sqlite3.Connection`**:
- Insert 1 file row (id=1, file_key="test_file_key_abc123", name="Test Design File")
- Insert 3 screens:
  - (id=1, file_id=1, figma_node_id="100:1", name="Home", width=428, height=926, device_class="iphone", node_count=10)
  - (id=2, file_id=1, figma_node_id="100:2", name="Settings", width=428, height=926, device_class="iphone", node_count=8)
  - (id=3, file_id=1, figma_node_id="100:3", name="Buttons and Controls", width=1200, height=800, device_class="component_sheet", node_count=5)
- Insert 10 nodes across screens (mix of FRAME, TEXT, RECTANGLE, INSTANCE types):
  - Screen 1: 5 nodes forming a simple tree (1 root FRAME, 2 child FRAMEs, 1 TEXT, 1 RECTANGLE)
  - Screen 2: 3 nodes (1 root FRAME, 1 TEXT, 1 INSTANCE)
  - Screen 3: 2 nodes (1 root FRAME, 1 COMPONENT)
  - Each node gets: figma_node_id (like "200:N"), name, node_type, depth, sort_order, path, is_semantic
  - Some nodes have fills (JSON), font properties, layout properties
- Insert 15 bindings in `node_token_bindings`:
  - 5 color bindings (fill.0.color) with known hex values: #09090B, #FFFFFF, #D4D4D8, #18181B, #09090B (duplicate for coverage testing)
  - 3 typography bindings: fontSize=16, fontFamily=Inter, fontWeight=600
  - 3 spacing bindings: padding.top=16, padding.bottom=16, itemSpacing=8
  - 2 radius bindings: cornerRadius=8, cornerRadius=12
  - 2 effect bindings: effect.0.color=#0000001A, effect.0.radius=6
  - All bindings: binding_status="unbound", token_id=NULL
- Insert 1 extraction_run (status="completed") and corresponding screen_extraction_status rows

**`seed_post_clustering(db) -> sqlite3.Connection`**:
- Call `seed_post_extraction(db)` first.
- Insert 1 token_collection (id=1, file_id=1, name="Colors")
- Insert 1 token_mode (id=1, collection_id=1, name="Default", is_default=1)
- Insert 4 tokens in the Colors collection:
  - (id=1, name="color.surface.primary", type="color", tier="extracted")
  - (id=2, name="color.surface.secondary", type="color", tier="extracted")
  - (id=3, name="color.border.default", type="color", tier="extracted")
  - (id=4, name="color.text.primary", type="color", tier="extracted")
- Insert 4 token_values (one per token, mode_id=1, resolved_values: #09090B, #18181B, #D4D4D8, #FFFFFF)
- Update 5 color bindings: set token_id to appropriate token, binding_status="proposed", confidence=1.0 or 0.95
- Insert 1 more collection for spacing, 1 token for space.4 with value "16"

**`seed_post_curation(db) -> sqlite3.Connection`**:
- Call `seed_post_clustering(db)` first.
- Update tokens: change tier from "extracted" to "curated" for all 4 color tokens and 1 spacing token
- Update bindings: change binding_status from "proposed" to "bound"

**`seed_post_validation(db) -> sqlite3.Connection`**:
- Call `seed_post_curation(db)` first.
- Insert export_validations rows (all passing):
  - (check_name="mode_completeness", severity="info", message="All tokens have all mode values")
  - (check_name="name_dtcg_compliant", severity="info", message="All names valid")
  - (check_name="orphan_tokens", severity="info", message="No orphan tokens")
  - (check_name="name_uniqueness", severity="info", message="All names unique")

**`make_mock_figma_response(screen_name: str, node_count: int = 10) -> list[dict]`**:
- Returns a list of dicts matching the shape returned by `use_figma` screen extraction.
- Each dict has keys: `figma_node_id`, `name`, `node_type`, `depth`, `sort_order`, `x`, `y`, `width`, `height`.
- Optional keys: `fills` (JSON string), `font_family`, `font_size`, `font_weight`, `line_height`, `layout_mode`, `padding_top`, etc.
- Generate a simple tree: 1 root FRAME + `node_count - 1` children of mixed types.
- Use deterministic data based on `screen_name` for reproducibility.

### 3. `tests/test_fixtures_smoke.py`

Create a small smoke test that validates the fixtures work:

- Test `seed_post_extraction`: verify file count, screen count, node count, binding count, all bindings are unbound
- Test `seed_post_clustering`: verify tokens exist, bindings have token_ids, binding_status is proposed
- Test `seed_post_curation`: verify tokens are curated, bindings are bound
- Test `seed_post_validation`: verify export_validations rows exist
- Test `make_mock_figma_response`: verify it returns a list of dicts with expected keys

Mark all tests with `@pytest.mark.unit`.

## Acceptance Criteria

- [ ] `python -c "from tests.fixtures import seed_post_extraction, seed_post_clustering, seed_post_curation, seed_post_validation, make_mock_figma_response"` exits 0
- [ ] `python -c "from tests.conftest import *"` exits 0 (conftest is importable)
- [ ] `pytest tests/test_fixtures_smoke.py -v` passes all tests
- [ ] `seed_post_extraction` inserts at least 3 screens, 10 nodes, 15 bindings
- [ ] `seed_post_clustering` extends extraction data with tokens and proposed bindings
- [ ] `seed_post_curation` promotes tokens to curated and bindings to bound
- [ ] `seed_post_validation` adds export_validation rows
- [ ] `make_mock_figma_response` returns a list of dicts with `figma_node_id` and `node_type` keys
- [ ] All fixture functions accept a `sqlite3.Connection` and return the same connection
- [ ] All fixture data uses deterministic values (no random/timestamp-dependent data except DB defaults)
- [ ] `pytest --co -q tests/` lists tests and shows registered markers without errors

## Notes

- The conftest must register custom markers to avoid pytest warnings. Use `pytest_configure` hook:
  ```python
  def pytest_configure(config):
      config.addinivalue_line("markers", "unit: unit tests")
      config.addinivalue_line("markers", "integration: integration tests")
      config.addinivalue_line("markers", "e2e: end-to-end tests")
      config.addinivalue_line("markers", "slow: slow tests (e2e)")
  ```
- Factory functions should use `db.executemany` for bulk inserts where possible for clarity.
- The `seed_*` functions are additive -- each calls the previous stage. This models the real pipeline progression.
- Use explicit column lists in INSERT statements (not `INSERT INTO table VALUES (...)`) for maintainability.
- The `make_mock_figma_response` function doesn't touch the DB -- it returns raw data matching what the extraction pipeline would receive from `use_figma`.