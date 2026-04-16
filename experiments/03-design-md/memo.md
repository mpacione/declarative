# Experiment 3 — design.md auto-generator

**Open question answered:** whether design.md should be a prompt-cache payload
or a retrieval target. Directly measured on Dank Experimental.

## 1. What got built

- `generator.py` — a single-command `dd design-md generate`-style extractor
  that reads the MLIR SQLite database and writes a markdown design spec.
  Command: `python generator.py --db Dank-EXP-02.declarative.db --out design.md`.
- `measure.py` — token-counts the output with `tiktoken` (cl100k_base) and
  emits `size-analysis.md` plus a JSON section-map consumable by downstream
  experiments.
- `design.md` — the generated artefact for Dank Experimental. Nine sections:
  metadata header, Component inventory (129 CKR entries with parent + sibling
  adjacency context), Token palette (raw-value census since the `tokens` table
  is empty post-restore), Typography scale (53 distinct combos, top-25
  rendered), Spacing rhythm (base-grid detection), Adjacencies (top container
  child sequences with percentages), Screen archetypes (structural
  fingerprint with anonymous-frame runs collapsed), Missing / gaps (48-type
  catalog × CKR × raw-node coverage matrix), Designer TODO stubs.
- `activity.log` — timestamped trace of each section's generation with
  counts and warning signals (e.g. `token_palette | warning | tokens table empty`).

Total artefact: **36,191 chars / 11,551 tokens** — well under the 50K
prompt-cache threshold.

## 2. Easy / hard / surprising

- **Trivial:** header, typography, gaps, radius (querying `nodes.corner_radius`
  directly is fuller than the token-binding census). The designer-TODO
  section is a static template.
- **Non-trivial:** adjacencies. Had to resolve CKR display names for
  container titles (parent INSTANCEs referenced by component-key hash are
  useless to the LLM) and emit child sequences with consistent naming. Also
  had to decide where to stop — stopped at top-12 containers with ≥ 3
  instances to cap variance.
- **Surprising:** the **Component-inventory section is 52% of the total
  tokens** on its own, dwarfing everything else. With 129 CKR entries it is
  the dominant cost, and extrapolating linearly to a 500-entry system
  already pushes total past 23K tokens.
- **Also surprising:** the base-grid detector said **2 px**, not 4 or 8.
  Dank uses `10 px` (43% of all spacing values) and `14 px` (20%) as its
  primary magnitudes, neither of which divides by 4 cleanly. That is a
  meaningful stylistic signal: this file does not follow the 8-point grid
  most production design systems ship with.

## 3. Data quality issues encountered

- **`tokens` table is empty** — clustering has not been re-run since the
  last restore. Handled by surfacing the raw `node_token_bindings` census
  and flagging the degradation in the rendered section. The rest of the
  pipeline still works.
- **`component_type_catalog` is empty in the DB** — the 48-type catalog
  lives in `dd/catalog.py` as a Python tuple, not in the SQLite table. The
  generator imports `CATALOG_ENTRIES` directly rather than relying on the
  view.
- **Duplicate CKR display names** — several distinct `component_key` values
  share a display name (e.g. `_Key` × 3, `icon/more` × 2, `icon/edit` × 2).
  Disambiguated by appending the first 8 chars of the key on collisions.
- **Over-inclusive `v_color_census`** — the view `LIKE 'fill%'`s pulls in
  `strokeWeight`, `fill.0.opacity`, `stroke.0.opacity` etc., which appear
  as numeric values in the palette. Bypassed by querying bindings directly
  with `property LIKE 'fill.%.color' OR property LIKE 'stroke.%.color'`.
- **Card / sheet / dialog as bare frames** — the Gap matrix shows `card` and
  `sheet` are present as raw node names but have *zero* shared components.
  This is a genuine finding about the design system's maturity: important
  containment components have not been componentised.
- **`screen_component_instances` is empty** — so the "semantic" screen-
  archetype path in `dd/screen_patterns.py` returns nothing. Fell back to a
  structural-fingerprint clustering (direct children of the screen root,
  anonymous-frame runs collapsed). Seven archetypes span all 204 app
  screens; mostly iPhone-vs-iPad layout variants.
- **Sibling counts are inflated by self-joins** — a component that lives in
  a homogeneous stack (e.g. `button/large/translucent` in `button/toolbar`)
  shows itself as its own top sibling. That's a real and useful signal
  but worth reading as "stacks with siblings of the same type", not as a
  distinct neighbour.

## 4. What v0.2 adds that v0.1 shouldn't

- **Embeddings-based adjacency clustering.** Right now two frames with
  different names but identical child-type sequences produce two separate
  adjacency entries. An embedding over the child sequence would collapse
  these. v0.1 fine without it; v0.2 would reduce Section Adjacencies by
  maybe 30% and group structurally-equivalent cards together.
- **Slot-aware component inventory.** Once `component_slots` is populated
  (the extractor exists but was never run on Dank per the planning doc),
  each row could also report *"slots present"* — a much cleaner signal for
  the LLM than scraped parent-sibling tuples.
- **DTCG token export.** Once `dd cluster` runs, the Token palette becomes
  a canonical DTCG JSON fragment, not a raw-value census. That maps
  directly to the synthetic-generation prompt.
- **Voice / intent TODO suggestions via LLM.** Feed design.md + a
  screenshot of 3 representative screens to a vision model, ask it to draft
  the Voice section as a designer-reviewable suggestion. Classifier, not
  authority.
- **Delta generation.** When a designer edits a TODO section, store the
  edits separately so re-running the extractor only updates the auto-
  sections. Today it round-trips through a full regeneration.

## 5. Where this lives in `dd/`

Promote `generator.py` to **`dd/design_md.py`** with three entry points:

```python
def build(conn: sqlite3.Connection, file_id: int) -> str: ...
def write(conn, file_id, path: Path) -> None: ...
def measure(text: str) -> SizeReport: ...
```

CLI wiring in `dd/cli.py`:

```
dd design-md generate --file <file_id> --out design.md
dd design-md measure --input design.md
dd design-md section <name> --input design.md
```

Plug it into the pipeline:

1. **After `dd ingest`** — emit a fresh design.md as part of the post-
   extraction summary, alongside the existing round-trip parity report.
2. **Before `dd generate-prompt`** — include design.md (tokens only) in
   the LLM context-bundle assembly.
3. **As a skill artefact** — ship a `SKILL.md` that maps the
   Experimentent-C design-md skill directly to this module, so a
   Claude/Codex user can invoke it on any project's DB without knowing
   about `dd/`.

The dependencies for this are: `dd.catalog` (already imported), the
SQLite connection (exists), and the census views (exist). Nothing new
required. The v0.2 additions above can each slot into `dd/design_md/`
as a sibling module once we decide to splurge on them.

## Numbers at a glance

| Metric | Value |
| --- | --- |
| Total chars | 36,191 |
| Total tokens (cl100k_base) | **11,551** |
| Largest section | Component inventory (52% of total) |
| CKR entries covered | 129 |
| Screen archetypes (top-7) | 7 (covering ~132/204 app screens) |
| Catalog types with CKR match | 9 / 48 |
| Catalog types with any match | 12 / 48 |
| Verdict | prompt-cache (< 50K threshold) |
