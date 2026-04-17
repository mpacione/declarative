# Mode 3 Composition — Integrated Research Memo

> **Status:** converged research memo, 2026-04-16 (pt-8).
> **Superseded-by (decisions):** [ADR-008](../architecture-decisions.md#adr-008-composition-providers--mode-3-synthesis-from-catalog-corpus-and-ingested-systems).
> **Source streams:** [`component-taxonomy-survey.md`](./component-taxonomy-survey.md) (Stream A — ontology) · [`style-induction.md`](./style-induction.md) (Stream B — values) · [`remix-mechanics.md`](./remix-mechanics.md) (Stream C — resolution).
> **Contract test scaffold:** `tests/test_mode3_contract.py`.

## Decisions taken post-review (see ADR-008 for binding specification)

- **"Role" renamed to "variant"** throughout Stream B's output. `role_binding → variant_token_binding`; `cluster_roles.py → cluster_variants.py`. The word "role" appears below as a historical record; binding specification lives in ADR-008 §"Naming".
- **`CatalogEntry.semantic_role`** is vestigial and deprecated but NOT removed in PR #0. Inline comment in `dd/catalog.py` marks it as such. Dedicated cleanup PR deferred post-v0.1.
- **PR ordering:** catalog ontology migration (PR #0) ships first, parity-gated to 204/204 unchanged; Mode 3 composition (PR #1) follows. Confirmed.
- **Universal-catalog template authorship:** hybrid — hand-authored layout/sizing/slots from Stream A + Exp I, colour/radius/shadow values ported from shadcn.
- **Unknown VLM labels:** persist as `custom_N` and include in LLM vocabulary; do not drop.
- **Feature flag:** `DD_DISABLE_MODE_3=1` + `DD_DISABLE_PROVIDER=<backend>` for surgical kill.
- **Test baseline:** 3 golden prompts (login, profile-settings, paywall) run on every PR; full 12 v3 prompts as wider benchmark.
- **Semantic-role alternatives considered:** `recipe`, `component token`, `style binding`, `theme binding` — all rejected for reasons in ADR-008 §"Naming".

## 1. Executive summary

Mode 3 — the missing pipeline stage that synthesises a novel UI subtree when the user's corpus lacks a ready-made component — decomposes cleanly into three independent layers. Each layer's design is informed by a leading pattern in the industry, and the three layers compose through well-defined interfaces that do not require an IR schema change in v0.1.

- **Ontology (Stream A)** — *what is a component?* 50 canonical types × rich slot grammar × four variant axes (`variant`, `size`, `state`, `tone`), with an 8-type extended tier for domain inputs. Our 48-type catalog is defensible in shape; we are slot-thin and variant-axis-incomplete, not ontologically wrong.
- **Induction (Stream B)** — *where do presentation values come from?* Two-layer: Layer A (atoms — palette / type / spacing / radius, which our existing clustering pipeline already produces) and Layer B (role bindings — `(type, variant, slot) → token_id`, which is new and is produced via hybrid clustering + VLM labelling over extracted instances). Novel territory — no commercial tool induces role bindings from an instance corpus.
- **Resolution (Stream C)** — *how does the renderer turn `{type, variant}` into a concrete subtree at generation time?* Hybrid Cascade + Registry: an ordered `ComponentProvider` registry resolves `(type, variant) → PresentationTemplate`; a DTCG token cascade resolves `{token}` refs within. Zero IR change v0.1. Every miss, partial match, or ambiguity surfaces through the ADR-006/007 structured-error channel under new `KIND_*` codes.

The combined v0.1 scope is a single new package (`dd/composition/`), a new DB table (`role_binding`), additions to `dd/catalog.py` and `dd/boundary.py`, and compose-layer integration at the Mode 3 fall-through point. No renderer changes. No schema migration for L0. Estimated: one engineer-week.

## 2. The trilayer model

Mode 3's job is to answer, for each IR node that lacks a resolved `component_key`:

> "Given this `type`, these `props`, these `children`, and this context (project tokens, ingested systems, universal catalog), what's the full subtree that should render here?"

The three streams factor this question along orthogonal axes:

```
                                            ┌─────────────────────────┐
                                            │  Stream A — Ontology    │
   IR node   {type, variant, props}  ─────▶│  Does 'button' exist?   │──▶ PresentationContract
                                            │  What are its slots?    │    (slots, variant axes, standard variants)
                                            └─────────────────────────┘
                                                        │
                                            ┌─────────────────────────┐
                                            │  Stream C — Resolution  │
                                            │  Who owns this variant? │──▶ PresentationTemplate
                                            │  Project ▶ ingested ▶   │    (layout, token refs, child slots)
                                            │  universal ▶ token-only │
                                            └─────────────────────────┘
                                                        │
                                            ┌─────────────────────────┐
                                            │  Stream B — Induction   │
                                            │  Resolve every {token.*}│──▶ concrete values
                                            │  through DTCG cascade + │    (hex, px, weight, …)
                                            │  role_binding lookups   │
                                            └─────────────────────────┘
                                                        │
                                                     Lowered IR subtree
                                                     (Phase 1 compose input)
```

The layers are independently testable and independently phaseable. Stream A's work can ship without waiting for Stream B's inducer. Stream C's registry can ship with only universal-catalog providers. Each layer's output interface is frozen by an ADR protocol; internals evolve underneath.

## 3. Ontology layer — what Stream A locks in

**Our catalog is defensible in shape; tighten it toward machine-decodable slot contracts.**

- **Count:** 50 core + 8 extended → 58 total. Ours is 48. Net deltas: demote 3 (`toggle_group`, `context_menu`, split `file_upload`), add 7 (`divider`, `progress`, `spinner`, `kbd`, `number_input`, `otp_input`, `command`). Optional adds (domain-dependent): `tag`, `rating`, `stat`, `multi_select`, `time_picker`, `color_picker`, `password_input`, `avatar_group`.
- **Slot grammar:** tighten from prose names to typed slot contracts. The industry consensus on `list_item` is six slots (Material's `leading / overline / headline / supporting / trailing_supporting / trailing`) — we use three. Upgrades: `card.image → card.media`; `alert` gets a `close` slot; `text_input` gets a `helper` slot; `dialog.footer` accepts `button_group`.
- **Variant axes:** add three first-class axes across interactive types — `state` (enum replacing scattered booleans: `default | hover | focus | pressed | disabled | loading | invalid`), `tone` (enum: `default | primary | destructive | success | warning | info`), `density` (enum: `compact | default | comfortable`). Currently buried inside `variant` or expressed as ad-hoc booleans.

**Integration with existing code:** `dd/catalog.py` is already the home. The migration is mechanical: update `CATALOG_ENTRIES` tuples, re-seed `component_type_catalog` DB table via the existing `seed_catalog` path. Back-compat: keep aliases for removed types (`toggle_group → toggle` with `grouped` prop) so extracted DBs don't invalidate.

**Deferred:** layout primitives (`Stack`, `Flex`, `Grid`, `Wrap`) stay out of the catalog — they're IR structural concerns, not semantic components. This is a Stream A open question that I'm calling here.

## 4. Induction layer — what Stream B locks in

**Two layers, already separated in our schema. Layer A is solved; Layer B is the new work.**

- **Layer A — atoms.** Palette, typography scale, spacing ladder, radius set, shadow set. Our existing `dd/cluster_*.py` pipeline already produces these as DTCG tokens. OKLCH clustering, GCD scale detection, composite-shadow merging — all live. No change needed for v0.1.
- **Layer B — roles.** The mapping `(catalog_type, variant, slot) → token_id`. This is what tells the renderer "Dank's `button.primary.bg` binds to `{color.brand.600}`, but `button.destructive.bg` binds to `{color.semantic.error}`." No commercial tool does this automatically. We will.

**v0.1 inducer: cluster-then-label (Stream B's candidate A + B).**

1. For each catalog type with ≥5 classified instances, compute a feature vector per instance (fills, strokes, radius, dimensions, icon-presence, adjacency).
2. K-means in OKLCH + normalised dimensions; silhouette score picks K.
3. For each cluster, send ≤10 rendered thumbnails to Gemini 3.1 Pro with the prompt: "assign one role from `{primary, secondary, destructive, ghost, link, disabled, unknown}` per cluster; justify with one line."
4. Persist as `role_binding (catalog_type, role, slot, token_id, confidence, source)`.

**Budget:** ~48 VLM calls total for the full Dank corpus (one per catalog type). Cheap.

**Cold-start:** when a project has <5 instances of a type, backfill from an ingested reference system (shadcn / Material) expressed in the same `role_binding` schema, then recolour its palette into the project's Layer-A tokens using nearest-neighbour OKLCH (Material You's HCT move, applied to role table). This is the shadcn-ingestion entry point from the original Exp H plan, now in its rightful layer.

**Deferred:** screen-context priors (Stream B candidate C) to v0.2 as a regulariser for ambiguous clusters. Render+critic refinement (Stream B candidate D) to v0.3, gated on RenderVerifier parity (pt-7 reality check).

**Integration with existing code:** new `cluster_roles` stage in `dd/cluster.py` orchestration; new `role_binding` table in DB; reuses existing `node_token_bindings` joins. The VLM call path already exists in `dd/visual_inspect.py` (Gemini 3.1 Pro) from Step 1 of this sprint.

## 5. Resolution layer — what Stream C locks in

**Provider registry + DTCG cascade. Zero IR schema change v0.1.**

Three concrete components in a new `dd/composition/` package:

- **`ComponentProvider` protocol** (mirrors `IngestAdapter`): `priority: int`, `backend: str`, `supports(type, variant) -> bool`, `resolve(type, variant, context) -> PresentationTemplate`. Built-in providers: `ProjectCKRProvider` (priority 100), `IngestedSystemProvider` (50), `UniversalCatalogProvider` (10), `TokenOnlyProvider` (0).
- **Registry** (`dd/composition/registry.py`): ordered walk, first `supports()`-true match wins, no provider matches → `KIND_NO_PROVIDER_MATCH`.
- **Token cascade** (`dd/composition/cascade.py`): resolves `{color.action.destructive}` style refs through three layers (project → ingested → universal) with structured-error on unresolved refs.

**Compose-layer integration:** Mode 3 is the fall-through point inside `compose.py`'s `_build_element` — when neither Mode 1 nor Mode 2 resolves, call `resolve(type, variant)` and splice the returned template's subtree into the IR as synthetic children. The renderer (unchanged) then emits Mode-1 / Mode-2 paths for each synthetic child.

**Failure modes, as new `KIND_*` on `dd/boundary.py`:**

- `KIND_NO_PROVIDER_MATCH` — exhausted provider walk. Terminal; no template emitted.
- `KIND_VARIANT_NOT_FOUND` — type exists but variant doesn't. Informational, walk continues.
- `KIND_TOKEN_UNRESOLVED` — template references a token that no cascade layer has. Literal-fallback emitted; render still proceeds.
- `KIND_SLOT_TYPE_MISMATCH` — slot expects `Button`, got `Text`. Informational; slot substitution proceeds with caveat.
- `KIND_ROLE_BINDING_MISSING` — Stream B produced no binding for this (type, variant, slot); caller falls through to universal catalog.

All five kinds feed ADR-007's existing per-node verification channel. No new channel; new vocabulary.

## 6. How the layers compose — the data flow

**Generation time, per Mode-3 IR node:**

1. **Ontology contract lookup.** `catalog_entry = get_catalog_entry(type)`. Returns slots, variant axes, standard variants. If the LLM's emitted `variant` isn't in the type's declared axes → `KIND_VARIANT_NOT_FOUND` (but we still try to resolve; some providers may know the variant).
2. **Provider resolution.** `template = registry.resolve(type, variant, context)`. Returns a `PresentationTemplate` with: layout (direction, sizing, padding tokens), slot contracts (what each slot accepts), child structure, token refs (not yet resolved).
3. **Token cascade.** For each `{path.to.token}` ref in the template, walk the cascade (project tokens → ingested → universal). Produces concrete values. Unresolved → `KIND_TOKEN_UNRESOLVED` with literal fallback.
4. **Role-binding lookup (Stream B).** For slots whose presentation is "inherit role binding for this (type, variant, slot)", query the `role_binding` table. No binding → `KIND_ROLE_BINDING_MISSING`; fall through to template's explicit defaults.
5. **Slot recursion.** For each slot in the template, if the IR has an LLM-supplied child for that slot, recurse through Mode 1 / Mode 2 / Mode 3 on the child. Otherwise emit the template's default (if declared) or skip.
6. **Synthesised IR subtree.** Returned as first-class IR nodes with `_synthesised_from: {type, variant, provider, slot}` provenance (v0.2 adds this as a visible field; v0.1 keeps it in an internal map consumed only by the inspector).

## 7. The user's walkthrough — novel destructive dialog in an 80-90% Dank screen

LLM emits:

```json
{"type": "screen", "children": [
  {"type": "header", "props": {"title": "Projects"}, "component_key": "header/dank"},
  {"type": "list", "children": [ /* … */ ]},
  {"type": "dialog", "variant": "destructive-confirm", "children": [
    {"type": "heading", "props": {"text": "Delete project?"}},
    {"type": "text", "props": {"text": "This cannot be undone."}},
    {"type": "button", "variant": "destructive", "props": {"text": "Delete"}},
    {"type": "button", "variant": "ghost", "props": {"text": "Cancel"}}
  ]}
]}
```

- **Screen, header, list:** Mode 1 via project CKR (unchanged).
- **Dialog:** project provider `supports("dialog", "destructive-confirm")` → False. `KIND_VARIANT_NOT_FOUND` (informational, walk continues). Ingested shadcn provider matches; returns template with `{header, body, footer}` slot contracts, padding tokens, radius tokens. Token cascade resolves `{space.dialog.padding}` at the project level (Dank has it), `{color.surface.dialog}` at ingested level (shadcn's default), `{radius.dialog}` at universal catalog. No `KIND_TOKEN_UNRESOLVED`.
- **Heading, text** inside the dialog's `body` slot: recurse; text types route through the existing Mode-2 text path (no Mode 3 needed).
- **Button (destructive):** project provider has `button` but `supports("button", "destructive")` → False. Fall through; ingested provider returns template. Stream B's `role_binding` lookup maps `button/destructive/bg` to the project's `{color.semantic.error}` token (learned from corpus induction). Cascade resolves → Dank's red.
- **Button (ghost):** project provider supports it from corpus induction; returns Dank-native template with Dank-native tokens.

Result: a destructive-confirm dialog that reads as Dank-native (project colours, project spacing, project typography) but carries shadcn's structural backbone for the parts the corpus hasn't observed. Structured-error channel reports: 2 × `KIND_VARIANT_NOT_FOUND` (dialog.destructive-confirm on project, button.destructive on project) — both recovered, zero terminal errors.

## 8. IR impact — what changes

**v0.1: nothing.** Every decision here is consumable from the existing IR shape (`type`, `variant`, `props`, `children`, `layout`, `component_key`, `style`). The new `PresentationTemplate` lives inside `dd/composition/`; synthesised subtrees splice in as regular IR children; provenance stays in an internal map.

**v0.2 (additive only):** optional `provider: str` field per node (`"project:dank" | "ingested:shadcn" | "catalog:universal"`) for auditability. Optional `role_binding: str` field naming the Stream-B row consumed. Both opt-in, no round-trip parity impact.

**v0.3 (speculative):** if the render+critic refinement loop proves itself, a `refined_from: {template, critique}` audit trail.

## 9. Integration with existing ADRs

- **ADR-006 (boundary).** Mode 3 resolution is a boundary egress — symmetric with ADR-006's ingest side. The `ComponentProvider` protocol has the same shape as `IngestAdapter`; the `StructuredError` vocabulary extends cleanly with the five new `KIND_*` codes. Stream C made this symmetric explicit.
- **ADR-007 (verification channel).** The five new kinds flow through the existing per-node `__errors` channel. RenderVerifier can already attribute them. The v0.3 render+critic loop from Stream B uses the same channel — no new machinery, more vocabulary.
- **ADR-008 (proposed).** This memo is the input. The ADR formalises the `ComponentProvider` protocol, the registry ordering, the cascade semantics, the new `KIND_*` codes, and the IR's non-change in v0.1.

## 10. v0.1 scope — what actually ships

Implementation order (TDD-driven):

1. **`dd/boundary.py`:** add the five new `KIND_*` constants. Zero runtime change. Tests verify constants exist.
2. **`dd/composition/protocol.py`:** `ComponentProvider` Protocol + `PresentationTemplate` dataclass. Failing tests first.
3. **`dd/composition/registry.py`:** ordered registry with priority resolution, structured-error emission. Tests for priority ordering, fall-through, terminal error.
4. **`dd/composition/cascade.py`:** DTCG token cascade with three-layer walk. Tests for ordering, unresolved-ref fallback.
5. **`dd/composition/providers/universal.py`:** first provider — universal catalog from `dd/catalog.py` + default presentation templates for the core 22 universal primitives. Tests verify round-trip resolution for `button/primary`.
6. **`dd/composition/providers/project_ckr.py`:** project CKR provider. Reads `component_key_registry` + `role_binding`. Tests verify project wins over universal for a given `(type, variant)`.
7. **`dd/composition/providers/ingested.py`:** ingested-system provider. Consumes an `IngestResult` (re-using ADR-006 shape). Tests with a shadcn fixture.
8. **`dd/cluster_roles.py`:** role-binding inducer (Stream B v0.1). Cluster + VLM label. Tests with fixture clusters.
9. **Migration:** `role_binding` table, `component_type_catalog` row updates for new types. Tests verify migration idempotence.
10. **`dd/compose.py`:** wire Mode 3 fall-through at the `_build_element` point. Tests verify the 12 v3 prompts now produce non-empty subtrees. Re-run the sanity gate.
11. **Catalog updates:** add the 7 new types (divider, progress, spinner, kbd, number_input, otp_input, command), thicken the slot grammar on list_item/card/alert/text_input/dialog, add state/tone/density axes to the catalog schema.

Estimated total: ~1,500 LOC new code + ~2,000 LOC tests + 2 migrations. One engineer-week of focused work.

## 11. Failure modes catalog (new `KIND_*` codes)

| Kind | Severity | When | Recovery |
|---|---|---|---|
| `KIND_NO_PROVIDER_MATCH` | terminal | Registry exhausted | emit placeholder + error |
| `KIND_VARIANT_NOT_FOUND` | informational | Type resolved, variant not in any provider | continue walk |
| `KIND_TOKEN_UNRESOLVED` | informational | Token ref missing from cascade | literal fallback |
| `KIND_SLOT_TYPE_MISMATCH` | informational | Slot expects type A, got B | splice anyway, emit warning |
| `KIND_ROLE_BINDING_MISSING` | informational | Stream B has no binding for (type, variant, slot) | use template default |

All five are per-node, fed to ADR-007's channel, visible in the render report.

## 12. Phasing

**v0.1 (ship-now, ~1 engineer-week):** Everything in §10. Re-run Wave 1.5 v3 prompts with Mode 3 live. Expected: default-100×100 count drops from 212 to <30. Sanity gate passes on ≥10/12 prompts.

**v0.2 (~1 engineer-week):** Screen-context priors in Stream B's inducer. IR `provider` + `role_binding` provenance fields. shadcn cold-start backfill with HCT palette transplantation. RenderVerifier provider-attribution.

**v0.3 (speculative, ~2 engineer-weeks):** Render+critic refinement loop à la GameUIAgent, gated on RenderVerifier parity across all `KIND_*` visual-loss classes (the pt-7 reality-check gate).

## 13. Open questions the ADR must resolve

1. **Tie-breaking at equal priority.** Alphabetical on `backend` (Stream C's lean) or `registered_at` order? Recommendation: alphabetical for reproducibility.
2. **Deep-merge vs replace on template overrides.** Shallow-merge on axes, replace on compound variants (Stream C's recommendation). Confirm.
3. **Slot-contract strictness.** Commit to Material's six-slot `list_item` grammar (Stream A), knowing ~60% of observed rows use three? Machine-decodable is non-negotiable; richness trades off against classification accuracy. Recommendation: yes, commit — classification can backfill optional slots as `null`.
4. **Role vocabulary closure.** Closed `{primary, secondary, destructive, ghost, link, disabled, unknown}` per catalog type (Stream B v0.1), or open string? Recommendation: closed for v0.1, expand with evidence.
5. **Compound-variant expression in templates.** Stream C's Option C (cva-style first-class) vs inline as template branches. Recommendation: inline in v0.1, first-class in v0.2 if the need shows up.
6. **Provenance scope in `__errors`.** Walk history (richer training signal) vs terminal-only (quieter CI)? Recommendation: behind a `verbose=True` flag.
7. **DTCG themes/modes.** Ship `$mode: "light" | "dark"` now or wait? Recommendation: wait — not on the Mode 3 critical path.
8. **Provider authorship.** Should `UniversalCatalogProvider` have presentation defaults for all 50 types in v0.1, or just the 22-type universal backbone? Recommendation: backbone only in v0.1; extended types return `KIND_VARIANT_NOT_FOUND` and rely on ingested shadcn backfill.

## 14. What this does not solve

- **Animation / transitions.** Out of scope for v0.1–v0.3.
- **Responsive breakpoints.** Template sizing is static in v0.1; breakpoints are a v0.4 concern.
- **A11y roles / ARIA.** Consumed from catalog's `semantic_role`; not inducer-driven.
- **Internationalisation.** RTL layout, bidi text, locale-aware tokens — not on the path.
- **Inverse capability (design → code).** Mode 3 is a synthesis-time concern; the reverse problem (extracting variants *to* code) is orthogonal.
- **Multi-file / multi-project transfer.** Role bindings are per-project in v0.1; transfer requires user opt-in and is a v0.2 measurement.

## 15. Relationship to prior sprint items

| Prior item | Status after this memo |
|---|---|
| Exp H Step 1 (shadcn MVP) | **Subsumed.** shadcn becomes the ingested-system provider in §5/10. Not a standalone step; folded into v0.1 scope. |
| Exp D (anchor exemplar impact) | Still pending, meaningful after v0.1 lands (role_binding provides the anchor corpus). |
| Exp I per-type defaults | Consumed by `UniversalCatalogProvider` as presentation defaults for the 22-type backbone. |
| Exp G positioning grammar | Consumed inside `PresentationTemplate.layout`. Not load-bearing for v0.1. |
| v3 memo items 1-4 | Items 1+2 (screen auto-layout, child sizing) still needed independently of Mode 3; Items 3+4 (Mode-2 prop expansion, default sizing) are what Mode 3 *is*. |
| Wave 2 designer ratings | Do not issue until v0.1 ships and the sanity gate passes on ≥10/12 prompts. |
| Auto-inspect gate | Already shipped. Gates both the pre-ADR baseline and the post-v0.1 verification. |

## 16. Decision points before ADR-008 drafts

Three questions for the user before I draft the ADR and failing tests:

1. **Scope confirmation:** v0.1 as described (one engineer-week, ~1,500 LOC new code + tests, universal catalog + project CKR + ingested shadcn provider + Stream-B role inducer + five new `KIND_*` codes). Yes / no / adjust.
2. **Catalog-migration timing:** ship the ontology changes (demote 3, add 7, thicken slots, add variant axes) as part of v0.1 or as a separate precursor PR? Leaning separate — it stands alone, round-trip parity regressions are easier to isolate. Your call.
3. **Stream-B v0.1 depth:** start with candidate A only (pure clustering, zero LLM, role names `variant.0/.1/.2`) and defer candidate B's VLM labelling to v0.2? Or ship both together? Leaning both together — VLM cost is trivial (~48 calls for Dank), labels are the whole point, and it gates v0.1 success criterion. Your call.

On your signal, I draft `adr-008-composition-providers.md` + `tests/test_mode3_contract.py` as the next output.
