# Declarative Design — short version

Source material for a short presentation. One idea per section. Skim
top-to-bottom in two minutes.

---

## What it is

A **compiler for design systems.**

Figma in. Figma out (today). React, SwiftUI, Flutter out (next).

In between: a typed language an LLM can write, that produces real
designs in a real design system.

```
    Figma file            prompt
        │                   │
        ▼                   ▼
    ┌───────────────────────────┐
    │    the compiler           │
    │    L0 / L1 / L2 / L3      │
    └───────────────────────────┘
        │                   │
        ▼                   ▼
    Figma (today)      React / SwiftUI
                        (proposed)
```

---

## The problem

AI design tools generate layouts.

They don't know your components.  
They don't bind to your tokens.  
They produce images or code — nothing your design system can reuse.

```
   The LLM can emit:

   ✗  Figma API code     → hallucinates methods
   ✗  pixels             → no design system
   ✗  free-form JSON     → raw values leak in

   ✓  a constrained markup?
      (tokens only, canonical types only, enums only)
```

---

## The bet

LLMs can't design.

LLMs **can** emit a short, highly constrained symbolic language.

If the compiler does everything below that language, generation
becomes tractable.

---

## The IR — four levels

```
L3   what the LLM writes     button "Sign in" variant=primary size=lg
L2   token bindings          fill = {color.brand.600}
L1   canonical identity      type = "button"
L0   scene graph             FRAME 160×48 fill #09090B …
```

Each level adds information; none replaces the one below.

Extraction climbs up. Generation comes down.

---

## The markup

What the LLM actually writes:

```
screen "sign-in" layoutMode=VERTICAL padding={space.xl}
  text  "Welcome back" style=heading.xl
  field #email    type=email
  field #password type=password
  button "Sign in" variant=primary size=lg
```

~15 lines.  
No Figma API code. No pixels. No raw colours.  
Every value is a token, a canonical type, or an enum.

---

## The compiler

L3 → L2 → L1 → L0 → Figma Plugin API script.

```
   L3 markup
       │
       ▼   Phase 1 — materialize nodes
       │
       ▼   Phase 2 — wire tree
       │
       ▼   Phase 3 — hydrate (tokens, components)
       │
       ▼
   Figma Plugin API script
```

A bridge plugin runs the script inside Figma.

The LLM never sees Figma code. That's the whole point.

---

## The verifier

```
   original  ──extract──►  L3 markup  ──render──►  re-rendered
      ▲                                                  │
      └─────────────  compare node-by-node  ─────────────┘
```

The extract → markup → render pipeline is **lossless** on a real
production Figma file. Every screen. Every node. Every property.

This is the floor, not the ceiling.  
It means the pipeline can be trusted.  
It says nothing yet about whether generation is good — that's next.

---

## Three modes of composition *(proposed)*

```
EDIT         near-exact match   → edit the donor
COMPOSE      partial match      → assemble, re-emit
SYNTHESIZE   no match           → catalog defaults
```

**Mode 1** (LLM references real components from the project's library)
works today — it's what proves the shape.

Modes 2 and 3 are the next milestone.

---

## The edit grammar

Seven verbs. One vocabulary.

```
set / delete / append / insert / move / swap / replace
```

```
                edit grammar
                (seven verbs)
                     │
        ┌────────────┼────────────┐
        │            │            │
       LLM        human        verifier
      writes     edits         emits drift
      L3         directly      (same sentences)
```

One grammar, many speakers.

---

## The loop *(proposed)*

```
prompt → L3 → render → verify → repair
                                    │
                                    ▼
                             edit-grammar sentences
                             LLM re-emits → re-render
```

The LLM's surface is tiny: one file, one vocabulary, one grammar.  
Everything below is deterministic.

---

## What's shipped

- Extraction (REST + Plugin)
- IR (L0 – L3)
- Token clustering + push-back as Figma Variables
- Classification: 5 sources + Set-of-Marks + consensus
- 65-type canonical catalog
- Deterministic renderer
- 7-verb edit grammar
- Lossless round-trip on a real production file

## What's proposed

- Slot definitions → unblocks composition
- First synthesis demo (component swap against live library)
- Composition cascade (Modes 2 & 3)
- Verifier-as-agent repair loop
- Grammar-native constrained decoding
- Second Figma file (generalisation)
- React / HTML renderer (cross-platform validation)
- SwiftUI + Flutter to follow

---

## The ladder

```
classifier  →  slot defs  →  first synth demo  →  second renderer  →  second project
```

Each gates the next.

---

## What this is not

Not a Figma plugin.  
Not another "AI generates your design" tool.  
Not a design-to-code tool (though that falls out once multiple
renderers exist).

It's the compiler. **Designs are the output. Code is the byproduct.**
