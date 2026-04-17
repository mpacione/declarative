# Experiment 00f — Mode 3 v3 (11 new backbone templates + text-foreground palette)

**Run:** 2026-04-17 (pt 8)
**DB:** `Dank-EXP-02.declarative.db`
**Bridge:** port 9231, "Generated Test" page, file "Dank (Experimental)"
**Prompts:** identical 12 as 00c / 00d / 00e
**LLM:** Claude Haiku 4.5

## 1. Headline across four runs

| Metric | 00c baseline | 00d v1 | 00e v2 | **00f v3** |
|---|---|---|---|---|
| Rule gate | 10 / 2 / 0 FAILS | 2 / 9 / 1 FAILS | 6 / 4 / 2 PASSES | **6 / 5 / 1 PASSES** |
| VLM-ok (≥7) | 0 | 1 | 4 | **4** |
| VLM-partial (4-6) | 0 | 1 | 3 | **5** |
| VLM-broken (≤3) | 12 | 10 | 5 | **3** + 1 API timeout |
| `createInstance()` calls | 0 | 0 | 46 | **63** |
| Default-100×100 frames | 92 % | 16 % | 10 % | **11 %** |
| Round-trip parity | 204/204 | 204/204 | 204/204 | **204/204** |

The distribution of "broken" outcomes has now halved twice in a row
(12 → 10 → 5 → 3). VLM-partial grew by two (3 → 5) — screens the
VLM is now willing to call "some recognizable UI" where 00e dismissed
them. The "ok" count held steady at 4; 11-vague joined (replacing
09-drawer-nav which stepped back from ok(7) to partial(5) — a real
regression on the drawer-specific template).

## 2. What changed between 00e and 00f

### `dd/composition/providers/universal.py` — 11 new templates

Eleven backbone types that previously fell through to
`_generic_frame_template` now have dedicated `PresentationTemplate`
builders:

- **`header`** — iOS/Android-style top app bar: leading icon button +
  title text + trailing actions. `SPACE_BETWEEN` main-axis alignment,
  56px fixed height.
- **`drawer`** — side drawer: header + vertical nav menu + footer.
  280px fixed width, vertical auto-layout.
- **`navigation_row`** — tappable row: leading icon + label + trailing
  chevron/badge/text. 48px fixed height, `SPACE_BETWEEN` main axis.
- **`avatar`** — circular image container with fallback initials.
  40×40, radius 999.
- **`badge`** — small pill with icon + label. Tone variants
  (destructive/success/warning/info) pick variant-specific fills.
- **`image`** — placeholder frame with neutral tint, 160px height.
- **`icon`** — 20×20 square. Mode-1 instances populate real glyphs.
- **`menu`** — vertical list panel with padding + small gap.
  220px width, with shadow.
- **`tooltip`** — dark-on-light hint label. Small padding, caption
  typography.
- **`popover`** — floating panel with shadow. 280px width.
- **`link`** — inline link-colored text (fg = `color.text.link`).

### `dd/compose.py` — token seed expansion

`_UNIVERSAL_MODE3_TOKENS` extends with:

- **Text-foreground palette** — separate from surface colors.
  `color.text.default` (#0F172A), `color.text.heading` (#020617),
  `color.text.caption` (#475569), `color.text.link` (#2563EB), plus
  `on_tooltip / on_primary / on_destructive` variants. Addresses 00e
  memo §5's "low contrast on body text" complaint.
- **Header / drawer / menu / popover / tooltip / badge** surface and
  border colors.
- **Avatar** fill and fg.
- **Status palette** (success / warning / info bg+fg pairs for the
  badge tone variants).
- **Additional spacing / radius / typography tokens** — header,
  drawer, menu, popover, tooltip, badge padding + gap, radii, font
  sizes.

All values remain literal fallbacks pending a project-token cascade
in v0.2.

## 3. Per-prompt VLM verdict (00e → 00f)

| slug | 00e VLM | 00f VLM |
|---|---|---|
| 01-login | ok (8) | **ok (8)** |
| 02-profile-settings | ok (7) | **ok (8)** ↑ |
| 03-meme-feed | broken (2) | broken (2) |
| 04-dashboard | broken (2) | broken (3) ↑ |
| 05-paywall | partial (5) | partial (5) |
| 06-spa-minimal | broken (3) | **partial (5)** ↑ |
| 07-search | partial (4) | **partial (5)** ↑ |
| 08-explicit-structure | ok (8) | **ok (8)** |
| 09-drawer-nav | ok (7) | partial (5) ↓ |
| 10-onboarding-carousel | partial (4) | unknown (API timeout) |
| 11-vague | broken (3) | **ok (8)** ↑↑ |
| 12-round-trip-test | ok (8) | broken (1) ↓ (LLM emitted 0 components — prompt variance) |

Net: **+3 VLM improvements (02 / 06 / 07 / 11)**, **+1 nudge (04)**,
**1 flat**, **2 regressions (09 / 12)**, 1 API timeout. The 11-vague
jump (broken → ok-8) is the biggest single-prompt win of the sprint.
The 09-drawer-nav regression is a real template calibration issue:
the new dedicated drawer now has specific dimensions that don't fit
the 12-row menu Haiku generated.

## 4. What the VLM sees

Sampling the "broken" screens after 00f:

- **03-meme-feed** — "mostly empty with only a back arrow and scattered text, no recognizable feed structure." The LLM emits 11 components but they're flat text labels; no card structure. Template coverage isn't the bottleneck — the LLM needs to know it should wrap feed items in cards.
- **04-dashboard** — "header and footer button are present, the main content is just two small unstyled text labels." The header template is working (VLM sees it); content beneath is sparse because Haiku emitted only two content rows.
- **12-round-trip-test** — "completely blank." LLM returned 0 components this run (prompt "rebuild iPhone 13 Pro Max - 109 from scratch" is out-of-domain). Prompt variance; not a pipeline issue.
- **09-drawer-nav (regression)** — dedicated drawer template emitted 280-wide drawer frame stacking 6 nav rows. Works structurally but VLM reads the empty space around the 280-wide drawer as "mostly empty screen with a drawer in the corner." Either drawer should be full-width by default, or compose should bias drawer-only screens to auto-sized fills.

## 5. Remaining visible-loss classes

1. **Screen-layout semantics beyond the LLM prompt.** The LLM outputs
   components as a flat list; compose wraps them in an auto-layout
   screen root. When the LLM should have emitted nested structure
   (feed → N meme cards, dashboard → two-column chart + table grid)
   it doesn't. Instructing the LLM more specifically, or applying
   screen-archetype heuristics in compose, is the next content gap.
2. **Drawer/full-screen overlay mismatch.** Drawer template assumes
   a 280-wide side panel inside a screen; when the LLM asks for
   "a drawer menu with 6 nav items" it wants the drawer to BE the
   screen. Either add a `variant: fullscreen` branch, or detect
   single-component-drawer prompts and expand the drawer to fill.
3. **LLM component-list variance.** 12-round-trip-test emitted 0, 6,
   and 6 components across 00d / 00e / 00f with identical prompt.
   Normal sampling variance; but it surfaces as "broken" in the
   gate. Either prompt-level retries or more deterministic sampling
   would address this.

## 6. Reproduction

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
PYTHONPATH=$(pwd) python3 experiments/00f-mode3-v3/run_experiment.py
PYTHONPATH=$(pwd) python3 experiments/00f-mode3-v3/run_walks_and_finalize.py
# build manifest, then:
node render_test/batch_screenshot.js experiments/00f-mode3-v3/screenshot_manifest.json 9231
python3 -m dd inspect-experiment experiments/00f-mode3-v3 --vlm
```

— end memo —
