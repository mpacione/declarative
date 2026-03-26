---
taskId: TASK-023
title: "Implement component a11y inference"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-020]
produces:
  - dd/extract_components.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_components import infer_a11y, insert_a11y"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_components import infer_a11y; a11y = infer_a11y(\"button\", \"button/primary\"); print(a11y); assert a11y[\"role\"] == \"button\" and a11y[\"min_touch_target\"] == 44"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-023: Implement component a11y inference

## Spec Context

### From Technical Design Spec -- Phase 4: Component Extraction

> 7. Populate `component_a11y`: infer role from component category and name (button -> `role: button`, input -> `role: textbox`). Set `min_touch_target = 44` for interactive components (iOS default). Manual augmentation during curation.

### From User Requirements Spec -- FR-3.7: Component Model

> FR-3.7.2: Accessibility contracts (`component_a11y`) capture per-component: ARIA role, required label flag, focus order, minimum touch target (44px iOS / 48px Android), keyboard shortcut, and freeform a11y notes.
> FR-3.7.5: All component model data is extractable where Figma metadata allows and manually augmentable during curation (slots, a11y, responsive).

### From schema.sql -- component_a11y table

> ```sql
> CREATE TABLE IF NOT EXISTS component_a11y (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     role            TEXT,
>     required_label  INTEGER NOT NULL DEFAULT 0,
>     focus_order     INTEGER,
>     min_touch_target REAL,
>     keyboard_shortcut TEXT,
>     aria_properties TEXT,
>     notes           TEXT,
>     UNIQUE(component_id)
> );
> ```

### From schema.sql -- v_component_catalog view

> ```sql
> CREATE VIEW v_component_catalog AS
> SELECT
>     c.id, c.name, c.category, c.description, c.composition_hint,
>     COUNT(DISTINCT cv.id) AS variant_count,
>     COUNT(DISTINCT cs.id) AS slot_count,
>     ca.role AS a11y_role,
>     ca.min_touch_target,
>     GROUP_CONCAT(DISTINCT va.axis_name) AS axes
> FROM components c
> LEFT JOIN component_variants cv ON cv.component_id = c.id
> LEFT JOIN component_slots cs ON cs.component_id = c.id
> LEFT JOIN component_a11y ca ON ca.component_id = c.id
> LEFT JOIN variant_axes va ON va.component_id = c.id
> GROUP BY c.id
> ORDER BY c.category, c.name;
> ```

### From dd/extract_components.py (produced by TASK-020)

> Exports:
> - `extract_components(conn, file_id, component_nodes) -> list[int]`
> - `insert_component(conn, file_id, component_data) -> int`
> - `infer_category(name) -> str | None`
> - `CATEGORY_KEYWORDS: dict[str, list[str]]`

## Task

Extend `dd/extract_components.py` by adding accessibility inference and insertion functions. The a11y data is inferred from the component's category and name, providing a baseline that can be manually refined during curation.

1. **`ROLE_MAP: dict[str, str]`**:
   - Map component categories to ARIA roles:
     ```python
     ROLE_MAP = {
         "button": "button",
         "input": "textbox",
         "nav": "navigation",
         "card": "article",
         "modal": "dialog",
         "icon": "img",
         "layout": "group",
         "chrome": "presentation",
     }
     ```

2. **`INTERACTIVE_CATEGORIES: frozenset[str]`**:
   - Categories that represent interactive components requiring touch targets:
     ```python
     INTERACTIVE_CATEGORIES = frozenset({"button", "input", "nav", "modal"})
     ```

3. **`infer_a11y(category: str | None, name: str) -> dict`**:
   - Accept the component's category (from `infer_category`) and full name.
   - Determine `role`: Look up category in ROLE_MAP. If category is None, try to infer from name: check if the lowercased name contains any key from ROLE_MAP, use that role. If nothing matches, set role to None.
   - Determine `required_label`: Set to 1 for interactive categories (button, input) where the user must provide an accessible label. Set to 0 for others.
   - Determine `min_touch_target`: 44.0 for INTERACTIVE_CATEGORIES (iOS default per probe data showing iPhone as primary device). None for non-interactive.
   - Determine `aria_properties`: For specific roles, suggest common ARIA properties as a JSON string:
     - button: `json.dumps({"aria-pressed": "boolean"})` (optional)
     - input: `json.dumps({"aria-required": "boolean", "aria-invalid": "boolean"})`
     - modal: `json.dumps({"aria-modal": "true"})`
     - For others: None
   - Determine `notes`: Set to None (populated during manual curation).
   - Return: `{"role": str|None, "required_label": int, "focus_order": None, "min_touch_target": float|None, "keyboard_shortcut": None, "aria_properties": str|None, "notes": None}`

4. **`insert_a11y(conn, component_id: int, a11y_data: dict) -> int`**:
   - UPSERT into `component_a11y`: `INSERT INTO component_a11y (component_id, role, required_label, focus_order, min_touch_target, keyboard_shortcut, aria_properties, notes) VALUES (...) ON CONFLICT(component_id) DO UPDATE SET role=excluded.role, required_label=excluded.required_label, focus_order=excluded.focus_order, min_touch_target=excluded.min_touch_target, keyboard_shortcut=excluded.keyboard_shortcut, aria_properties=excluded.aria_properties, notes=excluded.notes`.
   - Return the id of the row.

5. **Update `extract_components`**:
   - After inserting the component, call `infer_a11y(category, name)` and then `insert_a11y(conn, component_id, a11y_data)`.
   - This ensures every component gets a baseline a11y record.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_components import infer_a11y, insert_a11y, ROLE_MAP, INTERACTIVE_CATEGORIES"` exits 0
- [ ] `infer_a11y("button", "button/primary")` returns `{"role": "button", "required_label": 1, "min_touch_target": 44.0, ...}`
- [ ] `infer_a11y("input", "text field")` returns `{"role": "textbox", "required_label": 1, "min_touch_target": 44.0, ...}`
- [ ] `infer_a11y("card", "pricing card")` returns `{"role": "article", "required_label": 0, "min_touch_target": None, ...}`
- [ ] `infer_a11y("icon", "icon/chevron")` returns `{"role": "img", "required_label": 0, "min_touch_target": None, ...}`
- [ ] `infer_a11y(None, "button large")` infers role "button" from name
- [ ] `infer_a11y(None, "unknown widget")` returns role=None
- [ ] `insert_a11y` inserts a row and returns an integer ID
- [ ] `insert_a11y` with same component_id twice is idempotent (UPSERT)
- [ ] After `extract_components`, querying `v_component_catalog` returns rows with `a11y_role` populated
- [ ] Button/input components have `min_touch_target = 44.0`
- [ ] Non-interactive components have `min_touch_target` as None/NULL

## Notes

- The a11y inference is intentionally conservative and provides a baseline. The spec explicitly states "Manual augmentation during curation" -- users should review and adjust roles, labels, and touch targets.
- The 44px touch target is the iOS default (HIG). The probe results show iPhone as the primary device class. For Android (48px), the user can adjust during curation.
- `aria_properties` is stored as a JSON string containing common ARIA attributes for the role. This is suggestive, not prescriptive.
- The `focus_order` and `keyboard_shortcut` fields are left as None -- these require manual curation as they depend on page context, not component structure.