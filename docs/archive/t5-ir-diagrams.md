# T5 IR Architecture — Diagrams

Mermaid diagrams expressing the IR architecture, data flow, and internal structure.

---

## 1. Hub-and-Spoke: The IR as Universal Translation Hub

```mermaid
graph LR
    subgraph Inputs["PARSERS (Any Input → IR)"]
        P1["Text Prompt"]
        P2["Figma File"]
        P3["Screenshot"]
        P4["React Codebase"]
        P5["SwiftUI Code"]
        P6["URL / Live Site"]
        P7["Design Spec"]
    end

    subgraph IR["INTERMEDIATE REPRESENTATION"]
        direction TB
        CAT["Component Catalog\n~45-50 canonical types"]
        COMP["Composition Spec\nflat element map\n+ layout + tokens"]
        TOK["Token Vocabulary\nper-project values"]
    end

    subgraph Outputs["GENERATORS (IR → Any Output)"]
        G1["Figma\n+ variable bindings"]
        G2["React + shadcn"]
        G3["React + MUI"]
        G4["SwiftUI"]
        G5["Flutter"]
        G6["HTML + Tailwind"]
        G7["Design Spec"]
        G8["Design Tokens\nCSS / DTCG"]
    end

    P1 --> IR
    P2 --> IR
    P3 --> IR
    P4 --> IR
    P5 --> IR
    P6 --> IR
    P7 --> IR

    IR --> G1
    IR --> G2
    IR --> G3
    IR --> G4
    IR --> G5
    IR --> G6
    IR --> G7
    IR --> G8
```

---

## 2. The Three Layers of the IR

```mermaid
graph TB
    subgraph L1["Layer 1: CATALOG (Universal, Shared, Versioned)"]
        direction LR
        CT["Component Types\n~45-50 canonical"]
        LP["Layout Primitives\nstack, row, grid\noverlay, scroll, wrap"]
        SR["Semantic Roles\nheading, button\ninput, link, image"]
        PS["Prop/Slot Specs\ntyped definitions\nper component"]
    end

    subgraph L2["Layer 2: COMPOSITION (Per-Screen, Abstract, The Hub)"]
        direction LR
        EM["Element Map\nflat, ID-referenced\nnot nested"]
        LY["Layout Data\nflexbox model\ndirection, gap, sizing"]
        ST["Style References\ntoken refs, not\nhardcoded values"]
        BH["Behavior\nevents, actions\nconditions"]
    end

    subgraph L3["Layer 3: RENDERERS (Per-Platform, Mechanical)"]
        direction LR
        RF["Figma Renderer\nMCP calls\nvariable bindings"]
        RR["React Renderer\nJSX + imports\nshadcn/MUI/Radix"]
        RS["SwiftUI Renderer\nView structs\nmodifiers"]
        RH["HTML Renderer\nsemantic HTML\nTailwind/CSS"]
    end

    L1 -->|"defines vocabulary for"| L2
    L2 -->|"consumed by"| L3
```

---

## 3. Internal Structure of a CompositionSpec

```mermaid
graph TB
    CS["CompositionSpec"]
    CS --> ROOT["root: 'screen-1'"]
    CS --> VER["version: '1.0'"]
    CS --> CATREF["catalog: dd-catalog@1.0"]
    CS --> TOKENS["tokens: { resolved values }"]
    CS --> ELEMENTS["elements: Record&lt;id, Element&gt;"]

    ELEMENTS --> E1["screen-1"]
    ELEMENTS --> E2["header-1"]
    ELEMENTS --> E3["section-1"]
    ELEMENTS --> E4["toggle-1"]
    ELEMENTS --> E5["button-1"]

    E1 --> E1T["type: Screen"]
    E1 --> E1C["children: [header-1, section-1]"]
    E1 --> E1L["layout: { direction: vertical }"]
    E1 --> E1S["style: { bg: '{color.surface}' }"]

    E4 --> E4T["type: ToggleRow"]
    E4 --> E4P["props: { label, subtitle, default }"]
    E4 --> E4S["style: { font: '{type.body.md}' }"]
```

---

## 4. Element Internal Structure (Separated Concerns)

```mermaid
graph LR
    subgraph Element["Element (one node in the flat map)"]
        direction TB
        ID["id: string"]
        TYPE["type: string\n(from catalog)"]

        subgraph Structure["STRUCTURE"]
            CHILDREN["children: string[]\n(element IDs)"]
            SLOTS["slots: Record\n(named → element IDs)"]
        end

        subgraph Layout["LAYOUT"]
            DIR["direction"]
            GAP["gap"]
            PAD["padding"]
            ALIGN["alignment"]
            SIZE["sizing"]
        end

        subgraph Style["STYLE (token refs)"]
            BG["backgroundColor"]
            FONT["font"]
            COLOR["color"]
            RADIUS["borderRadius"]
        end

        subgraph Behavior["BEHAVIOR"]
            ON["on: { tap, hover }"]
            VIS["visible: condition"]
        end

        PLAT["$platform: { css, figma, swiftui }"]
    end
```

---

## 5. The Pattern Language Operating on the IR

```mermaid
graph TB
    BRIEF["Level 0: Screen Brief\n'Settings page for iOS app'"]

    BRIEF --> SK1["Skeleton A\ngrouped-sections"]
    BRIEF --> SK2["Skeleton B\nflat-list"]
    BRIEF --> SK3["Skeleton C\ntabbed"]

    SK1 --> EL1["Elaboration 1\ntoggle-rows"]
    SK1 --> EL2["Elaboration 2\nradio-groups"]
    SK1 --> EL3["Elaboration 3\ncard-based"]

    EL1 --> RESOLVE["Level 3: Token Resolution\n(deterministic DB lookup)"]

    RESOLVE --> IR["COMPOSITION SPEC\n(the IR instance)"]

    IR --> CRITIQUE["Level 4: Critique Cascade"]

    CRITIQUE --> PASS["Pass → Render to Figma"]
    CRITIQUE --> FAIL["Fail → Re-enter at\naffected level"]

    FAIL --> SK1

    style IR fill:#f9f,stroke:#333,stroke-width:3px
```

---

## 6. Parsing and Generation Flow (Bidirectional)

```mermaid
graph LR
    subgraph Parse["PARSING (Input → IR)"]
        direction TB
        FP["Figma Parser\nnode tree → elements\ntoken bindings → style\nauto-layout → layout"]
        RP["React Parser\nJSX AST → elements\ncomponent → type\nprops → props"]
        PP["Prompt Parser\nPattern Language\ndescent → elements"]
        SP["Screenshot Parser\nvision → classify\ninfer → elements"]
    end

    subgraph TheIR["THE IR"]
        COMP2["CompositionSpec\n(flat element map)"]
    end

    subgraph Generate["GENERATION (IR → Output)"]
        direction TB
        FG["Figma Generator\nelements → MCP calls\nstyle → variable bindings\nlayout → auto-layout"]
        RG["React Generator\nelements → JSX\ntype → component import\nstyle → className/CSS"]
        SG["SwiftUI Generator\nelements → View\ntype → native view\nlayout → HStack/VStack"]
        TG["Token Generator\ntokens → CSS vars\ntokens → Tailwind config\ntokens → DTCG JSON"]
    end

    FP --> COMP2
    RP --> COMP2
    PP --> COMP2
    SP --> COMP2

    COMP2 --> FG
    COMP2 --> RG
    COMP2 --> SG
    COMP2 --> TG
```

---

## 7. The Critique Cascade on IR Data

```mermaid
graph TB
    IR["CompositionSpec\n(the IR instance)"]

    IR --> L1["L1: System Critique\n(deterministic, FREE)"]
    IR --> L4["L4: Accessibility Critique\n(deterministic, FREE)"]

    L1 --> L1R{{"All tokens bound?\nNo hardcoded values?\nSlots filled?"}}
    L4 --> L4R{{"WCAG contrast?\nTouch targets?\nSemantic roles?"}}

    L1R -->|"Pass"| L2
    L4R -->|"Pass"| L2
    L1R -->|"Fail"| FIX1["Fix: re-enter L3"]
    L4R -->|"Fail"| FIX4["Fix: adjust tokens"]

    L2["L2: Structural Critique\n(Haiku, CHEAP)"]
    L2 --> L2R{{"Layout logic?\nHierarchy?\nGrouping?"}}

    L2R -->|"Pass"| L3
    L2R -->|"Fail"| FIX2["Fix: re-enter L1 or L2"]

    L3["L3: Visual Critique\n(Sonnet + screenshot, EXPENSIVE)"]
    L3 --> L3R{{"Visual balance?\nSpacing feel?\nHierarchy readable?"}}

    L3R -->|"Pass"| ACCEPT["Accept → Render"]
    L3R -->|"Fail"| FIX3["Fix: targeted adjustment"]

    style L1 fill:#90EE90
    style L4 fill:#90EE90
    style L2 fill:#FFD700
    style L3 fill:#FF6347
```

---

## 8. The Full System: IR at Center of Everything

```mermaid
graph TB
    subgraph Inputs["INPUTS"]
        PROMPT["Prompt"]
        FIGMA_IN["Figma File"]
        CODE_IN["Code Repo"]
        SCREEN["Screenshot"]
    end

    subgraph Core["CORE SYSTEM"]
        direction TB

        subgraph PL["Pattern Language"]
            L0["L0: Intent"]
            L1PL["L1: Skeleton"]
            L2PL["L2: Elaboration"]
        end

        IR2["IR\nCompositionSpec"]

        subgraph Eval["Evaluation"]
            TASTE["Taste Model\n(distributions)"]
            CRIT["Critique Cascade\n(L1-L4)"]
        end

        subgraph Data["Data Layer"]
            CAT2["Component Catalog\n(~45-50 types)"]
            TOKVOC["Token Vocabulary\n(per-project)"]
            DT["Decision Tree\n(exploration history)"]
        end
    end

    subgraph Outputs["OUTPUTS"]
        FIGMA_OUT["Figma\n+ bindings"]
        REACT["React"]
        SWIFT["SwiftUI"]
        HTML["HTML"]
        SPEC["Spec Doc"]
    end

    Inputs --> PL
    PL --> IR2
    TASTE -.->|"informs"| PL
    CAT2 -.->|"constrains"| IR2
    TOKVOC -.->|"provides values"| IR2
    IR2 --> CRIT
    CRIT -->|"pass"| Outputs
    CRIT -->|"fail"| PL
    IR2 -.->|"recorded in"| DT

    style IR2 fill:#f9f,stroke:#333,stroke-width:4px
```
