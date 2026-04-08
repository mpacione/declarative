# Declarative Design — Action Taxonomy

Exhaustive catalog of every action the agent can perform against the design system DB and Figma. Organized by tier (table-stakes → high-value), each action specifies inputs, outputs, and what verification looks like.

---

## Tier 1: Cleanup (Mechanical, Low Risk)

Deterministic corrections. Right answer is obvious. Could be fully automated.

### T1.1 — Round Fractional Values
- **Trigger**: `curate-report` flags fractional font sizes (e.g. `36.86px`)
- **Input**: Token ID, suggested rounded value
- **Action**: Update `token_values.resolved_value` and `raw_value`
- **Verify**: Query token value, confirm integer. Re-run `dd validate`.

### T1.2 — Rename Numeric Segments
- **Trigger**: Token name contains numeric segment (e.g. `color.surface.42`)
- **Input**: Token ID, new name derived from usage context
- **Action**: `rename_token(conn, token_id, new_name)`
- **Verify**: Token name updated, all bindings still reference same token ID.

### T1.3 — Merge Perceptually Identical Colors
- **Trigger**: Two color tokens with ΔE < 1.0 (indistinguishable)
- **Input**: Survivor token ID, victim token ID
- **Action**: `merge_tokens(conn, survivor_id, victim_id)`
- **Verify**: Victim deleted, all its bindings now point to survivor.

### T1.4 — Delete Noise Tokens
- **Trigger**: Token with ≤1 binding AND not part of a systematic pattern
- **Input**: Token ID
- **Action**: `reject_token(conn, token_id, cascade=True)`
- **Verify**: Token gone, binding reverted to `unbound`.

### T1.5 — Normalize Spacing Scale
- **Trigger**: Extracted spacing values are arbitrary (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13...)
- **Input**: Target scale (e.g. 4px base: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64)
- **Action**: Merge nearby spacing tokens onto the nearest scale step
- **Verify**: Spacing tokens match the target scale. Bindings redistributed.

---

## Tier 2: Semantic (Requires Design Judgment)

Agent must understand *what the token means* based on where it's used.

### T2.1 — Context-Based Renaming
- **Trigger**: Numeric token name + usage analysis needed
- **Input**: Token ID → agent queries bindings, node names, screen names
- **Action**: Infer role (e.g. "used on 200 card backgrounds" → `color.surface.card`), then `rename_token()`
- **Verify**: Name is meaningful, DTCG-compliant, unique.

### T2.2 — Split Overloaded Token
- **Trigger**: One token used for semantically different purposes (e.g. same blue for links AND primary buttons)
- **Input**: Token ID, list of node IDs to split off, new token name
- **Action**: `split_token(conn, token_id, new_name, node_ids)`
- **Verify**: Two tokens exist, bindings correctly distributed.

### T2.3 — Create Semantic Aliases
- **Trigger**: Primitive tokens exist but no semantic layer
- **Input**: Alias name, target primitive token ID, collection name
- **Action**: `create_alias(conn, alias_name, target_token_id, collection)`
- **Verify**: Alias resolves to primitive value. `v_resolved_tokens` shows chain.

### T2.4 — Group Into T-Shirt Sizes
- **Trigger**: Typography/spacing tokens are numbered instead of scaled
- **Input**: Token type, size mapping (xs, sm, md, lg, xl, 2xl...)
- **Action**: Rename tokens to t-shirt convention, ordered by value
- **Verify**: Names follow scale, values are monotonically increasing.

### T2.5 — Categorize by Role
- **Trigger**: Flat color list with no role hierarchy
- **Input**: Agent analyzes usage patterns across all colors
- **Action**: Rename into role buckets: `surface.*`, `border.*`, `text.*`, `feedback.*`, `brand.*`
- **Verify**: Every color token has a role prefix. No naming collisions.

### T2.6 — Identify and Tag Interactive States
- **Trigger**: Component variants have hover/focus/pressed/disabled states
- **Input**: Component analysis across variant axes
- **Action**: Tag tokens used in state variants, create state-specific aliases
- **Verify**: State tokens exist (e.g. `color.button.primary.hover`).

---

## Tier 3: Generative (Creates New Data in DB)

Goes beyond what extraction found. Agent creates tokens/modes that didn't exist in the Figma file.

### T3.1 — Derive Dark Mode
- **Trigger**: Only light mode exists
- **Input**: Light mode color tokens, dark mode derivation rules
- **Action**: Create `dark` mode. For each color: invert lightness, adjust saturation, preserve hue. Write new `token_values` rows.
- **Verify**: Every color token has both `light` and `dark` mode values. Dark values are perceptually coherent.

### T3.2 — Derive High Contrast Mode
- **Trigger**: Accessibility requirement
- **Input**: Existing color tokens
- **Action**: Create `high-contrast` mode. Maximize contrast ratios, use pure black/white where appropriate.
- **Verify**: All text/background pairs meet WCAG AAA (7:1).

### T3.3 — Create Missing Scale Steps
- **Trigger**: Spacing scale has gaps (e.g. 4, 8, 16 but no 12)
- **Input**: Scale type, base unit, target steps
- **Action**: Insert new tokens for missing steps
- **Verify**: Complete scale exists with no gaps.

### T3.4 — Generate Component Tokens
- **Trigger**: Primitives exist but no component-level tokens
- **Input**: Component name (e.g. "Button"), variant axes
- **Action**: Create component-specific aliases: `color.button.primary.bg` → `color.brand.500`, `color.button.primary.text` → `color.surface.white`
- **Verify**: Component token set is complete (bg, text, border, hover, focus, disabled for each variant).

### T3.5 — Bootstrap System From Single Screen
- **Trigger**: User provides one well-designed screen as reference
- **Input**: Screen ID
- **Action**: Extract implicit scale/palette/type system from that screen, generate full token set, apply to all other screens
- **Verify**: Token coverage increases across all screens.

---

## Tier 4: Structural (Changes System Shape)

Affects collections, modes, or the overall organization of the token system.

### T4.1 — Split Primitives and Semantics
- **Trigger**: All tokens are in one flat collection
- **Input**: Desired collection structure
- **Action**: Create `Primitives` and `Semantic` collections. Move raw tokens to Primitives, create aliases in Semantic.
- **Verify**: Two collections exist. Semantic tokens all alias Primitives.

### T4.2 — Add Mode
- **Trigger**: New context needed (dark, compact, high-contrast, brand-b)
- **Input**: Mode name, derivation rules
- **Action**: Create mode in all collections, populate values
- **Verify**: Mode completeness validation passes.

### T4.3 — Restructure Naming Convention
- **Trigger**: Naming doesn't match target system (e.g. migrating from type/role/variant to role/type/variant)
- **Input**: Mapping rules
- **Action**: Mass rename all tokens
- **Verify**: All names match new convention. No broken references.

### T4.4 — Re-cluster With Different Parameters
- **Trigger**: Clustering was too aggressive or too loose
- **Input**: New threshold (e.g. ΔE 1.5 instead of 2.0)
- **Action**: Delete existing tokens of that type, re-run clustering
- **Verify**: New token count, coverage percentage, no orphaned bindings.

### T4.5 — Import External Token Set
- **Trigger**: Adopting an existing system (Radix, shadcn, Material)
- **Input**: Token JSON/CSS from external system
- **Action**: Parse external tokens, create in DB, attempt to map existing bindings to closest match
- **Verify**: External tokens imported, binding coverage maintained or improved.

---

## Tier 5: Conjure — Compose (Read DB → Create in Figma)

The core value proposition. Agent reads the design vocabulary from DB, creates new designs in Figma using real tokens and components. Grouped by capability: transformations first (modify existing), then composition (create new), then intelligence (analyze and infer).

### Group A: Transform (modify existing nodes)

#### T5.1 — Systematic Refactor
- **Trigger**: "Migrate all screens from this old color to the new one"
- **Input**: Old token ID, new token ID, scope (all screens or specific ones)
- **Action**: Rebind all nodes from old token to new token in DB. Then push rebinding to Figma.
- **Verify**: No bindings reference old token. Figma nodes updated.
- **Figma required**: Yes (for the push step)

#### T5.2 — Theme Application
- **Trigger**: "Apply my design system to this wireframe"
- **Input**: Unstyled Figma frame + DB vocabulary
- **Action**: Walk frame tree, match each node to appropriate tokens (frames → surface colors, text → type tokens, spacing → space tokens). Bind all.
- **Verify**: Frame is now fully tokenized. Visual appearance follows system.
- **Figma required**: Yes

#### T5.3 — Generate Variant States
- **Trigger**: "Add hover, focus, disabled states to all buttons"
- **Input**: Component ID, list of desired states
- **Action**: For each existing button variant, create state variants. Derive state-specific values (hover = darken 10%, disabled = 50% opacity) from existing token values.
- **Verify**: New variants exist. State values are systematically derived, not random.
- **Figma required**: Yes

#### T5.4 — Layout Reflow
- **Trigger**: "Change this 2-column grid to a single-column stack"
- **Input**: Frame ID, target layout description
- **Action**: Modify auto-layout settings (direction, sizing, alignment) on existing frame. Reorder children if needed. Preserve all token bindings.
- **Verify**: Layout changed. No bindings lost. Visual hierarchy maintained.
- **Figma required**: Yes

#### T5.5 — Component Instance Override
- **Trigger**: "Swap the icon in all instances of this button to the new one"
- **Input**: Component ID or instance scope, property name, new override value
- **Action**: Query all instances of the component. Apply property overrides (TEXT, BOOLEAN, INSTANCE_SWAP) via Plugin API. Update `instance_overrides` in DB.
- **Verify**: All targeted instances show the override. DB reflects the change.
- **Figma required**: Yes

### Group B: Compose (create new nodes)

#### T5.6 — Duplicate Screen With Modifications
- **Trigger**: "Copy screen 12 but change the header to show the logged-out state"
- **Input**: Source screen ID, list of modifications (text changes, component swaps, visibility toggles)
- **Action**: Clone the screen's node tree in Figma. Apply modifications. All token bindings carried forward from source.
- **Verify**: New screen exists. Modifications applied. All token bindings intact.
- **Figma required**: Yes

#### T5.7 — Design System Documentation Page
- **Trigger**: "Create a component spec page for the Button"
- **Input**: Component ID from DB
- **Action**: Generate a Figma page showing all variants in a grid, with labels, spacing specs, token names annotated. Like a Storybook page but in Figma.
- **Verify**: Page exists with all variants rendered. Annotations match DB.
- **Figma required**: Yes

#### T5.8 — Compose Component From Prompt
- **Trigger**: "Create a notification banner component"
- **Input**: Description, desired variants, slots
- **Action**: Agent creates component set in Figma with variants (info/warning/error/success), proper auto-layout, all values from tokens. Registers in DB.
- **Verify**: Component has correct variants. All values are token-bound. Slots are configurable.
- **Figma required**: Yes

#### T5.9 — Compose Screen From Prompt
- **Trigger**: "Build me a settings page"
- **Input**: Natural language description + DB vocabulary (tokens, components, screen patterns)
- **Action**: Agent queries DB for relevant components and tokens. Composes frame in Figma using composition template from `patterns` table. Every color/type/spacing value comes from a token — nothing hardcoded.
- **Verify**: Screenshot matches intent. All nodes are bound to tokens (zero hardcoded values). Layout uses auto-layout.
- **Figma required**: Yes (MCP)

#### T5.10 — Responsive Adaptation
- **Trigger**: "Make an iPhone version of this iPad screen"
- **Input**: Source screen ID, target device dimensions
- **Action**: Read source screen composition tree from DB. Re-compose at target dimensions, adjusting layout (columns → stack, horizontal → vertical), maintaining all token bindings.
- **Verify**: New screen exists at target dimensions. Same tokens used. Layout adapts sensibly.
- **Figma required**: Yes

#### T5.11 — Flow/Multi-Screen Generation
- **Trigger**: "Build an onboarding flow — splash, email, password, confirm, welcome"
- **Input**: Flow description, screen count, DB vocabulary
- **Action**: Compose each screen, link with prototype connections, maintain consistent token usage across flow.
- **Verify**: All screens exist. Navigation works. Consistent system usage.
- **Figma required**: Yes

### Group C: Intelligence (analyze and infer)

#### T5.12 — Pattern Extraction → Template
- **Trigger**: "This card layout appears on 12 screens, save it as a pattern"
- **Input**: Representative node subtree (or agent detects repeated subtrees)
- **Action**: Extract common structure into a composition template. Store in `patterns` table with parameterized slots. Does NOT create Figma components — produces reusable DB templates for T5.9.
- **Verify**: Pattern stored. Template is valid (all referenced tokens/components exist).
- **Figma required**: No (reads DB only)

#### T5.13 — Pattern Extraction → Component
- **Trigger**: "This card layout appears on 12 screens, make it a component"
- **Input**: Representative node subtree (or agent detects repeated subtrees)
- **Action**: Extract common structure, create component with proper variants/slots, replace all instances in Figma with component instances.
- **Verify**: Component created. Original nodes replaced with instances. Visual output identical.
- **Figma required**: Yes

#### T5.14 — Screenshot to System-Native
- **Trigger**: User provides screenshot/wireframe + "recreate this with my system"
- **Input**: Image + DB vocabulary
- **Action**: Analyze image (colors, layout, typography). Match observed values to closest tokens in DB. Compose in Figma using matched tokens and available components.
- **Verify**: Visual similarity to reference. All values are token-bound.
- **Figma required**: Yes

---

## Tier 6: Sync — Push/Pull Between DB and Figma

Bidirectional sync operations. Required infrastructure for Tier 5 verification.

### T6.1 — Push Tokens as Figma Variables
- **Trigger**: After curation, before conjure
- **Input**: All curated tokens in DB
- **Action**: Create Figma variable collections + variables via `figma_setup_design_tokens` MCP. Write back variable IDs to `figma_variables` table.
- **Verify**: Variables visible in Figma. IDs stored in DB for future reference.
- **Figma required**: Yes (MCP)

### T6.2 — Rebind Nodes to Variables
- **Trigger**: After pushing variables
- **Input**: All bound nodes + their token mappings
- **Action**: Generate rebinding script. Execute via `figma_execute`. Each node's fills/strokes/effects get bound to the corresponding Figma variable.
- **Verify**: Nodes in Figma show variable bindings (not hardcoded values).
- **Figma required**: Yes (MCP)

### T6.3 — Pull Variable Changes
- **Trigger**: Designer changed variables in Figma directly
- **Input**: Current Figma variable state
- **Action**: Read variables via `figma_get_variables`, compare to DB, detect drift.
- **Verify**: Drift report shows correct diffs.
- **Figma required**: Yes (MCP)

### T6.4 — Reconcile Drift
- **Trigger**: Drift detected between DB and Figma
- **Input**: Drift report with per-token diffs
- **Action**: User chooses: accept Figma values → update DB, or reject → push DB values to Figma.
- **Verify**: DB and Figma are in sync. Drift report shows zero diffs.
- **Figma required**: Yes (MCP)

### T6.5 — Re-extract (Incremental)
- **Trigger**: New screens added to Figma since last extraction
- **Input**: File key, existing DB
- **Action**: Fetch file structure, identify new/changed screens, extract only those. Preserve existing curation.
- **Verify**: New screens appear in DB. Existing tokens/bindings unchanged.
- **Figma required**: Yes (REST API via CLI)

---

## Testing Strategy

### DB-only actions (Tiers 1-4):
Test by running the action, then querying the DB to verify state. No Figma connection needed. Can be fully automated in pytest.

### Figma-dependent actions (Tiers 5-6):
Require pushing tokens as variables first (T6.1), then composing/rebinding, then verifying via screenshot or node inspection. Testing requires:
1. A test Figma file (or a page in the existing file)
2. `FIGMA_ACCESS_TOKEN` set
3. MCP connection for `figma_execute` / `figma_setup_design_tokens`

### Recommended test order:
1. **T6.1** (push variables) — unlocks all Figma verification
2. **T1.1–T1.5** (cleanup) — prove the loop works
3. **T2.1–T2.6** (semantic) — prove judgment works
4. **T3.1** (dark mode) — first generative action
5. **T5.1** (compose screen) — first conjure action
6. **T5.2** (compose component) — second conjure action
7. Everything else in priority order

### Verification pattern for Conjure:
```
1. Agent reads DB vocabulary
2. Agent composes in Figma via MCP
3. Agent takes screenshot → visual check
4. Agent queries created nodes → confirms token bindings (not hardcoded)
5. Agent writes nodes back to DB for tracking (optional)
```
