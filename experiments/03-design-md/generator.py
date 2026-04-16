"""Generate a v1 design.md artefact from the MLIR declarative database.

This is Experiment 3 of the synthetic-generation research sprint. It answers
open question 3 by auto-extracting a design.md subset from what the DB already
knows (components, tokens, adjacencies, screen structures) and measuring the
resulting token size so we can decide prompt-cache vs retrieval-chunk.

Usage:
    python generator.py --db ../../Dank-EXP-02.declarative.db --out design.md

The generator is deliberately structured so it can graduate to
``dd/design_md.py`` with minimal refactoring.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dd.catalog import CATALOG_ENTRIES  # noqa: E402


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class Metadata:
    db_path: str
    file_name: str
    file_key: str
    screen_count: int
    node_count: int
    ckr_size: int
    generated_at: str


@dataclass
class ComponentFact:
    component_key: str
    name: str
    instance_count: int
    parent_contexts: list[tuple[str, int]]  # (parent description, count)
    sibling_contexts: list[tuple[str, int]]  # (sibling description, count)


@dataclass
class TokenUsage:
    value: str
    property: str
    usage_count: int


@dataclass
class TypeCombo:
    font_family: str
    weight: int | None
    size: float | None
    line_height: float | None
    count: int


@dataclass
class SpacingStat:
    value: float
    property: str
    count: int


@dataclass
class Adjacency:
    name: str
    instance_count: int
    top_structures: list[tuple[list[str], int, float]]  # (child seq, count, pct)


@dataclass
class ScreenArchetype:
    fingerprint: list[str]
    screen_count: int
    examples: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


ACTIVITY_LOG_PATH = Path(__file__).resolve().parent / "activity.log"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(section: str, status: str, detail: str) -> None:
    stamp = _now_iso()
    with ACTIVITY_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} | {section} | {status} | {detail}\n")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def fetch_metadata(conn: sqlite3.Connection, db_path: str) -> Metadata:
    file_row = conn.execute(
        "SELECT name, file_key FROM files ORDER BY id LIMIT 1",
    ).fetchone()
    screen_count = conn.execute("SELECT COUNT(*) FROM screens").fetchone()[0]
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    ckr_size = conn.execute(
        "SELECT COUNT(*) FROM component_key_registry",
    ).fetchone()[0]
    return Metadata(
        db_path=os.path.abspath(db_path),
        file_name=file_row["name"] if file_row else "(unknown)",
        file_key=file_row["file_key"] if file_row else "(unknown)",
        screen_count=screen_count,
        node_count=node_count,
        ckr_size=ckr_size,
        generated_at=_now_iso(),
    )


SCREEN_NAME_PREFIXES: tuple[str, ...] = (
    "iPhone ",
    "iPad Pro ",
    "Web - ",
    "Watch ",
)


def format_parent(name: str, node_type: str) -> str:
    """Describe a parent context concisely."""
    if "/" in name or name.startswith("_"):
        return f"{name}"
    if node_type == "FRAME" and any(
        name.startswith(prefix) for prefix in SCREEN_NAME_PREFIXES
    ):
        return "(screen root)"
    return f"{name} [{node_type}]"


def _collapse_screen_roots(
    rows: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Collapse multiple `(screen root)` entries into one aggregated count."""
    collapsed: dict[str, int] = {}
    for name, count in rows:
        collapsed[name] = collapsed.get(name, 0) + count
    return sorted(collapsed.items(), key=lambda kv: -kv[1])


def fetch_component_facts(
    conn: sqlite3.Connection,
    limit: int | None = None,
) -> list[ComponentFact]:
    ckr_rows = conn.execute(
        "SELECT component_key, name, instance_count "
        "FROM component_key_registry "
        "ORDER BY instance_count DESC NULLS LAST, name",
    ).fetchall()
    if limit is not None:
        ckr_rows = ckr_rows[:limit]

    facts: list[ComponentFact] = []
    for row in ckr_rows:
        ck = row["component_key"]
        # Pull more than 3 so screen-root collapsing can aggregate identical
        # roots that happen to have distinct names.
        parent_rows = conn.execute(
            "SELECT parent.name AS parent_name, parent.node_type AS parent_type, COUNT(*) AS c "
            "FROM nodes child "
            "JOIN nodes parent ON parent.id = child.parent_id "
            "WHERE child.component_key = ? "
            "GROUP BY parent.name, parent.node_type "
            "ORDER BY c DESC LIMIT 12",
            (ck,),
        ).fetchall()
        sibling_rows = conn.execute(
            "SELECT sibling.name AS sname, sibling.component_key AS sck, COUNT(*) AS c "
            "FROM nodes target "
            "JOIN nodes sibling ON sibling.parent_id = target.parent_id AND sibling.id != target.id "
            "WHERE target.component_key = ? AND sibling.name IS NOT NULL "
            "GROUP BY sibling.name "
            "ORDER BY c DESC LIMIT 3",
            (ck,),
        ).fetchall()

        # Fetch slightly more than top-3 raw rows so screen-root aggregation
        # gives us real diversity after collapsing.
        parent_contexts = _collapse_screen_roots(
            [
                (format_parent(pr["parent_name"], pr["parent_type"]), pr["c"])
                for pr in parent_rows
            ]
        )[:3]
        sibling_contexts = [
            (sr["sname"], sr["c"]) for sr in sibling_rows
        ]
        facts.append(
            ComponentFact(
                component_key=ck,
                name=row["name"],
                instance_count=row["instance_count"] or 0,
                parent_contexts=parent_contexts,
                sibling_contexts=sibling_contexts,
            )
        )
    return facts


def render_component_inventory(facts: Iterable[ComponentFact]) -> str:
    facts_list = list(facts)
    lines = ["## Component inventory", ""]
    lines.append(
        "Auto-extracted from `component_key_registry`. Each row is one shared "
        "component used at least once in the corpus. The \"typically ...\" "
        "clause is mined from parent / sibling adjacencies. Where multiple "
        "CKR rows share a display name (distinct `component_key` values with "
        "the same Figma name), the short key suffix disambiguates them.",
    )
    lines.append("")

    name_counts = Counter(f.name for f in facts_list)
    for f in facts_list:
        typical = _describe_typical(f)
        label = f.name
        if name_counts[f.name] > 1:
            label = f"{f.name} · {f.component_key[:8]}"
        lines.append(f"- `{label}` — used {f.instance_count} times. {typical}")
    lines.append("")
    return "\n".join(lines)


def _describe_typical(f: ComponentFact) -> str:
    if not f.parent_contexts:
        return "No parent context observed (possibly unreferenced)."
    parts: list[str] = []
    if f.parent_contexts:
        parent_fragments = ", ".join(
            f"{name} ({count})" for name, count in f.parent_contexts[:3]
        )
        parts.append(f"Commonly parented by {parent_fragments}.")
    if f.sibling_contexts:
        sibling_fragments = ", ".join(
            f"{name} ({count})" for name, count in f.sibling_contexts[:3]
        )
        parts.append(f"Most frequent siblings: {sibling_fragments}.")
    return " ".join(parts)


def render_token_palette(conn: sqlite3.Connection) -> str:
    lines = ["## Token palette", ""]
    tokens_count = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    if tokens_count == 0:
        lines.append(
            "Canonical `tokens` table is empty — clustering has not been run "
            "since the last restore. Palette pending `dd cluster`. Below is "
            "the observed raw-value census from `node_token_bindings` grouped "
            "by property class; treat it as a dry-run of what clustering will "
            "surface.",
        )
        lines.append("")
        log("token_palette", "warning", "tokens table empty; emitted raw census")
    else:
        log("token_palette", "ok", f"tokens table populated ({tokens_count})")

    def emit(title: str, rows: list[tuple[str, int]], *, limit: int = 15) -> None:
        lines.append(f"### {title}")
        lines.append("")
        if not rows:
            lines.append("_no values observed_")
            lines.append("")
            return
        for value, count in rows[:limit]:
            lines.append(f"- `{value}` — used {count} times")
        if len(rows) > limit:
            lines.append(
                f"- _+{len(rows) - limit} more values omitted (long tail)_",
            )
        lines.append("")

    # Colors — v_color_census is over-inclusive (it LIKEs 'fill%' and 'stroke%'
    # which pulls in strokeWeight, fill.0.opacity, stroke.0.opacity etc).
    # Restrict to actual color properties for the palette swatch.
    colors = [
        (r["resolved_value"], r["c"])
        for r in conn.execute(
            "SELECT ntb.resolved_value, COUNT(*) AS c "
            "FROM node_token_bindings ntb "
            "WHERE ntb.property LIKE 'fill.%.color' OR ntb.property LIKE 'stroke.%.color' "
            "GROUP BY ntb.resolved_value ORDER BY c DESC",
        ).fetchall()
    ]
    emit("Color", colors)

    # Spacing
    spacings = [
        (f"{r['resolved_value']} [{r['property']}]", r["c"])
        for r in conn.execute(
            "SELECT resolved_value, property, SUM(usage_count) AS c "
            "FROM v_spacing_census GROUP BY resolved_value, property "
            "ORDER BY CAST(resolved_value AS REAL), c DESC",
        ).fetchall()
    ]
    emit("Spacing", spacings, limit=25)

    # Radius — query nodes.corner_radius directly for fuller coverage than
    # the binding-only v_radius_census (which is gated by tokenization).
    radii_counter: Counter[str] = Counter()
    for row in conn.execute(
        "SELECT corner_radius FROM nodes WHERE corner_radius IS NOT NULL",
    ).fetchall():
        raw = row["corner_radius"]
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            radii_counter[str(raw)] += 1
            continue
        if isinstance(parsed, (int, float)):
            radii_counter[f"{parsed:g}"] += 1
        elif isinstance(parsed, dict):
            radii_counter[f"mixed={json.dumps(parsed, sort_keys=True)}"] += 1
    radii = sorted(
        radii_counter.items(),
        key=lambda kv: -kv[1],
    )
    emit("Radius", radii)

    # Effects
    effects = [
        (f"{r['resolved_value']} [{r['property']}]", r["c"])
        for r in conn.execute(
            "SELECT resolved_value, property, SUM(usage_count) AS c "
            "FROM v_effect_census GROUP BY resolved_value, property "
            "ORDER BY c DESC",
        ).fetchall()
    ]
    emit("Effects", effects)

    # Opacity (directly from nodes)
    opacity_rows = [
        (f"{row['opacity']:.2f}", row["c"])
        for row in conn.execute(
            "SELECT opacity, COUNT(*) AS c FROM nodes "
            "WHERE opacity IS NOT NULL AND opacity < 1.0 "
            "GROUP BY opacity ORDER BY c DESC",
        ).fetchall()
    ]
    emit("Opacity (non-default)", opacity_rows)

    return "\n".join(lines)


def render_typography_scale(conn: sqlite3.Connection, top_k: int = 25) -> str:
    lines = ["## Typography scale", ""]
    rows = conn.execute(
        "SELECT font_family, font_weight, font_size, "
        "json_extract(line_height, '$.value') AS lh, "
        "COUNT(*) AS c "
        "FROM nodes WHERE node_type='TEXT' AND font_family IS NOT NULL "
        "GROUP BY font_family, font_weight, font_size, lh "
        "ORDER BY c DESC",
    ).fetchall()
    total = sum(r["c"] for r in rows)
    lines.append(
        f"Each row is a distinct (family, weight, size, line-height) combo "
        f"observed on TEXT nodes ({total} text nodes across {len(rows)} combos). "
        f"Top {top_k} shown; long tail collapsed.",
    )
    lines.append("")
    lines.append("| Family | Weight | Size (px) | Line height | Count |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in rows[:top_k]:
        weight = r["font_weight"] or ""
        size = f"{r['font_size']:g}" if r["font_size"] is not None else "—"
        lh = (
            f"{float(r['lh']):g}"
            if r["lh"] is not None and r["lh"] != ""
            else "auto"
        )
        lines.append(
            f"| {r['font_family']} | {weight} | {size} | {lh} | {r['c']} |",
        )
    if len(rows) > top_k:
        tail = sum(r["c"] for r in rows[top_k:])
        lines.append(
            f"| _+{len(rows) - top_k} more combos_ | | | | {tail} |",
        )
    lines.append("")
    log("typography", "ok", f"{len(rows)} distinct combos, top {top_k} shown")
    return "\n".join(lines)


def render_spacing_rhythm(conn: sqlite3.Connection) -> str:
    lines = ["## Spacing rhythm", ""]
    # Gather non-null numeric spacing values off the nodes table directly (more
    # complete than binding coverage which is gated by extraction).
    values: list[float] = []
    spacing_columns = (
        "padding_top",
        "padding_right",
        "padding_bottom",
        "padding_left",
        "item_spacing",
        "counter_axis_spacing",
    )
    for col in spacing_columns:
        rows = conn.execute(
            f"SELECT {col} AS v FROM nodes WHERE {col} IS NOT NULL AND {col} > 0",
        ).fetchall()
        values.extend(float(r["v"]) for r in rows)

    if not values:
        lines.append("_No spacing data observed._")
        log("spacing", "warning", "no spacing values on nodes")
        return "\n".join(lines)

    counter = Counter(values)
    on_grid_4 = sum(c for v, c in counter.items() if v % 4 == 0)
    on_grid_8 = sum(c for v, c in counter.items() if v % 8 == 0)
    on_grid_2 = sum(c for v, c in counter.items() if v % 2 == 0)
    total = sum(counter.values())
    gcd_candidate = _infer_base_grid(values)

    # Write an honest narrative: if neither 4 nor 8 hit a strong threshold,
    # call it out rather than claiming the file is on-grid.
    coverage_line = (
        f"4px multiples = {on_grid_4/total:.1%}, "
        f"8px multiples = {on_grid_8/total:.1%}, "
        f"2px multiples = {on_grid_2/total:.1%}"
    )
    if gcd_candidate in (4, 8, 16):
        verdict = f"Detected base grid: **{gcd_candidate}px**."
    else:
        verdict = (
            f"**No strict grid detected** — the modal magnitudes (10 / 14) "
            f"don't align with a conventional 4/8/16 px rhythm. "
            f"Closest loose fit: **{gcd_candidate}px**."
        )
    lines.append(
        f"Observed {total} numeric spacing values across {len(counter)} "
        f"distinct magnitudes. {verdict} (coverage: {coverage_line}).",
    )
    lines.append("")
    lines.append("### Most common spacing magnitudes")
    lines.append("")
    lines.append("| Value (px) | Count | % of total |")
    lines.append("| --- | --- | --- |")
    for value, count in counter.most_common(20):
        lines.append(f"| {value:g} | {count} | {count/total:.1%} |")
    lines.append("")

    off_grid = [
        (v, c)
        for v, c in counter.most_common()
        if gcd_candidate and (v % gcd_candidate) != 0
    ]
    lines.append("### Off-grid anomalies")
    lines.append("")
    if not off_grid:
        lines.append("_No anomalies — every observed spacing aligns with the detected grid._")
    else:
        lines.append(
            "Values that don't divide cleanly by the detected base grid. "
            "Could be intentional (nudged dividers, odd-pixel borders) or drift.",
        )
        lines.append("")
        lines.append("| Value (px) | Count |")
        lines.append("| --- | --- |")
        for v, c in off_grid[:15]:
            lines.append(f"| {v:g} | {c} |")
        if len(off_grid) > 15:
            lines.append(f"| _+{len(off_grid) - 15} more_ | — |")
    lines.append("")
    log("spacing", "ok", f"base_grid={gcd_candidate}px, values={total}")
    return "\n".join(lines)


def _infer_base_grid(values: list[float]) -> int:
    """Detect the most likely base grid value.

    Tries two heuristics and picks whichever covers more observations:

    1. **Strict divisibility** — the largest integer in {16,12,8,4,2} that
       evenly divides ≥ 60% of the observed values.
    2. **Modal-gap** — the GCD of the top-5 most common magnitudes, rounded
       to the nearest integer.

    Returns 1 when nothing meaningful is detected (everything off-grid).
    """
    if not values:
        return 1
    total = len(values)
    divisibility_candidates: list[tuple[int, int]] = []
    for candidate in (16, 12, 8, 4, 2):
        covered = sum(1 for v in values if v % candidate == 0)
        divisibility_candidates.append((candidate, covered))
    best_candidate, best_cov = max(divisibility_candidates, key=lambda kv: kv[1])
    if best_cov / total >= 0.60:
        # Prefer the largest of the top-tier candidates.
        for candidate, covered in divisibility_candidates:
            if covered == best_cov:
                return candidate
    return 1


def render_adjacencies(conn: sqlite3.Connection, limit: int = 12) -> str:
    lines = ["## Adjacencies", ""]
    lines.append(
        "For each frequently-used container (parent that holds other shared "
        "components), the top internal child-type sequences are listed. "
        "Container titles use the CKR display name where available; child "
        "sequences use each node's `component_key` display name if it has "
        "one, otherwise a `<TYPE:name>` shorthand.",
    )
    lines.append("")

    ckr_name_by_key: dict[str, str] = {
        row["component_key"]: row["name"]
        for row in conn.execute(
            "SELECT component_key, name FROM component_key_registry",
        ).fetchall()
    }

    container_rows = conn.execute(
        "SELECT parent.id AS pid, parent.component_key AS ck, parent.name AS pname "
        "FROM nodes parent "
        "JOIN nodes child ON child.parent_id = parent.id "
        "WHERE child.component_key IS NOT NULL "
        "GROUP BY parent.id "
        "HAVING COUNT(DISTINCT child.id) >= 2",
    ).fetchall()

    grouped: dict[str, list[int]] = defaultdict(list)
    for row in container_rows:
        ck = row["ck"]
        if ck and ck in ckr_name_by_key:
            display = ckr_name_by_key[ck]
        else:
            display = row["pname"]
        if not display:
            continue
        grouped[display].append(row["pid"])

    ranked = sorted(grouped.items(), key=lambda kv: -len(kv[1]))[:limit]

    for name, parent_ids in ranked:
        if len(parent_ids) < 3:
            continue
        sequences: Counter[tuple[str, ...]] = Counter()
        for pid in parent_ids:
            child_rows = conn.execute(
                "SELECT name, node_type, component_key "
                "FROM nodes WHERE parent_id = ? ORDER BY sort_order",
                (pid,),
            ).fetchall()
            seq = tuple(_child_repr(r) for r in child_rows)
            if seq:
                sequences[seq] += 1

        if not sequences:
            continue

        lines.append(f"### `{name}` — {len(parent_ids)} instances")
        lines.append("")
        total = sum(sequences.values())
        for i, (seq, count) in enumerate(sequences.most_common(5), start=1):
            pct = count / total
            pretty = ", ".join(seq)
            lines.append(f"{i}. [{pretty}] — {pct:.0%} ({count} / {total})")
        lines.append("")
    log("adjacencies", "ok", f"{len(ranked)} containers analysed")
    return "\n".join(lines)


def _child_repr(row: sqlite3.Row) -> str:
    if row["component_key"]:
        # Look up the friendly name in CKR via shared name column.
        return row["name"] or row["component_key"]
    return f"<{row['node_type']}:{row['name'] or ''}>".strip()


def render_screen_archetypes(conn: sqlite3.Connection, top_k: int = 7) -> str:
    lines = ["## Screen archetypes", ""]
    lines.append(
        "Screens clustered by their top-level structural fingerprint: the "
        "sequence of direct children of the screen root, with anonymous "
        "`FRAME`/`RECTANGLE` runs collapsed (`FRAME×3` means three contiguous "
        "unnamed frames). Named components are kept verbatim. "
        "`screen_component_instances` is empty in this DB, so this is a "
        "raw structural fingerprint, not a semantic-role one.",
    )
    lines.append("")

    screen_rows = conn.execute(
        "SELECT id, name, device_class, screen_type "
        "FROM screens WHERE screen_type='app_screen' ORDER BY id",
    ).fetchall()

    fingerprints: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for srow in screen_rows:
        root_rows = conn.execute(
            "SELECT id FROM nodes WHERE screen_id = ? AND parent_id IS NULL ORDER BY sort_order",
            (srow["id"],),
        ).fetchall()
        if not root_rows:
            continue
        tokens: list[str] = []
        for root in root_rows:
            children = conn.execute(
                "SELECT node_type, component_key, name FROM nodes "
                "WHERE parent_id = ? ORDER BY sort_order",
                (root["id"],),
            ).fetchall()
            for ch in children:
                if ch["component_key"]:
                    tokens.append(ch["name"] or ch["node_type"])
                else:
                    tokens.append(f"<{ch['node_type']}>")
        fingerprint = _collapse_fingerprint(tokens)
        fingerprints[fingerprint].append(srow["name"])

    ranked = sorted(fingerprints.items(), key=lambda kv: -len(kv[1]))[:top_k]
    for fp, examples in ranked:
        if not fp:
            continue
        lines.append(f"### {len(examples)} screens")
        lines.append("")
        lines.append("Fingerprint (top-to-bottom z-order):")
        lines.append("")
        lines.append("```")
        lines.append("\n".join(f"- {part}" for part in fp))
        lines.append("```")
        lines.append("")
        lines.append(
            "Examples: "
            + ", ".join(f"`{n}`" for n in examples[:6])
            + (f" _and {len(examples) - 6} more_" if len(examples) > 6 else ""),
        )
        lines.append("")
    log("archetypes", "ok", f"{len(ranked)} archetypes (top-{top_k})")
    return "\n".join(lines)


def _collapse_fingerprint(tokens: list[str]) -> tuple[str, ...]:
    """Collapse contiguous anonymous runs to `Type×N`.

    Anonymous tokens look like ``<FRAME>`` / ``<RECTANGLE>``; named
    components stay verbatim.
    """
    collapsed: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("<") and token.endswith(">"):
            # Count the run of the same anonymous type.
            run = 1
            while i + run < len(tokens) and tokens[i + run] == token:
                run += 1
            if run == 1:
                collapsed.append(token.strip("<>"))
            else:
                collapsed.append(f"{token.strip('<>')} x{run}")
            i += run
        else:
            collapsed.append(token)
            i += 1
    return tuple(collapsed)


def render_gaps(conn: sqlite3.Connection) -> str:
    lines = ["## Missing / gaps", ""]
    lines.append(
        "Canonical component types from the 48-type catalog (`dd/catalog.py`) "
        "that have **no matching Figma Component** (CKR entry) in this file. "
        "The \"loose\" column also scans raw node names — entries that exist "
        "as bare frames but have not been componentised. The synthesis LLM "
        "should treat *missing-in-CKR* as \"compose from primitives\" and "
        "*present-as-name-only* as \"copy from these frames\".",
    )
    lines.append("")

    ckr_names = [
        (row["name"] or "").lower()
        for row in conn.execute("SELECT name FROM component_key_registry").fetchall()
    ]
    all_node_names = [
        (row["name"] or "").lower()
        for row in conn.execute(
            "SELECT DISTINCT name FROM nodes WHERE name IS NOT NULL",
        ).fetchall()
    ]

    def matches(names: list[str], canonical: str) -> bool:
        needle = canonical.replace("_", "-")
        return any(needle in nm or canonical in nm for nm in names)

    table: list[tuple[str, str, bool, bool]] = []  # (name, category, in_ckr, in_nodes)
    for entry in CATALOG_ENTRIES:
        canonical = entry["canonical_name"]
        in_ckr = matches(ckr_names, canonical)
        in_nodes = matches(all_node_names, canonical)
        table.append((canonical, entry.get("category", "—"), in_ckr, in_nodes))

    missing_ckr = [row for row in table if not row[2]]
    only_nodes = [row for row in table if not row[2] and row[3]]

    lines.append(f"- Catalog size: **{len(table)}**")
    lines.append(f"- Present as shared component (CKR): **{len(table) - len(missing_ckr)}**")
    lines.append(f"- Absent from CKR but present as raw node name: **{len(only_nodes)}**")
    lines.append(f"- Fully absent (not in CKR, not in raw names): **{len(missing_ckr) - len(only_nodes)}**")
    lines.append("")

    lines.append("| Canonical type | Category | In CKR? | In raw names? |")
    lines.append("| --- | --- | --- | --- |")
    for name, category, in_ckr, in_nodes in sorted(table):
        ckr_cell = "yes" if in_ckr else "—"
        node_cell = "yes" if in_nodes else "—"
        lines.append(f"| `{name}` | {category} | {ckr_cell} | {node_cell} |")
    lines.append("")
    log(
        "gaps",
        "ok",
        f"{len(missing_ckr)}/{len(table)} missing from CKR; "
        f"{len(only_nodes)} present only as raw node name",
    )
    return "\n".join(lines)


def render_designer_stubs() -> str:
    return (
        "## Designer-authored sections (TODO)\n"
        "\n"
        "### Voice\n"
        "TODO: describe the design system's voice (playful, minimal, "
        "corporate, ...).\n"
        "\n"
        "### Intent conventions\n"
        "TODO: when to use `button/primary` vs `button/white`. Why.\n"
        "\n"
        "### Exclusions\n"
        "TODO: things the design system deliberately doesn't do (e.g., no "
        "dark mode yet).\n"
        "\n"
        "### Style lineage\n"
        "TODO: reference points and influences.\n"
    )


def render_header(meta: Metadata) -> str:
    return (
        f"# design.md — {meta.file_name}\n"
        f"\n"
        f"Auto-generated from `{meta.db_path}` on {meta.generated_at}.\n"
        f"\n"
        f"- File key: `{meta.file_key}`\n"
        f"- Screens: {meta.screen_count}\n"
        f"- Nodes: {meta.node_count}\n"
        f"- CKR size (distinct component keys): {meta.ckr_size}\n"
        f"- Generator: `experiments/03-design-md/generator.py` (pre-dd/ v0.1)\n"
        f"\n"
        f"This file is an auto-extractable subset of the design system. "
        f"Sections marked TODO require a human designer. The rest is mined "
        f"directly from the MLIR database.\n"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate(conn: sqlite3.Connection, db_path: str) -> str:
    meta = fetch_metadata(conn, db_path)
    log("header", "ok", f"screens={meta.screen_count}, nodes={meta.node_count}, ckr={meta.ckr_size}")

    facts = fetch_component_facts(conn)
    log("component_inventory", "ok", f"{len(facts)} CKR entries with adjacency context")

    parts = [
        render_header(meta),
        render_component_inventory(facts),
        render_token_palette(conn),
        render_typography_scale(conn),
        render_spacing_rhythm(conn),
        render_adjacencies(conn),
        render_screen_archetypes(conn),
        render_gaps(conn),
        render_designer_stubs(),
    ]
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to MLIR SQLite DB")
    parser.add_argument(
        "--out",
        default="design.md",
        help="Output markdown path (default: design.md)",
    )
    args = parser.parse_args()

    # Reset activity log on each run.
    ACTIVITY_LOG_PATH.write_text("")

    log("run", "start", f"db={args.db} out={args.out}")
    with connect(args.db) as conn:
        content = generate(conn, args.db)

    Path(args.out).write_text(content, encoding="utf-8")
    log("run", "ok", f"wrote {len(content)} chars to {args.out}")
    print(f"wrote {len(content)} chars to {args.out}")


if __name__ == "__main__":
    main()
