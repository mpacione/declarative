# Exp H — Public design-system ingestion (specification)

> **Status:** engineering specification. This is the concrete design
> for the ingestion pipeline, synthesising findings from Exp G
> (positioning grammar), Exp I (sizing defaults), Exp H-candidates
> (system shortlist), and Wave 1.5 v3 (baseline failure modes).
>
> **Not another research experiment.** This is the plan for real code.

## The problem, grounded in data

Wave 1.5 v3 showed the synthetic pipeline produces 12/12 clean renders
structurally, but 212 of 229 non-screen nodes land at Figma's 100×100
`createFrame()` default. Mode-2 has no internal templates. The catalog
types map to empty grey rectangles because the pipeline has nowhere to
fall to when the user's own corpus (`component_key_registry`) doesn't
match.

Exp I confirmed that Dank's own data can only supply defaults for 12 of
48 catalog types (7 of them reliably). The other 36 types — including
`checkbox`, `text_input`, `toggle`, `dialog`, `avatar`, `list_item`,
`accordion`, `alert`, `tooltip`, `popover`, `breadcrumbs`,
`pagination`, `segmented_control`, `stepper`, ... — must come from
somewhere external.

Exp G established that the positioning vocabulary those external
components should be normalised into is a 16-construct grammar:
4 horizontal × 4 vertical anchors + proportional, with DTCG-token
offsets. Ingested components must be translated into this grammar at
ingest time so retrieval can match against them uniformly.

Exp H-candidates narrowed the survey to a three-tier rollout:
- **Tier 1:** shadcn/ui + Radix UI primitives
- **Tier 2:** Material Design 3 + Carbon + Fluent UI
- **Tier 3:** Polaris, Primer, Atlassian, Penpot

## What ingestion actually produces

For each ingested design system, a **secondary corpus** that mirrors
the main database schema. The retrieval system queries the union of
user-corpus + ingested-corpora; ingested entries are prefixed to avoid
collision and ranked lower than user-specific matches.

Secondary corpus schema (delta from main):

| Table | Main DB | Ingested corpus |
|---|---|---|
| `screens` | user's screens | one "catalog screen" per component (holds the component's internal demo structure) |
| `nodes` | ~87K Dank | one subtree per component, prefixed `<system>:` in `figma_node_id` |
| `component_key_registry` | 129 Dank | one row per component, `component_key = "shadcn:button"`, `name = "Button"` |
| `tokens` / `token_values` | Dank tokens | system's DTCG token export (colour / space / typography / radius / effect) |
| `assets` | Dank raster + SVG | system's static assets (rare; most components are code-expressible) |

Prefixed `component_key` is the collision guard. A user file with its
own `button` and shadcn's ingested `shadcn:button` coexist in the same
DB. The retrieval ranker prefers user-corpus matches when similarity is
comparable; falls through to ingested when user-corpus has no match.

## Ingest pipeline stages

The pipeline's job is, per system, to parse its native source format
into an IR subtree and write it into the secondary corpus. Each system
needs its own parser because the source formats differ:

- **shadcn/ui** — React/TSX source (~50 components), Tailwind classes,
  Radix composition. Parse: JSX structure + Tailwind utilities + Radix
  slot primitives.
- **Radix primitives** — React/TSX (~30 primitives), minimal styling,
  pure slot contracts. Parse: primitive slot trees.
- **Material Design 3** — DTCG JSON tokens + Material Web Components
  source. Parse: JSON directly for tokens; source for component shapes.
- **Fluent UI** — DTCG-draft JSON tokens + React component source.
- **Carbon** — DTCG JSON + multiple framework bindings; pick React.
- **(Tier 3 later.)**

Each parser lives in its own `dd/ingest/<system>.py` module. Shared
utilities for slot detection, positioning-grammar translation, and
catalog-type classification live in `dd/ingest/common.py`.

### The parse contract

Every system-specific parser produces a uniform output:

```python
@dataclass
class IngestedComponent:
    canonical_type: str        # e.g. "button"; MUST match a catalog entry or be rejected
    system_key: str            # prefixed key, e.g. "shadcn:button"
    name: str                  # human name, e.g. "Button"
    description: str           # short role description
    variants: list[str]        # optional sub-variants, e.g. ["default", "destructive", "ghost"]
    slots: dict[str, SlotDef]  # slot structure matching catalog's slot_definitions shape
    subtree: list[IRNode]      # the IR nodes representing this component's default structure
    default_size: dict         # width / height / sizing-mode triple (see Exp I defaults.yaml shape)
    positioning: SpatialIntent # spatial grammar entry per Exp G (for positioning IN a parent)
    token_refs: list[str]      # token names this component references
    license: str               # MIT / Apache-2.0 / MPL-2.0 / etc.
    source_url: str            # traceability
```

System parsers lift native format into this shape. The shared pipeline
consumes it regardless of source.

## Three guard rails the parser must enforce

Based on Exp I's alias-hijack finding, the ingest pipeline has to be
stricter about catalog matching than the current `derive_canonical_type`:

**Guard 1 — name match alone is not sufficient.** shadcn's `Sidebar`
must be structurally validated as a drawer-like surface, not blindly
aliased to `drawer` on the name. Every catalog type's `slot_definitions`
+ `recognition_heuristics` in `dd/catalog.py` provide the structural
contract. Ingested components either satisfy the contract or get
rejected with a structured error.

**Guard 2 — reject when the contract fails rather than approximating.**
If shadcn's parsing produces an `Alert` component whose slots don't
match the catalog's `alert.slot_definitions` (e.g. it has a `close`
slot the catalog doesn't list), the parser pushes a
`KIND_CATALOG_CONTRACT_VIOLATION` and skips the component. Better to
have 40 well-matched components than 60 partially-matched ones.

**Guard 3 — ingest-time normalization into G's grammar.** Every
non-auto-layout positioning expressed in a source component (e.g.
a Tailwind `absolute top-4 right-4`) gets translated into
`spatial: {horizontal: {anchor: trailing, offset: 16, from: parent},
vertical: {anchor: top, offset: 16, from: parent}}` at ingest time,
not retrieval time. This is what makes retrieval tractable — all
exemplars are already in the target grammar.

## CLI shape

New command `dd ingest-design-system`:

```bash
# Ingest a system. Downloads / clones source if needed; parses; writes
# secondary corpus. Idempotent.
dd ingest-design-system shadcn --source github:shadcn-ui/ui --out .dd/shadcn.corpus.db

# Query what's been ingested.
dd ingested-systems list
# shadcn            50 components, 847 tokens, ingested 2026-04-18
# material-design-3 78 components, 1247 tokens, ingested 2026-04-18

# Register an ingested corpus with a user's main DB.
dd ingested-systems link --db Dank-EXP-02.declarative.db --use shadcn,material-design-3
```

Multiple ingested corpora coexist. The user's main DB carries a
`linked_corpora` pointer table naming which secondary corpora to query
as fall-through during generation.

## Retrieval with fall-through

Synthetic generation's `GenerationContext` (per Exp A's adapter spec)
gets its `exemplars` field populated from the union query:

```python
def retrieve_exemplars(request: GenerationRequest, main_db, linked_corpora):
    # User corpus first. Embedding-based kNN against CKR + pattern table.
    user_hits = search_main_corpus(request, main_db, top_k=5)

    # Fall through to each linked corpus in order.
    for corpus in linked_corpora:
        if enough_confidence(user_hits):
            break
        system_hits = search_ingested_corpus(request, corpus, top_k=3)
        # Rank lower than user hits even if similarity is higher —
        # user's own design-system voice wins ties.
        user_hits.extend(dampen(system_hits, weight=0.8))

    # Final fall-through: catalog defaults (Exp I's defaults.yaml).
    return user_hits + catalog_defaults(request.canonical_types)
```

The dampening factor (~0.8 for ingested, 1.0 for user) is the knob
that keeps "this user's Dank-specific button" preferred over "shadcn's
generic button" even when shadcn's button is a better textbook match.

## Rollout sequence

**Step 1 — shadcn-only MVP (2-3 engineer-days).**
Parse shadcn's ~50 components. Map to 48-type catalog. Normalize
positioning into G's grammar. Write to secondary corpus. Wire retrieval.
Re-run Wave 1.5 v3's 12 prompts with shadcn linked. Measure: how many of
the 212 default-100×100 nodes now have real content?

**Step 2 — measure impact.** Compare Step 1's outputs to v3 baseline.
If the structural-quality delta (from Wave 2 ratings, or vision-critic
scoring) justifies the approach, proceed. If it doesn't (e.g. shadcn
style clashes badly with Dank's voice), reconsider weighting or
rollout order.

**Step 3 — Material Design 3 (2 engineer-days).** Adds ~80 more
components + comprehensive DTCG tokens. Primarily fills the 36-gap
list from Exp I with authoritative defaults.

**Step 4 — Tier 2 rounding out.** Carbon, Fluent UI. Mainly for
coverage of enterprise patterns (dialogs, data tables, complex
forms) that shadcn under-represents.

**Step 5 — Tier 3 opt-in.** Polaris, Primer, Atlassian added per user
request, not default.

Budget: Steps 1-2 are one engineer-week. Steps 3-5 are another week.
Total: ~2 weeks of focused implementation work. Not a research
experiment; a real shipping feature.

## Open questions (for v0.2 or user discussion)

- **Token collision.** Two ingested systems both define `color.accent.primary`
  with different values. Prefix tokens too, or allow the user to pick a
  "primary" system? (Probably prefix, but audit first.)
- **Cold-start UX.** A user runs `dd extract` on a new file with ten
  screens and a thin CKR. Should shadcn be auto-linked as a default, or
  require explicit opt-in? (Probably auto-link at Step 1, make opt-out
  obvious.)
- **Asset handling.** shadcn uses Lucide icons by default. Do we ingest
  Lucide's SVGs into the asset registry, or leave icon asset resolution
  to the user's own icon library? (Probably the former for complete
  cold-start plausibility.)
- **Version pinning.** shadcn updates frequently. Do we pin a specific
  commit for reproducibility, or always pull HEAD? (Pin per ingest run;
  user re-ingests when they want to refresh.)

## What this doesn't try to solve

- Cross-project style transfer. Ingested components provide *structure*,
  not voice. A user's screen rendered from shadcn exemplars will look
  shadcn-flavoured, not Dank-flavoured. Closing that gap is a retrieval-
  ranking + per-token override problem, not an ingestion problem.
- Component discovery. If a user wants a component shadcn doesn't have
  (`color_picker`, `rich_text_editor`), ingesting shadcn won't help.
  Exp H doesn't claim to cover the full 48-type catalog — it narrows
  the gap; a future Exp can add libraries that cover the rest.
- Token system coherence. If a user has their own token palette AND
  links shadcn, the rendered output may reference both. Normalising to
  the user's palette preferentially is a retrieval-ranking choice, not
  solved here.

## Success criteria for v0.1 ship

Exp H Step 1 (shadcn MVP) succeeds for v0.1 if:

1. All ~50 shadcn components parse to `IngestedComponent` instances
   without catalog-contract violations on the 10 most-used types
   (button, text, heading, card, input, select, checkbox, dialog,
   tabs, badge).
2. Positioning grammar normalisation covers 95%+ of shadcn's internal
   spatial choices (it should — shadcn is already auto-layout-first).
3. Re-running Wave 1.5 v3's 12 prompts with shadcn linked reduces the
   "default 100×100" node count from 212 to <50.
4. Either the Wave 2 designer ratings or the Wave 3 vision-critic
   scores improve measurably on intent_match + structural_quality
   when shadcn is linked vs not.

All four are measurable. Pass = ship; fail = iterate on parser or
ranker before more corpora.

## Next concrete action

Start Step 1 as a focused implementation sprint. The spec above is
detailed enough to hand off. Estimated scope: `dd/ingest/common.py`
(~200 LOC), `dd/ingest/shadcn.py` (~400 LOC), `dd/ingested_systems.py`
(CLI glue, ~150 LOC), plus tests. Total ~750 LOC of new code + tests +
one new migration for the `linked_corpora` pointer table.

Before coding: wait for the Wave 2 rating pass. If the ratings suggest
the 100×100 defaults aren't actually the biggest visible problem (e.g.
structure is worse than sizing), reweight the implementation priority.
