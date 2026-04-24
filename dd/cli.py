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

from __future__ import annotations

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
from dd.extract_screens import update_screen_status
from dd.figma_api import (
    convert_node_tree,
    extract_top_level_frames,
    get_file_tree,
)
from dd.ingest_figma import FigmaIngestAdapter


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
    from dd._timing import StageTimer

    if db_path is None:
        db_path = f"{file_key}.declarative.db"

    print(f"Extracting file {file_key} → {db_path}")

    timer = StageTimer()
    timer.meta(command="extract", file_key=file_key, db_path=db_path)

    with timer.stage("init_db"):
        conn = init_db(db_path)

    with timer.stage("fetch_file_structure"):
        if page_id:
            file_json = get_file_tree(file_key, token, page_id=page_id, depth=2)
            frames = extract_top_level_frames(file_json, page_id=page_id, from_nodes_endpoint=True)
            file_name = f"figma:{file_key}"
        else:
            file_json = get_file_tree(file_key, token, depth=2)
            frames = extract_top_level_frames(file_json)
            file_name = file_json.get("name", f"figma:{file_key}")

    print(f"Found {len(frames)} top-level frames")

    with timer.stage("inventory", items=len(frames), unit="frames"):
        inventory = run_inventory(conn, file_key, file_name, frames)
    run_id = inventory["run_id"]
    pending = inventory["pending_screens"]
    timer.meta(screen_count=len(pending))

    print(f"Extracting {len(pending)} screens (run {run_id})...")

    # ADR-006: ingest goes through the boundary adapter so null responses
    # and transient errors become structured entries rather than silent
    # drops / NoneType crashes. The adapter batches internally.
    adapter = FigmaIngestAdapter(file_key=file_key, token=token)
    by_id = {s["figma_node_id"]: s for s in pending}

    import time
    start = time.time()

    # Stage 2a: network fetch (REST API batched). Pure network round-trips
    # and JSON-body decode. Isolated from the per-screen DB processing so
    # we can see network vs parse time separately.
    with timer.stage(
        "rest_fetch_screens",
        items=len(by_id), unit="screens",
        batch_size=adapter.BATCH_SIZE if hasattr(adapter, "BATCH_SIZE") else None,
    ):
        ingest_result = adapter.extract_screens(list(by_id.keys()))

    # Record each adapter-level failure on the DB row so the run summary
    # is honest. Kind is preserved in the error text for downstream
    # diagnosis (e.g. "node_not_found: ...").
    for err in ingest_result.errors:
        screen = by_id.get(err.id or "")
        if not screen:
            continue
        update_screen_status(
            conn, run_id, screen["screen_id"], "failed",
            error=f"{err.kind}: {err.error or ''}".strip(": "),
        )
        print(
            f"  {screen['name']} — FAILED: {err.kind} ({err.error or ''})",
            file=sys.stderr,
        )
    conn.commit()

    # Stage 2b: per-screen processing. Tree walk → parse → DB inserts.
    # This is where binding-creation O(nodes × tokens) lives — watch for
    # screens with many bindings vs screens with many nodes.
    total = len(pending)
    processed_ok = 0
    total_nodes = 0
    total_bindings = 0
    parse_times: list[tuple[str, int, float]] = []  # (name, node_count, ms)
    with timer.stage(
        "process_screens",
        items=len(ingest_result.extracted), unit="screens",
    ):
        for entry in ingest_result.extracted:
            figma_node_id = entry["id"]
            screen = by_id[figma_node_id]
            screen_id = screen["screen_id"]
            name = screen["name"]
            processed_ok += 1

            try:
                t0 = time.monotonic()
                # Pass the per-response `components` map through so
                # INSTANCE nodes resolve componentId -> component_key
                # at ingest time (perf pt 6 improvement #2). The
                # FigmaIngestAdapter captures this during REST fetch;
                # empty dict if older ingest.
                components_map = entry.get("components") or {}
                raw_response = convert_node_tree(
                    entry["document"], components_map=components_map
                )
                result = process_screen(conn, run_id, screen_id, figma_node_id, raw_response)
                elapsed_screen = time.monotonic() - t0
                total_nodes += result["node_count"]
                total_bindings += result["binding_count"]
                parse_times.append((name, result["node_count"], elapsed_screen * 1000))
                elapsed = time.time() - start
                done_so_far = processed_ok + len(ingest_result.errors)
                avg = elapsed / max(done_so_far, 1)
                eta = avg * (total - done_so_far)
                print(
                    f"  [{done_so_far}/{total}] {name} — "
                    f"{result['node_count']} nodes, {result['binding_count']} bindings "
                    f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)"
                )
            except Exception as e:
                # process_screen already updates status to 'failed' in its
                # inner except. We log here for visibility.
                print(
                    f"  {name} — FAILED during process_screen: {e}",
                    file=sys.stderr,
                )

    timer.meta(total_nodes=total_nodes, total_bindings=total_bindings)

    # Surface the slowest-per-node screens so we can see where binding
    # creation or parsing is dominating. Sorted by ms/node descending.
    if parse_times:
        per_node = sorted(
            ((n, c, t, t / max(c, 1)) for (n, c, t) in parse_times),
            key=lambda x: -x[3],
        )[:5]
        print("\nTop 5 slowest screens (ms per node):", file=sys.stderr)
        for name, ct, ms, per_n in per_node:
            print(
                f"  {name[:50]:50s} {ct:4d} nodes  {ms:7.0f}ms  {per_n:5.2f} ms/node",
                file=sys.stderr,
            )

    with timer.stage("complete_run"):
        summary = complete_run(conn, run_id)
    print(
        f"\nDone: {summary['completed']}/{summary['total_screens']} screens, "
        f"{summary['failed']} failed, {summary['skipped']} skipped"
    )
    if ingest_result.errors:
        # Surface the structured channel so callers/CI can tell apart
        # "clean run" from "run completed but lossy".
        print(
            f"  (ingest reported {len(ingest_result.errors)} "
            f"structured error{'s' if len(ingest_result.errors) != 1 else ''})",
            file=sys.stderr,
        )

    # ADR-007 Session A: component_key_registry is a Mode 1 prerequisite.
    # Build it at the end of every extract so downstream generation can
    # resolve INSTANCE nodes to their masters. Without this, Mode 1's
    # gate evaluates False for every INSTANCE and the renderer silently
    # falls through to Mode 2 (createFrame). See project_adr007_execution_plan.md.
    try:
        with timer.stage("component_key_registry"):
            from dd.templates import build_component_key_registry
            ckr_count = build_component_key_registry(conn)
        print(f"component_key_registry: {ckr_count} rows")
    except Exception as exc:
        print(
            f"  component_key_registry build failed: {exc}",
            file=sys.stderr,
        )

    conn.close()
    timer.print_summary()


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


def _run_generate(
    db_path: str, screen_id: int, dry_run: bool = False,
    canvas_x: float | None = None, canvas_y: float | None = None,
) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.renderers.figma import generate_screen

    canvas_position = None
    if canvas_x is not None or canvas_y is not None:
        canvas_position = (canvas_x or 0.0, canvas_y or 0.0)

    conn = get_connection(db_path)
    result = generate_screen(
        conn, screen_id,
        canvas_position=canvas_position,
    )
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


def _run_classify(
    db_path: str,
    use_llm: bool = False,
    use_vision: bool = False,
    truncate: bool = False,
    since: int | None = None,
    limit: int | None = None,
    three_source: bool = False,
    classifier_v2: bool = False,
    force_reclassify: bool = False,
) -> None:
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if three_source or classifier_v2:
        # Both three-source and classifier-v2 require both LLM +
        # vision stages. Flip both flags so downstream wiring
        # (client + fetch_screenshot) follows the normal path.
        use_llm = True
        use_vision = True

    from dd.catalog import seed_catalog
    from dd.classify import run_classification, truncate_classifications

    conn = get_connection(db_path)

    # Ensure catalog is seeded before classifying
    seed_catalog(conn)

    if truncate:
        # M7.0.a path: full-cascade rerun with updated prompts.
        # Wipe the classification tables cleanly before starting.
        # Catalog + CKR + component_templates are not touched.
        result = truncate_classifications(conn)
        print(
            f"Truncated classifications: "
            f"{result['instances_deleted']} instances, "
            f"{result['skeletons_deleted']} skeletons."
        )

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
        # Classifier v2 uses scale=2 — 4x source pixels for small-
        # node crops; spotlight pipeline upscales to 400px min-side
        # so the vision model sees sharper detail. v1 stays at
        # scale=1 for byte-identical behaviour.
        scale = 2 if classifier_v2 else 1
        fetch_screenshot = make_figma_screenshot_fetcher(scale=scale)

    def _progress(i: int, n: int, sid: int, per_screen: dict) -> None:
        parts = [
            f"[{i}/{n}]", f"screen={sid}",
            f"formal={per_screen.get('formal', 0)}",
            f"heuristic={per_screen.get('heuristic', 0)}",
        ]
        if use_llm:
            parts.append(f"llm={per_screen.get('llm', 0)}")
        if use_vision and "vision" in per_screen:
            v = per_screen["vision"]
            parts.append(
                f"vision={v['validated']} "
                f"(✓{v['agreed']}/✗{v['disagreed']})"
            )
        if three_source and "vision_ps" in per_screen:
            parts.append(f"ps={per_screen['vision_ps']}")
        print(" ".join(parts), flush=True)

    if classifier_v2:
        from dd.classify_v2 import run_classification_v2
        result = run_classification_v2(
            conn, file_id,
            client=client,
            file_key=file_key,
            fetch_screenshot=fetch_screenshot,
            since_screen_id=since,
            limit=limit,
            force_reclassify=force_reclassify,
        )
    else:
        result = run_classification(
            conn, file_id,
            client=client,
            file_key=file_key if use_vision else None,
            fetch_screenshot=fetch_screenshot,
            since_screen_id=since,
            limit=limit,
            progress_callback=_progress,
            three_source=three_source,
        )
    conn.close()

    print("\nClassification complete:")
    print(f"  Screens processed:     {result['screens_processed']}")
    # classifier_v2 returns a different summary shape — skip the
    # per-stage counts (formal/heuristic/llm/parent_links) that only
    # exist on the non-v2 result dict.
    if not classifier_v2:
        print(f"  Formal classified:     {result['formal_classified']}")
        print(f"  Heuristic classified:  {result['heuristic_classified']}")
        if use_llm:
            print(f"  LLM classified:        {result['llm_classified']}")
        print(f"  Parent links:          {result['parent_links']}")
    if use_vision and not three_source:
        v = result["vision"]
        print(f"  Vision validated:      {v['validated']} (agreed={v['agreed']}, disagreed={v['disagreed']})")
    if three_source:
        print(f"  Vision PS applied:     {result.get('vision_ps_applied', 0)}")
        print(f"  Vision CS applied:     {result.get('vision_cs_applied', 0)}")
        consensus = result.get("consensus") or {}
        if consensus:
            print(f"  Consensus breakdown:")
            for method in sorted(consensus.keys()):
                print(f"    {method:<28} {consensus[method]}")
    if classifier_v2:
        print(f"  Dedup candidates:      {result.get('dedup_candidates', 0)}")
        print(f"  Dedup groups:          {result.get('dedup_groups', 0)}")
        print(f"  LLM inserts:           {result.get('llm_inserts', 0)}")
        print(f"  Vision PS applied:     {result.get('vision_ps_applied', 0)}")
        print(f"  Vision CS applied:     {result.get('vision_cs_applied', 0)}")
        print(f"  Vision SoM applied:    {result.get('vision_som_applied', 0)}")
        consensus = result.get("consensus") or {}
        if consensus:
            print(f"  Consensus breakdown:")
            for method in sorted(consensus.keys()):
                print(f"    {method:<28} {consensus[method]}")
    print(f"  Skeletons generated:   {result['skeletons_generated']}")


def _run_classify_review(
    db_path: str,
    *,
    screen_id: int | None = None,
    limit: int | None = None,
    no_preview: bool = False,
) -> None:
    """CLI entrypoint for the Tier 1.5 interactive review loop.

    Walks flagged rows on the given screen (or all flagged screens
    when no --screen is given), shows LLM/PS/CS verdicts + reasons +
    Figma deep-link, and records the human decision into
    `classification_reviews`.
    """
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.classify_review import run_review_tui

    conn = get_connection(db_path)
    cursor = conn.execute("SELECT file_key FROM files LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        print("Error: No file found in database.", file=sys.stderr)
        conn.close()
        sys.exit(1)
    file_key = row[0]

    fetch_screenshot = None
    if not no_preview:
        try:
            fetch_screenshot = make_figma_screenshot_fetcher()
        except Exception as e:
            # Screenshot previews are optional — don't block review
            # when Figma auth is misconfigured.
            print(
                f"  (preview disabled: {e!r})",
                file=sys.stderr,
            )

    summary = run_review_tui(
        conn,
        file_key=file_key,
        screen_id=screen_id,
        limit=limit,
        fetch_screenshot=fetch_screenshot,
    )

    conn.close()

    print("\nReview complete:")
    for decision_type, count in sorted(summary.items()):
        print(f"  {decision_type:<15} {count}")


def _run_classify_audit(
    db_path: str,
    *,
    sample: int,
    screen_id: int | None = None,
    seed: int | None = None,
    no_preview: bool = False,
) -> None:
    """CLI entrypoint for the audit spot-check loop."""
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.classify_audit import run_audit_tui

    conn = get_connection(db_path)
    cursor = conn.execute("SELECT file_key FROM files LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        print("Error: No file found in database.", file=sys.stderr)
        conn.close()
        sys.exit(1)
    file_key = row[0]

    fetch_screenshot = None
    if not no_preview:
        try:
            fetch_screenshot = make_figma_screenshot_fetcher()
        except Exception as e:
            print(
                f"  (preview disabled: {e!r})",
                file=sys.stderr,
            )

    summary = run_audit_tui(
        conn,
        n=sample,
        file_key=file_key,
        seed=seed,
        screen_id=screen_id,
        fetch_screenshot=fetch_screenshot,
    )

    conn.close()

    print("\nAudit complete:")
    for action, count in sorted(summary.items()):
        print(f"  {action:<15} {count}")


def _run_classify_review_index(
    db_path: str,
    *,
    out: str,
    screen_id: int | None = None,
    limit: int | None = None,
    no_screenshots: bool = False,
) -> None:
    """Render the static HTML companion page.

    Opens alongside `dd classify-review` — the terminal drives
    decisions, the browser shows the visual context.
    """
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.classify_review import render_review_index_html

    conn = get_connection(db_path)
    cursor = conn.execute("SELECT file_key FROM files LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        print("Error: No file found in database.", file=sys.stderr)
        conn.close()
        sys.exit(1)
    file_key = row[0]

    fetch_screenshot = None
    if not no_screenshots:
        try:
            fetch_screenshot = make_figma_screenshot_fetcher()
        except Exception as e:
            print(
                f"  (screenshots disabled: {e!r})",
                file=sys.stderr,
            )

    html_output = render_review_index_html(
        conn,
        file_key=file_key,
        screen_id=screen_id,
        limit=limit,
        fetch_screenshot=fetch_screenshot,
    )
    conn.close()

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_output, encoding="utf-8")
    print(f"Wrote review index: {out_path}")


def make_figma_screenshot_fetcher(
    session=None,
    token: str | None = None,
    max_retries: int = 5,
    retry_delay: float = 2.0,
    scale: int = 1,
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
        params = {
            "ids": ",".join(node_ids), "format": "png",
            "scale": str(scale),
        }

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
    from dd._timing import StageTimer

    timer = StageTimer()
    timer.meta(command="extract-supplement", db_path=db_path,
               port=args.port, batch_size=args.batch_size)

    conn = get_connection(db_path)

    with timer.stage("classify_screens"):
        classify_screens(conn)

    screen_count = conn.execute(
        "SELECT COUNT(*) FROM screens WHERE screen_type = 'app_screen'"
    ).fetchone()[0]
    timer.meta(screen_count=screen_count)

    if args.dry_run:
        print(f"Would extract Plugin API fields for {screen_count} app screens")
        print(f"  Port: {args.port}")
        print(f"  Batch size: {args.batch_size}")
        print("  Fields: componentKey, layoutPositioning, Grid properties")
        conn.close()
        return

    def execute_via_ws(script: str) -> dict:
        """Execute JS in Figma via PROXY_EXECUTE WebSocket.

        Uses process.stdout.write with a drain callback before exit —
        Node's process.exit() doesn't wait for pipe flush, and on
        macOS the default pipe buffer is 64KB. Without the callback,
        large result payloads get silently truncated at the 64KB
        boundary.
        """
        import subprocess
        node_js = (
            'const WebSocket = require("ws");'
            # Use localhost so we match the Bridge's IPv6 bind on systems
            # where ::1 is preferred over 127.0.0.1.
            f'const ws = new WebSocket("ws://localhost:{args.port}");'
            f'const code = {json.dumps(script)};'
            'ws.on("open", () => {'
            '  ws.send(JSON.stringify({ type: "PROXY_EXECUTE", id: "supp", code, timeout: 60000 }));'
            '});'
            'ws.on("message", (data) => {'
            '  const msg = JSON.parse(data);'
            '  if (msg.type === "PROXY_EXECUTE_RESULT") {'
            '    process.stdout.write(JSON.stringify(msg), () => {'
            '      ws.close(); process.exit(0);'
            '    });'
            '  }'
            '});'
            'ws.on("error", (err) => { process.stdout.write(JSON.stringify({error: err.message}), () => process.exit(1)); });'
            'setTimeout(() => { process.stdout.write(JSON.stringify({error: "timeout"}), () => process.exit(1)); }, 65000);'
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

    with timer.stage("run_supplement", items=screen_count, unit="screens"):
        result = run_supplement(conn, execute_via_ws, batch_size=args.batch_size)
    conn.close()

    print(f"\nDone: {result['total_nodes']} nodes updated")
    print(f"  component_key: {result['component_key']}")
    print(f"  layout_positioning: {result['layout_positioning']}")
    print(f"  grid: {result['grid']}")
    if result["failed"] > 0:
        print(f"  failed: {result['failed']} screens")
    timer.meta(
        total_nodes=result.get("total_nodes", 0),
        component_key=result.get("component_key", 0),
        layout_positioning=result.get("layout_positioning", 0),
        failed=result.get("failed", 0),
    )
    timer.print_summary()


def _run_extract_plugin(db_path: str, args: argparse.Namespace) -> None:
    """Unified Plugin-API extraction (pt 6 #3).

    One WebSocket round-trip per batch replaces the five separate passes
    (supplement + 4x targeted). Reuses the same WS executor helper as
    ``_run_extract_supplement`` and dispatches every field set through
    the existing apply_* functions via ``apply_plugin``.
    """
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.db import classify_screens
    from dd.extract_plugin import run_plugin_extract
    from dd._timing import StageTimer

    timer = StageTimer()
    timer.meta(
        command="extract-plugin", db_path=db_path,
        port=args.port, batch_size=args.batch_size,
        collect_component_key=args.collect_component_key,
    )

    conn = get_connection(db_path)

    with timer.stage("classify_screens"):
        classify_screens(conn)

    screen_count = conn.execute(
        "SELECT COUNT(*) FROM screens WHERE screen_type = 'app_screen'"
    ).fetchone()[0]
    timer.meta(screen_count=screen_count)

    if args.dry_run:
        print(f"Would run unified plugin extract for {screen_count} app screens")
        print(f"  Port: {args.port}")
        print(f"  Batch size: {args.batch_size}")
        print(f"  collect_component_key: {args.collect_component_key}")
        conn.close()
        return

    def execute_via_ws(script: str) -> dict:
        """Execute JS in Figma via PROXY_EXECUTE WebSocket (pt 6 #3 path).

        Identical mechanism to ``_run_extract_supplement`` — the single
        unified script is just longer than any individual pass's script.
        Timeout is bumped accordingly.
        """
        import subprocess
        # IMPORTANT: the unified plugin extract can return payloads
        # well over 64KB (relativeTransform for every node, vector
        # geometries, etc.). macOS pipes default to a 64KB buffer,
        # and Node's process.exit() DOES NOT wait for the stdout
        # stream to drain — any unflushed data beyond the buffer
        # boundary is silently dropped. The write callback below
        # fires only after the kernel has accepted the entire
        # payload, so we exit cleanly with the full JSON intact.
        node_js = (
            'const WebSocket = require("ws");'
            f'const ws = new WebSocket("ws://localhost:{args.port}");'
            f'const code = {json.dumps(script)};'
            'ws.on("open", () => {'
            '  ws.send(JSON.stringify({ type: "PROXY_EXECUTE", id: "plugin", code, timeout: 90000 }));'
            '});'
            'ws.on("message", (data) => {'
            '  const msg = JSON.parse(data);'
            '  if (msg.type === "PROXY_EXECUTE_RESULT") {'
            '    process.stdout.write(JSON.stringify(msg), () => {'
            '      ws.close(); process.exit(0);'
            '    });'
            '  }'
            '});'
            'ws.on("error", (err) => { process.stdout.write(JSON.stringify({error: err.message}), () => process.exit(1)); });'
            'setTimeout(() => { process.stdout.write(JSON.stringify({error: "timeout"}), () => process.exit(1)); }, 95000);'
        )
        result = subprocess.run(
            [_find_node_binary(), "-e", node_js],
            capture_output=True, text=True, timeout=100,
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

    print(
        f"Unified plugin extract: {screen_count} app screens "
        f"(port {args.port}, batch {args.batch_size}, "
        f"collect_component_key={args.collect_component_key})"
    )

    with timer.stage("run_plugin_extract", items=screen_count, unit="screens"):
        result = run_plugin_extract(
            conn,
            execute_via_ws,
            batch_size=args.batch_size,
            collect_component_key=args.collect_component_key,
        )
    conn.close()

    print(f"\nDone: {result['total_nodes_touched']} nodes touched")
    print(f"  supplement : lp={result['layout_positioning']}  ck={result['component_key']}  "
          f"grid={result['grid']}  overrides={result['overrides']}")
    print(f"  properties : mask={result['is_mask']}  bool_op={result['boolean_operation']}  "
          f"corner_sm={result['corner_smoothing']}  arc={result['arc_data']}")
    print(f"  sizing     : lsh={result['layout_sizing_h']}  lsv={result['layout_sizing_v']}  "
          f"tar={result['text_auto_resize']}  fst={result['font_style']}  "
          f"lw={result['layout_wrap']}")
    print(f"  transforms : rt={result['relative_transform']}  ot={result['opentype_features']}  "
          f"w/h={result['width_height']}  vp={result['vector_paths']}")
    print(f"  vector-geo : fill={result['fill_geometry']}  stroke={result['stroke_geometry']}")
    if "vector_assets_built" in result:
        print(f"  asset store: {result['vector_assets_built']} content-addressed SVG paths")
    if "vector_assets_error" in result:
        print(f"  asset store: FAILED — {result['vector_assets_error'][:120]}")
    if result["failed"] > 0:
        print(f"  failed: {result['failed']} screens")

    timer.meta(
        total_nodes_touched=result.get("total_nodes_touched", 0),
        failed=result.get("failed", 0),
    )
    timer.print_summary()


def _run_verify(db_path: str, args: argparse.Namespace) -> None:
    """ADR-007 Position 3: verify a rendered Figma subtree against its IR.

    Reads the IR from the DB (via ``generate_ir``) and the rendered-tree
    walk from ``--rendered-ref`` (a JSON file produced by the caller,
    typically by the harness or a ``figma_execute`` payload). Produces
    a RenderReport. Exit code is non-zero when ``is_parity != True``.
    """
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from dd.ir import generate_ir
    from dd.verify_figma import FigmaRenderVerifier
    from dataclasses import asdict

    rendered_path = Path(args.rendered_ref)
    if not rendered_path.exists():
        print(f"Error: --rendered-ref file not found: {rendered_path}", file=sys.stderr)
        sys.exit(1)
    rendered_ref = json.loads(rendered_path.read_text())

    conn = get_connection(db_path)
    try:
        ir_result = generate_ir(conn, int(args.screen))
        spec = ir_result["spec"]
    finally:
        conn.close()

    report = FigmaRenderVerifier().verify(spec, rendered_ref)

    if args.json:
        payload = {
            "backend": report.backend,
            "ir_node_count": report.ir_node_count,
            "rendered_node_count": report.rendered_node_count,
            "is_parity": report.is_parity,
            "parity_ratio": report.parity_ratio(),
            "errors": [asdict(e) for e in report.errors],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"RenderReport (screen {args.screen}, backend={report.backend}):")
        print(f"  ir_node_count:       {report.ir_node_count}")
        print(f"  rendered_node_count: {report.rendered_node_count}")
        print(f"  is_parity:           {report.is_parity}")
        print(f"  parity_ratio:        {report.parity_ratio():.4f}")
        print(f"  errors:              {len(report.errors)}")
        for err in report.errors[:20]:
            print(f"    kind={err.kind} id={err.id}  {(err.error or '')[:80]}")
        if len(report.errors) > 20:
            print(f"    ... ({len(report.errors) - 20} more)")

    if not report.is_parity:
        sys.exit(1)


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


def _run_induce_variants(db_path: str, args: argparse.Namespace) -> None:
    """Induce variant_token_binding rows for the user's corpus (ADR-008).

    Opt-in Stream-B inducer: clusters classified instances per catalog
    type, calls Gemini 3.1 Pro to label each cluster with a variant
    name from a closed vocabulary, and persists one row per
    (catalog_type, variant, slot) to ``variant_token_binding``.
    ``ProjectCKRProvider`` queries these rows at Mode-3 resolution
    time to attach project-native presentation values.

    Usage: ``dd induce-variants [--db PATH]``. Idempotent — re-running
    updates existing rows (UPSERT on the unique key).
    """
    from dd.cluster_variants import induce_variants
    from dd.visual_inspect import _default_gemini_call, VLM_PROMPT

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print(
            "Warning: GOOGLE_API_KEY not set — inducer will run with a stub "
            "VLM that labels every cluster 'unknown' (rows persist as "
            "custom_N). Set GOOGLE_API_KEY to get real variant labels.",
            file=sys.stderr,
        )

    def vlm_call(prompt: str, images: list) -> dict:
        """Adapter from the inducer's simple call shape to Gemini 3.1 Pro.

        v0.1: the inducer shell doesn't pass real rendered images yet
        (cluster analysis is a shell). When images are present, route
        through the existing Gemini call; otherwise return a conservative
        'unknown' verdict so the row persists as custom_N.
        """
        if not images or not api_key:
            return {"verdict": "unknown", "confidence": 0.0}
        try:
            import json as _json
            import re as _re
            raw = _default_gemini_call(prompt, images[0], api_key)
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip()
            if text.startswith("```"):
                text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.S)
            data = _json.loads(text)
            return {
                "verdict": str(data.get("verdict", "unknown")).lower(),
                "confidence": float(data.get("confidence", 0.5)),
            }
        except Exception as e:
            print(f"  VLM call failed: {e}", file=sys.stderr)
            return {"verdict": "unknown", "confidence": 0.0}

    conn = get_connection(db_path)
    try:
        written_per_type = induce_variants(conn, vlm_call)
    finally:
        conn.close()

    total_rows = sum(written_per_type.values())
    print(f"Induced variant_token_binding rows for {len(written_per_type)} catalog types:")
    for catalog_type in sorted(written_per_type.keys()):
        rows = written_per_type[catalog_type]
        print(f"  {catalog_type:<25} {rows:>3} rows")
    print(f"Total: {total_rows} rows written.")


def _run_inspect_experiment(args: argparse.Namespace) -> None:
    """Auto-inspect an experiment's rendered output before escalating to rating.

    Reads ``<path>/artefacts/<slug>/walk.json`` (+ optional ``screenshot.png``
    when ``--vlm``), produces a ``SanityReport``, writes ``sanity_report.json``
    and a Markdown memo fragment. Exits non-zero when the gate fails
    (more than half the prompts categorically broken).
    """
    from dd.visual_inspect import (
        compile_sanity_report,
        render_memo_fragment,
        write_report,
    )

    experiment_dir = Path(args.path).resolve()
    if not experiment_dir.is_dir():
        print(f"Error: experiment directory not found: {experiment_dir}", file=sys.stderr)
        sys.exit(1)

    api_key: str | None = None
    if args.vlm:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print(
                "Warning: --vlm requested but GOOGLE_API_KEY is not set — "
                "running rule-based gate only.",
                file=sys.stderr,
            )

    report = compile_sanity_report(
        experiment_dir,
        use_vlm=args.vlm and bool(api_key),
        api_key=api_key,
    )

    json_path = write_report(report, experiment_dir)
    memo_path = experiment_dir / "sanity_report.md"
    memo_path.write_text(render_memo_fragment(report, experiment_dir))

    print(
        f"Gate {'PASSES' if report.gate_passes else 'FAILS'}: "
        f"{report.broken} broken / {report.partial} partial / {report.ok} ok "
        f"(of {report.total})"
    )
    print(f"  {json_path}")
    print(f"  {memo_path}")

    if not report.gate_passes:
        sys.exit(1)


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
    classify_parser.add_argument(
        "--truncate", action="store_true",
        help=(
            "Delete all rows from screen_component_instances and "
            "screen_skeletons before reclassifying. Used by M7.0.a's "
            "full-cascade rerun. Catalog + CKR + templates untouched."
        ),
    )
    classify_parser.add_argument(
        "--since", type=int, default=None,
        help=(
            "Resume from screen id >= SINCE. Crude but effective — "
            "combined with per-row INSERT OR IGNORE, lets a crashed "
            "run pick up near where it left off. Redoes the most "
            "recent screen (cheap for formal/heuristic; incurs one "
            "duplicate LLM batch for that screen)."
        ),
    )
    classify_parser.add_argument(
        "--limit", type=int, default=None,
        help=(
            "Stop after processing this many screens. Useful for "
            "dry-runs (--limit 1 probes a single screen before "
            "committing token budget to the full corpus)."
        ),
    )
    classify_parser.add_argument(
        "--three-source", action="store_true",
        help=(
            "Run the three-source cascade (M7.0.a): formal/heuristic/"
            "LLM produce the primary verdict, then vision per-screen "
            "(PS) and vision cross-screen (CS) run on the same LLM "
            "candidate set, then consensus rule v1 votes. All three "
            "verdicts are persisted; canonical_type becomes the "
            "computed consensus. Implies --llm + --vision (both are "
            "required to produce the three sources). Budget: ~$35 "
            "on the full 204-screen Dank corpus."
        ),
    )
    classify_parser.add_argument(
        "--classifier-v2", action="store_true",
        help=(
            "Classifier v2 (M7.0.a step 11): corpus-wide dedup by "
            "structural signature + full-screen node filter + per-"
            "node spotlight crops to the vision model. Expected "
            "5-8x fewer API calls, higher accuracy on small-bbox "
            "nodes. Implies --llm + --vision. See "
            "docs/plan-classifier-v2.md."
        ),
    )
    classify_parser.add_argument(
        "--rerun", action="store_true",
        help=(
            "Re-classify every eligible node regardless of existing "
            "classifications. Uses UPSERT so existing sci rows are "
            "updated in place — classification_reviews (human "
            "decisions, FK'd via ON DELETE CASCADE) are preserved. "
            "Only meaningful with --classifier-v2; typical use is "
            "refreshing verdicts after a catalog expansion. Does NOT "
            "touch node_id, screen_id, parent_instance_id, or the "
            "review trail."
        ),
    )

    classify_review_parser = subparsers.add_parser(
        "classify-review",
        help=(
            "Interactively review flagged classification rows "
            "(M7.0.a Tier 1.5). Walks consensus-flagged rows on a "
            "screen, shows LLM/PS/CS verdicts + reasons + Figma "
            "deep-link, records the human decision."
        ),
    )
    classify_review_parser.add_argument("--db", help="Database path")
    classify_review_parser.add_argument(
        "--screen", type=int, default=None,
        help="Screen ID to review (defaults to all flagged screens)",
    )
    classify_review_parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after reviewing this many rows",
    )
    classify_review_parser.add_argument(
        "--no-preview", action="store_true",
        help=(
            "Skip fetching + opening the local PNG preview. Useful "
            "when Figma REST is rate-limited or when triaging "
            "offline."
        ),
    )

    classify_audit_parser = subparsers.add_parser(
        "classify-audit",
        help=(
            "Spot-check unflagged classification rows (M7.0.a "
            "Step 8). Catches systematic errors where all three "
            "sources agreed on the wrong answer. Samples N "
            "unflagged + unreviewed rows; decisions record "
            "decision_type='audit' in classification_reviews."
        ),
    )
    classify_audit_parser.add_argument("--db", help="Database path")
    classify_audit_parser.add_argument(
        "--sample", type=int, default=25,
        help="Number of rows to sample (default: 25).",
    )
    classify_audit_parser.add_argument(
        "--screen", type=int, default=None,
        help="Screen ID to sample from (defaults to all screens).",
    )
    classify_audit_parser.add_argument(
        "--seed", type=int, default=None,
        help=(
            "Seed for deterministic sampling. When set, rerunning "
            "with the same seed returns the same rows — useful for "
            "picking up a paused audit pass."
        ),
    )
    classify_audit_parser.add_argument(
        "--no-preview", action="store_true",
        help="Skip opening the local PNG preview.",
    )

    classify_review_index_parser = subparsers.add_parser(
        "classify-review-index",
        help=(
            "Dump a scrollable HTML companion page listing every "
            "flagged row with screenshot + three-source verdicts + "
            "Figma deep-link. Self-contained; open in a browser "
            "while driving classify-review in the terminal."
        ),
    )
    classify_review_index_parser.add_argument("--db", help="Database path")
    classify_review_index_parser.add_argument(
        "--screen", type=int, default=None,
        help="Screen ID to render (defaults to all flagged screens)",
    )
    classify_review_index_parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N rows",
    )
    classify_review_index_parser.add_argument(
        "--out", default="render_batch/m7_review_index.html",
        help=(
            "Output HTML path (default: "
            "render_batch/m7_review_index.html)."
        ),
    )
    classify_review_index_parser.add_argument(
        "--no-screenshots", action="store_true",
        help=(
            "Skip fetching node screenshots — faster, but no visual "
            "context. Useful for offline triage or when Figma REST "
            "is rate-limited."
        ),
    )

    ir_parser = subparsers.add_parser("generate-ir", help="Generate CompositionSpec IR for a screen")
    ir_parser.add_argument("--db", help="Database path")
    ir_parser.add_argument("--screen", required=True, help="Screen ID or 'all'")

    gen_parser = subparsers.add_parser("generate", help="Generate Figma creation script from IR")
    gen_parser.add_argument("--db", help="Database path")
    gen_parser.add_argument("--screen", required=True, help="Screen ID")
    gen_parser.add_argument("--dry-run", action="store_true", help="Show stats only")
    gen_parser.add_argument(
        "--canvas-x", type=float, default=None,
        help="Place the rendered screen's root frame at this x "
             "coordinate on the Figma canvas. Used by grid_render.py "
             "to lay multiple screens out side-by-side.",
    )
    gen_parser.add_argument(
        "--canvas-y", type=float, default=None,
        help="Place the rendered screen's root frame at this y "
             "coordinate on the Figma canvas.",
    )
    supp_parser = subparsers.add_parser("extract-supplement", help="Extract Plugin API-only fields (componentKey, layoutPositioning, Grid)")
    supp_parser.add_argument("--db", help="Database path")
    supp_parser.add_argument("--port", type=int, default=9227, help="WebSocket port for PROXY_EXECUTE")
    supp_parser.add_argument("--batch-size", type=int, default=5, help="Screens per batch")
    supp_parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted, don't execute")

    plugin_parser = subparsers.add_parser(
        "extract-plugin",
        help="Unified Plugin-API extraction (perf pt 6 #3): supplement + properties + "
             "sizing + transforms + vector-geometry in one walk.",
    )
    plugin_parser.add_argument("--db", help="Database path")
    plugin_parser.add_argument("--port", type=int, default=9227, help="WebSocket port for PROXY_EXECUTE")
    plugin_parser.add_argument("--batch-size", type=int, default=10, help="Screens per batch")
    plugin_parser.add_argument(
        "--collect-component-key",
        action="store_true",
        help="Fall back to getMainComponentAsync per INSTANCE. Default off — "
             "REST ingest now populates component_key from the response's "
             "components map (see perf pt 6 #2). Enable only if the REST "
             "map was unavailable for your extract.",
    )
    plugin_parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted, don't execute")

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

    induce_parser = subparsers.add_parser(
        "induce-variants",
        help="Induce variant_token_binding rows for Mode 3 (ADR-008 Stream B)",
    )
    induce_parser.add_argument("--db", help="Database path")

    inspect_parser = subparsers.add_parser(
        "inspect-experiment",
        help="Auto-inspect an experiment's rendered output (visual-sanity gate)",
    )
    inspect_parser.add_argument(
        "path",
        help="Path to the experiment directory (containing ./artefacts/<slug>/walk.json)",
    )
    inspect_parser.add_argument(
        "--vlm",
        action="store_true",
        help="Run the Gemini 3.1 Pro VLM pass (requires GOOGLE_API_KEY)",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify a rendered Figma subtree against its IR (ADR-007 Position 3)",
    )
    verify_parser.add_argument("--db", help="Database path")
    verify_parser.add_argument("--screen", required=True, help="Screen ID (DB id)")
    verify_parser.add_argument(
        "--rendered-ref",
        required=True,
        help="Path to JSON file with {\"eid_map\": {eid: {type, characters?, ...}}} "
             "from a rendered Figma subtree walk",
    )
    verify_parser.add_argument(
        "--json", action="store_true", help="Emit the full RenderReport as JSON",
    )

    # ── Stage 3 — `dd design` session-loop CLI ──────────────────────────
    design_parser = subparsers.add_parser(
        "design",
        help="Run the agent-driven design session loop (Stage 3 of "
             "docs/plan-authoring-loop.md)",
    )
    design_parser.add_argument("--db", help="Database path")
    design_subparsers = design_parser.add_subparsers(
        dest="design_command",
    )
    # `dd design --brief "..."`. The brief flag exists at the top
    # `design` parser too so `dd design --brief ...` (no subcommand)
    # works as documented in the plan.
    design_parser.add_argument(
        "--brief",
        help="Natural-language brief — starts a NEW design session.",
    )
    design_parser.add_argument(
        "--max-iters", type=int, default=4,
        help="Max iterations per session (default 4 — demo-friendly; "
             "bump to 8-10 for deeper sessions)",
    )
    # M1 — close the Figma round-trip. --starting-screen loads a real
    # screen from the project DB as the agent's starting context;
    # --render-to-figma additionally ships the final variant (and a
    # fresh render of the original) to the live plugin bridge so the
    # demo lands visibly on a new page. --project-db splits "where
    # sessions persist" from "where the source-of-truth screens live";
    # defaults to --db when omitted (single-DB workflow).
    design_parser.add_argument(
        "--starting-screen", type=int, default=None,
        help="Screen ID in the project DB to use as the agent's "
             "starting context (instead of the default empty SYNTHESIZE "
             "doc).",
    )
    design_parser.add_argument(
        "--render-to-figma", action="store_true",
        help="After the session halts, render the starting screen + "
             "the final variant to a new Figma page via the plugin "
             "bridge on port 9228. Requires --starting-screen.",
    )
    design_parser.add_argument(
        "--project-db",
        help="Path to the project DB (classified screens, tokens, "
             "CKR). Defaults to --db when omitted.",
    )
    # Diagnostic side-channel: write the generated JS render scripts
    # to <dir>/original.js and <dir>/variant.js so a human can inspect
    # what would ship to the Figma bridge. Additive — the bridge call
    # still runs. Useful when `--render-to-figma` times out or lands
    # an unexpected result and the question is "what did we send?".
    design_parser.add_argument(
        "--dump-scripts",
        metavar="DIR",
        help="Write the generated JS render scripts to "
             "<DIR>/original.js and <DIR>/variant.js for inspection "
             "(additive — bridge calls still run). Requires "
             "--render-to-figma.",
    )

    design_resume_parser = design_subparsers.add_parser(
        "resume",
        help="Continue an existing variant (or branch from a non-leaf)",
    )
    design_resume_parser.add_argument(
        "variant_id",
        help="Variant ULID to resume from. Resuming from a non-leaf "
             "creates a sibling chain — branching falls out for free.",
    )
    design_resume_parser.add_argument(
        "--max-iters", type=int, default=4,
        help="Max iterations (default 4 — matches --brief default)",
    )
    design_resume_parser.add_argument("--db", help="Database path")
    # M2 demo-blocker — multi-turn iteration needs the same Figma
    # round-trip flags on `resume` as on `--brief`. Without these,
    # the user can kick off a session with `--brief --render-to-figma`
    # but can't re-render after `resume`, which kills the
    # progressive-constraint demo (brief A, then resume with
    # refining brief B). ``starting_screen`` is not persisted on the
    # session row — user re-passes it, same as `--brief`.
    design_resume_parser.add_argument(
        "--starting-screen", type=int, default=None,
        help="Screen ID in the project DB to use as the original-"
             "render baseline (same value used on the initial "
             "`--brief` run). Required with --render-to-figma.",
    )
    design_resume_parser.add_argument(
        "--render-to-figma", action="store_true",
        help="After the resume session halts, render the starting "
             "screen + the NEW final variant to a new Figma page via "
             "the plugin bridge. Each resume lands on its own page "
             "(variant ULID in the page name), so iterations don't "
             "stack on top of each other.",
    )
    design_resume_parser.add_argument(
        "--project-db",
        help="Path to the project DB (classified screens, tokens, "
             "CKR). Defaults to --db when omitted.",
    )
    design_resume_parser.add_argument(
        "--dump-scripts",
        metavar="DIR",
        help="Write the generated JS render scripts to "
             "<DIR>/original.js and <DIR>/variant.js for inspection "
             "(additive — bridge calls still run). Requires "
             "--render-to-figma.",
    )

    design_score_parser = design_subparsers.add_parser(
        "score",
        help="Score every variant in a session via render+verify "
             "(deferred-scoring entry point per A2)",
    )
    design_score_parser.add_argument(
        "session_id", help="Session ULID to score",
    )
    design_score_parser.add_argument("--db", help="Database path")

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
        _run_classify(
            db_path,
            use_llm=args.llm,
            use_vision=args.vision,
            truncate=args.truncate,
            since=args.since,
            limit=args.limit,
            three_source=args.three_source,
            classifier_v2=args.classifier_v2,
            force_reclassify=args.rerun,
        )
    elif args.command == "classify-review":
        db_path = detect_db_path(args.db)
        _run_classify_review(
            db_path,
            screen_id=args.screen,
            limit=args.limit,
            no_preview=args.no_preview,
        )
    elif args.command == "classify-review-index":
        db_path = detect_db_path(args.db)
        _run_classify_review_index(
            db_path,
            out=args.out,
            screen_id=args.screen,
            limit=args.limit,
            no_screenshots=args.no_screenshots,
        )
    elif args.command == "classify-audit":
        db_path = detect_db_path(args.db)
        _run_classify_audit(
            db_path,
            sample=args.sample,
            screen_id=args.screen,
            seed=args.seed,
            no_preview=args.no_preview,
        )
    elif args.command == "generate-ir":
        db_path = detect_db_path(args.db)
        _run_generate_ir(db_path, args.screen)
    elif args.command == "generate":
        db_path = detect_db_path(args.db)
        _run_generate(
            db_path, int(args.screen), dry_run=args.dry_run,
            canvas_x=args.canvas_x, canvas_y=args.canvas_y,
        )
    elif args.command == "extract-supplement":
        db_path = detect_db_path(args.db)
        _run_extract_supplement(db_path, args)
    elif args.command == "extract-plugin":
        db_path = detect_db_path(args.db)
        _run_extract_plugin(db_path, args)
    elif args.command == "generate-prompt":
        db_path = detect_db_path(args.db)
        _run_generate_prompt(db_path, args.prompt, out=args.out, page_name=args.page)
    elif args.command == "push":
        db_path = detect_db_path(args.db)
        _run_push(db_path, args)
    elif args.command == "verify":
        db_path = detect_db_path(args.db)
        _run_verify(db_path, args)
    elif args.command == "inspect-experiment":
        _run_inspect_experiment(args)
    elif args.command == "induce-variants":
        db_path = detect_db_path(args.db)
        _run_induce_variants(db_path, args)
    elif args.command == "design":
        db_path = detect_db_path(args.db)
        _run_design(db_path, args)


def _run_design(db_path: str, args) -> None:
    """`dd design` dispatch — handles --brief / resume / score.

    Per Codex+Sonnet 2026-04-23 unanimous picks: 3 subcommands
    minimum-viable. ``ls`` and ``show`` deferred to follow-up;
    use raw SQL on the design_sessions / variants tables.
    """
    from dd.db import get_connection

    sub = args.design_command

    if sub is None:
        # Top-level `dd design --brief "..."` form.
        if not args.brief:
            print(
                "dd design: pass --brief \"<text>\" to start a new "
                "session, or use a subcommand (resume / score). See "
                "`dd design --help`.",
                file=sys.stderr,
            )
            sys.exit(1)
        _run_design_brief(
            db_path,
            brief=args.brief,
            max_iters=args.max_iters,
            starting_screen=args.starting_screen,
            render_to_figma=args.render_to_figma,
            project_db=args.project_db,
            dump_scripts=args.dump_scripts,
        )
        return

    if sub == "resume":
        _run_design_resume(
            db_path,
            variant_id=args.variant_id,
            max_iters=args.max_iters,
            starting_screen=args.starting_screen,
            render_to_figma=args.render_to_figma,
            project_db=args.project_db,
            dump_scripts=args.dump_scripts,
        )
        return

    if sub == "score":
        _run_design_score(db_path, session_id=args.session_id)
        return


def _make_anthropic_client():
    """Construct an Anthropic client. Surface API-key errors as
    user-friendly exits, not stack traces."""
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception as e:  # noqa: BLE001
        print(
            f"dd design: failed to initialize Anthropic client: {e}\n"
            "Set ANTHROPIC_API_KEY in your environment or .env file.",
            file=sys.stderr,
        )
        sys.exit(1)


def _run_design_brief(
    db_path: str,
    *,
    brief: str,
    max_iters: int,
    starting_screen: int | None = None,
    render_to_figma: bool = False,
    project_db: str | None = None,
    dump_scripts: str | None = None,
) -> None:
    """M1 of the authoring-loop Figma round-trip (docs/rationale/
    stage-3-session-loop.md + Codex sign-off 2026-04-24).

    Three modes:

    1. **SYNTHESIZE** (``--brief`` only): run the agent on the
       default empty starting doc, persist session, print summary.
    2. **Brief + starting-screen** (``--brief`` +
       ``--starting-screen``): load the starting doc from the project
       DB via generate_ir + compress_to_l3 round-trip, run the agent
       against it, persist session. Useful for testing without a
       live Figma bridge.
    3. **Full round-trip** (add ``--render-to-figma``): after the
       session halts, render the starting screen AND the final
       variant to a new Figma page keyed on the session ULID,
       side-by-side on one page. Requires ``--starting-screen``;
       rendering to Figma with no source material is an empty-canvas
       demo. Uses ``execute_script_via_bridge`` (M1.1) to ship each
       render over PROXY_EXECUTE.
    """
    from dd.agent.loop import run_session
    from dd.db import get_connection

    if not brief or not brief.strip():
        print("dd design: --brief must not be blank.", file=sys.stderr)
        sys.exit(1)

    # Flag-combination invariant (Codex's "ambiguous combinations"
    # risk): require --starting-screen alongside --render-to-figma.
    if render_to_figma and starting_screen is None:
        print(
            "dd design: --render-to-figma requires --starting-screen "
            "<ID>. Rendering with no source screen produces an "
            "empty-canvas demo.",
            file=sys.stderr,
        )
        sys.exit(1)

    starting_doc = None
    if starting_screen is not None:
        starting_doc = _load_starting_doc(
            project_db_path=project_db or db_path,
            screen_id=starting_screen,
        )

    # Auto-init the session DB schema. ``init_db`` is idempotent —
    # returns early if tables already exist — so the single-command
    # demo flow works against either a fresh path, an empty file,
    # or an existing session DB. Avoids the `no such table:
    # design_sessions` stumble on first run.
    from dd.db import init_db
    init_db(db_path).close()

    client = _make_anthropic_client()
    conn = get_connection(db_path)
    try:
        result = run_session(
            conn, brief=brief, client=client, max_iters=max_iters,
            starting_doc=starting_doc,
            progress_stream=sys.stderr,
        )
    except ValueError as e:
        print(f"dd design: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    page_hint = ""
    if render_to_figma:
        page_name = _render_session_to_figma(
            session_db_path=db_path,
            project_db_path=project_db or db_path,
            session_id=result.session_id,
            final_variant_id=result.final_variant_id,
            starting_screen_id=starting_screen,
            dump_scripts=Path(dump_scripts) if dump_scripts else None,
        )
        page_hint = (
            f"\n  → rendered to Figma page '{page_name}' "
            f"(original at x=0, variant offset right)"
        )

    print(result.session_id)
    print(
        f"  iterations: {result.iterations}  "
        f"halt: {result.halt_reason}  "
        f"final_variant: {result.final_variant_id}"
        f"{page_hint}"
    )


def _load_starting_doc(*, project_db_path: str, screen_id: int):
    """Load and round-trip an L3 starting doc from a project DB screen.

    Mirrors the capstone-test recipe (tests/test_stage3_acceptance.py):
    generate_ir → compress_to_l3 → emit_l3 + parse_l3 round-trip so the
    returned doc is the same shape the agent loop will produce after
    each iter. Surfaces a clear `screen {id} not found` error if the
    project DB doesn't have the screen — better than reaching the
    Anthropic client and burning an API call on a doomed session.
    """
    from dd.compress_l3 import compress_to_l3_with_maps
    from dd.db import get_connection
    from dd.ir import generate_ir
    from dd.markup_l3 import emit_l3, parse_l3

    conn = get_connection(project_db_path)
    try:
        row = conn.execute(
            "SELECT id FROM screens WHERE id=?", (screen_id,),
        ).fetchone()
        if row is None:
            print(
                f"dd design: screen {screen_id} not found in "
                f"{project_db_path}. Pass --project-db to point at "
                "a classified project DB.",
                file=sys.stderr,
            )
            sys.exit(1)
        ir_result = generate_ir(conn, screen_id)
        # CRITICAL: ``collapse_wrapper=False`` must match the value
        # used by the canonical render path (``generate_screen`` →
        # ``_compress_to_l3_impl`` at dd/renderers/figma.py:2554).
        # The public ``compress_to_l3`` defaults to collapse_wrapper=True
        # (a grammar- and round-trip-test shape); using that shape
        # produces an L3 doc whose eid-chain paths DIFFER from the
        # renderer's original_doc, so every entry in
        # ``rebuild_maps_after_edits``'s nid_map misses and the final
        # variant falls to Mode-2 cheap-emission (an almost-empty
        # frame) even though the agent's edits were minimal. Root
        # cause of the M1 live-capstone "variant is blank" regression
        # — diagnosed 2026-04-24 by a subagent-driven path-coverage
        # experiment (0/109 at True, 109/109 at False against the
        # same applied doc).
        doc, *_ = compress_to_l3_with_maps(
            ir_result["spec"], conn=conn, screen_id=screen_id,
            collapse_wrapper=False,
        )
        # Round-trip through emit/parse so the agent sees the exact
        # shape `apply_edits` would produce, not the compressor's
        # internal object identity. Prevents id(Node)-keyed maps from
        # mis-aligning on the first turn.
        return parse_l3(emit_l3(doc))
    finally:
        conn.close()


def _render_session_to_figma(
    *,
    session_db_path: str,
    project_db_path: str,
    session_id: str,
    final_variant_id: str,
    starting_screen_id: int,
    dump_scripts: Path | None = None,
) -> str:
    """Render the starting screen + the session's final variant to
    a new Figma page via the plugin bridge. Returns the page name.

    Two bridge calls (not one concatenated script): the page_name
    find-or-create preamble in render_figma_ast makes the second call
    idempotent on the same page. Two calls also let a mid-pipeline
    failure land visibly (original rendered, variant failed) rather
    than atomic-nothing — better for a demo where the user can
    diagnose by looking at the canvas.

    Page-name + canvas-position split:
      - Original render:  page_name="design session <SID8> / <VID12>",
                          canvas_position=(0, 0).
      - Variant render:   same page_name,
                          canvas_position=(screen_width + 200, 0).

    The variant-ULID suffix is the M2 page-collision fix: within a
    single session, successive resumes produce different final
    variants; keying the page name on BOTH the session AND the new
    leaf variant means each resume lands on its own page rather than
    stacking on top of a previous render. The shared session prefix
    keeps the iteration history visible in Figma's sidebar (all
    "design session 01ABCD / …" pages cluster alphabetically).
    The variant prefix is 12 chars (not 8) so it spans into the ULID
    random region; 10 chars is the time prefix only and two variants
    created in the same millisecond share that whole window.
    Resuming a session within the same millisecond as another
    resume is unlikely but happens in tests.

    ``dump_scripts``: if set, additionally write the generated JS to
    ``<dir>/original.js`` and ``<dir>/variant.js`` BEFORE shipping to
    the bridge. Diagnostic side-channel — bridge I/O is unchanged, so
    the dump survives even when the bridge rejects the variant script
    (at which point the on-disk file is the only thing left to
    inspect).
    """
    from dd.apply_render import (
        BridgeError, DegradedMapping, execute_script_via_bridge,
        render_applied_doc,
    )
    from dd.compress_l3 import _compress_to_l3_impl
    from dd.db import get_connection
    from dd.ir import generate_ir, query_screen_visuals
    from dd.renderers.figma import collect_fonts, generate_screen
    from dd.sessions import iter_edits_on_path, load_variant

    # ``session_id[:8]`` is the time prefix only — fine for grouping,
    # since the resume-loop creates new variants UNDER the same
    # session row. ``final_variant_id[:12]`` extends into the random
    # region so resumes that fire within the same millisecond still
    # land on distinct pages (10-char ULID time prefix + 2 chars of
    # the random suffix).
    page_name = (
        f"design session {session_id[:8]} / {final_variant_id[:12]}"
    )

    # --- Original render -------------------------------------------
    project_conn = get_connection(project_db_path)
    try:
        screen_row = project_conn.execute(
            "SELECT width FROM screens WHERE id=?", (starting_screen_id,),
        ).fetchone()
        screen_width = float(screen_row["width"] or 428.0) if screen_row else 428.0

        original_result = generate_screen(
            project_conn, starting_screen_id,
            canvas_position=(0.0, 0.0),
            page_name=page_name,
        )
        original_script = original_result["structure_script"]
        if dump_scripts is not None:
            dump_scripts.mkdir(parents=True, exist_ok=True)
            (dump_scripts / "original.js").write_text(original_script)
    finally:
        project_conn.close()

    # --- Variant render --------------------------------------------
    session_conn = get_connection(session_db_path)
    project_conn = get_connection(project_db_path)
    try:
        final_variant = load_variant(session_conn, final_variant_id)
        if final_variant is None:
            print(
                f"dd design: final variant {final_variant_id!r} not "
                "found — session persistence is inconsistent.",
                file=sys.stderr,
            )
            sys.exit(1)

        cumulative_edits = iter_edits_on_path(
            session_conn, final_variant_id,
        )

        # Rebuild the original-screen render-side state. The renderer's
        # maps are keyed on the original AST + the full edit list (via
        # rebuild_maps_after_edits); this is the same shape
        # generate_screen builds internally.
        ir_result = generate_ir(project_conn, starting_screen_id)
        spec = ir_result["spec"]
        visuals = query_screen_visuals(project_conn, starting_screen_id)
        ckr_exists = project_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='component_key_registry'"
        ).fetchone()
        if ckr_exists:
            ckr_row = project_conn.execute(
                "SELECT COUNT(*) FROM component_key_registry"
            ).fetchone()
            ckr_built = bool(ckr_row and ckr_row[0] > 0)
        else:
            ckr_built = False

        (
            original_doc, _eid_nid, nid_map, spec_key_map,
            original_name_map, _descendant_resolver,
        ) = _compress_to_l3_impl(
            spec, project_conn, screen_id=starting_screen_id,
            collapse_wrapper=False,
        )
        fonts = collect_fonts(spec, db_visuals=visuals)

        # ``strict_mapping=0.9`` — Codex's A' invariant (sign-off
        # 2026-04-24): if nid_map coverage drops below 90% of
        # eligible applied-doc nodes, raise DegradedMapping instead
        # of silently producing a Mode-2 empty frame. Originally
        # hit as the M1 "variant renders blank" bug
        # (wrapper-collapse mismatch between the agent's
        # starting-doc compression and the renderer's original-doc
        # compression). A future regression of the same class
        # surfaces as a user-visible BridgeError-like failure.
        try:
            variant_rendered = render_applied_doc(
                applied_doc=final_variant.doc,
                original_doc=original_doc,
                edits=cumulative_edits,
                spec=spec,
                conn=project_conn,
                db_visuals=visuals,
                fonts=fonts,
                old_nid_map=nid_map,
                old_spec_key_map=spec_key_map,
                old_original_name_map=original_name_map,
                ckr_built=ckr_built,
                page_name=page_name,
                canvas_position=(screen_width + 200.0, 0.0),
                strict_mapping=0.9,
            )
        except DegradedMapping as e:
            print(
                f"dd design: variant render would be degraded — {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        variant_script = variant_rendered.script
        if dump_scripts is not None:
            dump_scripts.mkdir(parents=True, exist_ok=True)
            (dump_scripts / "variant.js").write_text(variant_script)
    finally:
        session_conn.close()
        project_conn.close()

    # --- Bridge I/O ------------------------------------------------
    # Two PROXY_EXECUTE calls. Any BridgeError reaches the user via
    # sys.stderr + non-zero exit — we do NOT silently skip the variant
    # render if the original succeeded (the user wants both; half is
    # a bug, not a feature).
    try:
        from dd import apply_render as _ap
        _ap.execute_script_via_bridge(script=original_script)
        _ap.execute_script_via_bridge(script=variant_script)
    except BridgeError as e:
        print(
            f"dd design: render-to-figma bridge call failed: {e}\n"
            "Is the Figma plugin listening on port 9228?",
            file=sys.stderr,
        )
        sys.exit(1)

    return page_name


def _run_design_resume(
    db_path: str,
    *,
    variant_id: str,
    max_iters: int,
    starting_screen: int | None = None,
    render_to_figma: bool = False,
    project_db: str | None = None,
    dump_scripts: str | None = None,
) -> None:
    """M2 demo-blocker: resume must support the same Figma round-trip
    flag family as --brief so the multi-turn iteration story lands.

    Mirrors `_run_design_brief`'s post-session render path. Each
    resume produces a new leaf variant; ``_render_session_to_figma``
    keys the Figma page on BOTH the session prefix and the new
    variant prefix, so successive resumes land on different pages
    and the user can see the iteration history in the sidebar.
    """
    from dd.agent.loop import run_session
    from dd.db import get_connection, init_db

    # Same flag-combination invariant as --brief: rendering to Figma
    # with no starting screen produces an empty-canvas render that's
    # confusing for the user. Fail loudly.
    if render_to_figma and starting_screen is None:
        print(
            "dd design: --render-to-figma requires --starting-screen "
            "<ID>. Rendering with no source screen produces an "
            "empty-canvas demo.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Same auto-init contract as --brief. Idempotent on populated DBs.
    init_db(db_path).close()

    client = _make_anthropic_client()
    conn = get_connection(db_path)
    try:
        result = run_session(
            conn, parent_variant_id=variant_id,
            client=client, max_iters=max_iters,
            progress_stream=sys.stderr,
        )
    except ValueError as e:
        print(f"dd design: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    page_hint = ""
    if render_to_figma:
        page_name = _render_session_to_figma(
            session_db_path=db_path,
            project_db_path=project_db or db_path,
            session_id=result.session_id,
            final_variant_id=result.final_variant_id,
            starting_screen_id=starting_screen,
            dump_scripts=Path(dump_scripts) if dump_scripts else None,
        )
        page_hint = (
            f"\n  → rendered to Figma page '{page_name}' "
            f"(original at x=0, variant offset right)"
        )

    print(result.session_id)
    print(
        f"  iterations: {result.iterations}  "
        f"halt: {result.halt_reason}  "
        f"final_variant: {result.final_variant_id}"
        f"{page_hint}"
    )


def _run_design_score(db_path: str, *, session_id: str) -> None:
    """Stage 3 ships this as a stub that confirms the session
    exists and prints a "not yet implemented" line. The wiring is
    the user-facing surface; the deep render+VLM scoring lands in
    a follow-up (per Codex+Sonnet's A2 pick: deferred scoring).
    """
    from dd.db import get_connection
    from dd.sessions import list_sessions, list_variants

    conn = get_connection(db_path)
    try:
        sessions = list_sessions(conn)
        if session_id not in {s.id for s in sessions}:
            print(
                f"dd design: session {session_id!r} not found.",
                file=sys.stderr,
            )
            sys.exit(1)
        variants = list_variants(conn, session_id)
        print(
            f"dd design score: session {session_id} has "
            f"{len(variants)} variant(s)."
        )
        print(
            "  (deferred: render + fidelity scoring not yet "
            "wired into this subcommand. The session + variants + "
            "move log are persisted; rerun once the score backend "
            "lands.)"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
