"""Curation operations for design tokens."""

import re
import sqlite3
from typing import Optional

from dd.db import backup_db, insert_token_value


def _validate_dtcg_name(name: str) -> bool:
    """
    Validate a token name follows DTCG dot-path pattern.

    Args:
        name: Token name to validate

    Returns:
        True if valid, False otherwise
    """
    if not name:
        return False
    pattern = r'^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)*$'
    return re.match(pattern, name) is not None


def accept_token(conn: sqlite3.Connection, token_id: int) -> dict:
    """
    Accept a token: promote to curated tier and bind proposed bindings.

    Args:
        conn: Database connection
        token_id: Token to accept

    Returns:
        Dict with token_id and bindings_updated count

    Raises:
        ValueError: If token doesn't exist
    """
    cursor = conn.execute("SELECT id FROM tokens WHERE id = ?", (token_id,))
    if cursor.fetchone() is None:
        raise ValueError(f"Token {token_id} does not exist")

    conn.execute("""
        UPDATE tokens
        SET tier = 'curated', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE id = ?
    """, (token_id,))

    cursor = conn.execute("""
        UPDATE node_token_bindings
        SET binding_status = 'bound'
        WHERE token_id = ? AND binding_status = 'proposed'
    """, (token_id,))
    bindings_updated = cursor.rowcount

    conn.commit()
    return {"token_id": token_id, "bindings_updated": bindings_updated}


def accept_all(conn: sqlite3.Connection, file_id: int, db_path: Optional[str] = None) -> dict:
    """
    Bulk accept all extracted tokens and proposed bindings for a file.

    Args:
        conn: Database connection
        file_id: File to accept tokens for
        db_path: Database path for backup (None for :memory:)

    Returns:
        Dict with tokens_accepted and bindings_updated counts
    """
    if db_path and db_path != ":memory:":
        backup_db(db_path)

    cursor = conn.execute("""
        UPDATE tokens
        SET tier = 'curated', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE tier = 'extracted' AND collection_id IN (
            SELECT id FROM token_collections WHERE file_id = ?
        )
    """, (file_id,))
    tokens_accepted = cursor.rowcount

    cursor = conn.execute("""
        UPDATE node_token_bindings
        SET binding_status = 'bound'
        WHERE binding_status = 'proposed' AND node_id IN (
            SELECT n.id FROM nodes n
            JOIN screens s ON n.screen_id = s.id
            WHERE s.file_id = ?
        )
    """, (file_id,))
    bindings_updated = cursor.rowcount

    conn.commit()
    return {"tokens_accepted": tokens_accepted, "bindings_updated": bindings_updated}


def rename_token(conn: sqlite3.Connection, token_id: int, new_name: str) -> dict:
    """
    Rename a token.

    Args:
        conn: Database connection
        token_id: Token to rename
        new_name: New token name (must be valid DTCG format)

    Returns:
        Dict with token_id, old_name, and new_name

    Raises:
        ValueError: If token doesn't exist, name is invalid, or name already exists
    """
    cursor = conn.execute("SELECT name, collection_id FROM tokens WHERE id = ?", (token_id,))
    token = cursor.fetchone()
    if token is None:
        raise ValueError(f"Token {token_id} does not exist")

    if not _validate_dtcg_name(new_name):
        raise ValueError(f"Invalid DTCG name: {new_name}")

    old_name = token["name"]
    collection_id = token["collection_id"]

    cursor = conn.execute("""
        SELECT COUNT(*) FROM tokens
        WHERE collection_id = ? AND name = ? AND id != ?
    """, (collection_id, new_name, token_id))
    if cursor.fetchone()[0] > 0:
        raise ValueError(f"Token name '{new_name}' already exists in collection")

    conn.execute("""
        UPDATE tokens
        SET name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE id = ?
    """, (new_name, token_id))

    conn.commit()
    return {"token_id": token_id, "old_name": old_name, "new_name": new_name}


def merge_tokens(conn: sqlite3.Connection, survivor_id: int, victim_id: int,
                 db_path: Optional[str] = None) -> dict:
    """
    Merge victim token into survivor, reassigning all bindings.

    Args:
        conn: Database connection
        survivor_id: Token to keep
        victim_id: Token to merge and delete
        db_path: Database path for backup (None for :memory:)

    Returns:
        Dict with survivor_id, victim_id, and bindings_reassigned count

    Raises:
        ValueError: If tokens don't exist or are in different collections
    """
    if db_path and db_path != ":memory:":
        backup_db(db_path)

    cursor = conn.execute("SELECT collection_id FROM tokens WHERE id = ?", (survivor_id,))
    survivor = cursor.fetchone()
    if survivor is None:
        raise ValueError(f"Token {survivor_id} does not exist")

    cursor = conn.execute("SELECT collection_id FROM tokens WHERE id = ?", (victim_id,))
    victim = cursor.fetchone()
    if victim is None:
        raise ValueError(f"Token {victim_id} does not exist")

    if survivor["collection_id"] != victim["collection_id"]:
        raise ValueError("Cannot merge tokens from different collections")

    cursor = conn.execute("""
        UPDATE node_token_bindings
        SET token_id = ?
        WHERE token_id = ?
    """, (survivor_id, victim_id))
    bindings_reassigned = cursor.rowcount

    conn.execute("DELETE FROM token_values WHERE token_id = ?", (victim_id,))
    conn.execute("DELETE FROM tokens WHERE id = ?", (victim_id,))

    conn.commit()
    return {"survivor_id": survivor_id, "victim_id": victim_id,
            "bindings_reassigned": bindings_reassigned}


def split_token(conn: sqlite3.Connection, token_id: int, new_name: str,
                binding_ids: list[int]) -> dict:
    """
    Split a token by creating a new token and moving specified bindings.

    Args:
        conn: Database connection
        token_id: Original token
        new_name: Name for new token
        binding_ids: Binding IDs to move to new token

    Returns:
        Dict with original_token_id, new_token_id, and bindings_moved count

    Raises:
        ValueError: If token doesn't exist, name invalid, or bindings don't belong to token
    """
    cursor = conn.execute("""
        SELECT collection_id, type FROM tokens WHERE id = ?
    """, (token_id,))
    token = cursor.fetchone()
    if token is None:
        raise ValueError(f"Token {token_id} does not exist")

    if not _validate_dtcg_name(new_name):
        raise ValueError(f"Invalid DTCG name: {new_name}")

    collection_id = token["collection_id"]
    token_type = token["type"]

    cursor = conn.execute("""
        SELECT COUNT(*) FROM tokens
        WHERE collection_id = ? AND name = ?
    """, (collection_id, new_name))
    if cursor.fetchone()[0] > 0:
        raise ValueError(f"Token name '{new_name}' already exists in collection")

    if binding_ids:
        placeholders = ','.join('?' * len(binding_ids))
        cursor = conn.execute(f"""
            SELECT COUNT(*) FROM node_token_bindings
            WHERE id IN ({placeholders}) AND token_id = ?
        """, (*binding_ids, token_id))
        if cursor.fetchone()[0] != len(binding_ids):
            raise ValueError("Some binding IDs do not belong to token")

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier)
        VALUES (?, ?, ?, 'extracted')
    """, (collection_id, new_name, token_type))
    new_token_id = cursor.lastrowid

    source_values = conn.execute(
        "SELECT mode_id, raw_value, resolved_value, source FROM token_values WHERE token_id = ?",
        (token_id,),
    ).fetchall()
    for sv in source_values:
        insert_token_value(
            conn, token_id=new_token_id, mode_id=sv["mode_id"],
            raw_value=sv["raw_value"], resolved_value=sv["resolved_value"],
            source=sv["source"], changed_by="curate", reason="split_from_token",
        )

    if binding_ids:
        placeholders = ','.join('?' * len(binding_ids))
        conn.execute(f"""
            UPDATE node_token_bindings
            SET token_id = ?
            WHERE id IN ({placeholders})
        """, (new_token_id, *binding_ids))

    conn.commit()
    return {"original_token_id": token_id, "new_token_id": new_token_id,
            "bindings_moved": len(binding_ids)}


def reject_token(conn: sqlite3.Connection, token_id: int,
                 db_path: Optional[str] = None) -> dict:
    """
    Reject a token, reverting bindings to unbound and deleting the token.

    Args:
        conn: Database connection
        token_id: Token to reject
        db_path: Database path for backup (None for :memory:)

    Returns:
        Dict with token_id and bindings_reverted count

    Raises:
        ValueError: If token doesn't exist
    """
    if db_path and db_path != ":memory:":
        backup_db(db_path)

    cursor = conn.execute("SELECT id FROM tokens WHERE id = ?", (token_id,))
    if cursor.fetchone() is None:
        raise ValueError(f"Token {token_id} does not exist")

    cursor = conn.execute("""
        UPDATE node_token_bindings
        SET token_id = NULL, binding_status = 'unbound', confidence = NULL
        WHERE token_id = ?
    """, (token_id,))
    bindings_reverted = cursor.rowcount

    conn.execute("DELETE FROM tokens WHERE id = ?", (token_id,))

    conn.commit()
    return {"token_id": token_id, "bindings_reverted": bindings_reverted}


def create_alias(conn: sqlite3.Connection, alias_name: str, target_token_id: int,
                 collection_id: int) -> dict:
    """
    Create an alias token pointing to another token.

    Args:
        conn: Database connection
        alias_name: Name for the alias token
        target_token_id: Token to alias
        collection_id: Collection to create alias in

    Returns:
        Dict with alias_id, alias_name, target_id, and target_name

    Raises:
        ValueError: If target doesn't exist, is an alias, or name is invalid/duplicate
    """
    if not _validate_dtcg_name(alias_name):
        raise ValueError(f"Invalid DTCG name: {alias_name}")

    cursor = conn.execute("""
        SELECT name, type, alias_of FROM tokens WHERE id = ?
    """, (target_token_id,))
    target = cursor.fetchone()
    if target is None:
        raise ValueError(f"Target token {target_token_id} does not exist")

    if target["alias_of"] is not None:
        raise ValueError(f"Target token cannot be an alias")

    cursor = conn.execute("""
        SELECT COUNT(*) FROM tokens
        WHERE collection_id = ? AND name = ?
    """, (collection_id, alias_name))
    if cursor.fetchone()[0] > 0:
        raise ValueError(f"Token name '{alias_name}' already exists in collection")

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, alias_of)
        VALUES (?, ?, ?, 'aliased', ?)
    """, (collection_id, alias_name, target["type"], target_token_id))
    alias_id = cursor.lastrowid

    conn.commit()
    return {
        "alias_id": alias_id,
        "alias_name": alias_name,
        "target_id": target_token_id,
        "target_name": target["name"]
    }


def create_collection(conn: sqlite3.Connection, name: str, file_id: int,
                      mode_names: Optional[list[str]] = None) -> dict:
    """
    Create a new token collection with mode(s).

    Args:
        conn: Database connection
        name: Collection name
        file_id: File ID
        mode_names: Mode names (default: ["Default"])

    Returns:
        Dict with collection_id, name, mode_id (first mode)

    Raises:
        ValueError: If collection name already exists for this file
    """
    existing = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = ?",
        (file_id, name)
    ).fetchone()
    if existing:
        raise ValueError(f"Collection '{name}' already exists for file {file_id}")

    cursor = conn.execute(
        "INSERT INTO token_collections (file_id, name) VALUES (?, ?)",
        (file_id, name)
    )
    collection_id = cursor.lastrowid

    if mode_names is None:
        mode_names = ["Default"]

    first_mode_id = None
    for i, mode_name in enumerate(mode_names):
        cursor = conn.execute(
            "INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, ?, ?)",
            (collection_id, mode_name, 1 if i == 0 else 0)
        )
        if i == 0:
            first_mode_id = cursor.lastrowid

    conn.commit()
    return {
        "collection_id": collection_id,
        "name": name,
        "mode_id": first_mode_id,
    }


def convert_to_alias(conn: sqlite3.Connection, token_id: int,
                     target_token_id: int) -> dict:
    """
    Convert a valued token into an alias of another token.

    Preserves the token's ID, collection, and bindings. Clears token_values
    (aliases derive values from their target). Sets tier to 'aliased'.

    Args:
        conn: Database connection
        token_id: Token to convert
        target_token_id: Token to alias

    Returns:
        Dict with token_id, target_token_id

    Raises:
        ValueError: If target doesn't exist or is an alias
    """
    target = conn.execute(
        "SELECT id, alias_of FROM tokens WHERE id = ?",
        (target_token_id,)
    ).fetchone()
    if target is None:
        raise ValueError(f"Target token {target_token_id} does not exist")
    if target["alias_of"] is not None:
        raise ValueError("Target token cannot be an alias")

    token = conn.execute(
        "SELECT id FROM tokens WHERE id = ?", (token_id,)
    ).fetchone()
    if token is None:
        raise ValueError(f"Token {token_id} does not exist")

    conn.execute(
        "UPDATE tokens SET alias_of = ?, tier = 'aliased' WHERE id = ?",
        (target_token_id, token_id)
    )
    conn.execute("DELETE FROM token_values WHERE token_id = ?", (token_id,))

    conn.commit()
    return {"token_id": token_id, "target_token_id": target_token_id}