# How it works

A walkthrough of the proposed system, for designers and design-systems
people who are comfortable with technical ideas but don't need compiler
theory to get the point.

The short version: **this is a system for generating real designs, in
real design systems, from natural-language intent.** The foundation —
the compiler that turns an existing design into a typed representation
and renders it back out losslessly — is built and verified on a real
production file. The generation layer on top is the proposed next
phase, partially built, being validated in stages.

This document walks the architecture end to end and says out loud what
is shipped and what is not.

---

## 1. What the system is for

Design tools generate layouts now. They can suggest components,
rearrange elements, even produce whole screens from a prompt. What they
can't yet do is generate a design that uses **your** components, binds
to **your** tokens, respects **your** conventions, and produces
something a senior designer on your team would accept as a starting
point.

The reason isn't model intelligence. It's that the target is wrong. If
you ask an LLM to write Figma Plugin API JavaScript, it hallucinates
methods and invents properties. If you ask it to emit pixels, you lose
the design system. If you ask it to emit JSON that a renderer consumes,
you lose the constraint that values must reference tokens rather than
being raw.

```
  What can the LLM be asked to emit?

   ✗  Figma Plugin API JavaScript
      → hallucinated methods, invalid code, no system awareness

   ✗  pixels / raw layout
      → no design system; output is decoration, not a part

   ✗  free-form JSON
      → raw values leak in; nothing stops `#FF0000`

   ✓  a small, typed markup language
      where every value is a token reference,
      every component is a canonical type,
      every layout choice is grammatical —
      and the grammar rejects anything else.
```

The bet this system makes: **if you give an LLM a heavily constrained
symbolic language — one where every value is a token reference, every
component is a canonical type, and every layout choice is grammatical
rather than geometric — then generation becomes tractable within that
vocabulary.** The LLM writes a small amount of that language. A
deterministic compiler does everything below it. And the system can
verify, end to end, that the pipeline between intent and pixels doesn't
lose information.

Everything that follows exists so that language, that compiler, and
that verifier can work.

---

## 2. The four levels of representation

Before anything else, the idea that structures the whole system: the
**multi-level intermediate representation**, or IR.

Every design can be described at several levels of detail at once. Take
a single button on a screen:

```
L3   Semantic intent
     button "Sign in" variant=primary size=lg

L2   Token bindings
     fill    = {color.brand.600}
     padding = {space.md, space.lg}
     radius  = {radius.md}

L1   Canonical identity
     canonical_type: "button"
     variant: "primary"
     component_key: a7f2… (reference into the project library)

L0   Scene graph
     FRAME, 160×48, fill #09090B, stroke none, cornerRadius 8,
     parent_id 22001, children: [TEXT "Sign in", …], …
```

Each level adds information on top of the one below. None of them
replaces it. L0 is always the complete, lossless description. L1, L2,
and L3 are annotations and abstractions.

The direction of work through the stack determines what the system is
doing:

```
   Extraction (bottom-up)          Generation (top-down)
   ──────────────────▲             ▲──────────────────
                     │             │
              Figma file       Natural-language prompt
                               (LLM writes L3)

   Rendering (reads highest level available)
   ──────────────────▼
               Figma / React / SwiftUI / …
```

**Extraction** is bottom-up: parse the Figma file, fill L0 completely,
classify L1, cluster L2, compress to L3.

**Generation** is top-down: the LLM writes a short L3 document; the
compiler lowers through L2 and L1 to L0; the renderer emits the target.

**Rendering** is direction-agnostic: at each node, use the highest level
available. A fill with a token binding renders as a live Figma variable
or a CSS custom property. A fill without one renders as its literal L0
value. Both are correct; one is more portable.

This IR, all four levels, is shipped and validated. Everything else in
the document is a specific layer of the stack or a process that runs
across it.

---

## 3. Extraction — turning Figma into data

Figma gives you a file. To reason about it you need a queryable
database.

The extractor reads a Figma file through two APIs:

- **REST API** (fast, covers ~75% of properties). Bulk-fetch node
  trees, iterate, write to SQLite.
- **Plugin API bridge** (slower, covers the other 25%: rotation
  decomposition, vector authoring paths, instance overrides, OpenType
  features). A small custom Figma plugin runs in Figma Desktop and
  accepts commands over a local WebSocket.

```
        Figma file
            │
        ┌───┴───┐
        ▼       ▼
       REST   Plugin
       API    API bridge
        │       │
        └───┬───┘
            ▼
       SQLite DB  (L0)
```

The result is a SQLite database with roughly 87,000 nodes and 77
properties per node on a real production Figma file with a few hundred
screens. Extract time: around 220 seconds for a whole file.

A key discipline: **extract everything losslessly.** If a property is
dropped at extract, it can never be recovered at render. L0 is ground
truth; everything above is rebuilt from it.

---

## 4. Classification — naming the parts

Extraction gives you a FRAME with properties. Classification tells you
what the FRAME **is**. A button? A card? A modal? A navigation bar? A
skeleton loader?

This matters because generation can't compose from a corpus unless the
corpus is labelled. You can't ask "show me your buttons" of a file that
doesn't know what its buttons are.

Classification runs five sources in parallel and reaches consensus:

1. **Formal** — exact match against the project's component library.
   If a node is an INSTANCE of `button/primary/lg`, we know it's a
   button. No guessing.
2. **Heuristic** — size, position, and structural rules. A 44×44 square
   at the top-right of the screen is probably an icon button.
3. **LLM (text)** — Claude reads node metadata: name, type, structure.
4. **Vision (per-screen)** — Claude sees a cropped screenshot of the
   node plus its ~2× surrounding context.
5. **Vision (cross-screen)** — Claude sees similar nodes grouped
   across the whole file, to catch patterns that a single crop misses.

A sixth source, **Set-of-Marks**, renders the full screen with
numbered overlays on every candidate node and asks the model to
identify each overlay. It currently beats the individual vision sources
on hard cases.

What each source actually sees, for one candidate node (a 44×44 icon
in a toolbar):

```
  formal      Component Key lookup               → icon_button ✓
  heuristic   size + position + structure        → icon_button (0.7)
  LLM text    node name + metadata + tree        → icon_button
  vision PS   cropped screenshot + ~2× context   → icon_button
  vision CS   same-type nodes across the file    → icon_button
              (pattern recognition)
  SoM         full screen with numbered          → node #17 = icon_button
              overlays on every candidate
```

```
            INPUT: a FRAME with properties
                        │
        ┌──────┬────────┼────────┬──────┐
        ▼      ▼        ▼        ▼      ▼
     formal  heur.    LLM     vision   SoM
                     text    (PS + CS)
        └──────┴────────┬────────┴──────┘
                        ▼
                 consensus rules
                        │
                ┌───────┴───────┐
                ▼               ▼
             classify       disagreement
                                │
                                ▼
                         human review
                                │
                                ▼
                     feedback → rule calibration
```

Results feed a decision tree: unanimous → classify; majority with one
unsure → classify; real disagreement → send to a small human-review
tool, where the adjudications feed back into consensus-rule
calibration. The classifier learns from its own disagreements.

The catalog currently has 65 canonical types — button, text_input,
card, modal, tab_bar, progress_bar, spinner, toast, and so on — derived
from a survey of design systems (shadcn, Material, Clay, Ferret-UI,
ARIA).

Current state: shipped and running on a real production file. The
consensus rules and thresholds are calibrated on that one file;
generalising to a second project is a known next step, not something
that's been validated.

---

## 5. Tokens — the design system's language

In a design system, no one says "fill = #09090B". They say "fill =
`{color.surface.primary}`". When the brand updates, every surface
primary updates. The system's values aren't literal; they're
references.

The clustering pass walks L0, finds raw values that appear many times,
and proposes tokens:

- **Colour** — cluster in OKLCH space using ΔE as the distance metric.
  Perceptually uniform grouping by hue and lightness.
- **Spacing** — detect the modular grid (often 4, 8, or 16 pt
  multiples) and propose a scale.
- **Typography** — detect the type scale as ratios against a base size
  (1.125, 1.25, 1.333 …) and propose heading + body styles.
- **Radius, effects, borders** — cluster on numeric similarity.

Proposals are conservative and reviewed by a human curator before
push-back. Once curated, the system writes them back to the source
Figma file as live **Figma Variables** and rebinds every qualifying
property on every qualifying node. The original file benefits from the
abstraction, not just the generated output.

```
  raw values         cluster           curator           push to Figma
  (from L0)   ───►   into tokens  ───► review      ───►  as live Variables
  47 greys           (OKLCH + ΔE,                        + rebind bindings
  23 blues           modular grid,
  12 radii           type ratios)
  …
```

When L3 references a token like `{color.brand.600}`, it resolves
through a three-step cascade:

```
  L3:  fill = {color.brand.600}
              │
              ▼
   1. project tokens        → found? use it.
      (curated, pushed to        │
       Figma Variables)          ▼ no

   2. synthetic tokens      → found? use it.
      (auto-clustered from       │
       L0; not yet curated)      ▼ no

   3. universal catalog     → use it.
      (shadcn-flavoured
       defaults for cold
       start)
```

For projects without tokens yet, generation falls through to a
**universal default catalog** (currently shadcn-flavoured) so
cold-start synthesis still produces coherent output.

A hard rule across the whole system: **no raw values ever appear in
generated output.** Every colour is a token reference, every spacing
is a scale step, every radius is a named size.

---

## 6. The markup — what the LLM writes

To make the compression concrete: here's what the Figma API returns
for a single button node, and the same node expressed in L3.

```
  Raw (L0 as Figma returns it)        L3 markup

  {                                    button #submit
    "id": "22068",                       "Sign in"
    "type": "FRAME",                     variant=primary
    "absoluteBoundingBox": {             size=lg
      "x": 24, "y": 180,                 fullWidth
      "width": 380, "height": 48       
    },
    "fills": [{                        5 lines. No raw values.
      "type": "SOLID",                 No Figma API. LLM-writable.
      "color": {
        "r": 0.035, "g": 0.035,        Lowers back to exactly the
        "b": 0.043, "a": 1             raw on the left. No loss.
      }
    }],
    "strokes": [],
    "cornerRadius": 8,
    "layoutMode": "NONE",
    …60 more properties…
  }

  ~50 lines, ~70 properties            5 lines
```

The language the LLM produces. A whole screen looks like this:

```
screen "sign-in" layoutMode=VERTICAL padding={space.xl} gap={space.lg}
  text "Welcome back" style=heading.xl
  text "Sign in to continue" style=body.md color={color.text.secondary}
  field #email type=email placeholder="Email address"
  field #password type=password placeholder="Password"
  button #submit "Sign in" variant=primary size=lg fullWidth
  link "Forgot password?"
```

~15 lines. No Figma Plugin API code. No pixels. No raw colours. Every
value is one of three things:

1. A token reference — `{space.xl}`, `{color.text.secondary}`
2. A canonical type — `button`, `field`, `text`, `link`
3. A constrained enum — `VERTICAL`, `primary`, `lg`, `email`

Today the grammar is enforced by structured-output tool calls and a
strict parser: if the LLM emits something the grammar doesn't permit,
it fails validation and the system retries. The proposed next step is
**grammar-native constrained decoding** (GBNF / XGrammar), so invalid
tokens are never produced in the first place. Same constraint, earlier
enforcement.

What "the grammar rejects anything else" actually looks like:

```
   ✗  fill="#FF0000"
      raw hex values aren't in the grammar.

   ✗  fill={color.accent.forest}
      token doesn't exist in this project.
      grammar suggests: {color.brand.600}, {color.semantic.success}

   ✗  button varient=primary
      misspelled enum.

   ✓  button variant=primary fill={color.brand.600}

  The constraint lives in the grammar — not in a prompt instruction,
  not in a post-hoc filter. If it parses, it's valid; nothing else
  parses.
```

The markup has five axes any node can carry, in any combination:

- **Structure** (type, children, parent)
- **Content** (text, icons, placeholder)
- **Spatial** (layout mode, padding, gap, alignment)
- **Visual** (fill, stroke, radius, effect)
- **System** (token bindings, canonical identity, provenance)

```
           one node — values on up to five axes, in any combination

                 Structure   Content   Spatial   Visual    System

                   type=     text=     pad=      fill=     canonical=
                   parent=   icon=     gap=      stroke=   variant=
                   children= label=    layout=   radius=   component_key=

           every node uses a subset:

                 text label       → Content + Visual
                 layout container → Structure + Spatial
                 component        → Structure + System
                 button           → all five
```

A node can use any subset. A text label has Content + Visual. A
container has Structure + Spatial. A live component instance has
Structure + System. Density is per-node, not per-level.

### 6.1 The edit grammar

A second, smaller grammar sits inside the same language: **seven verbs
for mutation.**

```
set     @header.title "New title"
delete  @submit
append  screen -> button "Cancel" variant=ghost
insert  before @submit -> text "Review your details" style=caption
move    @submit position=last
swap    @avatar with=-> icon_button variant=outline
replace @old-card with=-> card variant=elevated
```

Edits are first-class grammatical statements, not JSON diffs. The
verifier emits them (proposed). The LLM emits them (in the proposed
repair loop). The human edits with them. One grammar, many speakers.

---

## 7. The renderer — deterministic lowering to Figma

The renderer is the compiler's back end. Given an L3 markup document
and access to the database (for tokens, component keys, assets), it
emits a Figma Plugin API script: an imperative JavaScript program that,
when executed inside Figma, builds the design.

It walks the L3 AST in three phases:

```
Phase 1 — Materialize
    Create every node with its basic type (FRAME, TEXT, INSTANCE, …).
    No parenting. No layout. Just nodes.

Phase 2 — Wire the tree
    appendChild in parent order. The tree now has shape.

Phase 3 — Hydrate
    Apply positions, sizes, constraints, fills, strokes, effects.
    Token references resolve to live Figma Variables.
    Component instances resolve via the project's Component Key
    Registry and inherit their overrides.
```

The tree state after each phase, for a simple sign-in screen:

```
After Phase 1 — Materialize:
    n1  n2  n3  n4  n5      (5 flat nodes, no tree, no properties)

After Phase 2 — Wire tree:
    n1
    ├── n2
    │   ├── n3
    │   └── n4
    └── n5                  (tree shape, still no properties)

After Phase 3 — Hydrate:
    n1 FRAME layout=VERT fill={color.surface}
    ├── n2 FRAME padding={space.md}
    │   ├── n3 TEXT  "Sign in" style=heading.xl
    │   └── n4 FIELD placeholder="Email"
    └── n5 BUTTON variant=primary size=lg     (fully resolved)
```

The phase ordering matters. Figma's Plugin API has order-dependent
quirks: `resize()` behaves differently across layout modes;
`layoutSizing=FILL` evaluates against siblings that may not exist yet;
some text properties change the bounding box by ~60% depending on when
they're applied. The three-phase structure isolates those quirks.

A bridge plugin running inside Figma Desktop executes the script. The
output is indistinguishable from a hand-authored file.

Because the renderer is exhaustive and deterministic, **it's the only
thing in the stack that has to understand Figma's API.** The LLM never
sees Figma code. A future React renderer or SwiftUI renderer should be
a new walker over the same L3 AST — not a new IR. That claim is
structurally believable (the L3 primitives are backend-neutral by
design) but not yet validated; the second renderer is the next test of
it.

---

## 8. Verifying the pipeline is lossless

The round-trip test is simple: extract a file, compress to L3, render
back out, and compare. If the result isn't identical to the original —
same nodes, same properties, same positions — something is broken.

```
      ┌──────────────────┐
      │ original Figma   │
      │       file       │
      └────────┬─────────┘
               │ extract
               ▼
            L0 DB
               │ compress
               ▼
           L3 markup
               │ render
               ▼
          Plugin JS
               │ execute
               ▼
      ┌──────────────────┐
      │   re-rendered    │
      │   Figma file     │
      └────────┬─────────┘
               │
               │ compare to original
               │ (node-by-node,
               │  property-by-property)
               ▼
         is_parity = true ?
```

On a real production Figma file with several hundred screens, the
extract → markup → render pipeline is verified lossless. Every node.
Every property. Checked at node granularity by a structured verifier
that emits a typed error channel (not just pass/fail), with per-node
diagnostic codes like `KIND_MISSING_ASSET`, `KIND_COMPONENT_MISSING`,
`KIND_LEAF_TYPE_APPEND_SKIPPED`.

This is a claim about the **pipeline**, not about generation. It says:
the extractor captures everything, the compressor loses nothing, the
renderer reproduces faithfully. It does **not** say anything yet about
whether synthetic output (L3 written by an LLM from a prompt) is good.
That's the next thing to validate.

Why does the pipeline claim matter at all, then? Because you cannot
trust synthetic generation on top of a pipeline that loses data
round-tripping its own input. If extract → render isn't identity, then
when generation produces something unexpected you can't tell whether
the generation was wrong or the renderer was lying. Round-trip parity
is the bar below which nothing else in the system is trustworthy.
Above it, you can separate "the model generated something odd" from
"the pipeline corrupted something."

Today the verifier emits structured error codes. The proposed next
step: have the verifier emit **edit-grammar sentences** describing
what's wrong.

```
set   @logo.fills  []
move  @avatar      position=2
swap  @card-legacy with=-> card variant=elevated
```

Same grammar the LLM writes. Same grammar the human edits in. Same
repair surface. With that in place, the LLM can read the verifier's
output, apply edits to its L3, and re-emit — a closed loop.

---

## 9. Composition — how the LLM gets the right parts

The hardest part of generation is deciding, for each piece of a
request, where the building blocks come from. The proposed architecture
is three modes, confidence gated, operating as a cascade:

```
User: "login screen with email, password, social auth"
       │
       ▼
Score request against the corpus + catalog
       │
   ┌───┴────────────┬──────────────┐
   │                │              │
   ▼                ▼              ▼
 ≥ 0.9           0.6 – 0.9        < 0.6
   │                │              │
 EDIT            COMPOSE         SYNTHESIZE
   │                │              │
 Near-exact     Assemble from   Fabricate from
 donor screen   donor parts,    catalog defaults
 exists in      passed as       only. Risky
 corpus — edit  exemplars to    but non-empty.
 it live.       LLM, which
                emits fresh L3
                that references
                the parts.
```

Two things to notice:

**Raw subtree stitching is never done.** Even in COMPOSE mode, the LLM
re-emits the combined design as a new L3 document. Stitching produces
Frankenstein output (mismatched paddings, broken bindings, orphan
overrides). Re-emission through the grammar keeps it coherent.

**Mode 1 is the precedent.** When the LLM's L3 references a component
that exists in the project's library (by Component Key), the renderer
creates a real live INSTANCE, inherits its overrides, and walks on.
That pathway works today end-to-end — it's what proves the "LLM emits
L3, compiler does the rest" shape is viable.

**The three-mode cascade is proposed.** COMPOSE and SYNTHESIZE are
designed and partially scaffolded; the confidence-gated routing, the
exemplar retrieval, and the re-emission step are the next build phase.
The corpus that will feed composition is exactly what the classifier
has been producing — every correctly classified node is a potential
donor.

---

## 10. The generation loop (proposed)

```
Prompt
  │
  ▼
Mode selection (EDIT / COMPOSE / SYNTHESIZE)
  │
  ▼
Retrieve: exemplar L3 from corpus + catalog + project tokens
  │
  ▼
LLM emits L3 markup (structured output → grammar-native decoding)
  │
  ▼
Compiler lowers L3 → L2 → L1 → L0
  │
  ▼
Renderer emits Figma Plugin API script
  │
  ▼
Bridge executes script in Figma
  │
  ▼
Verifier walks the result, emits structured report
  │
  ├── pipeline lossless, output matches intent  ──► done
  │
  ▼
  drift detected — verifier emits edit-grammar sentences
  │
  ▼
LLM applies edits, re-emits, re-renders, re-verifies
  (max 2–3 loops)
```

The important property: **the LLM's surface is tiny.** One file type
(L3). One vocabulary (tokens + catalog). One grammar (markup + seven
edit verbs). Everything below L3 is deterministic. Everything the LLM
is permitted to produce is constrained by the grammar.

Today the loop runs end-to-end for Mode-1 inputs (L3 that references
real project components). The first real synthesis demo — the LLM
generating a novel subtree that gets composed against the live library
— is the next milestone. The verifier-as-agent repair loop, where
drift triggers automatic edit-grammar feedback, is the step after that.

---

## 11. Where we are

**Shipped and verified on a real production file:**

- Full extraction (REST + Plugin bridge)
- Multi-level IR (L0 / L1 / L2 / L3)
- Token clustering and curation (colour, spacing, typography, radius,
  effects) with push-back to Figma Variables
- Classifier cascade: five sources + Set-of-Marks + consensus rules,
  with human-review feedback
- 65-type canonical catalog, still growing
- Deterministic markup-native renderer (three-phase lowering)
- Lossless extract → markup → render round-trip at node granularity
- Seven-verb edit grammar, end-to-end
- Structured verification channel with typed per-node error codes

**Proposed, scoped, partially built:**

- **Slot definitions** — derive the internal structure of each
  canonical type (what a button's slots are, what a card's slots are).
  Unblocks the first real composition demo.
- **First synthesis demo** — component swap against the live library,
  end-to-end via the grammar.
- **Composition cascade** — EDIT / COMPOSE / SYNTHESIZE modes with
  confidence-gated routing and exemplar retrieval.
- **Verifier-as-agent repair loop** — verifier emits edit-grammar
  hints; LLM applies and re-emits.
- **Grammar-native constrained decoding** — enforce the markup at
  generation time, not in post-hoc validation.

**Not yet validated beyond the current corpus:**

- **Second project file.** The extractor is registry-driven and should
  generalise, but that claim has not yet been tested on a different
  design system.
- **Second renderer target.** React / HTML / CSS is the next backend
  and the first real test of the IR's cross-platform claim. SwiftUI
  and Flutter follow the same pattern.

The critical path: classifier → slot definitions → first synthesis
demo → second renderer target → second project file. Each gates the
next.

```
  shipped         next            next           next          next
  ───────         ────            ────           ────          ────

  classifier ─►  slot defs  ─►  first synth  ─►  2nd backend  ─►  2nd project
                                   demo          (React)         (generalise)
```

---

*Last updated 2026-04-21.*
