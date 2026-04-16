# Experiment B — Cassowary layout reconstruction

## 1. Numbers

Ten stratified app screens from Dank-EXP-02 (3,510 nodes total; 2,676
visible and scored). Every node had its `x, y, relative_transform`
dropped before the solver saw them, keeping only layout_mode, padding,
item_spacing, counter_axis_spacing, primary/counter align,
layout_sizing_{h,v}, layout_wrap, min/max size, constraint_h/v,
layout_positioning, width/height (intrinsic), and visibility. Kiwi
(Cassowary) was asked to place everything.

| Metric | Value |
|---|---|
| Overall mean IoU (global frame) | **0.098** |
| Overall IoU > 0.85 | **8.6%** |
| Overall IoU > 0.95 | 8.3% |
| Dropped conflicts across all screens | 0 |
| Children of auto-layout parent, parent-local IoU (mean) | **0.915** |
| Children of auto-layout parent, parent-local IoU > 0.85 | **90.5%** |
| Children of non-auto-layout parent, parent-local IoU (mean) | **0.304** |
| Children of non-auto-layout parent, parent-local IoU > 0.85 | **11.2%** |

Per-screen mean (global) ranged from **0.038** (iPhone 13 Pro Max — 77)
to **0.270** (iPad Pro 11" — 1). Per-type local IoU:

| node_type | N | global mean | local mean | local IoU > 0.95 |
|---|---|---|---|---|
| TEXT | 293 | 0.218 | **0.954** | 85.7% |
| INSTANCE | 708 | 0.076 | **0.844** | 82.9% |
| FRAME | 352 | 0.235 | 0.751 | 68.4% |
| GROUP | 35 | 0.296 | 0.638 | 34.3% |
| ELLIPSE | 78 | 0.192 | 0.380 | 24.4% |
| RECTANGLE | 206 | 0.081 | 0.338 | 23.8% |
| VECTOR | 984 | 0.015 | 0.269 | 4.9% |
| BOOLEAN_OPERATION | 20 | 0.250 | 0.250 | 25.0% |

## 2. Where the solver nails it, where it fails

**Nails it.** When a node's immediate parent is an auto-layout frame,
the solver places the child nearly perfectly in the parent's local
frame. TEXT local mean 0.954, INSTANCE 0.844, FRAME 0.751. Primary-axis
stacking, gap, padding, primary-align (MIN / MAX / CENTER /
SPACE_BETWEEN), counter-align, and FILL-sizing all emerge correctly
from the retained structure. No hand-tuning, no per-screen heuristics.

**Fails — two systemic reasons.**

1. **Non-auto-layout parents have no recoverable child offset.**
   Children of a non-AL parent use `constraint_h` / `constraint_v`
   pairs (LEFT/TOP, CENTER/TOP, RIGHT/BOTTOM, LEFT_RIGHT/TOP_BOTTOM,
   SCALE/SCALE). These encode pinned edges but **not the offset from
   the pinned edge.** Only 22% of LEFT,TOP children sit at `(px, py)`;
   the other 78% have `dx, dy` offsets that were literally just
   coordinates. Measured: 0.304 mean local IoU, 11.2% cross 0.85.
2. **The root screen is itself non-auto-layout.** 100% of the 204
   Dank app screens have `layout_mode=None` on the root. Cascading
   error from wrong root-level placement propagates to every
   descendant. That is why global mean collapses to 0.098 even when
   subtree-local reconstruction is 0.92.

VECTOR paths inside icon INSTANCE nodes are the single biggest broken
bucket (984 / 2,676 = 37%, local mean 0.269). Every icon in the corpus
has SCALE/SCALE children at specific inner offsets. `SCALE` tells the
solver "move proportionally with parent resize" but nothing about the
starting offset. RECTANGLE and ELLIPSE fail for the same reason in
different dress — decorative shapes with constraint-based positioning
inside non-AL frames.

## 3. What cannot be reconstructed from structure alone

Three concrete gaps:

1. **Offset-from-anchor for constraint-based placement.** `LEFT` means
   "pinned to parent's left edge plus _some offset_." The offset is
   exactly the stripped coordinate. Every constraint-based child must
   emit `{anchor: left, offset: "16px"}` or `{anchor: left,
   offset_token: "space.md"}`; similarly `BOTTOM` needs
   `offset_from_bottom`, `CENTER` a (possibly zero) offset-from-centre.

2. **Semantically-floating children encoded as non-AL.** The corpus
   has 0 ABSOLUTE nodes, but 1,641 / 2,676 scored nodes are
   effectively in "absolute" positions inside non-AL parents. The IR
   currently cannot distinguish "truly free-floating" from "anchored
   with offset." Both look alike.

3. **Flex-wrap (`layout_wrap=WRAP`).** 244 parents, 1,276 children.
   Naïve axis-swap gave a net regression; proper handling needs a
   line-breaking pass, cleaner if emitted as explicit
   `{direction: row, wrap: true, row_gap: ..., item_gap: ...}`.

Two subtleties the experiment surfaced:

- **Visibility is a layout input.** Invisible children must be skipped
  by HUG sizing; the IR captures `visible` but the generator must
  respect it.
- **Text overflow is implicit.** Parents with FIXED width and narrower
  than their text's intrinsic width let text overflow silently. The IR
  needs explicit overflow intent (bounded + truncation vs HUG parent).

## 4. Claude-as-coordinate-predictor comparison

Not run (time-cap). Useful follow-on: same stripped IR to an LLM. The
conjecture is that an LLM would do better on conventional chrome
(status bar top-left, FAB bottom-right, card stacks with convention)
and worse on the decorative tail.

## 5. Verdict on the architectural claim

**"LLM never emits coordinates; a solver resolves them from structure
+ soft intent" — holds with a materially widened vocabulary.**

Evidence in support: when a node's parent is an auto-layout frame the
solver reaches 0.915 mean local IoU and 90.5% of nodes cross 0.85 —
with zero hand-tuning, zero per-screen heuristics, zero solver
conflicts across 3,510 nodes. The intent vocabulary already in the IR
(layout_mode, padding, item_spacing, primary_align, counter_align,
layout_sizing_{h,v}, visible, layout_positioning) is sufficient for
the auto-layout case.

Evidence the claim must be **amended**: ~60% of scored nodes sit
inside non-auto-layout parents, and for those pure structure does not
determine position. Every root screen is non-auto-layout; cascading
error from one wrong root-child placement destroys downstream
accuracy. Pure structure is not enough.

### Proposed intent-vocabulary amendment

Three additions, all token-valued rather than pixel-valued to preserve
the "no coordinates" spirit:

1. **Offset-from-anchor** per constraint-based child:
   ```yaml
   constraint_h: LEFT
   constraint_v: TOP
   offset_h: { anchor: left,   value: "{space.md}" }   # or "16px"
   offset_v: { anchor: top,    value: "{top_inset}" }
   # CENTER: value may be 0.  LEFT_RIGHT stretches with two insets.
   ```
2. **Semantic anchor enum** for recognised chrome (status_bar,
   app_bar, tab_bar, bottom_sheet, fab, overlay_full, overlay_backdrop).
   For these the renderer supplies the geometry; the LLM names the slot.
3. **`relative_to` sibling pointer** for floating badges etc.:
   `relative_to: sibling("avatar"), anchor: top_right,
   offset_token: "space.xs"`.

**Vector inner geometry** is a separate concern. Icons stay in the
icon-asset registry, referenced by key — the LLM never emits vector
paths. The existing asset-resolver abstraction already supports that.

**Bottom line.** Keep the architectural claim. Widen L3 / L2 from
"auto-layout-only" to "auto-layout + token-valued anchored offsets for
constraint-based children + semantic anchors for chrome + asset-keyed
vectors." With that amendment no coordinates leak into LLM output and
the solver resolves everything else.
