# Notes — 03-meme-feed

Prompt: `a feed of memes with upvote and share buttons under each`

## Stage completion

- parse: ok
- compose: ok
- render: ok
- walk: ok
- screenshot: ok

## LLM output (parse)

- component count (flat): 26
- types: `{'header': 1, 'card': 4, 'image': 4, 'text': 4, 'button_group': 4, 'icon_button': 8, 'pagination': 1}`

## Compose (IR)

- elements: 27
- types: `{'header': 1, 'image': 4, 'text': 4, 'icon_button': 8, 'button_group': 4, 'card': 4, 'pagination': 1, 'screen': 1}`
- warnings (Mode 2 fallbacks): 26
- token refs: 0
- script chars: 8,390
- createInstance count (Mode 1): 0
- createText count: 4
- createFrame count: 23

## Render (bridge execution)

- __ok: True
- errors: 0 — kinds: `{}`

## Walk (rendered subtree)

- eid_count: 27
- type distribution: `{'FRAME': 23, 'TEXT': 4}`
- max dimensions: 428 x 926
- Mode-2 default-sized (100x100) nodes: 14 / 27

## Screenshot

- `screenshot.png` — 8,858 bytes
- size > 4KB — rendered content visible

## Mechanical patterns

- render_thrown: none — no `heading`/`link` types in this IR
- all elements rendered as Mode-2 createFrame (no CKR matches surfaced to the LLM — `component_templates` has 1 row; `component_key_registry` has 129 rows but isn't exposed)
- 0 token references emitted (`tokens` table empty; cluster step never run)
