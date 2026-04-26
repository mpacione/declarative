# Section 08-mode3-composition — verdict (Phase D)

**Verdict:** WORKS-CLEAN (F9 contract holds: zero CKR-name leaks)

## Summary
Section 8 (`dd generate-prompt`) — WORKS-CLEAN, both prompts exit 0. **F9's "100% real keys" contract is intact**: every `importComponentByKeyAsync` argument that *was* emitted is a real 40-char hex CKR key. No CKR-name strings (e.g. `"buttons/button"`, `"cards/_default"`) leaked through. Numbers differ from Phase B post-F9 due to LLM planner non-determinism on which catalog types it asks the renderer to instantiate.

| Prompt | Phase B post-F9 imports | Phase D imports | Real keys (Phase D) |
|---|---|---|---|
| login | 5 | **0** | n/a — planner picked types (`header`, `card`, `text_input` ×2) for which no template exists in this project; renderer warned "will render as empty frame" 4× and emitted `createFrame()` instead of an `importComponentByKeyAsync` call |
| travel-card | 2 | 2 | 2/2 (`391336b2...` = `cards/_default`, `020745936f...` = `buttons/button with icon`) — both verified against `component_key_registry` |

**Critical verification (per project NEVER-BLINDLY-TRUST rule)**: ran `grep -oE 'importComponentByKeyAsync\("[^"]*"'` then matched each arg against `^[0-9a-f]{40}$`:
- login: 0 imports → 0 hex / 0 non-hex (vacuously clean)
- travel-card: 2 imports → 2 hex / 0 non-hex
- **Both args verified by DB join against `component_key_registry`: real components, real names, instance_count > 0.**

The drop from 5→0 imports on login is *not* a fix-cycle regression — F9's `_resolve_component_keys` is wired in (`dd/compose.py:1643`). The login planner this run chose 4 catalog types that have *no* templates in the corpus (`header`, `card`, `text_input` × 2) so the renderer printed warnings and used `createFrame` fallbacks rather than emitting any import call. This is the documented graceful-degradation path for missing templates, not the CKR-name-leak failure mode that F9 was authored to fix.

## Evidence
- `audit/20260425-1725-phaseD-fullsweep/sections/08-mode3-composition/generated-login.js` (29,910 bytes): 0 `importComponentByKeyAsync`; 8 `createFrame`; 8 `createText`; 0 `_missingComponentPlaceholder`
- `audit/20260425-1725-phaseD-fullsweep/sections/08-mode3-composition/generated-travel-card.js` (19,218 bytes): 2 `importComponentByKeyAsync`; 7 `createFrame`; 2 `createText`; 3 `createInstance`; 3 `_missingComponentPlaceholder` (for `card` type with no template — graceful fallback)
- DB verification:
  ```
  391336b2e1afd205352e135f6443ce9633f222b7 → cards/_default (instance_count=178)
  020745936fc42eaa558d98f7102bd44aea59c843 → buttons/button with icon (instance_count=33)
  ```
- `generate-prompt-login.stderr.txt`: `Warning: Type 'header'/'card'/'text_input'×2 has no template in this project — will render as empty frame`
- F9 source still wired: `code-graph-mcp grep "_resolve_component_keys" dd/` shows `dd/compose.py:76` (def) + `dd/compose.py:1643` (call site).
