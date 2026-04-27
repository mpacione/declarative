# Visual diff — HGB - Travel Request - Multiple Options (screen_id 44)

**Source screen:** `512:28164` on page `Screens` (1440×1148)
**Rendered copy:** `4215:87381` on page `Generated Test` (1440×1148)
**Sweep entry summary.json:** `is_parity=true`, `parity_ratio=1.0`, `error_count=0`, `error_kinds=[]`
**Walk JSON (`walks/44.json`):** 16 runtime errors (2 `font_load_failed` + 14 `text_set_failed`)
**Verifier report (`reports/44.json`):** `errors: []`, `is_parity: true`

Screenshots: `source.png` and `rendered.png` in this directory.

## REVISED finding (after bridge-truth verification)

The first-pass visual-diff (preserved below) hypothesized a "top-nav INSTANCE
componentProperties bug" as a NEW bug class slipping through every channel.

**Bridge-truth verification disproved that hypothesis.** Direct query of both
the source instance (`528:722`) and the rendered instance (`4215:87572`) for
their TEXT children's `characters` values, position-sorted by x:

| Position | Source `characters` | Rendered `characters` | Master id | Master font |
|---|---|---|---|---|
| left  | "Transactions" | "Transactions" ← matches | `296:7087` | Akkurat Regular |
| right | **"Travel Request"** | **"Rooms"** ← override didn't apply | `296:7093` | **Akkurat-Bold Bold** |

The right crumb's text override "Travel Request" did NOT apply because
the master node's font is `Akkurat-Bold` which the user's Figma session
cannot load. F11.1 caught the load rejection (`text_set_failed` entry
in `__errors`, kind `characters` — see indices [2], [3], [12] of
`walks/44.json`) and continued, leaving the master's default text "Rooms"
visible.

**This is the SAME bug class as every other visual diff on screen 44 —
unlicensed Akkurat fonts. NOT a separate componentProperties bug.**
The subagent (and I) misread the breadcrumb pattern.

## Recalibrated visual-diff findings

All 9 visible diffs trace to the same single root cause: 14 `text_set_failed`
events from Akkurat / Akkurat-Bold being unloadable in the user's Figma
session. F11.1's catch-and-continue keeps the structural render whole; the
rendered text either falls back to a system font (where the write attempted
fontName composition) or stays as the master's default (where the write
attempted `characters`).

| # | Visible diff | Same Akkurat-load root cause? |
|---|---|---|
| 1 | Right breadcrumb "Travel Request" → "Rooms" | YES (`text_set_failed` characters, no eid) |
| 2 | "Suggested Itinerary" header missing | YES (`text-1` text_set_failed) |
| 3 | Card subtitles "Hampton Inn" → "Airport Code" | YES (`heading-19/22/8` text_set_failed) |
| 4 | Flight time labels (cards 2+3) → "Airport Code" | YES (`text-83/86/89/92` text_set_failed) |
| 5 | Prices "$760.85" font fallback | YES (`heading-16` text_set_failed) |
| 6 | "1 of 3" pill text — actually present in rendered (subagent miscalled) | n/a (no diff) |
| 7 | Footer "Notes" / "Total Price" font fallback | YES (`text-97/98` text_set_failed) |
| 8 | Right rail layout drift | Cascading consequence of #2 |
| 9 | Letter body line-breaks | Cascading consequence of font fallback |

## Verifier-gap class — what genuinely slips through

The two real verifier-blindness classes ARE still:

1. **Walk → report → summary truncation.** The 16 runtime errors in
   `walks/44.json` never reach `reports/44.json` (errors: []) or
   `summary.json` (error_count: 0). The summary's structural
   parity number takes the report at face value.

2. **Per-eid attribution missing on the F11.1 `characters` catch.** Indices
   [2], [3], [12] of `__errors` say `kind: text_set_failed, property:
   "characters"` with NO eid. That makes them unattributable. The
   non-`characters` text-prop catch (`_emit_override_op` line 467) has
   the same gap — it has no `eid` to push because the override-tree code
   path doesn't thread eid through.

**There is NO third bug class.** The "top-nav componentProperties slips
through" hypothesis was wrong. Every visual diff on this screen is
ultimately a font failure that DOES surface in `__errors`, just with
imperfect attribution.

## Implications

- The "44/44 PARITY" headline overclaim that Codex caught is the SAME
  mistake the visual-diff hypothesis made. Both were making confident
  claims from incomplete data without consulting bridge truth. The
  fix is to surface walk `__errors` into the parity verdict (F12a) so
  is_parity=True with N>0 runtime errors becomes obvious at summary level.
- F12b (top-nav componentProperties bug) is no longer needed — there's
  no such bug.
- F11.1 has a real but cosmetic hole: missing `eid` attribution on the
  `characters` catch. Would be nice to fix (F11.2?) but doesn't change
  whether the renderer continues vs aborts.
- For the demo flow: nothing changes from yesterday's recommendation.
  Show one Akkurat-free screen pixel-perfect; show the visual gap on an
  Akkurat-using screen with the runtime-error channel as receipts;
  frame it as "loud failure when we can detect, graceful structural
  fallback when we can't license a font."

## Original first-pass findings (preserved for the record)

These were wrong on item #1 (top-nav componentProperties) and #6 (red
pill missing). Item #1's claim of "no recorded `__errors` entry" was
also wrong — entries [2/3/12] DO record the failure but without eid
attribution, which made them invisible to the eid-keyed cross-reference
the subagent did.
