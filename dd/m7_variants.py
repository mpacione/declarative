"""M7.0.c — variant family derivation from CKR naming patterns.

Dank's design system uses slash-delimited CKR names
(``button/large/translucent``, ``icon/back``, ``nav/top-nav``) where
the first segment is the component family and subsequent segments
are axis values. This module parses that pattern and writes one
``component_variants`` row per master with ``properties`` JSON
capturing the axis → value map.

When a family has mixed path depth (``button/white`` alongside
``button/large/translucent``), each depth is treated as its own
variant-shape group within the family. The LLM labels the axes
for each group via Claude Haiku.

Falls back cleanly:
- Single-segment CKR names (``New Folder``, ``_Key``) → one
  variant row with ``properties = {}`` (singleton family).
- Paths whose components row doesn't exist (Step 1 orphan-skip)
  → no variant row written.

Public entry: ``derive_variants_from_ckr(conn, *, llm_invoker)``.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any, Callable, Optional


_VARIANT_TOOL_SCHEMA = {
    "name": "emit_variant_axes",
    "description": (
        "Given a list of variant-path segment-tuples for ONE "
        "component family, emit one axis-name per position. Axis "
        "names are snake_case and describe the CONCEPT encoded "
        "at that position (size / style / state / layout / "
        "orientation, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "axis_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "One axis name per path-segment position, in "
                    "order. Length MUST match the path depth."
                ),
            },
        },
        "required": ["axis_names"],
    },
}


def parse_ckr_paths(
    ckr_names: list[str],
) -> dict[str, list[tuple[str, ...]]]:
    """Group CKR names by family root, return {family: [(seg, ...)]}.

    The first slash-delimited segment is the family; remaining
    segments are the variant path. Names without a slash become a
    singleton family with empty path tuple.
    """
    groups: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for name in ckr_names:
        if "/" in name:
            head, *rest = name.split("/")
            groups[head].append(tuple(rest))
        else:
            groups[name].append(())
    return dict(groups)


def _label_axes(
    family: str,
    paths: list[tuple[str, ...]],
    llm_invoker: Callable[[str], list[str]],
    *,
    depth: int,
) -> list[str]:
    """Ask the LLM for axis names for a uniform-depth path group.

    The prompt shows the family + all paths at that depth and asks
    for one axis name per position. Returns a list of ``depth``
    snake_case axis names (or ``["variant_N", ...]`` fallbacks if
    the LLM returns a malformed response).
    """
    if depth == 0:
        return []

    # Build a compact summary of the paths for the prompt.
    seg_samples: list[list[str]] = [[] for _ in range(depth)]
    for path in paths:
        for i, seg in enumerate(path[:depth]):
            if seg not in seg_samples[i]:
                seg_samples[i].append(seg)

    lines = [
        f"Family: {family!r}",
        f"Each variant path has {depth} axis positions.",
        f"Sample segments per position:",
    ]
    for i, samples in enumerate(seg_samples):
        lines.append(f"  position {i}: [{', '.join(samples[:6])}]")
    lines.append("")
    lines.append(
        "Emit one axis_name per position (in order). Use snake_case. "
        "Examples: size / style / state / orientation / density."
    )
    prompt = "\n".join(lines)

    try:
        axis_names = llm_invoker(prompt)
    except Exception:
        axis_names = []
    if (
        not isinstance(axis_names, list)
        or len(axis_names) != depth
        or not all(isinstance(n, str) and n for n in axis_names)
    ):
        # Fallback: synthetic names.
        return [f"variant_{i}" for i in range(depth)]
    return [str(n).strip() for n in axis_names]


def _figma_id_for_ckr(
    conn: sqlite3.Connection, ckr_name: str,
) -> Optional[str]:
    """Look up the master's figma_node_id from CKR by full name."""
    row = conn.execute(
        "SELECT figma_node_id FROM component_key_registry "
        "WHERE name = ? LIMIT 1",
        (ckr_name,),
    ).fetchone()
    return row[0] if row and row[0] else None


def derive_variants_from_ckr(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    llm_invoker: Optional[Callable[[str], list[str]]] = None,
) -> dict[str, Any]:
    """Populate ``component_variants`` from CKR naming patterns.

    Groups CKR entries by family root, asks the LLM to label each
    uniform-depth sub-group's axes, then writes one variant row
    per master with ``properties`` = {axis_name: value} mapping.

    Returns stats: ``families``, ``variants_inserted``, ``skipped
    _no_components_row``, ``singletons``, plus per-family summaries
    under ``per_family``.
    """
    # 1. Load all CKR names with resolved figma_node_id (remote-
    # library masters without one were skipped in Step 1 so we
    # can't write a variant row for them either).
    ckr_rows = conn.execute(
        "SELECT name FROM component_key_registry "
        "WHERE figma_node_id IS NOT NULL"
    ).fetchall()
    names = [r[0] for r in ckr_rows]

    groups = parse_ckr_paths(names)

    stats: dict[str, Any] = {
        "families": len(groups),
        "variants_inserted": 0,
        "skipped_no_components_row": 0,
        "skipped_existing": 0,
        "singletons": 0,
        "per_family": {},
    }

    for family, paths in sorted(groups.items()):
        # Bucket paths by depth — each depth is its own axis group.
        by_depth: dict[int, list[tuple[str, ...]]] = defaultdict(list)
        for path in paths:
            by_depth[len(path)].append(path)

        family_summary: dict[str, Any] = {
            "paths": len(paths),
            "depths": sorted(by_depth.keys()),
            "rows_written": 0,
        }

        for depth, paths_at_depth in sorted(by_depth.items()):
            if depth == 0:
                # Singleton family — one master with empty path.
                axis_names: list[str] = []
                stats["singletons"] += len(paths_at_depth)
            else:
                if llm_invoker is None:
                    # No LLM available → fallback names.
                    axis_names = [f"variant_{i}" for i in range(depth)]
                else:
                    axis_names = _label_axes(
                        family, paths_at_depth, llm_invoker,
                        depth=depth,
                    )

            for path in paths_at_depth:
                ckr_name = (
                    family if depth == 0
                    else family + "/" + "/".join(path)
                )
                figma_id = _figma_id_for_ckr(conn, ckr_name)
                if not figma_id:
                    continue
                comp_row = conn.execute(
                    "SELECT id FROM components "
                    "WHERE file_id = ? AND figma_node_id = ?",
                    (file_id, figma_id),
                ).fetchone()
                if comp_row is None:
                    stats["skipped_no_components_row"] += 1
                    continue
                component_id = comp_row[0]
                props = {
                    axis_names[i]: path[i] for i in range(depth)
                }
                try:
                    conn.execute(
                        "INSERT INTO component_variants "
                        "(component_id, figma_node_id, name, "
                        " properties) VALUES (?, ?, ?, ?)",
                        (
                            component_id, figma_id, ckr_name,
                            json.dumps(props),
                        ),
                    )
                    stats["variants_inserted"] += 1
                    family_summary["rows_written"] += 1
                except sqlite3.IntegrityError:
                    stats["skipped_existing"] += 1

            family_summary[f"axis_names_d{depth}"] = axis_names

        stats["per_family"][family] = family_summary

    conn.commit()
    return stats


def make_anthropic_axis_invoker(client: Any):
    """Production LLM invoker for _label_axes."""
    def _invoke(prompt: str) -> list[str]:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            tools=[_VARIANT_TOOL_SCHEMA],
            tool_choice={
                "type": "tool", "name": _VARIANT_TOOL_SCHEMA["name"],
            },
            messages=[{"role": "user", "content": prompt}],
        )
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != _VARIANT_TOOL_SCHEMA["name"]:
                continue
            inp = getattr(block, "input", None)
            if isinstance(inp, dict):
                axes = inp.get("axis_names")
                if isinstance(axes, list):
                    return [str(a) for a in axes]
        return []
    return _invoke
