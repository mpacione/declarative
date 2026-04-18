# Invalid variations — expected-rejected inputs for parser tests

**Status:** hand-authored Plan A.4/A.5 follow-on (reconciled after review).
Normative for Plan B Stage 1 parser tests (the parser MUST reject each
of these with the indicated `KIND_*` from the catalog in
`docs/spec-dd-markup-grammar.md` §9.5). Each variation shows the minimal
delta from its base fixture — ideally exactly one violation per example.

---

## 01-login-welcome — invalid variations

### 01-invalid-duplicate-eid.dd

Duplicate `#eid` within the same scope → `KIND_DUPLICATE_EID` (§5.1).

```
screen #01 {
  width=428 height=926
  frame #tile-1 width=140 height=100
  frame #tile-1 width=140 height=100   // ← duplicate #tile-1 in this scope
}
```

### 01-invalid-unresolved-token.dd

Token reference with no resolver hit → `KIND_UNRESOLVED_REF` (§4.2).

```
screen #01 {
  width=428 height=926
  fill={color.brand.accent}   // ← no matching token in scope
  // (compare to 01-login-welcome.dd which defines color.brand.accent
  //  in its tokens block; removing the tokens block breaks resolution)
}
```

### 01-invalid-unknown-function.dd

Unknown function name → `KIND_UNKNOWN_FUNCTION` (§4.3, strict — the
closed function set is `gradient-linear`, `gradient-radial`, `image`,
`rgba`, `shadow`).

```
screen #01 {
  width=428 height=926
  fill=radial-blur(#D9FF40, 42)   // ← `radial-blur` is not a function
}
```

---

## 02-card-sheet — invalid variations

### 02-invalid-slot-missing.dd

Pattern call omits a slot with no default → `KIND_SLOT_MISSING` (§6.1).

```
define card-section(
    heading: text = "Section",
    slot body,              // ← no default, required at call site
) {
  frame #section width=380 layout=vertical gap=8 {
    text {heading}
    {body}
  }
}

screen #02 {
  width=428 height=926
  & card-section heading="Presets"      // ← missing body= slot fill
}
```

### 02-invalid-dot-in-comp-path.dd

`.` inside a CompPath (slash-path-only) → `KIND_BAD_PATH` (§6.5).

```
screen #02 {
  width=428 height=926
  -> nav.top-nav x=0 y=0    // ← `.` in component ref (must be `/`)
}
```

### 02-invalid-slash-in-pattern-path.dd

`/` inside a PatternPath (dotted-path-only) → `KIND_BAD_PATH` (§6.5).

```
define row-tile() { frame #t }

screen #02 {
  width=428 height=926
  & row-tile/child         // ← `/` in pattern ref (must be `.`)
}
```

### 02-invalid-circular-define.dd

Definition cycle → `KIND_CIRCULAR_DEFINE` (§6.3).

```
define a(slot s = & b) { frame #a }
define b(slot s = & a) { frame #b }   // ← a → b → a cycle
```

---

## 03-keyboard-sheet — invalid variations

### 03-invalid-wildcard-in-construction.dd

Wildcard in a construction-context `@eid` — wildcards are edit-only →
`KIND_WILDCARD_IN_CONSTRUCT` (§5.2, §8 — wildcards are valid in `@eid`
addressing ONLY during edit verbs; a construction top-level `@` is
illegal).

```
screen #03 {
  width=428 height=926
  @grid/*/buy-button width=100 height=40   // ← `@eid` at construction
                                            //   position uses a wildcard
                                            //   which is edit-only
}
```

### 03-invalid-empty-block.dd

Empty `{}` block with nothing inside → `KIND_EMPTY_BLOCK` (§3, §6 —
"empty `{}` is forbidden — represent 'no children' by absence"; Q6).

```
screen #03 {
  width=428 height=926
  frame #decorative {}        // ← empty block; remove the braces instead
}
```

### 03-invalid-ambiguous-param.dd

A scalar-arg name collides with an internal eid inside the define body;
at the call site the `name=X` form can't disambiguate between
scalar-arg fill and path-override → `KIND_AMBIGUOUS_PARAM` (Q3, §9.5).

```
define row(
    header: text = "Top",          // ← scalar-arg named `header`
) {
  frame #header width=393 {        // ← internal eid also named `header`
    text {header}
  }
}

screen #03 {
  width=428 height=926
  & row header="Hi"                // ← at the call site, `header=` is
                                   //   ambiguous: scalar-arg fill OR
                                   //   path-override to `#header` node?
                                   //   Grammar rejects at define-decl
                                   //   time (Q3) with KIND_AMBIGUOUS_PARAM
}
```

---

## Implementation note (Plan B Stage 1.1)

The parser test suite (`tests/test_dd_markup_l3.py`) parametrizes over
these nine inputs. Each test:
1. Reads the fenced `.dd` code block from this file keyed by the
   section header's slug (e.g. `02-invalid-dot-in-comp-path`)
2. Attempts to parse via `dd.markup.parse_l3(source)` (the new L3
   parser API; see grammar spec §3.5 for the full contract)
3. Asserts the raised exception is `DDMarkupParseError` and carries the
   documented `.kind: str` matching the catalog in grammar spec §9.5

Coverage of the `KIND_*` catalog by these nine variations:
- `KIND_DUPLICATE_EID` (identity-collision)
- `KIND_UNRESOLVED_REF` (resolution miss)
- `KIND_UNKNOWN_FUNCTION` (closed-function-set violation)
- `KIND_SLOT_MISSING` (required-slot missing at call)
- `KIND_BAD_PATH` ×2 (dotted in slash-only / slash in dotted-only)
- `KIND_CIRCULAR_DEFINE` (define-graph cycle)
- `KIND_WILDCARD_IN_CONSTRUCT` (edit-only form in construction)
- `KIND_EMPTY_BLOCK` (grammar-shape violation)
- `KIND_AMBIGUOUS_PARAM` (param/eid name clash in define)

`KIND_CIRCULAR_IMPORT`, `KIND_SLOT_UNKNOWN`, `KIND_PROP_UNKNOWN`,
`KIND_OVERRIDE_TARGET_MISSING`, `KIND_INSTANCE_UNKEYED`,
`KIND_CIRCULAR_TOKEN`, and `KIND_UNUSED_IMPORT` are covered by
separate focused tests in `tests/test_dd_markup_l3.py` — they don't
need a fixture-delta since they're orthogonal to the three reference
screens.
