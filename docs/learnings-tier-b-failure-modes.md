# Tier B — Mode-3 failure-mode inventory

**Date**: 2026-04-21 (Tier B of `docs/plan-burndown.md`).
**Method**: `scripts/tier_b_demo.py` run on three component-scale
prompts against the live Figma plugin bridge on Dank. Bridge walk
produced `errors[]` arrays and partial `eid_map` coverage that
pinned each failure.

This is the SCOPING INPUT for Tier C's VLM fidelity scorer. The
scorer should test for *these specific failure modes*, not a
generic 5-dim rubric in the dark.

---

## Prompts run

| # | Prompt | IR elements | Rendered eids | Bridge errors |
|---|---|---|---|---|
| 1 | `a primary CTA button labeled 'Sign up'` | 2 | 2 | 2 |
| 2 | `a card with a heading 'Pricing', a description paragraph, and a primary action button` | 5 | 5 | 2 |
| 3 | `a settings row with a label, a description, and a toggle switch on the right` | 7 | **3** | 1 |

## Failure modes observed

### F1 — `text_set_failed` on `Inter Semi Bold`

**Seen on**: prompts 1, 2.

**Symptom**: the render script emits `n17.fontName = {family:"Inter",
style:"Semi Bold"}` but the preamble's `figma.loadFontAsync` manifest
never requests "Inter Semi Bold". Plugin rejects the fontName set on
a font that isn't preloaded.

```
in set_fontName: Cannot use unloaded font "Inter Semi Bold".
Please call figma.loadFontAsync({ family: "Inter", style: "Semi Bold" })
and await the returned promise first.
```

**Likely root cause**: `dd/renderers/figma.py::collect_fonts` builds
the font manifest from `spec["elements"][*].style.typography` — BUT
Mode-3 synthesises children with typography inherited from the
parent template *during compose*, so by the time `collect_fonts`
runs, typography refs on children may not have been fully expanded.
The render-time `typography` write then hits a font the preamble
didn't preload.

**Remediation candidates**:
- Make `collect_fonts` walk the template output, not just
  `spec.elements` — resolve every `typography` ref transitively.
- OR: preload the full Dank typography set (5-10 font styles) in
  the preamble unconditionally — heavy but robust.
- OR: emit `loadFontAsync` just-in-time before the font-using
  node's `fontName` setter.

**Tier C scorer test**: after render, grep the script's `__errors`
array for `kind: "text_set_failed"` + font name. Score ≤3/10 if
present on any node.

---

### F2 — `appendChild into instance` throws

**Seen on**: all 3 prompts. The single biggest failure class.

**Symptom**: when Mode-3 creates a CompRef node (e.g. `button-1`
resolves via Mode-1 to an INSTANCE), and the LLM tree has a TEXT
child hanging off that INSTANCE, the emitted script calls
`instance.appendChild(textNode)` which Figma's Plugin API rejects.

```
in appendChild: Cannot move node. New parent is an instance or is
inside of an instance
```

**Root cause**: this is a fundamental Figma constraint — an
INSTANCE's internal structure is defined by its main component and
cannot be mutated via `appendChild`. The LLM's "button with a text
child" mental model conflicts with Mode-1's "button IS a library
instance whose text is set via `characters = "..."`, not via a child
node."

**Related to `feedback_leaf_parent_appendchild.md`**: that memory
notes leaf types (TEXT, LINE) can't host children. This case is
similar but at a different layer — INSTANCEs also can't host
children.

**Remediation candidates**:
- Compose: when the LLM emits a CompRef parent with TEXT children,
  hoist those children to be siblings of the CompRef (or drop
  them), AND populate the CompRef's `props.text` with the
  hoisted-out content.
- Render: gate `appendChild` emission on `!isInstance(parent)` —
  soft-skip with a diagnostic (same shape as the leaf-parent gate).
- LLM prompt: add a system-level rule in `parse_prompt`:
  "Components resolved from the library cannot host children;
  express customisation via `props.text` / `props.icon` / slot
  overrides."

**Tier C scorer test**: after render, grep `__errors` for
`kind: "render_thrown"` + `"appendChild"`. Score ≤2/10 — F2 is a
hard failure.

---

### F3 — Cascading Phase-2 abort

**Seen on**: prompt 3 severely (only 3/7 elements rendered);
prompts 1-2 less severely (all rendered but with errors).

**Symptom**: when F2 hits in Phase 2 (`appendChild into instance`),
the outer `try/catch` around Phase 2 catches the exception and
pushes it to `__errors` — but the remainder of Phase 2 is NEVER
executed. Every subsequent `appendChild` / `resize` / `characters`
set after the throwing line is silently lost.

**Root cause**: the Phase 2 wrapper is one big `try/catch`, not
per-op guards. Per [`feedback_explicit_state_harness.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_explicit_state_harness.md)'s
principle, one failure should NOT cascade across all subsequent
operations.

**Remediation candidates**:
- Wrap each `appendChild` / `resize` / `characters` in its own
  `try/catch` with a `kind` tag (similar to ADR-005's null-safe
  createInstance pattern). Already done for some ops (`n.resize` at
  the end of Phase 2 wraps each op); just extend coverage.
- Audit every destructive op in Phase 2/3 and ensure each has a
  per-op try/catch.

**Tier C scorer test**: `rendered_eids / ir_elements` ratio. If
< 0.8, score ≤4/10 (partial render).

---

### F4 — CompRef parent + child tree mismatch (structural)

**Seen on**: prompts 2, 3. Indirect consequence of F2 but a
separate design issue.

**Symptom**: the LLM reasonably models a composite component as
"button with heading + icon children" or "card with toggle child",
but the library's button / toggle resolve as Mode-1 INSTANCES which
can't host children. This is a MISMATCH between the LLM's mental
model and the component library's structure.

**Root cause**: no system prompt guidance on when a component is
a "leaf" (resolves as INSTANCE) vs when it's a "container" (resolves
as FRAME and can host children). The LLM has no way to know without
consulting the library catalog.

**Remediation candidates**:
- System prompt: inject the canonical_type → "leaf vs container"
  mapping as a precondition. E.g., `button`, `icon`, `switch`,
  `chip` are leaves; `card`, `list_item`, `toolbar`, `header` are
  containers.
- Validate LLM output: before compose, reject component lists
  where a leaf-type has children. Return as a clarification
  refusal; let the user rephrase.
- OR: hoist children to become siblings (as in F2 remediation)
  and populate props.

**Tier C scorer test**: structural — count elements where
canonical_type ∈ LEAF_TYPES and has children > 0.

---

### F5 — Inspection underreports typography + slot values

**Seen on**: `_inspect_spec` only enumerates `fill / stroke /
radius / shadow / padding / gap`. Real IRs also carry `typography`
(the F1 failure vector), `spacing`, `sizing`, and slot fills.

**Remediation**: extend `_inspect_spec` to walk typography +
spacing + sizing. Would have flagged F1 at IR level before the
render attempt.

---

## Deferred prompts

The failure rate on 3 component-scale prompts is enough signal for
Tier C scoping. Broader prompt coverage (screens, variant families,
multi-column layouts) waits for Tier D with the scorer in place.

---

## Tier C scorer dimensions derived from this inventory

| Dimension | What it measures | Scored on |
|---|---|---|
| **rendered coverage** | `len(rendered.eid_map) / len(ir.elements)` — did Phase 2 abort? | F3 |
| **font readiness** | `__errors` contains no `text_set_failed` kind | F1 |
| **component-child consistency** | `__errors` contains no `render_thrown` with "appendChild" + "instance" | F2 |
| **leaf-type child count** | IR elements where `canonical_type` ∈ LEAF_TYPES have ≤ 0 children | F4 |
| **(optional) VLM semantic** | Gemini rubric on the saved screenshot, scoped to rest | catch-all |

These are CONCRETE, CHECKABLE, and each maps to an observed failure
mode. They cost nothing at query time (just regex + dict count) and
don't require a VLM call until the last optional dimension. Tier C
should implement the first 4 as pure functions + wire the VLM
scorer for the 5th.
