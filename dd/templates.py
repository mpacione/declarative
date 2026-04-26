"""Component template extraction from classified instances (Phase 4a).

Extracts the most common structure + visual defaults per catalog type
from the DB. Templates are used by the renderer for Mode 1 (instance
path via componentKey) and Mode 2 (frame construction from structure).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any

_TEMPLATE_FIELDS = [
    "layout_mode", "width", "height",
    "padding_top", "padding_right", "padding_bottom", "padding_left",
    "item_spacing", "primary_align", "counter_align",
    "corner_radius", "fills", "strokes", "effects", "opacity",
    "layout_sizing_h", "layout_sizing_v",
    "clips_content", "layout_wrap",
    "min_width", "max_width", "min_height", "max_height",
    "font_family", "font_size", "font_weight", "font_style",
    "line_height", "letter_spacing", "text_align",
]


def _mode_value(values: list[Any]) -> Any:
    """Return the most common value in a list (statistical mode)."""
    if not values:
        return None
    counter = Counter(
        tuple(v) if isinstance(v, list) else v
        for v in values
    )
    return counter.most_common(1)[0][0]


def compute_mode_template(instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the mode (most common value) for each field across instances.

    Returns a template dict with structure + visual fields, instance_count,
    and representative_node_id (first instance matching the mode values).
    """
    if not instances:
        return {}

    template: dict[str, Any] = {"instance_count": len(instances)}

    for field in _TEMPLATE_FIELDS:
        values = [inst.get(field) for inst in instances if field in inst]
        template[field] = _mode_value(values) if values else None

    node_ids = [inst.get("node_id") for inst in instances if inst.get("node_id")]
    mode_width = template.get("width")
    mode_height = template.get("height")

    representative = node_ids[0] if node_ids else None
    for inst in instances:
        if inst.get("width") == mode_width and inst.get("height") == mode_height:
            representative = inst.get("node_id", representative)
            break

    template["representative_node_id"] = representative
    return template


_MIN_CHILD_FREQUENCY = 0.1


def build_component_key_registry(conn: sqlite3.Connection) -> int:
    """Build a unified component_key → figma_node_id registry from the nodes table.

    Phase E #2 fix (2026-04-26): primary lookup is now via
    ``nodes.component_figma_id`` — every INSTANCE row already carries
    its master's figma node id (captured by the plugin extractor's
    ``getMainComponentAsync().id`` at extract_screens.py:276). This
    avoids the previous name-based fallback that needed COMPONENT
    nodes in `nodes` (Nouns has 0; the Components page isn't walked
    by extract_top_level_frames).

    Codex 2026-04-26 (gpt-5.5 high reasoning) review: "the current
    code already discovers the authoritative mapping at extraction
    time... use key lookup as fallback, not primary path."

    Resolution order:
    1. Most-frequent ``nodes.component_figma_id`` for this
       component_key (the new primary path).
    2. Name-based lookup against ``nodes WHERE node_type='COMPONENT'``
       (legacy: works when the Components page IS extracted).
    3. Name-based lookup against ``components`` table (legacy).
    4. NULL — downstream consumers handle gracefully (sticker_sheet
       and variants both check for None).

    Returns the number of registry entries created.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS component_key_registry ("
        "component_key TEXT PRIMARY KEY, "
        "figma_node_id TEXT, "
        "name TEXT NOT NULL, "
        "instance_count INTEGER)"
    )
    conn.execute("DELETE FROM component_key_registry")

    # Phase E #2: include component_figma_id in the per-key aggregate.
    # Use MIN to pick a deterministic representative when an INSTANCE
    # appears multiple times (all its rows agree by definition since
    # they're the same component_key → same master).
    keys = conn.execute(
        "SELECT n.component_key, "
        "  MIN(TRIM(n.name)) AS inst_name, "
        "  COUNT(*) AS cnt, "
        "  MIN(n.component_figma_id) AS master_fid "
        "FROM nodes n "
        "WHERE n.component_key IS NOT NULL "
        "GROUP BY n.component_key"
    ).fetchall()

    count = 0
    for row in keys:
        ck = row[0]
        inst_name = (row[1] or "").strip()
        inst_count = row[2]
        master_fid = row[3]  # may be None on older DBs / pre-migration

        if not inst_name:
            continue

        figma_node_id = None

        # Phase E #2 primary path: instance-resolved master id.
        if master_fid:
            figma_node_id = master_fid

        # Legacy fallback 1: name match against COMPONENT nodes (works
        # when extraction does walk a Components page; today's
        # extract_top_level_frames doesn't, but tests + future
        # extension may populate).
        if not figma_node_id:
            master = conn.execute(
                "SELECT figma_node_id FROM nodes "
                "WHERE node_type = 'COMPONENT' AND TRIM(name) = ? LIMIT 1",
                (inst_name,),
            ).fetchone()
            if master:
                figma_node_id = master[0]

        # Legacy fallback 2: name match against `components` table.
        if not figma_node_id:
            comp = conn.execute(
                "SELECT figma_node_id FROM components WHERE TRIM(name) = ? LIMIT 1",
                (inst_name,),
            ).fetchone()
            if comp:
                figma_node_id = comp[0]

        conn.execute(
            "INSERT OR REPLACE INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES (?, ?, ?, ?)",
            (ck, figma_node_id, inst_name, inst_count),
        )
        count += 1

    conn.commit()
    return count


def extract_child_composition(
    conn: sqlite3.Connection,
    file_id: int,
) -> dict[str, list[dict[str, Any]]]:
    """Extract child composition patterns from classified instance data.

    Analyzes parent→child relationships in screen_component_instances to
    discover what children typically appear inside each parent type. For
    each parent canonical_type, returns the statistical mode of child
    counts per child type, the most common child component_key, and
    the frequency (fraction of parent instances containing that child).

    Filters out children appearing in fewer than 10% of parent instances.
    """
    rows = conn.execute(
        "SELECT p.canonical_type AS parent_type, "
        "p.id AS parent_sci_id, "
        "c.canonical_type AS child_type, "
        "n_child.component_key AS child_key "
        "FROM screen_component_instances c "
        "JOIN screen_component_instances p ON c.parent_instance_id = p.id "
        "JOIN nodes n_child ON c.node_id = n_child.id "
        "JOIN nodes n_parent ON p.node_id = n_parent.id "
        "JOIN screens s ON n_parent.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen'",
        (file_id,),
    ).fetchall()

    parent_instances: dict[str, set[int]] = defaultdict(set)
    child_counts: dict[str, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    child_keys: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))

    for r in rows:
        pt = r[0]
        pid = r[1]
        ct = r[2]
        ck = r[3]

        parent_instances[pt].add(pid)
        child_counts[pt][pid][ct] += 1
        if ck:
            child_keys[pt][ct][ck] += 1

    result: dict[str, list[dict[str, Any]]] = {}

    for parent_type, pids in parent_instances.items():
        total_parents = len(pids)
        per_child_type: dict[str, list[int]] = defaultdict(list)

        for pid in pids:
            for child_type, count in child_counts[parent_type][pid].items():
                per_child_type[child_type].append(count)

        children: list[dict[str, Any]] = []
        for child_type, counts in per_child_type.items():
            frequency = len(counts) / total_parents
            if frequency < _MIN_CHILD_FREQUENCY:
                continue

            count_mode = Counter(counts).most_common(1)[0][0]

            best_key = None
            key_counter = child_keys[parent_type].get(child_type)
            if key_counter:
                best_key = key_counter.most_common(1)[0][0]

            figma_id = None
            if best_key:
                reg_row = conn.execute(
                    "SELECT figma_node_id FROM component_key_registry "
                    "WHERE component_key = ?",
                    (best_key,),
                ).fetchone()
                if reg_row:
                    figma_id = reg_row[0]

            children.append({
                "child_type": child_type,
                "count_mode": count_mode,
                "component_key": best_key,
                "component_figma_id": figma_id,
                "frequency": round(frequency, 3),
            })

        children.sort(key=lambda c: -c["frequency"])
        if children:
            result[parent_type] = children

    return result


def extract_templates(conn: sqlite3.Connection, file_id: int) -> int:
    """Extract component templates from classified instances.

    Groups instances by catalog_type and component_key, computes mode
    templates, and inserts into the component_templates table.

    Returns the number of templates created.
    """
    _ensure_font_columns(conn)
    conn.execute("DELETE FROM component_templates")

    cursor = conn.execute(
        "SELECT DISTINCT sci.canonical_type "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON sci.node_id = n.id "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen'",
        (file_id,),
    )
    catalog_types = [row[0] for row in cursor.fetchall()]

    composition = extract_child_composition(conn, file_id)

    template_count = 0

    for catalog_type in catalog_types:
        instances = _query_instances(conn, file_id, catalog_type)
        if not instances:
            continue

        slots_json = _serialize_composition(composition.get(catalog_type))

        keyed = [i for i in instances if i.get("component_key")]
        unkeyed = [i for i in instances if not i.get("component_key")]

        if keyed:
            groups: dict[str, list[dict]] = {}
            for inst in keyed:
                key = inst["component_key"]
                if key not in groups:
                    groups[key] = []
                groups[key].append(inst)

            for component_key, group in groups.items():
                template = compute_mode_template(group)
                variant = _variant_from_key(group)
                _insert_template(conn, catalog_type, variant, component_key, template, slots_json)
                template_count += 1

        if unkeyed:
            template = compute_mode_template(unkeyed)
            _insert_template(conn, catalog_type, None, None, template, slots_json)
            template_count += 1

    screen_template = _extract_screen_template(conn, file_id)
    if screen_template:
        _insert_template(conn, "screen", None, None, screen_template)
        template_count += 1

    conn.commit()
    return template_count


def _extract_screen_template(
    conn: sqlite3.Connection, file_id: int,
) -> dict[str, Any] | None:
    """Extract a template from screen-level frames (depth=0).

    Screen frames are not classified instances — they're the container.
    This captures their fills, effects, and dimensions as a "screen" template.
    """
    instances = conn.execute(
        "SELECT n.id as node_id, n.name, "
        "n.layout_mode, n.width, n.height, "
        "n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.primary_align, n.counter_align, "
        "n.corner_radius, n.fills, n.strokes, n.effects, n.opacity, "
        "n.layout_sizing_h, n.layout_sizing_v, "
        "n.clips_content, n.layout_wrap, "
        "n.min_width, n.max_width, n.min_height, n.max_height "
        "FROM nodes n "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen' AND n.depth = 0",
        (file_id,),
    ).fetchall()

    if not instances:
        return None

    columns = [desc[0] for desc in conn.execute(
        "SELECT n.id as node_id, n.name, "
        "n.layout_mode, n.width, n.height, "
        "n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.primary_align, n.counter_align, "
        "n.corner_radius, n.fills, n.strokes, n.effects, n.opacity, "
        "n.layout_sizing_h, n.layout_sizing_v, "
        "n.clips_content, n.layout_wrap, "
        "n.min_width, n.max_width, n.min_height, n.max_height "
        "FROM nodes n LIMIT 0"
    ).description]

    dicts = [dict(zip(columns, row)) for row in instances]
    return compute_mode_template(dicts)


_FONT_COLUMNS = [
    ("font_family", "TEXT"),
    ("font_size", "REAL"),
    ("font_weight", "INTEGER"),
    ("font_style", "TEXT"),
    ("line_height", "TEXT"),
    ("letter_spacing", "TEXT"),
    ("text_align", "TEXT"),
]


def _ensure_font_columns(conn: sqlite3.Connection) -> None:
    """Add font columns to component_templates if missing (schema migration)."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(component_templates)").fetchall()}
    for col_name, col_type in _FONT_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE component_templates ADD COLUMN {col_name} {col_type}")


def query_templates(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Fetch all templates keyed by catalog_type.

    Returns dict mapping catalog_type to list of template dicts.
    """
    _ensure_font_columns(conn)

    has_registry = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='component_key_registry'"
    ).fetchone()

    _SELECT_COLS = (
        "ct.catalog_type, ct.variant, ct.component_key, ct.representative_node_id, "
        "ct.instance_count, ct.layout_mode, ct.width, ct.height, "
        "ct.padding_top, ct.padding_right, ct.padding_bottom, ct.padding_left, "
        "ct.item_spacing, ct.primary_align, ct.counter_align, ct.corner_radius, "
        "ct.fills, ct.strokes, ct.effects, ct.opacity, ct.slots, "
        "ct.layout_sizing_h, ct.layout_sizing_v, "
        "ct.clips_content, ct.layout_wrap, "
        "ct.min_width, ct.max_width, ct.min_height, ct.max_height, "
        "ct.font_family, ct.font_size, ct.font_weight, ct.font_style, "
        "ct.line_height, ct.letter_spacing, ct.text_align"
    )

    if has_registry:
        cursor = conn.execute(
            f"SELECT {_SELECT_COLS}, "
            "ckr.figma_node_id as component_figma_id "
            "FROM component_templates ct "
            "LEFT JOIN component_key_registry ckr ON ct.component_key = ckr.component_key "
            "ORDER BY ct.catalog_type, ct.variant"
        )
    else:
        cursor = conn.execute(
            f"SELECT {_SELECT_COLS}, "
            "c.figma_node_id as component_figma_id "
            "FROM component_templates ct "
            "LEFT JOIN components c ON ct.variant = c.name "
            "ORDER BY ct.catalog_type, ct.variant"
        )
    columns = [desc[0] for desc in cursor.description]
    result: dict[str, list[dict[str, Any]]] = {}

    for row in cursor.fetchall():
        entry = dict(zip(columns, row))

        slots_raw = entry.get("slots")
        if slots_raw and slots_raw != "null":
            try:
                entry["children_composition"] = json.loads(slots_raw)
            except (json.JSONDecodeError, TypeError):
                entry["children_composition"] = []
        else:
            entry["children_composition"] = []

        cat_type = entry["catalog_type"]
        if cat_type not in result:
            result[cat_type] = []
        result[cat_type].append(entry)

    return result


def _query_instances(
    conn: sqlite3.Connection, file_id: int, catalog_type: str,
) -> list[dict[str, Any]]:
    """Fetch all instances of a catalog type with structure + visual props."""
    cursor = conn.execute(
        "SELECT n.id as node_id, n.name, n.component_key, "
        "n.layout_mode, n.width, n.height, "
        "n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.primary_align, n.counter_align, "
        "n.corner_radius, n.fills, n.strokes, n.effects, n.opacity, "
        "n.layout_sizing_h, n.layout_sizing_v, "
        "n.clips_content, n.layout_wrap, "
        "n.min_width, n.max_width, n.min_height, n.max_height, "
        "n.font_family, n.font_size, n.font_weight, n.font_style, "
        "n.line_height, n.letter_spacing, n.text_align "
        "FROM nodes n "
        "JOIN screen_component_instances sci ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen' "
        "AND sci.canonical_type = ?",
        (file_id, catalog_type),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _variant_from_key(group: list[dict[str, Any]]) -> str:
    """Derive a variant name from the most common node name in a group."""
    names = [inst.get("name", "") for inst in group]
    if not names:
        return "default"
    counter = Counter(names)
    return counter.most_common(1)[0][0]


def _serialize_composition(
    children: list[dict[str, Any]] | None,
) -> str | None:
    """Serialize composition children list to JSON for the slots column."""
    if not children:
        return None
    return json.dumps(children)


def _insert_template(
    conn: sqlite3.Connection,
    catalog_type: str,
    variant: str | None,
    component_key: str | None,
    template: dict[str, Any],
    slots_json: str | None = None,
) -> None:
    """Insert or replace a template row."""
    conn.execute(
        "INSERT OR REPLACE INTO component_templates "
        "(catalog_type, variant, component_key, representative_node_id, instance_count, "
        "layout_mode, width, height, padding_top, padding_right, padding_bottom, padding_left, "
        "item_spacing, primary_align, counter_align, corner_radius, "
        "fills, strokes, effects, opacity, slots, "
        "layout_sizing_h, layout_sizing_v, clips_content, layout_wrap, "
        "min_width, max_width, min_height, max_height, "
        "font_family, font_size, font_weight, font_style, "
        "line_height, letter_spacing, text_align) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            catalog_type, variant, component_key,
            template.get("representative_node_id"),
            template.get("instance_count"),
            template.get("layout_mode"),
            template.get("width"), template.get("height"),
            template.get("padding_top"), template.get("padding_right"),
            template.get("padding_bottom"), template.get("padding_left"),
            template.get("item_spacing"),
            template.get("primary_align"), template.get("counter_align"),
            template.get("corner_radius"),
            template.get("fills"), template.get("strokes"),
            template.get("effects"), template.get("opacity"),
            slots_json,
            template.get("layout_sizing_h"), template.get("layout_sizing_v"),
            template.get("clips_content"), template.get("layout_wrap"),
            template.get("min_width"), template.get("max_width"),
            template.get("min_height"), template.get("max_height"),
            template.get("font_family"), template.get("font_size"),
            template.get("font_weight"), template.get("font_style"),
            template.get("line_height"), template.get("letter_spacing"),
            template.get("text_align"),
        ),
    )
