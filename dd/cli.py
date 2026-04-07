"""CLI entrypoint for Declarative Design.

Usage:
    python -m dd extract <figma-url-or-key> [--token TOKEN] [--page PAGE_ID] [--db PATH]
    python -m dd cluster [--db PATH] [--threshold 2.0]
    python -m dd accept-all [--db PATH]
    python -m dd validate [--db PATH]
    python -m dd status [--db PATH]
    python -m dd export css|tailwind|dtcg [--db PATH] [--out FILE]
    python -m dd generate-prompt "your prompt" [--db PATH] [--out FILE] [--page NAME]
    python -m dd maintenance [--db PATH] [--keep-last N] [--dry-run]
"""

import argparse
import glob
import json
from pathlib import Path as _Path

from dotenv import load_dotenv

load_dotenv(_Path(__file__).resolve().parent.parent / ".env", override=True)
import os
import re
import sys
from pathlib import Path

from dd.db import get_connection, init_db
from dd.extract import complete_run, process_screen, run_inventory
from dd.figma_api import (
    convert_node_tree,
    extract_top_level_frames,
    get_file_tree,
    get_screen_nodes,
)


def resolve_token(flag_value: str | None) -> str:
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
    page_id: str | None = None,
    db_path: str | None = None,
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


def detect_db_path(explicit: str | None) -> str:
    if explicit:
        return explicit

    dbs = glob.glob("*.declarative.db")
    if len(dbs) == 1:
        return dbs[0]
    if len(dbs) == 0:
        print("Error: No .declarative.db found in current directory. Use --db to specify.", file=sys.stderr)
        sys.exit(1)
    print(f"Error: Multiple .declarative.db files found: {dbs}. Use --db to specify.", file=sys.stderr)
    sys.exit(1)


def _get_file_id(conn) -> int:
    row = conn.execute("SELECT id FROM files ORDER BY id LIMIT 1").fetchone()
    if not row:
        print("Error: No file found in database. Run extract first.", file=sys.stderr)
        sys.exit(1)
    return row[0] if isinstance(row, tuple) else row["id"]


def run_status(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.status import format_status_report

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    print(format_status_report(conn, file_id=file_id))
    conn.close()


def run_cluster(db_path: str, threshold: float = 2.0) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.cluster import run_clustering

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    result = run_clustering(conn, file_id=file_id, color_threshold=threshold)

    print(f"\n{result['total_tokens']} tokens, {result['coverage_pct']:.1f}% coverage")
    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Warning: {err}", file=sys.stderr)

    conn.close()


def run_accept_all(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.curate import accept_all

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    result = accept_all(conn, file_id=file_id)

    print(f"Accepted {result['tokens_accepted']} tokens, {result['bindings_updated']} bindings updated")
    conn.close()


def run_validate(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.validate import run_validation

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    result = run_validation(conn, file_id=file_id)

    if result["errors"] == 0:
        print(f"Validation passed: 0 errors, {result['warnings']} warnings")
    else:
        print(f"Validation: {result['errors']} errors, {result['warnings']} warnings")
        for issue in result.get("issues", [])[:10]:
            print(f"  [{issue['severity']}] {issue['message']}")

    conn.close()


def run_export(fmt: str, db_path: str, out: str | None = None) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)

    if fmt == "css":
        from dd.export_css import export_css
        content = export_css(conn, file_id=file_id)
        default_out = "tokens.css"
    elif fmt == "tailwind":
        from dd.export_tailwind import export_tailwind
        content = export_tailwind(conn, file_id=file_id)
        default_out = "tailwind.theme.js"
    elif fmt == "dtcg":
        from dd.export_dtcg import export_dtcg
        content = export_dtcg(conn, file_id=file_id)
        default_out = "tokens.json"
    else:
        print(f"Error: Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    if isinstance(content, (dict, list)):
        content = json.dumps(content, indent=2)

    output_path = out or default_out
    Path(output_path).write_text(content)
    print(f"Exported {fmt} → {output_path} ({len(content):,} chars)")
    conn.close()


def _run_curate_report(db_path: str, as_json: bool = False) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.curate_report import generate_curation_report

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    report = generate_curation_report(conn, file_id)

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        s = report["summary"]
        print(f"Curation Report: {s['total_actions']} actions needed\n")

        if report["numeric_names"]:
            print(f"  Numeric names ({s['numeric_names']}): tokens with numeric segments need semantic names")
            for t in report["numeric_names"][:5]:
                print(f"    {t['name']} ({t['type']})")
            if s["numeric_names"] > 5:
                print(f"    ... and {s['numeric_names'] - 5} more")

        if report["near_duplicates"]:
            print(f"\n  Near-duplicate colors ({s['near_duplicates']}): consider merging")
            for p in report["near_duplicates"]:
                print(f"    ΔE {p['delta_e']}: {p['token_a']} ({p['value_a']}) ↔ {p['token_b']} ({p['value_b']})")

        if report["low_use"]:
            print(f"\n  Low-use tokens ({s['low_use']}): ≤5 bindings, may be one-offs")
            for t in report["low_use"][:5]:
                print(f"    {t['name']} ({t['type']}) — {t['binding_count']} uses")
            if s["low_use"] > 5:
                print(f"    ... and {s['low_use'] - 5} more")

        if report["fractional_sizes"]:
            print(f"\n  Fractional font sizes ({s['fractional_sizes']}): likely Figma scaling artifacts")
            for f in report["fractional_sizes"][:5]:
                print(f"    {f['name']}: {f['value']}px → suggest {f['suggested']}px")

        if s["missing_semantic_layer"]:
            print("\n  No semantic layer: 0 aliases found. Consider creating semantic tokens (e.g. color.danger → color.surface.27)")

    conn.close()


def _run_seed_catalog(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.catalog import seed_catalog

    conn = get_connection(db_path)
    count = seed_catalog(conn)
    conn.close()
    print(f"Seeded {count} component types into catalog.")


def _run_generate(db_path: str, screen_id: int, dry_run: bool = False) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.renderers.figma import generate_screen

    conn = get_connection(db_path)
    result = generate_screen(conn, screen_id)
    conn.close()

    if dry_run:
        print(f"Screen {screen_id}:")
        print(f"  Elements:   {result['element_count']}")
        print(f"  Tokens:     {result['token_count']}")
        print(f"  Token refs: {len(result['token_refs'])}")
        print(f"  Script:     {len(result['structure_script'])} chars")
    else:
        print(result["structure_script"])


def _run_generate_ir(db_path: str, screen_arg: str) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.ir import generate_ir

    conn = get_connection(db_path)

    if screen_arg == "all":
        cursor = conn.execute("SELECT id, name FROM screens ORDER BY id")
        screens = cursor.fetchall()
        for screen_id, name in screens:
            result = generate_ir(conn, screen_id)
            print(f"Screen {screen_id} ({name}): {result['element_count']} elements, {result['token_count']} tokens")
    else:
        screen_id = int(screen_arg)
        result = generate_ir(conn, screen_id)
        print(result["json"])

    conn.close()


def _run_classify(db_path: str, use_llm: bool = False, use_vision: bool = False) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.catalog import seed_catalog
    from dd.classify import run_classification

    conn = get_connection(db_path)

    # Ensure catalog is seeded before classifying
    seed_catalog(conn)

    cursor = conn.execute("SELECT id, file_key FROM files LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        print("Error: No file found in database.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    file_id = row[0]
    file_key = row[1]

    client = None
    fetch_screenshot = None

    if use_llm or use_vision:
        import anthropic
        client = anthropic.Anthropic()

    if use_vision:
        fetch_screenshot = make_figma_screenshot_fetcher()

    result = run_classification(
        conn, file_id,
        client=client,
        file_key=file_key if use_vision else None,
        fetch_screenshot=fetch_screenshot,
    )
    conn.close()

    print("Classification complete:")
    print(f"  Screens processed:     {result['screens_processed']}")
    print(f"  Formal classified:     {result['formal_classified']}")
    print(f"  Heuristic classified:  {result['heuristic_classified']}")
    if use_llm:
        print(f"  LLM classified:        {result['llm_classified']}")
    print(f"  Parent links:          {result['parent_links']}")
    if use_vision:
        v = result["vision"]
        print(f"  Vision validated:      {v['validated']} (agreed={v['agreed']}, disagreed={v['disagreed']})")
    print(f"  Skeletons generated:   {result['skeletons_generated']}")


def make_figma_screenshot_fetcher(
    session=None,
    token: str | None = None,
    max_retries: int = 5,
    retry_delay: float = 2.0,
):
    """Create a batch screenshot fetcher with retry/backoff for Figma rate limits.

    Supports both single and batch calls:
      - fetch(file_key, "node_id") → bytes | None
      - fetch(file_key, ["id1", "id2", ...]) → {node_id: bytes}

    Figma's image API accepts comma-separated IDs, so batch mode makes
    one API call per screen instead of one per node.
    """
    import time
    if session is None:
        import requests
        session = requests.Session()
    if token is None:
        token = os.environ.get("FIGMA_ACCESS_TOKEN", "")

    def _fetch_image_urls(file_key: str, node_ids: list[str]) -> dict[str, str]:
        url = f"https://api.figma.com/v1/images/{file_key}"
        headers = {"X-Figma-Token": token}
        params = {"ids": ",".join(node_ids), "format": "png", "scale": "1"}

        delay = retry_delay
        for attempt in range(max_retries + 1):
            try:
                resp = session.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 429:
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= 2
                        continue
                    return {}
                resp.raise_for_status()
                return resp.json().get("images", {})
            except Exception:
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                return {}
        return {}

    def _download_image(image_url: str) -> bytes | None:
        try:
            resp = session.get(image_url, timeout=30)
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None

    def fetch(file_key: str, node_ids_or_id):
        if isinstance(node_ids_or_id, list):
            if not node_ids_or_id:
                return {}
            image_urls = _fetch_image_urls(file_key, node_ids_or_id)
            results = {}
            for nid, img_url in image_urls.items():
                if img_url:
                    data = _download_image(img_url)
                    if data:
                        results[nid] = data
            return results
        else:
            result = fetch(file_key, [node_ids_or_id])
            return result.get(node_ids_or_id)

    return fetch


def _run_maintenance(db_path: str, args: argparse.Namespace) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.maintenance import prune_export_validations, prune_extraction_runs

    conn = get_connection(db_path)
    keep_last = args.keep_last

    if args.dry_run:
        runs_count = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs"
        ).fetchone()[0]
        runs_to_delete = max(0, runs_count - keep_last)

        validations_count = conn.execute(
            "SELECT COUNT(DISTINCT run_at) FROM export_validations"
        ).fetchone()[0]
        validations_to_delete = max(0, validations_count - keep_last)

        print(f"Would delete {runs_to_delete} extraction runs (keeping {min(runs_count, keep_last)})")
        print(f"Would delete ~{validations_to_delete} export validation runs (keeping {min(validations_count, keep_last)})")
        conn.close()
        return

    runs_deleted = prune_extraction_runs(conn, keep_last=keep_last)
    validations_deleted = prune_export_validations(conn, keep_last=keep_last)

    print(f"Deleted {runs_deleted} extraction runs, {validations_deleted} export validation rows")
    conn.close()


def _run_extract_supplement(db_path: str, args: argparse.Namespace) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.db import classify_screens
    from dd.extract_supplement import run_supplement

    conn = get_connection(db_path)

    # Ensure screen_type is populated
    classify_screens(conn)

    screen_count = conn.execute(
        "SELECT COUNT(*) FROM screens WHERE screen_type = 'app_screen'"
    ).fetchone()[0]

    if args.dry_run:
        print(f"Would extract Plugin API fields for {screen_count} app screens")
        print(f"  Port: {args.port}")
        print(f"  Batch size: {args.batch_size}")
        print("  Fields: componentKey, layoutPositioning, Grid properties")
        conn.close()
        return

    def execute_via_ws(script: str) -> dict:
        """Execute JS in Figma via PROXY_EXECUTE WebSocket."""
        import subprocess
        node_js = (
            'const WebSocket = require("ws");'
            f'const ws = new WebSocket("ws://127.0.0.1:{args.port}");'
            f'const code = {json.dumps(script)};'
            'ws.on("open", () => {'
            '  ws.send(JSON.stringify({ type: "PROXY_EXECUTE", id: "supp", code, timeout: 60000 }));'
            '});'
            'ws.on("message", (data) => {'
            '  const msg = JSON.parse(data);'
            '  if (msg.type === "PROXY_EXECUTE_RESULT") {'
            '    console.log(JSON.stringify(msg));'
            '    ws.close(); process.exit(0);'
            '  }'
            '});'
            'ws.on("error", (err) => { console.log(JSON.stringify({error: err.message})); process.exit(1); });'
            'setTimeout(() => { console.log(JSON.stringify({error: "timeout"})); process.exit(1); }, 65000);'
        )
        result = subprocess.run(
            [_find_node_binary(), "-e", node_js],
            capture_output=True, text=True, timeout=70,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:200] or "node process failed")
        msg = json.loads(result.stdout.strip())
        if "error" in msg and isinstance(msg["error"], str):
            raise RuntimeError(msg["error"])
        inner = msg.get("result", {})
        if inner.get("success") is False:
            raise RuntimeError(inner.get("error", "execution failed"))
        return inner.get("result", inner)

    print(f"Supplemental extraction: {screen_count} app screens (port {args.port}, batch {args.batch_size})")

    result = run_supplement(conn, execute_via_ws, batch_size=args.batch_size)
    conn.close()

    print(f"\nDone: {result['total_nodes']} nodes updated")
    print(f"  component_key: {result['component_key']}")
    print(f"  layout_positioning: {result['layout_positioning']}")
    print(f"  grid: {result['grid']}")
    if result["failed"] > 0:
        print(f"  failed: {result['failed']} screens")


def _find_node_binary() -> str:
    """Find the node binary, checking common locations."""
    import shutil
    node = shutil.which("node")
    if node:
        return node
    # Check nvm
    import glob
    nvm_nodes = glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/node"))
    if nvm_nodes:
        return sorted(nvm_nodes)[-1]  # Latest version
    raise FileNotFoundError("node binary not found — required for Plugin API extraction")


def _run_push(db_path: str, args: argparse.Namespace) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if args.writeback:
        if not args.figma_state:
            print("Error: --writeback requires --figma-state", file=sys.stderr)
            sys.exit(1)

        from dd.export_figma_vars import writeback_variable_ids

        figma_response = json.loads(Path(args.figma_state).read_text())
        conn = get_connection(db_path)
        file_id = _get_file_id(conn)
        writeback_variable_ids(conn, file_id, figma_response)
        conn.close()
        print("Variable IDs written back to DB.")
        return

    from dd.push import generate_push_manifest

    figma_state = None
    if args.figma_state:
        figma_state = json.loads(Path(args.figma_state).read_text())

    conn = get_connection(db_path)
    file_id = _get_file_id(conn)
    manifest = generate_push_manifest(conn, file_id, figma_state, phase=args.phase)
    conn.close()

    if args.dry_run:
        for phase_name, phase_data in manifest["phases"].items():
            summary = phase_data.get("summary", {})
            print(f"Phase: {phase_name}")
            for key, val in summary.items():
                print(f"  {key}: {val}")
        return

    output = json.dumps(manifest, indent=2)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Manifest written to {args.out}", file=sys.stderr)
    else:
        print(output)


def _make_anthropic_client():
    """Create an Anthropic client. Separated for test mockability."""
    import anthropic
    return anthropic.Anthropic()


def _run_generate_prompt(db_path: str, prompt: str, out: str | None = None, page_name: str | None = None) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.prompt_parser import prompt_to_figma
    from dd.templates import build_component_key_registry, extract_templates

    conn = get_connection(db_path)
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    if file_row:
        file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
        build_component_key_registry(conn)
        extract_templates(conn, file_id)

    client = _make_anthropic_client()
    result = prompt_to_figma(prompt, conn, client, page_name=page_name)
    conn.close()

    script = result["structure_script"]
    warnings = result.get("warnings", [])

    if warnings:
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)

    if out:
        Path(out).write_text(script)
        print(f"Script written to {out} ({len(script):,} chars)", file=sys.stderr)
        print(f"Elements: {result['element_count']}", file=sys.stderr)
    else:
        print(script)

    rebind_entries = result.get("template_rebind_entries", [])
    if rebind_entries:
        print(f"Rebind entries: {len(rebind_entries)}", file=sys.stderr)


def _parse_figma_input(raw: str) -> str:
    match = re.search(r'figma\.com/(?:design|file)/([a-zA-Z0-9]+)', raw)
    if match:
        return match.group(1)
    return raw


def main(argv: list | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dd", description="Declarative Design CLI")
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser("extract", help="Extract Figma file to SQLite")
    extract_parser.add_argument("source", help="Figma file URL or file key")
    extract_parser.add_argument("--token", help="Figma access token (or set FIGMA_ACCESS_TOKEN)")
    extract_parser.add_argument("--page", help="Figma page node ID to scope extraction")
    extract_parser.add_argument("--db", help="Output database path")

    cluster_parser = subparsers.add_parser("cluster", help="Cluster bindings into token proposals")
    cluster_parser.add_argument("--db", help="Database path (auto-detected if omitted)")
    cluster_parser.add_argument("--threshold", type=float, default=2.0, help="Color delta-E threshold")

    accept_parser = subparsers.add_parser("accept-all", help="Accept all proposed tokens")
    accept_parser.add_argument("--db", help="Database path")

    validate_parser = subparsers.add_parser("validate", help="Validate tokens for export")
    validate_parser.add_argument("--db", help="Database path")

    status_parser = subparsers.add_parser("status", help="Show pipeline status")
    status_parser.add_argument("--db", help="Database path")

    export_parser = subparsers.add_parser("export", help="Export tokens")
    export_parser.add_argument("format", choices=["css", "tailwind", "dtcg"], help="Export format")
    export_parser.add_argument("--db", help="Database path")
    export_parser.add_argument("--out", help="Output file path")

    curate_report_parser = subparsers.add_parser("curate-report", help="Show curation issues for agent review")
    curate_report_parser.add_argument("--db", help="Database path")
    curate_report_parser.add_argument("--json", action="store_true", help="Output as JSON (for agent consumption)")

    maintenance_parser = subparsers.add_parser("maintenance", help="Prune old extraction runs and export validations")
    maintenance_parser.add_argument("--db", help="Database path")
    maintenance_parser.add_argument("--keep-last", type=int, default=50, help="Number of recent runs to keep (default: 50)")
    maintenance_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    seed_catalog_parser = subparsers.add_parser("seed-catalog", help="Seed universal component type catalog")
    seed_catalog_parser.add_argument("--db", help="Database path")

    classify_parser = subparsers.add_parser("classify", help="Classify screen components against catalog")
    classify_parser.add_argument("--db", help="Database path")
    classify_parser.add_argument("--llm", action="store_true", help="Enable LLM classification (requires ANTHROPIC_API_KEY)")
    classify_parser.add_argument("--vision", action="store_true", help="Enable vision cross-validation (requires ANTHROPIC_API_KEY + FIGMA_ACCESS_TOKEN)")

    ir_parser = subparsers.add_parser("generate-ir", help="Generate CompositionSpec IR for a screen")
    ir_parser.add_argument("--db", help="Database path")
    ir_parser.add_argument("--screen", required=True, help="Screen ID or 'all'")

    gen_parser = subparsers.add_parser("generate", help="Generate Figma creation script from IR")
    gen_parser.add_argument("--db", help="Database path")
    gen_parser.add_argument("--screen", required=True, help="Screen ID")
    gen_parser.add_argument("--dry-run", action="store_true", help="Show stats only")

    supp_parser = subparsers.add_parser("extract-supplement", help="Extract Plugin API-only fields (componentKey, layoutPositioning, Grid)")
    supp_parser.add_argument("--db", help="Database path")
    supp_parser.add_argument("--port", type=int, default=9227, help="WebSocket port for PROXY_EXECUTE")
    supp_parser.add_argument("--batch-size", type=int, default=5, help="Screens per batch")
    supp_parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted, don't execute")

    gen_prompt_parser = subparsers.add_parser("generate-prompt", help="Generate Figma script from natural language prompt")
    gen_prompt_parser.add_argument("prompt", help="Natural language description of the screen to build")
    gen_prompt_parser.add_argument("--db", help="Database path")
    gen_prompt_parser.add_argument("--out", help="Write script to file instead of stdout")
    gen_prompt_parser.add_argument("--page", help="Figma page name for the generated screen")

    push_parser = subparsers.add_parser("push", help="Generate Figma push manifest (variables + rebind)")
    push_parser.add_argument("--db", help="Database path")
    push_parser.add_argument("--figma-state", help="Path to figma_get_variables JSON response")
    push_parser.add_argument("--phase", choices=["variables", "rebind", "all"], default="all", help="Which phase to generate")
    push_parser.add_argument("--dry-run", action="store_true", help="Show summary only, no action payloads")
    push_parser.add_argument("--writeback", action="store_true", help="Apply variable ID writeback from Figma response")
    push_parser.add_argument("--out", help="Write manifest to file instead of stdout")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "extract":
        token = resolve_token(args.token)
        file_key = _parse_figma_input(args.source)
        run_extract(
            file_key=file_key,
            token=token,
            page_id=args.page,
            db_path=args.db,
        )
    elif args.command == "cluster":
        db_path = detect_db_path(args.db)
        run_cluster(db_path, threshold=args.threshold)
    elif args.command == "accept-all":
        db_path = detect_db_path(args.db)
        run_accept_all(db_path)
    elif args.command == "validate":
        db_path = detect_db_path(args.db)
        run_validate(db_path)
    elif args.command == "status":
        db_path = detect_db_path(args.db)
        run_status(db_path)
    elif args.command == "export":
        db_path = detect_db_path(args.db)
        run_export(args.format, db_path, args.out)
    elif args.command == "curate-report":
        db_path = detect_db_path(args.db)
        _run_curate_report(db_path, as_json=args.json)
    elif args.command == "maintenance":
        db_path = detect_db_path(args.db)
        _run_maintenance(db_path, args)
    elif args.command == "seed-catalog":
        db_path = detect_db_path(args.db)
        _run_seed_catalog(db_path)
    elif args.command == "classify":
        db_path = detect_db_path(args.db)
        _run_classify(db_path, use_llm=args.llm, use_vision=args.vision)
    elif args.command == "generate-ir":
        db_path = detect_db_path(args.db)
        _run_generate_ir(db_path, args.screen)
    elif args.command == "generate":
        db_path = detect_db_path(args.db)
        _run_generate(db_path, int(args.screen), dry_run=args.dry_run)
    elif args.command == "extract-supplement":
        db_path = detect_db_path(args.db)
        _run_extract_supplement(db_path, args)
    elif args.command == "generate-prompt":
        db_path = detect_db_path(args.db)
        _run_generate_prompt(db_path, args.prompt, out=args.out, page_name=args.page)
    elif args.command == "push":
        db_path = detect_db_path(args.db)
        _run_push(db_path, args)


if __name__ == "__main__":
    main()
