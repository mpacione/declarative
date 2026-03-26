"""CLI entrypoint for Declarative Design.

Usage:
    python -m dd extract --file-key KEY [--token TOKEN] [--page PAGE_ID] [--db-path PATH]
    python -m dd status [--db-path PATH]
    python -m dd export css|tailwind|dtcg [--db-path PATH] [--out FILE]
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from dd.db import get_connection, init_db
from dd.figma_api import (
    convert_node_tree,
    extract_top_level_frames,
    get_file_tree,
    get_screen_nodes,
)
from dd.extract import complete_run, process_screen, run_inventory


def resolve_token(flag_value: Optional[str]) -> str:
    if flag_value:
        return flag_value
    env_token = os.environ.get("FIGMA_ACCESS_TOKEN")
    if env_token:
        return env_token
    print("Error: Figma token required. Use --token or set FIGMA_ACCESS_TOKEN.", file=sys.stderr)
    sys.exit(1)


def run_extract(
    file_key: str,
    token: str,
    page_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    if db_path is None:
        db_path = f"{file_key}.declarative.db"

    print(f"Extracting file {file_key} → {db_path}")

    conn = init_db(db_path)

    print("Fetching file structure...")
    if page_id:
        file_json = get_file_tree(file_key, token, page_id=page_id, depth=2)
        frames = extract_top_level_frames(file_json, page_id=page_id, from_nodes_endpoint=True)
        file_name = f"figma:{file_key}"
    else:
        file_json = get_file_tree(file_key, token, depth=2)
        frames = extract_top_level_frames(file_json)
        file_name = file_json.get("name", f"figma:{file_key}")

    print(f"Found {len(frames)} top-level frames")

    inventory = run_inventory(conn, file_key, file_name, frames)
    run_id = inventory["run_id"]
    pending = inventory["pending_screens"]

    print(f"Extracting {len(pending)} screens (run {run_id})...")

    import time
    start = time.time()
    batch_size = 10
    processed = 0

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        batch_ids = [s["figma_node_id"] for s in batch]

        try:
            resp = get_screen_nodes(file_key, token, batch_ids)
        except Exception as e:
            for screen in batch:
                processed += 1
                print(f"  [{processed}/{len(pending)}] {screen['name']} — FAILED: {e}", file=sys.stderr)
            continue

        for screen in batch:
            processed += 1
            screen_id = screen["screen_id"]
            figma_node_id = screen["figma_node_id"]
            name = screen["name"]

            try:
                screen_data = resp["nodes"][figma_node_id]["document"]
                raw_response = convert_node_tree(screen_data)
                result = process_screen(conn, run_id, screen_id, figma_node_id, raw_response)

                elapsed = time.time() - start
                avg = elapsed / processed
                eta = avg * (len(pending) - processed)
                print(
                    f"  [{processed}/{len(pending)}] {name} — "
                    f"{result['node_count']} nodes, {result['binding_count']} bindings "
                    f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)"
                )
            except Exception as e:
                print(f"  [{processed}/{len(pending)}] {name} — FAILED: {e}", file=sys.stderr)

    summary = complete_run(conn, run_id)
    print(
        f"\nDone: {summary['completed']}/{summary['total_screens']} screens, "
        f"{summary['failed']} failed, {summary['skipped']} skipped"
    )

    conn.close()


def run_status(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.status import format_status_report

    conn = get_connection(db_path)
    print(format_status_report(conn))
    conn.close()


def run_export(fmt: str, db_path: str, out: Optional[str] = None) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = get_connection(db_path)

    if fmt == "css":
        from dd.export_css import export_css
        content = export_css(conn)
        default_out = "tokens.css"
    elif fmt == "tailwind":
        from dd.export_tailwind import export_tailwind
        content = export_tailwind(conn)
        default_out = "tailwind.theme.js"
    elif fmt == "dtcg":
        from dd.export_dtcg import export_dtcg
        content = export_dtcg(conn)
        default_out = "tokens.json"
    else:
        print(f"Error: Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    output_path = out or default_out
    Path(output_path).write_text(content)
    print(f"Exported {fmt} → {output_path} ({len(content)} chars)")
    conn.close()


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(prog="dd", description="Declarative Design CLI")
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser("extract", help="Extract Figma file to SQLite")
    extract_parser.add_argument("--file-key", required=True, help="Figma file key")
    extract_parser.add_argument("--token", help="Figma access token (or set FIGMA_ACCESS_TOKEN)")
    extract_parser.add_argument("--page", help="Figma page node ID to scope extraction")
    extract_parser.add_argument("--db-path", help="Output database path")

    status_parser = subparsers.add_parser("status", help="Show pipeline status")
    status_parser.add_argument("--db-path", required=True, help="Database path")

    export_parser = subparsers.add_parser("export", help="Export tokens")
    export_parser.add_argument("format", choices=["css", "tailwind", "dtcg"], help="Export format")
    export_parser.add_argument("--db-path", required=True, help="Database path")
    export_parser.add_argument("--out", help="Output file path")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "extract":
        token = resolve_token(args.token)
        run_extract(
            file_key=args.file_key,
            token=token,
            page_id=args.page,
            db_path=args.db_path,
        )
    elif args.command == "status":
        run_status(args.db_path)
    elif args.command == "export":
        run_export(args.format, args.db_path, args.out)


if __name__ == "__main__":
    main()
