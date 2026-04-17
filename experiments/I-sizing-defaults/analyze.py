"""Experiment I: per-canonical-type sizing-default profile.

For each of the 48 canonical catalog types:
  1. Classify all Dank app_screen nodes (via name + heuristic rules — a
     drop-in replacement for the empty SCI table, using the same machinery
     Exp 02 uses for matcher A).
  2. Compute width/height/aspect-ratio/sizing-mode distributions.
  3. Emit per-type detail JSON for the full histogram.
  4. Emit a summary CSV one-row-per-type.
  5. Emit a defaults.yaml with a v0.1 proposal, flagging types with
     <10 Dank instances as 'insufficient data' (defer to Exp H).

Why SCI isn't used:
  screen_component_instances is empty in the current DB. The classification
  logic encoded there is exactly what `derive_canonical_type` +
  `apply_heuristic_rules` replicate in code — catalog.py + classify_rules.py
  are the single source of truth for both.

Outputs under experiments/I-sizing-defaults/:
  - per_type_distribution.csv
  - per_type_details/<canonical_type>.json
  - defaults.yaml
  - activity.log
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dd.catalog import CATALOG_ENTRIES  # noqa: E402
from dd.classify_rules import (  # noqa: E402
    apply_heuristic_rules,
    is_system_chrome,
    parse_component_name,
)

EXP_DIR = Path(__file__).resolve().parent
DETAIL_DIR = EXP_DIR / "per_type_details"
DETAIL_DIR.mkdir(exist_ok=True)
LOG_PATH = EXP_DIR / "activity.log"
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"

MIN_INSTANCES_FOR_STATS = 10

# Common tablet/mobile form factors seen in Dank (for fallback screen dims
# if the screen root node width/height is NULL)
DEFAULT_SCREEN_W = 428.0
DEFAULT_SCREEN_H = 926.0

# Types where catalog aliases caused name-matching to capture the wrong
# semantic concept. We flag these in the YAML so readers know the Dank
# defaults aren't representative of the canonical type's true intent.
# (These are discovered by inspecting the matched node names — e.g. the
# single CKR entry under 'drawer' is "Sidebar" at 31x22, which is an icon
# toggle, not a drawer surface.)
ALIAS_HIJACK_NOTES: dict[str, str] = {
    "drawer": (
        "alias-hijack: matches the 'Sidebar' INSTANCE (31x22), "
        "which is a sidebar-toggle icon button, not a drawer surface. "
        "Treat as insufficient data for drawer-surface defaults."
    ),
    "image": (
        "alias-hijack: matches only 'logo' / 'logo/dank' INSTANCEs (24x24), "
        "not general photos. Use these as logo defaults; defer photo "
        "defaults to Exp H."
    ),
    "slider": (
        "single-component hijack: all 51 instances are one FRAME named "
        "'Slider' sized 340x22 on iPhone screens. Accurate for Dank but "
        "not a universal default; cross-reference Exp H."
    ),
    "card": (
        "Dank's 'card/modal' and 'card/sheet/*' naming places these under "
        "'card' via name-prefix rules. Median 428 width is an iPhone-form-"
        "factor artefact; card.sizing.HUG is correct."
    ),
    "header": (
        "widths cluster at 428/834/1536 (the three device form factors). "
        "Treat width as screen-width, not a fixed value; sizing FILL would "
        "be more accurate when auto-layout root is available."
    ),
}


# ────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────

def log(stage: str, status: str, detail: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    line = f"{ts} | {stage} | {status} | {detail}\n"
    with LOG_PATH.open("a") as f:
        f.write(line)


# ────────────────────────────────────────────────────────────────────────
# Classification (mirrors dd/catalog.py + dd/classify_rules.py)
# ────────────────────────────────────────────────────────────────────────

def build_alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for entry in CATALOG_ENTRIES:
        canonical = entry["canonical_name"]
        idx[canonical.lower()] = canonical
        for alias in (entry.get("aliases") or []):
            idx[alias.lower()] = canonical
    return idx


ALIAS_INDEX = build_alias_index()


def derive_canonical_type_by_name(name: str) -> str | None:
    """Name-matching classification. Mirror of Exp 02 matcher A."""
    if not name:
        return None
    if is_system_chrome(name):
        return "system_chrome"
    cands = parse_component_name(name)
    for cand in cands:
        if cand in ALIAS_INDEX:
            return ALIAS_INDEX[cand]
    return None


def classify_node(node: dict[str, Any], screen_w: float, screen_h: float) -> str | None:
    """Try name-matching; fall back to heuristic rules."""
    name = node.get("name")
    canon = derive_canonical_type_by_name(name)
    if canon:
        return canon
    res = apply_heuristic_rules(node, screen_w, screen_h)
    if res:
        return res[0]
    return None


# ────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ────────────────────────────────────────────────────────────────────────

def compute_percentile(values: list[float], p: float) -> float:
    """Percentile via linear interpolation. Accepts a float p in [0, 100]."""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def rounded_mode(values: list[float], precision: float = 1.0) -> tuple[float, int] | None:
    """Return the most common rounded value plus its count.

    Rounds each value to the nearest `precision`. For subpixel values
    this gives a much more useful mode than raw equality.
    """
    if not values:
        return None
    c = Counter(round(v / precision) * precision for v in values)
    if not c:
        return None
    return c.most_common(1)[0]


def top_modes(values: list[float], k: int = 3, precision: float = 1.0) -> list[tuple[float, int]]:
    if not values:
        return []
    c = Counter(round(v / precision) * precision for v in values)
    return c.most_common(k)


def build_histogram(values: list[float], bucket_size: float = 16.0, max_bins: int = 50) -> list[tuple[float, int]]:
    """Return [(bucket_lo, count), ...] sorted by bucket_lo."""
    if not values:
        return []
    bucket_counts: dict[int, int] = defaultdict(int)
    for v in values:
        bkt = int(v // bucket_size) * bucket_size
        bucket_counts[int(bkt)] += 1
    items = sorted(bucket_counts.items())
    if len(items) > max_bins:
        # Coalesce tail
        head = items[:max_bins - 1]
        tail_count = sum(c for _, c in items[max_bins - 1:])
        items = head + [(items[max_bins - 1][0], tail_count)]
    return [(float(b), c) for b, c in items]


def classify_aspect(w: float, h: float) -> str:
    if w <= 0 or h <= 0:
        return "invalid"
    ratio = w / h
    if 0.95 <= ratio <= 1.05:
        return "1:1"
    if ratio < 0.5:
        return "tall"
    if 0.5 <= ratio < 0.95:
        return "portrait"
    if 1.05 < ratio <= 2.0:
        return "landscape"
    if 2.0 < ratio <= 5.0:
        return "wide"
    return "very_wide"


# ────────────────────────────────────────────────────────────────────────
# Data loading
# ────────────────────────────────────────────────────────────────────────

def load_screen_dims(conn: sqlite3.Connection) -> dict[int, tuple[float, float]]:
    cur = conn.execute(
        "SELECT n.screen_id, n.width, n.height FROM nodes n "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.screen_type = 'app_screen' AND n.depth = 0"
    )
    out: dict[int, tuple[float, float]] = {}
    for sid, w, h in cur.fetchall():
        if w and h:
            out[sid] = (float(w), float(h))
        else:
            out[sid] = (DEFAULT_SCREEN_W, DEFAULT_SCREEN_H)
    return out


def classify_all_nodes(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Run classification across all app_screen nodes. Returns
    canonical_type -> list of node rows (dict)."""
    log("load", "START", "loading all app_screen nodes")
    screen_dims = load_screen_dims(conn)

    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT n.* FROM nodes n JOIN screens s ON n.screen_id = s.id "
        "WHERE s.screen_type = 'app_screen'"
    )
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total = 0
    for row in cur:
        d = dict(row)
        sw, sh = screen_dims.get(d["screen_id"], (DEFAULT_SCREEN_W, DEFAULT_SCREEN_H))
        canon = classify_node(d, sw, sh)
        total += 1
        if canon:
            by_type[canon].append(d)
    log(
        "load",
        "OK",
        f"classified {total} nodes into {len(by_type)} canonical types; "
        f"unclassified={total - sum(len(v) for v in by_type.values())}",
    )
    return dict(by_type)


# ────────────────────────────────────────────────────────────────────────
# Per-type analysis
# ────────────────────────────────────────────────────────────────────────

def analyze_type(canonical: str, nodes: list[dict[str, Any]], screen_dims: dict[int, tuple[float, float]]) -> dict[str, Any]:
    """Compute full distribution and summary stats for one canonical type."""
    widths = [float(n["width"]) for n in nodes if n.get("width") is not None]
    heights = [float(n["height"]) for n in nodes if n.get("height") is not None]

    sizing_h = Counter(n.get("layout_sizing_h") or "NONE" for n in nodes)
    sizing_v = Counter(n.get("layout_sizing_v") or "NONE" for n in nodes)

    node_types = Counter(n.get("node_type") or "UNKNOWN" for n in nodes)

    aspects: list[str] = []
    aspect_ratios: list[float] = []
    screen_width_ratios: list[float] = []  # width / screen_width
    for n in nodes:
        w = n.get("width")
        h = n.get("height")
        if w and h and w > 0 and h > 0:
            aspects.append(classify_aspect(w, h))
            aspect_ratios.append(w / h)
            sw, _sh = screen_dims.get(n["screen_id"], (DEFAULT_SCREEN_W, DEFAULT_SCREEN_H))
            if sw > 0:
                screen_width_ratios.append(w / sw)

    # Variant sub-analysis: group by first path segment of name when name
    # uses '/' convention. E.g. button/large/translucent -> 'large'
    variant_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        name = (n.get("name") or "").strip().lower()
        parts = name.split("/") if "/" in name else []
        variant_key = "_default"
        if len(parts) >= 2:
            # "button/small/solid" -> "small"
            variant_key = parts[1]
        variant_buckets[variant_key].append(n)

    # Summary
    count = len(nodes)
    summary: dict[str, Any] = {
        "canonical_type": canonical,
        "count": count,
        "sufficient_data": count >= MIN_INSTANCES_FOR_STATS,
    }

    if widths:
        w_mode = rounded_mode(widths, 1.0)
        summary["width"] = {
            "mean": round(statistics.fmean(widths), 2),
            "median": round(statistics.median(widths), 2),
            "stdev": round(statistics.pstdev(widths), 2) if len(widths) > 1 else 0.0,
            "mode": w_mode,
            "p25": round(compute_percentile(widths, 25), 2),
            "p50": round(compute_percentile(widths, 50), 2),
            "p75": round(compute_percentile(widths, 75), 2),
            "p95": round(compute_percentile(widths, 95), 2),
            "min": round(min(widths), 2),
            "max": round(max(widths), 2),
            "top_modes": top_modes(widths, 5, 1.0),
        }
    if heights:
        h_mode = rounded_mode(heights, 1.0)
        summary["height"] = {
            "mean": round(statistics.fmean(heights), 2),
            "median": round(statistics.median(heights), 2),
            "stdev": round(statistics.pstdev(heights), 2) if len(heights) > 1 else 0.0,
            "mode": h_mode,
            "p25": round(compute_percentile(heights, 25), 2),
            "p50": round(compute_percentile(heights, 50), 2),
            "p75": round(compute_percentile(heights, 75), 2),
            "p95": round(compute_percentile(heights, 95), 2),
            "min": round(min(heights), 2),
            "max": round(max(heights), 2),
            "top_modes": top_modes(heights, 5, 1.0),
        }

    summary["sizing_h"] = dict(sizing_h)
    summary["sizing_v"] = dict(sizing_v)
    summary["node_types"] = dict(node_types)
    summary["aspect_distribution"] = dict(Counter(aspects))
    if aspect_ratios:
        summary["aspect_ratio_stats"] = {
            "mean": round(statistics.fmean(aspect_ratios), 3),
            "median": round(statistics.median(aspect_ratios), 3),
            "p25": round(compute_percentile(aspect_ratios, 25), 3),
            "p75": round(compute_percentile(aspect_ratios, 75), 3),
        }
    if screen_width_ratios:
        summary["screen_width_ratio_stats"] = {
            "median": round(statistics.median(screen_width_ratios), 3),
            "mean": round(statistics.fmean(screen_width_ratios), 3),
        }

    # Variant breakdown (only for variants with ≥ 5 samples)
    variants_out: dict[str, dict[str, Any]] = {}
    for vk, vnodes in variant_buckets.items():
        if len(vnodes) < 5:
            continue
        vwidths = [float(n["width"]) for n in vnodes if n.get("width") is not None]
        vheights = [float(n["height"]) for n in vnodes if n.get("height") is not None]
        if not vwidths or not vheights:
            continue
        variants_out[vk] = {
            "count": len(vnodes),
            "width_median": round(statistics.median(vwidths), 2),
            "height_median": round(statistics.median(vheights), 2),
            "width_mode": rounded_mode(vwidths, 1.0),
            "height_mode": rounded_mode(vheights, 1.0),
            "sizing_h_dominant": Counter(n.get("layout_sizing_h") or "NONE" for n in vnodes).most_common(1)[0],
            "sizing_v_dominant": Counter(n.get("layout_sizing_v") or "NONE" for n in vnodes).most_common(1)[0],
        }
    summary["variants"] = variants_out

    # Histograms
    summary["width_histogram"] = build_histogram(widths, bucket_size=16.0)
    summary["height_histogram"] = build_histogram(heights, bucket_size=16.0)

    return summary


def write_detail(canonical: str, summary: dict[str, Any]) -> None:
    path = DETAIL_DIR / f"{canonical}.json"
    with path.open("w") as f:
        json.dump(summary, f, indent=2, default=str)


# ────────────────────────────────────────────────────────────────────────
# CSV + defaults.yaml
# ────────────────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "canonical_type",
    "count",
    "sufficient_data",
    "width_mean", "width_median", "width_p25", "width_p75", "width_p95",
    "width_mode", "width_std", "width_min", "width_max",
    "height_mean", "height_median", "height_p25", "height_p75", "height_p95",
    "height_mode", "height_std", "height_min", "height_max",
    "sizing_h_dominant", "sizing_h_dominant_share",
    "sizing_v_dominant", "sizing_v_dominant_share",
    "top_aspect", "top_aspect_share",
    "dominant_node_type", "dominant_node_type_share",
    "screen_width_ratio_median",
]


def _dominant(counter: dict[str, int]) -> tuple[str, float]:
    if not counter:
        return ("NONE", 0.0)
    total = sum(counter.values())
    if total == 0:
        return ("NONE", 0.0)
    k = max(counter, key=lambda x: counter[x])
    return (k, counter[k] / total)


def write_summary_csv(summaries: list[dict[str, Any]]) -> None:
    path = EXP_DIR / "per_type_distribution.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for s in summaries:
            row: dict[str, Any] = {"canonical_type": s["canonical_type"], "count": s["count"], "sufficient_data": s["sufficient_data"]}
            w = s.get("width") or {}
            h = s.get("height") or {}
            row["width_mean"] = w.get("mean")
            row["width_median"] = w.get("median")
            row["width_p25"] = w.get("p25")
            row["width_p75"] = w.get("p75")
            row["width_p95"] = w.get("p95")
            row["width_mode"] = (w.get("mode") or (None, None))[0]
            row["width_std"] = w.get("stdev")
            row["width_min"] = w.get("min")
            row["width_max"] = w.get("max")
            row["height_mean"] = h.get("mean")
            row["height_median"] = h.get("median")
            row["height_p25"] = h.get("p25")
            row["height_p75"] = h.get("p75")
            row["height_p95"] = h.get("p95")
            row["height_mode"] = (h.get("mode") or (None, None))[0]
            row["height_std"] = h.get("stdev")
            row["height_min"] = h.get("min")
            row["height_max"] = h.get("max")

            sh_dom, sh_share = _dominant(s.get("sizing_h", {}))
            sv_dom, sv_share = _dominant(s.get("sizing_v", {}))
            row["sizing_h_dominant"] = sh_dom
            row["sizing_h_dominant_share"] = round(sh_share, 3)
            row["sizing_v_dominant"] = sv_dom
            row["sizing_v_dominant_share"] = round(sv_share, 3)

            ap_dom, ap_share = _dominant(s.get("aspect_distribution", {}))
            row["top_aspect"] = ap_dom
            row["top_aspect_share"] = round(ap_share, 3)

            nt_dom, nt_share = _dominant(s.get("node_types", {}))
            row["dominant_node_type"] = nt_dom
            row["dominant_node_type_share"] = round(nt_share, 3)

            row["screen_width_ratio_median"] = (s.get("screen_width_ratio_stats") or {}).get("median")
            writer.writerow(row)


# ────────────────────────────────────────────────────────────────────────
# defaults.yaml writer
# ────────────────────────────────────────────────────────────────────────

def _yaml_escape(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in ":#{}[],&*!|>'\"%@`?\n") or s == "" or s[0] in ("- ", "? "):
        return f'"{s}"'
    return s


def _variance_label(stdev: float, median: float) -> str:
    if median == 0:
        return "n/a"
    cv = stdev / max(median, 1e-6)
    if cv < 0.15:
        return "low"
    if cv < 0.4:
        return "moderate"
    return "high"


def write_defaults_yaml(summaries_by_type: dict[str, dict[str, Any]], all_canonicals: list[str]) -> None:
    path = EXP_DIR / "defaults.yaml"
    lines: list[str] = []
    lines.append("# Experiment I — per-canonical-type sizing defaults")
    lines.append("# Generated from Dank-EXP-02 (204 app_screens, 79,833 nodes).")
    lines.append("#")
    lines.append("# Classification: derive_canonical_type (dd/catalog.py aliases) + ")
    lines.append("# apply_heuristic_rules (dd/classify_rules.py). This replicates what")
    lines.append("# screen_component_instances would contain — the SCI table is empty")
    lines.append("# in this DB because the formal classification stage hasn't been run.")
    lines.append("#")
    lines.append("# Types with < 10 Dank instances are flagged `data: insufficient`")
    lines.append("# and should be backfilled from Exp H (public design-system defaults).")
    lines.append("#")
    lines.append("# Units: pixels (Figma logical). Sizing modes per Figma: FIXED | HUG | FILL.")
    lines.append("# The 'value' field is the median; the 'min'/'max' bracket is p25-p95.")
    lines.append("")

    for canon in all_canonicals:
        s = summaries_by_type.get(canon)
        lines.append(f"{canon}:")
        if not s or not s.get("sufficient_data"):
            count = s["count"] if s else 0
            lines.append("  data: insufficient")
            lines.append(f"  count: {count}")
            lines.append('  note: "augment with public-system defaults in Exp H"')
            lines.append("")
            continue

        w = s["width"]
        h = s["height"]
        sh_dom, _ = _dominant(s["sizing_h"])
        sv_dom, _ = _dominant(s["sizing_v"])
        ap_dom, ap_share = _dominant(s.get("aspect_distribution", {}))
        swr_median = (s.get("screen_width_ratio_stats") or {}).get("median")

        lines.append(f"  count: {s['count']}")
        lines.append(f"  width:")
        lines.append(f"    value: {int(round(w['median']))}")
        lines.append(f"    sizing: {sh_dom}")
        lines.append(f"    min: {int(round(w['p25']))}")
        lines.append(f"    max: {int(round(w['p95']))}")
        lines.append(f"  height:")
        lines.append(f"    value: {int(round(h['median']))}")
        lines.append(f"    sizing: {sv_dom}")
        lines.append(f"    min: {int(round(h['p25']))}")
        lines.append(f"    max: {int(round(h['p95']))}")

        # Aspect note
        w_var = _variance_label(w["stdev"], w["median"])
        h_var = _variance_label(h["stdev"], h["median"])
        if swr_median is not None:
            lines.append(f'  screen_width_ratio_median: {swr_median}')
        lines.append(f'  aspect_dominant: "{ap_dom}"')
        lines.append(f"  aspect_dominant_share: {round(ap_share, 3)}")
        lines.append(f'  variance_width: {w_var}')
        lines.append(f'  variance_height: {h_var}')

        if canon in ALIAS_HIJACK_NOTES:
            lines.append(f'  note: "{ALIAS_HIJACK_NOTES[canon]}"')

        variants = s.get("variants") or {}
        # Only emit variants when distribution genuinely splits — i.e. when
        # there are ≥ 2 variants AND at least two variants differ meaningfully
        # in either width or height median (> 25% relative or >= 16px absolute).
        # Filter out variants that don't differ from the type-level median.
        if variants and canon != "icon":  # Icon variants are glyph identity, not sizing
            vkeys = [k for k in variants.keys() if k != "_default"]
            if len(vkeys) >= 2:
                type_w_median = w["median"]
                type_h_median = h["median"]
                # Keep variants that differ meaningfully from the overall median
                # (>= 8px absolute OR >= 10% relative on either axis), as long
                # as they have >= 5 samples. This captures bimodal splits like
                # button/small (40x40) vs button/large (48x52).
                meaningful: list[str] = []
                for vk in vkeys:
                    v = variants[vk]
                    if v["count"] < 5:
                        continue
                    w_diff = abs(v["width_median"] - type_w_median)
                    h_diff = abs(v["height_median"] - type_h_median)
                    w_rel = w_diff / max(type_w_median, 1.0)
                    h_rel = h_diff / max(type_h_median, 1.0)
                    if w_diff >= 8 or h_diff >= 8 or w_rel >= 0.1 or h_rel >= 0.1:
                        meaningful.append(vk)
                if len(meaningful) >= 2:
                    lines.append("  variants:")
                    for vk in sorted(meaningful, key=lambda k: variants[k]["count"], reverse=True):
                        v = variants[vk]
                        lines.append(f"    {vk}:")
                        lines.append(f"      count: {v['count']}")
                        lines.append(f"      width: {int(round(v['width_median']))}")
                        lines.append(f"      height: {int(round(v['height_median']))}")
                        lines.append(f"      sizing_h: {v['sizing_h_dominant'][0]}")
                        lines.append(f"      sizing_v: {v['sizing_v_dominant'][0]}")
        lines.append("")

    # Bonus section: non-catalog classifications from our pipeline (system_chrome,
    # container) that still need sizing defaults. These don't fit the 48 catalog
    # types but are live in classification.
    bonus = ["system_chrome", "container"]
    bonus_with_data = [b for b in bonus if summaries_by_type.get(b) and summaries_by_type[b].get("sufficient_data")]
    if bonus_with_data:
        lines.append("# ── Non-catalog classifications (live in classify_rules.py but not in")
        lines.append("# the 48-type component_type_catalog). Included for completeness.")
        for canon in bonus_with_data:
            s = summaries_by_type[canon]
            w = s["width"]
            h = s["height"]
            sh_dom, _ = _dominant(s["sizing_h"])
            sv_dom, _ = _dominant(s["sizing_v"])
            lines.append(f"{canon}:")
            lines.append(f"  count: {s['count']}")
            lines.append(f"  width:")
            lines.append(f"    value: {int(round(w['median']))}")
            lines.append(f"    sizing: {sh_dom}")
            lines.append(f"    min: {int(round(w['p25']))}")
            lines.append(f"    max: {int(round(w['p95']))}")
            lines.append(f"  height:")
            lines.append(f"    value: {int(round(h['median']))}")
            lines.append(f"    sizing: {sv_dom}")
            lines.append(f"    min: {int(round(h['p25']))}")
            lines.append(f"    max: {int(round(h['p95']))}")
            if canon == "system_chrome":
                lines.append('  note: "mix of iOS status bars, home indicators, keyboards — wide variance expected"')
            elif canon == "container":
                lines.append('  note: "generic layout frame (no visual properties). Sizing is layout-dependent; only use as last-resort default."')
            lines.append("")

    path.write_text("\n".join(lines) + "\n")


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────

def main() -> None:
    log("main", "START", f"DB={DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        by_type = classify_all_nodes(conn)
        screen_dims = load_screen_dims(conn)

        all_canonicals = sorted({e["canonical_name"] for e in CATALOG_ENTRIES})

        summaries: list[dict[str, Any]] = []
        summaries_by_type: dict[str, dict[str, Any]] = {}

        for canon in all_canonicals:
            nodes = by_type.get(canon, [])
            summary = analyze_type(canon, nodes, screen_dims)
            summaries.append(summary)
            summaries_by_type[canon] = summary
            write_detail(canon, summary)
            status = "OK" if summary["sufficient_data"] else "INSUFFICIENT"
            log("analyze", status, f"{canon}: count={summary['count']}")

        # Also analyze system_chrome even though it's not in the 48-type catalog
        # (important for realism — bottom nav / status bar dimensions are useful
        #  defaults, and classification uses 'system_chrome' as a canonical key)
        if "system_chrome" in by_type:
            s = analyze_type("system_chrome", by_type["system_chrome"], screen_dims)
            summaries.append(s)
            summaries_by_type["system_chrome"] = s
            write_detail("system_chrome", s)
            log("analyze", "OK", f"system_chrome: count={s['count']} (not in 48-type catalog)")
        if "container" in by_type:
            s = analyze_type("container", by_type["container"], screen_dims)
            summaries.append(s)
            summaries_by_type["container"] = s
            write_detail("container", s)
            log("analyze", "OK", f"container: count={s['count']} (heuristic rule only)")

        write_summary_csv(summaries)
        log("output", "OK", f"per_type_distribution.csv ({len(summaries)} rows)")

        write_defaults_yaml(summaries_by_type, all_canonicals)
        log("output", "OK", f"defaults.yaml ({len(all_canonicals)} entries)")

        sufficient = sum(1 for s in summaries if s.get("sufficient_data") and s["canonical_type"] != "system_chrome" and s["canonical_type"] != "container")
        insufficient = len(all_canonicals) - sufficient
        log("main", "DONE", f"sufficient={sufficient}/{len(all_canonicals)} types; insufficient={insufficient}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
