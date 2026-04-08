# Declarative Design

**The LLVM of design.** A compiler that translates UI between any source and any target through a multi-level intermediate representation — so you can speak interfaces into existence, sketch them on a napkin, or build them in Figma, and the system faithfully renders them anywhere.

```
          FRONTENDS                                    BACKENDS

  "A settings screen        ┌──────────────────┐       Figma file
   with a dark mode    ───> │                  │ ───>  (real components,
   toggle"                  │   Multi-Level    │       live tokens)
                            │                  │
  Figma file           ───> │   IR             │ ───>  React / JSX
                            │                  │
  React component      ───> │   L0  L1  L2  L3 │ ───>  SwiftUI
                            │                  │
  Sketch / photo       ───> │                  │ ───>  Flutter
                            └──────────────────┘
```

Designers work declaratively ("I want a card with these tokens") or imperatively (pixel-pushing in Figma). Developers describe UI in natural language, sketches, or code. The compiler understands all of it through the same IR — and can faithfully translate between any pair.

---

## Why This Exists

Every design-to-code tool today is a one-way street. Figma exports to React, but React can't update Figma. A design system lives in Figma AND code AND documentation, and they drift apart constantly.

The core insight: **this is a compiler problem.** LLVM solved it for programming languages — one IR, many frontends, many backends. We solve it for design.

| System | Design Tools | Code | Layout | Tokens | Bidirectional |
|--------|:-----------:|:----:|:------:|:------:|:-------------:|
| Figma Dev Mode | Yes | One-way | Partial | Partial | No |
| Mitosis (Builder.io) | No | Yes | No | No | No |
| Style Dictionary | No | Values only | No | Yes | No |
| W3C Design Tokens | No | Values only | No | Yes | No |
| **Declarative Design** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## How It Works

### The Compiler Model

```mermaid
graph LR
    subgraph Frontends
        F1["Figma Extraction"]
        F2["Natural Language"]
        F3["Sketch / Photo"]
        F4["React Parser"]
        F5["SwiftUI Parser"]
    end

    subgraph IR["Multi-Level IR (SQLite)"]
        L0["L0: Scene Graph<br/>86K nodes, 74 columns"]
        L1["L1: Classification<br/>48 component types"]
        L2["L2: Token Bindings<br/>182K bindings, 388 tokens"]
        L3["L3: Semantic Tree<br/>~20 elements per screen"]
        L0 --- L1 --- L2 --- L3
    end

    subgraph Backends
        B1["Figma Renderer"]
        B2["React / JSX + CSS"]
        B3["SwiftUI"]
        B4["Flutter"]
    end

    F1 --> L0
    F2 --> L3
    F3 --> L3
    F4 --> L1
    F5 --> L1

    L0 --> B1
    L1 --> B2
    L2 --> B3
    L3 --> B4

    style IR fill:#1a1a2e,color:#fff
```

Each frontend fills the IR levels it can. Each backend reads from the **highest level available** and falls back to lower levels for missing data. L0 is always the safety net — complete and lossless.

### The Four IR Levels

Inspired by [MLIR](https://mlir.llvm.org/) (Multi-Level IR, LLVM project). Core principle: **levels coexist, each adds information, none removes.**

| Level | What | Storage | Example |
|-------|------|---------|---------|
| **L0** | Complete scene graph | `nodes` table (74 cols) | Node 22068: FRAME, 428x80, fill=#09090B, cornerRadius=16 |
| **L1** | Semantic classification | `screen_component_instances` | Node 22068 is a `button` (confidence: 1.0) |
| **L2** | Design token bindings | `node_token_bindings` | Node 22068's fill is `{color.surface.primary}` |
| **L3** | Compact semantic tree | YAML | `button: { component: button/solid, text: Save }` |

An LLM producing a screen writes L3 (20 lines of YAML). The compiler fills in L2 (token bindings), L1 (component types), and L0 (all 74 visual properties). A Figma extraction fills all four levels at once. The result is the same IR — renderers don't care which frontend produced it.

### Progressive Fallback

Every renderer reads the highest IR level available and gracefully degrades:

```mermaid
graph TD
    L3["L3: Semantic Tree"] -->|"available?"| L2
    L2["L2: Token Bindings"] -->|"available?"| L1
    L1["L1: Classification"] -->|"available?"| L0
    L0["L0: Raw Properties"] -->|"always available"| R["Render"]

    style L3 fill:#2d6a4f,color:#fff
    style L2 fill:#40916c,color:#fff
    style L1 fill:#52b788,color:#fff
    style L0 fill:#74c69d,color:#000
```

A property with a token binding renders as a **live Figma variable** or **CSS custom property**. Without a binding, it renders as a hardcoded value from L0. Both are correct — one is more portable.

---

## Workflows

### 1. Speak UI Into Existence

Describe what you want in natural language. The LLM writes L3 (semantic YAML), the compiler fills in tokens and layout, and the renderer produces a real Figma file with live components and design tokens.

```mermaid
sequenceDiagram
    participant User
    participant LLM as Claude / LLM
    participant Compiler as Compiler
    participant Figma as Figma

    User->>LLM: "A settings screen with<br/>profile photo, dark mode toggle,<br/>and a logout button"
    LLM->>Compiler: L3 semantic YAML<br/>(~20 elements)
    Compiler->>Compiler: Resolve tokens (L2)<br/>Classify components (L1)<br/>Fill visual properties (L0)
    Compiler->>Figma: Plugin API script<br/>(real components, live tokens)
    Figma-->>User: Working design file
```

### 2. Extract and Translate

Pull a complete design system from Figma. Translate it to any target — another Figma file, React components, SwiftUI views, or CSS tokens.

```mermaid
sequenceDiagram
    participant Figma as Figma File
    participant CLI as dd extract
    participant DB as SQLite IR
    participant R1 as Figma Renderer
    participant R2 as React Renderer
    participant R3 as CSS Export

    Figma->>CLI: REST API + Plugin API
    CLI->>DB: 86K nodes, 74 cols each
    CLI->>DB: 182K token bindings
    CLI->>DB: 48 component types

    DB->>R1: Progressive fallback (L2 → L1 → L0)
    R1-->>Figma: Semantically equivalent file<br/>(real components, live tokens)

    DB->>R2: Progressive fallback
    R2-->>R2: JSX + CSS custom properties

    DB->>R3: Token export
    R3-->>R3: CSS / Tailwind / DTCG
```

### 3. Round-Trip Verification

The foundational proof that the compiler works: Figma -> DB -> Figma produces a visually identical, structurally equivalent design file. Not a flat screenshot — real components, live variables, correct hierarchy.

```
Original screen (Figma)          Reproduced screen (Figma)
┌─────────────────────┐          ┌─────────────────────┐
│  ┌───────────────┐  │          │  ┌───────────────┐  │
│  │    Header     │  │    ==    │  │    Header     │  │
│  └───────────────┘  │          │  └───────────────┘  │
│  ┌───────────────┐  │          │  ┌───────────────┐  │
│  │     Card      │  │          │  │     Card      │  │
│  │  ┌─────────┐  │  │          │  │  ┌─────────┐  │  │
│  │  │ Toggle  │  │  │          │  │  │ Toggle  │  │  │
│  │  └─────────┘  │  │          │  │  └─────────┘  │  │
│  └───────────────┘  │          │  └───────────────┘  │
│  ┌───────────────┐  │          │  ┌───────────────┐  │
│  │    Button     │  │          │  │    Button     │  │
│  └───────────────┘  │          │  └───────────────┘  │
└─────────────────────┘          └─────────────────────┘
  Components: real instances       Components: real instances
  Tokens: live variables           Tokens: live variables
  Hierarchy: preserved             Hierarchy: preserved
```

Proven on **11+ screens** (iPhone + iPad), 0.7-3.9s per screen.

---

## Quick Start

```bash
git clone https://github.com/mpacione/declarative.git
cd declarative

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify (1,816 tests)
pytest tests/ --tb=short
```

### Extract a Figma File

```bash
# Step 1: REST API extraction (no Figma Desktop needed)
python -m dd extract --file-key <your-figma-file-key> --page 0:1

# Step 2: Plugin API supplement (needs Figma Desktop + bridge plugin)
python -m dd extract-supplement --db your-file.declarative.db
```

### Use With Claude Code

```bash
claude  # Opens Claude Code in project directory
```

Then just talk:

| You say | What happens |
|---------|-------------|
| "Extract my Figma file" | `dd extract` via REST API -> SQLite |
| "Cluster the tokens" | OKLCH color grouping, type scale detection, spacing patterns |
| "Generate a settings screen" | LLM -> L3 YAML -> compile to all levels -> Figma |
| "Export to CSS" | `:root { --color-surface-primary: #fff; }` |
| "Push tokens to Figma" | Creates live Figma variables, binds to nodes |
| "Add a dark mode" | OKLCH lightness inversion, preserves hue/chroma |
| "Check for drift" | Compares DB tokens against live Figma variables |

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Extraction["Frontends (Extraction)"]
        REST["Figma REST API<br/>~90% of properties"]
        PLUGIN["Figma Plugin API<br/>componentKey, overrides"]
        PROMPT["LLM / Prompt<br/>natural language"]
        SKETCH["Sketch / Photo<br/>vision input"]
    end

    subgraph IR["Multi-Level IR (SQLite DB)"]
        direction TB
        NODES["L0: nodes table<br/>74 columns per node"]
        SCI["L1: screen_component_instances<br/>48 canonical types"]
        NTB["L2: node_token_bindings<br/>388 tokens, 182K bindings"]
        SEM["L3: Semantic tree<br/>YAML, ~20 elements/screen"]
    end

    subgraph Pipeline["Compiler Passes"]
        CLASSIFY["Classification<br/>formal + heuristic + LLM"]
        CLUSTER["Token Clustering<br/>OKLCH perceptual grouping"]
        CURATE["Curation<br/>rename, merge, split, alias"]
        VALIDATE["Validation Gate<br/>8 checks before export"]
    end

    subgraph Renderers["Backends (Renderers)"]
        FIGMA_R["Figma Renderer<br/>Plugin API JS"]
        REACT_R["React Renderer<br/>JSX + CSS vars"]
        SWIFT_R["SwiftUI Renderer"]
        CSS_R["CSS / Tailwind<br/>DTCG tokens"]
    end

    REST --> NODES
    PLUGIN --> NODES
    PROMPT --> SEM
    SKETCH --> SEM

    NODES --> CLASSIFY --> SCI
    NODES --> CLUSTER --> NTB

    NTB --> CURATE --> VALIDATE

    NODES --> FIGMA_R
    SCI --> FIGMA_R
    NTB --> FIGMA_R
    SEM --> REACT_R
    SCI --> REACT_R
    NTB --> SWIFT_R
    NTB --> CSS_R

    style IR fill:#1a1a2e,color:#fff
    style Pipeline fill:#16213e,color:#fff
```

### Three-Phase Rendering (Figma Backend)

The Figma Plugin API has implicit ordering constraints. The renderer uses three clean phases instead of scattering workarounds:

```mermaid
graph LR
    subgraph P1["Phase 1: Materialize"]
        C1["Create every node"]
        C2["Set intrinsic properties<br/>(fills, strokes, fonts, radius)"]
        C3["resize() for starting dimensions"]
    end

    subgraph P2["Phase 2: Compose"]
        A1["appendChild — wire tree"]
        A2["Set layoutSizing<br/>(parent context now known)"]
        A3["Auto-layout resolves"]
    end

    subgraph P3["Phase 3: Hydrate"]
        H1["resize/position on<br/>non-auto-layout children"]
        H2["loadFontAsync + characters<br/>(text reflows at correct widths)"]
    end

    P1 --> P2 --> P3

    style P1 fill:#264653,color:#fff
    style P2 fill:#2a9d8f,color:#fff
    style P3 fill:#e9c46a,color:#000
```

Each phase has a single responsibility. The boundaries eliminate an entire class of Figma Plugin API ordering bugs structurally. A React renderer wouldn't need Phase 3 at all — CSS reflows text automatically.

### Property Registry

A single source of truth (`dd/property_registry.py`) drives all pipeline stages:

```
FigmaProperty:
  figma_name ──> db_column ──> override_fields ──> value_type ──> emit pattern
       │              │              │                   │              │
       ▼              ▼              ▼                   ▼              ▼
   Plugin API     SQL SELECT    Override check     format_js_value   Template /
   extraction     columns       during decomp      type-aware        Handler /
                                                   formatting        Deferred
```

48 properties. Add one to the registry and it flows through extraction, query, overrides, and emission automatically. No parallel lists that drift apart.

---

## The IR in Detail

### L3 — What LLMs Write

```yaml
screen:
  size: [428, 926]
  layout: absolute

  header:
    component: nav/top-nav
    text: Settings

  card:
    layout: vertical
    padding: {space.lg}
    fill: {color.surface.white}

    heading: Notifications
    toggle: Push Notifications
    toggle: Dark Mode

  button:
    component: button/small/solid
    text: Save
```

20 lines. An LLM can produce this from a natural language description. The compiler resolves `{space.lg}` to `16px`, finds the `nav/top-nav` component in the registry, and fills in all 74 L0 properties needed to render it.

### L0 — What the DB Stores

74 columns per node. Complete, lossless. This is what makes round-trip possible — and what makes every downstream renderer trustworthy, because the Figma round-trip has already validated the data end-to-end.

---

## Current Status

- **Round-trip proven**: 11+ screens (iPhone + iPad), 0.7-3.9s each
- **Tests**: 1,816 passing
- **IR**: 86,761 nodes, 182,871 token bindings, 388 tokens, 338 screens
- **Properties**: 48 in registry, all emitted. 42 override types handled
- **Classification**: 93.6% coverage (47,292 / 50,517 nodes)

### What's Built

- Figma frontend (REST + Plugin API extraction)
- Figma backend (three-phase renderer with progressive fallback)
- Token pipeline (clustering, curation, validation, export)
- Natural language frontend (LLM -> L3 -> Figma)
- Export backends (CSS, Tailwind, DTCG, Figma variables)
- Round-trip verification on 11+ production screens

### What's Next

- React / SwiftUI / Flutter backends
- React / SwiftUI frontends (parser -> IR)
- Sketch / photo vision frontend
- L3 format formalization (YAML schema + constrained decoding)

---

## Design Principles

**Progressive fallback, not progressive enhancement.** Renderers start from the richest data available and degrade gracefully. A screen with full token bindings gets live variables. A screen with no tokens gets hardcoded values. Both render correctly.

**The IR stays pure.** Platform-specific concerns (Figma's three-phase ordering, CSS's `display:flex` requirement) live in the renderer, not the IR. The IR stores intent; renderers translate to platform constraints.

**Ground truth from source, not inference.** Extract actual values from the design tool. Don't infer sizing from parent context or guess font weights from style names. Heuristics compound.

**Single source of truth.** The property registry drives all pipeline stages. Add a property once, it flows everywhere. No parallel lists that drift apart.

**Fail open, not closed.** Unknown data is preserved, not stripped. Unexpected clipping is more destructive than missing clipping.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [compiler-architecture.md](docs/compiler-architecture.md) | Authoritative architecture spec |
| [continuation.md](docs/continuation.md) | Current state and session context |
| [module-reference.md](docs/module-reference.md) | Complete API reference |
| [cross-platform-value-formats.md](docs/cross-platform-value-formats.md) | Value formats per platform |
| [learnings.md](docs/learnings.md) | Active learnings and gotchas |
| [tier-progress.md](docs/tier-progress.md) | Token pipeline progress tracker |

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ --tb=short          # All 1,816 tests
pytest tests/test_ir.py           # IR generation
pytest tests/test_generate.py     # Figma renderer
pytest tests/test_visual.py       # Visual dict builder
```

## License

MIT
