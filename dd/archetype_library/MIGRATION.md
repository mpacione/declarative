# Archetype JSON → `.dd` migration plan — Plan B Stage 2

**Status:** pilot shipped. `login.dd` proves the migration path end-to-end.

## Current state (2026-04-18)

| Archetype | JSON | `.dd` | Status |
|---|---|---|---|
| login | `skeletons/login.json` | `skeletons/login.dd` | ✅ pilot shipped |
| chat | `skeletons/chat.json` | — | JSON only |
| dashboard | `skeletons/dashboard.json` | — | JSON only |
| detail | `skeletons/detail.json` | — | JSON only |
| drawer-nav | `skeletons/drawer-nav.json` | — | JSON only |
| empty-state | `skeletons/empty-state.json` | — | JSON only |
| feed | `skeletons/feed.json` | — | JSON only |
| onboarding-carousel | `skeletons/onboarding-carousel.json` | — | JSON only |
| paywall | `skeletons/paywall.json` | — | JSON only |
| profile | `skeletons/profile.json` | — | JSON only |
| search | `skeletons/search.json` | — | JSON only |
| settings | `skeletons/settings.json` | — | JSON only |

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

## Known gaps blocking full migration

### 1. Type-keyword registry is too narrow

JSON archetype types include `icon_button`, `text_input`, `link`,
`section_header`, `list_item`, `tag`, `notification`, ... — none of
which are in the current `_TYPE_KEYWORDS` frozenset
(`dd/markup_l3.py:1333`). Grammar §2.7 says:

> Parsers SHOULD warn on unknown type keywords but MUST NOT
> hard-fail (fail-open per `feedback_fail_open_not_closed.md`).

The current parser hard-fails on unknown identifiers in block body.
Fixing this would make migration drop-in lossless:

- Option A: extend `_TYPE_KEYWORDS` to include the archetype-level
  canonical types. Compile-time-safe and documents the catalog.
- Option B: make unknown type keywords a soft warning (as the
  spec requires). Lets archetypes use any semantic name.

Both are Stage 2 spec work. Currently blocked on not having decided
between A and B.

### 2. Params aren't exercised by the JSON skeletons

Archetype JSONs are structural templates only — no parametrization.
Per grammar §6.1, `define` supports scalar / slot / path-override
params; migrating to params would make the archetypes more useful
for synthesis (Priority 1 stage).

This is intentional future work — first close the structure-only
migration, then parametrize one archetype as a follow-up pilot.

### 3. No `use` / import mechanism wired up yet

Grammar §6.2 defines `use "path/to/library" as alias`. Semantic
passes don't yet resolve imports. Until they do, archetypes are
isolated documents; consumers can't `& login` to instantiate.

Wiring import resolution is blocked on Stage 2 design decisions
around file-system vs registry-lookup resolution.

### 4. Cycle detection exists for tokens/defines inside one doc

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
