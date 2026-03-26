"""Compute materialized paths and semantic flags for nodes in the tree."""

import sqlite3
from typing import Dict, List, Optional, Set, Tuple

from dd.types import NON_SEMANTIC_PREFIXES, SEMANTIC_NODE_TYPES


def compute_paths(conn: sqlite3.Connection, screen_id: int) -> None:
    """
    Compute materialized paths for all nodes in a screen.

    Paths are built as:
    - Root nodes (parent_id is NULL): path = str(sort_order)
    - Child nodes: path = parent_path + "." + str(sort_order)

    Processes nodes in depth order to ensure parents have paths before children.

    Args:
        conn: Database connection
        screen_id: ID of the screen to process
    """
    # Query all nodes for the screen, ordered by depth then sort_order
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, parent_id, sort_order, depth
        FROM nodes
        WHERE screen_id = ?
        ORDER BY depth ASC, sort_order ASC
    """, (screen_id,))

    nodes = cursor.fetchall()

    # Build in-memory dict: node_id -> path
    node_paths: Dict[int, str] = {}

    for node_id, parent_id, sort_order, depth in nodes:
        if parent_id is None:
            # Root node - path is just the sort_order
            path = str(sort_order)
        else:
            # Child node - parent should already have a path (due to depth ordering)
            parent_path = node_paths[parent_id]
            path = f"{parent_path}.{sort_order}"

        node_paths[node_id] = path

    # Batch update the paths
    updates = [(path, node_id) for node_id, path in node_paths.items()]
    cursor.executemany("UPDATE nodes SET path = ? WHERE id = ?", updates)

    conn.commit()


def compute_is_semantic(conn: sqlite3.Connection, screen_id: int) -> None:
    """
    Compute is_semantic flags for all nodes in a screen.

    A node is semantic if ANY of:
    1. node_type is TEXT, INSTANCE, or COMPONENT
    2. node_type is FRAME and layout_mode is not NULL
    3. name does not start with Frame, Group, Rectangle, or Vector
    4. Has >= 2 children and at least 1 child is semantic

    Args:
        conn: Database connection
        screen_id: ID of the screen to process
    """
    cursor = conn.cursor()

    # Query all nodes for the screen
    cursor.execute("""
        SELECT id, parent_id, name, node_type, layout_mode, depth
        FROM nodes
        WHERE screen_id = ?
        ORDER BY depth ASC
    """, (screen_id,))

    nodes = cursor.fetchall()

    # Build tree structure and node info
    node_info: Dict[int, Dict] = {}
    children_map: Dict[int, List[int]] = {}

    for node_id, parent_id, name, node_type, layout_mode, depth in nodes:
        node_info[node_id] = {
            'name': name,
            'node_type': node_type,
            'layout_mode': layout_mode,
            'depth': depth,
            'is_semantic': 0  # Default to not semantic
        }

        if parent_id is not None:
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(node_id)

    # First pass: Apply rules 1-3 (forward pass)
    for node_id, info in node_info.items():
        # Rule 1: Semantic node types
        if info['node_type'] in SEMANTIC_NODE_TYPES:
            info['is_semantic'] = 1
        # Rule 2: FRAME with layout_mode
        elif info['node_type'] == 'FRAME' and info['layout_mode'] is not None:
            info['is_semantic'] = 1
        # Rule 3: Name doesn't start with default prefixes
        elif not any(info['name'].startswith(prefix) for prefix in NON_SEMANTIC_PREFIXES):
            info['is_semantic'] = 1

    # Second pass: Apply rule 4 (bottom-up)
    # Process from deepest to shallowest
    max_depth = max((info['depth'] for info in node_info.values()), default=0)

    for depth in range(max_depth, -1, -1):
        for node_id, info in node_info.items():
            if info['depth'] != depth:
                continue

            # Rule 4: Has >= 2 children and at least 1 is semantic
            if node_id in children_map:
                child_ids = children_map[node_id]
                if len(child_ids) >= 2:
                    semantic_children = sum(1 for child_id in child_ids
                                           if node_info[child_id]['is_semantic'])
                    if semantic_children >= 1:
                        info['is_semantic'] = 1

    # Batch update the is_semantic flags
    updates = [(info['is_semantic'], node_id) for node_id, info in node_info.items()]
    cursor.executemany("UPDATE nodes SET is_semantic = ? WHERE id = ?", updates)

    conn.commit()


def compute_paths_and_semantics(conn: sqlite3.Connection, screen_id: int) -> None:
    """
    Convenience function to compute both paths and semantic flags.

    This is the main function called by the orchestrator.

    Args:
        conn: Database connection
        screen_id: ID of the screen to process
    """
    compute_paths(conn, screen_id)
    compute_is_semantic(conn, screen_id)