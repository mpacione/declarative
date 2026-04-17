# Exp H — Candidate public design systems for ingestion

> **Purpose:** survey publicly-available design systems that could be ingested as a fall-through layer for synthetic generation. When the user's own file lacks a requested component (or component variant, or token), the pipeline lowers through this layer before reaching "raw composition from catalog primitives."
>
> **Scope decision the user asked for:** which design systems are actually ingestable, what each one provides, and how they map to our 48-type catalog.

## Taxonomy of what we need

Ingestion needs to cover two distinct layers of the IR, which different sources provide to different degrees:

- **Tokens (L2)** — colour, spacing, typography, radius, effect values. Cross-system, standardised via DTCG 2025.10.
- **Component structures (subtrees that become L0/L1 exemplars)** — button with a text label, card with a heading + body + footer slot. These need real component implementations, not just token files.

A good candidate offers one or both. "Token-only" sources are cheap to ingest (just parse a JSON); "component-source" sources require more work (parse React/Vue/HTML to extract structure) but are vastly more valuable for the fall-through case.

## Candidate table

| System | Tokens (L2) | Components | Source format | DTCG-compliant | License | Ingest cost |
|---|---|---|---|---|---|---|
| **shadcn/ui** | Via Radix + Tailwind defaults | ~50 components, full source | React (TSX) + Tailwind + Radix primitives | No (CSS vars + Tailwind classes) | MIT | **Medium** — parse React for slot structure |
| **Radix UI primitives** | No (unstyled) | ~30 primitives, composition-focused | React (TSX) | N/A (style-agnostic) | MIT | **Medium** — parse React |
| **Material Design 3** | Yes, extensive | Full component list via Material Web Components | JSON tokens + TS components | Yes (DSP format) | Apache 2.0 | **Low for tokens, medium for components** |
| **Fluent UI (Microsoft)** | Yes | Large library | JSON tokens (DTCG draft) + React | Yes | MIT | **Low for tokens, medium for components** |
| **Polaris (Shopify)** | Yes | Moving to Web Components (Oct 2025) | JSON tokens + Web Components | Yes | MIT | **Low for tokens, medium for components** |
| **Primer (GitHub)** | Yes | 40+ components | CSS + React + ViewComponents | Partial | MIT | **Low for tokens, medium for components** |
| **Carbon (IBM)** | Yes | Full accessibility-focused library | JSON tokens + multiple framework bindings | Yes | Apache 2.0 | **Low for tokens, medium for components** |
| **Atlassian Design** | Yes | Large library | JSON tokens + React | Yes | ? verify | **Low for tokens, medium for components** |
| **Penpot built-in** | Yes | Growing component set | DTCG JSON + Penpot file format | Yes (native) | MPL | **Low** — designed for this |
| **Station UI** | Via Tailwind | ~40 components | Tailwind + React | No | MIT | **Medium** |
| **Ant Design** | Yes | Very large | Less (Less CSS) + React | No | MIT | **High** — non-DTCG tokens |
| **Chakra UI** | Yes | Medium | JS theme object + React | No | MIT | **Medium** |
| **component.gallery** | No | Catalogs across systems (~60 types flat) | HTML/markdown index | N/A | Content only | **Reference only** — link corpus, not ingestable |

## Recommended v0.1 ingest order

**Tier 1 — ingest first, start small**

1. **shadcn/ui** — React components with visible slot structure, widely understood by LLMs via training data, most likely to be what users' code targets. Start here.
2. **Radix UI primitives** — pairs with shadcn; provides the un-styled primitive layer.

**Tier 2 — ingest second, token-rich**

3. **Material Design 3** — most complete DTCG-compliant token exports, well-maintained by Google. Material tokens cover the full spectrum (colour, spacing, typography, motion, elevation, shape).
4. **Carbon (IBM)** — strong accessibility defaults; Apache 2.0 license means downstream users can actually ship derivatives.
5. **Fluent UI** — Microsoft's DTCG-draft tokens are exactly the format we want.

**Tier 3 — later, incremental**

6. Polaris, Primer, Atlassian — add as we encounter user files that reference them.
7. Penpot's token system — relevant if/when we add Penpot as a second ingest source (the user mentioned this as a potential future).

## What `component.gallery` actually gives us

Not ingestable as data — it's a curated catalog of components across many design systems with links to each system's implementation. Useful as:

- A reference for "how do different systems name and organise the same component" (e.g. what systems call `dropdown` vs `menu` vs `select`)
- A taxonomy sanity check against our 48-type catalog (their ~60-item flat taxonomy vs our 48-type-across-6-categories)
- A discovery source — when a user asks for a component we don't know, component.gallery shows which real systems have one

So it's useful as prior art for our catalog design, not as an ingestable corpus.

## What an ingest actually produces

For each ingested design system, the output should be a secondary corpus mirroring our main `Dank-EXP-02.declarative.db` schema:

- **assets rows** for tokens (colour / space / typography / radius / effect)
- **component_key_registry rows** mapping each component name to a structural exemplar
- **nodes rows** representing the component's internal structure (parent_id tree, type, key props, slot layout)
- **adjacency data** derived from the component's documented composition

The retrieval system then uses this secondary corpus the same way it uses the user's own Dank corpus — kNN against embeddings, fall through by similarity.

## Licensing / redistribution

All tier-1 and tier-2 candidates are MIT or Apache 2.0. Their content can be ingested, stored, queried, and shipped as part of a "defaults" bundle with our tool. Attribution requirements should be honored in the bundle's NOTICE file. Nothing in tier 1/2 has a commercial-use restriction.

Ant Design, Atlassian Design need license verification before ingestion — tier 3 status reflects the uncertainty, not a quality judgment.

## What Exp H should concretely produce

When we launch Exp H (after G and I land), the scope should be:

1. Write a `dd ingest-design-system` command that takes a source URL and kind (shadcn / material / radix / ...) and materialises a secondary corpus DB.
2. Run it on shadcn/ui as the first concrete end-to-end test.
3. Map shadcn components to our 48-type catalog; measure coverage (how many catalog types have shadcn equivalents).
4. Test fall-through: re-run Wave 1.5 v3 prompts with shadcn exemplars available. Compare structural output against the current empty-100×100 baseline.

This is ~1-2 engineer-weeks of work — properly scoped, worth doing well. Not an experiment in the "measurement" sense; a real pipeline addition.

## Open questions to resolve before launching H

- Does shadcn's slot structure map cleanly to our catalog's `slot_definitions`? (Probably, since both use the Radix pattern. Worth validating with one component first — e.g. does shadcn's `Button` with `asChild` align with our `button.slot_definitions.icon`?)
- How do we handle multiple design systems having the same canonical type but different structures? (E.g. Material's card vs Radix's card vs shadcn's card.) Per-exemplar fidelity metadata plus retrieval ranking probably covers this — worth thinking through.
- Do we prefix ingested component_keys to avoid collision with the user's own corpus? (Yes. `shadcn:button/primary` vs `dank:button/primary`.)
- Cold-start UX: when the user runs the CLI for the first time with no user corpus yet, do we preload shadcn by default, or require explicit opt-in? (Probably preload tier-1 as "built-in defaults"; tier-2+ by opt-in to keep the DB small.)

## Next step

Once Exp G (positioning vocabulary) and Exp I (sizing defaults) return, review both + this candidates doc together and write Exp H's concrete design document. That document becomes the specification for the ingestion pipeline, not just a plan.
