# Plan — M7.1 Seven-Verb Edit Grammar

**Status:** spec
**Authored:** 2026-04-19 (autonomous Plan-subagent design pass)
**Milestone:** M7.1 — "edit grammar: all seven verbs"
**Successor to:** M7.0.a (classification cascade, shipped)
**Exit criterion (from `docs/plan-synthetic-gen.md` §5):** All 7 verbs parse + apply correctly on minimal fixtures; each verb × each common case has a passing unit test.

---

## Preamble: Architecture Summary

The edit grammar reuses nearly all of the construction grammar. The grammar spec (§8) is explicit: "Construction and editing parse through identical productions." That means M7.1 is three orthogonal additions sitting on top of the existing parser, not a replacement of it:

1. **Parser**: new top-level production recognising verb-statement lines and dispatching to per-verb sub-parsers that return `EditStatement` objects.
2. **AST**: a small set of frozen dataclasses for edit statements, added to `L3Document`.
3. **Engine**: a pure function `apply_edits(doc, stmts) → doc` that walks the `L3Document` tree and applies statements sequentially.

None of the existing 3,106-line parser body changes; the new productions hook in at the `parse_l3` dispatch loop only.

---

## Section 1 — Parser Changes (`dd/markup_l3.py`)

### 1.1 Where verb productions hook in

The `parse_l3` main loop is in the section starting at line 1942:

```python
while c.peek().type != "EOF":
    t = c.peek()
    if t.type == "IDENT" and t.value == "define":
        top_level.append(_parse_define(c))
    else:
        top_level.append(_parse_node(c))
    c.skip_eols()
```

The `else` branch currently swallows everything non-`define`. The insertion point is a third branch before the `else`:

```python
    elif t.type == "IDENT" and t.value in _EDIT_VERBS:
        top_level.append(_parse_edit_statement(c))
```

where `_EDIT_VERBS = frozenset({"set", "append", "insert", "delete", "move", "swap", "replace"})`.

The implicit-set form (`@eid prop=val` with no verb keyword) is already partially handled via `_parse_edit_node`. Currently that path returns a bare `Node` with `head_kind="edit-ref"`. In M7.1 this path must be promoted to return a `SetStatement` instead. The dispatch in the top-level loop already triggers `_parse_node` for `AT`-headed statements; we need to intercept there too:

```python
    elif t.type == "AT":
        top_level.append(_parse_implicit_set(c))
```

The `_is_statement_starter` function at line 1347 already includes all seven verb keywords in its `value in (...)` guard — no change needed there.

### 1.2 Token shapes per verb

All seven verbs share a common prefix: the verb keyword as an `IDENT` token. The grammar §8.3 specifies keyword arguments for destination slots. Here is the complete token shape for each verb:

**`set`** (explicit form):
```
'set' ERef PropAssign+
```
`ERef` is parsed by the existing `_parse_edit_node` infrastructure (the `AT` path). PropAssign+ is the same property-parsing loop already in `_parse_edit_node`. No block body.

**`set`** (implicit form — §8.2):
```
ERef PropAssign+
```
This is the current `_parse_edit_node` return. The change is: instead of wrapping in a bare `Node`, construct a `SetStatement` directly.

**`delete`**:
```
'delete' ERef
```
The simplest verb. Single token after the keyword. No block, no keyword args.

**`append`**:
```
'append' 'to' '=' ERef Block
```
`to=` is a keyword arg whose value is an `ERef`. The `Block` body contains construction nodes (the normal `_parse_block` production). Note: `to` is not in `_KEYWORDS` (it is not reserved at the lexical level); it is parsed as a plain `IDENT` with value `"to"` followed by `=` and then an `AT`-headed `ERef`.

**`insert`**:
```
'insert' 'into' '=' ERef ('after' '=' ERef | 'before' '=' ERef)? Block
```
`into=` is mandatory; `after=` or `before=` is the positional anchor.

**`move`**:
```
'move' ERef 'to' '=' ERef ('position' '=' ('first' | 'last') | 'after' '=' ERef | 'before' '=' ERef)?
```
Per OQ-2 resolution: `position=first` / `position=last` are bare enum values; relative anchors are `after=@eid` or `before=@eid` as separate top-level kwargs (not `position=after=...`).

**`swap`**:
```
'swap' ERef 'with' '=' NodeExpr
```
`NodeExpr` is a single construction node — may be a CompRef (`-> button/primary/lg`), a PatternRef (`& option-row`), or a TypeKeyword node. Uses the existing `_parse_node` production. `with` parses as plain `IDENT` followed by `=`.

**`replace`**:
```
'replace' ERef Block
```
The `Block` body is the new subtree replacing the addressed node's CHILDREN (per OQ-3 Interpretation A). The `replace` target node itself stays; its block is replaced.

### 1.3 Disambiguating verb keywords from property names

Positional disambiguation:

At the top-level loop (and in block-body dispatch), a statement is a verb-statement if and only if the first token is `IDENT` with a value in `_EDIT_VERBS` AND the second token is either `AT` (for `set`, `delete`, `move`, `swap`, `replace`) or `IDENT` with value in `{"to", "into"}` (for `append`, `insert`).

In property-assignment context, `set=value` parses unambiguously because `=` follows immediately; that is never true for a verb-statement (which always has `@eid` or a keyword-arg keyword next).

### 1.4 Error recovery

Malformed verb statements use `KIND_BAD_EDIT_VERB` (a new KIND, see §2.5) carrying the verb name and the expected next token. Examples:

| Malformed input | Error KIND | Message example |
|---|---|---|
| `set @card-1` (no properties) | `KIND_BAD_EDIT_VERB` | "set statement requires at least one property assignment" |
| `append { ... }` (missing `to=`) | `KIND_BAD_EDIT_VERB` | "append requires `to=@eid` keyword arg" |
| `insert into=@grid { ... }` (missing `after=`/`before=`) | `KIND_BAD_EDIT_VERB` | "insert requires position anchor (`after=@eid` or `before=@eid`)" |
| `move @card to=@grid position=middle` | `KIND_BAD_EDIT_VERB` | "position must be `first` or `last`" |
| `swap @button-1` (missing `with=`) | `KIND_BAD_EDIT_VERB` | "swap requires `with=<node-expr>` keyword arg" |
| `delete` (no ERef) | `KIND_BAD_EDIT_VERB` | "delete requires an @eid argument" |
| `replace @header` (no block) | `KIND_BAD_EDIT_VERB` | "replace requires a block body `{ ... }`" |

---

## Section 2 — AST Type Additions

### 2.1 Per-verb frozen dataclasses (no ABC)

Reasoning: pattern-match exhaustiveness, no shared mutable behavior, consistent with existing AST style. An `EditStatement` Union alias is the type annotation for the union:

```python
EditStatement = Union[
    "SetStatement",
    "DeleteStatement",
    "AppendStatement",
    "InsertStatement",
    "MoveStatement",
    "SwapStatement",
    "ReplaceStatement",
]
```

### 2.2 ERef dataclass

```python
@dataclass(frozen=True)
class ERef:
    path: str                    # e.g. "card-1" or "card-1.title" or "grid/*"
    scope_alias: Optional[str]   # for "alias::path" cross-library refs (v0.3 reserved)
    has_wildcard: bool           # True if path contains * or **
    kind: str = "eref"
```

### 2.3 Per-verb dataclasses

```python
@dataclass(frozen=True)
class SetStatement:
    kind: str = "set"
    target: ERef = None
    properties: tuple[object, ...] = ()  # PropAssign | PathOverride
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class DeleteStatement:
    kind: str = "delete"
    target: ERef = None
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class AppendStatement:
    kind: str = "append"
    to: ERef = None
    body: Block = None
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class InsertStatement:
    kind: str = "insert"
    into: ERef = None
    anchor: ERef = None
    anchor_rel: Literal["after", "before"] = "after"
    body: Block = None
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class MoveStatement:
    kind: str = "move"
    target: ERef = None
    to: ERef = None
    position: Literal["first", "last", "after", "before"] = "last"
    position_anchor: Optional[ERef] = None
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class SwapStatement:
    kind: str = "swap"
    target: ERef = None
    with_node: Node = None
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class ReplaceStatement:
    kind: str = "replace"
    target: ERef = None
    body: Block = None
    line: Optional[int] = None
    col: Optional[int] = None
```

### 2.4 Integration with `L3Document`

A separate `edits: tuple[EditStatement, ...]` field on `L3Document` (NOT mixed into `top_level`):

```python
@dataclass(frozen=True)
class L3Document:
    namespace: Optional[str] = None
    uses: tuple[UseDecl, ...] = ()
    tokens: tuple[TokenAssign, ...] = ()
    top_level: tuple[object, ...] = ()
    edits: tuple[object, ...] = ()       # new
    warnings: tuple[Warning, ...] = ()
    source_path: Optional[str] = None
```

Non-breaking additive change; existing code constructing `L3Document` without `edits=` gets `()` by default.

### 2.5 KIND catalog additions

| KIND | When fired | Verb |
|---|---|---|
| `KIND_BAD_EDIT_VERB` | Malformed verb statement | any |
| `KIND_EID_NOT_FOUND` | `apply_edits` cannot resolve `@eid` | any |
| `KIND_EID_AMBIGUOUS` | `@eid` resolves to multiple nodes across sibling scopes | any |
| `KIND_EDIT_CONFLICT` | Two edit statements contradict | multi-edit |
| `KIND_EDIT_INVALID_TARGET` | Verb's operation is structurally invalid on the resolved target | append, insert, move |

### 2.6 Round-trip invariant

`parse_l3(emit_l3(doc)) == doc` holds for documents containing edit statements. Canonical emission order:

1. Preamble (namespace, use, tokens) — unchanged
2. Construction items (`top_level`) — unchanged
3. Edit statements (`edits`) — new section, blank-line separated

---

## Section 3 — `apply_edits` Engine

### 3.1 Function signature

```python
def apply_edits(
    doc: L3Document,
    stmts: list[EditStatement] | None = None,
    *,
    strict: bool = True,
) -> L3Document:
    ...
```

- `stmts` defaults to `list(doc.edits)` when `None`.
- `strict=True` raises `DDMarkupParseError` on first conflict / unresolvable ERef.
- `strict=False` collects errors as `Warning` and continues.
- Returns a new `L3Document`; never mutates input.

### 3.2 Sequential semantics

Statements execute in order. Each statement operates on the result of all previous statements. Conflicts:

1. Statement targeting an ERef previously deleted → `KIND_EDIT_CONFLICT`.
2. Two `set` statements on the same property+ERef → warn (duplicate override), do not hard-error in `strict=False`.

### 3.3 EID resolution strategy

Per spec §2.3.1 sibling-scoped uniqueness. Algorithm:

1. Walk tree collecting all nodes with `head.eid == target.path`.
2. Exactly one match → resolved.
3. Zero matches → `KIND_EID_NOT_FOUND`.
4. Multiple matches → `KIND_EID_AMBIGUOUS` (caller must use dotted-path `@parent-eid.child-eid` or slash-path `@parent/card-1`).

For dotted/slash paths: descend `@sheet.card-1` walks to `eid="sheet"` first then to its child with `eid="card-1"`.

Spec §3.4 prohibits addressing auto-id'd nodes — `KIND_EID_NOT_FOUND` with explanatory message.

### 3.4 Immutability

Use `dataclasses.replace()` for structural rebuild. For tree edits (delete, insert, move), rebuild path from root using `replace()` at each level. Rest of tree shared (copy-on-write).

### 3.5 Per-verb apply semantics

**`set`**: Find target, replace `head.properties` with merged property list, rebuild path to root.

**`delete`**: Find target, remove from parent's `block.statements`, rebuild upward.

**`append`**: Resolve `to=@eid`. Append body nodes to parent's `block.statements`. If parent has no block, create one.

**`insert`**: Resolve `into=@eid` and `anchor=@eid`. Insert body nodes immediately after/before anchor.

**`move`**: Compose `delete + insert` atomically within the move handler.

**`swap`**: Find target, replace in parent's `block.statements` with `with_node`. Preserve target's `head.eid` on replacement so subsequent edits address by same eid. Override-preservation deferred to M7.2.

**`replace`**: Find target, replace its `block` with body. Target node itself stays.

### 3.6 Rotation/mirror primitives

Already-correct behavior (per `feedback_l3_decomposed_primitives.md`). `set @icon-1 rotation=1.5708` sets the rotation primitive; renderer handles matrix reconstruction.

---

## Section 4 — Per-Verb Implementation Order

### Pass 1: Parser + AST (single commit, all red tests at once)

ERef + 7 dataclasses + Union type + `edits` field + 5 KINDs + `_parse_edit_statement` + `_parse_implicit_set` + `emit_edit_statement`. `apply_edits` stub raises NotImplementedError.

### Passes 2-8: verb-by-verb apply (one commit per verb)

1. **`set`** — smallest blast radius, validates ERef resolution
2. **`delete`** — structural reduction, validates parent-lookup pattern
3. **`append`** — structural addition, validates body-node creation
4. **`insert`** — append + anchor resolution
5. **`move`** — composed delete + insert
6. **`replace`** — block replacement
7. **`swap`** last — with M7.2 fixture stub for component-ref form

### Pass 9: integration tests + parity sweep

---

## Section 5 — Test Strategy

### 5.1 File placement

`tests/test_edit_grammar.py` (new file).

### 5.2 Per-verb test pattern

Construct doc → construct EditStatement → apply_edits → assertions on result + immutability of original + round-trip via parse(emit()).

### 5.3 Test cases per verb (S1/S2 ladder coverage)

| Verb | Test case | S-tier reference |
|---|---|---|
| `set` | text string | S1.1 |
| `set` | visibility toggle | S1.2 |
| `set` | color token | S1.3 |
| `set` | radius scalar | S1.4 |
| `set` (implicit) | `@card-1 radius={radius.lg}` no `set` keyword | S1.4 |
| `delete` | remove node | S2.1 |
| `append` | add child to container | S2.2 |
| `insert` | insert after sibling | S2.3 |
| `move` | relocate to new parent | S2.4 |
| `swap` | replace via TypeKeyword (not skipped) + via CompRef (skipped, M7.2 stub) | S2.5 |
| `replace` | replace subtree with new content | — |

### 5.4 Per-verb error cases

Each verb: missing ERef, ERef not found, ambiguous ERef, malformed verb.

### 5.5 Integration tests

1. Three-edit sequence
2. Partial failure (strict=False)
3. KIND_EDIT_CONFLICT detection (strict=True)

### 5.6 Fixture smoke tests

For each existing `.dd` fixture: `apply_edits(doc, [])` returns a doc `== doc` (identity).

### 5.7 Parity gate

After each verb commit: run `tests/test_option_b_parity.py` + `tests/test_script_parity.py`. 204/204 must hold.

---

## Section 6 — Out of Scope for M7.1

- LLM integration (M7.2)
- Verifier-as-agent repair loop (M7.5)
- Grammar-constrained decoding (M7.5)
- Real-component swap with variant family lookups (M7.0.c)
- Wildcard ERef resolution
- Cross-library edit addressing (`@alias::eid`)
- Synthetic token naming
- M6(b) `_spec_elements` shim removal

---

## Open Questions — RESOLVED 2026-04-19 (pending user review)

All resolutions logged in `docs/m7_assumptions_log.md`.

| OQ | Resolution |
|---|---|
| OQ-1 `before=` in insert | INCLUDE (symmetric with `after=`) |
| OQ-2 move position shape | `position=first/last` bare enums; `after=`/`before=` as separate top-level kwargs |
| OQ-3 `replace` semantics | Interpretation A (replaces block content; node stays) |
| OQ-4 multi-property set | ALLOW (`PropAssign+`) |
| OQ-5 auto-id targeting policy | `KIND_EID_NOT_FOUND` with explanatory message; `strict=True` API default |
| OQ-6 swap component-ref test | Write the test, mark `@pytest.mark.skip(reason="stub: M7.0.b")` |

---

## Implementation Sequence

```
Pass 1 — Infrastructure (single commit):
  - ERef + 7 dataclasses + EditStatement Union
  - edits field on L3Document
  - 5 new KINDs in spec §9.5
  - parser productions + emitter
  - apply_edits stub (NotImplementedError)
  - Spec EBNF additions in §8

Pass 2 — set + tests
Pass 3 — delete + tests
Pass 4 — append + tests
Pass 5 — insert + tests
Pass 6 — move + tests
Pass 7 — replace + tests
Pass 8 — swap + tests (one fixture skipped)
Pass 9 — integration tests + 204/204 parity sweep
```
