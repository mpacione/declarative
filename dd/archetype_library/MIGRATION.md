# Archetype JSON → `.dd` migration plan — Plan B Stage 2

**Status:** all 12 archetypes migrated. Each parses + round-trips
via `tests/test_archetype_skeletons.py`.

## Current state (2026-04-18)

| Archetype | `.dd` |
|---|---|
| chat | ✅ |
| dashboard | ✅ |
| detail | ✅ |
| drawer-nav | ✅ |
| empty-state | ✅ |
| feed | ✅ |
| login | ✅ (pilot) |
| onboarding-carousel | ✅ |
| paywall | ✅ |
| profile | ✅ |
| search | ✅ |
| settings | ✅ |

The `.dd` files live alongside the legacy `.json` skeletons under
`dd/archetype_library/skeletons/`. Both coexist while consumers
migrate — the `.json` files remain authoritative for now; `.dd`
files are the forward-path form.

## Migration recipe (per archetype)

1. **Read** the JSON skeleton.
2. **Map** each `{type: X}` entry to a dd-markup node of the matching
   type keyword. If the JSON type isn't in `_TYPE_KEYWORDS`
   (`dd/markup_l3.py:1333`), substitute the closest registered base +
   a `variant=<sub-kind>` PropAssign (see `login.dd` comment).
3. **Preserve** any `variant` / property values as PropAssigns on the
   node head.
4. **Wrap** the top-level array in a parameterless
   `define <archetype-name>() { ... }` declaration.
5. **Add test coverage**: the `.dd` file is automatically picked up by
   `tests/test_archetype_skeletons.py`'s parametrize + round-trip
   gates. No test file changes needed unless archetype-specific
   structural invariants are worth asserting (see
   `test_login_archetype_structure` for the shape).

## Closed gaps (fixed during Stage 2 migration)

### Type-keyword fail-open — CLOSED

The parser used to hard-fail on unknown IDENTs in block-body
position (including `icon-button`, `text-input`, `link`,
`list-item`, `navigation-row`, `empty-state`, `search-bar`,
`table`, `stepper`, `shopping-cart`, etc. that the archetype
JSONs reference). Grammar §2.7 requires fail-open.

Fix shipped alongside this migration: `_parse_node` now accepts
any IDENT in head position as a type keyword; the head-
continuation loop correctly terminates when an unknown IDENT
appears on a new line without a following `=` or `.`.

## Known gaps still blocking richer work

### Params aren't exercised by the JSON skeletons

Archetype JSONs are structural templates only — no parametrization.
Per grammar §6.1, `define` supports scalar / slot / path-override
params; migrating to params would make the archetypes more useful
for synthesis (Priority 1 stage).

This is intentional future work — first close the structure-only
migration, then parametrize one archetype as a follow-up pilot.

### No `use` / import mechanism wired up yet

Grammar §6.2 defines `use "path/to/library" as alias`. Semantic
passes don't yet resolve imports. Until they do, archetypes are
isolated documents; consumers can't `& login` to instantiate.

Wiring import resolution is blocked on Stage 2 design decisions
around file-system vs registry-lookup resolution.

### Cycle detection exists for tokens/defines inside one doc

Grammar §6.3 covers intra-doc cycle detection. Cross-document cycle
detection (via `use`) is Stage 2 scope.

## Next steps (when Stage 2 unblocks)

1. Decide type-keyword fail-open policy (gap #1 above).
2. Migrate remaining 11 archetypes in batches.
3. Wire `use` resolution.
4. Write `test_archetype_pattern_instantiation.py` — exercises
   `& login` call-site + slot fills.
5. Ship the archetype `.dd`s as the canonical form; deprecate the
   `.json` skeletons.
