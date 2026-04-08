"""Extraction orchestrator with resume support for the DD pipeline."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from typing import Any

from dd.extract_assets import process_vector_geometry
from dd.extract_bindings import create_bindings_for_screen
from dd.extract_components import extract_components
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
    frames: list[dict[str, Any]],
    node_count: int | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
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
    raw_response: list[dict[str, Any]],
) -> dict[str, Any]:
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
) -> dict[str, Any] | None:
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


def complete_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
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

    # Post-processing: convert vector geometry into content-addressed assets
    vector_count = 0
    if run_status == "completed":
        vector_count = process_vector_geometry(conn)

    conn.commit()

    return {
        "run_id": run_id,
        "status": run_status,
        "total_screens": total_screens,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "vector_assets_processed": vector_count,
    }


def get_component_sheets(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    """
    Get all component_sheet screens for a file.

    Args:
        conn: Database connection
        file_id: ID of the file

    Returns:
        List of dicts with screen_id, figma_node_id, and name
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, figma_node_id, name
        FROM screens
        WHERE file_id = ? AND device_class = 'component_sheet'
        """,
        (file_id,)
    )

    sheets = []
    for row in cursor.fetchall():
        sheets.append({
            "screen_id": row[0],
            "figma_node_id": row[1],
            "name": row[2],
        })

    return sheets


def generate_component_extraction_script(screen_node_id: str) -> str:
    """
    Generate JavaScript to extract components from a component_sheet frame.

    Args:
        screen_node_id: Figma node ID of the component_sheet frame

    Returns:
        JavaScript string for use_figma
    """
    script = f"""
    // Get the screen node
    const screenNode = figma.getNodeById('{screen_node_id}');
    if (!screenNode || !('children' in screenNode)) {{
        return [];
    }}

    const components = [];

    // Recursively find all COMPONENT and COMPONENT_SET nodes
    function findComponents(node) {{
        if (!node) return;

        if (node.type === 'COMPONENT_SET') {{
            // Extract the component set
            const componentSet = {{
                id: node.id,
                type: node.type,
                name: node.name,
                description: node.description || null,
                children: []
            }};

            // Process its variant children
            if ('children' in node) {{
                for (const child of node.children) {{
                    if (child.type === 'COMPONENT') {{
                        const variant = {{
                            id: child.id,
                            type: child.type,
                            name: child.name,
                            children: []
                        }};

                        // Get direct children for slot inference
                        if ('children' in child) {{
                            for (const grandchild of child.children) {{
                                variant.children.push({{
                                    name: grandchild.name,
                                    type: grandchild.type,
                                    characters: grandchild.type === 'TEXT' ? grandchild.characters : undefined
                                }});
                            }}
                        }}

                        componentSet.children.push(variant);
                    }}
                }}
            }}

            components.push(componentSet);
        }} else if (node.type === 'COMPONENT') {{
            // Standalone component
            const component = {{
                id: node.id,
                type: node.type,
                name: node.name,
                description: node.description || null,
                children: []
            }};

            // Get direct children for slot inference
            if ('children' in node) {{
                for (const child of node.children) {{
                    component.children.push({{
                        name: child.name,
                        type: child.type,
                        characters: child.type === 'TEXT' ? child.characters : undefined
                    }});
                }}
            }}

            components.push(component);
        }}

        // Recursively search children
        if ('children' in node) {{
            for (const child of node.children) {{
                findComponents(child);
            }}
        }}
    }}

    // Start the search from the screen node
    findComponents(screenNode);

    return components;
    """

    # Verify the script is under 50K chars
    if len(script) > 50000:
        raise ValueError(f"Component extraction script too long: {len(script)} chars")

    return script


def parse_component_extraction_response(response: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Parse and validate component extraction response from use_figma.

    Args:
        response: Raw response from use_figma component extraction

    Returns:
        List of normalized component dicts ready for extract_components
    """
    if not isinstance(response, list):
        raise ValueError(f"Expected list response, got {type(response)}")

    components = []
    for item in response:
        # Validate required fields
        if not isinstance(item, dict):
            continue
        if "id" not in item or "type" not in item:
            continue
        if item["type"] not in ("COMPONENT", "COMPONENT_SET"):
            continue

        # Normalize the component data
        components.append(item)

    return components


def run_component_extraction(
    conn: sqlite3.Connection,
    file_id: int,
    component_data: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Process component data and insert into database.

    Args:
        conn: Database connection
        file_id: ID of the file
        component_data: Pre-fetched component data from MCP

    Returns:
        Summary dict with component_count, variant_count, instances_linked
    """
    # Extract components using the function from extract_components module
    component_ids = extract_components(conn, file_id, component_data)

    # Count variants
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM component_variants cv
        JOIN components c ON cv.component_id = c.id
        WHERE c.file_id = ?
        """,
        (file_id,)
    )
    variant_count = cursor.fetchone()[0]

    # Link INSTANCE nodes to their components
    # This is a best-effort operation based on matching figma_node_id
    instances_linked = link_instances_to_components(conn, file_id)

    return {
        "component_count": len(component_ids),
        "variant_count": variant_count,
        "instances_linked": instances_linked,
    }


def link_instances_to_components(conn: sqlite3.Connection, file_id: int) -> int:
    """
    Link INSTANCE nodes to their corresponding components.

    This is a best-effort operation that attempts to match INSTANCE nodes
    to components based on stored component references.

    Args:
        conn: Database connection
        file_id: ID of the file

    Returns:
        Number of instances successfully linked
    """
    cursor = conn.cursor()

    # Find all INSTANCE nodes that don't have a component_id yet
    # We'll attempt to match them to components based on their names
    cursor.execute(
        """
        SELECT n.id, n.name
        FROM nodes n
        JOIN screens s ON n.screen_id = s.id
        WHERE s.file_id = ? AND n.node_type = 'INSTANCE' AND n.component_id IS NULL
        """,
        (file_id,)
    )

    instances = cursor.fetchall()
    linked_count = 0

    for node_id, node_name in instances:
        # Try to find a matching component
        # This is a simplified approach - in reality, we'd need to parse
        # the properties to find the component reference
        # For now, we'll try name matching as a fallback

        # Try exact name match first
        cursor.execute(
            """
            SELECT id FROM components
            WHERE file_id = ? AND name = ?
            LIMIT 1
            """,
            (file_id, node_name)
        )

        component_match = cursor.fetchone()

        if component_match:
            component_id = component_match[0]

            # Update the node with the component_id
            cursor.execute(
                """
                UPDATE nodes
                SET component_id = ?
                WHERE id = ?
                """,
                (component_id, node_id)
            )

            linked_count += 1

    conn.commit()
    return linked_count


def run_extraction_pipeline(
    conn: sqlite3.Connection,
    file_key: str,
    file_name: str,
    frames: list[dict[str, Any]],
    extract_fn: Callable[[str], list[dict[str, Any]]],
    node_count: int | None = None,
    agent_id: str | None = None,
    component_extract_fn: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Run the full extraction pipeline.

    Args:
        conn: Database connection
        file_key: Figma file key
        file_name: Name of the file
        frames: List of frame dicts from Figma
        extract_fn: Callback that takes figma_node_id (str) and returns list of node dicts
        node_count: Total node count in file (optional)
        agent_id: Agent identifier (optional)
        component_extract_fn: Optional callback for component extraction (optional)

    Returns:
        Summary dict from complete_run
    """
    start_time = time.time()

    # Set up inventory
    inventory = run_inventory(conn, file_key, file_name, frames, node_count, agent_id)
    run_id = inventory["run_id"]
    file_id = inventory["file_id"]
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
            # Call extract_fn to get raw response
            raw_response = extract_fn(figma_node_id)

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

    # Component extraction phase (if callback provided)
    if component_extract_fn:
        print("\n--- Component Extraction Phase ---")
        component_sheets = get_component_sheets(conn, file_id)

        if component_sheets:
            print(f"Found {len(component_sheets)} component sheet(s)")

            total_components = 0
            total_variants = 0
            total_instances_linked = 0

            for sheet in component_sheets:
                sheet_name = sheet["name"]
                sheet_node_id = sheet["figma_node_id"]

                print(f"Extracting components from {sheet_name}...")

                try:
                    # Call the component extraction callback
                    raw_component_data = component_extract_fn(sheet_node_id)

                    # Parse and validate the response
                    component_data = parse_component_extraction_response(raw_component_data)

                    if component_data:
                        # Run component extraction
                        comp_result = run_component_extraction(conn, file_id, component_data)

                        total_components += comp_result["component_count"]
                        total_variants += comp_result["variant_count"]
                        total_instances_linked += comp_result["instances_linked"]

                        print(f"  Extracted {comp_result['component_count']} component(s), "
                              f"{comp_result['variant_count']} variant(s)")
                    else:
                        print(f"  No components found in {sheet_name}")

                except Exception as e:
                    print(f"  Failed to extract components from {sheet_name}: {e}")

            print("\nComponent extraction complete:")
            print(f"  Total components: {total_components}")
            print(f"  Total variants: {total_variants}")
            print(f"  Instances linked: {total_instances_linked}")

            # Update the summary with component extraction info
            summary["components_extracted"] = total_components
            summary["variants_extracted"] = total_variants
            summary["instances_linked"] = total_instances_linked
        else:
            print("No component sheets found")

    total_elapsed = time.time() - start_time
    print(f"\nExtraction complete in {total_elapsed:.1f}s")
    print(f"Status: {summary['status']}")
    print(f"Completed: {summary['completed']}/{summary['total_screens']}")
    if summary['failed'] > 0:
        print(f"Failed: {summary['failed']}")
    if summary['skipped'] > 0:
        print(f"Skipped: {summary['skipped']}")

    return summary