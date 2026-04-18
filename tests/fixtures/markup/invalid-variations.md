# Invalid variations — expected-rejected inputs for parser tests

**Status:** hand-authored Plan A.4/A.5 follow-on. Normative for Plan B
Stage 1 parser tests (the parser MUST reject each of these with the
indicated `KIND_*` structured error).

Per Plan A.5 deliverable (4): "at least three invalid variations per
fixture." This file bundles all nine into one document so the parser
test suite can iterate over a single list. Each variation shows the
minimal delta from its base fixture.

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

Unknown function name → `KIND_UNKNOWN_FUNCTION` (§4.3, strict).

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
) { /* ... */ }

screen #02 {
  width=428 height=926
  & card-section heading="Presets"      // ← missing body= slot fill
}
```

### 02-invalid-mixed-path-styles.dd

Mixing `.` and `/` in a single reference path → lex error (`KIND_BAD_PATH`).

```
screen #02 {
  -> nav.top-nav x=0 y=0     // ← `.` in component ref (must be `/`)
  & option-row/tile          // ← `/` in pattern ref (must be `.`)
}
```

### 02-invalid-circular-define.dd

Definition cycle → `KIND_CIRCULAR_DEFINE` (§6.3).

```
define a(slot s = & b) { /* ... */ }
define b(slot s = & a) { /* ... */ }   // ← a → b → a cycle
```

---

## 03-keyboard-sheet — invalid variations

### 03-invalid-wildcard-in-construction.dd

Wildcard used outside edit context → `KIND_WILDCARD_IN_CONSTRUCT` (§5.2).

```
screen #03 {
  width=428 height=926
  frame #grid/*/buy-button   // ← `*` not valid in a construction #eid
        width=100 height=40
}
```

### 03-invalid-empty-block.dd

Empty `{}` block with nothing inside → `KIND_EMPTY_BLOCK` (§3, §6 — "empty `{}` is forbidden — represent 'no children' by absence").

```
screen #03 {
  width=428 height=926
  frame #decorative {}        // ← empty block; remove the braces instead
}
```

### 03-invalid-ambiguous-param.dd

A scalar-arg name collides with an eid declared inside the define body
(path-override name collision) → `KIND_AMBIGUOUS_PARAM` (Q3 decision).

```
define row(
    header: text = "Top",          // ← scalar-arg named `header`
) {
  frame #header width=393 {        // ← internal eid also named `header`
    text {header}
  }
}

screen #03 {
  & row header="Hi"                // ← which `header` does this bind to?
  & row #header.fill=#000          // ← vs path-override syntax
}
```

---

## Implementation note (Plan B Stage 1.1)

The parser test suite's `test_invalid_variations.py` parametrizes over
these nine inputs. Each test:
1. Reads the delta block from this file
2. Attempts to parse it via `dd.markup.parse_dd(source)`
3. Asserts that the raised exception is `DDMarkupParseError` (or its
   validation-specific subclass) and carries the expected `KIND_*` string

The nine variations cover: identity collisions (5.1), resolution errors
(4.2), type-system violations (6.1, 6.3), path-syntax errors (3),
edit-context violations (5.2, 8.5), grammar-shape errors (3, 6), and
parametrization ambiguity (Q3). One per category.
