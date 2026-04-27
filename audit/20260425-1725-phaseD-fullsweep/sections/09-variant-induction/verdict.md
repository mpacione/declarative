# Section 09-variant-induction — verdict (Phase D)

**Verdict:** WORKS-DEGRADED

## Summary
Section 9 (variant induction) — WORKS-DEGRADED, behaviour class unchanged from Phase B. `dd induce-variants` exits 0 in 157ms and writes **28 placeholder rows for 7 catalog types** (Phase B: 52 rows / 13 types). All confidences are 0.0; vlm_call still receives an empty image list; Gemini 3.1 Pro is not actually invoked. Same v0.1-shell behaviour as Phase B and the original audit.

The row-count delta vs Phase B is a **DB-state difference, not a regression**. `induce_variants` reads `SELECT DISTINCT canonical_type FROM screen_component_instances`. Phase D's DB has 7 distinct canonical types (`text` 7539, `container` 1396, `heading` 365, `image` 31, `bottom_nav` 22, `dialog` 14, `button` 11); Phase B's DB has 23 distinct canonical types. Both DBs are 44 screens / 20275 nodes / 82 catalog entries — the difference is in classification depth (`screen_component_instances` row diversity), not extraction surface.

## F5 honesty signal verified from source

Phase D evidence does not include a `dd-induce-variants-help.txt` capture (only the main run was captured this phase). Verified directly from the live CLI: `.venv/bin/python -m dd induce-variants --help` returns the F5-applied honest text:

> "Current behaviour: every catalog type is treated as a single cluster and the injected vlm_call is invoked with an EMPTY image list — no rendered thumbnails are plumbed in v0.1. ... Gemini 3.1 Pro is NOT actually called; the typical 100-200ms runtime is too short for a network round-trip."

The previously-misleading "calls Gemini 3.1 Pro" claim is absent. F5 doc-only fix is intact.

## Evidence
- `audit/20260425-1725-phaseD-fullsweep/sections/09-variant-induction/dd-induce-variants.exit-code.txt` → `0`
- `audit/20260425-1725-phaseD-fullsweep/sections/09-variant-induction/dd-induce-variants.wall-time-ms.txt` → `157`
- `audit/20260425-1725-phaseD-fullsweep/sections/09-variant-induction/dd-induce-variants.stdout.txt`: `Total: 28 rows written.` over 7 catalog types
- DB cross-check: `audit-fresh.declarative.db` → `variant_token_binding` count = 28; `screen_component_instances` distinct `canonical_type` = 7
- `dd/cluster_variants.py:166-214` (`induce_variants`) and `--help` text confirm v0.1-shell scope (F5 wording present)
