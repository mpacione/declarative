"""Phase 1: File inventory extraction for the DD pipeline."""

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from dd.types import DeviceClass, classify_device, is_component_sheet_name


def populate_file(
    conn: sqlite3.Connection,
    file_key: str,
    name: str,
    node_count: int | None = None,
    screen_count: int | None = None,
    last_modified: str | None = None,
    metadata: str | None = None,
) -> int:
    """
    UPSERT a file into the files table.

    Args:
        conn: Database connection
        file_key: Figma file key
        name: File name
        node_count: Total number of nodes in the file
        screen_count: Number of screens/frames in the file
        last_modified: Last modification timestamp
        metadata: Additional metadata as JSON string

    Returns:
        The file ID (primary key)
    """
    cursor = conn.cursor()

    # UPSERT the file
    cursor.execute(
        """
        INSERT INTO files (file_key, name, node_count, screen_count, last_modified, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_key) DO UPDATE SET
            name = excluded.name,
            last_modified = excluded.last_modified,
            node_count = excluded.node_count,
            screen_count = excluded.screen_count,
            metadata = excluded.metadata,
            extracted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (file_key, name, node_count, screen_count, last_modified, metadata),
    )

    # Get the file ID
    cursor.execute("SELECT id FROM files WHERE file_key = ?", (file_key,))
    result = cursor.fetchone()

    conn.commit()
    return result[0]


def classify_screen(
    name: str,
    width: float,
    height: float,
    has_components: bool = False,
    has_instances: bool = True,
) -> str:
    """
    Classify a screen based on heuristics.

    Args:
        name: Frame name
        width: Frame width
        height: Frame height
        has_components: Whether the frame contains component definitions
        has_instances: Whether the frame contains instance nodes

    Returns:
        Device class string value
    """
    # Heuristic 1: Name-based detection
    if is_component_sheet_name(name):
        return DeviceClass.COMPONENT_SHEET.value

    # Get device class from dimensions
    device_class = classify_device(width, height)

    # Heuristic 2: Unknown device + has components
    if device_class == DeviceClass.UNKNOWN and has_components:
        return DeviceClass.COMPONENT_SHEET.value

    # Heuristic 3: No instances + unknown device (definition sheet)
    if not has_instances and device_class == DeviceClass.UNKNOWN:
        return DeviceClass.COMPONENT_SHEET.value

    # Otherwise return the device classification
    return device_class.value


def populate_screens(
    conn: sqlite3.Connection,
    file_id: int,
    frames: list[dict[str, Any]],
) -> list[int]:
    """
    UPSERT screens into the screens table.

    Args:
        conn: Database connection
        file_id: ID of the parent file
        frames: List of frame dicts with keys: figma_node_id, name, width, height,
                optionally has_components, has_instances

    Returns:
        List of screen IDs
    """
    cursor = conn.cursor()
    screen_ids = []

    for frame in frames:
        # Extract frame properties
        figma_node_id = frame["figma_node_id"]
        name = frame["name"]
        width = frame["width"]
        height = frame["height"]
        has_components = frame.get("has_components", False)
        has_instances = frame.get("has_instances", True)

        # Classify the screen
        device_class = classify_screen(
            name, width, height, has_components, has_instances
        )

        # UPSERT the screen
        cursor.execute(
            """
            INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id, figma_node_id) DO UPDATE SET
                name = excluded.name,
                width = excluded.width,
                height = excluded.height,
                device_class = excluded.device_class,
                extracted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (file_id, figma_node_id, name, width, height, device_class),
        )

        # Get the screen ID
        cursor.execute(
            "SELECT id FROM screens WHERE file_id = ? AND figma_node_id = ?",
            (file_id, figma_node_id),
        )
        result = cursor.fetchone()
        screen_ids.append(result[0])

    conn.commit()
    return screen_ids


def create_extraction_run(
    conn: sqlite3.Connection,
    file_id: int,
    agent_id: str | None = None,
) -> int:
    """
    Create a new extraction run and initialize screen extraction status.

    Args:
        conn: Database connection
        file_id: ID of the file to extract
        agent_id: Optional agent identifier

    Returns:
        The extraction run ID
    """
    cursor = conn.cursor()

    # Count total screens for this file
    cursor.execute(
        "SELECT COUNT(*) FROM screens WHERE file_id = ?",
        (file_id,),
    )
    total_screens = cursor.fetchone()[0]

    # Create the extraction run
    cursor.execute(
        """
        INSERT INTO extraction_runs (file_id, agent_id, total_screens, status)
        VALUES (?, ?, ?, 'running')
        """,
        (file_id, agent_id, total_screens),
    )
    run_id = cursor.lastrowid

    # Initialize screen extraction status for all screens
    cursor.execute(
        """
        INSERT INTO screen_extraction_status (run_id, screen_id, status)
        SELECT ?, id, 'pending'
        FROM screens
        WHERE file_id = ?
        """,
        (run_id, file_id),
    )

    conn.commit()
    return run_id


def get_pending_screens(
    conn: sqlite3.Connection,
    run_id: int,
) -> list[dict[str, Any]]:
    """
    Get screens that are pending or failed for extraction.

    Screens that are in_progress but started less than 10 minutes ago
    are skipped (owned by another agent).

    Args:
        conn: Database connection
        run_id: Extraction run ID

    Returns:
        List of dicts with keys: screen_id, figma_node_id, name, device_class, status_id
    """
    cursor = conn.cursor()

    # Calculate the 10-minute threshold
    ten_minutes_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime(
        '%Y-%m-%dT%H:%M:%SZ'
    )

    # Query pending and failed screens, skipping recently started in_progress ones
    cursor.execute(
        """
        SELECT
            s.id AS screen_id,
            s.figma_node_id,
            s.name,
            s.device_class,
            ses.id AS status_id
        FROM screen_extraction_status ses
        JOIN screens s ON ses.screen_id = s.id
        WHERE ses.run_id = ?
          AND (
            ses.status IN ('pending', 'failed')
            OR (ses.status = 'in_progress' AND
                (ses.started_at IS NULL OR ses.started_at < ?))
          )
        ORDER BY s.id
        """,
        (run_id, ten_minutes_ago),
    )

    results = []
    for row in cursor.fetchall():
        results.append({
            "screen_id": row["screen_id"],
            "figma_node_id": row["figma_node_id"],
            "name": row["name"],
            "device_class": row["device_class"],
            "status_id": row["status_id"],
        })

    return results