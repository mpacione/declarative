# Roadmap

## State of the project

The "round-trip foundation" phase is complete. Every app screen in the
Dank Experimental corpus (204 / 204) extracts, re-generates, and
re-renders at `is_parity = True` against a structured-error verifier.
The IR, the Figma extractor, the Figma renderer, and the verification
channel are load-bearing and tested under one real-world design file.

With that foundation paid for, the roadmap splits three ways:

1. **Second renderer.** The IR's cross-platform claim is unverified
   until there's a second backend. That's the top priority.
2. **Additional extractors.** Lower priority — Figma is the hardest
   source shape and it's already covered. We'll add extractors when
   there's concrete pull for one, not because the matrix wants filling
   out.
3. **Synthetic screen generation.** The next major phase. The
   architecture was designed with this in mind; the commodity LLM
   landscape is at the point where it's tractable.

## Priority 1 — React + HTML/CSS renderer

The next backend. Rationale:

- **The web is the largest UI target.** Anything we learn from a React
  renderer applies to every other SPA framework variant.
- **The IR's L2 token layer maps cleanly to CSS custom properties.**
  A `{space.lg}` binding becomes `var(--space-lg)`. Live theming falls
  out for free; so does OS-level dark-mode media query handling.
- **The IR's L1 classification layer maps cleanly to JSX component
  types.** A node classified as `button` becomes `<Button />`, imported
  from a generated component library that's a React translation of the
  Figma master component.
- **The IR's L0 layer maps cleanly to inline / CSS-module styles.**
  The progressive-fallback contract carries over: tokens where
  available, component types where classified, literal values where
  not.

### Scope

| Piece | Approach |
|---|---|
| Output shape | One `.tsx` file per screen + a shared `tokens.css` + a shared component library. No runtime dependencies beyond React + a CSS-module loader. |
| Token emission (L2) | `tokens.css` with CSS custom properties per mode (light / dark / brand). JSX reads via `var(--name)`. |
| Component emission (L1) | Imported `<Button />`-style JSX for each classified instance. Master components compile to standalone React components in a generated `components/` directory. Overrides map to props. |
| Raw property emission (L0) | CSS modules per screen. Each declarative property (fill, stroke, corner radius, layout) gets the same per-backend value transform the Figma renderer already defines (hex → `rgba()`, font weight stays numeric, rotation in deg, alignment `"start"` → `"flex-start"`). |
| Layout | Auto-layout frames → flex containers. Absolute children → `position: absolute` with the constraint-model translated to `left/right/top/bottom + flex-shrink`. |
| Vector assets | The content-addressed SVG store already holds normalised path data. React renderer emits inline `<svg>` or imports from `public/assets/<hash>.svg`. |
| Raster assets | `<img src>` pointing at exported files. |
| Text | `<span>` / `<p>` with inline style, OpenType features via `font-feature-settings`. |
| Verification | Same unified verification channel as Figma. The rendered React tree walks through a DOM-to-IR reverse function; parity is checked with the same `dd verify` code path. A new `RenderVerifier` specialisation per backend, not a new pipeline. |

### What makes this not a rewrite

Most of the hard work is already in the IR. The renderer is
registry-driven: every Figma property has a `FigmaProperty` entry
with an emit pattern and a capability gate. Adding a React renderer
is (approximately) adding a second emit pattern per registry entry,
not writing a second compiler.

The three-phase emit pattern (Materialise → Compose → Hydrate) applies
differently in React (JSX is declarative; Figma is imperative) but the
underlying phases exist: materialisation is the JSX tree literal,
composition is the component hierarchy, hydration is client-side
effects (fonts loading, images resolving, state).

### What it unlocks

- First real test of the "progressive fallback" promise with a
  different platform's tokens / component-import conventions.
- A reference target for cross-platform parity testing: if the same
  Figma source renders to a React tree whose DOM walks back to an IR
  that matches the original, the IR is honest about what it contains.
- A plausible "preview" artefact for synthetic generation before we
  have a full round-trip story for React.

## Priority 2 — Additional renderers (SwiftUI, Flutter)

Same pattern as React. Different per-backend value transforms (see
`docs/cross-platform-value-formats.md` for the table). Different
component-instantiation syntax. Different flexbox dialect.

SwiftUI and Flutter both have first-class token / theme mechanisms
(`.foregroundStyle(.accent)`, `ThemeData`), which makes L2 binding
emission straightforward.

These renderers will come after React is proven. They aren't
technically harder; they're scheduled later because the cross-platform
claim is already validated once React works.

## Priority 3 — Additional extractors

Currently: Figma only. Figma is the hardest source (imperative API,
deep scene graph, vector-path authoring primitives). Every other
extractor will be easier.

Plausible future extractors:

- **Design tokens JSON (W3C DTCG).** Single-level import — just the
  token layer, no scene graph. Cheap to build, useful for bootstrapping
  a design system without a Figma file.
- **Sketch, Penpot.** Alternative design tools. Shape is close to
  Figma's; extractor would be a variant of the Figma one.
- **React / SwiftUI parsers.** Reverse of the renderer. Parses a
  component library into L1 + L2 (token refs + component types). Would
  let us ingest production code into the IR. High value, less urgent.

The trigger for any of these is concrete pull (a user, a corpus, a
use case), not roadmap completeness.

## Priority 4 — Synthetic screen generation

The next major phase after this "release." The architecture has been
built with this in mind from the start; the infrastructure now exists.

### The claim we want to test

Given a natural-language prompt ("a settings screen with account info
and notification toggles"), and the existing IR plus Figma renderer,
can we produce a real Figma file that:

1. Is structurally correct (a Figma file, not a hallucination)
2. Uses real component masters from the design system when possible
3. Uses real design tokens when possible
4. Renders without errors and passes the verifier
5. Is idiomatic enough that a human designer would use it as a
   starting point

This is a very different problem from "have the LLM write Figma
Plugin API JavaScript directly." That approach produces invalid code,
hallucinated APIs, and no grounding in the design system.

### Generation target: the IR, not the script

The generator emits **synthetic IR**, not Figma scripts. The existing
Figma renderer (the one that now achieves 204 / 204 parity) turns IR
into scripts deterministically. The LLM's job is to produce a valid
IR tree; the deterministic renderer's job is to turn valid IR into
valid Figma.

This split matters because:

- The IR is a smaller, more constrained output space than
  Plugin-API JavaScript.
- The IR has a formal structure we can validate before rendering
  (see boundary contract, below).
- Any improvement to the renderer (new property support, new
  component handling, bug fix) automatically applies to synthetic
  output without retraining.
- Training signal flows back through the existing verifier:
  generated IR → render → walk → `is_parity` → reward.

### The fall-through chain

When the generator wants a component that doesn't exist in the
design system's component library, it has options in order:

1. **Component library (CKR).** If the design system has a master
   for what the generator wants (a `button/primary`, a `card`,
   a `tab-bar`), the IR emits a Mode-1 INSTANCE referencing it by
   `component_key`. The renderer resolves this to a real
   `createInstance()` call.

2. **Symbols in the DB (L0 patterns).** If no published master
   exists but the database contains structurally similar subtrees
   — repeated patterns detected by the extraction pipeline — the
   generator can reuse those patterns as inline IR subtrees.

3. **Raw property composition (L0 bottom-up).** If neither a
   master nor a pattern matches, the generator composes a frame
   from first principles using the property registry: a FRAME
   with the right layout flags, the right padding, the right
   children. This is what the LLM is worst at doing well, so it's
   the fallback of last resort.

4. **Robust default set.** A small, curated library of
   "default" components (a plain button, a plain card, a plain
   text input) that exist as fallback fixtures independent of the
   design system being worked with. The IR gets a valid subtree
   even when the design system is empty.

### Input modalities

Priority order:

1. **Text prompt.** First milestone. "Create a login screen with
   email, password, and a submit button."
2. **Text prompt + context.** "Create a login screen for the Dank
   app" — grounded in an available component library and existing
   screens. The generator learns to mimic style.
3. **Sketch / wireframe.** Low-fidelity hand-drawn or digital
   sketch. Output respects the sketch's spatial layout.
4. **Screenshot reference.** Produce an editable Figma version of
   a screenshot, using the design system's components where the
   screenshot's elements map to them.

All four go to the same IR; they differ in how the prompt gets
parsed into generator context.

### Model

**Claude API to start.** Two reasons:

1. **Prompt caching + tool use give us iteration cheaply.** The
   design-system component catalog, the token palette, the IR
   schema, and the fall-through contract can live in a cached
   system prompt. The generator's job is a tool-use loop.
2. **Constrained decoding via tool schemas.** Anthropic's tool-use
   type system is strict about argument shapes. Every synthetic
   IR node is a structured tool call; the schema pre-validates the
   shape before we even render.

Later, plausibly:

- **Fine-tuned smaller model.** Once we have enough rendered
  synthetic output to supervise a fine-tune, a local Llama or
  Mistral variant could be cheaper and faster than Claude API per
  screen.
- **Something more exotic.** Diffusion-style generation over the
  IR graph, RL from the verifier's parity signal, or constrained
  decoding with a proper grammar (see below). Open question.

### Why this architecture positions us well

This isn't "a generator bolted onto the side of a compiler." The
compiler's invariants happen to also be exactly what a generator
needs:

- **Capability-gated emission as a constrained-decoding grammar.**
  Every property in the registry has a per-backend capability
  table. `is_capable()` answers "can this backend express this
  property on this node type?" at every emission site. Flip that
  around: at generation time, `is_capable()` answers "is this
  token sequence valid in the grammar?" The same table that
  drives emission also drives generation validity. No separate
  grammar file to maintain. See `feedback_capability_gated_emission.md`.

- **Boundary contract as pre-decode validation.** ADR-006 defines
  a `BoundaryContract` protocol with structured failure modes
  at every external-system edge. Synthetic IR crossing into the
  renderer is another edge — it goes through the same validation
  surface. Invalid structure becomes a `KIND_*` structured error,
  not a crash.

- **Verification channel as dense training signal.** ADR-007
  refactored round-trip success so every failure mode has a
  named `KIND_*` at node granularity. Rendering 1,000 synthetic
  IR trees produces 1,000 `RenderReport`s, each with per-node
  `is_parity` and a list of structured errors. That's dense
  supervised signal per screen. For RL, it's a reward function
  that's not "was there a compile error" (too coarse) but
  "which of 87 nodes failed which way" (fine-grained and
  typed).

- **Corpus of (source, IR, render, report) tuples.** We already
  have 204 source screens, 204 IR trees, 204 renders, 204
  reports. Every new extraction grows this. For supervised
  fine-tuning, that's the data.

### Open questions (to plan explicitly in the next phase)

- **Training signal shape.** Supervised fine-tuning on
  (prompt, IR) pairs vs. RL with the verifier as reward vs.
  pure prompting + retrieval over the catalog? Probably a mix;
  we don't know yet.
- **Catalog bootstrapping.** The generator is only as good as
  its knowledge of the component library it's targeting.
  Automatic generation of a catalog-augmented prompt from the
  CKR + token palette is a sub-project.
- **Structured-output vs. free-form.** Claude tool-use gives
  us strict argument shapes but limits call granularity. A
  tree with 87 nodes needs 87 tool calls or one giant one.
  Tuning this is real engineering work.
- **Evaluation.** "Does this look like a good settings screen"
  is not a machine-checkable rubric. We'll need human-
  evaluation tooling in addition to `is_parity` sweeps.

## Supporting work

### Closing remaining verifier kinds

The 204/204 parity sweep is clean against today's verifier. As the
verifier gets stricter, new failure kinds will surface. Known
candidates:

- **Gradient stop comparison.** Current check is SOLID-only.
  Gradient-stop color comparison is the next visual-fidelity
  resolution level.
- **Icon variant drift.** Verifier currently doesn't detect
  wrong-master instance swaps (wrong icon chosen for a slot).
  Needs IR ↔ SOURCE via `ResourceProbe` (ADR-006).
- **Shadow colour / offset comparison.** Current check is
  count-only on effects.

Each new kind is additive — it strengthens the test but doesn't
invalidate existing parity claims.

### Corpus scaling

Dank Experimental is one file. The extractor is registry-driven and
shouldn't be file-specific, but this is unproven. Testing against
other real-world Figma files is part of the pre-generation phase,
because the generator needs a catalog of *styles* to mimic and a
single-file corpus limits that.

### Public surface

The CLI is stable (`dd extract`, `dd extract-plugin`, `dd cluster`,
`dd curate-report`, `dd generate`, `dd verify`, `dd push`). The
Python API is not — it's still reshaped regularly as the internal
architecture evolves. A long-term question is whether to expose
this as an MCP server, a REST API, or keep it CLI-first. No plan
yet; flagging as an open question.

## Non-goals (for now)

- **Pixel-level visual diffing.** Our verifier is structural +
  semantic, not screenshot-based. Pixel-level diffs are noisy
  against font rendering and anti-aliasing; they are not how we
  define correctness.
- **Supporting every Figma plugin.** We handle the core design
  properties. Plugins that write custom data to `pluginData` or
  to non-standard property types are out of scope.
- **Live-edit round-tripping.** The pipeline is one-shot: extract,
  transform, render. Watching a Figma file for edits and keeping
  a mirror in sync is a different system.
- **A UI.** This is a library + CLI + MCP-adjacent tooling. A
  graphical curator dashboard is not planned.
