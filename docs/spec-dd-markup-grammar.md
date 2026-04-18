# dd markup — Grammar Specification

**Status:** Canonical (Plan A.5 output). Every construct parses against the
fixtures in `tests/fixtures/markup/`. Every open question is closed by
a decision recorded below.
**Target format:** formal EBNF suitable for a recursive-descent parser
AND for constrained-decoding grammar files (XGrammar / Outlines / llguidance).
**Authored:** 2026-04-18.

This is the canonical grammar specification for dd markup — the L3
authoring surface of the multi-level IR. It is the single source of
truth that both the parser implementation (`dd/markup.py`, to be rebuilt
against this spec per Plan B Stage 1.2) and the LLM grammar mask
consume.

---

## Relationship to `docs/requirements.md` and `docs/requirements-v0.3.md`

This spec is the concrete realization of the design principles stated in
Tier 0 §4 (axis-polymorphic specification, one grammar many speakers,
definitions as first-class, provenance, multi-granularity editing).

If this doc conflicts with Tier 0 §4, Tier 0 wins — update this spec to
match. If a fixture under `tests/fixtures/markup/` disagrees with this
spec, the **fixture is normative** (Plan A.5 "fixtures are normative"
principle) and this spec is wrong — update the spec.

---

## 1. Introduction and scope

### 1.1 What this grammar expresses

dd markup expresses the **L3 semantic tree** of the multi-level IR: a
compact, referential tree of elements where every styling / spacing /
typography value is a reference (to a token, a pattern, a component, or
a universal-catalog default) and the structural axis may be populated
at any density.

One grammar, many speakers — the same grammar expresses:
- Extractor output (what `compress(L0+L1+L2)` produces; see
  `docs/spec-l0-l3-relationship.md`)
- User authoring (what a designer/engineer types)
- LLM synthesis output (what the generator model emits)
- Edits (construction + addressing existing `@eid`; same grammar)
- Verifier feedback (critic emits edit-grammar patches)

Any distinction between these speakers lives in semantics (validation
mode), not syntax.

### 1.2 What this grammar does NOT express

- **L0 scene graph** — the DB `nodes` table with every Figma property. L0
  is the ground-truth source for extraction and round-trip verification;
  dd markup is derived FROM L0 (see `docs/spec-l0-l3-relationship.md`).
- **L1 classification annotations** as first-class — canonical types
  appear as **type keywords** in dd markup (`button`, `card`, etc.),
  but the per-node classification confidence and classification-source
  (formal/heuristic/LLM/vision) don't surface. They're available via the
  L2 provenance channel if needed.
- **L2 token bindings as a raw table** — dd markup references tokens by
  path (`{color.action.primary.bg}`); the binding table is an
  extraction-side artifact, not a user-facing construct.

### 1.3 Relationship to KDL v2 substrate

dd markup borrows from **KDL v2** (Kaylee's Document Language) at the
lexical layer:
- `{ }` block bounding
- Line-terminated statements (newline is significant)
- Identifier chars include dashes
- Triple-quoted multiline strings

At the syntactic layer, dd markup **diverges from KDL**:
- Type names come first (KDL calls them "names") — dd names them as
  keywords from a fixed list
- dd introduces four non-KDL sigils: `{name}` for refs, `->` for
  component refs, `&` for pattern refs, `#eid` for identity
- dd has formal `define` blocks with typed parameters + slots; KDL has
  no analog

The dialect is intentionally restrictive compared to bare KDL: the
grammar is designed to be LLM-constrained-decodable, not to be a
general-purpose document language.

### 1.4 Audience

**LLM emission + technical-reader human-readable** (engineer,
design-systems lead). NOT designer-facing in v0.3. Grammar-complexity
tradeoffs favor constrained-decoding reliability and precise parse
semantics over visual accessibility for non-technical users.

---

## 2. Lexical grammar

### 2.1 Character set

UTF-8. Source files MUST be valid UTF-8 byte sequences. Implementations
MAY reject BOMs (the parser does not skip them; they are invalid input).

### 2.2 Whitespace and line terminators

- `' '` (space), `'\t'` (tab), and line terminators are whitespace
- Line terminators: `'\n'` (LF) and `'\r\n'` (CRLF). Bare `'\r'` is a
  lexical error
- **Newline is mostly non-significant inside a node head**: a NodeHead
  may span multiple lines so long as each continuation line is
  positioned where a new property / path-override / node-trailer is
  expected. The head ends when one of the following appears:
  - `{` — opens a Block
  - `}` — closes an enclosing Block
  - A blank line (one or more EOL with nothing else between them)
  - A new line starting with a **statement-starter token**:
    - Any TypeKeyword (§2.7)
    - `->` (CompRef)
    - `&` (PatternRef)
    - `@` (edit ref)
    - `define` / `namespace` / `use` / `tokens`
    - An edit verb (`set`, `append`, `insert`, `delete`, `move`, `swap`,
      `replace`)
    - `$ext.` (extension metadata)
  - **Exception for TypeKeyword followed by `=` or `.`:** a
    TypeKeyword in continuation position that is IMMEDIATELY followed
    by `=` or `.` is treated as a **property-path continuation**, not a
    new statement. This lets fixtures write `container.gap=8` as a
    path-override on a `& option-row` call (where `container` is both
    a TypeKeyword and a legal internal-eid path prefix). The parser
    disambiguates via a single-token look-ahead after the TypeKeyword.
- Whitespace between tokens on the same line is ignored except where it
  separates adjacent identifiers that would otherwise fuse
- **Between top-level statements and inside a Block**, a blank line is
  a statement separator and is advisory only (does not change parse
  semantics beyond terminating a multi-line NodeHead)

### 2.3 Comments

- `// ...` line comment, runs to the next line terminator
- `/* ... */` block comment, does not nest
- Both are whitespace-equivalent to the parser (produce no tokens)

### 2.4 Identifiers

```
IDENT ::= (letter | '_') (letter | digit | '_' | '-')*
```

- `letter` matches ASCII `[A-Za-z]`
- Dashes `-` are valid continuation characters (matches KDL; matches
  Figma component-name convention like `nav/top-nav` on the per-segment
  basis)
- Identifiers are case-sensitive
- Reserved words (listed in §2.7) MUST NOT be used as bare identifiers
  where they would parse ambiguously; they MAY be used as property keys
  or within string literals

### 2.5 String literals

```
StringLit     ::= SingleLine | MultiLine
SingleLine    ::= '"' (Char | EscapeSeq)* '"'
MultiLine     ::= '"""' LineBreak (Char | EscapeSeq | LineBreak)*? LineBreak '"""'
EscapeSeq     ::= '\\' ( '"' | '\\' | 'n' | 't' | 'r' | '0' | 'u' '{' HexDigit+ '}' )
```

- Single-line strings: no raw line terminators (hard-error); use
  escape `\n` or switch to multiline
- Multi-line strings: leading indentation is stripped (the indentation
  level of the closing `"""` determines the common prefix to strip,
  Python-style)
- Unicode escapes: `\u{NNNN}` where `NNNN` is 1–6 hex digits
- No single-quoted strings; no backticks

### 2.6 Numeric literals

```
NumberLit     ::= SignedInt | SignedFloat
SignedInt     ::= '-'? DecDigit+
SignedFloat   ::= '-'? DecDigit+ '.' DecDigit+ Exponent?
                | '-'? DecDigit+ Exponent
Exponent      ::= ('e' | 'E') ('+' | '-')? DecDigit+
```

- All numbers represent dimensional pixels unless the property's schema
  dictates otherwise (e.g., `opacity` is unitless 0..1; `rotation` is
  radians for round-trip, renderer converts)
- Percentages and alternative units (`rem`, `em`, `%`) are NOT part of
  v0.3 — reserved for post-v0.3
- Hex color literals are NOT numbers; see §2.8

### 2.7 Keywords (reserved)

Three reserved-word categories. Each is context-free (no multi-context
disambiguation needed):

**Document-structure keywords:**
`namespace`, `use`, `as`, `tokens`, `define`, `slot`

**Node type keywords** (canonical types from the catalog):
`screen`, `frame`, `text`, `rectangle`, `vector`, `group`, `ellipse`,
`button`, `card`, `header`, `container`, `icon`, `image`, `slider`,
`heading`, `tabs`, `overlay`, `list`, `input`, `toggle`, `checkbox`,
`radio`, `avatar`, `badge`, `dialog`, `drawer`, `menu`, `popover`,
`tooltip`, `chart`, `divider`, `boolean-operation`, `line`, `star`,
`polygon`, `nav`

The type keyword list extends over time as the canonical-type catalog
grows; the parser MUST accept any identifier matching
`TypeKeyword` from a registry loaded at parse initialization. Parsers
SHOULD warn on unknown type keywords but MUST NOT hard-fail (fail-open
per `feedback_fail_open_not_closed.md`).

**Edit-verb keywords:**
`set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`

**Value keywords:**
`true`, `false`, `null`, `hug`, `fill`, `fixed`

### 2.8 Sigils

| Sigil | Role | Precedence |
|-------|------|-----------|
| `#`   | eid prefix (`#form-card`) | Attaches to immediately-following IDENT |
| `@`   | eid reference (`@form-card`, `@card-1.title`) | Used only in edit context |
| `->`  | Component reference (`-> nav/top-nav`) | Node-starter alternative to type keyword |
| `&`   | Pattern reference (`& option-row`) | Node-starter alternative to type keyword |
| `{`   | Open block OR open value-ref OR open property-group | Disambiguated by context (§3.4) |
| `}`   | Close of a `{`-opened region | — |
| `::`  | Scope resolution (`sheet22::card-section`) | Inside CompPath / PatternPath |
| `=`   | Property / slot assignment | Always binary |
| `.`   | Dotted-path separator (inside refs and path overrides) | |
| `/`   | Slash-path separator (inside component keys) | |
| `#[`  | Open value-level provenance trailer | Followed by trailer content |
| `]`   | Close of a `#[`-opened trailer | — |
| `(`   | Open function-call argument list OR node-level trailer | Context |
| `)`   | Close of a `(`-opened region | — |
| `$`   | Extension-metadata prefix (`$ext.foo`) | Only in property-key position |

---

## 3. Syntactic grammar (EBNF)

Below is the complete EBNF. All productions use the following
conventions:
- `X*` — zero or more
- `X+` — one or more
- `X?` — optional
- `(X | Y)` — alternation
- `EOL` — end-of-line terminator, one or more consecutive line breaks
  treated as a single EOL

```ebnf
Document         ::= Preamble TopLevelItem* EOF

Preamble         ::= NamespaceDecl? UseDecl* TokensBlock?

NamespaceDecl    ::= 'namespace' DottedPath EOL
UseDecl          ::= 'use' StringLit 'as' IDENT EOL
TokensBlock      ::= 'tokens' Block

TopLevelItem     ::= DefineDecl | Node

DefineDecl       ::= 'define' IDENT ParamList Block
ParamList        ::= '(' (Param (',' Param)* ','?)? ')'
Param            ::= ScalarParam | SlotParam | OverrideParam
ScalarParam      ::= IDENT ':' TypeHint ('=' ValueExpr)?
SlotParam        ::= 'slot' IDENT ('=' NodeExpr)?
OverrideParam    ::= DottedPath '=' ValueExpr         // declared at define level
                                                      // for documentation; actual
                                                      // override happens at call
                                                      // site (see PathOverride)

TypeHint         ::= 'text' | 'number' | 'bool' | 'color' | 'dimension'
                   | 'node' | 'slot'       // structural params typed as node/slot
                   | IDENT                  // user-defined type-name (future)

Node             ::= NodeHead Block?
NodeHead         ::= (TypeKeyword | CompRef | PatternRef)
                     EID?
                     PositionalContent?                 // e.g. text "Hello"
                     NodeProperty*
                     NodeTrailer?
NodeProperty     ::= PropAssign | PathOverride
PositionalContent::= StringLit | TokenRef               // single positional value;
                                                        // only valid on text-bearing
                                                        // TypeKeyword nodes (text,
                                                        // heading, button, etc.)
                                                        // — validator enforces per
                                                        // §7.3

CompRef          ::= '->' CompPath OverrideArgs?        // override-args allow
                                                        //   -> comp(prop=val, ...)
                                                        // as a compact inline
                                                        // override form used at
                                                        // slot-default sites
PatternRef       ::= '&' PatternPath

OverrideArgs     ::= '(' (OverrideArg (',' OverrideArg)* ','?)? ')'
OverrideArg      ::= PropKey '=' ValueExpr

CompPath         ::= (IDENT '::')? SlashPath
PatternPath      ::= (IDENT '::')? DottedPath

SlashPath        ::= IDENT ('/' IDENT)+
DottedPath       ::= IDENT ('.' IDENT)*

EID              ::= '#' IDENT
ERef             ::= '@' IDENT ('.' IDENT)*            // edit addressing
                   | '@' SlashPath
                   | '@' IDENT? ('/' ('*' | '**' | IDENT))+  // wildcards (edit-only)

PropAssign       ::= PropKey '=' ValueExpr
PropKey          ::= DottedPath | ExtKey
ExtKey           ::= '$' 'ext' '.' IDENT ('.' IDENT)*

PathOverride     ::= DottedPath '=' ValueExpr          // at pattern-ref call site

ValueExpr        ::= Literal
                   | TokenRef
                   | CompRef
                   | PatternRef
                   | FunctionCall
                   | PropGroup
                   | Sizing                            // fill / hug / fixed + bounds
                   | NodeExpr                          // only as slot value

NodeExpr         ::= Node                              // exactly one top-level node

Literal          ::= StringLit | NumberLit | HexColorLit | AssetHashLit
                   | BoolLit | NullLit
HexColorLit      ::= '#' HexDigit{6,8}                 // 6 or 8 hex digits
AssetHashLit     ::= HexDigit{40}                      // SHA-1 content-address
                                                       // for asset-registry values;
                                                       // bare hex, no `#` prefix,
                                                       // exactly 40 chars. Valid in
                                                       // ValueExpr position only
                                                       // inside image(asset=...) and
                                                       // similar asset-referencing
                                                       // function calls; the
                                                       // validator restricts.
BoolLit          ::= 'true' | 'false'
NullLit          ::= 'null'

TokenRef         ::= '{' DottedPath '}'                // also resolves param refs

FunctionCall     ::= IDENT '(' FuncArgs? ')'
FuncArgs         ::= FuncArg ((',' | EOL) FuncArg)* ','?
FuncArg          ::= ValueExpr | IDENT '=' ValueExpr   // positional or keyword
                                                       // FuncArgs accept EOL as
                                                       // separator so multi-line
                                                       // calls like gradient-linear(
                                                       //   {stop1},
                                                       //   {stop2}
                                                       // ) parse cleanly

PropGroup        ::= '{' PropGroupEntries? '}'
PropGroupEntries ::= PropAssign (PropGroupSep PropAssign)* PropGroupSep?
PropGroupSep     ::= ',' | EOL | WHITESPACE           // space, comma, or newline
                                                       // all separate entries. This
                                                       // makes `{top=8 bottom=12}`
                                                       // and `{top=8, bottom=12}`
                                                       // and multi-line forms all
                                                       // valid — LLM-reliable.

Sizing           ::= SizingKeyword                     // bare `fill` / `hug` / `fixed`
                   | SizingBounded                     // `fill(min=N, max=N)`
SizingKeyword    ::= 'fill' | 'hug' | 'fixed'
SizingBounded    ::= ('fill' | 'hug') '(' SizingArg (',' SizingArg)* ')'
SizingArg        ::= ('min' | 'max') '=' NumberLit

Block            ::= '{' EOL?
                       (Node | SlotPlaceholder | PropAssign | PathOverride
                        | SlotFill | ValueTrailer)*
                     '}'
SlotFill         ::= IDENT '=' NodeExpr                // inside a pattern-ref body
                                                       // or a CompRef Block (for
                                                       // Figma instance overrides
                                                       // targeting a slot-shaped
                                                       // child of the master)
SlotPlaceholder  ::= '{' IDENT '}'                     // expands slot/arg at
                                                       // semantic analysis; same
                                                       // lexical form as TokenRef,
                                                       // disambiguated by position
                                                       // (block vs value)

NodeTrailer      ::= '(' IDENT PropAssign* ')'         // node-level provenance
ValueTrailer     ::= '#[' IDENT PropAssign* ']'        // value-level provenance;
                                                       // `#[` is a COMPOUND TOKEN
                                                       // (single lex token when `#`
                                                       // is immediately followed by
                                                       // `[` with no whitespace);
                                                       // distinguishes from `#eid`
                                                       // which is `#` + IDENT.
```

### 3.1 Disambiguating `{` contexts

`{` opens one of four syntactic regions, distinguished by what precedes
and what follows:

| Context | Recognition | Example |
|---------|-------------|---------|
| **Block** | After a node head (or `tokens`, `define`, or a slot-fill RHS node-expression) | `frame #x { ... }` |
| **TokenRef / ParamRef** (value position) | After `=` or inside a function-call arg list — single identifier-path inside | `fill={color.surface.card}` |
| **SlotPlaceholder** (block position) | Standalone statement in a Block, single IDENT inside braces | `{cta}` on its own line |
| **PropGroup** | After `=` — `key=value` pairs inside | `padding={top=8 bottom=12}` |

Parser state determines context:
- **In a Block**, `{IDENT}` as a standalone statement is a
  SlotPlaceholder — at semantic analysis, it expands to the slot's
  NodeExpr (or, in the general `{param}` case, to the param's default).
- **In value position** (after `=` or inside a function-call arg list):
  - If the next non-whitespace token after `{` is an IDENT followed by
    `.` or `}`, it's a TokenRef / ParamRef (resolves to a scalar).
  - If the next non-whitespace token is an IDENT followed by `=`, it's
    a PropGroup (nested key-value properties).

### 3.2 Disambiguating slot-fill vs property-assign

Inside a PatternRef Block OR a CompRef Block, an assignment statement
`key = X` can be either:

- A **property assignment** (`PropAssign`) if `X` is a ValueExpr starting
  with a literal, token ref, function call, prop group, or sizing
  keyword
- A **slot fill** (`SlotFill`) if `X` is a NodeExpr (starts with a type
  keyword, `->`, or `&`)

Disambiguation rule (first-token lookahead on RHS, applied identically
in PatternRef and CompRef block contexts):

| First RHS token | Statement kind |
|-----------------|---------------|
| StringLit / NumberLit / HexColorLit / AssetHashLit / BoolLit / NullLit | PropAssign |
| `{` (followed by IDENT `.` / IDENT `}`) | PropAssign (TokenRef value) |
| `{` (followed by IDENT `=`) | PropAssign (PropGroup value) |
| `fill` / `hug` / `fixed` (bare SizingKeyword) | PropAssign (Sizing value) |
| `fill(` / `hug(` | PropAssign (SizingBounded) |
| IDENT `(` (other function names) | PropAssign (FunctionCall value) |
| TypeKeyword | SlotFill |
| `->` | SlotFill |
| `&` | SlotFill |

The rule is syntactic (first-token lookahead) and does NOT require
resolved knowledge of the target define's slot table — it's a pure
parse-time decision. The SEMANTIC CHECK (does the key match a declared
slot / property?) runs after parsing; a SlotFill against a non-slot key
emits `KIND_SLOT_UNKNOWN`, a PropAssign against a non-property key emits
`KIND_PROP_UNKNOWN` at validation time.

**Applies identically to CompRef blocks.** Figma instance overrides
(e.g., `-> button/small/translucent { text="Done" }`) treat the Block
identically — `text="Done"` is a PropAssign (string literal on RHS).
A nested override targeting a slot-shaped child of the master
component uses the SlotFill form: `-> card/primary { action = button #cta }`.

### 3.3 Disambiguating function call vs IDENT reference

Inside a ValueExpr, `IDENT` alone is a bare identifier — an error except
for the three SizingKeyword forms (`fill`, `hug`, `fixed`) which have
dedicated productions. `IDENT(...)` is a function call (or
SizingBounded for `fill`/`hug`). `{IDENT...}` is a TokenRef or
PropGroup (braces disambiguate per §3.1).

### 3.3 Disambiguating function call vs IDENT reference

Inside a ValueExpr, `IDENT` alone is a bare identifier (reserved for
future use, currently an error). `IDENT(...)` is a function call.
`{IDENT...}` is a TokenRef (braces disambiguate).

### 3.4 Auto-generated EIDs

When an explicit `#eid` is absent AND no `as name` alias is used, the
parser synthesizes an id at semantic-analysis time:

```
auto_eid := <TypeKeyword> '-' <1-based-sibling-index-within-parent-of-same-type>
```

Example: three `frame` children of a container with no `#eid` become
`frame-1`, `frame-2`, `frame-3`. This matches the dict IR convention
from `dd/ir.py::build_composition_spec` (see screen-1 → frame-1 →
container-1 pattern).

Auto-ids are NOT stable across tree edits (inserting a new frame at
position 1 renumbers everyone). Code that edits a document MUST NOT
address auto-id'd nodes by their synthesized id — promote to explicit
`#eid` first.

### 3.5 AST shape — `L3Document` and friends

This section specifies the Python object shape the parser emits and the
emitter consumes. It's binding on `dd/markup.py` and on any test that
does `.attr` access on parsed output (see
`tests/test_dd_markup_l3.py`).

All classes live in `dd.markup` and are frozen dataclasses
(`@dataclass(frozen=True)`). Frozen means structural equality holds
via `==`; this is what the round-trip tests check.

```python
from dataclasses import dataclass, field
from typing import Literal, Optional, Union


# --- Top-level ------------------------------------------------------------

@dataclass(frozen=True)
class L3Document:
    namespace: Optional[str]                    # from `namespace x.y.z`
    uses: tuple["UseDecl", ...]                 # from `use "path" as alias`
    tokens: tuple["TokenAssign", ...]           # from `tokens { ... }`
    top_level: tuple["TopLevelItem", ...]       # defines + root nodes, in
                                                # source order
    warnings: tuple["Warning", ...]             # e.g. KIND_UNUSED_IMPORT
    source_path: Optional[str]                  # origin file (for errors)


@dataclass(frozen=True)
class UseDecl:
    path: str                                   # the quoted string literal
    alias: str
    is_relative: bool                           # True if `./` or `../` prefix


@dataclass(frozen=True)
class TokenAssign:
    path: str                                   # e.g. "color.brand.accent"
    value: "Value"


# Top-level items are either defines or construction/edit nodes.
TopLevelItem = Union["Define", "Node"]


# --- Definitions ----------------------------------------------------------

@dataclass(frozen=True)
class Define:
    kind: Literal["define"] = "define"          # discriminant
    name: str = ""                              # the `define NAME` part
    params: tuple["Param", ...] = ()
    body: "Block" = None                        # the `{ ... }` body


@dataclass(frozen=True)
class Param:
    kind: Literal["scalar", "slot", "override"]
    name: str                                   # IDENT
    type_hint: Optional[str]                    # scalar: "text"/"number"/etc.
    default: Optional["Value"]                  # scalar/slot: None if
                                                # required at call site


# --- Nodes ----------------------------------------------------------------

@dataclass(frozen=True)
class Node:
    kind: Literal["node"] = "node"              # discriminant
    head: "NodeHead" = None
    block: Optional["Block"] = None


@dataclass(frozen=True)
class NodeHead:
    head_kind: Literal["type", "comp-ref", "pattern-ref"]
    type_or_path: str                           # TypeKeyword, CompPath, or
                                                # PatternPath string form
    alias: Optional[str]                        # from `alias::` prefix, if any
    scope_alias: Optional[str]                  # = alias (repeated for clarity
                                                # when scope is relevant)
    eid: Optional[str]                          # from `#eid`
    override_args: tuple["PropAssign", ...]     # CompRef `-> c(k=v, ...)` args
    positional: Optional["Value"]               # positional text content
    properties: tuple["Property", ...]          # NodeProperty list
    trailer: Optional["NodeTrailer"]            # `(kind ...)` trailer


@dataclass(frozen=True)
class Block:
    statements: tuple["BlockStatement", ...]


# Block statements — tagged union.
BlockStatement = Union[
    Node,
    "SlotPlaceholder",
    "PropAssign",
    "PathOverride",
    "SlotFill",
    "ValueTrailerStatement",    # rare; provenance on a bare value in a block
]


@dataclass(frozen=True)
class SlotPlaceholder:
    kind: Literal["slot-placeholder"] = "slot-placeholder"
    name: str = ""                              # the IDENT inside `{...}`


# --- Properties / overrides / slot-fills ----------------------------------

Property = Union["PropAssign", "PathOverride"]


@dataclass(frozen=True)
class PropAssign:
    kind: Literal["prop-assign"] = "prop-assign"
    key: str                                    # DottedPath or ExtKey
    value: "Value"
    trailer: Optional["ValueTrailer"]           # `#[kind ...]` on the value


@dataclass(frozen=True)
class PathOverride:
    kind: Literal["path-override"] = "path-override"
    path: str                                   # DottedPath into internal
                                                # structure of a pattern
    value: "Value"


@dataclass(frozen=True)
class SlotFill:
    kind: Literal["slot-fill"] = "slot-fill"
    slot_name: str
    node: Node                                  # single NodeExpr


# --- Values ---------------------------------------------------------------

Value = Union[
    "Literal",
    "TokenRef",
    "ComponentRefValue",
    "PatternRefValue",
    "FunctionCall",
    "PropGroup",
    "SizingValue",
    Node,                                       # when in slot-value position
]


@dataclass(frozen=True)
class Literal:
    kind: Literal["literal"] = "literal"
    lit_kind: Literal["string", "number", "hex-color", "asset-hash",
                      "bool", "null"]
    raw: str                                    # the lexeme as written
    py: object                                  # Python-typed value
                                                # (str / int / float / bool /
                                                # None; hex-color as str)


@dataclass(frozen=True)
class TokenRef:
    kind: Literal["token-ref"] = "token-ref"
    path: str                                   # DottedPath
    scope_alias: Optional[str]                  # `alias::path` prefix


@dataclass(frozen=True)
class FunctionCall:
    kind: Literal["function-call"] = "function-call"
    name: str                                   # e.g. "gradient-linear"
    args: tuple["FuncArg", ...]


@dataclass(frozen=True)
class FuncArg:
    name: Optional[str]                         # None = positional
    value: Value


@dataclass(frozen=True)
class PropGroup:
    kind: Literal["prop-group"] = "prop-group"
    entries: tuple["PropAssign", ...]


@dataclass(frozen=True)
class SizingValue:
    kind: Literal["sizing"] = "sizing"
    size_kind: Literal["fill", "hug", "fixed"]
    min: Optional[float]                        # only for bounded fill/hug
    max: Optional[float]


# --- Trailers -------------------------------------------------------------

@dataclass(frozen=True)
class NodeTrailer:
    kind: str                                   # e.g. "extracted"
    attrs: tuple[tuple[str, Value], ...]        # ordered key=value pairs


@dataclass(frozen=True)
class ValueTrailer:
    kind: str                                   # e.g. "user-edited"
    attrs: tuple[tuple[str, Value], ...]


# --- Errors ---------------------------------------------------------------

@dataclass
class Warning:
    kind: str                                   # e.g. "KIND_UNUSED_IMPORT"
    message: str
    line: Optional[int]
    col: Optional[int]


class DDMarkupError(Exception):
    """Base — carries `.line`, `.col`, `.snippet` when known."""


class DDMarkupLexError(DDMarkupError):
    """Lex-time failure. No `.kind` — lex errors happen before semantics."""


class DDMarkupParseError(DDMarkupError):
    """Parse- or semantic-analysis failure. Has `.kind: str` from the KIND
    catalog in §9.5. Also carries `.eid: Optional[str]` when the error
    is attributable to a specific node."""
    kind: str
    eid: Optional[str]


class DDMarkupSerializeError(DDMarkupError):
    """Emitter failure — value has no canonical serialization. Carries
    `.path` (dotted-key trail from the IR root)."""
```

**Public API on `dd.markup`:**

```python
def parse_l3(source: str, *, source_path: str | None = None) -> L3Document: ...

def emit_l3(doc: L3Document) -> str: ...

def validate(doc: L3Document, *, mode: str = "E") -> list[Warning]: ...
```

All three are pure functions. `parse_l3` + `emit_l3` satisfy:
- `parse_l3(emit_l3(doc)) == doc` — round-trip through the AST
- `emit_l3(parse_l3(src))` is idempotent under a `parse_l3` reparse

The emitter is deterministic (§7.5, §7.6 ordering rules).

---

## 4. Value grammar

### 4.1 Value forms

Five ValueExpr forms, one slot per property. The parser disambiguates
on the first character of the RHS.

| Form | Starts with | Example |
|------|-------------|---------|
| Literal | digit, `-`, `#`, `"`, `true`, `false`, `null` | `42`, `"Skip"`, `#F6F6F6` |
| TokenRef / ParamRef | `{` followed by IDENT + `.` or `}` | `{color.surface.card}` |
| ComponentRef | `->` | `-> nav/top-nav` |
| PatternRef | `&` | `& option-row` |
| FunctionCall | IDENT followed by `(` | `gradient-linear(...)` |
| PropGroup | `{` followed by IDENT + `=` | `{top=8 bottom=12}` |
| NodeExpr (slot-fill only) | a type keyword, `->`, or `&` | inside `{ body = frame ... }` |

### 4.2 Resolution order for `{name}` references

When a `{DottedPath}` is encountered during semantic analysis,
resolution proceeds in this order:

1. **Enclosing-define param scope.** If the path's first segment matches
   a scalar param, slot param, or override param of the innermost
   enclosing `define`, substitute the value.
2. **Top-level `tokens` block** of the current document.
3. **Imported tokens.** For each `use` declaration in reverse order
   (most-recent wins on collision), look up the path.
4. **Universal catalog.** The shadcn-flavored default set
   (`_UNIVERSAL_MODE3_TOKENS` in `dd/compose.py`) is the last resort.
5. **Unresolved.** Hard-error at parse/semantic time with
   `KIND_UNRESOLVED_REF` (per ADR-006 boundary contract).

### 4.3 Function values

Function values are dimension-rich composed values that one-line literals
can't express cleanly:

| Function | Purpose | Example |
|----------|---------|---------|
| `gradient-linear(stop1, stop2, ...)` | Linear gradient fill | `gradient-linear(#D9FF40, #9EFF85)` |
| `gradient-radial(...)` | Radial gradient fill | `gradient-radial(#FFF, #000)` |
| `image(asset=<hash>, mode=<scale>)` | Image fill from asset registry | `image(asset=79b6..., mode=fill)` |
| `rgba(r, g, b, a)` | Raw RGBA (rare; prefer hex) | `rgba(0, 0, 0, 0.3)` |
| `shadow(x, y, blur, color, ...)` | Per-shadow specification | `shadow(0, 2, 8, #0000001A)` |

Function names are a closed set defined by this spec. Unknown function
names are hard-errors (strict — shadowing a typo with a silent pass-through
corrupts extraction fidelity).

### 4.4 Special sizing values

```
Sizing := 'fill' | 'hug' | 'fixed' | NumberLit | FillBounded | HugBounded
FillBounded := 'fill' '(' ('min' '=' NumberLit)? (',' 'max' '=' NumberLit)? ')'
HugBounded  := 'hug'  '(' ('min' '=' NumberLit)? (',' 'max' '=' NumberLit)? ')'
```

Bare number is implicit `fixed`: `width=397` == `width=fixed(397)`.

---

## 5. Node identity

### 5.1 EID rules

- `#eid` is OPTIONAL. Auto-id is generated when absent (see §3.4).
- `#eid` MUST be present when:
  - The node is targeted by a `@eid` reference elsewhere in the document
  - The node is overriden via path-override at any call site
  - The node is a slot-fill target
- Duplicate `#eid` within the same scope is a **hard-error at parse time**
  with `KIND_DUPLICATE_EID`. No auto-rename.
- EID scope is the enclosing Block. `#foo` inside a child block is
  distinct from `#foo` in the parent.

### 5.2 `@eid` addressing (edit context)

- `@eid` dereferences a previously-defined node. Only valid in edit
  context (construction uses `#eid` to define, `@eid` to refer to an
  already-constructed node in the same document or an imported one).
- Path-style addressing: `@card-1.title` descends into the named subtree;
  `@root/header/logo` uses slash-path traversal.
- Wildcards `*` (one level) and `**` (any depth, including zero) are
  valid ONLY in edit addressing: `@grid/*/buy-button`.

### 5.3 `as <name>` aliases

Alternative to `#eid` at pattern-reference call sites. Sugar:

```
& option-row as featured   title="Featured"
```

is equivalent to:

```
& option-row #featured     title="Featured"
```

`as` reads more naturally at LLM-emission time when the caller wants to
name the output; `#eid` reads more naturally when the author is
pre-planning.

---

## 6. Definitions and references

### 6.1 `define` semantics

A `define NAME(params) { body }` declaration introduces a named subtree
template. The body is a Block; the params are typed and may have
defaults.

**Three parametrization primitives, non-overlapping:**

| Primitive | Syntax | What it customizes |
|-----------|--------|-------------------|
| Scalar param | `name: type = default` | Content or scalar property values |
| Slot param | `slot name = default-expr` | Structural subtree fills |
| Path override | `path.inside.pattern = value` (at call site) | Deep property overrides |

At call site:

```
& pattern.product-card
    title="Product"                     # scalar-arg fill
    card.fill={color.action.primary.bg} # path override (if `card` is a slot-or-node id inside)
{
    action = button label="Buy"          # slot fill (if `action` is a slot)
}
```

### 6.2 `use` and namespacing

```
use "path/to/library" as alias
```

- Path is a string literal. Resolution cases:
  - Starts with `./` or `../` → **relative path**, resolved from the
    importing file's directory. `use "./02-card-sheet" as sheet22`.
  - Ends with `.dd` (with or without `./`) → **relative path** (the
    extension is suffixed if absent).
  - Otherwise → **logical library name**, resolved against a configured
    search path. A library name MAY contain `/` (e.g.,
    `"universal/tokens"` resolves within the search path; this is NOT
    a relative path). The search path is configured per-parse-context
    (project-local + system libraries).
- Alias is mandatory. No un-aliased imports.
- Inside the document, cross-library refs use `alias::path`:
  `-> studio::nav/top-nav`, `& sheet22::card-section`.
- Same-library refs use unqualified paths: `& option-row`,
  `-> nav/top-nav`.
- An imported alias that is NEVER referenced inside the document is a
  WARNING (`KIND_UNUSED_IMPORT`) — not fatal, but flagged to drive
  cleanup. Authors who want to declare the import for forward-compat
  without a reference can silence with `use "..." as alias #[keep]`.

### 6.2.1 Define ordering — forward references permitted

Pattern definitions (`define name(...) { body }`) MAY appear either
BEFORE or AFTER their first `& name` reference in a document. The
parser runs in two passes:

1. **Discovery pass** — walks the whole document, records every `define`
   declaration keyed by name into the file's define table. Does NOT
   expand bodies.
2. **Resolution pass** — walks again, expanding `& name` refs against
   the populated define table.

Forward references work. Circular references are detected during
resolution (`KIND_CIRCULAR_DEFINE`, §6.3).

### 6.3 Cycle detection

Definition references form a directed graph. Cycles are hard-errors at
parse time (three-color DFS, `KIND_CIRCULAR_DEFINE`). No transitive
limits; single-level self-recursion is also a cycle.

### 6.4 Scope resolution and shadowing

- Inside a `define`, the param scope shadows outer token refs at
  resolution step 1.
- Nested blocks do NOT introduce new scopes for `{name}` resolution —
  resolution only scopes at the `define` boundary. This keeps scoping
  simple and predictable.
- Imported definitions are flat-namespaced under their alias (`alias::name`);
  there's no nested namespace within an alias.

### 6.5 Dotted-paths vs slash-paths

Two path flavors, **never colliding**:

| Flavor | Used for | Where |
|--------|----------|-------|
| Dotted `a.b.c` | Pattern names, token paths, override paths | Inside `&`, `{}`, and PathOverride |
| Slash `a/b/c` | Component keys | Inside `->` only |

A single ref never mixes: `& a.b.c` is pattern path; `-> a/b/c` is
component path; `a.b/c` is a lex error.

### 6.6 Pattern body cannot contain document preamble

A `define` body is a sequence of nodes / properties / slots / overrides.
It cannot contain `namespace`, `use`, or `tokens` declarations — those
are document-level only.

---

## 7. Axis population

Tier 0 §4.1 defines five specification axes. Each axis maps to a set of
properties in dd markup:

| Axis | Properties | On which node types |
|------|------------|---------------------|
| **Structure** | children, type, slot declarations | All |
| **Content** | text content (positional or `text=`), `label=`, data bindings | Text-bearing types (text, button, heading, ...) |
| **Spatial** | `x`, `y`, `width`, `height`, `layout`, `gap`, `padding`, `align`, `mainAxis`, `constraints`, `min-width`, `max-width`, `min-height`, `max-height` | All with a visual surface |
| **Visual** | `fill`, `fills`, `stroke`, `strokes`, `effects`, `shadow`, `radius`, `opacity`, `visible`, `blend` | All with a visual surface |
| **System** | Top-level `tokens { }` block declaring palette, type scale, spacing scale, shadow scale | Document-level only |

### 7.1 Any axis subset is valid on any node

Wireframe-density content (Structure + Spatial only) is as valid as
full-density content (all five axes). Fixture 03 demonstrates both
wireframe-only and style-only nodes within a single document.

### 7.2 Defaults fill unpopulated axes

When a node specifies a subset, the renderer fills missing axes from:
1. The component or pattern template default (if the node is a ref)
2. The canonical-type catalog default
3. The universal catalog default

Explicit `null` removes a default; absence is "use the default."

### 7.3 Property schema validation

Per-property capability gating (ADR-001) is enforced at **semantic
analysis** time, not parse time. The parser accepts any `IDENT=value`
assignment; the validator (see §10) checks against the per-backend
capability table.

### 7.4 Alignment — `align` shorthand vs `mainAxis` / `crossAxis`

The Spatial axis has three alignment properties that interact:

| Property | Applies to | Values |
|----------|-----------|--------|
| `mainAxis` | Primary-axis alignment within a horizontal/vertical layout | `start` / `end` / `center` / `space-between` / `space-around` / `space-evenly` |
| `crossAxis` | Cross-axis alignment within a horizontal/vertical layout | `start` / `end` / `center` / `stretch` / `baseline` |
| `align` | **Shorthand** for `mainAxis=<v> crossAxis=<v>` when both equal | `start` / `end` / `center` / `stretch` |

**Normalization rule (for emission determinism — Tier 2 byte-parity):**
- If both `mainAxis` and `crossAxis` are set to the SAME value from the
  shorthand-legal set (`start`, `end`, `center`, `stretch`), emit the
  shorthand `align=<v>` and OMIT both long-form props.
- If they differ, or if only one is set, emit the long form(s).
- The emitter MUST be deterministic: the shorthand and long form are
  NEVER both emitted on the same node.

### 7.5 Property key ordering within a node (canonical emission order)

For emission determinism, properties on a single node are emitted in
this total order (Tier 2 byte-parity requires determinism; a stable
total order makes two independent emitters produce byte-identical
output for the same semantic node):

1. **Structural / identity block** (in order):
   `variant`, `role`, `as`
2. **Content block** (in declaration order — text-bearing types only):
   `text`, `label`, `placeholder`, `content`, `value`, `min`, `max`
3. **Spatial block** (in order):
   `x`, `y`, `width`, `height`, `min-width`, `max-width`, `min-height`,
   `max-height`, `layout`, `gap`, `padding`, `mainAxis`, `crossAxis`,
   `align`, `constraints`
4. **Visual block** (in order):
   `fill`, `fills`, `stroke`, `strokes`, `stroke-weight`, `effects`,
   `shadow`, `radius`, `opacity`, `blend`, `visible`, `font`, `size`,
   `weight`, `color`, `line-height`, `letter-spacing`
5. **Extension metadata** (lex order):
   all `$ext.*` keys sorted lexicographically
6. **Path overrides** (at call site only, lex order):
   `dotted.path` overrides sorted lexicographically
7. **NodeTrailer** (last on head line):
   `(kind ...)`

Within each block, keys not listed are sorted lexicographically after
the enumerated keys. Parsers MUST accept any ordering; emitters MUST
use this canonical ordering.

### 7.6 PropGroup entries — canonical internal ordering

Inside a `PropGroup` (e.g. `padding={top=8 right=12 bottom=8 left=12}`),
entries are emitted in this order when the group is one of the
well-known structural groups:

| Group | Order |
|-------|-------|
| `padding={...}` | top, right, bottom, left |
| `radius={...}` | top-left, top-right, bottom-right, bottom-left |
| `constraints={...}` | horizontal, vertical |
| `sizing={...}` | width, height, min-width, max-width, min-height, max-height |

For unknown PropGroup keys, entries are emitted in lex order. Entries
that are absent are omitted from the emission (no `null` placeholders).

---

## 8. Edit grammar (same grammar, addressed at existing nodes)

Construction and editing parse through identical productions. The
difference is whether a node is being *created* (Node with `#eid`) or
*addressed* (Node starting with an `ERef` `@eid`).

### 8.1 Seven verbs (closed set)

| Verb | Role | Example |
|------|------|---------|
| `set` | Mutate properties on an existing node | `set @card-1 radius={radius.lg}` — often sugared |
| `append` | Add a new node as last child of `to=` | `append to=@form { button label="New" }` |
| `insert` | Add at an explicit position | `insert into=@grid after=@card-3 { ... }` |
| `delete` | Remove a node and its subtree | `delete @card-2` |
| `move` | Relocate a node under a new parent | `move @card-1 to=@grid position=first` |
| `swap` | Replace a node with a different one | `swap @button-1 with=-> button/primary/lg` |
| `replace` | Replace subtree in-place with new subtree | `replace @header { frame ... }` |

### 8.2 `set` is implicit on property assignment

When a statement starts with `@eid` followed by `PropAssign`, it's an
implicit `set`:

```
@card-1 radius={radius.lg}
```

is equivalent to:

```
set @card-1 radius={radius.lg}
```

### 8.3 Keyword args for destination

Verbs that take a position use keyword args, not positional:
- `to=@eid` — parent for append
- `into=@eid after=@eid` — position-relative insert
- `with=NodeExpr` — replacement for swap

This avoids "which arg is the source vs target" puzzles that punctuation-
based syntaxes run into.

### 8.4 Construction inside an edit block

The body of an edit verb IS construction using the normal grammar:

```
append to=@form {
  button #submit label="Save"
  text "Required fields marked *"
}
```

### 8.5 Edit addressing — NOT shipping in v0.3 Stage 1 body

Stage 1 ships the parser + emitter for construction. Edit grammar
**parses** in Stage 1 (same grammar, no extra code) but is **not
evaluated** until Stage 4 (Priority 1). Fixture 03 shows the edit form
inside a comment block to illustrate without activating Stage 4 scope.

---

## 9. Provenance annotations

Six kinds per Tier 0 §4.4:
- `extracted` — from the source Figma file
- `retrieved` — from a corpus donor during composition
- `substituted` — from an LLM intervention
- `synthesized` — from a catalog template or universal default
- `user-edited` — from a human author
- `catalog-default` — fallback when no other provenance applies

### 9.1 Node-level trailer

Syntax: `(kind key=value ...)` on the node's head line, before the block:

```
screen #main (extracted src=181) {
  ...
}

card (retrieved src="donor:142" conf=0.91) {
  ...
}
```

Inheritance: a node's trailer sets the default provenance for ALL
descendants. Descendants override by declaring their own trailer.

### 9.2 Value-level trailer

Syntax: `#[kind key=value ...]` after the value, on the same logical
line:

```
fill=#F8F8F8 #[user-edited reason="approved brand review"]
padding={top=8} #[synthesized conf=0.72]
```

Inheritance: none — value trailers are per-value and only apply to that
property.

### 9.3 When to emit a trailer

**Rule of parsimony.** Emit a trailer only when the provenance is
RICHER than what the value's syntax self-describes. A `#F8F8F8` literal
is self-evidently raw (post-Stage-3 this becomes extract-degraded); no
trailer needed unless the origin is non-obvious. A `{color.surface.card}`
token ref is self-evidently a token; no trailer unless the token was
synthesized mid-generation.

### 9.4 Queryable semantics

Provenance trailers are PRESERVED through serde — the parser produces
them as part of the IR, the emitter re-emits them verbatim. The verifier
uses provenance to target low-confidence `synthesized` values first.
UIs filter views by kind.

### 9.5 Structured-error channel and KIND catalog

If parse encounters any structured error, a `DDMarkupParseError` is
raised carrying a `.kind: str` attribute drawn from the **closed KIND
catalog** below. The catalog is normative — parser implementations MUST
emit exactly these kinds for the listed triggers. Tests in
`tests/test_dd_markup_l3.py` and `tests/fixtures/markup/invalid-variations.md`
assert against these exact strings.

This mirrors ADR-006 (boundary contract) and ADR-007 (unified
verification channel): one vocabulary for failure, used by the parser
AND the renderer AND the verifier.

#### Catalog — parse / semantic-analysis errors

| KIND | When fired | Where in spec |
|------|-----------|---------------|
| `KIND_DUPLICATE_EID` | Two `#eid` with the same IDENT in the same Block scope | §5.1 |
| `KIND_UNRESOLVED_REF` | `{dotted.path}` cannot resolve via the order in §4.2 | §4.2 |
| `KIND_UNKNOWN_FUNCTION` | A `FunctionCall` uses an IDENT not in the closed function set (§4.3) | §4.3 |
| `KIND_SLOT_MISSING` | A `& pattern` call site omits a slot with no default | §6.1 |
| `KIND_SLOT_UNKNOWN` | Slot-fill targets an IDENT not declared in the referenced `define`'s slot list | §3.2 |
| `KIND_PROP_UNKNOWN` | Property key is not in the capability table for the node's TypeKeyword on the active backend | §7.3 |
| `KIND_BAD_PATH` | A SlashPath uses `.` or a DottedPath uses `/`; or an EID contains non-IDENT chars | §6.5, §2.8 |
| `KIND_CIRCULAR_DEFINE` | Definition graph has a cycle (detected by three-color DFS) | §6.3 |
| `KIND_CIRCULAR_IMPORT` | `use` import graph has a cycle | §6.2 (and L0↔L3 §3.3) |
| `KIND_CIRCULAR_TOKEN` | `tokens { }` block has a self-referential token cycle | L0↔L3 §2.10 |
| `KIND_AMBIGUOUS_PARAM` | Scalar-arg name collides with an internal eid in the same `define`; call site's `name=X` could bind to either | Q3 |
| `KIND_WILDCARD_IN_CONSTRUCT` | A wildcard `*` or `**` appears inside an `@eid` used in a construction context (not an edit verb) | §5.2, §8 |
| `KIND_EMPTY_BLOCK` | An empty `{}` block body (no children, no properties inside the block) | Q6 |
| `KIND_OVERRIDE_TARGET_MISSING` | A path override at a `& pattern` call site targets an eid that doesn't exist after expansion | §6 (L0↔L3 spec) |
| `KIND_INSTANCE_UNKEYED` | `node_type=INSTANCE` with null `component_key` (extractor-side; fail-open in L3 emission) | L0↔L3 §OQ-2 |
| `KIND_UNUSED_IMPORT` | **Warning** (non-fatal): `use` alias declared but never referenced via `alias::...` | §6.2 |

Note on severity: all KIND values listed are **hard-errors** (halt the
parse) EXCEPT `KIND_UNUSED_IMPORT`, which is a **warning** (surfaced on
the parse result's `warnings` list, parse succeeds).

#### Lex-time errors

Lex-time errors use simpler error classes (not `DDMarkupParseError`)
since they fire before KIND-level semantics exist. They carry only
`line`, `col`, `snippet`:

- Malformed hex literal (wrong digit count, non-hex char)
- Unterminated string literal
- Invalid escape sequence
- Bare `\r` without `\n`
- `*` or non-IDENT char inside `#...` (EID position)
- Unmatched bracket / brace

These propagate as `DDMarkupLexError(DDMarkupError)`.

---

## 10. Grammar-constrained decoding

### 10.1 Supported decoders

XGrammar (ICML 2025), Outlines, llguidance. All three accept EBNF or a
nearly-equivalent BNF with per-production priorities. The EBNF in §3 is
written in a subset acceptable to all three (no unbounded lookahead, no
left-recursion, no greedy quantifiers mixed with alternation).

### 10.2 Token-vocabulary exposure vs grammar mask

Two separate LLM-side mechanisms, both depending on the same capability
table (ADR-001):

| Mechanism | What it does | Failure mode if missing |
|-----------|--------------|-------------------------|
| **System-prompt exposure** | Informs LLM of available tokens / components / patterns / catalog types | Generates references to non-existent tokens (hallucinates) |
| **Grammar mask** | Enforces at decode time that only valid paths emit | Blocks valid but unadvertised paths (empty output) |

Both are required. Exposure without masking → hallucinations under
distribution shift. Masking without exposure → empty / repetitive
output.

### 10.3 Per-backend capability grammar

The ADR-001 capability table is keyed by `(property, backend, node_type)`.
For a given backend, the grammar is specialized: `card` nodes on the
Figma backend accept `radius=` but SwiftUI may not accept per-corner
radius. The per-backend specialization is generated from the capability
table at decode-start time.

### 10.4 Unknown / extension properties

- `$ext.*` property keys are ALWAYS accepted by the grammar (opaque
  preserved). Never constrained.
- Unknown IDENT property keys on known type keywords are warned but
  parsed (fail-open per
  `feedback_fail_open_not_closed.md`).
- Unknown TypeKeyword on a node head is warned but parsed.

---

## 11. Reserved / extension

These are placeholders for post-v0.3 extensions. The parser MUST accept
them as opaque now so forward-compatibility holds:

- `$ext.*` — tool-specific metadata (§4.1, §10.4)
- Alternative units (`rem`, `em`, `%`) — reserved for post-v0.3 spatial
  axis
- `@alias::eid` cross-library edit addressing — reserved; single-library
  edits only in v0.3
- `pattern` as a document root type (like `screen` and `component`) —
  reserved for library files

---

## 12. Canonical example documents

The three fixtures under `tests/fixtures/markup/` are the canonical,
normative examples. Every construct in this spec parses against at
least one fixture:

| Fixture | Exercises |
|---------|-----------|
| [`01-login-welcome.dd`](../tests/fixtures/markup/01-login-welcome.dd) | Preamble, `tokens` block, `define` with all 3 param primitives, `& pattern-ref`, `-> component-ref`, raw-literal fallbacks, node-level + value-level provenance |
| [`02-card-sheet.dd`](../tests/fixtures/markup/02-card-sheet.dd) | Inline `card` type, slot fill with node-expression RHS, path overrides, per-corner `radius`, nested pattern-refs |
| [`03-keyboard-sheet.dd`](../tests/fixtures/markup/03-keyboard-sheet.dd) | Mixed-axis density (wireframe / style-only / full), cross-file `use` alias, multiline string, `$ext.*`, edit-grammar preview in comment |

Per Plan A.5 deliverable (4), three invalid variations per fixture are
documented in the companion `*.invalid-*.dd` files (one commit group;
see Plan B Stage 1.1 tests).

---

## 13. Open questions — CLOSED

All ten open questions are resolved. Decisions below; the spec above
implements each.

### Q1. Token-ref syntax — CLOSED: `{dotted.path}`

**Decision.** `{dotted.path}` is the canonical token-ref form, unified
with param-substitution. Resolution order per §4.2. Rejected
alternatives: `::path` (Rust-like — LLMs confuse with scope operator),
`$path` (YAML-like — conflicts with `$ext`).

### Q2. Provenance trailer syntax — CLOSED: dual `(...)` and `#[...]`

**Decision.**
- Node-level trailer: `(kind key=value ...)` on the head line before
  the block. Inherits to descendants.
- Value-level trailer: `#[kind key=value ...]` after the value.
  Per-value only.

Rationale: visual distinction helps LLM emission reliability. Node-level
has natural home on the head line (no ambiguity with children block);
value-level uses `#[` so it doesn't collide with the `#eid` sigil or
with a standalone `#rgba` color literal.

### Q3. Parametrization primitives — CLOSED: three non-overlapping forms

**Decision.**
- Scalar: `name: type = default-value`
- Slot: `slot name = default-node-expr`
- Path override (at call site): `path.inside = value` — declared at call
  site, not as a param of the define

Collision between a scalar-arg name and a path-override name: at call
site, the parser resolves `name=X` as scalar-arg if `name` matches a
defined scalar; as path-override if `name` matches an internal eid. If
both, it's a hard-error `KIND_AMBIGUOUS_PARAM`; force disambiguation via
`#name=` vs `name=`.

### Q4. Hierarchical ID semantics — CLOSED: optional + auto + hard-collide

**Decision.**
- `#eid` is optional. Auto-id is `{TypeKeyword}-{sibling-index}` (§3.4).
- `#eid` required when the node is referenced from elsewhere.
- Duplicate `#eid` within a scope: hard-error (`KIND_DUPLICATE_EID`).

### Q5. Wildcards — CLOSED: `*` one level, `**` any depth, edit-only

**Decision.** `*` matches exactly one path segment; `**` matches
any-depth zero-or-more. Wildcards are valid ONLY in edit addressing
(`@eid` paths), never in construction. Resolution is against the
symbol table at edit-apply time.

### Q6. Whitespace and block boundaries — CLOSED: explicit braces

**Decision.** Mandatory `{ ... }` for:
- Block on a node with children
- `define` body
- `tokens` body

Empty `{}` is forbidden — represent "no children" by absence.

Inline properties can appear on the head line OR on continuation lines
(any whitespace after the head is valid until the next non-whitespace
token that ends a statement).

### Q7. Comments — CLOSED: `//` and `/* */`, no `/-`

**Decision.** `//` line comments and `/* */` block comments. `/-` (KDL
slash-dash) is NOT adopted — using `delete @eid` in edit context is
more explicit and LLM-reliable. `/-` may be recognized in future as
author-commented-out nodes but it's not in v0.3 scope.

### Q8. Number formats — CLOSED: full IEEE 754 input, canonical emission

**Decision.** Accept: integers, decimals, signed, scientific. Emit:
shortest lossless representation. `8` not `8.0`. Percentages as `0.5`
not `50%`. Pixels are the implicit unit; alternative units reserved.

### Q9. String escapes — CLOSED: standard + unicode, no single quotes

**Decision.** `\n \t \r \" \\ \0` and `\u{NNNN}`. Double-quoted only.
Triple-quoted `"""..."""` for multiline with Python-like dedent.
Newlines inside single-line strings are hard-errors.

### Q10. Extension mechanism — CLOSED: `$ext.*` opaque pass-through

**Decision.** `$ext.*` property keys are always accepted. The grammar
preserves them through parse + emit verbatim. Validator ignores.
External tooling can embed arbitrary metadata at any node level.

---

## 14. One-page cheat sheet (for LLM prompting)

```
// preamble
namespace <dotted.path>
use "<path>" as <alias>
tokens { <key> = <value> ... }

// pattern definition
define <name>(
    <arg>: <type> = <default>,
    slot <slot> = <default-node>,
) {
    <body>
}

// screen root
screen #<eid> (<provenance>) {
    <width=N> <height=N> <fill=...>
    <children ...>
}

// node forms (any of these)
frame      #<eid> <prop=val...> { children }
text       "content" <prop=val...>
rectangle  #<eid> <prop=val...>
-> <path/to/component> #<eid> <prop=val...>
& <pattern-name> #<eid> <prop=val...>

// values
literal:       42  "text"  #F6F6F6  true  false  null
token-ref:     {color.surface.card}
function:      gradient-linear({color.a}, {color.b})
prop-group:    {top=8 right=12 bottom=8 left=12}

// provenance
node-level:    (<kind> <key>=<val>)
value-level:   <value> #[<kind> <key>=<val>]

// sizing
width=fill                 // expand to parent
width=hug                  // shrink to content
width=397                  // fixed pixels (implicit)
width=fill(min=320,max=480)// bounded fill

// layout
layout=horizontal gap=8 padding={top=12 left=16 bottom=12 right=16} align=center
layout=vertical gap=12
layout=absolute  // default; children use x=/y=

// comments
// line comment
/* block comment */
```

---

## 15. Implementation hook

Once this spec is stable, `dd/markup.py` is rebuilt against it during
Plan B Stage 1.2. The existing ~786 LOC of mechanical dict-IR serde
shares these pieces with the new parser:

- Tokenizer primitives (keyword table, string-escape table, number
  parsing)
- `DDMarkupParseError` / `DDMarkupSerializeError` error classes with
  line/col tracking
- The Tier 2 test harness (`tests/test_script_parity.py`)

Everything else — value-form parsing, definition expansion, edit-verb
handling, pattern / token resolution, grammar-mask generation — is new
code against this spec.

---

*This doc is load-bearing. Update this file BEFORE touching
`dd/markup.py` or any consumer.*
