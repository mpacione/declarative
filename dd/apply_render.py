"""Render-map maintenance across L3 edit statements (M7.2 closure).

``dd.markup_l3.apply_edits`` returns an L3 document with freshly-spliced
Python objects along the edit path. The Figma renderer's companion
maps — ``spec_key_map`` / ``nid_map`` / ``original_name_map`` — are
keyed on ``id(Node)`` and stop covering the new subtree the moment a
swap (or any verb that touches the tree) runs.

This module rebuilds those maps for an applied doc without forcing the
whole DB round-trip through ``dd.ir.generate_ir`` again. The design
principle is conservative: carry forward whatever the original
compressor produced for each matched node, and only fabricate new
entries for the specific nodes the edits replaced.

Scope for M7.2: the ``swap`` verb at comp-ref heads. Other verbs
(``set`` / ``delete`` / ``append`` / ``insert`` / ``move`` / ``replace``)
preserve or rearrange existing nodes; their rendering story is for a
later closure.

Also exposes ``adjust_spec_elements_for_edits`` — a companion that
shallow-copies the original ``spec["elements"]`` dict and updates the
per-eid entry for each swap target so the renderer's ``_spec_elements``
shim and the verifier see a consistent view of the mutated tree.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dd.markup_l3 import L3Document, Node, SwapStatement


class SwapUnresolvedInCKR(Exception):
    """Raised when a ``swap @X with=-> master/path`` references a
    master that isn't in the project's ``component_key_registry``.

    Surfacing this loudly is deliberate: the renderer would otherwise
    fall through to ``_missingComponentPlaceholder`` (a grey wireframe
    rectangle) and the verifier would report ``KIND_TYPE_SUBSTITUTION``
    a round-trip later. Catching the mismatch at rebuild time keeps the
    diagnostic close to the cause.
    """


@dataclass
class AppliedRenderMaps:
    """Result of :func:`rebuild_maps_after_edits`.

    ``nid_map`` / ``spec_key_map`` / ``original_name_map`` are keyed on
    ``id(Node)`` and cover every node in the applied doc that the
    renderer will touch. ``db_visuals_patch`` is a ``{nid: dict}``
    fragment the caller must ``.update()`` into the real ``db_visuals``
    before calling ``render_figma`` — it carries the swap target's
    CKR-resolved ``component_figma_id`` so Mode-1 ``createInstance``
    resolves the new master.
    """

    nid_map: dict[int, int]
    spec_key_map: dict[int, str]
    original_name_map: dict[int, str]
    db_visuals_patch: dict[int, dict[str, Any]] = field(default_factory=dict)


def _bfs_nodes(doc: L3Document) -> list[Node]:
    """Enumerate all ``Node`` instances in ``doc`` in BFS order (the
    same order the renderer walks). Matches ``dd.render_figma_ast._walk_ast``'s
    traversal shape on the AST; repeating the walk locally keeps this
    module independent of the renderer's internals."""
    out: list[Node] = []
    queue: list[Node] = list(doc.top_level)
    while queue:
        n = queue.pop(0)
        out.append(n)
        block = n.block
        if block is not None:
            for s in block.statements:
                if isinstance(s, Node):
                    queue.append(s)
    return out


def _index_by_path(doc: L3Document) -> dict[tuple, Node]:
    """Index every node in ``doc`` by its eid-chain path from the
    document root.

    Path shape: ``(root_eid, child_eid, grandchild_eid, ...)``

    Grammar §2.3.1 forbids duplicate eids WITHIN a parent block
    (raises ``KIND_DUPLICATE_EID`` at parse time), so (parent_path,
    eid) is unique within a parent. Cousin subtrees (different
    parents with children sharing an eid) get distinct path keys
    because their parent chain differs.

    Sibling indices are deliberately NOT part of the key: insert /
    move / delete shift sibling positions, but the eid stays stable.
    Matching by eid-chain survives all three mutations.

    Caveat: multiple top-level docs with the same root eid would
    collide. The current grammar has a single top-level screen per
    doc, so this isn't an issue.

    Known limits (see tier-A review a333523d, documented here so
    future sessions don't re-discover them):

    - **move** is modeled as atomic delete+insert in
      :func:`dd.markup_l3._apply_move`. When a node moves under a
      different parent, its old path is absent from the applied
      doc and its new path is absent from the original doc. The
      move target is indexed as "new node" and loses its DB nid
      (silent fidelity loss — renders via Mode-2 cheap-emit
      instead of its DB style). Old positional-BFS algorithm had
      the same behavior. Full fix: index by eid AND path, fall
      back to eid-match when path-match fails, detect it as a
      move and carry forward the DB nid from the original home.
      Deferred until Tier D/E needs it.

    - **swap-under-move** in the same edit sequence: the swap
      target's new-path has no original counterpart, so the swap
      handler's ``applied_node.head.eid in swapped_eids`` check
      never fires. Silently rendered as Mode-2 plain node. Rare
      in practice; flag for Tier D tests.

    - **empty eids**: two sibling nodes with empty head.eid would
      collide on the same path key. Grammar §2.3.1 forbids
      duplicates but whether it catches empty-eid pairs is
      parser-dependent. The walker below uses a stable index
      tiebreak (``(eid or f"__anon_{idx}")``) to avoid silent
      overwrite.
    """
    out: dict[tuple, Node] = {}

    def walk(nodes, prefix):
        for idx, n in enumerate(nodes):
            if not isinstance(n, Node):
                continue
            eid_key = n.head.eid or f"__anon_{idx}"
            key = prefix + (eid_key,)
            out[key] = n
            block = n.block
            if block is not None:
                walk(block.statements, key)

    walk(doc.top_level, ())
    return out


def _collect_swap_statements(
    edits: list[object],
) -> list[SwapStatement]:
    return [s for s in edits if isinstance(s, SwapStatement)]


def _lookup_master_in_ckr(
    conn: sqlite3.Connection, name: str,
) -> Optional[str]:
    """Return the ``figma_node_id`` for a CKR row whose ``name``
    column matches ``name`` exactly. ``None`` when not found — caller
    decides whether to raise :class:`SwapUnresolvedInCKR`."""
    row = conn.execute(
        "SELECT figma_node_id FROM component_key_registry WHERE name = ?",
        (name,),
    ).fetchone()
    if not row:
        return None
    return row[0]


def rebuild_maps_after_edits(
    *,
    applied_doc: L3Document,
    original_doc: L3Document,
    edits: list[object],
    old_nid_map: dict[int, int],
    old_spec_key_map: dict[int, str],
    old_original_name_map: dict[int, str],
    conn: sqlite3.Connection,
) -> AppliedRenderMaps:
    """Re-key the old renderer maps onto the applied doc's node ids.

    Algorithm:

    1. If no edits or the applied doc is the original doc (``apply_edits``
       short-circuits on an empty stmt list), return the old maps as-is.
    2. Walk both trees in BFS. Pair up nodes by position — the AST
       shape is stable across a swap (same children count, same
       positions); only the objects along the edit path are new.
    3. For each matched pair:

       - Head equal → carry forward ``old_nid_map`` /
         ``old_spec_key_map`` / ``old_original_name_map`` entries onto
         the new ``id()``.
       - Head differs with same ``eid`` → a swap fired here. Emit
         a *synthetic negative* nid (distinct per swap to avoid DB
         collision), record the new master's CKR ``figma_node_id``
         into ``db_visuals_patch``, and label the node with the new
         master's name.

    4. If a swap target's new master isn't in the CKR, raise
       :class:`SwapUnresolvedInCKR`.

    Non-swap AST mutations (append/insert/move/replace with a subtree)
    can introduce nodes with no original counterpart; those aren't in
    M7.2's scope. This function skips them silently — the renderer
    will fall to the Mode-2 cheap-emission path, which is visible
    enough to catch in review but not catastrophic.
    """
    if not edits or applied_doc is original_doc:
        return AppliedRenderMaps(
            nid_map=dict(old_nid_map),
            spec_key_map=dict(old_spec_key_map),
            original_name_map=dict(old_original_name_map),
            db_visuals_patch={},
        )

    # Tier A.2: path-based matching (upgraded from the M7.2-era
    # positional BFS). Insert / delete / move shift positions, so
    # position-based pairing misaligns the moment one of those
    # verbs fires mid-tree. Path keys — (eid, sibling_idx) chain
    # from the root — are stable across additions/removals at
    # sibling positions.
    original_by_path = _index_by_path(original_doc)

    new_nid_map: dict[int, int] = {}
    new_spec_key_map: dict[int, str] = {}
    new_original_name_map: dict[int, str] = {}
    db_visuals_patch: dict[int, dict[str, Any]] = {}

    # Synthetic nid allocator. Stays negative so it can't collide
    # with any DB-assigned id.
    next_synth_nid = -1

    swap_stmts = _collect_swap_statements(edits)
    swapped_eids: dict[str, str] = {
        s.target.path: s.with_node.head.type_or_path for s in swap_stmts
    }

    def walk(nodes, prefix):
        nonlocal next_synth_nid
        for idx, applied_node in enumerate(nodes):
            if not isinstance(applied_node, Node):
                continue
            eid_key = applied_node.head.eid or f"__anon_{idx}"
            path = prefix + (eid_key,)
            orig_node = original_by_path.get(path)

            if orig_node is not None:
                # Same path in both trees. Either identity-preserving
                # (head equal → carry forward) or a swap target
                # (head differs, eid preserved by the swap verb).
                same_head = (
                    orig_node.head.eid == applied_node.head.eid
                    and orig_node.head.head_kind == applied_node.head.head_kind
                    and orig_node.head.type_or_path == applied_node.head.type_or_path
                )
                new_id = id(applied_node)
                if same_head:
                    oid = id(orig_node)
                    if oid in old_nid_map:
                        new_nid_map[new_id] = old_nid_map[oid]
                    if oid in old_spec_key_map:
                        new_spec_key_map[new_id] = old_spec_key_map[oid]
                    if oid in old_original_name_map:
                        new_original_name_map[new_id] = old_original_name_map[oid]
                elif applied_node.head.eid in swapped_eids:
                    # Swap target — synth nid + CKR-resolved figma_id.
                    new_master = applied_node.head.type_or_path
                    figma_id = _lookup_master_in_ckr(conn, new_master)
                    if not figma_id:
                        raise SwapUnresolvedInCKR(
                            f"swap target `@{applied_node.head.eid}` "
                            f"references master `{new_master}` which "
                            "is not in the component_key_registry "
                            "on this DB."
                        )
                    synth_nid = next_synth_nid
                    next_synth_nid -= 1
                    new_nid_map[new_id] = synth_nid
                    # Preserve the old spec_key so baseline_walk_idx
                    # lookup stays valid (see M7.2 note).
                    new_spec_key_map[new_id] = old_spec_key_map.get(
                        id(orig_node), applied_node.head.eid,
                    )
                    new_original_name_map[new_id] = new_master
                    db_visuals_patch[synth_nid] = {
                        "component_figma_id": figma_id,
                        "component_key": None,
                        "node_type": "INSTANCE",
                        "figma_node_id": figma_id,
                    }
                # (Else: path matches but head differs and no swap —
                # shouldn't happen under current grammar; skip
                # silently.)
            else:
                # No counterpart in original. This is a fresh node
                # from append / insert / replace. No DB nid (never
                # existed); no CKR lookup (it's a type-keyword new
                # node, not a comp-ref swap target). Emit just
                # spec_key + original_name so the renderer's
                # M[<eid>] = nN.id emission reaches it. The
                # renderer's Mode-2 cheap-emission path handles
                # node materialisation (createFrame/createText/etc).
                new_id = id(applied_node)
                eid = applied_node.head.eid or ""
                if eid:
                    new_spec_key_map[new_id] = eid
                    new_original_name_map[new_id] = eid

            block = applied_node.block
            if block is not None:
                walk(block.statements, path)

    walk(applied_doc.top_level, ())

    return AppliedRenderMaps(
        nid_map=new_nid_map,
        spec_key_map=new_spec_key_map,
        original_name_map=new_original_name_map,
        db_visuals_patch=db_visuals_patch,
    )


def adjust_spec_elements_for_edits(
    elements: dict[str, dict[str, Any]],
    *,
    edits: list[object],
) -> dict[str, dict[str, Any]]:
    """Return a copy of ``elements`` updated to reflect each ``swap``
    applied in ``edits``.

    For each swap target eid:

    - ``comp_ref`` gets the new master name.
    - ``visual.fills`` / ``visual.strokes`` / ``visual.effects`` are
      set to ``None`` so :class:`dd.verify_figma.FigmaRenderVerifier`
      skips the solid-color / effect-count comparisons (they'd fire
      spuriously — the new master supplies its own fills at render
      time, not whatever the old master had on the DB row).

    Other element fields (``type`` / ``layout.sizing`` / ``props`` /
    children) stay untouched — they're either structurally correct
    after the swap (the new master is still a ``button``) or they
    feed the wireframe-placeholder fallback in Mode-1 and should be
    left alone."""
    out = {eid: dict(e) for eid, e in elements.items()}
    for stmt in _collect_swap_statements(edits):
        eid = stmt.target.path
        if eid not in out:
            continue
        entry = out[eid]
        entry["comp_ref"] = stmt.with_node.head.type_or_path
        visual = dict(entry.get("visual") or {})
        if "fills" in visual:
            visual["fills"] = None
        if "strokes" in visual:
            visual["strokes"] = None
        if "effects" in visual:
            visual["effects"] = None
        entry["visual"] = visual
        out[eid] = entry
    return out


# ---------------------------------------------------------------------------
# Full-pipeline render wrapper
# ---------------------------------------------------------------------------


@dataclass
class RenderedApplied:
    """Output of :func:`render_applied_doc`.

    ``script`` is the Figma JS string the caller hands to the plugin
    bridge. ``adjusted_spec`` is the CompositionSpec-shaped dict that
    :class:`dd.verify_figma.FigmaRenderVerifier` should compare against
    the walked render (its ``elements`` reflects the applied swaps).
    ``applied_maps`` is the side-car output of
    :func:`rebuild_maps_after_edits`, exposed so callers can inspect
    which eids got synthesised-nid patches. ``token_refs`` is forwarded
    from ``render_figma`` unchanged — not M7.2-relevant but callers
    may want it for later rebind passes.

    ``eid_to_spec_key`` maps each swap target's eid onto the spec
    element key the renderer wrote into ``M[...]``. Callers need it
    to look up the rendered entry in ``rendered_ref.eid_map``; the
    walker keys that on whatever ``M`` contains, which is the
    spec_key, not the user-facing eid."""

    script: str
    adjusted_spec: dict[str, Any]
    applied_maps: AppliedRenderMaps
    token_refs: list[tuple[str, str, str]]
    eid_to_spec_key: dict[str, str]


def render_applied_doc(
    *,
    applied_doc: L3Document,
    original_doc: L3Document,
    edits: list[object],
    spec: dict[str, Any],
    conn: sqlite3.Connection,
    db_visuals: dict[int, dict[str, Any]],
    fonts: list[tuple[str, str]],
    old_nid_map: dict[int, int],
    old_spec_key_map: dict[int, str],
    old_original_name_map: dict[int, str],
    ckr_built: bool = True,
    page_name: Optional[str] = None,
    canvas_position: Optional[tuple[float, float]] = None,
) -> RenderedApplied:
    """Render the applied L3 doc as a full Figma script.

    Wires :func:`rebuild_maps_after_edits` →
    :func:`adjust_spec_elements_for_edits` → ``render_figma``. Callers
    give the *original* compressor output (``doc`` + 3 maps + spec +
    db_visuals + fonts) and the edit statements; the wrapper rebuilds
    the renderer's internal state against the applied doc.

    The caller keeps ``db_visuals`` read-only — the wrapper merges the
    synthetic swap patches into a local copy so the original stays
    reusable across multiple swap attempts."""
    from dd.render_figma_ast import render_figma

    maps = rebuild_maps_after_edits(
        applied_doc=applied_doc,
        original_doc=original_doc,
        edits=edits,
        old_nid_map=old_nid_map,
        old_spec_key_map=old_spec_key_map,
        old_original_name_map=old_original_name_map,
        conn=conn,
    )

    original_elements = spec.get("elements") or {}
    adjusted_elements = adjust_spec_elements_for_edits(
        original_elements, edits=edits,
    )
    adjusted_spec = dict(spec)
    adjusted_spec["elements"] = adjusted_elements

    merged_visuals = dict(db_visuals)
    merged_visuals.update(maps.db_visuals_patch)

    script, token_refs = render_figma(
        applied_doc, conn, maps.nid_map,
        fonts=fonts,
        spec_key_map=maps.spec_key_map,
        original_name_map=maps.original_name_map,
        db_visuals=merged_visuals,
        ckr_built=ckr_built,
        page_name=page_name,
        canvas_position=canvas_position,
        _spec_elements=adjusted_elements,
        _spec_tokens=spec.get("tokens") or {},
    )

    # Invert spec_key_map for the caller. Walk the applied doc and
    # pair each swap target eid with the spec_key the renderer used.
    swap_targets: set[str] = {
        s.target.path for s in _collect_swap_statements(edits)
    }
    eid_to_spec_key: dict[str, str] = {}
    if swap_targets:
        for n in _bfs_nodes(applied_doc):
            if n.head.eid in swap_targets:
                sk = maps.spec_key_map.get(id(n))
                if sk is not None:
                    eid_to_spec_key[n.head.eid] = sk

    return RenderedApplied(
        script=script,
        adjusted_spec=adjusted_spec,
        applied_maps=maps,
        token_refs=token_refs,
        eid_to_spec_key=eid_to_spec_key,
    )


# ---------------------------------------------------------------------------
# Plugin-bridge wrapper (round-trip walk to rendered_ref)
# ---------------------------------------------------------------------------


class BridgeError(RuntimeError):
    """Raised when ``walk_rendered_via_bridge`` fails: walk_ref.js not
    found, node binary unavailable, bridge connection timed out, or the
    subprocess returned non-zero. Message carries the specific cause;
    the return-shape is never ambiguous."""


_DEFAULT_WALK_SCRIPT = Path("render_test/walk_ref.js")


def walk_rendered_via_bridge(
    *,
    script: str,
    ws_port: int = 9228,
    walk_script: Path = _DEFAULT_WALK_SCRIPT,
    timeout: float = 180.0,
    node_binary: Optional[str] = None,
    keep_artifacts: bool = False,
    artifact_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Send ``script`` to a live Figma plugin bridge and walk the
    rendered subtree. Returns the parsed ``rendered_ref`` dict.

    The bridge contract is what ``render_test/walk_ref.js`` expects: a
    WebSocket on ``ws://localhost:<ws_port>`` that accepts
    ``{type:"PROXY_EXECUTE", id, code, timeout}`` and responds with
    ``{type:"PROXY_EXECUTE_RESULT", id, result:{result:{...}}}``. The
    Figma plugin harness in the repo already implements that protocol.

    ``keep_artifacts=True`` preserves the script + output JSON in
    ``artifact_dir`` (or a new temp dir) so a failed round-trip can be
    reproduced from disk. By default the tempdir is cleaned on success.

    Raises :class:`BridgeError` on any failure — the caller decides
    whether to fall through to structural-only verification."""
    if node_binary is None:
        node_binary = shutil.which("node") or ""
    if not node_binary:
        raise BridgeError(
            "`node` not on PATH — Figma plugin bridge wrapper can't "
            "run without a Node.js binary."
        )
    if not walk_script.exists():
        raise BridgeError(
            f"bridge walk script not found at {walk_script}; pass "
            "walk_script= to override."
        )

    workdir = artifact_dir or Path(tempfile.mkdtemp(prefix="m7_bridge_"))
    workdir.mkdir(parents=True, exist_ok=True)
    script_path = workdir / "script.js"
    out_path = workdir / "rendered_ref.json"
    script_path.write_text(script)

    cmd = [
        node_binary, str(walk_script),
        str(script_path), str(out_path), str(ws_port),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=Path.cwd(),
        )
    except subprocess.TimeoutExpired as e:
        raise BridgeError(
            f"walk_ref.js timed out after {timeout}s "
            f"(port {ws_port}); is the Figma plugin listening?"
        ) from e

    if proc.returncode != 0:
        raise BridgeError(
            f"walk_ref.js exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout or '').strip()[:500]}"
        )
    if not out_path.exists():
        raise BridgeError(
            "walk_ref.js produced no output JSON — check stderr: "
            f"{proc.stderr.strip()[:500]}"
        )
    try:
        payload = json.loads(out_path.read_text())
    except json.JSONDecodeError as e:
        raise BridgeError(
            f"walk_ref.js wrote invalid JSON: {e}"
        ) from e
    if not keep_artifacts:
        # When we own the tempdir (artifact_dir is None), shutil.rmtree
        # handles any sidecar files walk_ref.js might write (stderr
        # logs, partial payloads) without race-ing on rmdir. When the
        # caller passed an artifact_dir, leave it intact — the
        # sidecars belong to them.
        if artifact_dir is None:
            import shutil as _shutil
            _shutil.rmtree(workdir, ignore_errors=True)
    return payload
