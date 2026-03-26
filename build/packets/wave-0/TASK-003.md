---
taskId: TASK-003
title: "Create shared constants and type definitions"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-001]
produces:
  - dd/types.py
verify:
  - type: typecheck
    command: 'python -c "from dd.types import DeviceClass, BindingStatus, Tier, SyncStatus; print(list(DeviceClass)); print(list(BindingStatus))"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-003: Create shared constants and type definitions

## Spec Context

### From Technical Design Spec -- Phase 1: File Inventory

> **Device classification logic:**
> | Width | Height | device_class |
> |-------|--------|-------------|
> | 428   | 926    | iphone      |
> | 834   | 1194   | ipad_11     |
> | 1536  | 1152   | ipad_13     |
> | other | other  | unknown     |
>
> **Component sheet detection heuristics** (frames that are NOT screens):
> 1. Name contains "Buttons", "Controls", "Components", "Modals", "Popups", "Icons", "Website", or "Assets" (case-insensitive).

### From schema.sql -- CHECK constraints and ENUMs

> ```sql
> -- tokens.tier
> CHECK(tier IN ('extracted', 'curated', 'aliased'))
>
> -- tokens.sync_status
> CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted'))
>
> -- node_token_bindings.binding_status
> CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden'))
>
> -- extraction_runs.status
> CHECK(status IN ('running', 'completed', 'failed', 'cancelled'))
>
> -- screen_extraction_status.status
> CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped'))
>
> -- screens.device_class
> device_class TEXT,  -- iphone, ipad_11, ipad_13, web, component_sheet, unknown
>
> -- export_validations.severity
> CHECK(severity IN ('error', 'warning', 'info'))
> ```

### From Technical Design Spec -- Phase 3: Value Normalization + Binding Creation

> | Property path | Raw value example | Resolved value |
> |---|---|---|
> | `fill.0.color` | `{"r":0.035,"g":0.035,"b":0.043,"a":1}` | `#09090B` |
> | `stroke.0.color` | `{"r":0.831,"g":0.831,"b":0.847,"a":1}` | `#D4D4D8` |
> | `cornerRadius` | `8` | `8` |
> | `fontSize` | `16` | `16` |
> | `fontFamily` | `"Inter"` | `Inter` |
> | `fontWeight` | `600` | `600` |
> | `lineHeight` | `{"value":24,"unit":"PIXELS"}` | `24` |
> | `letterSpacing` | `{"value":-0.5,"unit":"PIXELS"}` | `-0.5` |
> | `padding.top` | `16` | `16` |
> | `itemSpacing` | `8` | `8` |
> | `opacity` | `0.5` | `0.5` |
> | `effect.0.color` | `{"r":0,"g":0,"b":0,"a":0.1}` | `#0000001A` |
> | `effect.0.radius` | `6` | `6` |
> | `effect.0.offsetX` | `0` | `0` |
> | `effect.0.offsetY` | `4` | `4` |
> | `effect.0.spread` | `-1` | `-1` |

### From User Requirements Spec -- FR-2.4

> FR-2.4: DTCG v2025.10 compatible type system (color, dimension, fontFamily, fontWeight, number, shadow, border, transition, gradient).

### From Technical Design Spec -- Phase 2: is_semantic computation

> A node is flagged `is_semantic = 1` if ANY of these are true:
> 1. `node_type` is TEXT, INSTANCE, or COMPONENT.
> 2. `node_type` is FRAME and `layout_mode` is not NULL (auto-layout container).
> 3. Node `name` does not start with "Frame", "Group", "Rectangle", or "Vector" (user-renamed = intentional).
> 4. Node has >= 2 children and at least one child is `is_semantic` (meaningful parent).

## Task

Create `dd/types.py` containing all enumerations, constants, and type aliases used across the pipeline. This is the canonical source for all string enums that correspond to CHECK constraints in the database.

1. **Enums** (use `enum.Enum` with string values):
   - `DeviceClass`: `IPHONE = "iphone"`, `IPAD_11 = "ipad_11"`, `IPAD_13 = "ipad_13"`, `WEB = "web"`, `COMPONENT_SHEET = "component_sheet"`, `UNKNOWN = "unknown"`
   - `BindingStatus`: `UNBOUND = "unbound"`, `PROPOSED = "proposed"`, `BOUND = "bound"`, `OVERRIDDEN = "overridden"`
   - `Tier`: `EXTRACTED = "extracted"`, `CURATED = "curated"`, `ALIASED = "aliased"`
   - `SyncStatus`: `PENDING = "pending"`, `FIGMA_ONLY = "figma_only"`, `CODE_ONLY = "code_only"`, `SYNCED = "synced"`, `DRIFTED = "drifted"`
   - `RunStatus`: `RUNNING = "running"`, `COMPLETED = "completed"`, `FAILED = "failed"`, `CANCELLED = "cancelled"`
   - `ScreenExtractionStatus`: `PENDING = "pending"`, `IN_PROGRESS = "in_progress"`, `COMPLETED = "completed"`, `FAILED = "failed"`, `SKIPPED = "skipped"`
   - `Severity`: `ERROR = "error"`, `WARNING = "warning"`, `INFO = "info"`
   - `DTCGType`: `COLOR = "color"`, `DIMENSION = "dimension"`, `FONT_FAMILY = "fontFamily"`, `FONT_WEIGHT = "fontWeight"`, `NUMBER = "number"`, `SHADOW = "shadow"`, `BORDER = "border"`, `TRANSITION = "transition"`, `GRADIENT = "gradient"`

2. **Device classification dictionary**:
   - `DEVICE_DIMENSIONS: dict[tuple[int, int], DeviceClass]` mapping `(428, 926)` -> `DeviceClass.IPHONE`, `(834, 1194)` -> `DeviceClass.IPAD_11`, `(1536, 1152)` -> `DeviceClass.IPAD_13`

3. **Component sheet name heuristics**:
   - `COMPONENT_SHEET_KEYWORDS: list[str] = ["buttons", "controls", "components", "modals", "popups", "icons", "website", "assets"]` (all lowercase for case-insensitive comparison)

4. **Non-semantic node name prefixes**:
   - `NON_SEMANTIC_PREFIXES: tuple[str, ...] = ("Frame", "Group", "Rectangle", "Vector")` (case-sensitive as from Figma)

5. **Semantic node types** (always semantic):
   - `SEMANTIC_NODE_TYPES: frozenset[str] = frozenset({"TEXT", "INSTANCE", "COMPONENT"})`

6. **Property path constants** (commonly used in bindings):
   - `FILL_COLOR_PATTERN = "fill.{}.color"` (format string)
   - `STROKE_COLOR_PATTERN = "stroke.{}.color"`
   - `EFFECT_FIELD_PATTERN = "effect.{}.{}"` (index, field)
   - `PADDING_PROPERTIES: tuple[str, ...] = ("padding.top", "padding.right", "padding.bottom", "padding.left")`
   - `SPACING_PROPERTIES: tuple[str, ...] = ("itemSpacing", "counterAxisSpacing")`
   - `TYPOGRAPHY_PROPERTIES: tuple[str, ...] = ("fontSize", "fontFamily", "fontWeight", "lineHeight", "letterSpacing")`
   - `DIMENSION_PROPERTIES: tuple[str, ...] = ("cornerRadius", "opacity")`

7. **Helper function `classify_device(width: float, height: float) -> DeviceClass`**:
   - Round width and height to integers.
   - Look up in `DEVICE_DIMENSIONS`.
   - Return the matching `DeviceClass` or `DeviceClass.UNKNOWN`.

8. **Helper function `is_component_sheet_name(name: str) -> bool`**:
   - Return `True` if any keyword from `COMPONENT_SHEET_KEYWORDS` appears in `name.lower()`.

## Acceptance Criteria

- [ ] `python -c "from dd.types import DeviceClass, BindingStatus, Tier, SyncStatus, RunStatus, ScreenExtractionStatus, Severity, DTCGType"` exits 0
- [ ] `python -c "from dd.types import DeviceClass; assert DeviceClass.IPHONE.value == 'iphone'"` exits 0
- [ ] `python -c "from dd.types import BindingStatus; assert BindingStatus.UNBOUND.value == 'unbound'"` exits 0
- [ ] `python -c "from dd.types import classify_device, DeviceClass; assert classify_device(428, 926) == DeviceClass.IPHONE"` exits 0
- [ ] `python -c "from dd.types import classify_device, DeviceClass; assert classify_device(999, 999) == DeviceClass.UNKNOWN"` exits 0
- [ ] `python -c "from dd.types import is_component_sheet_name; assert is_component_sheet_name('Buttons and Controls') == True"` exits 0
- [ ] `python -c "from dd.types import is_component_sheet_name; assert is_component_sheet_name('Home Screen') == False"` exits 0
- [ ] `python -c "from dd.types import DEVICE_DIMENSIONS; assert len(DEVICE_DIMENSIONS) == 3"` exits 0
- [ ] `python -c "from dd.types import NON_SEMANTIC_PREFIXES, SEMANTIC_NODE_TYPES; assert 'Frame' in NON_SEMANTIC_PREFIXES; assert 'TEXT' in SEMANTIC_NODE_TYPES"` exits 0
- [ ] `python -c "from dd.types import PADDING_PROPERTIES, TYPOGRAPHY_PROPERTIES; assert len(PADDING_PROPERTIES) == 4; assert 'fontSize' in TYPOGRAPHY_PROPERTIES"` exits 0

## Notes

- All enum classes should inherit from `str, enum.Enum` (i.e., `class DeviceClass(str, enum.Enum)`) so that `.value` returns a string that can be used directly in SQL queries.
- The `classify_device` function rounds to int before lookup because Figma dimensions can be floats (e.g., 428.0).
- `NON_SEMANTIC_PREFIXES` are case-sensitive because Figma's default names use title case.