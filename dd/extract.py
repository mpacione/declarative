"""Extraction orchestrator with resume support for the DD pipeline."""

import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

from dd.extract_bindings import create_bindings_for_screen
from dd.extract_inventory import (
    create_extraction_run,
    get_pending_screens,
    populate_file,
    populate_screens,
)
from dd.extract_screens import (
    compute_is_semantic,
    generate_extraction_script,
    insert_nodes,
    parse_extraction_response,
    update_screen_status,
)
from dd.paths import compute_paths_and_semantics


def run_inventory(
    conn: sqlite3.Connection,
    file_key: str,
    file_name: str,
    frames: List[Dict[str, Any]],
    node_count: Optional[int] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set up extraction run with file and screens.

    Args:
        conn: Database connection
        file_key: Figma file key
        file_name: Name of the file
        frames: List of frame dicts from Figma
        node_count: Total node count in file (optional)
        agent_id: Agent identifier (optional)

    Returns:
        Dict with file_id, run_id, screen_count, and pending_screens
    """
    # UPSERT the file
    file_id = populate_file(
        conn, file_key, file_name, node_count, len(frames)
    )

    # UPSERT all screens
    screen_ids = populate_screens(conn, file_id, frames)

    # Check for existing running extraction_run for resume support
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM extraction_runs
        WHERE file_id = ? AND status = 'running'
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (file_id,)
    )

    existing_run = cursor.fetchone()

    if existing_run:
        # Reuse existing run for resume support
        run_id = existing_run[0]
    else:
        # Create new extraction run
        run_id = create_extraction_run(conn, file_id, agent_id)

    # Get pending screens
    pending_screens = get_pending_screens(conn, run_id)

    return {
        "file_id": file_id,
        "run_id": run_id,
        "screen_count": len(screen_ids),
        "pending_screens": pending_screens,
    }


def process_screen(
    conn: sqlite3.Connection,
    run_id: int,
    screen_id: int,
    figma_node_id: str,
    raw_response: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Process a single screen's extraction response.

    Args:
        conn: Database connection
        run_id: Extraction run ID
        screen_id: Screen ID to process
        figma_node_id: Figma node ID for the screen
        raw_response: Raw response from use_figma

    Returns:
        Dict with screen_id, node_count, binding_count, and status
    """
    try:
        # Mark screen as in_progress
        update_screen_status(conn, run_id, screen_id, "in_progress")

        # Parse and clean the response
        parsed_nodes = parse_extraction_response(raw_response)

        # Compute semantic flags
        nodes_with_semantic = compute_is_semantic(parsed_nodes)

        # Insert nodes into DB
        node_ids = insert_nodes(conn, screen_id, nodes_with_semantic)

        # Compute paths and update semantic flags in DB
        compute_paths_and_semantics(conn, screen_id)

        # Create bindings
        binding_count = create_bindings_for_screen(conn, screen_id)

        # Mark screen as completed
        node_count = len(node_ids)
        update_screen_status(
            conn, run_id, screen_id, "completed",
            node_count=node_count,
            binding_count=binding_count
        )

        # Increment extracted_screens counter
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE extraction_runs
            SET extracted_screens = extracted_screens + 1
            WHERE id = ?
            """,
            (run_id,)
        )
        conn.commit()

        return {
            "screen_id": screen_id,
            "node_count": node_count,
            "binding_count": binding_count,
            "status": "completed",
        }

    except Exception as e:
        # Mark screen as failed
        error_msg = str(e)
        update_screen_status(
            conn, run_id, screen_id, "failed", error=error_msg
        )

        # Re-raise for visibility
        raise


def get_next_screen(
    conn: sqlite3.Connection, run_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get the next screen to process.

    Args:
        conn: Database connection
        run_id: Extraction run ID

    Returns:
        Screen dict or None if no screens remain
    """
    pending = get_pending_screens(conn, run_id)
    return pending[0] if pending else None


def get_extraction_script(screen_figma_node_id: str) -> str:
    """
    Get the JavaScript extraction script for a screen.

    Convenience wrapper for generate_extraction_script.

    Args:
        screen_figma_node_id: Figma node ID of the screen

    Returns:
        JavaScript code string
    """
    return generate_extraction_script(screen_figma_node_id)


def complete_run(conn: sqlite3.Connection, run_id: int) -> Dict[str, Any]:
    """
    Complete an extraction run and update status.

    Args:
        conn: Database connection
        run_id: Extraction run ID

    Returns:
        Summary dict with run status and counts
    """
    cursor = conn.cursor()

    # Count screen statuses
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
        FROM screen_extraction_status
        WHERE run_id = ?
        """,
        (run_id,)
    )

    row = cursor.fetchone()
    total_screens = row[0]
    completed = row[1] or 0
    failed = row[2] or 0
    skipped = row[3] or 0

    # Determine run status
    if failed > 0:
        run_status = "failed"
    elif completed == total_screens:
        run_status = "completed"
    else:
        run_status = "running"

    # Update extraction_runs
    if run_status in ["completed", "failed"]:
        cursor.execute(
            """
            UPDATE extraction_runs
            SET status = ?, completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ?
            """,
            (run_status, run_id)
        )
    else:
        cursor.execute(
            """
            UPDATE extraction_runs
            SET status = ?
            WHERE id = ?
            """,
            (run_status, run_id)
        )

    conn.commit()

    return {
        "run_id": run_id,
        "status": run_status,
        "total_screens": total_screens,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
    }


def run_extraction_pipeline(
    conn: sqlite3.Connection,
    file_key: str,
    file_name: str,
    frames: List[Dict[str, Any]],
    extract_fn: Callable[[str], List[Dict[str, Any]]],
    node_count: Optional[int] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full extraction pipeline.

    Args:
        conn: Database connection
        file_key: Figma file key
        file_name: Name of the file
        frames: List of frame dicts from Figma
        extract_fn: Callback that takes screen_figma_node_id and returns raw response
        node_count: Total node count in file (optional)
        agent_id: Agent identifier (optional)

    Returns:
        Summary dict from complete_run
    """
    start_time = time.time()

    # Set up inventory
    inventory = run_inventory(conn, file_key, file_name, frames, node_count, agent_id)
    run_id = inventory["run_id"]
    total_screens = inventory["screen_count"]

    print(f"Starting extraction for {total_screens} screens...")

    # Process each pending screen
    processed = 0
    for i, screen in enumerate(inventory["pending_screens"], 1):
        screen_id = screen["screen_id"]
        figma_node_id = screen["figma_node_id"]
        name = screen["name"]
        device_class = screen["device_class"]

        try:
            # Call extract_fn to get raw response (MCP call abstraction)
            extraction_script = get_extraction_script(figma_node_id)
            raw_response = extract_fn(extraction_script)

            # Process the screen
            result = process_screen(conn, run_id, screen_id, figma_node_id, raw_response)

            processed += 1
            elapsed = time.time() - start_time

            # Calculate ETA
            if processed > 0:
                avg_time_per_screen = elapsed / processed
                remaining = len(inventory["pending_screens"]) - processed
                eta = avg_time_per_screen * remaining
            else:
                eta = 0

            # Report progress
            print(f"[{processed}/{len(inventory['pending_screens'])}] "
                  f"Screen \"{name}\" ({device_class}) - "
                  f"{result['node_count']} nodes, {result['binding_count']} bindings - "
                  f"elapsed: {elapsed:.1f}s, ETA: {eta:.1f}s")

        except Exception as e:
            print(f"Failed to process screen {name}: {e}")
            # Continue with next screen
            continue

    # Complete the run
    summary = complete_run(conn, run_id)

    total_elapsed = time.time() - start_time
    print(f"\nExtraction complete in {total_elapsed:.1f}s")
    print(f"Status: {summary['status']}")
    print(f"Completed: {summary['completed']}/{summary['total_screens']}")
    if summary['failed'] > 0:
        print(f"Failed: {summary['failed']}")
    if summary['skipped'] > 0:
        print(f"Skipped: {summary['skipped']}")

    return summary