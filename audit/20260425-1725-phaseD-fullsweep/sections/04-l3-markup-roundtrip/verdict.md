# Section 04-l3-markup-roundtrip — verdict (Phase D)

**Verdict:** WORKS-CLEAN

## Summary
Section 4 (L3 markup parser/serializer) — WORKS-CLEAN, parity with Phase B's post-fix state. All 5/5 sample screens (22 / 35 / 41 / 17 / 27) round-trip byte-identically through compress passes 1 and 2. Sample diff `screen_22.markup1.dd` vs `screen_22.markup2.dd` produces 0 lines; same is true for all other four pairs (verified individually). F2 + F3 + F7 fixes that flipped this section from BROKEN-CONTRACT to WORKS-CLEAN in Phase B continue to hold under the Phase D full sweep. Pytest status not re-measured per instructions; assume Phase B baseline of 4 fails (1 timeout artifact + 3 stale snapshots) unchanged.

## Evidence
- audit/20260425-1725-phaseD-fullsweep/sections/04-l3-markup-roundtrip/roundtrip-results.json: 5/5 OK, every entry has `"identical": true` with `pass1 == pass2` (1142 / 11612 / 5237 / 4308 / 30492 bytes respectively); elapsed 129–231 ms per screen
- audit/20260425-1725-phaseD-fullsweep/sections/04-l3-markup-roundtrip/screen_{17,22,27,35,41}.markup{1,2}.dd — sizes match across both passes for every screen
- `diff screen_22.markup1.dd screen_22.markup2.dd` -> 0 lines (verified)
- Diff loop across all five pairs: each yields 0 lines (`screen_17 / 22 / 27 / 35 / 41`)
- F2 (multi-line text on screens 35 + 41), F3 (numeric-segment paths + preamble), and F7 (collapsed canvas fill hoist) all still produce byte-identical idempotent markup on the canonical Phase B sample set
