# v0.3 Deprecation tracker

Files, functions, tests, and concepts marked for deletion as part of
the **Option B migration** (see `docs/decisions/v0.3-option-b-cutover.md`).

Nothing here is deleted yet — deletion happens at **Milestone M6
(cutover)**, after the markup-native renderer (M1–M4) achieves 204/204
byte-parity + pixel-parity with the Option A path, and upstream
consumers (M5) have migrated.

**Until cutover, both paths coexist in CI.** The Option A machinery
stays operational so the 204/204 baseline is never violated.

---

## Production code (`dd/`)

### Pending deletion at M6

| Artifact | Replaced by | Reason |
|---|---|---|
| `dd/ir.py::generate_ir()` | `dd/ir.py::derive_markup()` | Returns `L3Document` directly; no dict IR intermediate |
| `dd/ir.py::build_composition_spec()` | Inlined into `derive_markup`'s AST builders | Dict-shape-specific; no consumer post-cutover |
| `dd/ir.py::query_screen_visuals()` | Per-node lookups inside `render_figma` | Renderer queries `conn` directly, not via pre-baked dict |
| `dd/renderers/figma.py::generate_figma_script()` | `dd/renderers/figma.py::render_figma(doc, conn)` | Walks markup AST; no dict input |
| `dd/renderers/figma.py::generate_screen()` | Absorbed into `render_figma` | Dict-shape adapter no longer needed |
| `dd/decompress_l3.py` (entire module) | Not replaced — removed | Option A's lowering step; no lowering in Option B |
| `dd/compress_l3.py::_collapse_synthetic_screen_wrapper` | Folded into `derive_markup` | Screen-wrapper collapse happens at markup construction time |
| `$ext.nid` PropAssign emission (in `_compress_element`) | Removed | Node-id lookup moves into the renderer; no side-channel needed |
| `--via-markup` CLI flag (`dd generate`) | Becomes the default (only) path | Single render path post-cutover |
| `--via-markup` sweep flag (`render_batch/sweep.py`) | Becomes default | Same |
| `render_batch/scripts-markup/`, `walks-markup/`, `reports-markup/`, `summary-markup.json` | Merged into primary artefact dirs | One sweep path remains |

### Partial rewrite at M5 (upstream consumers)

| Artifact | Action |
|---|---|
| `dd/compose.py` | Consumes `L3Document` instead of dict IR |
| `dd/composition/*` (~29 functions) | Provider interfaces typed on `Node` / `L3Document` |
| `dd/rebind_prompt.py::query_token_variables` | Still used; interface unchanged |
| `dd/verify/*` | Compare walk against markup AST rather than `generate_ir` output |

### Core compressor (`dd/compress_l3.py`) — reused, not deleted

The per-axis derivation logic (`_spatial_props`, `_visual_props`,
`_fill_to_value`, `_effects_to_shadow`, `_normalize_raw_paint`,
canonical-type integration, override merging) becomes the core of
`derive_markup`. Module likely renamed to `dd/derive_markup.py` to
reflect the collapsed compressor-vs-decompressor duality (there is
no decompressor in Option B).

---

## Tests (`tests/`)

### Pending deletion at M6

| Test file | Reason |
|---|---|
| `tests/test_decompress_l3.py` (~77 tests) | Decompressor module gone |
| `tests/test_markup_render_pipeline.py` | Tests Option A round-trip (compress → emit → parse → decompress → render); replaced by M2/M3 byte-parity tests |
| `tests/test_script_parity.py` | Tests legacy `dd.markup` (mechanical dict-IR serde) path; predates even Option A |

### Renamed / rescoped at M6

| Test file | New role |
|---|---|
| `tests/test_compress_l3.py` | Becomes `tests/test_derive_markup.py` — tests DB → AST directly |
| `tests/fixtures/markup/*.dd` (3 fixtures) + snapshots | Unchanged — they describe the AST shape, not a specific pipeline |

### Preserved — no change

- `tests/test_markup_l3.py`, `tests/test_dd_markup_l3.py` — grammar / parser / emitter / semantic passes. Unaffected.
- `tests/test_archetype_skeletons.py` — archetype `.dd` files parse + round-trip. Already markup-native.

---

## Grammar / markup constructs

### `$ext.nid` — deprecated

Introduced in commit `5a5bcd9` as a compile-time side-channel to
bridge dict-IR node identity across the Option A lowering boundary.
In Option B, there's no lowering and the renderer looks up DB
visuals on-demand from `conn` using the node's `head.eid` (sanitized
original name) plus screen context. The channel is unnecessary.

Emitter continues to accept `$ext.nid` values for legacy parsing
compatibility (the grammar tolerates any `$ext.*` key per §11), but
the compressor stops emitting them at M6.

### `$ext.spec_key` — never shipped

Was considered as a bridge for dict-IR element-key identity; design
review concluded it was Option A scaffolding for a system being
demolished. Never made it past draft. Not in any commit.

### `--via-markup` as distinct path — deprecated

The flag exists in `dd generate` and `render_batch/sweep.py` as part
of the Option A round-trip probe. At M6 the markup path is the ONLY
path; the flag is removed (rendering is always "via markup" because
there's no other IR).

---

## Documentation

### Pending update at M6 (post-cutover)

- `docs/requirements-v0.3.md` §3.8 ("From AST to dict IR") — entire section obsolete; delete.
- `docs/spec-l0-l3-relationship.md` §3.2 (Option A vs B) — rewrite as historical "which was chosen and why" since the decision is made.
- `docs/learnings-v0.3.md` — add entry covering lessons from the A→B pivot once M6 lands.

### Tier 0 / Tier 1 references to "dict IR"

Any remaining phrasing that treats `dict IR` as an architectural
level (e.g. "dict IR remains canonical on the render path", "the
existing Figma renderer path (dict IR → script → pixels)") gets
reworked into implementation-shape language at M6. The levels are
L0–L3; dict IR was a v0.2-era implementation artefact.

---

## Out of scope for this deprecation

These look related but are kept:

- `dd/markup.py` (the probe / mechanical serializer) — already deleted pre-session; not tracked here.
- `dd/markup_l3.py` — the grammar parser / emitter / AST. Backbone of Option B. **Preserved.**
- `dd/compress_l3.py` — renamed and reshaped, not deleted (see above).
- `dd/archetype_library/*.dd` — markup-native, preserved.
- DB schema, extract path (`dd/extract_*.py`) — unchanged.
- Grammar spec (`docs/spec-dd-markup-grammar.md`) — unchanged.

---

## Progress tracker

Moved from "Pending" to "Deleted" as each item is removed at M6:

| Date | Item | Commit |
|---|---|---|
| — | — | — |

(Empty until M6 cutover PR lands.)
