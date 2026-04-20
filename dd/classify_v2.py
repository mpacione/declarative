"""Classifier v2 orchestrator — corpus-wide dedup + per-node crops.

Three changes from v1:
1. Candidates are pooled across all screens, then deduped by
   structural signature. One representative per group gets
   classified; the verdict propagates to every sci row in the
   group. Expected 5-8x cost reduction.
2. Full-screen canvas nodes are filtered at the SQL layer (see
   `dd.classify_llm._get_unclassified_for_llm` + `dd.classify_
   vision_batched._fetch_unclassified_for_screen`).
3. Vision passes use per-node spotlight crops instead of full
   screens + bbox lists. Each crop shows the target at full
   brightness with its bbox outlined in magenta; surroundings are
   dimmed. Vision model doesn't do visual attention-mapping —
   classification target is unambiguous.

The 3-source architecture is preserved: LLM (text-only, reps only)
+ Vision PS (single-crop per group rep) + Vision CS (multi-crop
across screens for groups with ≥2 members; singletons inherit PS).
Consensus runs per-screen at the end via `apply_consensus_to_screen`.

Entry point: `run_classification_v2`. See `docs/plan-classifier-v2.md`
for the full spec + rationale.
"""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

from dd.catalog import get_catalog
from dd.classify import (
    apply_consensus_to_screen,
    classify_formal,
    link_parent_instances,
)
from dd.classify_dedup import dedup_key, group_candidates
from dd.classify_few_shot import (
    format_few_shot_block,
    retrieve_few_shot,
)
from dd.classify_heuristics import classify_heuristics
from dd.classify_llm import (
    CLASSIFY_TOOL_SCHEMA,
    _extract_classifications_from_response,
    _get_unclassified_for_llm,
    build_classification_prompt,
)
from dd.classify_rules import is_system_chrome
from dd.classify_skeleton import extract_skeleton
from dd.classify_vision_batched import (
    CLASSIFY_CROPS_TOOL_SCHEMA,
    classify_crops_batch,
)
from dd.classify_vision_crop import crop_node_with_spotlight


_LLM_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_CONFIDENCE = 0.7


def _list_screens(
    conn: sqlite3.Connection,
    file_id: int,
    since_screen_id: Optional[int],
    limit: Optional[int],
) -> list[int]:
    query = (
        "SELECT id FROM screens WHERE file_id = ? "
        "AND (device_class IS NULL OR device_class != 'component_sheet')"
    )
    params: list[Any] = [file_id]
    if since_screen_id is not None:
        query += " AND id >= ?"
        params.append(since_screen_id)
    query += " ORDER BY id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return [r[0] for r in conn.execute(query, params).fetchall()]


def _collect_all_candidates(
    conn: sqlite3.Connection,
    screen_ids: list[int],
) -> list[dict[str, Any]]:
    """Pool unclassified candidates across every screen. Reuses
    `_get_unclassified_for_llm` per screen (already applies the
    full-screen + system-chrome filters).

    Enriches each candidate with screen-level context so downstream
    prompt builders (classify_llm._describe_node) can compute
    geometric features (aspect ratio, position on screen,
    size-relative-to-viewport). v2.1 Phase C.
    """
    # Fetch screen metadata once per screen.
    pooled: list[dict[str, Any]] = []
    for sid in screen_ids:
        screen_row = conn.execute(
            "SELECT name, width, height, device_class "
            "FROM screens WHERE id = ?",
            (sid,),
        ).fetchone()
        sw, sh = 0.0, 0.0
        device_class = None
        if screen_row:
            sw = float(screen_row[1] or 0)
            sh = float(screen_row[2] or 0)
            device_class = screen_row[3]
        cands = _get_unclassified_for_llm(conn, sid)
        for c in cands:
            c["screen_id"] = sid
            c["screen_width"] = sw
            c["screen_height"] = sh
            if device_class:
                c["device_class"] = device_class
            pooled.append(c)
    return pooled


def _llm_classify_representatives(
    reps: list[dict[str, Any]],
    client: Any,
    catalog: list[dict[str, Any]],
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[int, tuple[str, float, Optional[str]]]:
    """Classify all group representatives in one LLM call.

    When `conn` is provided, retrieves up to 3 few-shot examples per
    representative from the user's review history and prepends them
    to the prompt. Uniform example set across all reps in the batch;
    if reps span multiple parent types, we pool examples from each.

    Returns a `{node_id: (canonical_type, confidence, reason)}` map.
    """
    if not reps:
        return {}
    few_shot_block = ""
    if conn is not None:
        # Collect ≤3 examples PER distinct parent context across reps.
        seen_parents: set[str] = set()
        pooled: list[dict[str, Any]] = []
        for rep in reps:
            parent = rep.get("parent_classified_as") or ""
            if parent in seen_parents:
                continue
            seen_parents.add(parent)
            pooled.extend(retrieve_few_shot(conn, rep, k=2))
            if len(pooled) >= 6:
                break
        # Dedup pooled examples on sci_id.
        seen_ids = set()
        unique_pool: list[dict[str, Any]] = []
        for e in pooled:
            sid = e.get("sci_id")
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            unique_pool.append(e)
        few_shot_block = format_few_shot_block(unique_pool[:6])

    # v1's prompt builder + few-shot prepended.
    base_prompt = build_classification_prompt(
        nodes=reps,
        catalog=catalog,
        screen_name="(global representatives batch)",
        screen_width=0, screen_height=0,
        skeleton_notation=None, skeleton_type=None,
    )
    prompt = (few_shot_block + "\n" + base_prompt) if few_shot_block else base_prompt

    response = client.messages.create(
        model=_LLM_MODEL,
        max_tokens=8192,
        tools=[CLASSIFY_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": CLASSIFY_TOOL_SCHEMA["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    classifications = _extract_classifications_from_response(response)
    out: dict[int, tuple[str, float, Optional[str]]] = {}
    for c in classifications:
        nid = c.get("node_id")
        ctype = c.get("canonical_type")
        conf = c.get("confidence", _DEFAULT_CONFIDENCE)
        reason = c.get("reason")
        if isinstance(nid, int) and isinstance(ctype, str):
            out[nid] = (
                ctype, float(conf),
                reason if isinstance(reason, str) else None,
            )
    return out


def _insert_llm_verdicts(
    conn: sqlite3.Connection,
    groups: list[list[dict[str, Any]]],
    reps: list[dict[str, Any]],
    verdicts_by_node_id: dict[int, tuple[str, float, Optional[str]]],
    catalog: list[dict[str, Any]],
) -> int:
    """Propagate the representative's LLM verdict to every member
    of its group. INSERTs one sci row per member.
    """
    catalog_id_lookup = {e["canonical_name"]: e["id"] for e in catalog}
    inserts: list[tuple[Any, ...]] = []
    for members, rep in zip(groups, reps):
        verdict = verdicts_by_node_id.get(rep["node_id"])
        if verdict is None:
            continue
        ctype, conf, reason = verdict
        if ctype in ("container", "unsure"):
            catalog_id = None
        else:
            catalog_id = catalog_id_lookup.get(ctype)
            if catalog_id is None:
                # Model invented a type not in the catalog — skip.
                continue
        for m in members:
            inserts.append((
                m["screen_id"], m["node_id"], catalog_id, ctype,
                conf, "llm", reason, ctype, conf,
            ))
    if inserts:
        conn.executemany(
            "INSERT OR IGNORE INTO screen_component_instances "
            "(screen_id, node_id, catalog_type_id, canonical_type, "
            " confidence, classification_source, llm_reason, "
            " llm_type, llm_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            inserts,
        )
        conn.commit()
    return len(inserts)


def _fetch_screenshots_for_screens(
    conn: sqlite3.Connection,
    screen_ids: list[int],
    fetch_screenshot: Callable,
    file_key: str,
) -> dict[str, bytes]:
    """One REST call per screen (or a batched call where the fetcher
    supports it). Returns `{screen_figma_id: png_bytes}`.
    """
    rows = conn.execute(
        "SELECT id, figma_node_id FROM screens "
        "WHERE id IN (%s)" % ",".join("?" * len(screen_ids)),
        screen_ids,
    ).fetchall()
    figma_ids = [fid for _, fid in rows if fid]
    screenshots: dict[str, bytes] = {}
    try:
        result = fetch_screenshot(file_key, figma_ids)
        if isinstance(result, dict):
            screenshots = result
    except TypeError:
        pass
    # Fallback: per-node fetch for anything missing.
    for fid in figma_ids:
        if fid not in screenshots:
            data = fetch_screenshot(file_key, fid)
            if data is not None:
                screenshots[fid] = data
    return screenshots


def _screen_root_offset(
    conn: sqlite3.Connection, screen_id: int,
) -> tuple[float, float]:
    """Subtract the screen root's (x, y) from node absolute canvas
    coords to get screen-relative coords for cropping.
    """
    row = conn.execute(
        "SELECT COALESCE(x, 0), COALESCE(y, 0) FROM nodes "
        "WHERE screen_id = ? AND parent_id IS NULL LIMIT 1",
        (screen_id,),
    ).fetchone()
    if row is None:
        return (0.0, 0.0)
    return (float(row[0]), float(row[1]))


def _screen_figma_id(
    conn: sqlite3.Connection, screen_id: int,
) -> Optional[str]:
    row = conn.execute(
        "SELECT figma_node_id FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    return row[0] if row else None


def _build_crop(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    screenshots: dict[str, bytes],
) -> Optional[bytes]:
    """Spotlight-crop a single candidate's node region from its
    screen screenshot. Returns None if we don't have the screen's
    PNG or if the bbox is degenerate.
    """
    fig_id = _screen_figma_id(conn, candidate["screen_id"])
    if fig_id is None:
        return None
    screen_png = screenshots.get(fig_id)
    if screen_png is None:
        return None
    rx, ry = _screen_root_offset(conn, candidate["screen_id"])
    screen_dims = conn.execute(
        "SELECT width, height FROM screens WHERE id = ?",
        (candidate["screen_id"],),
    ).fetchone()
    if screen_dims is None:
        return None
    sw = float(screen_dims[0] or 0)
    sh = float(screen_dims[1] or 0)
    try:
        return crop_node_with_spotlight(
            screen_png=screen_png,
            node_x=float(candidate.get("x") or 0) - rx,
            node_y=float(candidate.get("y") or 0) - ry,
            node_width=float(candidate.get("width") or 0),
            node_height=float(candidate.get("height") or 0),
            screen_width=sw, screen_height=sh,
        )
    except Exception:
        return None


_LOW_CONFIDENCE_THRESHOLD = 0.70
_DEFAULT_WORKERS = 4
_RETRY_BACKOFF_S = 10.0


def _classify_crops_with_retry(
    batch: list[dict[str, Any]],
    crops: dict[tuple[int, int], bytes],
    client: Any,
    catalog: list[dict[str, Any]],
    *,
    retry_mode: bool = False,
    max_attempts: int = 3,
) -> list[dict[str, Any]]:
    """Call classify_crops_batch with retry/backoff on transient
    errors (Anthropic 429 / 529 / SSL hiccups). Returns [] on
    final failure rather than propagating the exception so one bad
    batch doesn't abort the whole parallel run.
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            return classify_crops_batch(
                batch, crops, client,
                catalog=catalog, retry_mode=retry_mode,
            )
        except Exception:
            attempt += 1
            if attempt >= max_attempts:
                return []
            time.sleep(_RETRY_BACKOFF_S * attempt)
    return []


def _vision_ps_classify(
    conn: sqlite3.Connection,
    reps: list[dict[str, Any]],
    screenshots: dict[str, bytes],
    client: Any,
    catalog: list[dict[str, Any]],
    *,
    workers: int = _DEFAULT_WORKERS,
) -> dict[tuple[int, int], tuple[str, float, Optional[str]]]:
    """Vision PS pass: one crop per group representative. Batches
    multiple reps into a single classify_crops_batch call (up to
    ~8 per batch for token budget reasons).

    Phase E: after the first pass, any row with confidence < 0.7
    or canonical_type == 'unsure' goes through a retry pass with
    CoT-framed prompting. If the retry returns higher confidence,
    we use its verdict; otherwise we keep the first pass's.
    """
    if not reps:
        return {}
    results: dict[tuple[int, int], tuple[str, float, Optional[str]]] = {}
    batch_size = 8

    # Pre-compute every rep's crop on the main thread. SQLite
    # connections can't cross threads, so all DB reads must happen
    # before the ThreadPoolExecutor dispatches.
    rep_crops: dict[tuple[int, int], bytes] = {}
    for rep in reps:
        crop = _build_crop(conn, rep, screenshots)
        if crop is not None:
            rep_crops[(rep["screen_id"], rep["node_id"])] = crop

    def _apply_classifications(
        classifications: list[dict[str, Any]],
        target: dict[tuple[int, int], tuple[str, float, Optional[str]]],
    ) -> None:
        for c in classifications:
            sid = c.get("screen_id")
            nid = c.get("node_id")
            ctype = c.get("canonical_type")
            conf = c.get("confidence", _DEFAULT_CONFIDENCE)
            reason = c.get("reason")
            if not (
                isinstance(sid, int) and isinstance(nid, int)
                and isinstance(ctype, str)
            ):
                continue
            target[(sid, nid)] = (
                ctype, float(conf),
                reason if isinstance(reason, str) else None,
            )

    def _build_and_classify(
        batch: list[dict[str, Any]], *, retry_mode: bool = False,
    ) -> list[dict[str, Any]]:
        crops: dict[tuple[int, int], bytes] = {}
        for rep in batch:
            key = (rep["screen_id"], rep["node_id"])
            pre = rep_crops.get(key)
            if pre is not None:
                crops[key] = pre
        if not crops:
            return []
        return _classify_crops_with_retry(
            batch, crops, client, catalog, retry_mode=retry_mode,
        )

    # Initial pass — parallelize batches across a thread pool.
    # Anthropic's SDK is thread-safe; one client is shared.
    batches = [
        reps[i:i + batch_size] for i in range(0, len(reps), batch_size)
    ]
    if workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_build_and_classify, b)
                for b in batches
            ]
            for fut in as_completed(futures):
                _apply_classifications(fut.result(), results)
    else:
        for b in batches:
            _apply_classifications(_build_and_classify(b), results)

    # Phase E — rejection sampling. Find reps whose first verdict
    # was low-confidence or unsure; re-classify with CoT prompt.
    retry_reps: list[dict[str, Any]] = []
    for rep in reps:
        key = (rep["screen_id"], rep["node_id"])
        verdict = results.get(key)
        if verdict is None:
            continue
        ctype, conf, _reason = verdict
        if ctype == "unsure" or conf < _LOW_CONFIDENCE_THRESHOLD:
            retry_reps.append(rep)
    if retry_reps:
        retry_results: dict[
            tuple[int, int], tuple[str, float, Optional[str]]
        ] = {}
        retry_batches = [
            retry_reps[i:i + batch_size]
            for i in range(0, len(retry_reps), batch_size)
        ]
        if workers > 1 and len(retry_batches) > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        _build_and_classify, b, retry_mode=True,
                    )
                    for b in retry_batches
                ]
                for fut in as_completed(futures):
                    _apply_classifications(
                        fut.result(), retry_results,
                    )
        else:
            for b in retry_batches:
                _apply_classifications(
                    _build_and_classify(b, retry_mode=True),
                    retry_results,
                )
        # Merge retry verdicts: keep the higher-confidence one or
        # promote a non-unsure retry over an initial `unsure`.
        for key, retry_verdict in retry_results.items():
            r_ctype, r_conf, r_reason = retry_verdict
            existing = results.get(key)
            first_conf = existing[1] if existing else 0.0
            first_type = existing[0] if existing else None
            use_retry = (
                r_conf > first_conf
                or (first_type == "unsure" and r_ctype != "unsure")
            )
            if use_retry:
                results[key] = retry_verdict
    return results


def _vision_cs_classify(
    conn: sqlite3.Connection,
    groups: list[list[dict[str, Any]]],
    reps: list[dict[str, Any]],
    screenshots: dict[str, bytes],
    client: Any,
    catalog: list[dict[str, Any]],
    *,
    workers: int = _DEFAULT_WORKERS,
) -> dict[tuple[int, int], tuple[str, float, Optional[str]]]:
    """Vision CS pass: for each group with ≥2 members, classify the
    representative using crops of ALL members (or up to 5) as
    multi-image context — the cross-screen visual-consistency signal.
    Singletons are skipped (CS == PS for a group of 1; PS already ran).

    Groups are processed in parallel via ThreadPoolExecutor — each
    group is one independent API call. Anthropic SDK is thread-safe.
    """
    # Only groups with ≥2 members do CS; singletons inherit PS.
    multi_groups = [
        (members, rep)
        for members, rep in zip(groups, reps)
        if len(members) >= 2
    ]

    # Pre-compute crops for every sampled member on the main thread.
    # Worker threads can't touch the sqlite connection.
    member_crops: dict[tuple[int, int], bytes] = {}
    for members, _rep in multi_groups:
        for m in members[:5]:
            key = (m["screen_id"], m["node_id"])
            if key in member_crops:
                continue
            crop = _build_crop(conn, m, screenshots)
            if crop is not None:
                member_crops[key] = crop

    def _classify_group(
        members: list[dict[str, Any]], rep: dict[str, Any],
    ) -> Optional[tuple[tuple[int, int], tuple[str, float, Optional[str]]]]:
        sample = members[:5]
        crops: dict[tuple[int, int], bytes] = {}
        for m in sample:
            key = (m["screen_id"], m["node_id"])
            pre = member_crops.get(key)
            if pre is not None:
                crops[key] = pre
        if not crops:
            return None
        classifications = _classify_crops_with_retry(
            sample, crops, client, catalog,
        )
        for c in classifications:
            sid = c.get("screen_id")
            nid = c.get("node_id")
            if sid == rep["screen_id"] and nid == rep["node_id"]:
                ctype = c.get("canonical_type")
                conf = c.get("confidence", _DEFAULT_CONFIDENCE)
                reason = c.get("reason")
                if isinstance(ctype, str):
                    return (
                        (sid, nid),
                        (
                            ctype, float(conf),
                            reason if isinstance(reason, str) else None,
                        ),
                    )
                break
        return None

    results: dict[tuple[int, int], tuple[str, float, Optional[str]]] = {}
    if workers > 1 and len(multi_groups) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_classify_group, members, rep)
                for members, rep in multi_groups
            ]
            for fut in as_completed(futures):
                out = fut.result()
                if out is not None:
                    key, verdict = out
                    results[key] = verdict
    else:
        for members, rep in multi_groups:
            out = _classify_group(members, rep)
            if out is not None:
                key, verdict = out
                results[key] = verdict
    return results


def _propagate_vision_to_members(
    conn: sqlite3.Connection,
    groups: list[list[dict[str, Any]]],
    reps: list[dict[str, Any]],
    ps: dict[tuple[int, int], tuple[str, float, Optional[str]]],
    cs: dict[tuple[int, int], tuple[str, float, Optional[str]]],
) -> tuple[int, int]:
    """Write vision_ps_* + vision_cs_* columns for every member of
    every group where the representative got a verdict. Singletons
    inherit PS for CS.
    """
    ps_applied = 0
    cs_applied = 0
    for members, rep in zip(groups, reps):
        rep_key = (rep["screen_id"], rep["node_id"])
        ps_verdict = ps.get(rep_key)
        cs_verdict = cs.get(rep_key)
        # Singletons: CS has no meaningful distinct verdict. Inherit PS.
        if cs_verdict is None and ps_verdict is not None:
            cs_verdict = ps_verdict

        for m in members:
            if ps_verdict is not None:
                ctype, conf, reason = ps_verdict
                conn.execute(
                    "UPDATE screen_component_instances "
                    "SET vision_ps_type = ?, vision_ps_confidence = ?, "
                    "    vision_ps_reason = ? "
                    "WHERE screen_id = ? AND node_id = ?",
                    (ctype, conf, reason, m["screen_id"], m["node_id"]),
                )
                ps_applied += 1
            if cs_verdict is not None:
                ctype, conf, reason = cs_verdict
                conn.execute(
                    "UPDATE screen_component_instances "
                    "SET vision_cs_type = ?, vision_cs_confidence = ?, "
                    "    vision_cs_reason = ? "
                    "WHERE screen_id = ? AND node_id = ?",
                    (ctype, conf, reason, m["screen_id"], m["node_id"]),
                )
                cs_applied += 1
    conn.commit()
    return (ps_applied, cs_applied)


def run_classification_v2(
    conn: sqlite3.Connection,
    file_id: int,
    client: Any,
    file_key: str,
    fetch_screenshot: Callable,
    *,
    since_screen_id: Optional[int] = None,
    limit: Optional[int] = None,
    progress_callback: Any = None,
    workers: int = _DEFAULT_WORKERS,
) -> dict[str, Any]:
    """Orchestrate the full v2 cascade.

    Flow:
    1. Per-screen formal + heuristic + link_parents (fast, no API).
    2. Pool unclassified candidates globally across all screens.
    3. Dedup into groups via `classify_dedup.group_candidates`.
    4. LLM: classify group representatives in a single batched call.
    5. Propagate LLM verdicts → INSERT sci rows for every member.
    6. Fetch screen screenshots for the corpus (batched).
    7. Vision PS: one crop per rep, batched ~8 at a time.
    8. Vision CS: multi-crop per group (>=2 members) for cross-screen
       consistency signal.
    9. Propagate vision verdicts to all group members.
    10. Per-screen apply_consensus_to_screen + extract_skeleton.

    Returns a summary dict with counts at each stage.
    """
    screen_ids = _list_screens(conn, file_id, since_screen_id, limit)

    # Pass 1: per-screen rule-based stages.
    for sid in screen_ids:
        classify_formal(conn, sid)
        classify_heuristics(conn, sid)
        link_parent_instances(conn, sid)

    # Pass 2: collect candidates globally.
    candidates = _collect_all_candidates(conn, screen_ids)

    # Pass 3: dedup.
    groups_map = group_candidates(candidates)
    groups_list = list(groups_map.values())
    reps = [members[0] for members in groups_list]

    catalog = get_catalog(conn)

    # Pass 4: LLM on representatives. Passes the DB connection so
    # few-shot retrieval pulls from classification_reviews.
    llm_verdicts = _llm_classify_representatives(
        reps, client, catalog, conn=conn,
    )

    # Pass 5: propagate LLM verdicts → INSERT sci rows.
    llm_inserts = _insert_llm_verdicts(
        conn, groups_list, reps, llm_verdicts, catalog,
    )

    # Re-link parent chains now that new sci rows exist.
    for sid in screen_ids:
        link_parent_instances(conn, sid)

    # Pass 6: fetch screenshots for every screen containing any
    # candidate. Caller's `fetch_screenshot` determines pixel scale
    # (production uses scale=2 via `make_figma_screenshot_fetcher(
    # scale=2)`; tests pass a mock).
    screens_with_reps = sorted({r["screen_id"] for r in reps})
    screenshots: dict[str, bytes] = {}
    if screens_with_reps:
        screenshots = _fetch_screenshots_for_screens(
            conn, screens_with_reps, fetch_screenshot, file_key,
        )

    # Pass 7 + 8: vision PS + CS. Parallelized across workers.
    ps_verdicts = _vision_ps_classify(
        conn, reps, screenshots, client, catalog,
        workers=workers,
    )
    cs_verdicts = _vision_cs_classify(
        conn, groups_list, reps, screenshots, client, catalog,
        workers=workers,
    )

    # Pass 9: propagate vision verdicts.
    ps_applied, cs_applied = _propagate_vision_to_members(
        conn, groups_list, reps, ps_verdicts, cs_verdicts,
    )

    # Pass 10: consensus + skeleton per screen.
    consensus_counts: dict[str, int] = {}
    skeletons_generated = 0
    for sid in screen_ids:
        counts = apply_consensus_to_screen(conn, sid)
        for k, v in counts.items():
            consensus_counts[k] = consensus_counts.get(k, 0) + v
        skel = extract_skeleton(conn, sid)
        if skel is not None:
            skeletons_generated += 1
        if progress_callback is not None:
            progress_callback(sid, counts)

    return {
        "screens_processed": len(screen_ids),
        "dedup_candidates": len(candidates),
        "dedup_groups": len(groups_list),
        "llm_inserts": llm_inserts,
        "vision_ps_applied": ps_applied,
        "vision_cs_applied": cs_applied,
        "consensus": consensus_counts,
        "skeletons_generated": skeletons_generated,
    }
