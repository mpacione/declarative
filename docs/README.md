# Declarative Design Compiler

A design-system compiler. It takes a design source (today: a Figma file)
and translates it to a design target (today: Figma again, for round-trip
validation; soon: React + HTML/CSS) through a multi-level intermediate
representation modelled after [MLIR](https://mlir.llvm.org/). Bidirectional
by construction: the same IR is both what you extract *into* and what
you render *from*.

The system is currently at the end of its "round-trip foundation" phase.
The claim we can defend today, and the load-bearing invariant for
everything downstream, is this:

> Every app screen in our test file (204 / 204) extracts to the database,
> generates a script from the database, executes that script in Figma, and
> produces a rendered subtree whose structural and visual properties match
> the original at `parity_ratio = 1.0000`, zero structured errors, across
> the entire corpus.

The verifier is not "does it look right to a human." It walks the
rendered subtree node-by-node, compares against the IR node-by-node, and
raises a structured error on any mismatch. The 204 / 204 result is
machine-checked.

## Why this project exists

Every serious design system lives twice — once as a design file, once as
production code. They drift. Token values diverge. Components diverge.
Layout diverges. The tools that exist today either convert in one
direction (Figma Dev Mode exports, Mitosis compiles JSX to frameworks),
or cover only a slice (W3C Design Tokens covers values but not layout
or components), or require a human to stitch the pieces back together.

The move inspired by LLVM is: **put an IR in the middle.** Extraction
passes become frontends. Renderers become backends. Classification,
token clustering, semantic compression become IR passes, written once,
reused by every backend. A React renderer and a SwiftUI renderer share
the same understanding of what "this FRAME is a button, its padding is
`space.lg`, its fill is the `--accent` color token" means. They just
emit different syntax.

The foundational question: *can the IR round-trip to its source with
zero loss?* If not, every consumer inherits the gap. If yes, the IR is
trustworthy and cross-platform rendering is a matter of writing more
backends.

This repo is the answer to that question, in the one-source one-target
case. Scaling to more targets is the next phase.

## What it does today

| Capability | State |
|---|---|
| **Extract** from Figma (REST API + Plugin API) | Complete for single-file pipelines; 338 screens × 86,766 nodes extracted in 221s on the test corpus |
| **Normalize** into a multi-level IR (L0 scene graph, L1 classification, L2 token bindings, L3 semantic tree) | L0 complete; L1 / L2 operational with curation UI |
| **Cluster** raw values into token proposals (colors, spacing, typography, effects, radius) | Complete; backed by materialised SQL census views |
| **Curate** proposed tokens (accept, reject, merge, rename) | CLI + batch accept-all |
| **Push** curated tokens back into Figma as live variables and rebound bindings | Complete; two-phase manifest (variables first, then rebinds) |
| **Render** the IR to a Figma script that rebuilds the file | Complete for 204 app screens; zero structural or visual drift |
| **Verify** a rendered subtree against the IR | Complete; unified structured-error channel with per-node granularity |
| **Generate** a screen from a natural-language prompt | Operational end-to-end; text → component list → IR → Figma script |
| React / HTML-CSS renderer | Not started — primary next target |
| SwiftUI, Flutter renderers | Not started — same pattern, later |
| Synthetic screen generation | Not started — next major phase |

## Architecture at a glance

```
  ┌────────────────────────────────────────────────────────────────────┐
  │                       Multi-Level IR                               │
  │                                                                    │
  │      L3  Semantic tree        (≈20 elements per screen, YAML)      │
  │      L2  Token bindings       (design-system refs on properties)   │
  │      L1  Classification       (component-type annotations)         │
  │      L0  Scene graph          (DB; 86,766 rows, 74 columns/node)   │
  └────────────────────────────────────────────────────────────────────┘
      ▲                                                      │
      │ frontends                                   backends │
      │ (extractors)                                (renderers)
      │                                                      ▼
  Figma  ───── REST + Plugin API ────┐          ┌──── Figma   (live today)
  React parser                        │          │
  SwiftUI parser       (future)       │          │     React/HTML-CSS (next)
  Sketch / Penpot                     │          │     SwiftUI  (future)
  Prompt / LLM   ────────────────────┘          └──── Flutter  (future)
```

Frontends fill as many levels as their source supports. Figma extraction
fills all four. A React parser would fill L1 + L2 (it has components and
tokens; it doesn't have Figma's scene graph). An LLM produces L3.

Backends read the **highest level available** for each property and fall
back to lower levels. A property with a token binding renders as a live
Figma variable or a CSS custom property. A property without one renders
as a literal value from L0. Both are correct; one is more portable.

### Why the IR is worth the complexity

Without it you have an M × N problem: five frontends × five backends =
twenty-five translators, each reimplementing classification, token
mapping, semantic understanding. With it, those passes are written
once and shared. Classification is a pass on L0 that writes L1.
Clustering is a pass on L1 that writes L2. Semantic compression is a
pass on L2 that writes L3.

This is the same trick LLVM uses. C, Rust, and Swift are different
languages with different constructs, but once they're in LLVM IR the
optimization passes and the machine-code backends don't care which
frontend they came from. Our intermediate representation does the same
job for design systems.

### Why Figma is the first source, and what that buys us later

Figma's REST API exposes structure; its Plugin API exposes the rest.
Between the two we get a complete scene graph, every node's transform
and sizing, every instance's component reference, every text node's
styled segments, every vector's path data. That is the *hardest*
extractor we will build — it's a visual tool with an imperative API.
Everything else (React AST, SwiftUI view hierarchy, design tokens JSON)
is a simpler shape.

Starting with the hardest source lets us validate the IR's coverage.
If L0 can express a 86,000-node Figma file without loss, L0 can express
a React tree.

## The pipeline, end to end

```
         ┌─────────┐                            ┌─────────┐
         │  Figma  │                            │  Figma  │
         │  file   │                            │ variables│
         └────┬────┘                            │+ rebound │
              │                                 │ bindings │
              ▼                                 └─────▲────┘
      ┌──────────────┐                               │
      │   INGEST     │  REST fetch (all screens)     │
      │              │  Plugin-API unified pass:     │
      │              │  • layout / sizing flags      │
      │              │  • instance overrides         │  push
      │              │  • transforms, vectorPaths    │  (two-phase manifest)
      │              │  • OpenType features          │
      │              │  → L0 database                │
      └──────┬───────┘                               │
             │                                       │
             ▼                                       │
      ┌──────────────┐                               │
      │  ANALYZE     │  Classify (L1):  catalog-matched  │
      │              │    component types (button, card, │
      │              │    tab-bar, ...)                   │
      │              │                                    │
      │              │  Cluster (L2):   color / spacing /  │
      │              │    typography / effect / radius    │
      │              │    proposals from raw property     │
      │              │    bindings                        │
      │              │                                    │
      │              │  Curate:         accept, reject,   │
      │              │    merge, rename token proposals   │
      └──────┬───────┘                                    │
             │                                            │
             ▼                                            │
      ┌──────────────┐                                    │
      │   GENERATE   │  Compose L3 semantic tree          │
      │              │  Emit Figma Plugin-API script via  │
      │              │    progressive-fallback renderer:  │
      │              │    • L2 → live variable bindings   │
      │              │    • L1 → createInstance(), real   │
      │              │           master components        │
      │              │    • L0 → literal property values  │
      │              │  Three-phase emit: Materialize →   │
      │              │    Compose → Hydrate               │
      └──────┬───────┘                                    │
             │                                            │
             ▼                                            │
     ┌──────────────┐                                     │
     │   VERIFY     │  Walk rendered subtree              │
     │              │  Compare per-node to IR             │
     │              │  Structured-error channel with      │
     │              │    per-node granularity             │
     │              │  is_parity = True required for      │
     │              │    "round-trip successful"          │
     └──────────────┘                                     │
             │                                            │
             └─────────── push (optional) ────────────────┘
```

Every box is a separate `dd` CLI subcommand. The pipeline is
composable — you can stop after INGEST and use the DB as a read-only
queryable source; you can skip ANALYZE and round-trip raw L0; you can
re-run VERIFY against any prior render.

### Safety at every boundary

Two architectural decisions (ADR-006, ADR-007) back the pipeline's
trust-worthiness:

- **Boundary contract (ADR-006).** Every external-system boundary
  (ingest from Figma, freshness-probe of Figma) runs through an
  adapter that converts transient errors, null responses, and
  malformed payloads into structured entries rather than crashes or
  silent drops. One batch timing out does not stop the pipeline; it
  produces a `KIND_API_ERROR` entry and the other batches continue.
  The same pattern will apply symmetrically on the egress side
  (synthetic IR validation before decode).

- **Unified verification channel (ADR-007).** Round-trip success is
  redefined from "no exceptions were thrown" to `is_parity == True`
  at the IR level. The renderer emits structured warnings for codegen
  degradation (e.g. `KIND_DEGRADED_TO_MODE2` when a component
  reference couldn't resolve to a real master). The runtime script
  wraps each write in a per-op micro-guard that pushes
  `{eid, kind, error}` into an `__errors` array without aborting the
  whole render. A post-render `RenderVerifier` walks the result and
  diffs against the IR. Every failure mode has a named `KIND_*`;
  every `KIND_*` is visible to tooling and potential training signal.

These two contracts make the round-trip test believable. Without them
a `is_parity=True` result could mean "everything worked" *or* "the
render silently ate three text nodes and the walk didn't notice."
With them, parity means parity.

## Numbers (Dank Experimental, the test corpus)

| | |
|---|---:|
| Figma file | Dank (Experimental), mobile/tablet meme app |
| App screens verified | 204 / 204 at `is_parity = True` |
| Nodes extracted | 86,766 |
| INSTANCE nodes (component references) | 27,811 |
| Component-key registry (Mode 1 lookup table) | 129 components |
| Content-addressed SVG path assets | 253 unique, 26,050 node references |
| Node-property token bindings | 293,183 |
| Full extraction pipeline (cold) | 221 s |
| Full corpus round-trip sweep | 449 s (2.2 s per screen average) |
| Test count | 1,979 |
| Architectural Decisions (ADRs) on record | 7 |

The parity sweep is reproducible: `python3 render_batch/sweep.py --port N`.
It writes a per-screen `RenderReport` JSON and an aggregate summary.

## Getting oriented in the code

| If you want to... | Read |
|---|---|
| Understand the IR levels and what each stores | [`compiler-architecture.md`](compiler-architecture.md), §3 |
| Understand the renderer's three-phase emit and progressive fallback | [`compiler-architecture.md`](compiler-architecture.md), §5 |
| See every module's purpose and public API | [`module-reference.md`](module-reference.md) |
| Understand why things are the way they are | [`architecture-decisions.md`](architecture-decisions.md) (ADR-001..007) |
| See how renderers transform values per platform | [`cross-platform-value-formats.md`](cross-platform-value-formats.md) |
| See the measured extraction performance numbers | [`extract-performance.md`](extract-performance.md) |
| See what's coming next | [`roadmap.md`](roadmap.md) |

## Quick start

```bash
# One-time setup: Python deps, Node deps (for Desktop Bridge), .env
git clone <repo> && cd declarative-build
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
echo 'FIGMA_ACCESS_TOKEN=figd_...' > .env

# Extract a Figma file to SQLite
python3 -m dd extract "https://www.figma.com/design/<FILE_KEY>/<Name>"

# (Bridge must be connected for the next two — see dd/ingest_figma.py and
#  ~/.figma-console-mcp/ for setup. The extract-plugin step collects
#  fields the REST API doesn't expose.)
python3 -m dd extract-plugin --port 9231

# Render one screen end-to-end and check parity
python3 -m dd generate --screen 324 > /tmp/out.js
node render_test/walk_ref.js /tmp/out.js /tmp/walk.json 9231
python3 -m dd verify --screen 324 --rendered-ref /tmp/walk.json

# Sweep the whole corpus
python3 render_batch/sweep.py --port 9231
```

## Current limits, honestly

- **One source, one target.** Figma → Figma. React/CSS is next, not yet.
- **One file tested.** Dank Experimental is the entire corpus; generalisation
  to other Figma files is plausible given the extractor is registry-driven,
  but is not yet demonstrated at the same depth.
- **Token clustering is heuristic.** It works on the test corpus but the
  proposals benefit from curator review before push. Calling this
  "clustering + curation" is accurate; calling it "fully automatic" is
  not.
- **No persistence contract across Figma file edits.** If someone renames
  the source file's components between extract and render, the CKR-based
  lookup will emit a wireframe placeholder (the placeholder pattern is
  intentional — it's visible to human review rather than silent blank).
- **Plugin-API extraction requires a running Figma Desktop bridge.** The
  REST-only path covers ~75 % of properties; the last 25 % (relative
  transforms, vector paths, OpenType features, overrides) needs the
  Plugin API. That's a build-time dependency, not a runtime one.
- **Synthetic generation is the next phase, not this one.** The
  architecture is positioned for it (capability-gated emission doubles
  as a constrained-decoding grammar; the verification channel gives
  dense training signal) but the code isn't there yet.

## What's next

The headline item on the roadmap is a **React + HTML/CSS renderer** —
the first genuinely new backend and the first real test of the IR's
cross-platform claim. In parallel we're beginning work on **synthetic
screen generation**: text prompts (and eventually image/sketch inputs)
through a Claude-API-driven generator that emits IR, which the existing
Figma renderer (and, soon, the React renderer) turns into running
output.

See [`roadmap.md`](roadmap.md) for the full picture.
