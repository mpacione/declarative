# Learnings Log

Accumulated insights from building and testing the curation pipeline. These inform the design of `dd push` and the agent protocol.

---

## Figma Push

### Delete + Recreate vs Incremental Sync
- **Current approach**: Delete all collections, recreate from DB. Works but loses Figma variable IDs.
- **Target approach**: Incremental sync — update existing variables, create new ones, delete removed ones.
- **Blocker**: We don't write back Figma variable IDs to the DB after creation. Need `writeback_variable_ids()`.
- **Risk with delete/recreate**: If any Figma nodes are bound to variables, deleting the variable breaks the binding. Incremental sync preserves bindings.

### Batching
- `figma_setup_design_tokens` creates a collection + up to 100 tokens in one call.
- `figma_batch_create_variables` adds tokens to an existing collection (also 100 max).
- Typography (164 tokens) requires 2 calls: first 100 via `setup_design_tokens`, remaining 64 via `batch_create_variables` using the collection ID from the first call.
- **Automation need**: The `dd push` CLI command must auto-batch and handle this split transparently.

### Duplicate Collections
- If you call `figma_setup_design_tokens` with a collection name that already exists, it creates a SECOND collection with the same name. No upsert behavior.
- **Mitigation**: Always check for existing collections and delete or reuse them before creating.

### Type Conversion
- DB stores all values as strings. Figma needs actual numbers for FLOAT, strings for STRING.
- Opacity was stored as STRING type in DB but Figma needs FLOAT. The export layer must handle this.
- **Decision needed**: Store both native type and string in DB? Or just convert at export time?
- **Current approach**: Convert at export time. Works but fragile — easy to miss a type.

### Async Plugin API
- `figma_execute` with async code returns `undefined` because the promise isn't awaited at the top level.
- **Workaround**: Use `console.log("PREFIX:" + JSON.stringify(data))` then parse from `figma_get_console_logs`.
- **Better approach**: Use dedicated MCP tools (`figma_setup_design_tokens`, `figma_batch_create_variables`, `figma_batch_update_variables`) which handle async properly and return structured data.
- **Rule**: Never use `figma_execute` for async operations when a dedicated tool exists.

---

## Curation Operations

### split_token() Doesn't Inherit Tier
- When splitting a token, the new token gets `tier='extracted'` instead of inheriting the parent's `tier='curated'`.
- **Workaround**: Manually update tier after split.
- **Fix needed**: `split_token()` should copy the parent token's tier to the new token.

### split_token() Takes binding_ids, Not node_ids
- The SKILL.md documented `node_ids` but the actual API uses `binding_ids`.
- **Reason**: A node can have multiple bindings (fill + stroke), and you might want to split only the fill binding.
- **SKILL.md updated**: Yes, corrected.

### create_alias() Takes collection_id, Not collection Name
- Need to create or find the collection first, then pass the integer ID.
- **Workflow**: Check if "Semantic" collection exists → create if not → pass ID to `create_alias()`.

### Naming Collisions During Split
- `color.brand.blue` already existed when we tried to split the blue fill bindings into that name.
- **Mitigation**: Always check for existing token names before splitting. Use a unique name or append a disambiguator.

### DTCG Pattern Was Too Strict
- Original: `^[a-z][a-z0-9]*(\.[a-z0-9]+)*$` — rejected camelCase like `fontSize`.
- Fixed: `^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)*$` — allows camelCase in property suffixes.
- Both `validate.py` and `curate.py` had the old pattern and needed updating.

---

## Extraction

### REST API Extraction is Fast and Reliable
- 338 screens, 86K nodes, 205K bindings in 135 seconds via CLI.
- Batches of 10 screens per API call. Rate limiting handled with exponential backoff.
- Zero failures on the Dank (Experimental) file.

### Color Clustering Crashed on Gradients
- `fill.0.gradient` bindings have `resolved_value='gradient'` which can't be parsed as hex.
- **Fix**: Filter the SQL query to only `fill.%.color` and `stroke.%.color` patterns, and require `resolved_value LIKE '#%'`.

### Fractional Values From Figma Scaling
- Figma produces values like `36.85981369018555px` when frames are scaled.
- These need rounding during curation (T1.1), not extraction — extraction should capture exactly what Figma reports.

---

## Architecture

### CLI for Deterministic, Agent for Judgment
- Extraction, clustering, validation, export = CLI commands. No judgment needed.
- Renaming, merging, splitting, aliasing, dark mode = Agent operations. Require context and design knowledge.
- **The curation report bridges them**: `dd curate-report --json` gives the agent a structured list of issues to act on.

### The Push Problem
- Every DB change needs to be synced to Figma. Currently this is manual (7+ MCP calls per sync).
- **Target**: `dd push` command that reads DB state, diffs against Figma state, and applies incremental changes.
- **Dependency**: Need to store Figma variable IDs in DB for incremental sync.
- **Discovery**: Working through tiers first to learn all payload types before building the CLI command.

### Curation → Push → Verify Should Be Atomic
- Currently 3 manual steps: modify DB → push to Figma → read back and verify.
- **Target**: `dd push --verify` that does all three.
- Still discovering what "verify" means for each token type (color spot-check vs typography full comparison).
