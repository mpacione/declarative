# Experiment E — Principles induction via Gemini 3.1 Pro

**Question:** Can Gemini 3.1 Pro look at a stratified sample of screenshots from a design system and produce usable first-draft content for the four TODO sections in `design.md` — Voice, Intent conventions, Exclusions, Style lineage?

**Short answer:** Yes, substantially usable with light editing. One prompt, one call, 21 seconds, ~8 cents. Output cites specific visual evidence and is on-point. A designer would trim rather than rewrite.

## 1. Sampling strategy

25 screens drawn from 204 `app_screen` rows in `Dank-EXP-02.declarative.db`, stratified on three axes: form factor (9 iPhone, 8 iPad 11", 8 iPad 12.9" — keeps responsive behaviour in evidence), complexity (per-form-factor tertile split on `n_nodes`, range 249–614), and distinctive features (≥1 keyboard-bearing screen per form factor — only 5 such in the whole corpus — and a mix of checkbox-bearing list/pickers vs non, 11:14).

Screen names are generic ("iPhone 13 Pro Max - 109"), so content-type stratification was driven by which CKR instances each screen contained. The captured sample ended up covering: workshop/home, several modal sheets (Add Image, Characters, Border, Text Size), canvas-editor views with object selection, list pickers, keyboard visible, and responsive variants on each tablet form factor.

## 2. Model observations

**Hallucination check:** I verified each concrete claim against the screenshots. All six load-bearing observations confirm on the evidence: chartreuse-active-state (Workshop nav 180, Medium chip 233, Upload card 195), white pill floating toolbars with soft drop shadows (219, 233, 239), black pill Cancel buttons (195, 324, 295), blue bounding-box object selection (239, 241, 219), no-dark-mode (all 25), pill border radii throughout.

**One minor inaccuracy:** the claim "No serif or decorative typography" slightly understates reality — the DANK wordmark is a chunky/slanted display type that's part of the system vocabulary. Body UI typography is indeed neutral sans, but the wordmark is expressive. A designer would reword this bullet.

**No fabricated claims.** Nothing referenced content the screenshots don't show. No external brand knowledge leaked in — the word "Dank" is plastered across the nav yet never named in the output; Gemini treated it as a visual artefact.

**Most surprising inference:** the Voice section's observation that "UI typography remains strictly neutral and minimal, deliberately stepping back to let the chaotic, highly saturated user-generated meme content take center stage" — that's a design-*intent* inference from observing the figure-ground relationship between chrome and canvas, not a description of a visible feature. It got the "why", not just the "what".

**Evidence grounding:** strong. Each intent convention is anchored in an observable pattern, and the model hedges ("observed", "typically") leaving room for designer override.

## 3. Honest assessment

**Usable-with-editing.** Roughly 80-90% of the text would survive unchanged after designer review; one bullet (serif claim) needs rework, and a designer would layer in system-knowledge that isn't purely visual — brand history, evolution plans, the fact that chartreuse is the specific CTA accent etc. Without that layer the output is still a competent first draft, the kind a designer writes in 20 minutes but can now get in 20 seconds.

It is **not** better than what a designer would write — intent, history, and forward direction are inaccessible to a VLM. But the memo-style description of what is visually on-screen is solid. The generate-then-edit framing holds.

## 4. Cost

- **Input tokens:** 28,096 (26,854 image + 1,242 text; 25 images at ~1024px).
- **Output tokens:** 375 response + 1,558 thinking (Gemini 3 bills thinking as output).
- **Wall-clock:** 20.9 s for the Gemini call. Capture (bridge) + resize (PIL) added ~24 s. Under 3 min of compute end-to-end.
- **API spend:** $0.079 at Gemini 3.1 Pro Preview Paid rates ($2.00 / M input, $12.00 / M output incl. thinking). Cheap relative to designer time saved; even a 500-screen corpus would cost under $1.

## 5. Recommendation for v0.1

**Ship auto-induction behind a flag.** Add `--induce-principles` to `dd design-md generate`. When on, the CLI:

1. Selects a stratified ~20-screen sample using the axes from this experiment.
2. Captures each via the existing bridge (Node helper already written here).
3. Calls Gemini 3.1 Pro with `experiments/E-principles-induction/prompt.txt`.
4. Inserts the four sections into the generated `design.md` clearly marked `(auto-induced v1 — please review)` so no designer mistakes it for their own writing.

Opt-in to start. Do **not** default-enable until we've run the same experiment on 2-3 more design systems and confirmed quality holds outside Dank — the risk isn't hallucination but that Dank is a *legible* system (saturated accent, strong B&W contrast). A monochrome minimalist enterprise app may produce weaker induction.

**Not a separate command.** Principles induction belongs inside `design-md generate` because voice may reference colours the token palette section lists; splitting the pipeline creates version drift between the data-driven and voice-driven halves.

## 6. What NOT to attempt

The vision model should not be trusted to draft:

- **Accessibility conventions.** Visual presence ≠ a11y policy. `a11y` stays human-authored.
- **Tone-of-voice copy rules.** Visual voice ≠ copywriting voice. No "use present tense" from screenshots.
- **Motion / transition principles.** Static images can't reveal motion; any animation claim would be fabrication.
- **Token semantics / naming.** It may call a colour "a primary accent" but not name it `color.brand.primary` vs `color.accent.energy`.
- **Cross-screen narrative / flow.** Surface variety, not flow logic. Information design is out of scope.

## Files

`sample.csv`, `sample.py` (selection), `screenshots/<id>-<slug>.png` (1× bridge capture, resized to 1024px longest), `capture.js`, `capture_all.py`, `resize_all.py`, `prompt.txt`, `run_gemini.py`, `outputs/raw-response.json`, `outputs/voice.md` / `intent-conventions.md` / `exclusions.md` / `lineage.md` (per-section), `outputs/merged-draft.md` (drop-in block), `activity.log`.
