# Section 03a-classify-heuristic — verdict (Phase D)

**Verdict:** WORKS-CLEAN

## Summary
Section 3a (heuristic classify) — WORKS-CLEAN, unchanged from Phase B. `dd seed-catalog` populates 82 component types in `component_type_catalog`; `dd classify` writes 9378 rows into `screen_component_instances` (56 formal / 9322 heuristic) across 44 screens in 458 ms. Stdout footer matches DB ground-truth (formal 56, heuristic 9322, parent links 6797, skeletons 44). No F-fix touched this stage and the numbers are stable across the full Phase D sweep.

## Evidence
- audit/20260425-1725-phaseD-fullsweep/sections/03a-classify-heuristic/dd-seed-catalog.* — exit 0, "Seeded 82 component types into catalog."
- audit/20260425-1725-phaseD-fullsweep/sections/03a-classify-heuristic/dd-classify-heuristic.* — exit 0, 458 ms, 44/44 screens
- DB query on `audit-fresh.declarative.db`:
  - `SELECT classification_source, COUNT(*) FROM screen_component_instances GROUP BY classification_source`:
    - `('heuristic', 9322)`
    - `('formal', 56)`
  - `SELECT COUNT(*) FROM component_type_catalog` -> 82
  - `SELECT COUNT(DISTINCT screen_id) FROM screen_component_instances` -> 44
- Note: actual column is `classification_source`, not `classification_method` as cited in the request — verified via `PRAGMA table_info`.
