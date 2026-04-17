# L3 spatial-intent grammar

**Version:** v0.1-proposal.
**Source:** 37,877 non-AL-parented Dank nodes (8,449 LLM-emittable);
prior-art survey of iOS / Android / CSS / Tailwind / Figma
(see [`prior_art.md`](./prior_art.md)).

## 1. Design principles

1. **No coordinates in LLM output.** Ever. An offset is a DTCG token
   reference or a named semantic constant. Raw px is allowed but
   flagged.
2. **Grammar is pair-independent.** `horizontal` and `vertical` are
   two independent sub-grammars. An LLM picks one from each.
3. **Non-auto-layout only.** Children of auto-layout frames use the
   existing sizing + order vocabulary — covered by the Cassowary
   solver at 0.92 mean IoU. This grammar fills the other half.
4. **Two translation tables that already exist.** Every construct maps
   to (a) a Figma `constraint_h/constraint_v` + inset emission and
   (b) a CSS `position` / `inset` / `align-self` / `justify-self`
   combination. If a construct fails either mapping, it's wrong.
5. **Minimal — 8 constructs cover 99.28%.** Adding a ninth for
   proportional/scale covers 100% of observed Dank positioning.

## 2. Data model

Proposed IR-node field:

```yaml
spatial:
  # one or both axes may be present; absent axis = inherit parent's
  # layout rule (auto-layout sibling).
  horizontal:
    anchor: leading | center | trailing | stretch | proportional
    offset: "{space.md}" | 16 | 0            # required; 0 allowed
    trailing_offset: "{space.md}" | 16       # only with anchor=stretch
    from: parent | safe_area_leading | safe_area_trailing | sibling:<eid>
  vertical:
    anchor: top | center | bottom | stretch | proportional
    offset: "{space.md}" | 16 | 0
    trailing_offset: "{space.md}" | 16       # only with anchor=stretch
    from: parent | safe_area_top | safe_area_bottom | sibling:<eid>
```

**Field semantics**

- `anchor` — which edge/centre-line of the `from` region the node pins
  to. Dimensionless.
- `offset` — signed distance from the anchor inward into the region.
  `0` means "flush to edge" or "exactly centred". Positive is always
  inward. Negative offsets are legal for center (`-4` shifts left of
  centre) and for stretch-asymmetric (`-10` overhang).
- `trailing_offset` — only meaningful for `anchor: stretch`. Encodes
  the distance from the opposite edge inward. Default: equals `offset`
  (symmetric stretch, the 86% case).
- `from` — the reference region. `parent` (default) is the bounding
  box of the direct parent node. Safe-area variants project onto the
  platform's safe region. `sibling:<eid>` anchors to a named sibling
  — deferred to v0.2 but reserved in the schema.
- `proportional` — for `horizontal.anchor: proportional`, the
  `offset` is a 0.0–1.0 ratio of parent width (CSS `%`, Figma
  `SCALE`). Covers the 2.1% Dank iPad-illustration case.

**A node's full spatial intent is up to 10 tokens** of LLM output:
`{anchor, offset, trailing_offset?, from?} × {h, v}`.

## 3. Coverage claim

Measured against the 8,449 LLM-emittable Dank nodes (non-AL parents,
excluding instance-internal descendants). See
[`part1_stats.json`](./part1_stats.json).

| Construct | Dank count | Dank % | Cum % |
|---|---|---|---|
| `leading × top`     | 1,652 | 19.55 | 19.55 |
| `center  × top`     | 1,475 | 17.46 | 37.01 |
| `leading × stretch` |   988 | 11.69 | 48.70 |
| `stretch × stretch` |   903 | 10.69 | 59.39 |
| `center  × bottom`  |   524 |  6.20 | 65.59 |
| `center  × center`  |   486 |  5.75 | 71.35 |
| `stretch × bottom`  |   453 |  5.36 | 76.71 |
| `leading × bottom`  |   353 |  4.18 | 80.89 |
| `trailing × top`    |   280 |  3.31 | 84.20 |
| `trailing × bottom` |   278 |  3.29 | 87.49 |
| `leading × center`  |   266 |  3.15 | 90.64 |
| `stretch × top`     |   206 |  2.44 | 93.08 |
| `proportional × proportional` (SCALE,SCALE) | 170 |  2.01 | 95.09 |
| `trailing × center` |   156 |  1.85 | 96.93 |
| `stretch × center`  |   102 |  1.21 | 98.14 |
| `trailing × stretch`|    96 |  1.14 | 99.28 |
| `center × stretch`  |    54 |  0.64 | 99.92 |
| `stretch × proportional` |  7 |  0.08 | 100.00 |

**18 anchor-combinations total**; 12 of them cover 93.08% of nodes;
all 18 cover 100%. All 18 are expressible as
`(horizontal.anchor) × (vertical.anchor)` with no new constructs.

**Offsets.** Of the non-scale LLM-emittable nodes (8,272):

- **35.5% have both offsets = 0** — pure anchored-flush.
- **53%** are both-axes bucket-clean on {0, 4, 8, 10, 12, 16, 20, 24,
  32, 40, 48, 64, 80, 96, 112, 160, …}. The Dank rhythm diverges from
  classical 4-pt multiples (10, 30, 50, 60, 70 recur) — confirmed in
  Exp 3 (Dank has no 8-point grid).
- **76%** are horizontally bucket-clean; **64%** are vertically
  bucket-clean.
- The tail (20–35% per-axis "non-bucket") is dominated by three value
  families: (a) iPad artboard half-widths (~725 px = parent 1536 / 2),
  (b) large decorative image offsets, (c) sub-pixel residues from
  designer drag (0.5, 3, 9, 13 — unintentional).

## 4. Translation tables

### 4.1 L3 → Figma (`constraint_h/v` + coordinates)

For a node inside a non-AL parent of width `W`, height `H`:

| L3 horizontal | Figma `constraint_h` | Position output |
|---|---|---|
| `{anchor: leading,  offset: o}`           | `MIN`    | `x = o` |
| `{anchor: trailing, offset: o}`           | `MAX`    | `x = W - width - o` |
| `{anchor: center,   offset: o}`           | `CENTER` | `x = (W - width) / 2 + o` |
| `{anchor: stretch,  offset: l, trailing_offset: t}` | `STRETCH` (LEFT_RIGHT) | `x = l`; `width = W - l - t`; emit `layoutSizingHorizontal: FIXED` |
| `{anchor: proportional, offset: ratio}`   | `SCALE`  | `x = W * ratio` (Figma computes on resize) |

Vertical is symmetric (`top` → `MIN`, `bottom` → `MAX`, etc.).

**`from: safe_area_*`** — the renderer resolves by reading the
  screen's notch geometry (iPhone 13 Pro Max: top=47, bottom=34;
  iPad Pro 11": top=24, bottom=20) and adding the inset to `offset`
  before emission. The emitted Figma `constraint_*` is unchanged;
  only the numeric offset shifts.

**`from: sibling:<eid>`** — the lowering layer emits the sibling's
  resolved geometry + offset at emit time; Figma has no native
  sibling-anchor, so we materialize the position relative to the
  common parent. Renderer contract: sibling must appear earlier in
  the node tree; forward references are rejected at boundary.

### 4.2 L3 → CSS (position / inset / align)

For a parent that is `position: relative`:

| L3 horizontal | CSS output (child) |
|---|---|
| `{anchor: leading, offset: o}`            | `position: absolute; inset-inline-start: o` |
| `{anchor: trailing, offset: o}`           | `position: absolute; inset-inline-end: o` |
| `{anchor: center, offset: 0}`             | `position: absolute; inset-inline: 0; justify-self: center` |
| `{anchor: center, offset: o}`             | `position: absolute; inset-inline-start: calc(50% + {o}); transform: translateX(-50%)` |
| `{anchor: stretch, offset: l, trailing_offset: t}` | `position: absolute; inset-inline-start: l; inset-inline-end: t` |
| `{anchor: proportional, offset: r}`       | `position: absolute; inset-inline-start: calc({r} * 100%)` |

Vertical maps to `inset-block-start`/`inset-block-end` and
`align-self`.

**`from: safe_area_top`** — add
`env(safe-area-inset-top, 0px)` to the offset value via `calc()`.
Native CSS supports this directly on iOS Safari / Chrome Android.

**Tailwind shorthand.** `inset-x-0`, `start-4`, `end-2`, `top-4`,
`-translate-x-1/2`, `self-center`, `justify-self-center` cover
every construct in 4-pt increments. For non-bucket offsets we emit
arbitrary values: `start-[13px]`.

### 4.3 SwiftUI (informative, for cross-platform future)

| L3 horizontal | SwiftUI |
|---|---|
| `{anchor: leading, offset: o}` | `.frame(maxWidth: .infinity, alignment: .leading).padding(.leading, o)` |
| `{anchor: stretch, offset: l, trailing_offset: t}` | `.frame(maxWidth: .infinity).padding(.leading, l).padding(.trailing, t)` |
| `{anchor: center, offset: o}` | `.frame(maxWidth: .infinity).offset(x: o)` |
| `{from: safe_area_top}` | `.safeAreaInset(edge: .top) { … }` |

## 5. Minimality argument

Every construct's necessity, with Dank coverage loss if dropped:

| Drop this construct | Dank nodes orphaned | What breaks |
|---|---|---|
| `leading`           | 3,259 (38.6%) | Most top-left chrome, default positioning |
| `center` (h)        | 2,539 (30.1%) | Title bars, centred modals, bottom FABs |
| `trailing`          |   810 ( 9.6%) | Right-aligned actions, overflow menus |
| `stretch` (h)       | 1,671 (19.8%) | Nav bars, tab bars, full-width cards — not expressible otherwise |
| `top`               | 3,613 (42.8%) | Every top-anchored thing |
| `bottom`            | 1,608 (19.0%) | Bottom sheets, home indicators, tab bars |
| `center` (v)        | 1,010 (12.0%) | Vertically-centred content |
| `stretch` (v)       | 2,041 (24.2%) | Full-height side rails, content regions |
| `proportional`      |   347 ( 4.1% across both axes) | iPad decorative illustrations — would need coords |
| offsets as non-zero | 5,591 (66.2%) non-zero-offset nodes would collapse to at-edge | Fine-grained chrome spacing impossible |
| `stretch.trailing_offset` | 209 (12.5% of stretches) asymmetric | Asymmetric full-width layouts fail |
| `from: safe_area_*` | ~300 top/bottom chrome elements | Every iPhone notch layout breaks |

Every construct above is load-bearing for a non-trivial fraction
of observed nodes. The only one that could arguably defer is
`proportional` (2.1%); v0.1 can ship without it and accept a
coordinate-fallback for that bucket.

## 6. What is NOT in the grammar (5% exceptions)

Deliberately omitted:

1. **Sub-pixel residue offsets (0.5 / 3.0 / 13.0 px)** — designer
   drag noise, not semantic. The generator should round to the
   nearest token / multiple-of-4; the renderer preserves the
   rounded value.
2. **Bias (0.0-1.0 distribute)** — Android's explicit mid-bias.
   Dank has 0 occurrences. Covered implicitly by `center` + signed
   offset.
3. **Chains** — Android's row-of-siblings.  Not applicable to non-AL
   parents. Our auto-layout vocabulary already handles
   `primary_align: SPACE_BETWEEN`.
4. **Barriers** — Android's "align to the widest of N siblings". 0
   detected Dank cases. Defer until observed.
5. **Rotations** — 15.7% of LLM-emitted nodes are rotated
   (mostly 90° ruled lines in `picker-zoom` on the watch app).
   Rotations are expressed separately as `transform.rotation`; they
   compose with `spatial` but aren't part of the positioning
   grammar.
6. **Readable-content-width guide (iOS)** — no analogue in Dank;
   deferred.
7. **`clip` / `overflow`** — orthogonal concern. The grammar does not
   cover clipping intent.

## 7. Explicit schema (Zod-style)

```ts
const SpatialAxisSchema = z.object({
  anchor: z.enum(["leading", "center", "trailing", "stretch", "proportional"]),
  offset: z.union([
    z.string().regex(/^\{[\w.]+\}$/),   // DTCG token ref
    z.number(),                          // raw px
  ]),
  trailing_offset: z.union([
    z.string().regex(/^\{[\w.]+\}$/),
    z.number(),
  ]).optional(),                         // only with anchor=stretch
  from: z.enum([
    "parent",
    "safe_area_leading", "safe_area_trailing",
    "safe_area_top",     "safe_area_bottom",
  ]).or(z.string().regex(/^sibling:[\w-]+$/)).optional().default("parent"),
});

const SpatialSchema = z.object({
  horizontal: SpatialAxisSchema.optional(),
  vertical:   SpatialAxisSchema.optional(),
}).refine(
  // trailing_offset only legal with stretch anchor
  (s) => {
    for (const ax of [s.horizontal, s.vertical]) {
      if (ax?.trailing_offset !== undefined && ax.anchor !== "stretch") {
        return false;
      }
    }
    return true;
  },
  { message: "trailing_offset requires anchor: stretch" },
);
```

This schema is small enough to ship directly as a grammar-constrained
decoding ABNF for LLM output — all enumerated fields, one conditional
cross-field invariant.
