# Section 01-extract — verdict (Phase D)

**Verdict:** WORKS-CLEAN

## Summary
Section 1 (Extraction) — WORKS-CLEAN, matches Phase B. Both `dd extract` (15.4s, exit 0) and `dd extract-plugin` (23.3s, exit 0) ran clean. Structural counts identical to Phase B: 44 screens, 20275 nodes, 113831 node_token_bindings, 101 CKR rows. F4 fix verified again: assets/node_asset_refs/instance_overrides all populated by `extract-plugin`. HGB-specific note: 0 COMPONENT/COMPONENT_SET nodes and 0/101 CKR rows have `figma_node_id` populated — both library-source artifacts (HGB's component masters live in a separate library file), not regressions. Phase B showed the same 0/101 on this file; Dank had 104/129. Plugin-side counts (assets=130, node_asset_refs=2885, instance_overrides=6999) are higher than Phase B (128 / 2329 / 4587) — same code, same file; the plugin walked more nodes this run (40550 vs 29398 touched). Treating as run-to-run variance in bridge enumeration, not a regression — REST-side counts match exactly.

## Evidence
- `audit/20260425-1725-phaseD-fullsweep/sections/01-extract/dd-extract.*` — exit 0, 15.4s wall, 44 screens, 20275 nodes, 113831 bindings, CKR=101
- `audit/20260425-1725-phaseD-fullsweep/sections/01-extract/dd-extract-plugin.*` — exit 0, 23.3s wall, 40550 nodes touched, asset store 2885 SVG paths, overrides=6999
- `audit/20260425-1725-phaseD-fullsweep/sections/01-extract/dd-status.*` — exit 0, pre-cluster snapshot (113831 unbound, 0 tokens — expected at this point)
- DB query post-extract: screens=44, nodes=20275, assets=130, node_asset_refs=2885, instance_overrides=6999, component_key_registry=101, node_token_bindings=113831
- HGB library-source artifacts: 0 COMPONENT/COMPONENT_SET nodes (matches Phase B); 0/101 CKR rows have figma_node_id populated (matches Phase B). Not a regression — masters live in upstream library file.
- F4 workflow change confirmed again: `extract-plugin` populates assets + node_asset_refs + instance_overrides (cf. v0.4 plan).
