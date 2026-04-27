# Plan — Type / Role Split

**Status**: Planned. Decisions locked 2026-04-22. Not yet started.
**Rollback tag**: `pre-type-role-split` (set at Stage 0 start).
**Cross-refs**: [plan-v0.3.md](plan-v0.3.md), [decisions/v0.3-grammar-modes.md](decisions/v0.3-grammar-modes.md), `feedback_leaf_parent_appendchild.md`, `feedback_dank_corpus_drift_25.md`.

## 1. Problem

Every IR element carries a single `type` field that today conflates two independent answers:

- **Structural primitive** — what Figma node to create (`FRAME` / `TEXT` / `RECTANGLE` / `GROUP` / `INSTANCE` / `LINE` / `ELLIPSE` / `VECTOR`). Deterministic; sourced from Figma's own `node_type`.
- **Semantic role** — what the element represents (heading, card, button_group, text, container). Probabilistic; sourced from the classifier ensemble (LLM + CS + PS + SoM).

The conflation is resolved in [dd/ir.py:292](../dd/ir.py#L292) as:

```python
return node.get("canonical_type") or node_type_raw.lower() or "frame"
```

Classifier opinion wins when both are present. This lets a FRAME (container, has children) be re-typed as `text` (leaf, can't have children) when the classifier labels its semantic role as text-like. The downstream renderer's leaf-parent gate ([dd/render_figma_ast.py:975](../dd/render_figma_ast.py#L975)) correctly refuses `text.appendChild(children)` (would crash at runtime) and emits `leaf_type_append_skipped`. Children are orphaned. Verifier reports `missing_child` drift.

**Scope observed 2026-04-21**: 148 screens with ≥1 container SCI-classified as a leaf type; 24 of 25 current round-trip drifts (96%) root-cause to this. Pre-classifier-v2 (before 2026-04-20) these miscodings did not exist; classifier-v2 introduced them by weight.

**Classifier-side caveat**: the classifier is not 100% accurate and never will be. Any design that assumes classifier correctness is fragile by construction. Fix must tolerate classifier error without depending on it being reduced.

## 2. Decision (locked)

Split the single `type` field into two:

- **`type`** — structural primitive from Figma source. **Always present.** Dispatch-safe. Comes from `node_type` lowercased (+ `GROUP` → `group` special case).
- **`role`** — semantic label from classifier. **Optional.** Emitted only when `role != type`. Sourced from `canonical_type`.

Grammar gains an **optional** `role=` attribute in the head. Markup examples:

```
@card-1(type=frame, role=card) { ... }        # classifier says card, primitive is frame
@heading-2(type=text, role=heading) { ... }   # role differs from type
@text-3(type=text) { ... }                    # role==type, attr elided
@frame-338(type=frame) { ... }                # no classifier opinion, no role attr
```

Prior art validated in research sweeps 2026-04-22:
- **Pattern name**: discriminator + role (compiler-IR family).
- **Canonical compiler analogue**: MLIR Type/Attribute split.
- **Canonical design-system analogue**: [Webstudio Instance schema](https://github.com/webstudio-is/webstudio/blob/main/packages/sdk/src/schema/instances.ts) — `{type (literal), component (semantic), tag (structural)}`.
- **Cautionary precedent**: MLIR D130092 (2022) ripped the universal `type` field off attributes because most didn't need it. Lesson: `role` is **optional** on a per-element basis.
- **Counter-cautionary**: ARIA-in-HTML has the split but both `role` and `tag` are author-editable, causing 70% more a11y errors. Inapplicable here: only `type` is author-sourced (extractor). `role` is classifier-generated.

## 3. Locked sub-decisions

1. **Role confidence threshold**: none. Emit `role=` always when `role != type`. Verifier catches misuse.
2. **Role storage**: add nullable `nodes.role` column. `screen_component_instances.canonical_type` remains the write-source-of-truth with provenance (confidence, reason, ensemble breakdown, review audit). `nodes.role` is the cheap-read column populated at classifier commit time. Requires migration + backfill (Stage 0).
3. **Eid naming**: re-canonicalize every build from scratch under the new rule `{role || type}-{counter}`, per-prefix counter pools. No preservation of old eids. Round-trip fixtures regenerate.
4. **Grammar spec location**: `docs/decisions/v0.3-grammar-modes.md` (canonical) + `dd/markup_l3.py` (implementation).
5. **Mode 3 LLM prompt**: updated in Stage 3b (same arc, not deferred).

## 4. Staged delivery

### Stage 0 — DB migration + backfill (`type-role-stage-0-complete`)

**Goal**: `nodes.role` column exists and is populated for all classified nodes.

**Work**:
- New migration `dd/migrations/021_add_nodes_role.sql` (or next sequential number — check `dd/migrations/`): adds `role TEXT` column, nullable, no default.
- Backfill statement: `UPDATE nodes SET role = (SELECT canonical_type FROM screen_component_instances WHERE screen_component_instances.node_id = nodes.id)` — run once after migration.
- Update `dd/classify_v2` commit path: after writing SCI, also write `nodes.role` (keeps them in sync going forward).
- Update `query_screen_for_ir` in [dd/ir.py](../dd/ir.py): add `n.role` to the SELECT list.

**Tests**:
- `test_migration_021_adds_role_column`
- `test_backfill_populates_role_from_sci`
- `test_classify_v2_writes_role_alongside_sci`
- `test_query_screen_for_ir_returns_role`

**Risk**: migration on a 245MB DB. Wrap in transaction. Backup tag before running.

**Acceptance**: all existing classified nodes have `nodes.role` matching their SCI canonical_type.

---

### Stage 1 — IR layer split (`type-role-stage-1-complete`)

**Goal**: `map_node_to_element` returns `{type: <primitive>, role: <optional>}` with the optional emission rule.

**Tests (failing first)**:
- `test_map_node_to_element_FRAME_classified_text_splits_type_role` → `{type: "frame", role: "text"}`
- `test_map_node_to_element_FRAME_no_role_omits_role_key` → `{type: "frame"}` (no `role`)
- `test_map_node_to_element_TEXT_role_matches_type_elides_role` → `{type: "text"}` (no `role`)
- `test_map_node_to_element_TEXT_role_heading_keeps_role` → `{type: "text", role: "heading"}`
- `test_map_node_to_element_GROUP_preserves_group_type` → `{type: "group", role: None|absent}`
- `test_resolve_element_type_no_longer_conflates` — deletes conflation fallback
- `test_single_source_resolve_element_type` — consolidates the duplicate in [dd/composition/providers/corpus_retrieval.py:391](../dd/composition/providers/corpus_retrieval.py#L391)

**Files**: [dd/ir.py](../dd/ir.py), [dd/composition/providers/corpus_retrieval.py](../dd/composition/providers/corpus_retrieval.py).

**Off-ramp**: ship Stage 0+1 alone. `role` lives in IR dict; no downstream consumer reads it yet. Not shippable value on its own but structurally unharmful.

---

### Stage 2 — Eid re-canonicalization (`type-role-stage-2-complete`)

**Goal**: `{role || type}-{counter}` per-prefix pools, applied uniformly.

**Tests**:
- `test_eid_prefix_uses_role_when_role_present`
- `test_eid_prefix_uses_type_when_role_absent`
- `test_eid_counter_per_prefix_pool` — `heading-1`, `heading-2`, `frame-1` coexist without collision
- `test_two_classified_same_role_get_counted_separately` — two cards → `card-1`, `card-2`
- `test_real_text_and_classified_heading_share_no_counter` — no cross-pool interference

**Files**: [dd/ir.py](../dd/ir.py) counter logic (single location).

**Fixture impact**: every test fixture referencing a specific eid regenerates. **Pre-flight audit**: `grep -rn '"text-[0-9]' tests/` (and similar for each type prefix) to count hard-coded eids. If >100, do the rename pass in a dedicated commit separate from the counter-logic change.

**Risk**: high fixture churn. Commit fixture regeneration separately from logic change for reviewability.

---

### Stage 3a — Renderer + verifier reader migration (`type-role-stage-3a-complete`)

**Goal**: every reader of the conflated `type` field reads `type` (primitive) or `role` (semantic) based on what it needs.

**Audit matrix** (locked by research; 32 primary reads across 9 files, 73 downstream):

| Reader | Wants | Reads |
|---|---|---|
| Leaf-parent gate (`dd/render_figma_ast.py:968`) | primitive | `type` |
| createX dispatch (`dd/renderers/figma.py` Phase 1) | primitive | `type` |
| Verifier structural parity (`dd/verify_figma.py`) | primitive | `type` |
| `_mode1_eligible` gate (`dd/ir.py:327`) | primitive | `type` |
| Grammar head emission `type=` (`dd/markup_l3.py`) | primitive | `type` |
| Eid prefix naming (`dd/ir.py:1263`) | role-first | `role || type` |
| Corpus retrieval type filter (`dd/composition/providers/corpus_retrieval.py`) | role | `role` |
| Composition slot decisions (`dd/compose.py`) | both (see 3b) | `role` for slot semantics, `type` for primitive |

**Tests**: characterization tests for each of the 32 reads first, pinning current behavior; then flip.

**Files**: the 9 primary files identified in diagnosis.

**Off-ramp**: ship Stages 0-3a. Grammar still emits only `type=<primitive>` (no `role=` attr yet). Round-trip parity returns to ~204/204. Mode 3 benefits deferred.

---

### Stage 3b — Mode 3 path update (`type-role-stage-3b-complete`)

**Goal**: Mode 3 LLM and composition emit type/role cleanly.

**Work**:
- Update the Mode 3 prompt (`dd/compose.py` compose.generate_from_prompt, and any prompt templates under `dd/prompts/` or similar) to teach the LLM:
  - `type=` must be chosen from the ~8 primitive vocabulary
  - `role=` is optional and drawn from the ~81-type classifier catalog
  - When eid prefix equals `role`, `role=` attr can be elided in the head
- Update `compose._mode3_synthesise_children` to read `role` for slot-semantic decisions but never to use role as a Figma primitive
- GBNF grammar constraint (if constrained decoding is active): enforce `type=<primitive>` enum

**Tests**:
- `test_mode3_prompt_emits_primitive_type` — LLM output for a "button" produces `type=frame, role=button` (not `type=button`)
- `test_mode3_compose_reads_role_for_slot_decision`
- `test_mode3_synthesise_never_uses_role_as_primitive`

**Files**: [dd/compose.py](../dd/compose.py), Mode 3 prompt templates (locate via grep for the active prompt strings).

---

### Stage 4a — Grammar head extension (`type-role-stage-4a-complete`)

**Goal**: parser and serializer accept/emit optional `role=` in heads.

**Tests**:
- `test_markup_parser_accepts_type_and_role_in_head`
- `test_markup_parser_accepts_type_only_head` (backward-compat)
- `test_markup_parser_rejects_role_only_head` (type is always required)
- `test_markup_serializer_emits_role_when_differs_from_type`
- `test_markup_serializer_elides_role_when_equals_type`
- `test_markup_roundtrip_preserves_role_when_present`
- `test_markup_roundtrip_elides_role_when_absent`

**Files**: [dd/markup_l3.py](../dd/markup_l3.py) parser + serializer, `docs/decisions/v0.3-grammar-modes.md` (spec update).

**Fixture impact**: round-trip fixtures for the 148 affected screens regenerate with `role=` attrs. Again, commit fixture regeneration separately.

---

### Stage 4b — Verifier compatibility rule (`type-role-stage-4b-complete`)

**Goal**: verifier flags `type`/`role` incompatibility at IR-build time instead of masking it at render time.

**Compatibility rule**:
- `type=<leaf>` with children → forbidden (leaf types cannot contain children)
- `role=<container_role>` on `type=<leaf>` → forbidden (role implies structure that type can't support)
- `type=<container>` with `role=<leaf_role>` → allowed (a frame labeled "text" is a frame containing text — common)
- `type=<container>` with `role=<container_role>` → allowed
- `type=<leaf>` with `role=<leaf_role>` → allowed

**Tests**:
- `test_verifier_flags_leaf_type_with_children_error_kind_role_type_incompatible`
- `test_verifier_flags_container_role_on_leaf_type`
- `test_verifier_tolerates_leaf_role_on_container_type`
- `test_verifier_hint_points_to_classifier_source_and_suggests_repair`

**Files**: [dd/verify_figma.py](../dd/verify_figma.py).

**Integration hook**: `StructuredError.hint` for the new `role_type_incompatible` error kind feeds the M7.5 repair loop per [feedback_unified_verification_channel.md]. Loop can propose either `delete @eid` (if the node shouldn't exist) or `type=<container>` override (if the classifier's semantic call was correct but the primitive was wrong).

---

### Stage 5 — Acceptance sweep (`type-role-complete`)

**Run the 204-screen sweep.**

**Acceptance gates**:
1. `is_parity=True` on ≥200 of 204 (allows ≤4 other-cause drifts)
2. Zero `leaf_type_append_skipped` errors on Dank-sourced round-trip (gate still defensive-active for Mode 3 synthesis)
3. 3146-passing test count maintained (existing suite not regressed)
4. Verifier catches ≥24 of the known 148 SCI misclassifications at IR-build time as `role_type_incompatible` (rather than at render time as `missing_child`)
5. No new fixtures or frozen expectations outside the 148 affected set have changed bytes unexpectedly

**Rollback**: `pre-type-role-split` tag, single `git reset --hard`.

---

### Stage 6 — Defense-in-depth (deferred, separate session)

Not blocking the core split. Tracked for a follow-up session.

- **Structural pre-filter** on classifier input — pass `has_children` + `figma_type` into the prompt, mask structurally-impossible labels from the candidate set before the ensemble vote (Prune4Web 2025 pattern; 46.8% → 88.28% grounding accuracy in their setting).
- **Voter-level structural gating** — when any consensus voter proposes a structurally-impossible label, weight that vote to 0 before `consensus_method='weighted_majority'` computes. Novel direction; no 2025 literature covers ensemble voter gating this way.
- **Constrained decoding** on LLM enum output — Outlines / XGrammar / GBNF for the `role` vocabulary and the `type` primitive vocabulary. PLDI 2025: 74.8% illegal-output reduction vs 9% syntax-only.

All three are layer-2 defense. The IR split (Stages 0-5) is load-bearing and must land first.

## 5. Rollback tags

```
pre-type-role-split                Stage 0 start
type-role-stage-0-complete         migration + backfill done
type-role-stage-1-complete         IR split done
type-role-stage-2-complete         eid re-canonicalization done
type-role-stage-3a-complete        renderer/verifier readers migrated
type-role-stage-3b-complete        Mode 3 path done
type-role-stage-4a-complete        grammar extended
type-role-stage-4b-complete        verifier rule landed
type-role-complete                 acceptance sweep passed
```

Any tag → `git reset --hard <tag>` rolls back to that point.

## 6. Total estimate

**2–3 focused days end to end.** Stage 3 is the longest pole; Stage 2's fixture churn is the biggest risk. Stage 0 is quick but gets special care because it touches a 245MB DB.

## 7. Validation inputs (external research)

Research threads run 2026-04-22, synthesized and referenced throughout §2:

- **Classifier-robustness research** — confirmed IR-layer separation is "load-bearing fix" in 2025–2026 literature. Three defense-in-depth layers (IR separation, structural pre-filter, constrained decoding). UI-specific classifiers (Ferret-UI 2, OmniParser v2, UI-TARS, ShowUI) mostly don't structurally constrain; Prune4Web (2025) is the exception.
- **IR prior-art research** — identified "discriminator + role" pattern, Webstudio as canonical design-system example, MLIR Type/Attribute as compiler analogue, D130092 as the "make it optional" lesson, ARIA as the author-dual-field cautionary tale (inapplicable here).

Research transcripts are in agent outputs; key findings are inlined in §2 and §6 of this plan.
