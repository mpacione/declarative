---
taskId: TASK-040
title: "Implement curation operations (accept, rename, merge, split, reject, alias)"
wave: wave-4
testFirst: true
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - dd/curate.py
verify:
  - type: typecheck
    command: 'python -c "from dd.curate import accept_token, rename_token, merge_tokens, split_token, reject_token, create_alias"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_curation.py -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-040: Implement curation operations (accept, rename, merge, split, reject, alias)

## Spec Context

### From Technical Design Spec -- Phase 6: Curation Review

> The user sees:
> 1. **Token list** -- proposed names, types, resolved values, usage counts (from `v_token_coverage`).
> 2. **Low-confidence bindings** -- anything with `confidence < 0.9` for manual review.
> 3. **Orphan values** -- bindings still `unbound` after clustering (one-off values, likely design inconsistencies).
>
> User actions:
> - **Accept** -- token stays, tier promoted to `curated`.
> - **Rename** -- update `tokens.name`.
> - **Merge** -- combine two tokens, update all bindings to point to the survivor.
> - **Split** -- break a token into two, reassign bindings.
> - **Reject** -- delete token, bindings revert to `unbound`.
> - **Create alias** -- new token with `tier = aliased`, `alias_of` pointing to a curated token. Alias depth enforced to 1 by DB trigger.
>
> After curation, remaining `unbound` bindings are either:
> - Intentionally hardcoded (one-off values, not worth tokenizing).
> - Flagged as design debt for future cleanup.

### From User Requirements Spec -- NFR-9

> NFR-9: **Backup before destructive ops** -- Before any bulk curation operation (merge, reject, re-extract), the system creates a timestamped DB snapshot (SQLite `VACUUM INTO` or file copy). Snapshots are rotatable (keep last 5).

### From User Requirements Spec -- UC-2: Cluster

> - User reviews proposals -- accepts, renames, merges, splits, or rejects.
> - Accepted tokens promoted to `tier = curated`.

### From schema.sql -- tokens table

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of        INTEGER REFERENCES tokens(id),
>     description     TEXT,
>     figma_variable_id TEXT,
>     sync_status     TEXT NOT NULL DEFAULT 'pending'
>                     CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(collection_id, name)
> );
> ```

### From schema.sql -- alias depth triggers

> ```sql
> CREATE TRIGGER trg_alias_depth_check
> BEFORE INSERT ON tokens
> WHEN NEW.alias_of IS NOT NULL
> BEGIN
>     SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
>     WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
> END;
>
> CREATE TRIGGER trg_alias_depth_check_update
> BEFORE UPDATE OF alias_of ON tokens
> WHEN NEW.alias_of IS NOT NULL
> BEGIN
>     SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
>     WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
> END;
> ```

### From schema.sql -- node_token_bindings table

> ```sql
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id              INTEGER PRIMARY KEY,
>     node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property        TEXT NOT NULL,
>     token_id        INTEGER REFERENCES tokens(id),
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     confidence      REAL,
>     binding_status  TEXT NOT NULL DEFAULT 'unbound'
>                     CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden')),
>     UNIQUE(node_id, property)
> );
> ```

### From schema.sql -- token_values table

> ```sql
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
> ```

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`
> - `backup_db(source_path: str) -> str`

### From dd/types.py (produced by TASK-003)

> Exports:
> - `Tier` enum: EXTRACTED, CURATED, ALIASED
> - `BindingStatus` enum: UNBOUND, PROPOSED, BOUND, OVERRIDDEN

## Task

Create `dd/curate.py` implementing all curation operations from Phase 6. Each operation is a standalone function that modifies the DB. Destructive operations (merge, reject, bulk accept) call `backup_db` first per NFR-9.

1. **`accept_token(conn, token_id: int) -> dict`**:
   - UPDATE `tokens SET tier = 'curated', updated_at = strftime(...)` WHERE `id = ?`.
   - UPDATE all `node_token_bindings SET binding_status = 'bound'` WHERE `token_id = ?` AND `binding_status = 'proposed'`.
   - Return: `{"token_id": int, "bindings_updated": int}`.
   - Raise `ValueError` if token doesn't exist.

2. **`accept_all(conn, file_id: int, db_path: str | None = None) -> dict`**:
   - Bulk accept: promote ALL extracted tokens to curated and all proposed bindings to bound.
   - If `db_path` is provided (not `:memory:`), call `backup_db(db_path)` first.
   - UPDATE `tokens SET tier = 'curated', updated_at = ...` WHERE `tier = 'extracted'` AND collection_id in collections for this file_id.
   - UPDATE `node_token_bindings SET binding_status = 'bound'` WHERE `binding_status = 'proposed'` AND node_id is in nodes for this file_id.
   - Return: `{"tokens_accepted": int, "bindings_updated": int}`.

3. **`rename_token(conn, token_id: int, new_name: str) -> dict`**:
   - Validate `new_name` matches DTCG dot-path pattern: `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$`.
   - Check uniqueness within the token's collection: `SELECT COUNT(*) FROM tokens WHERE collection_id = ? AND name = ? AND id != ?`.
   - UPDATE `tokens SET name = ?, updated_at = ...` WHERE `id = ?`.
   - Return: `{"token_id": int, "old_name": str, "new_name": str}`.
   - Raise `ValueError` if name is invalid or not unique.

4. **`merge_tokens(conn, survivor_id: int, victim_id: int, db_path: str | None = None) -> dict`**:
   - Merge `victim` into `survivor`. All bindings pointing to `victim` are reassigned to `survivor`.
   - If `db_path` is provided, call `backup_db(db_path)` first.
   - Verify both tokens exist and are in the same collection.
   - UPDATE `node_token_bindings SET token_id = ?` WHERE `token_id = ?` (victim -> survivor).
   - DELETE `token_values` WHERE `token_id = victim_id` (cascade should handle this, but be explicit).
   - DELETE `tokens` WHERE `id = victim_id`.
   - Return: `{"survivor_id": int, "victim_id": int, "bindings_reassigned": int}`.
   - Raise `ValueError` if either token doesn't exist or they're in different collections.

5. **`split_token(conn, token_id: int, new_name: str, binding_ids: list[int]) -> dict`**:
   - Create a new token with `new_name` in the same collection, same type, tier='extracted'.
   - Copy `token_values` from the original token to the new token.
   - Reassign the specified `binding_ids` from the original token to the new token.
   - Validate `new_name` follows DTCG pattern and is unique.
   - Validate all `binding_ids` currently reference `token_id`.
   - Return: `{"original_token_id": int, "new_token_id": int, "bindings_moved": int}`.
   - Raise `ValueError` if name invalid, bindings don't belong to the token, or name not unique.

6. **`reject_token(conn, token_id: int, db_path: str | None = None) -> dict`**:
   - Reject a token: bindings revert to unbound, token is deleted.
   - If `db_path` is provided, call `backup_db(db_path)` first.
   - UPDATE `node_token_bindings SET token_id = NULL, binding_status = 'unbound', confidence = NULL` WHERE `token_id = ?`.
   - DELETE `tokens` WHERE `id = ?` (CASCADE deletes token_values).
   - Return: `{"token_id": int, "bindings_reverted": int}`.
   - Raise `ValueError` if token doesn't exist.

7. **`create_alias(conn, alias_name: str, target_token_id: int, collection_id: int) -> dict`**:
   - Create a new token with `tier = 'aliased'` and `alias_of = target_token_id`.
   - Validate `alias_name` follows DTCG pattern and is unique within the collection.
   - Validate target token exists and is NOT itself an alias (the DB trigger enforces this, but check proactively for a better error message).
   - INSERT into `tokens` (collection_id, name=alias_name, type=target_token_type, tier='aliased', alias_of=target_token_id).
   - Return: `{"alias_id": int, "alias_name": str, "target_id": int, "target_name": str}`.
   - Raise `ValueError` if name invalid, not unique, target doesn't exist, or target is itself an alias.

8. **Internal helper `_validate_dtcg_name(name: str) -> bool`**:
   - Return True if name matches `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$`.
   - Used by rename_token, split_token, create_alias.

All functions should import `sqlite3`, `json`, `re`, and import `backup_db` from `dd.db`.

## Acceptance Criteria

- [ ] `python -c "from dd.curate import accept_token, accept_all, rename_token, merge_tokens, split_token, reject_token, create_alias"` exits 0
- [ ] `accept_token` promotes tier to 'curated' and binding_status to 'bound'
- [ ] `accept_all` bulk-promotes all extracted tokens and proposed bindings
- [ ] `accept_all` calls `backup_db` when db_path is provided
- [ ] `rename_token` updates the name and validates DTCG pattern
- [ ] `rename_token` raises ValueError for invalid names or duplicates
- [ ] `merge_tokens` reassigns all victim bindings to survivor
- [ ] `merge_tokens` deletes the victim token and its values
- [ ] `merge_tokens` raises ValueError if tokens are in different collections
- [ ] `split_token` creates a new token and moves specified bindings
- [ ] `split_token` copies token_values from original to new token
- [ ] `reject_token` reverts bindings to unbound and deletes the token
- [ ] `create_alias` creates a token with tier='aliased' and alias_of set
- [ ] `create_alias` raises ValueError if target is itself an alias
- [ ] DTCG name validation rejects "Invalid Name", "UPPERCASE", "123start"
- [ ] DTCG name validation accepts "color.surface.primary", "space.4", "type.body.md"

## Notes

- The `backup_db` function from `dd.db` returns empty string for `:memory:` databases. Curation functions should pass `db_path` through -- the caller provides it or None.
- The alias depth check is enforced both by the DB trigger and by proactive validation in `create_alias`. The proactive check gives a better error message; the trigger is the safety net.
- `merge_tokens` is the most complex operation. The key invariant: after merge, zero bindings reference the victim token, and the victim token is deleted.
- `split_token` is the inverse of merge: it creates a new token and moves a subset of bindings. The original token keeps the remaining bindings.
- All operations should commit within the function (not rely on external commit).