# dd markup — Grammar Specification

**Status:** ⚠ PLACEHOLDER. To be authored during Plan A.5, concurrent with Plan A.4 (hand-authored fixtures). See `docs/plan-v0.3.md`.
**Target format:** formal BNF/EBNF suitable for parser implementation AND for constrained-decoding grammar files (XGrammar / Outlines / llguidance).
**Authored:** 2026-04-18 (scaffold only).

This is the canonical grammar specification for dd markup — the L3 authoring surface of the multi-level IR. It will be the single source of truth that both the parser implementation (`dd/markup.py`) and the LLM grammar mask consume.

When this doc is complete, it fully specifies:
- What a valid `.dd` document looks like at the byte level
- What every sigil, prefix, and keyword means
- How the LLM grammar mask constrains emission
- How the parser disambiguates every syntactic form

---

## Relationship to `docs/requirements.md` and `docs/requirements-v0.3.md`

This spec is the concrete realization of the design principles stated in Tier 0 §4:

- Axis-polymorphic specification (§4.1) → the grammar accepts any subset of axes on any node
- One grammar, many speakers (§4.2) → construction and edits parse identically
- Definitions as first-class (§4.3) → `define` + `&` are first-class productions
- Provenance (§4.4) → annotations and value trailers are grammar-level, not sugar
- Multi-granularity editing (§4.5) → seven verbs + property-set sugar, same parser

If this doc conflicts with Tier 0 §4, Tier 0 wins — update this spec to match.

---

## Table of contents (to be filled in during Plan A.5)

### 1. Introduction and scope
- What this grammar expresses (L3, the semantic tree level)
- What it does NOT express (L0/L1/L2 are DB-resident)
- Relationship to KDL v2 substrate
- Grammar audience (LLM + technical human)

### 2. Lexical grammar
- Character set (UTF-8)
- Whitespace and line terminators
- Comments (`//` single-line, `/* */` block)
- Identifiers (start char, continuation chars, reserved words)
- String literals (escape sequences, multiline)
- Numeric literals (integers, floats, scientific notation, signed)
- Keywords (`define`, `use`, `namespace`, `as`, `slot`, the seven edit verbs, `true`, `false`, `null`)
- Sigils and their roles (`#`, `@`, `->`, `&`, `{`, `}`, `::` or alternative)

### 3. Syntactic grammar (BNF/EBNF)
- Document structure (`namespace` + `use` + top-level nodes)
- Node declarations
- Property assignments
- Children blocks
- Slot declarations and fills
- Edit verbs

### 4. Value grammar
- Value forms, one slot:
  - Raw literal — `#hex`, number, `"string"`, `true`/`false`/`null`, path
  - Token reference — `{color.brand.primary}` (DTCG brace-syntax)
  - Component reference — `-> button/primary/lg` (external instance)
  - Pattern reference — `& pattern.product-card` (local definition)
- Value-form disambiguation rules (parser) and constraint rules (constrained decoding)
- Special value forms for layout (fill / hug / fixed + min/max bounds)

### 5. Node identity
- `#eid` declares a new node's id (must be unique within scope)
- `@eid` references an existing node
- Auto-generated ids (`scope@N` by sibling count when no explicit `#` or `as` alias)
- Explicit aliases at call site (`pattern.product-card as featured`)
- Hierarchical paths for addressing (slash-separated: `grid/featured/buy-button`)
- Wildcards for bulk edits (`*` same-level, `**` any-descendant)

### 6. Definitions and references
- `namespace <name>` (required at top of file)
- `use "path/to/lib" as <alias>` (mandatory alias)
- `define <name>(<params>) { <body> }` — with three parametrization primitives:
  - Typed scalar args: `title: text = "default"`
  - Named slots with defaults: `slot action = button/primary(...)`
  - Path-addressed property overrides at call site: `& pattern card.fill=black`
- Reference expansion semantics
- Cycle detection (three-color DFS, hard-error at parse time)
- Scope resolution and shadowing rules
- Dot-paths for namespace (`pattern.product-card`) vs slash-paths for addressing (`grid/featured/buy`) — do not collide

### 7. Axis population
- What each axis contains at the grammar level:
  - **Structure** — type, children, slot declarations
  - **Content** — text, labels, props
  - **Spatial** — sizing (fill/hug/fixed), position, padding, gap, arrangement
  - **Visual** — fills, strokes, effects, typography (per-node)
  - **System** — top-level tokens block, palette, type scale, spacing scale
- All axes optional on any node (Tier 0 §4.1)
- How the parser validates partial specifications

### 8. Edit grammar (same grammar, addressed at existing nodes)
- Seven closed-set verbs: `set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`
- `set` implicit on property assignment: `@card-1 radius={radius.lg}`
- Keyword args (`to=`, `from=`, `into=`, `after=`, `before=`, `position=`)
- Stable eid addressing, never positional
- Construction inside an edit block: `append to=@card-1 { button label="New" }`

### 9. Provenance annotations
- Provenance kinds (the six from Tier 0 §4.4): extracted / retrieved / substituted / synthesized / user-edited / catalog-default
- Node-level trailer: `card (retrieved src="donor:142" conf=0.91)` — inherits to descendants
- Value-level trailer: `fill=#F8F8F8 #[user-edited]` — only when richer than value syntax self-describes
- Queryable semantics (how the DB / verifier / UI filter by provenance)

### 10. Grammar-constrained decoding notes
- How this grammar maps to XGrammar / Outlines / llguidance formats
- Token vocabulary exposure (what goes into the system prompt vs what's enforced by the mask)
- Per-backend capability grammar derived from ADR-001 table
- Handling of unknown / extension properties (fail-open vs fail-closed)

### 11. Reserved for future
- Provenance metadata beyond the six kinds (if ever needed)
- Multi-target catalog extension syntax (Stage 6)

### 12. Canonical example documents
- (From `tests/fixtures/markup/` — referenced here once authored)

---

## Open questions (to be resolved before this spec is complete)

Listed in priority order. Each must have a decision recorded in this spec by the end of Plan A.5.

### Q1. Token-ref syntax — confirm `{path}` vs alternatives

`{color.brand.primary}` is the DTCG standard and appears in the largest volume of LLM training data (Style Dictionary docs, CSS-var patterns). Alternative `::path` (Rust-like) or `$path` (YAML-like) considered and rejected in prior session chats.

**Proposed:** `{color.brand.primary}` as first-class value form.
**Needs:** explicit BNF production; confirmation that LLM constrained-decoding libraries handle brace-tokens cleanly.

### Q2. Provenance trailer syntax — `#[kind args]` or alternative

LLM emission reliability is the deciding factor. Trailer should:
- Only appear when richer than value syntax self-describes (Scenario A has zero trailers)
- Be easy to skip in the parser (so absent-trailer is the fast path)
- Be unambiguous next to value forms

**Candidate:** `#[kind args]` value trailer; `(kind args)` node-level trailer on the node's head line.

### Q3. Slot syntax

Three primitives (scalar args / named slots / path overrides) don't unify. Exact syntax for each:

**Candidate:**
- Scalar arg: `title: text = "Product"` (typed with default)
- Named slot: `slot action = button/primary(label="Go")` (default is a call)
- Path override at call site: `& pattern.product-card card.fill={color.surface.muted}`

**Needs:** explicit grammar production for each; resolution order for collisions between scalar arg and path override with same name.

### Q4. Hierarchical ID semantics

When is `#eid` optional vs required? What does the parser generate for auto-ids?

**Candidate:**
- `#eid` optional except when a node needs to be addressable by edits / other references
- Auto-id is `{type}@{sibling-count}` when no `#eid` and no `as` alias
- `as name` at call site is the friendly-alias escape hatch

**Needs:** precise rule for when ids collide (error, warning, or auto-rename).

### Q5. Wildcards and path semantics

`@grid/*/buy-button label="Click"` applies the edit to every `buy-button` child of any direct child of `grid`. What about `@**/button`? Recursion depth?

**Candidate:** `*` one level, `**` any depth (including zero). Parser checks against symbol table at edit-apply time.

### Q6. Whitespace and block boundaries

KDL allows both `{ ... }` blocks and bare statements. Our grammar must decide: mandatory block braces on definitions? Optional where unambiguous?

**Candidate:** mandatory braces on `define` and edit block forms; inline-property single-statement nodes don't need braces.

### Q7. Comments

`//` line and `/* */` block per KDL v2. KDL also has `/-` slash-dash for "delete this node" — do we adopt for edits, or use explicit `delete @eid`?

**Candidate:** use explicit `delete @eid` for edits. Reserve `/-` for author-commented-out blocks (not semantically meaningful).

### Q8. Number formats

Integers, floats, scientific notation, signed. What's the canonical emission form (matters for round-trip byte-equality across serde)?

**Candidate:** emit the most-compact lossless form. Parser accepts all forms. Round-trip is at IR-equality, not byte-equality.

### Q9. String escapes

`\n \t \r \" \\ \0` plus unicode escapes. How to handle newlines inside strings (forbidden vs multiline quotes)?

**Candidate:** standard escape set; newlines inside single-line strings are forbidden (hard-error at parse); multiline strings use triple-quote or similar.

### Q10. Extension mechanism

DTCG's `$extensions` pattern — tool-specific metadata that spec-compliant parsers preserve through round-trip. Do we want this?

**Candidate:** support as a `$ext` property-key namespace. Unknown `$ext.*` properties preserved literally through serde; validator ignores; tools can embed private metadata.

---

## Plan A.5 deliverables

When this doc is complete, the following must be true:

1. All 10 open questions above have decisions recorded in the spec.
2. Every `.dd` fixture file in `tests/fixtures/markup/` parses successfully against this grammar.
3. At least three invalid variations on each fixture are listed as expected-rejected inputs (for the parser-implementation test suite).
4. A smoke test using constrained decoding (Haiku + XGrammar or llguidance) produces valid `.dd` output for a small prompt (e.g., "a 3-card grid"). This is a coarse existence proof that the grammar is decodable, not a full validation.
5. The spec has a one-page "cheat sheet" summary section suitable for prompting an LLM.

---

## Implementation hook

Once this spec is stable, `dd/markup.py` gets rebuilt against it. The existing `dd/markup.py` (~786 LOC on `v0.3-integration`) is a mechanical dict-IR serializer and is NOT the parser for this grammar. Some infrastructure (tokenizer primitives, error classes, test harness) is reusable; the value-form parsing, definition expansion, and edit-verb handling must all be rebuilt to match this spec.

---

*Plan A.5 authors this doc. Plan B Stage 1 implements against it. No code is written against dd markup before this doc is stable.*
