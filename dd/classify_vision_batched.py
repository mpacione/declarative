"""Batched vision classification across multiple screens (M7.0.a).

Replaces the per-node vision path with a per-batch approach:

- One call classifies all unclassified nodes across N screens at once.
- Each screen's full-resolution image is sent alongside a list of
  ``{node_id, bbox, name, sample_text, parent_type, ...}`` entries
  for the nodes to classify on that screen.
- The model is explicitly asked to use cross-screen comparison
  signal when available — consistency checks, variant detection,
  outlier flagging — and to cite specific (other_screen_id,
  other_node_id) pairs when it does.

Two batch sizes are supported and compared via
``scripts/m7_vision_bakeoff.py``:

- **N=1** (per-screen batched): preserves max visual fidelity per
  screen, no cross-screen signal.
- **N=5** (cross-screen batched, grouped by `skeleton_type` +
  `device_class`): adds cross-screen comparison signal; same token
  + cost budget as N=1 within measurement noise.

The module is pure-function today — it returns classifications
and does NOT write to ``screen_component_instances``. Wiring the
winner into ``run_classification`` happens after the bake-off
decides between N=1 and N=5.
"""

from __future__ import annotations

import base64
import sqlite3
from collections.abc import Callable
from typing import Any

from dd.catalog import get_catalog
from dd.classify_llm import _format_catalog_for_prompt


DEFAULT_MODEL = "claude-sonnet-4-6"


# Tool schema for cross-screen classification. Each entry is a
# (screen_id, node_id) pair plus the canonical type, confidence,
# reason, and — when applicable — explicit cross-screen evidence
# citing other nodes in the batch. Structural evidence rather
# than prose prevents the model from fabricating cross-screen
# relationships that aren't visible.
CLASSIFY_ACROSS_SCREENS_TOOL_SCHEMA = {
    "name": "classify_nodes_across_screens",
    "description": (
        "Return one classification entry per node across all "
        "screens in the batch. Each entry names the canonical UI "
        "component type, a calibrated confidence, a short "
        "evidence-based reason, and optional cross-screen evidence "
        "(IDs of related nodes in other screens in this batch). "
        "Use `container` for structural layout frames with no "
        "specific identity. Use `unsure` when identity cannot be "
        "determined from the provided visual + structural signals. "
        "Every (screen_id, node_id) in the input must appear in the "
        "output exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "screen_id": {"type": "integer"},
                        "node_id": {"type": "integer"},
                        "canonical_type": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One short sentence citing the "
                                "visual signals (shape, content, "
                                "position, affordances) AND any "
                                "structural context (parent, "
                                "siblings, sample text). Evidence-"
                                "based; no speculation."
                            ),
                        },
                        "cross_screen_evidence": {
                            "type": "array",
                            "description": (
                                "Optional: node IDs from OTHER "
                                "screens in this batch that help "
                                "confirm or contrast this "
                                "classification. Empty when the "
                                "batch only has one screen or no "
                                "related nodes are visible."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "other_screen_id": {"type": "integer"},
                                    "other_node_id": {"type": "integer"},
                                    "relation": {
                                        "type": "string",
                                        "enum": [
                                            "same_component",
                                            "same_variant_family",
                                            "contrasting_variant",
                                            "structural_analogue",
                                            "outlier",
                                        ],
                                    },
                                },
                                "required": [
                                    "other_screen_id",
                                    "other_node_id",
                                    "relation",
                                ],
                            },
                        },
                    },
                    "required": [
                        "screen_id", "node_id",
                        "canonical_type", "confidence", "reason",
                    ],
                },
            },
        },
        "required": ["classifications"],
    },
}


def _describe_node_in_batch(node: dict[str, Any]) -> str:
    parts = [
        f"node_id={node['node_id']}",
        f'name="{node["name"]}"',
        f"bbox=({int(node.get('x') or 0)},{int(node.get('y') or 0)},"
        f"{int(node.get('width') or 0)},{int(node.get('height') or 0)})",
    ]
    if node.get("layout_mode"):
        parts.append(f"layout={node['layout_mode']}")
    total_children = node.get("total_children")
    if total_children:
        dist = node.get("child_type_dist") or {}
        parts.append(
            f"children={total_children}"
            f" ({', '.join(f'{k}:{v}' for k, v in dist.items())})"
        )
    if node.get("sample_text"):
        t = str(node["sample_text"])[:60]
        parts.append(f'sample_text="{t}"')
    if node.get("parent_classified_as"):
        parts.append(f"parent={node['parent_classified_as']}")
    if node.get("ckr_registered_name"):
        parts.append(f'component_key="{node["ckr_registered_name"]}"')
    return "  - " + "; ".join(parts)


def build_batched_vision_prompt(
    batch: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> str:
    """Render the full prompt for a batched vision call.

    ``batch`` is a list of per-screen dicts, each containing:
    ``screen_id``, ``name``, ``device_class``, ``skeleton``,
    ``width``, ``height``, and ``unclassified`` (list of node
    dicts with bbox + context).
    """
    catalog_block = _format_catalog_for_prompt(catalog)

    screen_blocks: list[str] = []
    for i, s in enumerate(batch, 1):
        node_lines = "\n".join(
            _describe_node_in_batch(n) for n in s["unclassified"]
        )
        screen_blocks.append(
            f"### Screen {i} — screen_id={s['screen_id']}: "
            f"{s['name']} ({int(s['width'])}×{int(s['height'])}, "
            f"{s.get('device_class', 'unknown')})\n"
            f"Skeleton: `{s.get('skeleton') or '(none)'}`\n\n"
            f"Unclassified nodes to classify on this screen:\n"
            f"{node_lines}"
        )
    screens_text = "\n\n".join(screen_blocks)

    cross_rules = ""
    if len(batch) > 1:
        cross_rules = """

## Cross-screen rules

You are seeing {n} screens from the same design system grouped by device class and skeleton type. Use them together:

- **Cross-screen signal REINFORCES a specific classification, it does NOT downgrade.** If a header pattern appears on multiple screens, that confirms `header` — not `container`. Cross-screen similarity is evidence FOR specificity, not against it.
- Cite `cross_screen_evidence` with `relation="same_component"` / `"same_variant_family"` for shared patterns, `"contrasting_variant"` / `"structural_analogue"` for parallel slots filled differently, `"outlier"` for nodes inconsistent with the rest (and lower confidence in that case).
- Cross-screen evidence is **optional**. Leave the array empty when nothing in other screens clarifies this classification.
""".format(n=len(batch))

    n_classifications_expected = sum(
        len(s["unclassified"]) for s in batch
    )

    return f"""You are classifying UI nodes across {len(batch)} screens from a Figma design file against a fixed catalog of canonical component types. This classification feeds a design-system compiler — accuracy matters, and "unsure" is a valid answer.

## Canonical types (pick exactly one per node)

Use the behavioral description to disambiguate. The UI component that matches the *function* of the node wins, not the one that merely looks similar.
{catalog_block}

## Rules

1. **Pick one canonical type per node.** `container` and `unsure` are valid but prefer a specific type when evidence supports it.

2. **Confidence is calibrated.**
   - **0.95+** — unambiguous (visual + structural both point to one type).
   - **0.85–0.94** — strong signal + minor alternative.
   - **0.75–0.84** — real evidence + plausible alternative. Use the specific type at this band.
   - **Below 0.75** — **prefer `unsure`** with a reason rather than a low-confidence specific type. Hedging with "container at 0.70" loses more information than an honest `unsure`.

3. **Don't regress to `container` when a specific type has evidence.** `container` is for *truly generic layout frames with no identity signals*. If the node has ANY specific signal (distinctive name, characteristic children, sample text, known pattern, distinctive visual affordance in the screenshot), classify it specifically. A `button_group` is more useful downstream than a `container` with 3 button children. Visual evidence from the screenshot ALWAYS trumps structural ambiguity.

4. **Empty-frame grid pattern.** Multiple identical frames (same size, same parent, no children, no text) arranged in a grid → `skeleton` (loading placeholder). Only call it `image` when the frame visibly contains image content in the screenshot.

5. **Decorative-child pattern.** A small frame with N identical decorative children (3 ellipses → grabber/dots, 2 chevrons → toggle indicator) is typically a single semantic `icon`, not a `container` of N independent things. Use the screenshot to confirm the glyph-like appearance.

6. **Reasons are evidence-based.** Cite visual signals (shape, content, affordances) AND structural context (parent, sample text, layout, child count). "Structural grouping of controls" is a weak reason — if the children are all buttons in the screenshot, say `button_group` and cite the buttons.

7. **Every (screen_id, node_id) in the input must appear in the output exactly once.** {n_classifications_expected} nodes total across the batch.{cross_rules}

## Screens + nodes to classify

{screens_text}

Return your classifications via the `classify_nodes_across_screens` tool."""


def _extract_classifications_from_response(response: Any) -> list[dict[str, Any]]:
    """Pull the ``classifications`` array from a Claude tool-use
    response. Returns an empty list if the tool_use block is
    missing or the input is malformed — caller logs + skips,
    never invents data.
    """
    if response is None or not getattr(response, "content", None):
        return []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != CLASSIFY_ACROSS_SCREENS_TOOL_SCHEMA["name"]:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            classifications = inp.get("classifications")
            if isinstance(classifications, list):
                return [c for c in classifications if isinstance(c, dict)]
        return []
    return []


def _fetch_unclassified_for_screen(
    conn: sqlite3.Connection, screen_id: int,
    target_source: str = "unclassified",
) -> list[dict[str, Any]]:
    """Fetch candidate FRAME/INSTANCE/COMPONENT nodes on a screen
    with bbox + enriched context (parent classification, child
    distribution, sample text, CKR master name).

    ``target_source`` controls which nodes are returned:

    - ``"unclassified"`` (default) — nodes with no row in
      `screen_component_instances`. Used by single-source vision
      (pre-three-source) when vision classifies what formal /
      heuristic / LLM didn't cover.
    - ``"llm"`` — nodes classified by the LLM text stage. Used by
      three-source vision PS + CS: all three sources classify the
      SAME candidate set, then consensus votes.

    Returns bbox coordinates (x/y/width/height) so the prompt can
    point the model at the exact spatial region.
    """
    if target_source == "llm":
        sci_filter = "sci.classification_source = 'llm'"
    elif target_source == "llm_missing_cs":
        # Resume path: only LLM rows that haven't received a CS
        # verdict yet. Lets a crashed three-source run pick up where
        # it left off without re-paying for completed batches.
        sci_filter = (
            "sci.classification_source = 'llm' "
            "AND sci.vision_cs_type IS NULL"
        )
    else:
        sci_filter = "sci.id IS NULL"

    cursor = conn.execute(
        f"""
        SELECT n.id AS node_id, n.name, n.node_type, n.depth,
               n.x, n.y, n.width, n.height, n.layout_mode,
               n.parent_id, n.component_key
        FROM nodes n
        LEFT JOIN screen_component_instances sci
          ON sci.node_id = n.id AND sci.screen_id = n.screen_id
        WHERE n.screen_id = ?
          AND n.node_type IN ('FRAME', 'INSTANCE', 'COMPONENT')
          AND n.depth >= 1
          AND {sci_filter}
        ORDER BY n.depth, n.sort_order
        """,
        (screen_id,),
    )
    cols = [d[0] for d in cursor.description]
    raw = [dict(zip(cols, row)) for row in cursor.fetchall()]

    from dd.classify_rules import is_system_chrome
    candidates = [r for r in raw if not is_system_chrome(r["name"])]

    for r in candidates:
        pid = r.get("parent_id")
        if pid is not None:
            pr = conn.execute(
                "SELECT sci.canonical_type "
                "FROM nodes n LEFT JOIN screen_component_instances sci "
                "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
                "WHERE n.id = ?",
                (pid,),
            ).fetchone()
            r["parent_classified_as"] = pr[0] if pr else None
        else:
            r["parent_classified_as"] = None

        children = conn.execute(
            "SELECT node_type, COUNT(*) FROM nodes "
            "WHERE parent_id = ? GROUP BY node_type",
            (r["node_id"],),
        ).fetchall()
        r["child_type_dist"] = {k: v for k, v in children}
        r["total_children"] = sum(v for _, v in children)

        text_child = conn.execute(
            "SELECT text_content FROM nodes "
            "WHERE parent_id = ? AND node_type = 'TEXT' "
            "AND text_content IS NOT NULL AND text_content != '' "
            "ORDER BY sort_order LIMIT 1",
            (r["node_id"],),
        ).fetchone()
        r["sample_text"] = text_child[0] if text_child else None

        ck = r.get("component_key")
        if ck:
            ckr_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='component_key_registry'"
            ).fetchone()
            if ckr_exists:
                ckr = conn.execute(
                    "SELECT name FROM component_key_registry "
                    "WHERE component_key = ?",
                    (ck,),
                ).fetchone()
                r["ckr_registered_name"] = ckr[0] if ckr else None
            else:
                r["ckr_registered_name"] = None
        else:
            r["ckr_registered_name"] = None
    return candidates


def _build_batch_payload(
    conn: sqlite3.Connection, screen_ids: list[int],
    fetch_screenshot: Callable, file_key: str,
    target_source: str = "unclassified",
) -> list[dict[str, Any]]:
    """Fetch + assemble the per-screen payload for a batch.

    Each entry has the screen metadata, the screen's image bytes,
    its screen skeleton notation, and the list of candidate nodes
    with bbox + context. ``target_source`` is forwarded to
    `_fetch_unclassified_for_screen` (see its docstring).
    """
    batch: list[dict[str, Any]] = []
    # Fetch screens metadata + skeletons + figma_node_id for the
    # screen itself (needed as the Figma REST /images target).
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.device_class, s.width, s.height,
               s.figma_node_id, ss.skeleton_notation
        FROM screens s
        LEFT JOIN screen_skeletons ss ON ss.screen_id = s.id
        WHERE s.id IN (%s)
        ORDER BY s.id
        """ % ",".join("?" * len(screen_ids)),
        screen_ids,
    ).fetchall()
    screens_by_id = {r[0]: r for r in rows}

    # Fetch all screen screenshots in one batched call where possible.
    figma_ids = [screens_by_id[sid][5] for sid in screen_ids if sid in screens_by_id]
    screenshots = {}
    try:
        result = fetch_screenshot(file_key, figma_ids)
        if isinstance(result, dict):
            screenshots = result
    except TypeError:
        pass
    # Per-screen fallback for any missing from the batch call.
    for sid in screen_ids:
        meta = screens_by_id.get(sid)
        if not meta:
            continue
        figma_id = meta[5]
        if figma_id in screenshots:
            continue
        img = fetch_screenshot(file_key, figma_id)
        if img is not None:
            screenshots[figma_id] = img

    for sid in screen_ids:
        meta = screens_by_id.get(sid)
        if not meta:
            continue
        _, name, device_class, width, height, figma_id, skeleton = meta
        img_bytes = screenshots.get(figma_id)
        if img_bytes is None:
            # No screenshot — skip this screen (caller should log).
            continue
        unclassified = _fetch_unclassified_for_screen(
            conn, sid, target_source=target_source,
        )
        if not unclassified:
            # Nothing to classify on this screen; skip.
            continue
        batch.append({
            "screen_id": sid,
            "name": name,
            "device_class": device_class,
            "width": width,
            "height": height,
            "skeleton": skeleton,
            "image_bytes": img_bytes,
            "unclassified": unclassified,
        })
    return batch


def classify_batch(
    conn: sqlite3.Connection,
    screen_ids: list[int],
    client: Any,
    file_key: str,
    fetch_screenshot: Callable,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 32768,
    target_source: str = "unclassified",
) -> list[dict[str, Any]]:
    """Classify all candidate nodes across a batch of screens in one
    tool-use call. Returns the list of classifications (screen_id +
    node_id + canonical_type + confidence + reason + optional
    cross_screen_evidence). Caller decides whether to persist them.

    ``screen_ids`` is typically a same-group batch (same
    device_class + skeleton_type) of size 1 (per-screen) to ~6
    (cross-screen sweet spot per the 2026-04-19 session).

    ``target_source`` picks the candidate set per
    `_fetch_unclassified_for_screen`: ``"unclassified"`` for
    single-source vision, ``"llm"`` for three-source vision PS + CS
    (classify the same candidates LLM did).
    """
    batch = _build_batch_payload(
        conn, screen_ids, fetch_screenshot, file_key,
        target_source=target_source,
    )
    if not batch:
        return []

    catalog = get_catalog(conn)
    prompt = build_batched_vision_prompt(batch, catalog)

    content: list[dict[str, Any]] = []
    for i, s in enumerate(batch, 1):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(s["image_bytes"]).decode("utf-8"),
            },
        })
    content.append({"type": "text", "text": prompt})

    # max_tokens > ~16K triggers Anthropic's long-request gate,
    # which requires streaming. Use the streaming client and
    # collect the final accumulated message so we keep a single
    # code path for small + large batches.
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        tools=[CLASSIFY_ACROSS_SCREENS_TOOL_SCHEMA],
        tool_choice={
            "type": "tool",
            "name": CLASSIFY_ACROSS_SCREENS_TOOL_SCHEMA["name"],
        },
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()

    results = _extract_classifications_from_response(response)
    if not results:
        # Empty result: dump the response shape so the bake-off /
        # debugger can see what happened. Don't fabricate.
        import os as _os
        if _os.environ.get("DD_CLASSIFY_DEBUG"):
            try:
                stop_reason = getattr(response, "stop_reason", None)
                blocks = [
                    (getattr(b, "type", None), getattr(b, "name", None),
                     (getattr(b, "text", "") or "")[:200] if getattr(b, "type", None) == "text" else None,
                     "input_keys=" + ",".join(list(getattr(b, "input", {}).keys())[:8])
                        if getattr(b, "type", None) == "tool_use" else None)
                    for b in (response.content or [])
                ]
                usage = getattr(response, "usage", None)
                print(
                    f"[debug] empty tool result: stop_reason={stop_reason!r} "
                    f"blocks={blocks} usage={usage}",
                    flush=True,
                )
            except Exception as e:
                print(f"[debug] response introspection failed: {e!r}", flush=True)
    return results


def group_screens_by_skeleton_and_device(
    conn: sqlite3.Connection,
    screen_ids: list[int],
    target_batch_size: int = 5,
) -> list[list[int]]:
    """Group screen_ids into batches by (device_class,
    skeleton_type), each batch up to ``target_batch_size`` screens.

    Groups smaller than ``target_batch_size`` are emitted at their
    natural size (no padding across group boundaries — preserves
    within-batch consistency signal). Groups larger than the
    target are split into consecutive chunks.
    """
    rows = conn.execute(
        """
        SELECT s.id, s.device_class, ss.skeleton_type
        FROM screens s
        LEFT JOIN screen_skeletons ss ON ss.screen_id = s.id
        WHERE s.id IN (%s)
        ORDER BY s.device_class, ss.skeleton_type, s.id
        """ % ",".join("?" * len(screen_ids)),
        screen_ids,
    ).fetchall()

    groups: dict[tuple[str, str], list[int]] = {}
    for sid, device_class, skeleton_type in rows:
        key = (device_class or "", skeleton_type or "")
        groups.setdefault(key, []).append(sid)

    batches: list[list[int]] = []
    for _, sids in sorted(groups.items()):
        for i in range(0, len(sids), target_batch_size):
            batches.append(sids[i:i + target_batch_size])
    return batches
