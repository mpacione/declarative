# Compression + Efficiency Profile — v0.3 Dank Corpus

**Generated:** 2026-04-19 via `python3 scripts/profile_compression.py` on
the full 204-screen Dank Experimental corpus. Raw per-screen CSV at
`render_batch/compression-profile.csv`.

Answers the question: where does the compiler spend bytes, and where are
the cheapest optimisation wins before M5/M6?

## Pipeline byte sizes (204 screens, full corpus)

| Stage | Total | Mean/screen | Median | Max |
|---|---:|---:|---:|---:|
| DB (raw row data) | 143.9 MB | 705 KB | 715 KB | 1.11 MB |
| dict IR (spec JSON) | 23.6 MB | 116 KB | 124 KB | 194 KB |
| **L3 markup AST** | **2.56 MB** | **12.5 KB** | **13.5 KB** | **27 KB** |
| Figma script (baseline) | 32.2 MB | 158 KB | 164 KB | 289 KB |
| Figma script (Option B) | 32.1 MB | 157 KB | 164 KB | 288 KB |

## Compression ratios (output / input)

| Stage transition | Mean | Median | Min | Max |
|---|---:|---:|---:|---:|
| DB → spec | 16.5% | 17.1% | 9.5% | 21.6% |
| spec → L3 markup | **10.3%** | 10.6% | 4.3% | 15.3% |
| L3 markup → script | **13.4×** | 12.6× | 10.0× | 20.8× |
| spec → script | 1.33× | 1.34× | 0.77× | 1.70× |
| Option B / baseline script | 0.997 | 0.997 | 0.988 | 1.008 |

## Plugin API op counts

| Operation | Mean | Median | Max |
|---|---:|---:|---:|
| dict IR elements | 392 | 421 | 625 |
| L3 AST emitted eids | 93 | 95 | 192 |
| createNode calls | 96 | 98 | 194 |
| appendChild calls | 95 | 97 | 193 |
| loadFontAsync calls | 21 | 21 | 34 |

**Largest screen ceiling:** 289 KB script, 194 createNode calls.

## Key findings

### 1. L3 markup is a big compression win

L3 markup is **10.3% of the dict IR** and **1.8% of raw DB bytes**. Mean
12.5 KB per screen; max 27 KB. The grammar's axis-polymorphic encoding is
doing real work: the same information that takes 705 KB in raw DB
compresses to 12.5 KB in L3 markup — a **56× reduction**.

**Implication for synthetic generation:** every L3 screen fits in an LLM's
context window comfortably. Even the max-size screen (27 KB ≈ 7K tokens)
leaves room for 50+ screens in a 128K context — enough for corpus-retrieval
patterns (v0.2 Mode 3) without chunking.

### 2. The Figma script is the expensive stage

The script is **13.4× the size of the L3 markup** that generated it. On an
average screen that's 12 KB → 158 KB. The script expansion comes from:

- **Per-node boilerplate** — each node gets `const nN = figma.createX();`,
  `nN.name = "..."`, `M["eid"] = nN.id;`, plus any properties. ~10–15 lines
  per node minimum, ~1 KB at average line length.
- **Mode 1 `createInstance` IIFEs** — each instance node expands to a
  ~300–500 byte async IIFE with `getNodeByIdAsync` + fallback-chain error
  guards + `_missingComponentPlaceholder` reference.
- **Override tree emission** — swap targets and per-property overrides each
  emit a `try { ... } catch` wrapper.
- **Phase 3 ops** — resize, position, constraints; each wrapped in
  `try { ... } catch` for the ADR-007 per-op guard.

### 3. Script expansion is constant per node

`script_bytes / createNode_calls` ≈ 1,640 bytes per node on average.
That's the per-node "overhead" baseline pays:

- createCall + name + fills-clear + clipsContent-clear + M[] assignment
  ≈ 180 bytes structural
- visual emission (fills/strokes/effects) ≈ 300–800 bytes (varies by type)
- layout emission (resize, layoutMode, paddings, align) ≈ 150–300 bytes
- text emission (fontName, characters, align) ≈ 300 bytes on text nodes
- Mode 1 nodes get an additional ~400 bytes for the createInstance IIFE
- override tree per instance adds 100–500 bytes depending on override count

### 4. Option B matches baseline within 0.3%

Across 204 screens the Option B script is **0.997× baseline size on
average** (min 0.988, max 1.008). Pixel-parity is 204/204 (M4 gate). The
markup-native path produces structurally-equivalent output; the tiny
~0.3% delta is known edge cases (see M2+ list below).

## Figma Plugin API constraints

Against Figma's known limits:

- **Script execution size**: no documented hard cap, but practical limits
  around 2–5 MB before the plugin evaluator gets sluggish. Max observed
  289 KB is well under (**~6% of the soft ceiling**).
- **Async op count**: 21 `loadFontAsync` + ≤194 `getNodeByIdAsync`
  prefetches + 1 `await new Promise(setTimeout, 0)` per phase. Around
  250 async boundaries worst-case. Within the Plugin API's comfortable
  operating range; the live 204-screen sweep clocked **mean 2.6 s per
  screen**.
- **Number of `appendChild` calls**: ≤194 per screen. No known limit;
  linear cost. Live render handles this in seconds per screen.

## Optimization candidates (ranked by value)

### Tier 1 — high-impact, low-risk

**a. Shared try/catch helper function**
Every Phase 3 op is wrapped in an inline `try { ... } catch (__e) { __errors.push(...); }`. For 100+ ops per screen, that's 60–80 bytes per
wrapping × 100 = 6–8 KB of boilerplate. A preamble-defined helper
`_op(var, kind, thunk)` could collapse each to ~30 bytes. Estimated
saving: **10–20% script size reduction**. Risk: low (pure refactor of
the boilerplate).

**b. Property-bag bulk-assign**
Sequences of `nN.x = 10; nN.y = 20; nN.width = 100; nN.height = 50;` (4
separate statements) could compile to `Object.assign(nN, {x:10, y:20,
width:100, height:50})`. For the 5–10 property-bags per node, this
would save 30–50% of the property-emit bytes. Estimated saving:
**~5–10% script size**. Risk: low.

**c. Shared Mode 1 createInstance helper**
The `const nN = await (async () => { ... })()` IIFE is near-identical
across every Mode 1 node. Extract to a preamble helper
`_makeInst(id, fallbackName, w, h, eid)` and each call site collapses
from ~450 bytes to ~80. On a screen with 30 Mode 1 nodes (the median),
that's 10 KB saved — **~6% script reduction**. Risk: low; the fallback
logic remains identical.

### Tier 2 — moderate impact

**d. Deduplicated shared paint arrays**
20 nodes with the same SOLID white fill each emit a full
`fills = [{type:"SOLID", color:{r:1,g:1,b:1,a:1}}]` — ~60 bytes × 20 =
1.2 KB. Could hoist to a preamble `const _whiteSolid = [...]` and
reference by variable. On high-repetition screens could save 5–10 KB.
Risk: moderate — caller's mutation of the array would leak to all
referencing nodes; needs immutable pattern.

**e. Font prefetch cache across screens**
Currently each screen re-emits its 21-on-average `loadFontAsync` block.
For a corpus sweep this is 21 × 204 = 4,284 font-load awaits. A
single-sweep preamble that loads all corpus fonts once could drop the
per-screen overhead to zero and speed up the full sweep by ~2× (font
loading is async and dominates non-render time).

### Tier 3 — architectural

**f. Figma plugin-side helper library**
If we ship a small JS library alongside the plugin (~5 KB), loaded
once per session, every generated script could `importScripts` it and
shave its preamble down to a single `const __errors = []; const M = {};
const _rootPage = figma.currentPage;` — eliminating ~95% of the
preamble boilerplate. Risk: higher — requires plugin-side cooperation.

## Script size vs LLM context

The 12.5 KB median L3 markup is **~3,200 tokens** (gpt tokenizer).
Claude 3/4 handles this comfortably. The full 204-corpus L3 markup is
**~640K tokens total** — above 200K context but retrievable via
corpus-retrieval (v0.2 Mode 3 precedent).

In contrast, the 158 KB median baseline Figma script is **~40K tokens**
— 12× worse for LLM-in-the-loop workflows. The grammar earns its place
as the LLM-facing IR.

## Numbers for M5/M6 planning

- **M6 cutover script-size impact:** zero. Option B script is already
  within 0.3% of baseline across the corpus.
- **Post-M6 optimization envelope:** if Tier-1 optimizations (a+b+c) land,
  script size would drop from 158 KB median to ~110 KB median (~30%
  reduction), and the max would drop from 289 KB to ~200 KB.
- **LLM fine-tune target:** L3 markup averages 3.2K tokens per screen —
  a 10K-screen dataset fits in 32M tokens, within single-epoch fine-tune
  budgets.

---

*Profile raw data: `render_batch/compression-profile.csv` (204 rows).
Regenerate: `python3 scripts/profile_compression.py --csv <path>`.*
