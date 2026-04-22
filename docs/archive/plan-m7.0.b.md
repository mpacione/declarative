# Plan — M7.0.b Slot-Definition Derivation

**Status:** ✅ **SHIPPED 2026-04-21** in two steps. Step 1 (commits `faf9902` → `ec5967c`) backfills `components` from CKR — 100 rows, migration 018 adds `canonical_type` column, SD-3 consensus filter applied. Step 2 (commits `5dc3705` → `44a06dd`) clusters trusted instances by semantic child-class (TEXT / ICON / COMPONENT / CONTAINER), LLM-labels dominant cluster via Claude Haiku, writes `component_slots`. 99 rows total (button 9, icon 86, tabs 1, header 3). Schema decisions SD-1 / SD-2 / SD-3 / SD-4 applied per recommendation in this doc. Open questions OQ-1/2/3 resolved pragmatically (per-canonical-type, default_content deferred to M7.3, button-family ⊂ canonical_type 'button' only).

Downstream integration: `dd.library_catalog.serialize_library(include_slots=True)` surfaces slots in the LLM context. `dd.ir.generate_ir(semantic=True)` reads slot defs via `query_slot_definitions` and assigns children to named slots.

**Authored:** 2026-04-19 (autonomous design pass).
**Trigger to revisit:** if a second project with a different naming convention needs slot derivation — the cluster-by-semantic-class is data-driven but the `dominant_cluster` threshold (default 0.5) may need tuning.

---

## 1. Why this is more involved than it looks

The plan-synthetic-gen.md framing says:
> M7.0.b — Slot-definition derivation per canonical_type. For each canonical_type with ≥N instances, auto-cluster children by role/position; Claude labels each cluster's slot purpose. Populates `component_slots`.

But the existing schema for `component_slots` is keyed on `component_id` (FK to `components.id`), not on `canonical_type`:

```sql
CREATE TABLE component_slots (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    slot_type       TEXT,
    is_required     INTEGER NOT NULL DEFAULT 0,
    default_content TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    description     TEXT,
    UNIQUE(component_id, name)
);
```

And `components` is currently empty (0 rows). The Component Key Registry (CKR) is populated (129 components) but lives in a separate table.

Two-step problem:

1. **Backfill `components` from CKR.** Each CKR entry → one `components` row. ~129 rows. No API cost.
2. **Derive slots per canonical_type, apply per-component.** For each canonical_type with ≥N instances, cluster the instances' children by structural shape, label clusters via Claude, write `component_slots` rows for every `component_id` in the canonical_type's CKR set.

## 2. Schema decisions (require user sign-off)

### SD-1 — Backfill `components` from CKR

**Decision:** populate `components` from `component_key_registry` rows. Each CKR entry becomes one `components` row with:
- `figma_node_id` = CKR.figma_node_id
- `name` = CKR.name
- `category` = derived from canonical_type (look up via `screen_component_instances` joined to `component_type_catalog`)
- `composition_hint`, `variant_properties` left NULL (M7.0.c populates)

**Why:** the `components` table is the schema's authoritative master-component list. `component_slots` FKs to it. Empty `components` means we can't write slots at all.

**Reversal cost:** delete from components; the cascade clears component_slots.

### SD-2 — Per-canonical-type clustering, per-component slot rows

**Decision:** cluster all instances of a given canonical_type (e.g., all 401 `button_group` rows), find the recurring child-shape patterns. For each pattern, treat it as one slot. Then write slot rows for every `components.id` whose CKR entry's canonical_type matches.

**Why:** the plan's intuition is "same canonical_type → same slot vocabulary." Variants of the same component (button/primary/sm vs button/primary/lg) share slots. Cross-screen instances of the same component_key share slots even more obviously. Clustering at the canonical_type level captures both.

**Edge case:** the same canonical_type may have heterogeneous structures (e.g., some buttons have icons, some don't). The cluster step finds the SUPERSET of slots; `is_required = 0` flags optional slots not present in every instance.

**Reversal cost:** restructure to per-component-key clustering (smaller batches, less generalisation, more API cost).

### SD-3 — Trusted-instance subset for clustering

**Decision:** only cluster instances where `consensus_method IN ('formal', 'heuristic', 'unanimous')`. Skip `majority`, `any_unsure`, `three_way_disagreement`, and any `flagged_for_review = 1` rows.

**Why:** clustering on noisy classifications produces noisy slot definitions. The trusted subset is large enough (~85% of total per dry-run) for stable patterns to emerge.

**Reversal cost:** include majority rows; cluster output may be noisier but training signal from more rows.

### SD-4 — Initial scope: button family only

**Decision:** ship M7.0.b first on `button` canonical_type only (single canonical_type pass). Then scale to other types after the pattern is validated.

**Why:** button is the M7.2 demo target. Validating on one type catches design issues (clustering shape, slot-naming, default_content shape) before scaling.

**Reversal cost:** zero — this is just sequencing.

## 3. Implementation

### Step 1 — Backfill `components` (SD-1)

`scripts/backfill_components.py`:

```python
# 1. Read CKR.
# 2. For each entry, look up the canonical_type via the most-common
#    classification across instances (joined sci.classification_source
#    weighted by formal > heuristic > consensus_method='unanimous').
# 3. Map canonical_type → category (use component_type_catalog.category).
# 4. INSERT INTO components (file_id, figma_node_id, name, category)
#    VALUES (?, ?, ?, ?) for each.
# 5. Stats: how many CKR entries got populated; how many lacked
#    classifications.
```

No API calls. Pure SQL.

### Step 2 — Slot clustering + labelling for `button` (SD-2 + SD-4)

`scripts/b_button_slots.py`:

```python
# 1. SELECT instance node_ids where canonical_type='button' AND
#    consensus_method IN ('formal','heuristic','unanimous').
# 2. For each instance, fetch children (TEXT, ICON, INSTANCE) +
#    their attributes (text_content, sample text, position, size).
# 3. Cluster by structural shape:
#    - Number of TEXT children
#    - Number of ICON children
#    - Order (icon-first vs text-first)
# 4. Each cluster → one (slot_name, slot_type, is_required) tuple.
# 5. Use Claude Haiku 4.5 to label each cluster's slot:
#    Prompt: "These N button instances all have a TEXT child at
#    position 0 and an optional ICON child at position 1. What slot
#    name + role best describes (a) the TEXT and (b) the ICON?"
# 6. INSERT INTO component_slots (component_id, name, slot_type, ...)
#    for every component_id in the button family.
```

Cost estimate: ~$0.50-2 (5-10 cluster prompts per canonical_type).

### Step 3 — Validation

Sanity check on the populated slots:

- For each `components.id` in the button family, verify `component_slots` has at least one row.
- For each slot, verify the inferred default_content (if any) is a valid token reference.
- Cross-reference: do the slots match the catalog's behavioral_description for `button`? ("Primary interactive control that triggers an action.")

## 4. Out of scope

- Other canonical_types (after button validates, scale per-type).
- Variant-family detection (M7.0.c).
- Forces/context labels (M7.0.d).
- Pattern extraction (M7.0.e).
- Sticker-sheet reconciliation (M7.0.f).

## 5. Acceptance bar

M7.0.b ships when:

- `components` has ≥100 rows (most of CKR backfilled).
- `component_slots` has ≥1 row for every button-family component.
- A spot-check of 10 button instances: their structure matches the slot definitions (label always present, leading_icon optional).
- Cost ≤ $5 total.

## 6. Open questions for user

- **OQ-M7.0.b-1:** SD-2 (per-canonical-type clustering) vs per-component-key clustering. Per-canonical-type is more efficient but may over-generalize. Per-component-key is more accurate but ~129x more expensive. Spec recommends per-canonical-type for M7.0.b initial scope; user may prefer per-component-key for production.

- **OQ-M7.0.b-2:** the `default_content` JSON shape isn't specified anywhere. Recommend: `{"type": "text"|"icon"|"component", "value": "<token-ref-or-string>"}`. User to confirm shape before script-writing.

- **OQ-M7.0.b-3:** should slots be derived ONLY from instances classified as `button`, or include `button_group` (collection of buttons that may have a different slot vocabulary)? Spec recommends button-only first; button_group is its own canonical_type with its own M7.0.b pass.
