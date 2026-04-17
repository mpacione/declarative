# Prior art — semantic positioning vocabularies

Compared systems: **iOS Auto Layout (NSLayoutAnchor + UILayoutGuide)**,
**Android ConstraintLayout**, **CSS 2021+ (absolute + flex + grid + inset +
anchor positioning)**, **Tailwind CSS utilities**, **Figma's constraint enum**.
Goal: extract the common denominator so L3 maps cleanly to each.

## The primitives everyone exposes

Five primitives show up in every system, with different names:

| Primitive | iOS | Android | CSS | Tailwind | Figma |
|---|---|---|---|---|---|
| Pin-to-leading-edge | `leadingAnchor` | `layout_constraintStart_toStartOf` | `left:0` (LTR) / `inset-inline-start:0` | `start-0` | `constraint_h: MIN` |
| Pin-to-trailing-edge | `trailingAnchor` | `layout_constraintEnd_toEndOf` | `right:0` (LTR) / `inset-inline-end:0` | `end-0` | `constraint_h: MAX` |
| Pin-to-top | `topAnchor` | `layout_constraintTop_toTopOf` | `top:0` | `top-0` | `constraint_v: MIN` |
| Pin-to-bottom | `bottomAnchor` | `layout_constraintBottom_toBottomOf` | `bottom:0` | `bottom-0` | `constraint_v: MAX` |
| Pin-to-center | `centerXAnchor` / `centerYAnchor` | opposite-edge pair with `bias=0.5` | `justify-self:center` + `align-self:center` on abs-positioned with `inset:0` | `self-center` / `justify-self-center` | `constraint_*: CENTER` |
| Stretch-between-edges | both `leadingAnchor` + `trailingAnchor` | both `Start_toStartOf` + `End_toEndOf` parent | `left:0; right:0` or `inset-x:0` | `inset-x-0` | `constraint_h: STRETCH` (a.k.a. LEFT_RIGHT) |
| Proportional scale | N/A (must use multiplier) | `layout_constraintWidth_percent` | `width: 50%` | `w-1/2` | `constraint_*: SCALE` |

Every system has the first six; only Figma and CSS have a first-class
proportional-scale primitive. iOS reaches percentage via multiplier on
constraints (e.g. `view.widthAnchor.constraint(equalTo: parent.widthAnchor, multiplier: 0.5)`).

## What each system adds beyond the common core

**iOS Auto Layout** — layout guides. The critical ones:

- `safeAreaLayoutGuide` — introduced iOS 11, represents the region
  unobscured by status bar / home indicator / nav bar / tab bar
  ([Apple docs](https://developer.apple.com/documentation/uikit/uiview/safearealayoutguide)).
  In practice nearly every top-level screen positions its content
  against this guide, not against the view itself.
- `layoutMarginsGuide` — inset by system-default margins (8–16 pt by
  size class).
- `readableContentGuide` — width-constrained for legibility; stops
  widening past ~672 pt. Used for long-form text content
  ([Use Your Loaf](https://useyourloaf.com/blog/readable-content-guides/)).

**Android ConstraintLayout** — four helpers beyond the core:

- **Bias** — when both edges are pinned, the child centers by default
  at bias=0.5. Any value 0.0–1.0 shifts the tie-breaker. Efficient
  replacement for `marginStart + constraintEnd_toEndOf parent`
  computations.
- **Chains** — a contiguous run of N siblings with paired constraints;
  `chainStyle = spread | spread_inside | packed`. Replaces the iOS
  "add 3 constraints per element" for horizontal stacks. Effectively
  a row of flex children.
- **Barriers** — an invisible line defined as the max edge across N
  referenced views; other views constrain to it. Used when you have a
  label+value pair and want the column separator to sit at the widest
  label. No CSS analogue; approximated by JavaScript in web layouts.
- **Guidelines** — fixed percentage or fixed offset lines declared once
  per layout; many children constrain to them. CSS grid tracks are the
  closest analogue.

Source: [Android docs — Responsive UI with ConstraintLayout](https://developer.android.com/develop/ui/views/layout/constraint-layout)
and [Pusher ConstraintLayout Part 2](https://pusher.com/tutorials/constraintlayout-kotlin-part-2/).

**CSS** — the extensive surface:

- `position: absolute` + `top/right/bottom/left` is the direct primitive
  translation of Figma's constraint enum.
- `inset-inline-*` / `inset-block-*` variants carry RTL awareness out
  of the box.
- **`env(safe-area-inset-top)`** — browser-provided CSS environment
  variable that maps to the iOS notch / Android gesture nav. Used via
  `padding: env(safe-area-inset-top)` or `top: env(safe-area-inset-top)`.
  Equivalent of iOS `safeAreaLayoutGuide`.
- **`align-self` / `justify-self` on absolutely-positioned items**
  (CSS Align Level 3, stable 2024) — when `inset: 0` is set, these
  properties have a non-zero containing-block to align within, turning
  the absolute box into a grid-like alignable item. This is the
  cleanest CSS representation of "anchor + center" without having to
  compute `margin: auto` tricks
  ([MDN `justify-self`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/justify-self)).
- **`position-area` / CSS Anchor Positioning** (2025) — declaratively
  position an element relative to another by name. Closest web
  analogue of Figma "relative to sibling X"
  ([OddBird anchor-positioning](https://www.oddbird.net/2025/02/25/anchor-position-area/)).
- **Flex `justify-content` / `align-items`** — orthogonal to positioning;
  these are for auto-layout siblings, not for free-floating children.
  Our L3 already has this via `primary_align` / `counter_align`.

**Tailwind** — utility aliases for the CSS primitives:

- `top-0 / top-4 / top-6` = `top: 0`, `top: var(--spacing, 1rem)`, …
  Spacing scale matches design-token rhythm (4px increments).
- `inset-0 / inset-x-0 / inset-y-0` = all four / both x / both y
  pinned. Direct stretch primitive.
- `self-start / self-center / self-end / self-stretch` — per-item
  override of parent's `align-items`.
- `justify-self-*` — per-item grid alignment.
  ([Tailwind `top/right/bottom/left`](https://tailwindcss.com/docs/top-right-bottom-left),
  [Tailwind `position`](https://tailwindcss.com/docs/position))

**Figma** — the five-enum constraint system:

- `MIN` / `CENTER` / `MAX` / `STRETCH` / `SCALE` per axis
  ([Figma API — Constraints](https://developers.figma.com/docs/plugins/api/Constraints/)).
- No carry-offset: pin-to-MIN doesn't encode how far from MIN. That
  offset lives in the child's `x`/`y` + `relativeTransform` — what
  Exp B found missing when reconstructing from structure alone.
- No safe-area guide. iOS-chrome placement is done by positioning
  a StatusBar INSTANCE component — the component knows its own
  geometry; the screen knows to pin it `LEFT_RIGHT / TOP`. The
  "safe area" is expressed as design content, not as a layout guide.

## Gaps that mattered for our grammar

1. **Offset from anchor is load-bearing, not optional.** iOS has it
   via `constant:`, Android via `layout_marginStart`, CSS via the
   `inset: Npx` value, Tailwind via the `-<n>` scale. Figma doesn't
   surface it in the constraint enum — but the Plugin API's
   `x`/`y` / `relativeTransform` carry it. L3 must expose it as a
   token-valued offset per anchor.

2. **Stretch wants two offsets, not one.** iOS: both
   `leadingAnchor.constraint(equalTo: safeArea.leadingAnchor, constant: 16)`
   and trailing equivalent. CSS: `left: 16px; right: 16px;`.
   Tailwind: `inset-x-4` (both sides equal) or
   `left-4 right-8` (asymmetric). L3 must support
   `{anchor: stretch, leading_inset: Tok, trailing_inset: Tok}`.
   Dank data: 86% of stretches use equal insets; ~14% are
   asymmetric — worth supporting both.

3. **Center with offset is meaningful, not a bug.** iOS: `centerXAnchor.constraint(equalTo: parent.centerXAnchor, constant: -40)`.
   Android: `layout_constraintHorizontal_bias="0.35"`. CSS:
   `left: calc(50% - 40px)`. Tailwind: `start-1/2 -translate-x-1/2 -ml-10`.
   Dank: 44% of `anchor_h=center` nodes have non-zero offset.

4. **Safe-area-relative positioning is a first-class concept.** Every
   mobile system has it. L3's `from` field should support
   `safe_area_top` / `safe_area_bottom` / `safe_area_leading` / `safe_area_trailing`
   as distinct from raw `parent`. The renderer knows how to project
   those onto Figma (add 47/34/0/0 px padding) or SwiftUI
   (`.safeAreaInset`). In Dank this is done implicitly through
   StatusBar / HomeIndicator INSTANCE nodes — but a generator would
   want the explicit form.

5. **Sibling-relative positioning.** Android barriers and chains plus
   CSS anchor positioning address this. Dank data: 13 "floating
   badge on avatar" patterns detected by name heuristic; not
   prevalent enough to make v0.1 required. But the data model
   should leave the door open — `from: sibling("avatar")` is a
   small extension.

6. **Percentage/scale**. Only Figma and CSS (`width: 50%`) have this
   first-class. Dank data: 2.1% of LLM-emitted nodes carry
   `SCALE/SCALE`. Mostly decorative illustrations in iPad screens.
   Worth supporting as a `proportional` anchor for the responsive
   iPad case; can be deferred if scope requires.

## Common-denominator vocabulary

Every construct below is expressible in iOS / Android / CSS / Figma:

```
horizontal anchor ∈ { leading, center, trailing, stretch }
vertical anchor   ∈ { top,     center, bottom,   stretch }
offset            ∈ token (DTCG dimension ref) | px number | 0
stretch-kind      ∈ { equal-inset | asymmetric | none }
from              ∈ parent | safe-area-* | sibling-<id>
```

Scale/proportional is a platform-specific addition; we mark it
`future` in the base grammar and support it opt-in.

## Sources

- [Apple — `safeAreaLayoutGuide`](https://developer.apple.com/documentation/uikit/uiview/safearealayoutguide)
- [Use Your Loaf — Safe Area Layout Guide](https://useyourloaf.com/blog/safe-area-layout-guide/)
- [Use Your Loaf — Pain Free Constraints with Layout Anchors](https://useyourloaf.com/blog/pain-free-constraints-with-layout-anchors/)
- [Use Your Loaf — Readable Content Guides](https://useyourloaf.com/blog/readable-content-guides/)
- [Hacking with Swift — Auto Layout cheat sheet](https://www.hackingwithswift.com/articles/140/the-auto-layout-cheat-sheet)
- [Android — Build a responsive UI with ConstraintLayout](https://developer.android.com/develop/ui/views/layout/constraint-layout)
- [Android — Barrier API reference](https://developer.android.com/reference/androidx/constraintlayout/widget/Barrier)
- [ConstraintLayout — Creating a chain](https://constraintlayout.com/basics/create_chains.html)
- [Pusher — ConstraintLayout Part 2: constraints, bias, chains](https://pusher.com/tutorials/constraintlayout-kotlin-part-2/)
- [Riggaroo — ConstraintLayout Guidelines, Barriers, Chains, Groups](https://riggaroo.dev/constraintlayout-guidelines-barriers-chains-groups/)
- [MDN — `position`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/position)
- [MDN — `justify-self`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/justify-self)
- [MDN — `align-self`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/align-self)
- [MDN — `place-self`](https://developer.mozilla.org/en-US/docs/Web/CSS/place-self)
- [CSS-Tricks — Complete Guide to Grid](https://css-tricks.com/snippets/css/complete-guide-grid/)
- [OddBird — CSS Anchor Positioning with position-area](https://www.oddbird.net/2025/02/25/anchor-position-area/)
- [Tailwind — `top / right / bottom / left`](https://tailwindcss.com/docs/top-right-bottom-left)
- [Tailwind — `position`](https://tailwindcss.com/docs/position)
- [Figma Developer Docs — Constraints](https://developers.figma.com/docs/plugins/api/Constraints/)
- [Figma Learn — Apply constraints to define how layers resize](https://help.figma.com/hc/en-us/articles/360039957734-Apply-constraints-to-define-how-layers-resize)
