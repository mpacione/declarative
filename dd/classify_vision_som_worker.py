"""SoM classifier worker — library module.

Reusable between the M7 bake-off (scripts/m7_bakeoff_som.py) and
the production classify_v2 pipeline. The bake-off was the original
home for these functions; moving them into `dd/` lets the classify
pipeline call SoM as a fourth vision source without a script-level
import dance.

Three entry points:

- ``build_screen_annotations``: per-rep annotation dicts for the SoM
  overlay renderer + VLM schema.
- ``prepare_screen_bundle``: gather screenshot + annotations + per-
  node renders + self-hidden plugin-toggle renders for one screen.
  Main-thread work (DB reads, HTTP calls, Node subprocesses) — cheap
  to serialise so worker threads see pre-computed bundles only.
- ``run_som_on_screen``: given a prepared bundle + VLM client, run
  the visibility dispatch (SoM for visible; per-crop vision for
  ancestor-hidden; dedup-twin / LLM-text cascade for self-hidden).
  Worker-thread safe.

Plus the orchestrator:

- ``classify_reps_with_som``: group deduped reps by screen, prepare
  bundles main-thread, dispatch SoM calls across workers, merge
  results. Used by both the bake-off and `classify_v2`.

Self-hidden reps: if the Figma desktop bridge + plugin is reachable
on ``plugin_port``, those reps go through the plugin render-toggle
+ checkerboard path and join the main SoM call. Otherwise they fall
through to dedup-twin propagation → LLM-text fallback → unsure.
"""

from __future__ import annotations

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional


def build_screen_annotations(
    reps_on_screen: list[dict[str, Any]],
    root_x: float,
    root_y: float,
    *,
    was_self_hidden: bool = False,
) -> list[dict[str, Any]]:
    """Convert rep rows → SoM annotation dicts (one per mark).

    Uses 1..N ids scoped per screen so the model's mark labels stay
    short. ``was_self_hidden`` marks annotations that were toggled
    visible via the plugin render-toggle so the caller can label
    those verdicts with a distinct path in bake-off / pipeline
    output.
    """
    annotations: list[dict[str, Any]] = []
    for i, r in enumerate(reps_on_screen, 1):
        annotations.append({
            "id": i,
            "sci_id": r["sci_id"],
            "node_id": r["node_id"],
            "x": float(r.get("x") or 0) - root_x,
            "y": float(r.get("y") or 0) - root_y,
            "w": float(r.get("width") or 0),
            "h": float(r.get("height") or 0),
            "rotation": float(r.get("rotation") or 0),
            "name": r.get("name"),
            "node_type": r.get("node_type"),
            "sample_text": r.get("sample_text"),
            "parent_classified_as": r.get("parent_classified_as"),
            "total_children": r.get("total_children"),
            "was_self_hidden": was_self_hidden,
        })
    return annotations


def prepare_screen_bundle(
    conn: sqlite3.Connection,
    screen_id: int,
    reps_on_screen: list[dict[str, Any]],
    file_key: str,
    fetch_screenshot: Callable,
    *,
    use_plugin_for_hidden: bool = True,
    plugin_port: int = 9227,
) -> Optional[dict[str, Any]]:
    """Pre-fetch everything a SoM worker needs for one screen.

    Runs on the main thread. Splits reps by visibility:
    - ``visible_effective=1``: eligible for SoM overlay.
    - ``visible_self=1, visible_effective=0``: ancestor-hidden → per-
      node Figma render + per-crop vision downstream.
    - ``visible_self=0``: self-hidden → when ``use_plugin_for_hidden``
      is set, try the plugin render-toggle to draw those nodes onto
      the screen (and composite on a checkerboard base so transparent
      regions are visible). Nodes that render this way join the main
      SoM annotation set; any that don't fall through to the dedup-
      twin / LLM-text cascade.

    Returns ``None`` for unusable screens (missing screen row, no
    screenshot fetch, etc.).
    """
    row = conn.execute(
        "SELECT figma_node_id, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    if row is None:
        return None
    fig_id, sw, sh = row[0], float(row[1] or 0), float(row[2] or 0)

    root = conn.execute(
        "SELECT x, y FROM nodes WHERE screen_id = ? AND parent_id IS NULL",
        (screen_id,),
    ).fetchone()
    rx = float(root[0] or 0) if root else 0.0
    ry = float(root[1] or 0) if root else 0.0

    visible = [r for r in reps_on_screen if r.get("visible_effective", 1)]
    anc_hidden = [
        r for r in reps_on_screen
        if not r.get("visible_effective", 1) and r.get("visible_self", 1)
    ]
    self_hidden = [
        r for r in reps_on_screen if not r.get("visible_self", 1)
    ]

    try:
        screen_png = fetch_screenshot(file_key, fig_id)
    except Exception as e:
        print(f"  screen {screen_id}: screenshot fetch failed: {e}",
              file=sys.stderr, flush=True)
        return None
    if not screen_png:
        return None

    # Self-hidden plugin path: toggle hidden nodes + ancestors visible,
    # export the screen, composite on checkerboard. Self-hidden reps
    # that successfully render this way enter the main SoM annotation
    # set; the rest fall through to the dedup-twin / LLM-text cascade.
    self_hidden_for_som: list[dict[str, Any]] = []
    self_hidden_fallback: list[dict[str, Any]] = self_hidden
    if use_plugin_for_hidden and self_hidden:
        hidden_fig_ids = [
            r.get("node_figma_id") for r in self_hidden
            if r.get("node_figma_id")
        ]
        if hidden_fig_ids:
            from dd.checkerboard import composite_on_checkerboard
            from dd.plugin_render import render_screen_with_visible_nodes

            toggled_png = render_screen_with_visible_nodes(
                screen_figma_id=fig_id,
                hidden_node_figma_ids=hidden_fig_ids,
                scale=2,
                port=plugin_port,
            )
            if toggled_png is not None:
                screen_png = composite_on_checkerboard(toggled_png)
                self_hidden_for_som = [
                    r for r in self_hidden if r.get("node_figma_id")
                ]
                self_hidden_fallback = [
                    r for r in self_hidden if not r.get("node_figma_id")
                ]
            else:
                reason = getattr(
                    render_screen_with_visible_nodes, "last_error", None,
                )
                print(
                    f"  screen {screen_id}: plugin render-toggle "
                    f"unavailable ({reason or 'unknown'}); self-hidden "
                    f"reps use fallback cascade.",
                    file=sys.stderr, flush=True,
                )

    annotations = build_screen_annotations(visible, rx, ry)
    hidden_annotations = build_screen_annotations(
        self_hidden_for_som, rx, ry, was_self_hidden=True,
    )
    next_id = len(annotations) + 1
    for a in hidden_annotations:
        a["id"] = next_id
        next_id += 1
    annotations.extend(hidden_annotations)

    # Per-node renders for ancestor-hidden reps, fetched main-thread
    # to avoid SQLite connection crossing in workers.
    hidden_renders: dict[int, bytes] = {}
    for r in anc_hidden:
        nfid = r.get("node_figma_id")
        if not nfid:
            continue
        try:
            png = fetch_screenshot(file_key, nfid)
        except Exception:
            png = None
        if png is not None:
            hidden_renders[r["sci_id"]] = png

    return {
        "screen_id": screen_id,
        "annotations": annotations,
        "screen_png": screen_png,
        "screen_width": sw,
        "screen_height": sh,
        "visible_reps": visible,
        "anc_hidden_reps": anc_hidden,
        "hidden_renders": hidden_renders,
        "self_hidden_reps": self_hidden_fallback,
    }


def run_som_on_screen(
    *,
    screen_id: int,
    annotations: list[dict[str, Any]],
    screen_png: bytes,
    screen_width: float,
    screen_height: float,
    anc_hidden_reps: list[dict[str, Any]],
    hidden_renders: dict[int, bytes],
    self_hidden_reps: list[dict[str, Any]],
    client: Any,
    catalog: list[dict[str, Any]],
    visible_reps: Optional[list[dict[str, Any]]] = None,
) -> dict[int, dict[str, Any]]:
    """Visibility-dispatching SoM worker.

    Runs:
    - SoM overlay classification on annotations (visible +
      plugin-toggled self-hidden).
    - Per-crop vision on ancestor-hidden reps via the stored
      per-node renders.
    - Dedup-twin → LLM-text → unsure cascade on any self-hidden
      reps that didn't render via the plugin.

    Returns a ``{sci_id: verdict}`` dict where each verdict carries
    ``canonical_type``, ``confidence``, ``reason``, and a ``path``
    label marking which branch produced the result.
    """
    from dd.classify_dedup import dedup_key
    from dd.classify_vision_batched import classify_crops_batch
    from dd.classify_vision_som import classify_screen_som

    out: dict[int, dict[str, Any]] = {}

    # 1. SoM for visible (and plugin-toggled self-hidden).
    if annotations and screen_png:
        try:
            som_out = classify_screen_som(
                screen_png=screen_png,
                annotations=annotations,
                client=client,
                catalog=catalog,
                screen_width=screen_width, screen_height=screen_height,
            )
        except Exception as e:
            print(f"  screen {screen_id}: SoM call failed: {e}",
                  file=sys.stderr, flush=True)
            som_out = []
        by_mark = {a["id"]: a for a in annotations}
        for c in som_out:
            ann = by_mark.get(c["mark_id"])
            if ann is None:
                continue
            out[ann["sci_id"]] = {
                "canonical_type": c["canonical_type"],
                "confidence": c["confidence"],
                "reason": c["reason"],
                "path": (
                    "self_hidden_plugin_som"
                    if ann.get("was_self_hidden")
                    else "som"
                ),
            }

    # 2. Per-crop vision for ancestor-hidden reps.
    usable_hidden = [
        r for r in anc_hidden_reps if r["sci_id"] in hidden_renders
    ]
    if usable_hidden:
        crops = {
            (r["screen_id"], r["node_id"]): hidden_renders[r["sci_id"]]
            for r in usable_hidden
        }
        try:
            hidden_out = classify_crops_batch(
                usable_hidden, crops, client, catalog=catalog,
            )
        except Exception as e:
            print(
                f"  screen {screen_id}: hidden-crop call failed: {e}",
                file=sys.stderr, flush=True,
            )
            hidden_out = []
        by_key = {(r["screen_id"], r["node_id"]): r for r in usable_hidden}
        for c in hidden_out:
            key = (c.get("screen_id"), c.get("node_id"))
            rep = by_key.get(key)
            if rep is None:
                continue
            out[rep["sci_id"]] = {
                "canonical_type": c.get("canonical_type"),
                "confidence": c.get("confidence", 0.7),
                "reason": c.get("reason", ""),
                "path": "hidden_pernode",
            }

    # 3. Self-hidden fallback ladder for reps that didn't go through
    # the plugin path. Twin propagation → LLM-text → unsure.
    sig_to_verdict: dict[tuple, dict[str, Any]] = {}
    for r in (annotations or []):
        verdict = out.get(r["sci_id"])
        if verdict:
            try:
                sig = dedup_key({
                    "name": r.get("name"),
                    "node_type": r.get("node_type"),
                    "parent_classified_as": r.get("parent_classified_as"),
                    "child_type_dist": {},
                    "sample_text": r.get("sample_text"),
                    "component_key": None,
                    "width": r.get("w"),
                    "height": r.get("h"),
                })
                sig_to_verdict.setdefault(sig, verdict)
            except Exception:
                pass
    for r in anc_hidden_reps:
        verdict = out.get(r["sci_id"])
        if verdict:
            try:
                sig = dedup_key(r)
                sig_to_verdict.setdefault(sig, verdict)
            except Exception:
                pass

    for r in self_hidden_reps:
        propagated: Optional[dict[str, Any]] = None
        try:
            sig = dedup_key(r)
            if sig in sig_to_verdict:
                propagated = sig_to_verdict[sig]
        except Exception:
            propagated = None
        if propagated:
            out[r["sci_id"]] = {
                "canonical_type": propagated["canonical_type"],
                "confidence": float(propagated.get("confidence", 0.75)),
                "reason": (
                    "Self-hidden node; propagated from visible twin "
                    "with matching dedup signature."
                ),
                "path": "self_hidden_twin",
            }
            continue
        llm_type = r.get("llm_type")
        if llm_type:
            out[r["sci_id"]] = {
                "canonical_type": llm_type,
                "confidence": 0.6,
                "reason": (
                    "Self-hidden node (visible=0); classified from "
                    "LLM text signal alone (no vision). Verdict copied "
                    f"from sci.llm_type={llm_type!r}."
                ),
                "path": "self_hidden_llm_only",
            }
        else:
            out[r["sci_id"]] = {
                "canonical_type": "unsure",
                "confidence": 0.0,
                "reason": (
                    "Self-hidden node with no usable signals (no "
                    "vision render possible, no LLM verdict)."
                ),
                "path": "self_hidden_unsure",
            }

    return out


def classify_reps_with_som(
    conn: sqlite3.Connection,
    reps: list[dict[str, Any]],
    client: Any,
    catalog: list[dict[str, Any]],
    fetch_screenshot: Callable,
    file_key: str,
    *,
    workers: int = 4,
    use_plugin_for_hidden: bool = True,
    plugin_port: int = 9227,
) -> dict[int, dict[str, Any]]:
    """Run SoM across a deduped rep set.

    Reps MUST already be deduplicated (each sci_id should be a
    dedup-group representative). Callers propagate the returned
    verdicts to every member of the group downstream.

    Flow:
    1. Group reps by screen.
    2. Prepare bundles main-thread (DB reads + REST fetch +
       optional plugin render-toggle).
    3. Dispatch SoM + per-crop vision across workers, one screen
       per task.
    4. Merge per-screen verdict maps into one ``{sci_id: verdict}``.

    Returns a dict mapping each rep's sci_id to its verdict. Reps
    that couldn't be classified (unusable screen, empty visibility
    class) are silently dropped — callers treat missing keys as
    "SoM had no verdict for this rep".
    """
    if not reps:
        return {}

    reps_by_screen: dict[int, list[dict[str, Any]]] = {}
    for r in reps:
        reps_by_screen.setdefault(r["screen_id"], []).append(r)

    bundles: list[dict[str, Any]] = []
    for sid, ra in reps_by_screen.items():
        bundle = prepare_screen_bundle(
            conn, sid, ra, file_key, fetch_screenshot,
            use_plugin_for_hidden=use_plugin_for_hidden,
            plugin_port=plugin_port,
        )
        if bundle is not None:
            bundles.append(bundle)

    def _submit(bundle: dict[str, Any]) -> dict[str, Any]:
        return dict(
            screen_id=bundle["screen_id"],
            annotations=bundle["annotations"],
            screen_png=bundle["screen_png"],
            screen_width=bundle["screen_width"],
            screen_height=bundle["screen_height"],
            anc_hidden_reps=bundle.get("anc_hidden_reps", []),
            hidden_renders=bundle.get("hidden_renders", {}),
            self_hidden_reps=bundle.get("self_hidden_reps", []),
            visible_reps=bundle.get("visible_reps", []),
            client=client,
            catalog=catalog,
        )

    merged: dict[int, dict[str, Any]] = {}
    if workers > 1 and len(bundles) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_som_on_screen, **_submit(b)): b["screen_id"]
                for b in bundles
            }
            for fut in as_completed(futures):
                sid = futures[fut]
                try:
                    merged.update(fut.result())
                except Exception as e:
                    print(f"  screen {sid} failed: {e}",
                          file=sys.stderr, flush=True)
    else:
        for b in bundles:
            try:
                merged.update(run_som_on_screen(**_submit(b)))
            except Exception as e:
                print(f"  screen {b['screen_id']} failed: {e}",
                      file=sys.stderr, flush=True)

    return merged
