# L0 ↔ L3 Relationship Specification

**Status:** Canonical (Plan A.6 output). Every open question is closed
by a decision recorded below.
**Authored:** 2026-04-18.

This spec answers the question: **when we have the dd markup grammar
(from `docs/spec-dd-markup-grammar.md`) and hand-authored fixtures
(under `tests/fixtures/markup/`), how does the rest of the system
produce and consume them?**

It defines:
1. The **compression algorithm** that turns L0+L1+L2 (DB state) into
   L3 (dd markup)
2. The **expansion algorithm** that turns L3 back into a renderable
   dict IR (and from there into a Figma script via the existing
   renderer)
3. The **round-trip proof shape** — what "dd markup round-trips the
   Dank corpus at pixel parity" concretely means at three tiers
4. **Density semantics** — what happens when L3 is less than fully
   populated across the five axes
5. **Interaction with existing machinery** — where `generate_ir`,
   `generate_figma_script`, and `sweep.py` fit

---

## Relationship to the other specs

- `docs/requirements.md` (Tier 0) states the design principles and
  invariants this spec must uphold
- `docs/requirements-v0.3.md` (Tier 1) scopes v0.3
- `docs/spec-dd-markup-grammar.md` (S2) defines the surface syntax;
  THIS doc defines the semantics
- `tests/fixtures/markup/` (S4) are normative examples

If this doc conflicts with S2, update this doc. If either conflicts
with Tier 0, update Tier 0 and propagate.

---

## 1. Introduction

### 1.1 Scope

This spec covers the bidirectional transformation between:
- **L0+L1+L2** (the DB — scene graph, classification, token bindings)
- **L3** (dd markup, axis-polymorphic semantic tree)

It does NOT cover:
- Raw L3 parsing and lexing — that's S2 (`spec-dd-markup-grammar.md`)
- Rendering L3 directly to pixels — this is delegated to the existing
  `generate_figma_script(dict_ir)` via the lowering step specified in §3
- Synthetic token generation — that's Stage 3 / S5 (to be specified)

### 1.2 Existing machinery

Three existing entry points are load-bearing for this spec:

| Function | File | Role in the L0↔L3 pipeline |
|----------|------|---------------------------|
| `query_screen_for_ir(conn, screen_id)` | `dd/ir.py` | DB rows → flat dict |
| `build_composition_spec(data)` | `dd/ir.py` | Flat dict → dict IR |
| `generate_ir(conn, screen_id, semantic=True)` | `dd/ir.py` | Composed entry point |
| `generate_figma_script(ir)` | `dd/renderers/figma.py` | Dict IR → Figma Plugin API JS |
| `render_batch/sweep.py` | `render_batch/sweep.py` | Drives Tier 3 pixel-parity sweep |

The compression algorithm in this spec adds a new step AFTER
`build_composition_spec` that takes its dict output and emits dd markup.
The expansion algorithm adds a new step BEFORE `generate_figma_script`
that takes dd markup and produces the equivalent dict IR.

---

## 2. Compression — L0+L1+L2 → L3

### 2.1 Pipeline overview

```
  DB rows (L0 + L1 SCI + L2 NTB)
       │
       ▼
  query_screen_for_ir(conn, screen_id)          // existing
       │
       ▼
  build_composition_spec(data)                  // existing
       │
       ▼                                       ← (if semantic=True)
  filter_system_chrome + build_semantic_tree    // existing
       │
       ▼
  compress_to_l3_ast(dict_ir)                   // NEW (Plan B Stage 1.4)
       │
       ▼
  emit_dd(l3_ast)                               // NEW (Plan B Stage 1.4)
       │
       ▼
  .dd source text
```

### 2.2 Compression as per-axis decomposition

The compression algorithm walks the dict IR produced by
`build_composition_spec` and for each element produces a dd-markup
AST node with properties populated from the five axes:

```
for element in dict_ir["elements"]:
    l3_node = L3Node(type=resolve_type_keyword(element))
    l3_node.eid = element_eid_if_addressable(element)
    l3_node.children = ordered_children(element)        # Structure
    l3_node.properties.update(content_axis(element))    # Content
    l3_node.properties.update(spatial_axis(element))    # Spatial
    l3_node.properties.update(visual_axis(element))     # Visual
    l3_node.provenance = infer_provenance(element)
```

The System axis (document-level `tokens { }` block) is assembled once
per document from the union of all referenced tokens.

### 2.3 Structure axis

Input: L0 `parent_id` tree + L1 classification + synthetic-node filter.

Rules:
1. **Synthetic-node filter** (per
   `feedback_synthetic_allowlist_not_heuristic.md`) drops Figma
   platform artifacts like `(Auto Layout spacer)`. Filter runs before
   L3 compression (already done by `build_composition_spec`).
2. **Type keyword resolution** for a surviving element:
   - If L1 SCI has a `canonical_type` AND the node has `component_key`,
     emit a **component reference**: `-> <slash-path>` (see §2.7 for
     slash-path derivation).
   - If L1 SCI has a `canonical_type` but no `component_key`, emit the
     canonical type as a dd keyword: `card { ... }`, `button { ... }`,
     `heading { ... }`, etc.
   - If L1 SCI is absent, fall back to a dd primitive type keyword
     based on `node_type`: `FRAME → frame`, `TEXT → text`,
     `RECTANGLE → rectangle`, `VECTOR → vector`, `ELLIPSE → ellipse`,
     `GROUP → group`, `BOOLEAN_OPERATION → boolean-operation`,
     `LINE → line`, `STAR → star`, `POLYGON → polygon`.
3. **Children ordering** preserves `sort_order` from L0.
4. **EID emission** — see §2.3.1 below for the sanitization algorithm.

### 2.3.1 EID sanitization algorithm (normative)

Every surviving element receives an EID. The compressor attempts, in
order:

1. **Name-derived EID.** Take `nodes.name`, apply the normalization
   below. If the result is a non-empty IDENT per §2.4 of the grammar
   spec AND is unique within the parent-Block scope, use it.
2. **Auto-incremented EID.** Otherwise, use `{type}-{n}` where `type`
   is the emitted TypeKeyword or the CompRef's last slash segment, and
   `n` is the 1-based index of this node among same-type siblings.

#### Normalization (Figma layer name → EID candidate)

```
normalize_to_eid(raw: str) -> str:
    s = raw.lower()
    s = replace_runs_of(s, r"[\s/]+", "-")     # spaces and slashes → `-`
    s = replace_runs_of(s, r"[^a-z0-9_-]+", "") # drop all other non-IDENT chars
    s = s.strip("-_")                          # trim leading/trailing separators
    s = collapse_runs_of(s, r"-+", "-")        # collapse `--` → `-`
    if s == "" or s[0].isdigit():              # invalid IDENT start
        return ""                              # signal: use auto-increment
    return s
```

Examples:
- `"iPhone 13 Pro Max - 119"` → `"iphone-13-pro-max-119"` (starts with
  letter; no invalid chars) → **accepted**
- `"nav/top-nav"` → `"nav-top-nav"` → **accepted**
- `"Safari - Bottom"` → `"safari-bottom"` → **accepted**
- `"Frame 354"` → `"frame-354"` → **accepted**
- `"(internal spacer)"` → after paren-strip: `"internal-spacer"` →
  **accepted** (but this case won't occur; synthetic nodes filtered)
- `"123"` → `"123"` → **rejected** (digit start) → auto-increment fires
- `""` → `""` → **rejected** → auto-increment fires

#### Collision handling

When the normalized EID already exists in the parent-Block scope,
append `-N` where N is the smallest integer ≥ 2 producing a unique
id. Example: two sibling `"nav/top-nav"` nodes become `#nav-top-nav`
and `#nav-top-nav-2`.

#### When to omit the explicit `#eid`

The compressor emits `#eid` ONLY when at least one of the following
holds:
- The node is referenced from any path override at any call site
- The node is targeted by an instance-override in the input DB
- The normalized name-derived EID is meaningfully different from the
  auto-id (so preserving it carries information)

Otherwise, the node relies on parser auto-id (grammar §3.4). This
keeps emission compact — ~20 elements per screen, not 200 labeled
eids.

### 2.4 Content axis

Input: `text_content` column on L0 TEXT nodes, plus instance-override
text on L1 INSTANCE nodes.

Rules:
1. `text` nodes receive a positional string-literal arg containing the
   raw text content.
2. On component references (`-> ...`), instance-override text becomes a
   property assignment `text=<literal>` on the ref node (§8 of the
   grammar spec; Figma renderer treats it as an override at render
   time).
3. Multiline text uses triple-quoted strings (§2.5 of grammar spec).

### 2.5 Spatial axis

Input: `x`, `y`, `width`, `height`, `layout_mode`, `item_spacing`,
`padding_*`, `primary_align`, `counter_align`, `layout_sizing_h`,
`layout_sizing_v`, `min_*`, `max_*` from L0.

Rules:
1. **Position.** For absolute-positioned children (parent has no
   `layout_mode`), emit `x=<px>` and `y=<px>` relative to parent.
   For auto-layout children, omit x/y (flow provides position).
   Root-of-screen: emit `x=` / `y=` only when non-zero.
2. **Sizing.**
   - `layout_sizing_h`:`FIXED` → `width=<px>`
   - `layout_sizing_h`:`FILL` → `width=fill`
   - `layout_sizing_h`:`HUG` → `width=hug`
   - Same for `layout_sizing_v` → `height=...`
   - `min_width` / `max_width` → `width=fill(min=..., max=...)` when
     both are set; otherwise omit (bare `fill` carries no bounds)
3. **Layout.**
   - `layout_mode`:`HORIZONTAL` → `layout=horizontal`
   - `layout_mode`:`VERTICAL` → `layout=vertical`
   - `layout_mode` is null / missing → omit (absolute is default)
4. **Gap.** `item_spacing` → `gap=<px>`. Absent → omit.
5. **Padding.** Four sides → `padding={top=<px> right=<px> bottom=<px> left=<px>}`. Emit only non-zero sides; emit nothing if all zero.
6. **Alignment.** `primary_align` / `counter_align` → `mainAxis=...` /
   `crossAxis=...`. `align=center` shorthand when both primary and
   counter are `CENTER`.

### 2.6 Visual axis

Input: `fills`, `strokes`, `effects`, `corner_radius`, `opacity`,
`visible`, `blend_mode`, `stroke_weight`, font properties from L0, PLUS
any L2 bindings matching those properties.

Rules:
1. **Fills** (array; common case single-fill):
   - Single-fill SOLID with L2 binding → `fill={<token-path>}`
   - Single-fill SOLID without L2 binding → `fill=<hex-literal>`
     (pre-Stage-3; post-Stage-3 this becomes a synthetic-token ref)
   - Single-fill GRADIENT_LINEAR → `fill=gradient-linear(<stop1>, <stop2>, ...)`,
     each stop a token-ref or hex literal per its own L2 binding
   - Single-fill IMAGE → `fill=image(asset=<hash>, mode=<scaleMode>)`
   - Multi-fill → `fills=[<fill1>, <fill2>, ...]` (rarer)
2. **Strokes** — analogous to fills, property name `stroke`/`strokes`.
3. **Effects** — shadow / blur array. Each effect emitted via its
   function form: `shadow(x=<px>, y=<px>, blur=<px>, color={...})`
   or `shadow={shadow.card}` when a token is bound.
4. **Radius.**
   - Uniform: `radius=<px>` or `radius={radius.card}` (token).
   - Per-corner: `radius={top-left=<px> top-right=<px> bottom-left=<px> bottom-right=<px>}`.
5. **Opacity.** Non-default (not 1.0) → `opacity=<float>`.
6. **Visibility.** `visible=false` emitted explicitly. True is default;
   omit.
7. **Blend mode.** Non-default → `blend=<mode>`.

### 2.7 Component references (L1 Mode-1-eligible instances)

When an L0 node is an INSTANCE with a resolved `component_key`, the
compressor emits a CompRef. Slash-path derivation is normative — two
implementers must produce the same output.

#### 2.7.1 Slash-path normalization

The slash-path that appears after `->` is derived from the component
master's NAME, NOT from the instance node's layer name. The master
name lives in the **`component_key_registry.name`** column reached via
`nodes.component_key → component_key_registry.component_key`.

(Earlier drafts of this spec cited `components.name`. On the Dank DB,
the `components` table has no `key` column and zero rows — the
authoritative CKR-vs-instances join goes through
`component_key_registry`, which `dd/ir.py::query_screen_visuals`
already uses at line 592–596. Confirmed against the live DB:
25 CKR entries with null `figma_node_id` are the Mode-2 fallback
"orphan" case and still carry a `name` field.)

```
derive_comp_slash_path(component_name: str) -> str:
    # Master names in Dank are already slash-structured: "nav/top-nav",
    # "button/small/translucent", "ios/alpha-keyboard". But they also
    # may carry mixed-case + spaces + parens: "Safari - Bottom".
    # Normalize each path segment with the same rule used for EIDs.
    segments = component_name.split("/")
    normalized = [normalize_to_eid(seg) for seg in segments if seg.strip()]
    if not normalized or any(s == "" for s in normalized):
        return ""                               # signal: fall back to Mode 2
    return "/".join(normalized)
```

Examples (verified against Dank CKR):
- `"nav/top-nav"` → `"nav/top-nav"` (already normalized)
- `"button/small/translucent"` → `"button/small/translucent"`
- `"Safari - Bottom"` → `"safari-bottom"` (no `/` in master name →
  single-segment slash-path; still emits `-> safari-bottom`)
- `"iOS/StatusBar"` → `"ios/statusbar"` (mixed case lowered)
- `"ios/alpha-keyboard"` → `"ios/alpha-keyboard"`
- `".icons/safari/lock"` → `"icons/safari/lock"` (leading dot stripped
  by segment-normalization)

When normalization produces an empty segment (e.g. all-numeric master
name), the CompRef is dropped and the node falls through to the Mode 2
inline frame path with `component_key` preserved as `$ext.component_key`
for the renderer's Mode-1 attempt.

#### 2.7.2 Instance override flattening

Instance overrides are recorded in the `instance_overrides` DB table
and aggregated into an `override_tree` by
`dd/ir.py::build_override_tree`. **The override tree is NOT present in
the `generate_ir(..., semantic=True)` dict output** — it lives in the
raw visual-dict produced by `query_screen_visuals` and consumed by the
renderer directly, not the semantic CompositionSpec. The compressor
therefore takes a `sqlite3.Connection` alongside the dict IR so it can
query overrides directly:

```python
compress_to_l3(spec: dict, conn: sqlite3.Connection) -> L3Document
```

Once the override tree is fetched per-screen, flattening onto the
`-> ref` follows a **three-step walk**:

1. **Direct text overrides** on the INSTANCE itself → `text=<literal>`
   as a top-level property on the CompRef's NodeHead. The Figma
   renderer recognizes `text=` on a CompRef as an instance-override
   hint and resolves it against the master's default text slot.
2. **Visual or nested-text overrides** within the component's child
   tree → path-addressed property assignments using the target
   child's **layer name path** from the master. Format:
   `<child-slug>.<property>=<value>`. The child-slug is
   `normalize_to_eid(child.name)`.
3. **Instance swaps** (a child INSTANCE in the master is replaced by
   a different INSTANCE in the override) → a nested CompRef inside
   the outer ref's block:
   ```
   -> card/sheet/success #sheet {
     body = -> meme-editor/custom-layout #body
   }
   ```
   The outer ref's block is a CompRef Block (see grammar §3.2 — slot-
   fill / property-assign disambiguation applies identically).

#### 2.7.3 Override-args shorthand for slot defaults

At `define`-level slot defaults, an inline override form is available
(grammar §3):

```
slot cta = -> button/small/solid(label={cta_label})
```

This expands to:

```
slot cta = -> button/small/solid #auto {
    label = {cta_label}
}
```

The override-args form is compact and preferred at define-level slot
defaults. At call sites and at document-body CompRefs, prefer the
explicit Block form for clarity.

### 2.8 Determinism

Compression MUST be deterministic: given the same DB snapshot,
`compress_to_l3(snapshot)` MUST produce byte-identical output on re-run.
Required for Tier 2 script byte-parity.

Ordering rules:
- Elements within a parent: sorted by `sort_order`, tie-break by
  `node_id`.
- Properties on an element: **canonical total order** per grammar §7.5
  (structural → content → spatial → visual → extension → override →
  trailer, with intra-block ordering specified for each category).
- PropGroup entries: **canonical total order** per grammar §7.6 (e.g.
  `padding={top=... right=... bottom=... left=...}` in that order).
- Token block entries: sorted lexicographically by token path.
- Imports: sorted lexicographically by alias (not path), ties broken
  by path.

These rules collectively produce byte-identical output for the same
semantic input across independent emitter implementations.

### 2.9 Synthetic tokens (pre-Stage-3 posture)

Before Stage 3 clustering ships, compression emits **raw literals** for
un-tokenized values (hex colors, pixel dimensions not matching the
universal catalog). This violates Tier 0 §3.3 temporarily per the
explicit waiver in `docs/requirements-v0.3.md` §2.5.

After Stage 3:
- Colors not matching a universal catalog entry run through ΔE
  clustering → assigned to a synthetic-token entry `color.synthetic.N`
  with a stable cluster name
- Dimensions run through histogram clustering → assigned to
  `space.synthetic.N` or nearest universal entry
- Typography runs through nearest-step matching → assigned to a
  typography compound

Compressor emits the synthetic-token reference in the L3 output; the
synthetic-token DEFINITION lives in the top-level `tokens { }` block
(so round-trip remains self-contained).

### 2.10 Tokens-block internal resolution

A top-level `tokens { ... }` block MAY declare tokens that reference
other tokens inside the same block (self-referential token graph).
Example from fixture 01:

```
tokens {
  color.brand.accent.start = #D9FF40
  color.brand.accent.end   = #9EFF85
  color.brand.accent       = gradient-linear(
                               {color.brand.accent.start},
                               {color.brand.accent.end}
                             )
}
```

Resolution rules for a `tokens { }` block:

1. Build a dependency graph from token assignments. Each `TokenRef`
   inside a value establishes an edge.
2. Topological sort. Cycles are hard-errors
   (`KIND_CIRCULAR_TOKEN` — added to §9.5 of the grammar spec).
3. Resolve in topo order. Each token's resolved value is memoized.
4. Forward references within the block ARE permitted; the compressor
   does not require declaration order.

### 2.11 Fixture-vs-algorithm divergence (Stage 1 test oracle)

An intentional mismatch exists between the hand-authored reference
fixtures (`tests/fixtures/markup/01-login-welcome.dd`) and what the
Stage 1 compression algorithm emits today:

- **Fixtures:** express the DESIRED post-Stage-3 IR, with synthetic
  tokens (`{color.brand.accent}`) and clean `tokens { }` blocks.
- **Algorithm at Stage 1:** emits raw literals, because no Stage 3
  clustering has run to define synthetic tokens yet.

This is deliberate. The fixtures are the NORMATIVE GRAMMAR TARGET.
They prove the grammar is rich enough for post-Stage-3 output.

Stage 1 tests are therefore parameterized against TWO expected
outputs per reference screen:

| Test | Expected output |
|------|----------------|
| `test_fixture_parses` | Hand-authored `NN-*.dd` (grammar coverage) |
| `test_fixture_roundtrips` | `parse(emit(parse(fixture))) == parse(fixture)` |
| `test_compression_stage1` | Auto-generated `NN-*.stage1-expected.dd` — the raw-literal output of today's `compress_to_l3` against the DB screen |
| `test_compression_stage3` | Not yet — gated on Stage 3 |

Plan B Stage 1.3 creates the `NN-*.stage1-expected.dd` files by
running a first-pass compressor against each reference screen's DB
state and committing the result as a golden file. The fixture
authoring (Plan A.4) and the Stage 1 compression output diverge;
both are valid, and Stage 3 closes the gap.

---

## 3. Expansion — L3 → dict IR

### 3.1 Pipeline overview

```
  .dd source text
       │
       ▼
  parse_dd(source)                              // S2 grammar (Plan B 1.2)
       │
       ▼
  l3_ast
       │
       ▼
  resolve_namespace_imports(ast, context)       // NEW (Plan B 1.2)
       │
       ▼
  expand_pattern_refs(ast)                      // NEW (Plan B 1.2)
       │
       ▼
  resolve_token_refs(ast, context.tokens)       // NEW (Plan B 1.2)
       │
       ▼
  fill_axis_defaults(ast, context.catalog)      // NEW (Plan B 1.2)
       │
       ▼
  ast_to_dict_ir(ast, context.ckr)              // NEW (Plan B 1.4)
       │
       ▼
  dict IR  ─── hands off to ──▶  generate_figma_script(ir)   // existing
```

### 3.2 Option A vs Option B — DECISION: Option A

**Option A (chosen)** — L3 → dict IR lowering; reuse existing renderer.
- `ast_to_dict_ir` produces a dict with the same shape as
  `build_composition_spec`'s output.
- The existing `generate_figma_script(ir)` consumes it unchanged.
- Only new code: the markup-side lowering step.
- Zero risk to the 204/204 parity baseline.

**Option B (rejected for v0.3)** — L3-aware renderer.
- A new renderer path walking the markup AST directly.
- Potentially faster or better at preserving provenance in emitted JS.
- Duplicates rendering machinery; introduces parity-risk surface.
- Reserve for post-v0.3 if empirical evidence shows the dict-IR
  intermediate loses semantic information the renderer could use.

Rationale per OQ-5: "Keep the 204/204 dict-IR renderer as ground truth;
dd markup round-trip becomes 'markup → dict IR → existing renderer.'
Only new code is the markup-to-dict-IR lowering."

### 3.3 Namespace import resolution

- `use "path" as alias` — path resolution:
  - Relative path (`./file` or `../file`) → relative to importing file
  - Bare name → search path configured at parse-context creation
- Each imported file is parsed into its own AST, cached by resolved
  absolute path (for deduplication in case of diamond imports).
- Circular imports are hard-errors: `KIND_CIRCULAR_IMPORT`.

### 3.4 Pattern-ref expansion (`& name`)

For each `& name` reference:
1. Look up `name` in the enclosing document's `define` table (or,
   for `alias::name`, in the imported file's define table).
2. Expand the define body into the ref's AST position:
   - Substitute scalar-arg `{name}` refs with the provided values
   - Fill slots with the provided slot-fill NodeExpr (or the default)
   - Apply path-overrides by walking the expanded subtree and
     rewriting the target property at each `path.to.prop` address
3. Assign new EIDs to expanded nodes that were auto-id'd inside the
   define (scoped to the expansion site); explicit `#eid` inside the
   define is preserved — pattern-internal IDs are LEXICAL (not unique
   across call sites) and the lowering pass disambiguates by prefixing
   with the expansion site's eid.

### 3.5 Component-ref resolution (`-> name`)

`-> name` references stay in the dict IR until render time. The
rendering pass (`generate_figma_script`) looks up the component via the
CKR by matching the `-> <slash-path>` against the `component_name`
column. At render time:
- Hit → Mode 1: `getNodeByIdAsync(figma_node_id).createInstance()`
- Miss → Mode 2 wireframe placeholder (`feedback_missing_component_placeholder`)

The dd-markup expansion step does NOT pre-resolve components — it
leaves the `-> path` annotation in the IR for the renderer. This
preserves the fallback semantics.

### 3.6 Token-ref resolution

Per S2 §4.2, resolution order:
1. Enclosing-define param scope (during pattern expansion)
2. Top-level `tokens { }` block of the document
3. Imported tokens via `use`-aliased paths
4. Universal catalog (`_UNIVERSAL_MODE3_TOKENS` in `dd/compose.py`)
5. Unresolved → `KIND_UNRESOLVED_REF`

Resolution produces a concrete value (hex color, pixel dimension,
font family, etc.) which replaces the `{path}` in the dict IR. Token
identity is preserved separately in the IR's `tokens` map for the
renderer's Figma-variables path.

### 3.7 Axis default fill

When an axis is unpopulated on a node, defaults fill from (highest
priority first):
1. The component template default (if the node is a `-> component`
   ref and the component has a known template)
2. The pattern template default (if the node is a `& pattern` ref and
   the pattern set it in its body)
3. The canonical-type catalog default
   (`UniversalCatalogProvider.resolve(comp_type, variant, ...)`)
4. The universal-catalog shadcn defaults

If all four miss, the axis stays empty in the dict IR and the renderer
uses its built-in platform defaults (Figma's `createFrame` defaults;
see `feedback_figma_default_visibility`).

### 3.8 From AST to dict IR

The `ast_to_dict_ir` transform walks the resolved AST and produces the
dict shape compatible with `build_composition_spec`'s output:

```python
{
    "version": "1.0",
    "root": "<root-eid>",
    "elements": {
        "<eid>": {
            "type": "<type-keyword>",
            "layout": {...},   # spatial axis
            "visual": {...},   # visual axis
            "children": ["<eid>", ...],
            "_original_name": "<preserved-name>",
            ...
        },
        ...
    },
    "tokens": {...},           # System axis
    "_node_id_map": {...}      # populated only on extract-path
}
```

Specific transforms:
- `layout=horizontal gap=8 align=center padding={top=8 ...}` →
  `{"direction": "horizontal", "gap": 8, "mainAxisAlignment": "center",
    "crossAxisAlignment": "center", "padding": {"top": 8, ...}}`
- `width=fill` → `{"sizing": {"width": "fill"}}`
- `fill={color.surface.card}` → `{"fills": [{"type": "solid",
  "color": <resolved-hex>, "token": "color.surface.card"}]}`
- `fill=gradient-linear(#D9FF40, #9EFF85)` → `{"fills": [{"type":
  "gradient-linear", "stops": [{"color": "#D9FF40", "position": 0.0},
  {"color": "#9EFF85", "position": 1.0}]}]}`

The full transform table is large; Plan B Stage 1.4 implements it
against this spec and against a golden-output test suite.

---

## 4. Round-trip proof shape

The proof: extract a source Figma screen → DB → compress to L3 →
expand to dict IR → render to Figma script → execute → walk rendered
subtree → verify `is_parity=True`.

Three tiers of evidence, in order of cost:

### 4.1 Tier 1 — Dict-level round-trip

**Claim:** `expand(compress(dict_ir)) == dict_ir` for every screen.

Comparison is **structural equality** on the dict, not byte equality.
Missing `_original_name` or differing dict-key insertion order is
acceptable at Tier 1.

- Cost: single-digit seconds per screen in memory.
- Gate: Plan B Stage 1.5 (one fixture).
- Full corpus (204 screens): Plan B Stage 1.7.
- Per-commit in CI after Stage 1.7 green.

### 4.2 Tier 2 — Script byte-parity

**Claim:** `generate_figma_script(expand(compress(dict_ir)))` produces a
byte-identical JS script to `generate_figma_script(dict_ir)` for every
screen.

This is STRONGER than Tier 1: dict-key ordering and property
serialization MUST be identical. Pattern identified on `v0.3-dd-markup-probe`
branch's probe where the probe's mechanical serde was gated at Tier 2.

- Cost: ~15s for the full 204 corpus (per existing
  `tests/test_script_parity.py` runtime).
- Gate: Plan B Stage 1.7, per-PR after Stage 1 ships.

### 4.3 Tier 3 — Pixel parity via Figma sweep

**Claim:** `sweep.py` with markup-path enabled reports 204/204
`is_parity=True`. Requires a live Figma bridge; this is the ultimate
proof that the whole pipeline produces the same pixels.

- Cost: ~450s for the full 204 corpus (per the current sweep runtime).
- Gate: merge-to-main and nightly; matches
  `docs/decisions/v0.3-branching-strategy.md`.

### 4.4 CI cadence

| Tier | Runs on |
|------|---------|
| Tier 1 | Every commit (pytest fast path) |
| Tier 2 | Every PR (script-parity gate) |
| Tier 3 | Every merge to `main` + nightly |

This matches the three-tier gate of existing work on `v0.3-integration`
(see `docs/decisions/v0.3-branching-strategy.md`).

---

## 5. Density semantics

Per S2 §7.1, dd markup accepts any axis subset on any node. Not every
subset round-trips to a pixel-identical Figma file.

### 5.1 Density classes

| Density | What's populated | Round-trips to... |
|---------|------------------|-------------------|
| Full | Structure + Content + Spatial + Visual + System | Pixel-identical Figma |
| Wireframe | Structure + Spatial (no Visual, no Content, no System) | Figma with renderer-default visual + placeholder content |
| Style-only | System + Visual (no Structure) | Not a full screen — a "theme" |
| Mixed | Some axes per node, arbitrary | Figma where each node renders at its own density |

### 5.2 Round-trippability claim

Compression from the DB emits **full density** (every axis populated
with either ground-truth values or inferred-from-neighbors values).
Hand-authored fixtures at lower densities exercise the renderer's
fill-in path but do NOT round-trip to pixel parity — by construction.

Verification at non-full densities uses **structural parity**: the
rendered output has the same element tree and same elements populated
at the intended density. Missing-axis absences are NOT failures.

### 5.3 Distinguishing "intentional sparse" from "incomplete"

The grammar treats both identically — absence of an axis is legal.
Semantic intent is carried by provenance (§9 of grammar spec):
- `(synthesized conf=0.8)` — generator filled in defaults; low-
  confidence synthesis may warrant verifier attention
- `(extracted)` — missing axis means it was missing in the source
- `(user-edited stage=draft)` — author left it sparse on purpose

Verifier feedback targets low-confidence `synthesized` values first;
UI filters by provenance kind.

---

## 6. Definitions and expansion — at render time

See S2 §6 for syntax. Semantics:

### 6.1 Pattern body cycles

Expansion uses three-color DFS (white/gray/black) during semantic
analysis. A cycle is `KIND_CIRCULAR_DEFINE` (hard-error at parse
time; never reached at render time).

### 6.2 Slot ordering

Slots are filled in declaration order. The slot fill inside a
pattern-ref body is a keyword arg; the slot's position inside the
pattern body is determined by where `{slot-name}` appears in the
define.

### 6.3 Path-override application

Path overrides `container.gap=8` apply LAST in expansion order (after
scalar args and slot fills). This allows overrides to target nodes
that were created by scalar-arg or slot substitution.

Example:
```
& option-row title="Featured" container.gap=8
```
Expansion order:
1. Substitute `{title}` with `"Featured"` everywhere in the body
2. Apply any slot fills (none here)
3. Walk to `#container` (inside the body), set `gap=8`

If `#container` doesn't exist after steps 1–2, the override is a
hard-error `KIND_OVERRIDE_TARGET_MISSING`.

### 6.4 Auto-EID prefixing across pattern expansion

Per S2 §6.1, explicit `#eid` inside a define is LEXICAL to the define.
When expanded, the EID gets prefixed with the call-site's EID to stay
unique:

```
& option-row #row-recent        // → all internal eids prefix with "row-recent-"
& option-row #row-favorites     // → all internal eids prefix with "row-favorites-"
```

So `#container` inside the define becomes `#row-recent-container` and
`#row-favorites-container` after expansion. This keeps Tier 1 dict IR
internally consistent.

Address-at-edit-time continues to work via the original path:
`@row-recent/container.gap=8` still resolves.

---

## 7. Interaction with existing machinery

### 7.1 `dd/ir.py::generate_ir`

**Stays in place.** Compression is a NEW function `compress_to_l3` that
consumes `generate_ir`'s output. In Stage 1, the call graph is:

```
dd extract-screen --screen 181
  → generate_ir(conn, 181, semantic=True)  (existing)

dd compress-to-markup --screen 181         (NEW CLI — Plan B 1.4)
  → generate_ir(conn, 181, semantic=True)
  → compress_to_l3_ast(ir)
  → emit_dd(l3_ast)

dd render-from-markup --path fixture.dd    (NEW CLI — Plan B 1.5)
  → parse_dd(source)
  → expand_from_l3(ast)
  → ast_to_dict_ir(resolved_ast, ckr)
  → generate_figma_script(dict_ir)         (existing)
```

### 7.2 `dd/renderers/figma.py::generate_figma_script`

**Unchanged.** All dd-markup round-trip work lives BEFORE this function.
The renderer consumes a dict IR — whether it came from
`build_composition_spec` (extract path) or `ast_to_dict_ir` (markup
path) is opaque to it.

### 7.3 `render_batch/sweep.py`

Gets a new opt-in flag:

```
python3 render_batch/sweep.py --port N --via-markup
```

When set, each screen:
1. Extract → dict IR (as today)
2. **Compress → dd markup**
3. **Parse → expanded AST**
4. **Ast-to-dict** → dict IR'
5. Compare dict IR' to original (Tier 1)
6. Render dict IR' to Figma script (Tier 2 implicit)
7. Walk rendered subtree, verify (Tier 3)

Without `--via-markup`, behavior is unchanged (existing 204/204).

### 7.4 `dd/composition/*` (Stage 4 retrieval)

**Not touched in Stage 1.** The retrieval + generation pipeline
(cascade, CorpusRetrievalProvider, UniversalCatalogProvider) runs AFTER
Stage 1 in the staging plan. When Stage 4 arrives, generated outputs
feed INTO the dd-markup grammar at the synthesis-output boundary — the
same parser consumes both extracted and synthesized inputs.

### 7.5 Existing `dd/markup.py`

**Rebuilt in Plan B Stage 1.2.** Reusable:
- Tokenizer primitives (digit/string/identifier scanners)
- `DDMarkupError` / `DDMarkupParseError` / `DDMarkupSerializeError`
  classes with line/col
- The `tests/test_script_parity.py` Tier 2 harness pattern

Everything else — value-form parsing, definition table, pattern
expansion, token resolution, axis composition — is new code against
this spec.

---

## 8. Open questions — CLOSED

All ten open questions are resolved. Decisions below; the spec above
implements each.

### OQ-1. Which L0 nodes become L3 elements? — CLOSED: all classified + parent containers

**Decision.** All L0 nodes survive compression EXCEPT:
- Synthetic nodes (per `is_synthetic_node` allowlist) — filtered
  already by `build_composition_spec`
- Transitive descendants of synthetic nodes

Every surviving node becomes an L3 element. The ~10× reduction from
"207 L0 nodes → ~20 L3 elements" described in early docs was aspirational;
today's `generate_ir(semantic=True)` already collapses via
`filter_system_chrome` and `build_semantic_tree`. Stage 1 preserves that
existing collapse behavior and layers dd markup on top — Stage 1 does
NOT introduce new collapsing.

Deferred: aggressive collapse (sibling groups → `list<type>`) is a
**Rule-of-Three optimization pass** per Tier 0 §3.2 (user-gated, never
auto-applied). Out of Stage 1 scope.

### OQ-2. Inline vs component reference at extract — CLOSED: node_type-driven

**Decision** (matches `feedback_figma_frames_are_visual.md`):
- `node_type = INSTANCE` with non-null `component_key` → `-> <name>`
- `node_type = INSTANCE` with null `component_key` → emit as `frame`
  with a warning (`KIND_INSTANCE_UNKEYED`)
- Any other node_type → inline with its keyword (`frame`, `text`,
  `rectangle`, etc.)

FRAME is NEVER collapsed to a component ref by the extractor. A frame
in Figma is a visual element, not a structural wrapper — the extractor
preserves that intent.

### OQ-3. Inline pattern detection — CLOSED: never auto, suggest-only

**Decision** (matches Tier 0 §3.2): inline patterns stay inline.
Rule-of-Three (N ≥ 3 structural-equivalent siblings) is detected by a
separate `dd suggest-patterns` CLI pass (Stage 2 scope) that emits
SUGGESTIONS for promotion — the user approves each, then the extractor
re-runs with the new defines in scope.

Suggestions are stored in the `patterns` DB table (existing schema) with
a `status` column ∈ {suggested, accepted, rejected}. Only `accepted`
suggestions flow into subsequent extractions as defines.

### OQ-4. Synthetic token emission timing — CLOSED: Stage 3 gate

**Decision**:
- Stage 1 compression emits raw literals for un-tokenized values.
  Tier 0 §3.3 invariant temporarily waived per Tier 1 §2.5.
- Stage 3 runs clustering + synthetic-token generation between
  extraction and compression. After Stage 3, compression emits
  `{synthetic.N}` refs and declares the mapping in the doc-level
  `tokens { }` block.

This means Stage 1 round-trip proof ships with raw-literal L3 outputs.
Stage 3 closes the invariant without touching Stage 1's parser or
emitter (only the compression-step inputs change).

### OQ-5. Expansion architecture — CLOSED: Option A (L3 → dict IR)

**Decision** (see §3.2). Option A: parse → expand → lower to dict IR →
hand to existing renderer. Zero renderer changes. Option B reserved
for post-v0.3 if empirical pressure justifies.

### OQ-6. Tier 1 / Tier 2 / Tier 3 cadence — CLOSED: per-commit / per-PR / per-merge

**Decision** (see §4.4):
- Tier 1 on every commit (fast path in pytest)
- Tier 2 on every PR (script-parity gate)
- Tier 3 on every merge to `main` + nightly (live Figma bridge)

Matches `docs/decisions/v0.3-branching-strategy.md`.

### OQ-7. Density round-trippability — CLOSED: pixel for full, structural for sparse

**Decision** (see §5):
- Full-density dd markup round-trips to pixel-identical Figma (gate:
  `is_parity=True`).
- Wireframe / style-only / mixed density dd markup round-trips to
  structurally-equivalent Figma (gate: all populated axes match; absent
  axes NOT failures).
- The verifier distinguishes these modes via a `density_mode` hint on
  the `RenderReport` (Stage 5 scope — Stage 1 gate is full-density
  only).

### OQ-8. Compression determinism — CLOSED: yes, byte-stable

**Decision** (§2.8): compression MUST be deterministic. Stable sort on
`(parent_eid, sort_order, node_id)` for elements; lex ordering on
property keys; lex ordering on tokens block entries. Required for
Tier 2 script byte-parity.

### OQ-9. Override tree handling — CLOSED: flatten onto the ref

**Decision** (§2.7): Figma instance overrides from `build_override_tree`
flatten onto the `-> ref` as property assignments. Nested instance
swaps become nested `->` blocks inside the ref.

Property-path naming for overrides: use the slot/role name from the
master component when available (e.g., `label.color=...`), fall back
to the Figma layer name when not.

### OQ-10. Relationship to `generate_ir` — CLOSED: compression consumes its output

**Decision** (§7.1): `compress_to_l3_ast` consumes
`generate_ir(conn, screen_id, semantic=True)`'s output. The
`generate_ir` function stays unchanged. This keeps the existing dict-IR
layer as the authoritative intermediate; L3 is a thin layer on top.

---

## 9. Plan A.6 deliverables — CHECKLIST

- [x] All 10 open questions have decisions recorded in this spec
- [x] The compression algorithm is specified precisely enough for a
      human reader to hand-simulate it on one reference screen and
      produce the same `.dd` as the fixture
- [x] The expansion algorithm is specified precisely enough to predict
      what `generate_figma_script` would emit given a parsed AST
- [x] Round-trip proof shape specified with concrete acceptance
      criteria per tier
- [x] Relationship to existing machinery (`generate_ir`,
      `generate_screen`, `sweep.py`) diagrammed

---

## 10. Implementation hooks (preview of Plan B Stage 1)

Per Plan B in `docs/plan-v0.3.md`:

| Step | Deliverable | Against this spec |
|------|-------------|-------------------|
| 1.1 | Parser tests | §3 (expansion pipeline input) |
| 1.2 | Parser implementation | §3 (resolution, AST shape) |
| 1.3 | Emitter tests | §2 (compression output) |
| 1.4 | Emitter (compression) | §2 (per-axis derivation) |
| 1.5 | Round-trip one fixture | §4.1 Tier 1 |
| 1.6 | Round-trip 3 fixtures | §4.1 + §4.2 Tier 1+2 |
| 1.7 | Full 204 corpus | §4 all tiers |

---

*This doc defines what the dd markup MEANS at the IR level. Plan B
Stage 1 implements against it. No code for compression / expansion
before this doc is stable; no Stage 2+ work before Stage 1 ships
204/204 across all three tiers.*
