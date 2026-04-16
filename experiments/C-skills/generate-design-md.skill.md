---
name: generate-design-md
description: Auto-generate a design.md style snapshot from an already-extracted Figma file. Produces a human-readable markdown document describing the project's components, tokens, typography scale, spacing rhythm, common adjacencies, and screen archetypes — all derived from the MLIR. Designer reviews and edits the output; the edited design.md becomes the authoritative style context for synthetic generation.
when_to_use: After extract-figma has populated the database. User phrases like "summarize my design system", "what does this Figma file look like", "make a style guide from this", "prep for generation". Also useful as prep before generate-screen.
requires:
  - An existing declarative-build SQLite database with the IR
---

# generate-design-md

Writes a `design.md` style snapshot extracted from the IR. Covers:

- Component inventory — each CKR entry with a one-line role plus the
  top-3 observed adjacencies.
- Token palette — colors, spacing, typography, radius, effects,
  opacity. Grouped by collection, with usage counts.
- Typography scale — distinct font × weight × size combinations in use.
- Spacing rhythm — detected base grid (4px, 8px, 12px, ...) plus
  off-grid anomalies.
- Adjacency patterns — per container-capable type (cards, nav bars,
  dialogs), the top 3-5 observed internal compositions.
- Screen archetypes — clustered top-level structural fingerprints.
- Gaps — catalog types that this file does NOT have (important for
  synthetic generation to know what's not available).
- Designer-authored sections (placeholders) — voice, intent
  conventions, exclusions, style lineage. These need human input; the
  skill emits TODO blocks for the designer to fill.

## Inputs

Required:
- `db` — path to the SQLite database.

Optional:
- `out` — output path. Default: `design.md` in the database's directory.
- `adjacency_top_k` — how many adjacencies to report per container
  type. Default: 5.
- `include_usage_counts` — boolean, default true. Set false for a
  cleaner markdown without numeric clutter.

## Behaviour

1. Load the IR from the database.
2. For each CKR entry, derive role + adjacency stats from `parent_id`
   and `sort_order` patterns in the `nodes` table.
3. Pull token data from `tokens`, `token_values`, `token_modes` tables.
   If clustering hasn't run, emit a note.
4. Detect spacing grid via modal analysis on padding + item_spacing
   values.
5. Cluster internal structures for each container-type using immediate-
   child type sequences.
6. Cluster top-level screen structures for archetypes.
7. Diff `component_type_catalog` against CKR for gaps.
8. Emit markdown with all sections filled + TODO blocks for designer-
   authored content.
9. Report output path + approximate token count (tiktoken
   `cl100k_base`).

## Outputs

- `design.md` — the style snapshot.
- A summary: section count, total approximate tokens, any sections
  that couldn't be populated (e.g. "token palette empty because
  clustering hasn't run yet").

## What this skill does NOT do

- Does not generate anything. Read-only against the database plus
  statistical analysis.
- Does not ask the designer questions. The TODO blocks mark where
  human input is required.
- Does not write to the Figma file. Pure extraction.
- Does not run clustering. If tokens are missing, the skill notes the
  gap and proceeds; user can run `dd cluster` + `dd accept-all`
  separately.

## Example usage

```
User: "Summarize the design system in my extracted file."

Assistant runs:
  dd design-md generate --db my-app.declarative.db --out design.md

Reports:
  ✓ design.md written. 143 CKR components documented. 47 spacing
    anomalies flagged. 89 tokens in palette. Approx 28,400 tokens
    (well under prompt-cache budget).
  ⚠ Token clustering has not run; palette pending. Run 'dd cluster'
    + 'dd accept-all' to populate.
  ⚠ 4 sections are TODO for designer: voice, intent conventions,
    exclusions, style lineage.
```

## Typical chain

1. `extract-figma` populates the database.
2. `generate-design-md` writes a v1 design.md.
3. Designer reviews and edits, filling TODO sections.
4. `generate-screen` uses the designer-edited design.md as its primary
   style-context input.
