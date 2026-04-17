"""Experiment G — Empirical analysis of Dank positioning patterns.

For every node in the 204 app screens whose **parent has no auto-layout**
(`layout_mode IS NULL`), classify its positioning intent as an
(anchor_h, offset_h, stretch_h) + (anchor_v, offset_v, stretch_v) tuple.

Output:
  - dank_positioning_patterns.csv   per-node classification
  - anchor_distribution.csv         aggregate (anchor_h, anchor_v) x freq
  - offset_distribution.csv         aggregate offsets -> freq, bucketed
  - coverage_cumulative.csv         cumulative coverage at N most-common constructs
  - part1_stats.json                headline numbers for the memo

We deliberately include INSIDE-INSTANCE-SUBTREE nodes (figma_node_id
starts with 'I') in the stats but tag them so we can split both ways —
those won't be LLM-emitted under component abstraction, but they're
still part of the positioning grammar the renderer must honour.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db")
OUT_DIR = Path("/Users/mattpacione/declarative-build/experiments/G-positioning-vocab")
ACTIVITY_LOG = OUT_DIR / "activity.log"


def log(stage: str, status: str, detail: str = "") -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"{ts} | {stage} | {status} | {detail}\n"
    with ACTIVITY_LOG.open("a") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Tolerances

LEADING_THRESHOLD_PX = 1.0       # local position within 1px of edge -> "at edge"
CENTER_THRESHOLD_PX = 4.0        # center alignment tolerance
STRETCH_THRESHOLD_PX = 2.0       # width matches parent (for implicit stretch)
ASPECT_SCALE_RATIO_TOL = 0.02    # +-2% means "fills" proportionally


# Token-like buckets drawn from common spacing scales (4pt/8pt + outliers).
# We'll compute real offsets first then snap-to-nearest for reporting.
STANDARD_BUCKETS_PX = [
    0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 40, 48, 56, 64, 72,
    80, 96, 112, 128, 144, 160, 192, 224, 256, 320, 384, 448, 512,
]


def bucket_offset(value: float) -> tuple[str, float]:
    """Return (label, nearest bucket px) — 'exact' label when within 0.5px.

    Also returns a coarse label 'negative', 'irregular', or the px value.
    """
    if value is None:
        return ("none", 0.0)
    if abs(value) < 0.5:
        return ("0", 0.0)
    for b in STANDARD_BUCKETS_PX:
        if abs(value - b) <= 0.5:
            return (f"{b}", float(b))
        if abs(value + b) <= 0.5:
            return (f"-{b}", float(-b))
    # non-standard: return signed integer rounded
    rounded = round(value)
    if value < 0:
        return ("negative-non-bucket", float(rounded))
    return ("non-bucket", float(rounded))


# ---------------------------------------------------------------------------
# Positioning classifier

def classify_horizontal(
    local_x: float,
    width: float,
    parent_width: float,
    constraint_h: str | None,
) -> tuple[str, float, str]:
    """Return (anchor, offset, stretch_kind).

    anchor ∈ {leading, trailing, center, stretch, unknown}
    offset is the px distance from anchor origin (positive = inset)
    stretch_kind ∈ {'', 'both_edges'} — when True we record two offsets,
    represented as "{offset_from_leading}/{offset_from_trailing}" in the
    label column.
    """
    if parent_width <= 0:
        return ("unknown", 0.0, "")

    # STRETCH case — LEFT_RIGHT enum or visibly full-width
    gap_right = parent_width - (local_x + width)
    if constraint_h == "LEFT_RIGHT":
        return ("stretch", local_x, "both_edges")
    if (abs(local_x) < STRETCH_THRESHOLD_PX and abs(gap_right) < STRETCH_THRESHOLD_PX
            and constraint_h in (None, "LEFT", "LEFT_RIGHT", "SCALE")):
        return ("stretch", 0.0, "both_edges")

    # SCALE — proportional; treat as stretch-with-percent-based offsets for v0.1 bucket
    if constraint_h == "SCALE":
        return ("scale", local_x, "")

    # CENTER anchor — explicit CENTER enum, or center-aligned by geometry
    parent_center = parent_width / 2.0
    node_center = local_x + width / 2.0
    if constraint_h == "CENTER" or abs(node_center - parent_center) < CENTER_THRESHOLD_PX:
        return ("center", node_center - parent_center, "")

    # TRAILING — RIGHT enum or visible right-edge anchoring
    if constraint_h == "RIGHT" or (abs(gap_right) < LEADING_THRESHOLD_PX and gap_right <= 2.0):
        return ("trailing", gap_right, "")

    # LEADING default — LEFT enum or leftmost
    return ("leading", local_x, "")


def classify_vertical(
    local_y: float,
    height: float,
    parent_height: float,
    constraint_v: str | None,
) -> tuple[str, float, str]:
    if parent_height <= 0:
        return ("unknown", 0.0, "")

    gap_bottom = parent_height - (local_y + height)
    if constraint_v == "TOP_BOTTOM":
        return ("stretch", local_y, "both_edges")
    if (abs(local_y) < STRETCH_THRESHOLD_PX and abs(gap_bottom) < STRETCH_THRESHOLD_PX
            and constraint_v in (None, "TOP", "TOP_BOTTOM", "SCALE")):
        return ("stretch", 0.0, "both_edges")

    if constraint_v == "SCALE":
        return ("scale", local_y, "")

    parent_center = parent_height / 2.0
    node_center = local_y + height / 2.0
    if constraint_v == "CENTER" or abs(node_center - parent_center) < CENTER_THRESHOLD_PX:
        return ("center", node_center - parent_center, "")

    if constraint_v == "BOTTOM" or (abs(gap_bottom) < LEADING_THRESHOLD_PX and gap_bottom <= 2.0):
        return ("bottom", gap_bottom, "")

    return ("top", local_y, "")


# ---------------------------------------------------------------------------
# Extraction

def load_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return every node whose parent exists AND parent has layout_mode IS NULL.

    Scopes to `screens.screen_type='app_screen'`.
    """
    sql = """
    SELECT
        s.id                AS screen_id,
        s.name              AS screen_name,
        s.device_class      AS device_class,
        n.id                AS node_id,
        n.figma_node_id     AS fid,
        n.parent_id         AS parent_id,
        n.name              AS node_name,
        n.node_type         AS node_type,
        n.depth             AS depth,
        n.x                 AS n_x,
        n.y                 AS n_y,
        n.width             AS n_w,
        n.height            AS n_h,
        n.rotation          AS rotation,
        n.constraint_h      AS constraint_h,
        n.constraint_v      AS constraint_v,
        n.layout_positioning AS layout_positioning,
        n.visible           AS visible,
        p.x                 AS p_x,
        p.y                 AS p_y,
        p.width             AS p_w,
        p.height            AS p_h,
        p.node_type         AS parent_type,
        p.layout_mode       AS parent_layout_mode
    FROM nodes n
    JOIN screens s ON n.screen_id = s.id
    JOIN nodes p   ON n.parent_id = p.id
    WHERE s.screen_type = 'app_screen'
      AND p.layout_mode IS NULL
      AND n.width IS NOT NULL AND n.height IS NOT NULL
      AND p.width IS NOT NULL AND p.height IS NOT NULL
    """
    cur = conn.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Analysis pipeline

def analyze() -> dict[str, Any]:
    OUT_DIR.mkdir(exist_ok=True, parents=True)
    log("setup", "start", "Experiment G Part 1")
    conn = sqlite3.connect(str(DB_PATH))
    rows = load_rows(conn)
    log("load", "ok", f"{len(rows)} non-AL-parented nodes in app screens")

    classified: list[dict[str, Any]] = []
    anchor_counter: collections.Counter[tuple[str, str]] = collections.Counter()
    offset_h_counter: collections.Counter[str] = collections.Counter()
    offset_v_counter: collections.Counter[str] = collections.Counter()
    construct_counter: collections.Counter[tuple] = collections.Counter()
    sizing_counter: collections.Counter[tuple[str, str, str, str]] = collections.Counter()
    parent_type_split: collections.Counter[tuple[str, bool]] = collections.Counter()

    exceptions = 0
    rotated_count = 0
    absolute_in_al_ancestor = 0

    for r in rows:
        lx = r["n_x"] - r["p_x"]
        ly = r["n_y"] - r["p_y"]
        pw = r["p_w"]
        ph = r["p_h"]
        nw = r["n_w"]
        nh = r["n_h"]
        rot = r["rotation"] or 0.0
        if abs(rot) > 0.5:
            rotated_count += 1

        anchor_h, off_h, stretch_h = classify_horizontal(lx, nw, pw, r["constraint_h"])
        anchor_v, off_v, stretch_v = classify_vertical(ly, nh, ph, r["constraint_v"])

        # For STRETCH with both_edges, offset_h encodes leading inset;
        # we also want trailing inset for reporting.
        trailing_inset_h = pw - (lx + nw) if stretch_h == "both_edges" else None
        trailing_inset_v = ph - (ly + nh) if stretch_v == "both_edges" else None

        bucket_h_lbl, bucket_h = bucket_offset(off_h)
        bucket_v_lbl, bucket_v = bucket_offset(off_v)

        # Construct signature — the "word" of the grammar at this node
        construct = (anchor_h, bucket_h_lbl, anchor_v, bucket_v_lbl)

        is_instance_descendant = r["fid"].startswith("I") if r["fid"] else False

        anchor_counter[(anchor_h, anchor_v)] += 1
        offset_h_counter[bucket_h_lbl] += 1
        offset_v_counter[bucket_v_lbl] += 1
        construct_counter[construct] += 1
        sizing_counter[(anchor_h, anchor_v, stretch_h, stretch_v)] += 1
        parent_type_split[(r["parent_type"] or "", is_instance_descendant)] += 1

        classified.append({
            "screen_id": r["screen_id"],
            "screen_name": r["screen_name"],
            "device_class": r["device_class"],
            "node_id": r["node_id"],
            "figma_node_id": r["fid"],
            "node_name": r["node_name"],
            "node_type": r["node_type"],
            "parent_type": r["parent_type"],
            "depth": r["depth"],
            "is_instance_descendant": is_instance_descendant,
            "local_x": round(lx, 2),
            "local_y": round(ly, 2),
            "width": round(nw, 2),
            "height": round(nh, 2),
            "parent_width": round(pw, 2),
            "parent_height": round(ph, 2),
            "rotation": round(rot, 2),
            "constraint_h": r["constraint_h"],
            "constraint_v": r["constraint_v"],
            "layout_positioning": r["layout_positioning"],
            "anchor_h": anchor_h,
            "offset_h_px": round(off_h, 2),
            "offset_h_bucket": bucket_h_lbl,
            "stretch_h": stretch_h,
            "trailing_inset_h": (
                round(trailing_inset_h, 2) if trailing_inset_h is not None else None
            ),
            "anchor_v": anchor_v,
            "offset_v_px": round(off_v, 2),
            "offset_v_bucket": bucket_v_lbl,
            "stretch_v": stretch_v,
            "trailing_inset_v": (
                round(trailing_inset_v, 2) if trailing_inset_v is not None else None
            ),
        })

    log("classify", "ok", f"{len(classified)} rows; rotated={rotated_count}")

    # ---- Write per-node CSV --------------------------------------------------
    if classified:
        pnodes_path = OUT_DIR / "dank_positioning_patterns.csv"
        with pnodes_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(classified[0].keys()))
            w.writeheader()
            w.writerows(classified)
        log("write", "ok", f"dank_positioning_patterns.csv {len(classified)} rows")

    # ---- Anchor distribution -------------------------------------------------
    # Dump BOTH universes (ALL + LLM-emitted subset) in one file with a column.
    total_all = sum(anchor_counter.values())
    llm_rows = [r for r in classified if not r["is_instance_descendant"]]
    total_llm = len(llm_rows)
    llm_anchor = collections.Counter((r["anchor_h"], r["anchor_v"]) for r in llm_rows)

    anchor_path = OUT_DIR / "anchor_distribution.csv"
    with anchor_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "anchor_h", "anchor_v", "count", "pct", "cum_pct"])
        running = 0
        for (ah, av), cnt in anchor_counter.most_common():
            running += cnt
            w.writerow(["ALL", ah, av, cnt,
                        f"{cnt/total_all*100:.2f}", f"{running/total_all*100:.2f}"])
        running = 0
        for (ah, av), cnt in llm_anchor.most_common():
            running += cnt
            w.writerow(["LLM_EMITTED", ah, av, cnt,
                        f"{cnt/total_llm*100:.2f}" if total_llm else "",
                        f"{running/total_llm*100:.2f}" if total_llm else ""])

    # ---- Offset distributions ------------------------------------------------
    llm_offh = collections.Counter(r["offset_h_bucket"] for r in llm_rows)
    llm_offv = collections.Counter(r["offset_v_bucket"] for r in llm_rows)
    offset_path = OUT_DIR / "offset_distribution.csv"
    with offset_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "axis", "bucket", "count", "pct"])
        for lbl, cnt in offset_h_counter.most_common():
            w.writerow(["ALL", "h", lbl, cnt, f"{cnt/total_all*100:.2f}"])
        for lbl, cnt in offset_v_counter.most_common():
            w.writerow(["ALL", "v", lbl, cnt, f"{cnt/total_all*100:.2f}"])
        for lbl, cnt in llm_offh.most_common():
            w.writerow(["LLM_EMITTED", "h", lbl, cnt,
                        f"{cnt/total_llm*100:.2f}" if total_llm else ""])
        for lbl, cnt in llm_offv.most_common():
            w.writerow(["LLM_EMITTED", "v", lbl, cnt,
                        f"{cnt/total_llm*100:.2f}" if total_llm else ""])

    # ---- Construct (grammar-word) cumulative coverage ------------------------
    # LLM-emitted subset is the one that matters for grammar design.
    cov_path = OUT_DIR / "coverage_cumulative.csv"
    llm_constructs: collections.Counter[tuple] = collections.Counter()
    for r in llm_rows:
        llm_constructs[(r["anchor_h"], r["offset_h_bucket"],
                        r["anchor_v"], r["offset_v_bucket"])] += 1
    running_all = 0
    running_llm = 0
    with cov_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "rank", "anchor_h", "offset_h", "anchor_v", "offset_v",
                    "count", "pct", "cum_pct"])
        for rank, (ckey, cnt) in enumerate(construct_counter.most_common(), 1):
            running_all += cnt
            w.writerow(["ALL", rank, *ckey, cnt,
                        f"{cnt/total_all*100:.2f}", f"{running_all/total_all*100:.2f}"])
        for rank, (ckey, cnt) in enumerate(llm_constructs.most_common(), 1):
            running_llm += cnt
            w.writerow(["LLM_EMITTED", rank, *ckey, cnt,
                        f"{cnt/total_llm*100:.2f}" if total_llm else "",
                        f"{running_llm/total_llm*100:.2f}" if total_llm else ""])

    # ---- Headline stats ------------------------------------------------------
    # Split results into two universes:
    #   ALL (includes inside-instance descendants)
    #   LLM-EMITTED (outside-instance — what a generator would actually emit)
    # Component-internal positioning is asset-keyed, not part of L3 grammar.

    def stats_for(subset: list[dict]) -> dict[str, Any]:
        sub_total = len(subset)
        if sub_total == 0:
            return {"total": 0}
        cc: collections.Counter[tuple] = collections.Counter()
        for row in subset:
            cc[(row["anchor_h"], row["offset_h_bucket"],
                row["anchor_v"], row["offset_v_bucket"])] += 1

        running = 0
        thresholds = {50: None, 75: None, 90: None, 95: None}
        for rank, (_k, cnt) in enumerate(cc.most_common(), 1):
            running += cnt
            pct = running / sub_total * 100
            for t in thresholds:
                if thresholds[t] is None and pct >= t:
                    thresholds[t] = rank

        # anchor distribution
        ah_counter = collections.Counter((r["anchor_h"], r["anchor_v"]) for r in subset)
        bucket_clean = sum(
            1 for r in subset
            if not r["offset_h_bucket"].startswith("non-")
            and not r["offset_v_bucket"].startswith("non-")
        )
        rotated = sum(1 for r in subset if abs(r.get("rotation", 0) or 0) > 0.5)

        return {
            "total": sub_total,
            "rotated_pct": round(rotated / sub_total * 100, 2),
            "coverage_N_for_50pct": thresholds[50],
            "coverage_N_for_75pct": thresholds[75],
            "coverage_N_for_90pct": thresholds[90],
            "coverage_N_for_95pct": thresholds[95],
            "bucket_clean_pct": round(bucket_clean / sub_total * 100, 2),
            "anchor_combos_distinct": len(ah_counter),
            "top_anchor_combos": [
                {"anchor_h": k[0], "anchor_v": k[1], "count": v,
                 "pct": round(v/sub_total*100, 2)}
                for k, v in ah_counter.most_common(15)
            ],
            "top_20_constructs": [
                {"anchor_h": k[0], "offset_h": k[1], "anchor_v": k[2], "offset_v": k[3],
                 "count": v, "pct": round(v/sub_total*100, 2)}
                for k, v in cc.most_common(20)
            ],
        }

    llm_subset = [r for r in classified if not r["is_instance_descendant"]]
    inst_subset = [r for r in classified if r["is_instance_descendant"]]

    stats = {
        "ALL": stats_for(classified),
        "LLM_EMITTED": stats_for(llm_subset),
        "INSIDE_INSTANCE": stats_for(inst_subset),
    }
    with (OUT_DIR / "part1_stats.json").open("w") as f:
        json.dump(stats, f, indent=2)

    llm_95 = stats["LLM_EMITTED"].get("coverage_N_for_95pct")
    log("stats", "ok", f"LLM-emitted top-K for 95% = {llm_95} constructs")
    conn.close()
    return stats


if __name__ == "__main__":
    s = analyze()
    print(json.dumps(s, indent=2))
