# Experiment G — Minimum positioning vocabulary

## Headline

**4 horizontal anchors × 4 vertical anchors = 16 constructs cover
97.91% of Dank's 8,449 LLM-emittable positioning decisions.** Add
`proportional` (one more primitive per axis) and coverage reaches
100%. 12 constructs cover 93%.

The grammar is: `anchor ∈ {leading, center, trailing, stretch} × {top,
center, bottom, stretch}`, each carrying an optional `offset` (DTCG
token or px, default 0), plus a second `trailing_offset` when
`anchor = stretch` to handle asymmetric full-bleed (13% of stretch
cases). An optional `from` field routes the anchor to
`parent | safe_area_* | sibling:<eid>` when the default parent-box
isn't the right reference. See [`grammar.md`](./grammar.md) for full
schema, [`prior_art.md`](./prior_art.md) for cross-platform
comparison.

Verdict: **ship in v0.1**.

## Methodology, in brief

Part 1 extracted every non-AL-parented node from the 204 Dank app
screens (37,877 rows), computed parent-local position, classified
each node as `(anchor_h, offset_h) × (anchor_v, offset_v)`, and
partitioned into "inside an instance subtree" (29,428 — not LLM
territory, asset-keyed) vs "outside" (8,449 — what a generator would
emit). All headline numbers use the 8,449 subset.

Part 2 surveyed iOS Auto Layout, Android ConstraintLayout, CSS
2021+ (inset/`align-self` on abs positioning / `env(safe-area-*)` /
anchor positioning), Tailwind utilities, and Figma's constraint
enum. Pulled the common-denominator vocabulary.

Part 3 synthesised the grammar from Dank's observed patterns + the
prior-art intersection + explicit translation tables to both Figma
(now) and CSS (future React).

## How Dank analysis changed my priors

Three surprises.

**(1) The anchor vocabulary is tiny.** I expected ~30-40 distinct
patterns. There are 18 total, 12 cover 93%, and they're all
expressible as cross products of `{leading, center, trailing,
stretch}` × `{top, center, bottom, stretch}`. Two edge-case
entries (`stretch × proportional`, `proportional × proportional`)
sit in the long tail. Everything rhymes with the primitives every
mainstream system (iOS, Android, CSS, Tailwind) already has.

**(2) The offsets are where the complexity lives, and Dank is not a
4/8/16 grid system.** 66% of LLM-emitted nodes have non-zero offsets.
Of those, 53% snap to standard buckets {0, 4, 8, 10, 12, 16, 20, 24,
…} but 20-30% (per axis) are "non-bucket" values like 3, 9, 13, 30,
50, 60, 70. Those aren't noise — they're stable recurring Dank
tokens. Exp 3 already flagged this ("Dank has no conventional 4/8
grid; 43% of modal padding is 10px"); this experiment confirms it
operates system-wide. **The grammar must allow arbitrary numeric
offsets, not only bucket-multiples.** DTCG tokens are the right
abstraction — the project's tokens should define whatever spacing
scale the designer actually uses, not an industry-standard one
we impose.

**(3) Root-screen direct children are cleaner than the interior
tree.** 98.1% of the 2,328 depth-1 nodes (the first children of a
screen root) live in just 7 anchor combos: `center × top`
(46.7%), `stretch × bottom` (19.5%), `center × bottom` (11.4%),
`stretch × top` (8.8%), `center × center` (6.0%), `leading × bottom`
(3.1%), `leading × top` (2.6%). This shape matches the intuition
— top bars are centred-top or stretched-top, bottom bars are
centred-bottom or stretched-bottom, modals centre-centre, and
everything else is a content region. The interior tree adds
complexity, but the root is almost trivial to describe.

## Most important design decision

**Offsets are token references, not raw px, and the grammar refuses
to special-case them.** An LLM emits `offset: "{space.md}"` or
`offset: 16`; both are legal, both pass through the same schema. The
lowering stage resolves token refs by reading the project's DTCG
token file; raw-px literals are passed through unchanged.

Why this matters:

- Dank's "non-bucket" values (10px, 50px, 70px) become
  project-specific tokens in design.md's token palette. Exp 3
  already shows the token extractor can surface them. The LLM
  doesn't need a universal grid; it references whatever the project
  actually uses.
- The grammar naturally aligns with the DTCG-at-L2 decision from
  the broader synthesis plan. Tokens are the unit of decoration;
  the positioning grammar is the unit of structure. They compose
  orthogonally.
- Cross-platform portability falls out for free. In Figma the
  offset is a px value; in CSS it's either a `var(--space-md)` or
  a raw px; in SwiftUI it's a `CGFloat` resolved from a tokens
  bundle. The LLM writes the same thing.
- Raw-px fallback means the grammar doesn't block migration: a
  legacy screen with coords 13, 17, 213 can be expressed in L3 by
  just emitting those numbers and deferring token adoption.

The alternative — "constrain offsets to a fixed bucket list" —
was rejected because Dank's actual bucket list isn't the industry's,
and hardcoding values crosses the DTCG tokenisation line.

## The 5% that doesn't fit

**Rotations** (15.7% of LLM-emitted nodes). Most are 90°-rotated
ruled-line markers in watch-face `picker-zoom` components. These are
orthogonal — `transform.rotation` lives as a sibling property of
`spatial`, not inside it. The grammar doesn't need to expand.

**Sub-pixel residue** (1-3% per axis). Values like 0.5, 0.87, 13.0,
3.0 accumulated from designer drag. Not semantic. The generator
should round, the lowering stage should preserve the rounded value.
Not a grammar concern.

**Proportional (SCALE) positioning** (2.1%). Real — iPad artboard
illustrations that resize with the parent at percent-based x/y.
Valid construct, represented by `anchor: proportional, offset:
<0.0-1.0>`. But low-frequency. Can defer to v0.2 and accept a
coordinate-fallback for that bucket without losing much.

**Large-coordinate non-scale positioning** (~1,800 LLM-emitted
nodes with absolute offsets > 100px). Mostly `anchor: center,
offset: ±725` on iPad where a 1536-wide screen has an element
shifted by half-parent-width. These are fine in the grammar as-is
(`center` + signed offset), but visually they scream "this should
be a sibling anchor or a proportional positioning." Not wrong
today; room for v0.2 refinement.

**Sibling-relative positioning**. Data doesn't yet show strong
usage (a handful of "badge on avatar" name-heuristic matches). The
schema reserves `from: sibling:<eid>` but v0.1 doesn't need to
implement it.

## Ship / don't-ship verdict

**Ship.**

The case for v0.1:

- Core grammar covers 97.91% of observed LLM-emittable positioning
  with 16 constructs. Success criterion (90% at <10 constructs) is
  met: 12 constructs cover 93%.
- Both translation tables are concrete and testable. Figma table
  maps onto the existing `constraint_h/v` emission already in
  [`dd/lowering.py`](../../dd/lowering.py); CSS table maps onto
  standard modern CSS.
- The data model is 10 tokens of LLM output at most (`{anchor,
  offset, trailing_offset?, from?} × {h, v}`) — tractable for
  grammar-constrained decoding.
- `proportional` (2.1%) can ship in v0.1 as a fifth enum on both
  axes; it's a three-line addition to both translation tables and
  doesn't cost schema complexity.
- The schema has one cross-field invariant (`trailing_offset`
  requires `anchor: stretch`) — trivial to enforce as a Zod
  refinement or ABNF disjunct.

The case for one more pass:

- Sibling-relative positioning is reserved but not validated. We
  don't have enough signal yet. Revisit after the generator
  produces real outputs and we see whether the solver struggles.
- Rotations are out-of-band; we should spec the companion
  `transform.rotation` field before v0.1 lands.
- The "non-bucket offset" phenomenon deserves an explicit
  tokenisation pass on Dank to produce the project's actual
  spacing tokens. This is Exp 3's work — confirmed, not new.

None of the "one more pass" items block v0.1 shipping; they're
follow-on cleanup.

## Connections to adjacent work

- **Exp B** motivated this experiment. Its recommendation of "three
  IR fields" (offset-from-anchor, semantic-anchor, relative_to
  sibling) is subsumed by the grammar proposed here — with cleaner
  factoring: offset lives on every anchor (not just constraint-based
  ones), `from` generalises both `safe_area_*` and sibling refs
  into one field, and the stretch case gets its own degree of
  freedom (`trailing_offset`).
- **Exp 3** revealed Dank's non-grid spacing; this experiment
  confirms the grammar must allow arbitrary token values. DTCG at
  L2 + this grammar at L3 compose.
- **ADR-006 / ADR-007** — the structured-error channel carries
  `KIND_SPATIAL_UNREPRESENTABLE` for the <1% of nodes that can't
  be expressed; the boundary contract shape already exists.
- **Capability-gated emission** (registry) — each property in the
  grammar gets a per-backend capability flag. SwiftUI can do
  `safeAreaInset` natively; Figma emits via constraint_* + coord
  math; CSS gets `env(safe-area-inset-*)`. The grammar is the same.

## Concrete recommendation

Merge the grammar as `experiments/G-positioning-vocab/grammar.md`.
Open a draft `dd/intent.py` PR that:

1. Defines `SpatialAxisSchema` per grammar.md §7.
2. Implements `lower_l3_to_l0(spatial, parent_geom) -> (constraint_h,
   constraint_v, x, y, width, height)` per the Figma translation
   table.
3. Implements `derive_l3_from_l0(node, parent) -> spatial` for
   retrieval exemplars — reads `x`, `y`, `width`, `height`,
   `parent_width`, `parent_height` + any existing `constraint_*`
   and classifies via the rules in `analyze.py`.

Defer `from: sibling:<eid>` until the generator lands and we see
whether it's needed. Everything else is v0.1.

---

**Artefacts**

- [`analyze.py`](./analyze.py) — 260-line classifier; single
  sqlite read; outputs all CSVs.
- [`dank_positioning_patterns.csv`](./dank_positioning_patterns.csv)
  — 37,877 rows, per-node classification.
- [`anchor_distribution.csv`](./anchor_distribution.csv) — aggregate
  anchor combos × count × cum-pct, both universes.
- [`offset_distribution.csv`](./offset_distribution.csv) — bucket
  histograms per axis, both universes.
- [`coverage_cumulative.csv`](./coverage_cumulative.csv) — full
  grammar-construct histogram; computes how many top-K cover each
  percentile threshold.
- [`part1_stats.json`](./part1_stats.json) — headline numbers.
- [`prior_art.md`](./prior_art.md) — cross-platform vocabulary
  comparison with sources.
- [`grammar.md`](./grammar.md) — the proposed v0.1 L3 grammar with
  coverage claim, translation tables, minimality argument, Zod
  schema.
