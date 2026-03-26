---
taskId: TASK-035
title: "Write unit tests for all clustering modules"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-034]
produces:
  - tests/test_clustering.py
verify:
  - type: test
    command: 'pytest tests/test_clustering.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-035: Write unit tests for all clustering modules

## Spec Context

### From dd/cluster_colors.py (produced by TASK-030)

> Exports:
> - `cluster_colors(conn, file_id, collection_id, mode_id, threshold) -> dict`
> - `group_by_delta_e(colors, threshold) -> list[list[dict]]`
> - `propose_color_name(role, lightness, index, existing_names) -> str`
> - `query_color_census(conn, file_id) -> list[dict]`
> - `classify_color_role(properties) -> str`
> - `ensure_collection_and_mode(conn, file_id, collection_name) -> tuple[int, int]`

### From dd/cluster_typography.py (produced by TASK-031)

> Exports:
> - `cluster_typography(conn, file_id, collection_id, mode_id) -> dict`
> - `group_type_scale(census) -> list[dict]`
> - `propose_type_name(category, size_suffix, existing_names) -> str`
> - `query_type_census(conn, file_id) -> list[dict]`
> - `ensure_typography_collection(conn, file_id) -> tuple[int, int]`

### From dd/cluster_spacing.py (produced by TASK-032)

> Exports:
> - `cluster_spacing(conn, file_id, collection_id, mode_id) -> dict`
> - `detect_scale_pattern(values) -> tuple[float, str]`
> - `propose_spacing_name(value, base, notation, index, total) -> str`
> - `query_spacing_census(conn, file_id) -> list[dict]`
> - `ensure_spacing_collection(conn, file_id) -> tuple[int, int]`

### From dd/cluster_misc.py (produced by TASK-033)

> Exports:
> - `cluster_radius(conn, file_id, collection_id, mode_id) -> dict`
> - `cluster_effects(conn, file_id, collection_id, mode_id) -> dict`
> - `propose_radius_name(value, index, total) -> str`
> - `propose_effect_name(index, total) -> str`
> - `group_effects_by_composite(census) -> list[dict]`
> - `query_radius_census(conn, file_id) -> list[dict]`
> - `query_effect_census(conn, file_id) -> list[dict]`

### From dd/cluster.py (produced by TASK-034)

> Exports:
> - `run_clustering(conn, file_id, color_threshold, agent_id) -> dict`
> - `generate_summary(conn, file_id, results) -> dict`
> - `validate_no_orphan_tokens(conn, file_id) -> list[int]`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_extraction(db) -> sqlite3.Connection` -- inserts files, screens, nodes, bindings

### Fixture data from TASK-007

> seed_post_extraction provides:
> - 1 file (id=1)
> - 3 screens with 10 nodes
> - 15 bindings: 5 color (fill.0.color with hex values #09090B, #FFFFFF, #D4D4D8, #18181B, #09090B),
>   3 typography (fontSize=16, fontFamily=Inter, fontWeight=600),
>   3 spacing (padding.top=16, padding.bottom=16, itemSpacing=8),
>   2 radius (cornerRadius=8, cornerRadius=12),
>   2 effect (effect.0.color=#0000001A, effect.0.radius=6)
> - All bindings are binding_status="unbound"

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `tests/test_clustering.py` with comprehensive unit tests for all clustering modules. Use `@pytest.mark.unit` on all tests. Tests must use the fixture DB seeded with extraction output.

### Test Groups

**1. Color clustering tests** (prefix: `test_color_`):

- `test_color_group_by_delta_e_identical`: Two identical hex values -> 1 group
- `test_color_group_by_delta_e_similar`: #09090B and #0A0A0B (delta_e < 2.0) -> 1 group
- `test_color_group_by_delta_e_different`: #FF0000 and #0000FF -> 2 groups
- `test_color_group_preserves_usage_order`: Most-used color is group representative
- `test_color_propose_name_surface`: role="surface", produces "color.surface.primary"
- `test_color_propose_name_uniqueness`: Same role proposed twice -> different names
- `test_color_classify_role_stroke`: properties containing "stroke" -> "border"
- `test_color_classify_role_fill`: properties with only "fill" -> "surface"
- `test_color_clustering_full(db)`: Seed DB with extraction data, run `cluster_colors`. Verify:
  - Tokens created in DB with type="color" and tier="extracted"
  - Token values created with correct resolved_value
  - Bindings updated to binding_status="proposed" with token_id set
  - Confidence = 1.0 for exact matches
  - No orphan tokens
- `test_color_clustering_idempotent(db)`: Run cluster_colors twice, verify same result (second run finds no unbound bindings)

**2. Typography clustering tests** (prefix: `test_typography_`):

- `test_typography_group_type_scale_display`: font_size=32 -> category="display"
- `test_typography_group_type_scale_body`: font_size=16 -> category="body"
- `test_typography_group_type_scale_label`: font_size=12 -> category="label"
- `test_typography_group_type_scale_suffixes`: Multiple sizes in same category get lg/md/sm
- `test_typography_propose_name`: category="body", suffix="md" -> "type.body.md"
- `test_typography_clustering_full(db)`: Seed DB, run `cluster_typography`. Verify:
  - Individual atomic tokens created (fontSize, fontFamily, fontWeight)
  - Token names follow pattern "type.{category}.{suffix}.{property}"
  - Bindings updated for matching TEXT nodes
  - Confidence = 1.0

**3. Spacing clustering tests** (prefix: `test_spacing_`):

- `test_spacing_detect_scale_4px`: [4, 8, 12, 16, 24, 32] -> base=4, notation="multiplier"
- `test_spacing_detect_scale_8px`: [8, 16, 24, 32, 48] -> base=8, notation="multiplier"
- `test_spacing_detect_no_pattern`: [5, 13, 27] -> notation="tshirt"
- `test_spacing_propose_name_multiplier`: value=16, base=4 -> "space.4"
- `test_spacing_propose_name_tshirt`: notation="tshirt", index=1 -> "space.sm"
- `test_spacing_clustering_full(db)`: Seed DB, run `cluster_spacing`. Verify:
  - Tokens created for unique spacing values
  - One token shared across all spacing properties with same value
  - Bindings updated

**4. Radius clustering tests** (prefix: `test_radius_`):

- `test_radius_propose_name_3values`: 3 values -> sm, md, lg
- `test_radius_propose_name_5values`: 5 values -> xs, sm, md, lg, xl
- `test_radius_clustering_full(db)`: Seed DB, run `cluster_radius`. Verify tokens + bindings

**5. Effect clustering tests** (prefix: `test_effect_`):

- `test_effect_propose_name`: index=0, total=3 -> "shadow.sm"
- `test_effect_clustering_full(db)`: Seed DB, run `cluster_effects`. Verify:
  - Individual atomic tokens created per effect field
  - Token names follow "shadow.{size}.{field}" pattern

**6. Orchestrator tests** (prefix: `test_orchestrator_`):

- `test_orchestrator_run_clustering(db)`: Seed DB, run `run_clustering`. Verify:
  - Summary dict has all keys (total_tokens, total_bindings_updated, coverage_pct, by_type)
  - All clustering types ran (by_type has entries for color, typography, spacing, radius, effects)
  - Tokens exist for all types in DB
  - Coverage_pct > 0
- `test_orchestrator_no_orphans(db)`: Run clustering, then validate_no_orphan_tokens returns empty list
- `test_orchestrator_idempotent(db)`: Run clustering twice, second run creates 0 new tokens
- `test_orchestrator_summary(db)`: Run clustering, verify generate_summary returns correct counts matching DB

### Helper Functions

- `_seed_and_get_ids(db)`: Calls `seed_post_extraction(db)`, creates collections and modes, returns (file_id, collection_id, mode_id) for use in individual clustering tests.
- For the full orchestrator tests, just seed and call `run_clustering` which handles collection creation internally.

## Acceptance Criteria

- [ ] `pytest tests/test_clustering.py -v` passes all tests
- [ ] At least 30 test functions across the 6 groups
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB via the `db` fixture
- [ ] DB tests seed with `seed_post_extraction` from fixtures
- [ ] Color clustering tests verify delta_e grouping with exact assertions
- [ ] Typography tests verify atomic token creation (not composite)
- [ ] Spacing tests verify scale pattern detection
- [ ] Orchestrator tests verify full pipeline integration
- [ ] Idempotency verified: second run produces 0 new tokens
- [ ] No orphan tokens after any clustering operation
- [ ] Token name uniqueness verified within each collection
- [ ] `pytest tests/test_clustering.py -v --tb=short` exits 0

## Notes

- Use `seed_post_extraction` from `tests.fixtures` to set up the DB. This provides realistic extraction output (15 bindings across 5 types).
- For the full clustering tests, you need to create collection + mode first (via the `ensure_*` functions), OR use `run_clustering` which does it automatically.
- The fixture data has limited variety (5 colors, 1 type scale entry, 2 spacing values, 2 radius values, 2 effect values). Tests should still verify the clustering logic works correctly with this data.
- Pure function tests (group_by_delta_e, detect_scale_pattern, propose_*_name) don't need DB access.
- Use `@pytest.mark.timeout(30)` on DB-heavy tests as a safety net.