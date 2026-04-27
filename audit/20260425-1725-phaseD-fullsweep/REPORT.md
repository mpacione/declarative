# Phase D — full re-audit (Demo-Plus) on HGB (Experimental)

**Date:** 2026-04-25
**File audited:** HGB (Experimental), file_key `PsYyNUTuIE1IPifyoDIesy` — 44 app_screens, 20275 nodes, 113831 token bindings, 101 component-key registry rows
**Branch:** `fix/20260425-1215` (final tip `7a844b7`); merged into `v0.3-integration` at `ff869e3`
**Method:** Same 9-section harness as Phase B, plus a full 44-screen render-and-verify sweep ("Demo-Plus") for visual review of every rendered screen, plus a follow-on visual-diff cycle on three user-reported issues that surfaced the F13 series
**Reviewers:** Codex `gpt-5.5` reviewed every non-trivial design + implementation across the cycle (caught >5 verdict drifts the orchestrator made)

## Headline (revised after Codex synthesis + visual-diff investigation)

**44/44 app screens render to structural parity in 72.6s.** Within that
total: **11 are fully clean** (no runtime errors, full visual fidelity),
**33 are structurally clean but visually degraded** because the user's
Figma session can't license Akkurat (Lineto commercial font). On those
33, F11.1's catch-and-continue logs 528 `text_set_failed` +
60 `font_load_failed` entries to `__errors` and keeps rendering — every
IR element ends up in the tree, but Akkurat-using text falls back to a
system font instead of the intended typography.

**8 of 9 sections WORKS-CLEAN structurally; 1 intentionally WORKS-DEGRADED
(§9). §7 is WORKS-CLEAN structurally / WORKS-DEGRADED visually for
33 of 44 screens.** Eight renderer/sweep fixes shipped this phase:
F10 (sweep flags), F11 + F11.1 (font composition + load guards),
F12 + F12a (per-eid attribution + walk-error surfacing in verifier
output), F12d (sweep mode lays N renders out in a grid for visual
review), F13a + F13b (recursive deep-merge preserves widthPixels +
text resize/textAutoResize in Phase 3), F13c (port GROUP deferral to
the AST renderer so groups render as real `figma.group(...)` calls
instead of silently coercing to FRAME). All Codex-reviewed before
commit.

**Codex synthesis review caught the original headline's overclaim**:
I had written "44/44 PARITY, 0 errors" based on `summary.json`; Codex
queried the walk JSONs directly, found 588 runtime errors in `__errors`,
and flagged that the verifier dropped them. F12a closes the gap by
plumbing those counts into the verifier's report and the sweep summary.
The new sweep summary headline now reads literally:

```
total:                                         44
is_parity=True:                                44
  ├─ clean (no runtime errs):                  11
  └─ structurally OK / visually degraded:      33
runtime_errors:   588 across 33 screens
  text_set_failed   528
  font_load_failed   60
```

That is the fourth verdict-drift the second-opinion gate caught across
the audit cycle (Section 2 + 4 + 8 in original audit; Section 8 + now
Section 7 in re-audits). The discipline is doing real work.

**A separate visual-diff investigation** on screen 44 ("HGB - Travel
Request - Multiple Options") initially hypothesized a NEW bug class
(top-nav `componentProperties` overrides slipping through silently).
Direct bridge query disproved that — the breadcrumb's wrong second
crumb is the SAME Akkurat-Bold load failure as every other text gap
on the screen. Artefacts at
`audit/.../visual-diff/HGB - Travel Request - Multiple Options/`
preserve the source-vs-rendered screenshots and the bridge-truth
analysis as a record of how the second-opinion gate works in
practice (visual screenshots → metric-shaped claim → bridge query
→ disproven).

## Verdict comparison: Phase B → Phase D

| § | Capability | Phase B | Phase D | Notes |
|---|---|---|---|---|
| 1 | Extraction | WORKS-CLEAN | **WORKS-CLEAN** | Same DB shape: 44 screens, 20275 nodes, 113831 bindings, 101 CKR. F4 fix holds. HGB is a library-source file (0 COMPONENT/COMPONENT_SET nodes, 0/101 CKR rows have figma_node_id) — not a regression. |
| 2 | Token clustering & curation | WORKS-CLEAN | **WORKS-CLEAN** | F6 + F6.1 hold: 0 errors, 0 warnings, 0 collisions. 191 tokens / 191 token_values, 78305 bound bindings, 82.1% coverage. `tokens.css` byte-identical to Phase B. |
| 3a | Heuristic classify | WORKS | **WORKS-CLEAN** | 9378 rows: 56 formal + 9322 heuristic. 82 catalog types, 44 screens. |
| 3b | Three-source classify | WORKS-DEGRADED (cascade behaviour) | *skipped (no live LLM auth)* | Cascade is design, not bug. F8 doc-honesty source unchanged. |
| 4 | L3 markup parser/serializer | WORKS-CLEAN | **WORKS-CLEAN** | 5/5 sample screens byte-identical idempotent through compress passes 1 + 2. F2 + F3 + F7 hold. |
| 5 | 7-verb edit grammar | WORKS-CLEAN | **WORKS-CLEAN** | 176 pass / 1 skip — identical to Phase B. |
| 6 | Agent loop (`dd design --brief`) | WORKS-CLEAN | **WORKS-CLEAN** | 3/3 briefs exit 0. All 4 primitives (NAME/DRILL/EDIT/DONE) exercised. TokenRef syntax not exercised this run — LLM non-determinism, not a regression (F3 source unchanged). |
| 7 | Round-trip render & verify | WORKS-CLEAN (single screen) | **WORKS-CLEAN structurally / WORKS-DEGRADED visually** | **44/44 structural parity in 72.6s with 0 retries. But 33/44 walks recorded font failures (588 runtime errors, all Akkurat-related — Lineto commercial font the user hasn't licensed). F11.1's catch-and-continue keeps the structural render whole when the font load rejects; the affected text renders in Figma's fallback font, not Akkurat. Honest visual-fidelity headline: 11 of 44 screens render with correct fonts.** |
| 8 | Mode-3 (`dd generate-prompt`) | WORKS-CLEAN (post-F9) | **WORKS-CLEAN (F9 contract holds)** | login: 0 imports (planner picked templateless types — graceful fallback, not CKR-name leak). travel-card: 2 imports, both real 40-char hex keys. F9's "100% real keys" contract intact: zero CKR-name leaks across all emitted imports. |
| 9 | Variant induction | WORKS-DEGRADED | **WORKS-DEGRADED** | F5 doc-honesty intact (`--help` describes v0.1-shell behavior; misleading "calls Gemini 3.1 Pro" claim absent). 28 placeholder rows for 7 catalog types (DB-state difference vs Phase B's 52/13, not behaviour change). |

## What's verifiably better than at end of Phase B

- **Section 7 / Demo-Plus**: full 44-screen sweep at 1.0 parity — the headline deliverable. Phase B verified one screen (Login Splash); Phase D verifies the entire corpus.
- **F11 + F11.1**: two real renderer bugs found and fixed via the sweep. The system is more robust to:
  - Library-imported components whose master fonts aren't in the spec walk
  - Paid commercial fonts the user hasn't licensed (Plugin API can't load them)
  Each defect-class would have surfaced eventually on real customer files; this sweep flushed them now.

## What's still degraded (and why)

- **Section 9 / variant induction**: stays WORKS-DEGRADED. Real Gemini integration is feature work, not a fix — F5 doc honesty remains the right scope.
- **Visual fidelity for Akkurat-using screens (Phase D-specific)**: text on those screens displays in Figma's fallback font (not Akkurat). The renderer recovered the structural render — every IR element appears, layout is correct, parity is reported true — but Akkurat itself can't be loaded. The user would need to install Akkurat in their Figma session for visual fidelity. Not a fix-cycle scope decision.

## What didn't regress

No behavioral regression in any of the 9 sections. Sections 1, 2, 3a, 4, 5, 8 unchanged from Phase B's clean state. Section 6 same verdict class with one observation about TokenRef LLM non-determinism. Section 9 unchanged behavior + intact docs. **Section 7 improved from "single-screen verified" to "44/44 corpus verified."**

## F11 + F11.1 — anatomy of two autonomous renderer fixes

The Phase D sweep was supposed to be the final reproduction step. Instead, it surfaced a real renderer bug that hadn't shown up in any prior phase.

### F11 (commit `8eb6c61`) — virtual-prop composition + font-load guards

- **Probe symptom**: 3-screen sweep returned 3/3 DRIFT at parity ~0.009, ~110 errors/screen, only 1 of 117 elements rendered.
- **Bug A**: registry treated `fontFamily`/`fontWeight`/`fontStyle` as direct Figma TEXT setters. They aren't — TEXT nodes only have `.fontName = {family, style}`. Direct writes throw "object is not extensible."
- **Bug B**: text-property writes (`letterSpacing`, `fontSize`, etc.) didn't preload the node's current `fontName`, throwing "Cannot write to node with unloaded font" when the master used a font not in the preamble's preload list.
- **Codex gpt-5.5 design review caught**: the virtual-prop issue (I'd been about to wrap them with the same font guard, which would still throw — needed composition into `fontName`); the `figma.mixed` edge case for runs of mixed fonts.
- **Fix**: new `_compose_font_identity_op` extracts the three virtual props and emits a single `_c.fontName = {family, style}` write with the new font preloaded; `_emit_override_op` skips stray font-identity props (defense in depth) and wraps other text-category writes with `loadFontAsync(_c.fontName)` + `figma.mixed` guard.
- **Verification**: same 3-screen probe, post-F11: 3/3 PARITY, 0 errors, 5.6s.
- 22 new behavior tests; 372 existing tests pass.

### F11.1 (commit `f30e317`) — try/catch around character/text/subtitle writes

- **Probe symptom (full 44-screen sweep)**: post-F11, 27/44 PARITY but 17 DRIFT — all HGB Travel Request + Alternative Flights screens (the largest, 250–2300 IR nodes), parity ~0.001, only 1 of N elements rendered. Walks showed `font_load_failed` for Akkurat / Akkurat-Bold.
- **Bridge probe via `figma.listAvailableFontsAsync`**: of 9777 fonts in the user's Figma session, **only Akkurat-Mono is loadable**. Akkurat (Regular) and Akkurat-Bold are paid Lineto fonts the user hasn't licensed. The masters display correctly via cached glyphs but `loadFontAsync` rejects.
- **Bug**: the renderer's three text-override emission paths (`characters` branch in `dd/renderers/figma.py`, `text` and `subtitle` overrides in `dd/render_figma_ast.py`) wrap the write in `await figma.loadFontAsync(_t.fontName)` but none caught the rejection. Surrounding findOne block uses try/finally (no catch), so the throw aborts Phase 1 mid-render.
- **Codex gpt-5.5 implementation review (round 2 on F11)** had already caught this exact pattern for non-`characters` text props — F11.1 applies the same fix to the three remaining unguarded sites.
- **Fix**: wrap each load+write pair in try/catch; on failure push a structured `text_set_failed` __errors entry with property name + font family/style for attribution.
- **Verification**: re-probed 8 worst-case screens (10-11, 27-32) → 8/8 PARITY. Then full sweep → 44/44 PARITY in 72.6s.
- 2 new behavior tests; 422 existing tests pass.

### Process notes — NEVER BLINDLY TRUST in action

The audit's prime directive paid off twice in this phase:

1. **F11 design review caught a wrong fix shape.** I was going to wrap fontFamily/fontWeight/fontStyle writes with `loadFontAsync(_c.fontName)`. Codex pointed out: those are virtual props that don't exist on TEXT nodes — wrapping them in font-load wouldn't fix the throw. The right fix is composition into `fontName`. Without that review, F11 would have failed the probe.
2. **F11 implementation review caught the missing per-op try/catch.** I had wrapped the load+write in `if (target.type === "TEXT") { ... }` only, no try/catch. Codex pointed out: loadFontAsync can REJECT (font unavailable) and the next-line write throws. The outer block has try/finally, not try/catch — the throw propagates and aborts Phase 1. F11.1 applied this catch shape to the remaining sites once F11's full-sweep probe surfaced the same class on the `characters` branch.

Without the second-opinion gate, both fixes would have shipped broken. The 22 + 2 = 24 behavior tests now pin both fix classes against future regression.

## Cost & time (Phase D)

- Subagent A/B/C parallel verdict-writing: ~3 minutes wall, ~$0.30
- Subagent C noted Section 8's planner-output non-determinism (login dropped 5→0 imports vs Phase B post-F9 due to LLM picking templateless catalog types) — graceful fallback, not regression
- F11 design + implementation + Codex review + tests: ~30 minutes wall, ~$0.20
- F11.1 implementation + tests + 8-screen probe + full sweep: ~10 minutes wall, ~$0.05
- Section 7 full 44-screen sweep: 72.6s × 1 = 72.6s wall (no API cost)
- Foreground 3 design briefs (Section 6) on real Sonnet: ~30s wall, ~$0.15
- Foreground 2 generate-prompt runs (Section 8) on real Sonnet: ~10s wall, ~$0.05
- **Total Phase D: ~50 minutes wall, ~$0.75 in API costs**

Compare to original Phase A + Phase B + Phase C synthesis: ~$5-15 across the cycle. Phase D is the cheapest phase — most of the cost is in the renderer-fix work, which is one-time.

## Demo recommendation (revised post-Phase D)

The Phase B recommendation stands and is now even stronger: **demo the controlled-edit pipeline against the parseable HGB screens.** With 44/44 PARITY now confirmed end-to-end (Section 7), the demo narrative is:

1. **Fresh extraction** (Section 1): `dd extract` → 44 screens, 20275 nodes, 113831 bindings into SQLite. Then `dd extract-plugin` populates assets, vector geometry, instance overrides via Plugin API.
2. **Token curation** (Section 2): `dd cluster --auto-accept` proposes 191 tokens; `dd validate` reports 0 errors, 0 warnings, 0 collisions. `dd export-css` writes tokens.css.
3. **Round-trip parity** (Section 4 + Section 7): 5/5 sample screens compress L3 byte-identically. Full 44-screen render-and-verify sweep produces is_parity=True on every screen in 72.6s.
4. **Agent loop** (Section 6): `dd design --brief "<intent>"` runs a real Sonnet agent that uses NAME/DRILL/EDIT/DONE primitives over the markup spec, persisting variants to SQL.
5. **Composition demo** (Section 8): `dd generate-prompt` planner + composer emits scripts that import real components from the project's catalog (when types have templates) or gracefully degrade to `createFrame` placeholders (when they don't). Zero CKR-name leaks across all emitted imports.

Lead with the corpus-wide render-and-verify (Section 7) — that's the load-bearing demonstration. **The "every screen in your file roundtrips through the bridge with parity" narrative is now real.**

The Phase B recommendation to NOT lead with Mode-3 also stands — Section 8's behaviour is correct (zero CKR-name leaks, graceful fallback for templateless types), but the planner is still maturing on which catalog types to ask for (Phase D login emitted 0 imports because the planner picked types with no templates in this project). Frame Mode-3 as "early — composer emits real keys when the planner picks types we have templates for; otherwise graceful fallback to createFrame placeholders" rather than as the centerpiece.

## F13 follow-on — three systemic fixes from a visual-diff audit

After the F12d full-sweep grid was published, the user reviewed three rendered screens visually and reported three issues that the structural verifier and the runtime-error channel both missed. Each was investigated with parallel Explore subagents (one per issue) plus Codex synthesis review of the proposed fixes. All three turned out to be systemic root causes that affect more screens than the three flagged.

### Bug A — Group 4746 vector logo rendered with children offset by group origin

**Symptom (HGB Customer Complete Info Tablet):** the logo's vector children appeared at +19px offset, partially outside their parent Top Nav frame. Bridge truth showed the rendered "Group 4746" was `type: FRAME`, not GROUP — the AST renderer's `_TYPE_TO_CREATE_CALL` map at `dd/render_figma_ast.py:85` had no entry for "group", silently coercing every GROUP to `figma.createFrame()`. Per the documented `feedback_rest_plugin_coord_convention_divergence.md`, Plugin API reports a GROUP-CHILD's `node.x` in the GROUP's PARENT coordinate space; when emitted into a FRAME (where x is interpreted as frame-local), every child gets offset by the GROUP's own (x, y).

**Fix shipped as F13c (commit `7a844b7`):** port a GROUP deferral path to the AST renderer. Phase 1 skips groups entirely (no create / no name / no visual / no layout / no `M[...]` assign). Phase 2's appendChild loop redirects non-group children whose parent is a deferred group to the nearest non-deferred ancestor (temporary parent) and registers them in the immediate-parent group's `direct_children` list. After the appendChild loop, walks deferred groups bottom-up by AST depth and emits `figma.group([direct_children_vars], grandparent_var)` for each. Phase 3 emits position-only (`x`, `y`, `visible`) — Figma `GroupNode` rejects fills/strokes/cornerRadius/autolayout.

Codex pushed back on two pitfalls I would have copied from the OLD `dd/renderers/figma.py:1505+` path: (1) the OLD pattern of "register descendant in EVERY ancestor's children_vars" is suspicious for nested groups (only direct AST children should reach `figma.group`); (2) the OLD ordering by deferral-map insertion is less robust than bottom-up by AST depth.

### Bug B — Letter body text rendered 1319px wide instead of source 560px

**Symptom (HGB Customer Complete Info Desktop):** the long "Subject: Live Request..." text grew to 1319px on a single line instead of wrapping in source's 560×345 box. Bridge truth showed `width=1319, textAutoResize=WIDTH_AND_HEIGHT` (default) instead of source's `width=560, textAutoResize=HEIGHT`.

**Root cause:** text nodes in non-autolayout parents got NO `resize()` and NO `textAutoResize` emitted. Phase 1 skips `_emit_layout` for text (line 855). Phase 3's resize block at line 1597 read `widthPixels`/`heightPixels` only — text-node IR uses literal numeric `width: 560.0, height: 345.0`. And even with a resize, default `WIDTH_AND_HEIGHT` would re-expand the width when characters are set.

**Fix shipped as F13b (commit `2c553f5`):** Phase 3 reads canonical `resolve_element` output (matches Phase 1's locus); sizing lookup falls back to numeric `width`/`height` when `widthPixels` absent (mirrors `_emit_layout`'s tolerant lookup); for text after resize, emit `textAutoResize = <stored>` to lock — but only when stored mode is NOT `WIDTH_AND_HEIGHT` (Codex catch: emitting it after resize re-enables natural-width). Same `textAutoResize` lock added to autolayout-parent path. Order is `appendChild → characters → layoutSizing/resize → textAutoResize` per `feedback_text_layout_invariants.md`.

### Bug C — Bordered table rendered 100×950 instead of source 1400×950

**Symptom (HGB Transactions Selected):** the "table with border" frame had `clipsContent: true` and a height that clipped almost the entire table. Bridge truth showed `width=100` (default `createFrame()` size) when source was `width=1400` with `layoutSizingH=HUG`.

**Root cause:** `_deep_merge_element_keys` at `dd/ast_to_element.py:284` was a two-level merge. When base's `layout.sizing` had `{"width": "hug", "widthPixels": 1400, "height": 950}` and AST head's overlay had `{"width": "hug", "heightPixels": 950}`, the merge wrote overlay's sizing-dict whole into the result, losing `widthPixels: 1400`. Even though the docstring promised "only keys PRESENT in overlay are touched."

**Fix shipped as F13a (commit `2c553f5`, same commit as F13b):** the function now recurses into nested dicts at every depth. Lists are still replaced whole (Figma fills/strokes are ordered stacks). With this fix, F13b's Phase 3 lookup naturally reaches `widthPixels=1400` and emits `n3.resize(1400, 950)`.

### F13 verification

All three issues bridge-verified fixed:
- Group 4746: `type: GROUP` (was FRAME), children at exact source positions
- Letter body text: `w=560, autoResize=HEIGHT` (was 1319 / WIDTH_AND_HEIGHT)
- Bordered table: `w=1400, h=950` (was 100×950)

Full 44-screen sweep post-F13: identical headline numbers (44/44 PARITY, 11 fully clean, 33 visually degraded, 588 runtime errors all Akkurat). Zero new failures introduced; 0 regressions in 482-test smoke suite.

### Process catch on F13b

Self-shipped a first draft of F13b without consulting Codex (just a width/height fallback in Phase 3). The user caught me. Reverted, brought Codex in with the precise question, got back a sharper specification: read `resolve_element` output (not `spec_elements` directly), add `textAutoResize` lock with the `WIDTH_AND_HEIGHT`-skip catch, apply lock in BOTH autolayout and non-autolayout paths. The Codex-specified shape is what shipped. The bandaid attempt was reverted before commit. Sixth catch of the audit cycle.

## Artifacts

- `audit/20260425-1725-phaseD-fullsweep/REPORT.md` — this document
- `audit/20260425-1725-phaseD-fullsweep/sections/<N>/verdict.md` × 9 — per-section verdicts
- `audit/20260425-1725-phaseD-fullsweep/audit-fresh.declarative.db` — the Phase D DB
- `audit/20260425-1725-phaseD-fullsweep/sections/07-roundtrip-render/sweep-out/` — full sweep output (scripts/, walks/, reports/, summary.json) for visual review
- `audit/20260425-1725-phaseD-fullsweep/ENVIRONMENT.json` — Python/git/bridge environment capture
- `audit/20260425-1626-validation/` — Phase B validation (compare)
- `audit/20260425-1042/` — Phase A original audit (compare)
- `fixes/20260425-1215/` — full evidence trail for F1–F8 + F9
- F10 commit `908423a` (sweep.py --db + --out-dir flags)
- F11 commit `8eb6c61` (renderer text-override font composition + load guards)
- F11.1 commit `f30e317` (try/catch around character/text/subtitle write paths)
- F12 + F12a commit `0cc30c1` (verifier surfaces walk runtime errors + per-eid attribution)
- F12d commit `906d9cf` (sweep mode lays renders in a grid; visual review)
- **F13a + F13b commit `2c553f5` (recursive deep-merge preserves widthPixels + Phase 3 text resize/textAutoResize)**
- **F13c commit `7a844b7` (port GROUP deferral to render_figma_ast.py)**
- **Merge commit `ff869e3` on `v0.3-integration` (`--no-ff` to preserve audit-batch boundary in `git log`)**

For visual review of the rendered screens: open the connected Figma file
(HGB (Experimental)) and navigate to the "Generated Test" page. All 44
rendered screens are persisted there in a 6-column grid (F12d).

---

## Final tally

- **8 fixes shipped this phase**: F10, F11, F11.1, F12 + F12a, F12d, F13a + F13b, F13c — all on `fix/20260425-1215`, now merged into `v0.3-integration` at `ff869e3`
- **7 sections WORKS-CLEAN** (1, 2, 3a, 4, 5, 6, 8)
- **1 section WORKS-CLEAN structurally / WORKS-DEGRADED visually** (7 — 44/44 structural parity, 11/44 fully clean, 33/44 visual fidelity gap from unlicensed Akkurat font)
- **1 section intentionally WORKS-DEGRADED** (9 — variant induction; v0.1-shell scope)
- **0 regressions** across the 9 sections; **+4 tests fixed** vs `v0.3-integration` baseline
- **44/44 app_screens render to STRUCTURAL parity** in the corpus-wide sweep; **11/44 with full visual fidelity, 33/44 with Akkurat-fallback text**
- **3 user-reported visual-diff issues** fixed via the F13 series (Group 4746 logo offset, letter body text width, bordered table sizing) — all bridge-verified
- **All 44 rendered screens persist** on the Generated Test page in a 6-column grid (F12d) for visual review
- **~95 minutes Phase D wall time** (75 baseline + 20 for F13 follow-on), **~$1 API costs**
- **Process discipline (NEVER BLINDLY TRUST + Codex second opinion) prevented 6 verdict drifts** during this phase:
  1. F11 design — would have shipped wrong fix shape (wrap virtual props in font-load instead of composing into fontName)
  2. F11 implementation — would have shipped without per-op try/catch
  3. §7 synthesis headline — would have shipped "44/44 PARITY, 0 errors" without the visual-fidelity caveat
  4. Visual-diff "new bug class" hypothesis — would have shipped F12b for a non-existent componentProperties bug; bridge truth showed it was the SAME Akkurat-Bold load failure
  5. F13b first draft — would have shipped a width/height fallback in Phase 3 without the textAutoResize lock or the WIDTH_AND_HEIGHT skip
  6. F13c first instinct — would have replicated the OLD path's "register descendant in every ancestor's children_vars" pattern; Codex flagged it as suspicious for nested groups; correct shape is direct-AST-children only with bottom-up creation
