# Style Induction for Mode-3 Synthetic Components

**Status:** Research memo, pt-7 sprint
**Date:** 2026-04-16
**Author:** claude-opus-4-7 (research agent)
**Decision this memo informs:** how Mode 3 obtains presentation values (fills, radii, padding, typography) for a novel component (e.g. "confirmation dialog with destructive button") that must feel native to the user's corpus, without hand-authored `(type × variant)` templates.

## 1. Executive summary

Induce style in two layers, already-separated in our DB schema. **Layer A (atoms)** is what our token clustering already produces: palette, type scale, spacing ladder, radius set, shadow set — DTCG tokens. **Layer B (roles)** is missing: the mapping from *semantic role* (`button.primary.bg`, `button.destructive.bg`, `surface.dialog`) to a specific token in Layer A. Recommendation: ship v0.1 as a **hybrid clustering + VLM-labelling pipeline** — feature-cluster every instance of a catalog type (e.g. all 129 button variants in Dank), let Gemini 3.1 Pro label each cluster with a role from a closed vocabulary, persist the mapping as a `role_binding` table. For cold-start / sparse corpora, back-fill unassigned roles from an **ingested reference system** (shadcn) expressed in the same schema. Render + critic loop is v0.2. This keeps determinism where we have data, and gates LLM use to semantic labelling — never to visual values.

## 2. Prior art — academic

- **SPEC / SpecifyUI** ([arxiv 2509.07334](https://arxiv.org/abs/2509.07334)) — structured, parameterised, hierarchical IR with **global / regional / component scopes**. Extracts SPEC from reference UIs via region segmentation + VLM, then composes across sources. Directly validates the hybrid approach: VLM for extraction, parameterised IR for composition.
- **GameUIAgent** ([arxiv 2603.14724](https://arxiv.org/abs/2603.14724)) — Design-Spec-JSON IR; LLM generates, VLM "Reflection Controller" critiques each rasterised render, six-stage neuro-symbolic loop. Their **Rendering-Evaluation Fidelity Principle** ("partial rendering enhancements paradoxically degrade VLM evaluation by amplifying structural defects") is a warning for v0.1: render-and-critique only pays off once the renderer is already consistent. We already know this from pt-6 (`feedback_verifier_blind_to_visual_loss.md`).
- **UICrit** ([arxiv 2407.08850](https://arxiv.org/abs/2407.08850), [UIST '24 PDF](https://people.eecs.berkeley.edu/~bjoern/papers/duan-uicrit-uist2024.pdf)) — 3,059 human critiques with bounding boxes on 1,000 Rico screens; few-shot visual prompting yields 55 % gain in LLM UI feedback quality. Useful as the rubric schema for a future critic.
- **UIED** ([DL 10.1145/3368089.3417940](https://dl.acm.org/doi/10.1145/3368089.3417940)) — hybrid CV + CNN for element detection. Not directly needed (we have structural extraction), but the taxonomy is compatible with our 48-type catalog.
- **Screen2Vec** ([arxiv 2101.11103](https://arxiv.org/abs/2101.11103)) — self-supervised embedding of GUI screens + components via text, visual design, layout, app metadata. A template for learning an embedding that could replace hand-crafted feature vectors in the clustering step.
- **VINS** ([arxiv 2102.05216](https://arxiv.org/abs/2102.05216)) — attention-aware autoencoder producing a joint embedding of structure + content; 80-90 % retrieval precision. Template for "nearest-neighbour from corpus" as a fallback role resolver.
- **CLAY / Rico-denoise** ([arxiv 2201.04100](https://arxiv.org/abs/2201.04100)) — 59k human-annotated screen layouts, 82.7 % F1 on invalid-object detection, 85.9 % on type recognition. Establishes that component-type classification from layout is a solved problem at ~85 %, which bounds our expected accuracy for variant role assignment.
- **Rico-SCA** ([Rico-SCA](https://huggingface.co/datasets/rootsautomation/RICO-SCA), [Rico](https://interactionmining.org/rico)) — 66k screens × 24 component categories × 197 text-button concepts × 97 icon classes. Relevant as training set if we eventually fine-tune a role classifier.
- **Material You HCT / dynamic color** ([material-color-utilities](https://github.com/material-foundation/material-color-utilities), [M3 color system](https://m3.material.io/styles/color/system/how-the-system-works)) — quantise source image, score for theming suitability, generate 5 tonal palettes × 13 tones in HCT space. The strongest precedent for **palette induction** from sparse signal. Our `cluster_colors.py` with OKLCH delta-E is a simpler cousin of this.

## 3. Prior art — industrial

- **Figma Variables + component properties / variants** ([help.figma.com/.../Explore-component-properties](https://help.figma.com/hc/en-us/articles/5579474826519-Explore-component-properties)) — the shape we ultimately emit into. Dank uses slash-notation naming (`Button/Primary/Destructive`) which is structurally the vocabulary we need to recover.
- **Penpot + Tokens Studio** ([Penpot native tokens](https://help.penpot.app/user-guide/design-tokens/), [Tokens Studio announcement](https://tokens.studio/blog/bringing-design-tokens-to-penpot-an-open-source-collaboration-for-the-design-systems-community)) — first fully-DTCG design tool. We already emit DTCG, so interop is free; **no variant-role induction** (users author).
- **Vercel v0 + shadcn registry** ([working with Figma and custom design systems](https://vercel.com/blog/working-with-figma-and-custom-design-systems-in-v0), [AI-powered prototyping with design systems](https://vercel.com/blog/ai-powered-prototyping-with-design-systems)) — a **registry** (Tailwind config + `globals.css` + component code) *is* the design system; v0 treats it as ground truth rather than inducing it. Cold-start strategy: supply shadcn registry for free.
- **Builder.io Visual Copilot** ([figma-to-code-visual-copilot](https://www.builder.io/blog/figma-to-code-visual-copilot), [match-my-code-style announcement](https://x.com/builderio/status/1767960584241217900)) — trained from-scratch model plus "match my code style"; CLI replaces generic colours with project tokens before generating. Style matching is **post-hoc substitution**, not induction. Limited relevance to our problem because their input is a Figma design, not an abstract request.
- **Anima Figma-to-React** ([variants announcement](https://www.animaapp.com/blog/product-updates/anima-introduces-support-of-component-variants/), [variants to React](https://www.animaapp.com/blog/product-updates/convert-figma-variants-into-interactive-react-components/)) — pass-through: same-layer-structure variants become React props. No induction; requires user-authored variants.
- **Supernova** ([design tokens pipeline](https://www.supernova.io/design-tokens), [MCP automation](https://www.supernova.io/blog/simplify-your-design-token-pipeline-november-2023-release)) — exporter pipelines for CSS / Style Dictionary / Tailwind. Downstream of our work, not competitor.
- **Knapsack + MCP** ([MCP server announcement](https://www.knapsack.cloud/blog/knapsacks-mcp-server-turns-design-systems-into-production-engines)) — exposes existing DS to AI agents via MCP. Same shape as our v0.2 output surface: once we have induced roles, we can expose them over MCP.
- **DESIGNLANG / skillui** ([designlang.vercel.app](https://designlang.vercel.app/), [skillui](https://github.com/amaancoderx/skillui)) — Playwright-based live-site reverse-engineers: screenshots, DOM, class fingerprints, interaction diffs. Points at "capture everything" as a style-ingestion format; orthogonal input source to Figma extraction.

**Key industrial gap:** every commercial tool today either **passes through** user-authored variants (Anima, Figma, Penpot) or **consumes a provided registry** (v0, Knapsack). None induce role → token bindings from a corpus of instances. That's our novel surface.

## 4. Our existing code

Read: `dd/cluster.py`, `cluster_colors.py`, `cluster_typography.py`, `cluster_spacing.py`, `cluster_misc.py`, `dd/curate.py`.

- `cluster_colors.py` — OKLCH delta-E ≤ 2.0 grouping; role classification is a property-name heuristic (`stroke.*` → `border`, else `surface`) with order index mapped to `primary|secondary|tertiary`. No role classifier reads *what kind of node* the color is attached to.
- `cluster_typography.py` — font-size bands → `display|heading|body|label|caption`; assigns t-shirt suffix. No link to node semantic role.
- `cluster_spacing.py` — GCD scale detection (`4px`, `8px`); multiplier vs t-shirt naming.
- `cluster_misc.py` — radius + effect + opacity + stroke-weight; composite-shadow grouping.
- `dd/curate.py` — accept / merge / split / rename / alias.

**Gap for Mode-3 style induction:** our pipeline clusters *values* into *atoms*. It never asks "are these three fills three variants of the same button, or three unrelated uses of blue?" The Layer-B mapping `role → token` is not computed. The 48-type catalog already defines slot names (`Button.bg`, `Button.fg`, `Button.border`); we need to fill them. Extension is straightforward because the binding table (`node_token_bindings`) already joins to nodes, and nodes carry (post pt-7 Exp I) their classified component type.

## 5. Algorithm candidates

### A. Pure feature clustering (extension of current pipeline)

**Input:** all `INSTANCE` + `FRAME` nodes classified by catalog type (Dank has ~129 button instances). Feature vector per node: background fill hex, text fill hex, border fill hex, border weight, corner radius, height, pad-x, icon-presence, text-length bucket.
**Output:** for each catalog type, K clusters each labelled by position (`variant.0`, `variant.1`, …) and emitted as `role_binding (type, variant_index, slot, token_id)`.
**Mechanism:** k-means in OKLCH + normalised dimensions; silhouette score picks K. Representative per cluster drives token assignment.
**Coverage:** handles the "common" case — clear visual separations (filled vs outlined vs ghost).
**Cost:** zero LLM; ~seconds.
**Failure modes:** (i) indices are meaningless — cluster 0 might be destructive not primary; (ii) features that don't load on the main axes (e.g. icon size) collapse; (iii) sparse variants of size 1 get merged into noise.
**Prior art:** our `cluster_colors.py`; Material You's quantise-then-score; VINS's embedding approach ([arxiv 2102.05216](https://arxiv.org/abs/2102.05216)).

### B. VLM-assisted role labelling (cluster-then-name)

**Input:** candidate A's clusters. Plus for each cluster: 3-5 rendered thumbnails of actual instances; the screen-context crop; the node's adjacency (what it sits inside, what it sits next to).
**Output:** same `role_binding` table, but `variant_index` is replaced with a **named role** from a closed vocabulary (`primary | secondary | destructive | ghost | link | …`) per catalog type.
**Mechanism:** one batched Gemini 3.1 Pro call per catalog type. Prompt: "Here are K clusters of button-like instances from this app. For each, assign one role from {primary, secondary, destructive, ghost, link, disabled} or `unknown`. Justify with a one-liner." Structured output → closed vocab. VLM looks at renders, not raw JSON, so it sees what a designer would see.
**Coverage:** solves A's naming problem; handles most real systems.
**Cost:** ~48 VLM calls total (one per type), each ≤ 10 images. Cheap.
**Failure modes:** (i) role vocabulary drift between corpora (Dank might have `warning` while shadcn doesn't) — mitigated by per-type closed vocab; (ii) VLM assigns `primary` to multiple clusters — verifier rejects and asks for re-ranking; (iii) small clusters get `unknown` — acceptable, fall back to defaults.
**Prior art:** SpecifyUI extraction step ([arxiv 2509.07334](https://arxiv.org/abs/2509.07334)); UICrit's visual-prompting gains ([arxiv 2407.08850](https://arxiv.org/abs/2407.08850)) justify the visual-crop format.

### C. Screen-context induction

**Input:** node + its ancestor screen's classified type (login, checkout, action-sheet, …). Positional priors: "leftmost in row", "fills container", "adjacent to text label".
**Output:** soft role prior per node, consumed by A/B as a regulariser.
**Mechanism:** rule-based first (login-screen's only button = primary; action-sheet's 3rd button with red fill = destructive), optionally refined by an LLM pass over screen-level JSON.
**Coverage:** disambiguates A when structural features alone collide; rescues sparse variants (one destructive button across 204 screens) because position carries strong role signal.
**Cost:** rule-based is free; LLM refinement is ~204 small prompts if ever needed.
**Failure modes:** positional priors encode cultural conventions that don't hold universally (right-aligned = primary on iOS; left = primary on Android — see `feedback_figma_frames_are_visual.md`). Use as a **tie-breaker**, not ground truth.
**Prior art:** Screen2Vec task-aware embeddings ([arxiv 2101.11103](https://arxiv.org/abs/2101.11103)); Rico-SCA's per-screen semantic annotations ([Rico-SCA](https://huggingface.co/datasets/rootsautomation/RICO-SCA)).

### D. Render + critic refinement

**Input:** B's output plus a rendered candidate Mode-3 component.
**Output:** same `role_binding` but mutated post-render by VLM feedback.
**Mechanism:** GameUIAgent's Reflection Controller ([arxiv 2603.14724](https://arxiv.org/abs/2603.14724)). Render synthesised candidate next to three real instances; VLM scores along `(palette fit, radius fit, padding rhythm, type rhythm)`; mutate, bounded iterations.
**Coverage:** closes the loop when B's labelling is off in aggregate but visually obvious on render.
**Cost:** 3-5 VLM calls per generation, per component — at scale this is the expensive path.
**Failure modes:** Rendering-Evaluation Fidelity Principle — a partial render (missing asset, wrong padding one dimension) induces VLM to nitpick the wrong axes; we're blind to this until RenderVerifier is solid (ADR-007 tracks, `feedback_unified_verification_channel.md`).
**Prior art:** GameUIAgent directly; SpecifyUI's multi-agent generator loop; our own ADR-007.

## 6. Cold-start

Three tiers, selected by corpus size:

1. **Dense** (≥ 50 instances of the catalog type, covering ≥ 3 visually-distinct variants): run A + B, result is ground truth.
2. **Thin** (5–50 instances, 1–2 variants visible): run A + B where possible; for missing variants, **back-fill from an ingested reference system** (shadcn-registry expressed in our same `role_binding` schema) and *recolour* its slot values into the corpus palette using nearest-neighbour in OKLCH. This is the Material You move — transplant the skeleton, repaint the atoms.
3. **Sparse** (< 5 instances): degrade to the full reference system with the corpus's Layer-A tokens (palette + type + spacing + radius); no attempt to induce.

Never prompt the user for variant assignment — the corpus is the source of truth. If we have to ask, we've failed.

## 7. Recommendation + phasing

**v0.1 (ship-now):** A + B (clustering + VLM labelling). Persist as `role_binding (catalog_type, role, slot, token_id, confidence, source)`. Renderer queries this table at Mode-3 time. Acceptance gate: on Dank, ≥ 80 % of catalog types have all their observed variants labelled, ≥ 90 % of rendered Mode-3 buttons pass a three-screen human sanity check (learned from `feedback_auto_inspect_before_human_rate.md` — gate before asking humans, but humans still gate v0.1 release).

**v0.2:** add C (screen-context priors as regularisers) and cold-start back-fill from shadcn-registry. Measure: delta in variant-coverage on a synthetic thin-corpus test (10-screen subset of Dank).

**Deferred:** D (render + critic). Blocked on `KIND_MISSING_ASSET` + full RenderVerifier parity so the critic doesn't chase rendering ghosts (pt-7 reality check).

## 8. Open questions

1. **Vocabulary closure**: can we commit to a closed 48-type × ~6-role matrix, or must we allow `custom_role: string`? Closed is simpler but will miss `ghost-destructive`-style rarities.
2. **Instance minimum**: below what instance count does B's labelling become unreliable? UICrit's 55 % gain was measured at k=5 few-shot; we should pilot at k=3 before committing.
3. **Tokens-Studio interop**: W3C-DTCG has no concept of `role_binding`. Do we emit it as a DTCG extension, a sidecar JSON, or a proprietary table? v0.1 answer: sidecar, upgrade later.
4. **Multi-corpus transfer**: once a project has `role_binding`, can we reuse it cross-project as a bootstrap prior? Probably not without user opt-in, but measuring transferability would validate whether there's a universal role vocabulary worth extracting.

---

*~1,470 words excluding headings.*
