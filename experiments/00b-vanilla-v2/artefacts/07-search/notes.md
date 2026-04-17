# Notes — 07-search

Prompt: `a search screen`

## Stage completion

- parse: ok
- compose: ok
- render: ok
- walk: ok
- screenshot: ok

## LLM output (parse)

- component count (flat): 18
- types: `{'header': 1, 'search_input': 1, 'card': 2, 'heading': 2, 'list': 2, 'list_item': 8, 'badge': 1, 'button': 1}`

## Compose (IR)

- elements: 19
- types: `{'header': 1, 'search_input': 1, 'heading': 2, 'list_item': 8, 'list': 2, 'card': 2, 'badge': 1, 'button': 1, 'screen': 1}`
- warnings (Mode 2 fallbacks): 18
- token refs: 0
- script chars: 6,159
- createInstance count (Mode 1): 0
- createText count: 2
- createFrame count: 17

## Render (bridge execution)

- __ok: True
- errors: 1 — kinds: `{'render_thrown': 1}`
  - kind=`render_thrown` eid=`None` msg=`object is not extensible`

## Walk (rendered subtree)

- eid_count: 1
- type distribution: `{'FRAME': 1}`
- max dimensions: 428 x 926
- Mode-2 default-sized (100x100) nodes: 0 / 1

## Screenshot

- `screenshot.png` — 3,520 bytes
- **size signal:** tiny (< 4KB) — screen-1 is empty grey frame (throw happened before children were appended)

## Mechanical patterns

- **render_thrown ×1:** outer guard caught `object is not extensible` — leaf-type bug: `heading`/`link` IR types render as TEXT but aren't in `_LEAF_TYPES`, so `.layoutMode = "VERTICAL"` is still emitted and the Plugin API rejects it
- all elements rendered as Mode-2 createFrame (no CKR matches surfaced to the LLM — `component_templates` has 1 row; `component_key_registry` has 129 rows but isn't exposed)
- 0 token references emitted (`tokens` table empty; cluster step never run)
