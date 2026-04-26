# Section 07-roundtrip-render — verdict (Phase D)

**Verdict:** WORKS-CLEAN structurally / WORKS-DEGRADED visually

(Codex synthesis review caught this overclaim. Original verdict "WORKS-CLEAN"
was based on `is_parity=True` × 44 from `summary.json`. The walk JSONs tell a
fuller story: 33 of 44 screens recorded **588 runtime errors** in `__errors`
that the structural verifier doesn't surface in its parity summary. They're
font failures, not structural drifts, but they are real.)

## Summary

Section 7 (Round-trip render & verify) — **44/44 STRUCTURAL PARITY** on the
full HGB corpus after F11 + F11.1, with **visual font fidelity degraded on
33 screens** because the user's Figma session can't license Akkurat
(Lineto commercial font).

```
sweep summary.json (structural parity):
total:            44
is_parity=True:   44
is_parity=False:  0
generate_failed:  0
walk_failed:      0
retried:          0
elapsed:          72.6s   (~1.65s/screen)
error_kinds:      {}      (verifier sees 0 missing_child errors)

walk-side runtime errors (NOT counted by the structural verifier):
walks with runtime errors: 33 of 44
total runtime errors:      588
  528  text_set_failed       (F11.1's catch-and-continue working as designed)
   60  font_load_failed      (Akkurat / Akkurat-Bold reject in preamble preload)
```

**The 33-of-44 number is the honest visual-fidelity headline**, not the
sweep's `error_kinds: {}`. The structural verifier (the thing producing
is_parity=True) walks the rendered tree against IR for missing children;
it doesn't surface `__errors` entries from the render script's runtime
catch handlers. F11.1 deliberately decoupled "structural render survives
font failure" from "every text node loads its font correctly" — the
former is now true on every screen; the latter is true on 11 of 44.

For the user's "review screens visually" goal: 11 screens render with
correct fonts (those using only Inter / DM Sans / Akkurat-Mono / etc.);
33 screens render with Akkurat-using text in Figma's fallback font, which
is a noticeable visual drift but not a layout drift.

## Phase D arc — the two findings that drove F11 + F11.1

The sweep was preceded by two probe iterations that surfaced real renderer
bugs. Both required Codex gpt-5.5 review before fixing.

### Iteration 1 (pre-F11): 3-screen probe → 0/3 PARITY

```
[1/3] screen=1 DRIFT  parity=0.009  errs=116  ir=117  rendered=1
[2/3] screen=2 DRIFT  parity=0.009  errs=112  ir=113  rendered=1
[3/3] screen=3 DRIFT  parity=0.009  errs=109  ir=110  rendered=1
```

**Root cause (F11):** Mode-1 instance override emitter routed
`fontFamily`/`fontWeight`/`fontStyle` through the generic registry path,
emitting `_textNode.fontFamily = "DM Sans"`. TEXT nodes in the Plugin API
have NO such setter — only a composed `.fontName = {family, style}`. Every
direct write threw "object is not extensible". Mode-2's `_emit_text_props`
already did the composition correctly; Mode-1 didn't. Compounded by other
text-property writes (`letterSpacing`, `fontSize`, etc.) lacking the
`loadFontAsync(_t.fontName)` guard the `characters` branch already had.

Fix shipped as commit `8eb6c61` (`fix(renderer): F11`). 22 new
behavior tests in `tests/test_f11_text_override_font_compose.py`.

### Iteration 2 (post-F11): 44-screen sweep → 27/44 PARITY, 17 DRIFT

The 17 DRIFT screens shared a signature: all HGB Travel Request +
Alternative Flights screens (the largest screens in the corpus, 250–2300
IR nodes each). Walks showed exactly 1 of N elements rendered, with
~110–2300 missing_child errors per screen.

Bridge probe via `figma.listAvailableFontsAsync` confirmed: of 9777 fonts
in the user's Figma session, **only Akkurat-Mono is loadable**. Akkurat
(Regular) and Akkurat-Bold reject `loadFontAsync` — they're paid Lineto
commercial fonts the user hasn't licensed. The text in the file's masters
displays correctly (cached glyphs/PNG) but Plugin API `loadFontAsync`
genuinely cannot fetch them.

**Root cause (F11.1):** the renderer's three text-override emission paths
(`characters` branch in `dd/renderers/figma.py`, `text` and `subtitle`
overrides in `dd/render_figma_ast.py`) each wrap the write in
`await figma.loadFontAsync(_t.fontName); _t.characters = "..."` but NONE
of them caught the rejection. The surrounding findOne block uses
try/finally (no catch), so the throw aborted Phase 1 mid-render at the
first instance whose master used Akkurat.

Fix shipped as commit `f30e317` (`fix(renderer): F11.1`). 2 additional
tests in the same file pin the catch shape.

### Iteration 3 (post-F11.1): 44/44 PARITY

The current verdict.

## Caveat — visual fidelity for unloadable fonts

Text in the rendered Akkurat-using screens visually shows as Figma's
fallback font, NOT as Akkurat. The renderer recovered the **structural**
render — every IR element appears, layout is correct, parity is reported
true — but the visual font fidelity is compromised on the screens whose
masters use Akkurat. This is the right boundary: the renderer cannot
license fonts on the user's behalf; it can ensure that one missing font
doesn't take down 117 other unrelated elements. Surfaced as
`text_set_failed` entries in `__errors` for downstream attribution.

If the user wants Akkurat-rendering screens for visual review, they need
to install Akkurat in their Figma installation OR use the renderer's
existing fallback behavior (which now degrades gracefully instead of
aborting Phase 1).

## Evidence

- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep-out/summary.json` —
  full structured per-screen JSON: 44/44 is_parity=True, 0 retried, 0 walk_failed,
  elapsed 72.6s. Error kinds dict empty.
- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep-out/scripts/<id>.js`
  — 44 generated render scripts.
- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep-out/walks/<id>.json`
  — 44 per-screen walk payloads (`__ok=true`, `eid_map` complete).
- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep-out/reports/<id>.json`
  — 44 dd verify --json reports.
- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep.log` —
  per-screen stdout from the sweep run.
- Commits: `8eb6c61` (F11), `f30e317` (F11.1) on `fix/20260425-1215`.
- Codex gpt-5.5 reviewed F11 design (caught virtual-prop issue + figma.mixed)
  and F11 implementation (caught missing per-op try/catch — drove F11.1).

## Performance baseline

- 72.6s wall for 44 screens / 9378 IR nodes total = ~1.65s/screen, ~129 nodes/s.
- 0 walk timeouts (320s wrapper limit unused).
- 0 retries (max_retries=1 was set; never triggered).
- Compare to Dank-EXP-02 baseline: 14/14 in 38.5s after the 2026-04-22 phase-1
  perf cycle (~2.75s/screen on smaller corpus). Phase D HGB at 1.65s/screen
  is consistent — bigger corpus, simpler screens (less variant induction).
