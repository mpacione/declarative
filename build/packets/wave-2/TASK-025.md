---
taskId: TASK-025
title: "Write unit tests for component extraction"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-020, TASK-021, TASK-022, TASK-023]
produces:
  - tests/test_components.py
verify:
  - type: test
    command: 'pytest tests/test_components.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-025: Write unit tests for component extraction

## Spec Context

### From dd/extract_components.py (produced by TASK-020, TASK-021, TASK-022, TASK-023)

> Exports:
> - `INTERACTION_STATE_VALUES: frozenset[str]` -- {"default", "hover", "focus", "pressed", "disabled", "selected", "loading"}
> - `CATEGORY_KEYWORDS: dict[str, list[str]]` -- maps categories to name keywords
> - `ROLE_MAP: dict[str, str]` -- maps categories to ARIA roles
> - `INTERACTIVE_CATEGORIES: frozenset[str]` -- {"button", "input", "nav", "modal"}
> - `NON_SLOT_HEURISTICS: set[str]` -- {"background", "bg", "divider", "separator", "spacer", ...}
>
> Functions:
> - `infer_category(name: str) -> str | None`
> - `parse_variant_properties(variant_name: str) -> dict[str, str]`
> - `detect_interaction_axis(axis_name: str, axis_values: list[str]) -> bool`
> - `parse_component_set(component_set_data: dict) -> dict`
> - `parse_standalone_component(component_data: dict) -> dict`
> - `insert_component(conn, file_id, component_data) -> int`
> - `insert_variants(conn, component_id, variants) -> list[int]`
> - `insert_variant_axes(conn, component_id, axes) -> list[int]`
> - `populate_variant_dimension_values(conn, component_id) -> int`
> - `infer_slot_type(child: dict) -> str`
> - `infer_slots(children: list[dict]) -> list[dict]`
> - `insert_slots(conn, component_id, slots) -> list[int]`
> - `infer_a11y(category: str | None, name: str) -> dict`
> - `insert_a11y(conn, component_id, a11y_data) -> int`
> - `extract_components(conn, file_id, component_nodes) -> list[int]`

### Mock Component Data Shape

> A COMPONENT_SET from Figma:
> ```python
> {
>     "id": "500:1", "name": "button", "type": "COMPONENT_SET",
>     "description": "Primary button component",
>     "children": [
>         {"id": "500:2", "name": "size=large, style=solid, state=default",
>          "type": "COMPONENT", "width": 200, "height": 48,
>          "children": [
>              {"name": "Icon", "node_type": "INSTANCE", "sort_order": 0},
>              {"name": "Label", "node_type": "TEXT", "sort_order": 1, "text_content": "Submit"}
>          ]},
>         {"id": "500:3", "name": "size=large, style=solid, state=hover",
>          "type": "COMPONENT", "width": 200, "height": 48, "children": []},
>         {"id": "500:4", "name": "size=large, style=outline, state=default",
>          "type": "COMPONENT", "width": 200, "height": 48, "children": []},
>         {"id": "500:5", "name": "size=small, style=solid, state=default",
>          "type": "COMPONENT", "width": 120, "height": 36, "children": []}
>     ]
> }
> ```
>
> A standalone COMPONENT:
> ```python
> {"id": "600:1", "name": "logo", "type": "COMPONENT", "description": "App logo"}
> ```

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `tests/test_components.py` with comprehensive unit tests for all component extraction functions. Use `@pytest.mark.unit` marker on all tests.

### Test Groups

1. **Category inference tests** (at least 5 tests):
   - `test_infer_category_button`: "button/large" -> "button"
   - `test_infer_category_input`: "text field/default" -> "input"
   - `test_infer_category_nav`: "nav/tabs" -> "nav"
   - `test_infer_category_none`: "some random component" -> None
   - `test_infer_category_case_insensitive`: "BUTTON Large" -> "button"

2. **Variant property parsing tests** (at least 4 tests):
   - `test_parse_variant_properties_standard`: "size=large, style=solid, state=default" -> {"size": "large", "style": "solid", "state": "default"}
   - `test_parse_variant_properties_single`: "size=large" -> {"size": "large"}
   - `test_parse_variant_properties_empty`: "" -> {}
   - `test_parse_variant_properties_whitespace`: "size = large , style = solid" -> handles extra whitespace

3. **Interaction axis detection tests** (at least 4 tests):
   - `test_detect_interaction_axis_state`: axis_name="state", values=["default", "hover", "focus"] -> True
   - `test_detect_interaction_axis_by_values`: axis_name="status", values=["default", "pressed", "disabled"] -> True
   - `test_detect_interaction_axis_size`: axis_name="size", values=["small", "medium", "large"] -> False
   - `test_detect_interaction_axis_mixed`: values=["default", "hover", "custom_state"] -> False (not ALL are interaction states)

4. **Component set parsing tests** (at least 3 tests):
   - `test_parse_component_set_basic`: Parse the mock button COMPONENT_SET, verify name, variant count, axes.
   - `test_parse_component_set_axes`: Verify 3 axes extracted: size (not interaction), style (not interaction), state (interaction).
   - `test_parse_component_set_default_values`: Verify default_value for "state" axis is "default".

5. **Standalone component parsing tests** (at least 2 tests):
   - `test_parse_standalone_component`: Parse standalone logo, verify empty variants/axes.
   - `test_parse_standalone_component_category`: Logo component has no matching category (None).

6. **DB insertion tests** (at least 5 tests, using in-memory DB):
   - `test_insert_component_creates_row`: Insert, verify row in components table.
   - `test_insert_component_upsert`: Insert same figma_node_id twice, verify 1 row.
   - `test_insert_variants_creates_rows`: Insert 4 variants, verify 4 rows.
   - `test_insert_variant_axes_creates_rows`: Insert 3 axes, verify 3 rows with correct is_interaction.
   - `test_extract_components_full`: Run `extract_components` with a list containing 1 COMPONENT_SET and 1 standalone COMPONENT, verify all tables populated.

7. **Variant dimension values tests** (at least 3 tests):
   - `test_populate_variant_dimension_values_basic`: 4 variants, 3 axes -> 12 rows in variant_dimension_values.
   - `test_populate_variant_dimension_values_standalone`: 0 variants -> 0 rows (no error).
   - `test_populate_variant_dimension_values_query`: After population, the hover-state query from the Agent Cookbook returns expected results.

8. **Slot inference tests** (at least 5 tests):
   - `test_infer_slot_type_text`: TEXT node -> "text"
   - `test_infer_slot_type_icon_instance`: INSTANCE named "Icon" -> "icon"
   - `test_infer_slot_type_component_instance`: INSTANCE named "Badge" -> "component"
   - `test_infer_slots_filters_noise`: Children including "background" and "spacer" are filtered out.
   - `test_infer_slots_snake_case_names`: "Leading Icon" -> slot name "leading_icon"
   - `test_infer_slots_text_required`: TEXT slot has is_required=1
   - `test_insert_slots_creates_rows`: Insert 2 slots, verify 2 rows in component_slots.

9. **A11y inference tests** (at least 5 tests):
   - `test_infer_a11y_button`: category="button" -> role="button", required_label=1, min_touch_target=44.0
   - `test_infer_a11y_input`: category="input" -> role="textbox", required_label=1, min_touch_target=44.0
   - `test_infer_a11y_card`: category="card" -> role="article", required_label=0, min_touch_target=None
   - `test_infer_a11y_from_name`: category=None, name="button large" -> role="button"
   - `test_infer_a11y_unknown`: category=None, name="widget" -> role=None
   - `test_insert_a11y_creates_row`: Insert, verify row in component_a11y.
   - `test_insert_a11y_upsert`: Insert twice for same component, verify 1 row.

### Helper

Create a `_make_mock_component_set()` function returning the button COMPONENT_SET mock data. Create a `_make_mock_standalone_component()` for the logo. Each function must insert the required `files` row first when using DB fixtures.

## Acceptance Criteria

- [ ] `pytest tests/test_components.py -v` passes all tests
- [ ] At least 36 test functions across the 9 groups
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB (no file I/O)
- [ ] All assertions are specific (exact values, counts, types)
- [ ] Variant dimension values are verified including the hover-state cross-component query
- [ ] Slot inference tests verify filtering, naming, and type detection
- [ ] A11y inference tests verify role mapping, touch targets, and required labels
- [ ] DB insertion tests verify UPSERT idempotency
- [ ] `pytest tests/test_components.py -v --tb=short` exits 0

## Notes

- These are unit tests. Each test creates its own in-memory DB or uses the `db` fixture from conftest.
- The mock component data should closely match what Figma returns via `use_figma` for component frames.
- DB tests need to insert a `files` row first (FK requirement for components).
- For `extract_components` full test, provide a list with both COMPONENT_SET and standalone COMPONENT to test both code paths.
- Use `@pytest.mark.timeout(10)` for any tests that do DB operations as a safety net.