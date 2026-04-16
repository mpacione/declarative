"""Experiment B — Cassowary layout reconstruction.

Stress-tests the architectural claim: "LLM never emits coordinates; a
constraint solver resolves them from structure + soft intent."

For each test screen we strip x, y (and relative_transform) from every
node, keep the structural layout properties, and let Kiwi (Cassowary)
compute positions. We then compare reconstructed bboxes to ground truth
via IoU.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

import kiwisolver as kw


DB_PATH = Path("/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db")
OUT_DIR = Path("/Users/mattpacione/declarative-build/experiments/B-solver")
ACTIVITY_LOG = OUT_DIR / "activity.log"


# ---------------------------------------------------------------------------
# Activity log helpers

def log(screen_id: int | str, stage: str, status: str, detail: str = "") -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"{ts} | {screen_id} | {stage} | {status} | {detail}\n"
    with ACTIVITY_LOG.open("a") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Data loading

NODE_COLS = [
    "id", "figma_node_id", "parent_id", "name", "node_type",
    "sort_order", "depth",
    "x", "y", "width", "height",
    "layout_mode", "padding_top", "padding_right",
    "padding_bottom", "padding_left",
    "item_spacing", "counter_axis_spacing",
    "primary_align", "counter_align",
    "layout_sizing_h", "layout_sizing_v",
    "layout_wrap",
    "min_width", "max_width", "min_height", "max_height",
    "constraint_h", "constraint_v",
    "layout_positioning",
    "rotation",
    "visible",
]


def load_screen(conn: sqlite3.Connection, screen_id: int) -> tuple[dict, list[dict]]:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    )
    s = cur.fetchone()
    screen = {"id": s[0], "name": s[1], "width": s[2], "height": s[3]}

    sql = f"SELECT {', '.join(NODE_COLS)} FROM nodes WHERE screen_id = ? ORDER BY depth, sort_order"
    cur.execute(sql, (screen_id,))
    nodes = []
    for row in cur.fetchall():
        nodes.append(dict(zip(NODE_COLS, row)))
    return screen, nodes


def build_tree(nodes: list[dict]) -> tuple[dict[int, dict], dict[int, list[int]], int | None]:
    """Return (node_by_id, children_by_parent, root_id)."""
    node_by_id: dict[int, dict] = {}
    children: dict[int, list[int]] = {}
    root_id: int | None = None

    for n in nodes:
        node_by_id[n["id"]] = n
        children.setdefault(n["id"], [])

    for n in nodes:
        pid = n["parent_id"]
        if pid is None:
            root_id = n["id"]
        else:
            children.setdefault(pid, []).append(n["id"])

    for pid, ids in children.items():
        ids.sort(key=lambda nid: node_by_id[nid]["sort_order"])

    return node_by_id, children, root_id


# ---------------------------------------------------------------------------
# Cassowary solver construction

class SolverContext:
    """One solver per screen, accumulating constraints across the tree."""

    def __init__(self) -> None:
        self.solver = kw.Solver()
        self.vars: dict[tuple[int, str], kw.Variable] = {}
        self.dropped_conflicts: list[str] = []

    def var(self, node_id: int, axis: str) -> kw.Variable:
        key = (node_id, axis)
        v = self.vars.get(key)
        if v is None:
            v = kw.Variable(f"n{node_id}_{axis}")
            self.vars[key] = v
        return v

    def add(self, constraint: kw.Constraint, tag: str = "") -> bool:
        try:
            self.solver.addConstraint(constraint)
            return True
        except Exception as exc:  # noqa: BLE001
            self.dropped_conflicts.append(f"{tag}: {exc}")
            return False


# Strength helpers.  Order, from strongest to weakest, is determined by
# how the constraints stack.  We use kiwi's built-in strengths.

STRONG = kw.strength.strong
MEDIUM = kw.strength.medium
WEAK = kw.strength.weak
REQUIRED = kw.strength.required


# ---------------------------------------------------------------------------
# Per-node constraint generation

def add_root_anchor(ctx: SolverContext, root: dict) -> None:
    """Anchor the root frame at its ground-truth x/y/w/h."""
    nid = root["id"]
    x = ctx.var(nid, "x")
    y = ctx.var(nid, "y")
    w = ctx.var(nid, "w")
    h = ctx.var(nid, "h")
    ctx.add(x == root["x"], f"root anchor x {nid}")
    ctx.add(y == root["y"], f"root anchor y {nid}")
    ctx.add(w == root["width"], f"root anchor w {nid}")
    ctx.add(h == root["height"], f"root anchor h {nid}")


def add_size_constraints(ctx: SolverContext, node: dict) -> None:
    """Size constraints based on sizing mode.  Intrinsic W/H is kept as data,
    so FIXED becomes a hard equality; HUG/FILL are weaker.  Also declares
    position variables with a WEAK default at 0 so every node has them — if
    no stronger constraint pins the position, the solver picks 0 and we at
    least get a defined output."""
    nid = node["id"]
    x = ctx.var(nid, "x")
    y = ctx.var(nid, "y")
    w = ctx.var(nid, "w")
    h = ctx.var(nid, "h")

    # We keep width/height as intrinsic data (they are not coordinates).
    # Even HUG/FILL nodes ultimately need a width — we honour the stored
    # width as the "solved intrinsic" but do it at a weaker strength so
    # parent-driven FILL can override.
    lsh = node.get("layout_sizing_h")
    lsv = node.get("layout_sizing_v")

    wgt_w = STRONG if lsh == "FIXED" else MEDIUM
    wgt_h = STRONG if lsv == "FIXED" else MEDIUM

    ctx.add((w == float(node["width"])) | wgt_w, f"size w n{nid} {lsh}")
    ctx.add((h == float(node["height"])) | wgt_h, f"size h n{nid} {lsv}")
    # WEAK default on position so every node is reachable via updateVariables.
    ctx.add((x == 0.0) | WEAK, f"xdefault n{nid}")
    ctx.add((y == 0.0) | WEAK, f"ydefault n{nid}")


def add_auto_layout_children(ctx: SolverContext, parent: dict, children_nodes: list[dict]) -> None:
    """Lay children out inside an auto-layout parent."""
    lm = parent["layout_mode"]
    if lm not in ("HORIZONTAL", "VERTICAL"):
        return

    pid = parent["id"]
    pad_l = parent.get("padding_left") or 0.0
    pad_r = parent.get("padding_right") or 0.0
    pad_t = parent.get("padding_top") or 0.0
    pad_b = parent.get("padding_bottom") or 0.0
    gap = parent.get("item_spacing") or 0.0
    primary = parent.get("primary_align") or "MIN"
    counter = parent.get("counter_align") or "MIN"

    # NOTE: layout_wrap == "WRAP" is NOT handled.  Naïve axis-swap gave a
    # small net regression (the children of WRAP parents are not always
    # single-row).  Honest flex-wrap would need a line-breaking pass that
    # considers children widths + available axis length.  Counted as a
    # limitation in the memo.

    px = ctx.var(pid, "x")
    py = ctx.var(pid, "y")
    pw = ctx.var(pid, "w")
    ph = ctx.var(pid, "h")

    # Filter out of the flow: (a) absolute-positioned floaters and (b)
    # invisible children.  Figma's auto-layout skips both — invisibility is
    # an implicit layout input.  ADR-006 "ABSOLUTE" children are allowed to
    # have a coordinate-derived baseline per the spec.
    in_flow = [
        c for c in children_nodes
        if c.get("layout_positioning") != "ABSOLUTE"
        and c.get("visible", 1) != 0
    ]

    if not in_flow:
        return

    if lm == "HORIZONTAL":
        # Primary axis = X
        primary_start = px + pad_l
        primary_end = px + pw - pad_r
        counter_lo = py + pad_t
        counter_hi = py + ph - pad_b
        primary_size_key = "w"
        counter_size_key = "h"
        primary_pos_key = "x"
        counter_pos_key = "y"
    else:  # VERTICAL
        primary_start = py + pad_t
        primary_end = py + ph - pad_b
        counter_lo = px + pad_l
        counter_hi = px + pw - pad_r
        primary_size_key = "h"
        counter_size_key = "w"
        primary_pos_key = "y"
        counter_pos_key = "x"

    # Primary-axis stacking with gaps.
    total_gap = gap * max(0, len(in_flow) - 1)
    # Sum of children primary sizes (used for SPACE_BETWEEN/MAX/CENTER).
    children_primary = [ctx.var(c["id"], primary_size_key) for c in in_flow]
    primary_sum = children_primary[0]
    for v in children_primary[1:]:
        primary_sum = primary_sum + v

    # Where does the stack start?
    if primary == "MIN":
        cursor = primary_start
    elif primary == "MAX":
        # Stack ends at primary_end.  cursor = primary_end - total_size - total_gap
        cursor = primary_end - primary_sum - total_gap
    elif primary == "CENTER":
        cursor = (primary_start + primary_end - primary_sum - total_gap) * 0.5
    elif primary == "SPACE_BETWEEN":
        cursor = primary_start
        # gap is dynamic: (available - primary_sum) / (n-1)
        if len(in_flow) > 1:
            avail = primary_end - primary_start
            gap_expr = (avail - primary_sum) * (1.0 / (len(in_flow) - 1))
            # For SPACE_BETWEEN gap expression replaces the constant gap.
            # Implement by overriding below.
            gap = None  # sentinel
            dyn_gap = gap_expr
        else:
            cursor = primary_start
    else:
        # Fallback: treat as MIN.
        cursor = primary_start

    for i, child in enumerate(in_flow):
        cid = child["id"]
        cpos = ctx.var(cid, primary_pos_key)
        csize = ctx.var(cid, primary_size_key)
        # Primary axis position.
        ctx.add(cpos == cursor, f"al primary n{cid}")
        if primary == "SPACE_BETWEEN" and len(in_flow) > 1:
            cursor = cpos + csize + dyn_gap
        else:
            cursor = cpos + csize + (gap if gap is not None else 0.0)

    # Counter-axis placement per child.
    inner = counter_hi - counter_lo
    for child in in_flow:
        cid = child["id"]
        cpos = ctx.var(cid, counter_pos_key)
        csize = ctx.var(cid, counter_size_key)
        c_align = counter
        # FILL sizing on counter axis: stretch to parent's inner box.
        cls_key = "layout_sizing_v" if lm == "HORIZONTAL" else "layout_sizing_h"
        if child.get(cls_key) == "FILL":
            ctx.add((csize == inner) | STRONG, f"al counter fill n{cid}")
        if c_align == "MIN":
            ctx.add(cpos == counter_lo, f"al counter MIN n{cid}")
        elif c_align == "MAX":
            ctx.add(cpos == counter_hi - csize, f"al counter MAX n{cid}")
        elif c_align == "CENTER":
            ctx.add(cpos == (counter_lo + counter_hi - csize) * 0.5, f"al counter CENTER n{cid}")
        elif c_align == "BASELINE":
            # Treat as MIN for now.
            ctx.add(cpos == counter_lo, f"al counter BASELINE n{cid}")

    # Primary-axis FILL: children with FILL on the primary axis should expand
    # to fill remaining space.  We implement this by adding a soft constraint
    # that FILL children have equal sizes (a rudimentary flex:1 approximation).
    fill_key = "layout_sizing_h" if lm == "HORIZONTAL" else "layout_sizing_v"
    fill_children = [c for c in in_flow if c.get(fill_key) == "FILL"]
    if fill_children and len(fill_children) > 1:
        first = ctx.var(fill_children[0]["id"], primary_size_key)
        for c in fill_children[1:]:
            other = ctx.var(c["id"], primary_size_key)
            ctx.add((other == first) | WEAK, f"fill equal n{c['id']}")

    # HUG parent on primary axis: constrain parent primary size to match stacked.
    if parent.get("layout_sizing_h" if lm == "HORIZONTAL" else "layout_sizing_v") == "HUG":
        parent_primary = pw if lm == "HORIZONTAL" else ph
        pad_primary = pad_l + pad_r if lm == "HORIZONTAL" else pad_t + pad_b
        ctx.add((parent_primary == primary_sum + total_gap + pad_primary) | MEDIUM,
                f"hug primary n{pid}")


def add_non_auto_children(ctx: SolverContext, parent: dict, children_nodes: list[dict]) -> None:
    """Handle children of a non-auto-layout parent via constraint_h/v.

    Since we've dropped coordinates, we don't know where these children want
    to sit.  The constraint_h/v tells us which edges to pin to the parent
    but not the offset.  For LEFT/TOP we pin to the parent's origin.  For
    RIGHT/BOTTOM we pin to the far edge with zero offset.  LEFT_RIGHT /
    TOP_BOTTOM stretches.  SCALE/SCALE preserves the child's relative
    position within the parent as a fraction.  In all cases this will be
    wrong for any floater whose offset can't be inferred from structure —
    which is the whole point of the experiment.
    """
    pid = parent["id"]
    px = ctx.var(pid, "x")
    py = ctx.var(pid, "y")
    pw = ctx.var(pid, "w")
    ph = ctx.var(pid, "h")

    for child in children_nodes:
        cid = child["id"]
        cx = ctx.var(cid, "x")
        cy = ctx.var(cid, "y")
        cw = ctx.var(cid, "w")
        ch = ctx.var(cid, "h")

        ch_h = child.get("constraint_h") or "LEFT"
        ch_v = child.get("constraint_v") or "TOP"

        # Horizontal axis
        if ch_h == "LEFT":
            ctx.add((cx == px) | MEDIUM, f"ca LEFT n{cid}")
        elif ch_h == "RIGHT":
            ctx.add((cx + cw == px + pw) | MEDIUM, f"ca RIGHT n{cid}")
        elif ch_h == "CENTER":
            ctx.add((cx + cw * 0.5 == px + pw * 0.5) | MEDIUM, f"ca HCENTER n{cid}")
        elif ch_h == "LEFT_RIGHT":
            ctx.add((cx == px) | MEDIUM, f"ca LR-left n{cid}")
            ctx.add((cx + cw == px + pw) | MEDIUM, f"ca LR-right n{cid}")
        elif ch_h == "SCALE":
            # No offset info; pin to parent origin as a weak default.
            ctx.add((cx == px) | WEAK, f"ca SCALE-x n{cid}")

        # Vertical axis
        if ch_v == "TOP":
            ctx.add((cy == py) | MEDIUM, f"ca TOP n{cid}")
        elif ch_v == "BOTTOM":
            ctx.add((cy + ch == py + ph) | MEDIUM, f"ca BOTTOM n{cid}")
        elif ch_v == "CENTER":
            ctx.add((cy + ch * 0.5 == py + ph * 0.5) | MEDIUM, f"ca VCENTER n{cid}")
        elif ch_v == "TOP_BOTTOM":
            ctx.add((cy == py) | MEDIUM, f"ca TB-top n{cid}")
            ctx.add((cy + ch == py + ph) | MEDIUM, f"ca TB-bottom n{cid}")
        elif ch_v == "SCALE":
            ctx.add((cy == py) | WEAK, f"ca SCALE-y n{cid}")


# ---------------------------------------------------------------------------
# Driver

def reconstruct(screen: dict, nodes: list[dict]) -> tuple[dict[int, tuple[float, float, float, float]], SolverContext]:
    node_by_id, children_by_parent, root_id = build_tree(nodes)
    if root_id is None:
        raise RuntimeError("no root")

    ctx = SolverContext()

    # Sizes for every node first (intrinsic).
    for n in nodes:
        add_size_constraints(ctx, n)

    # Root anchor.
    add_root_anchor(ctx, node_by_id[root_id])

    # Walk tree depth-first.  For each parent, decide auto-layout vs constraint.
    def visit(nid: int) -> None:
        parent = node_by_id[nid]
        kids = [node_by_id[cid] for cid in children_by_parent.get(nid, [])]
        if not kids:
            return
        if parent.get("layout_mode") in ("HORIZONTAL", "VERTICAL"):
            add_auto_layout_children(ctx, parent, kids)
        else:
            add_non_auto_children(ctx, parent, kids)
        for c in kids:
            visit(c["id"])

    visit(root_id)

    ctx.solver.updateVariables()

    # Read out solved bboxes.
    rec: dict[int, tuple[float, float, float, float]] = {}
    for n in nodes:
        nid = n["id"]
        x = ctx.vars[(nid, "x")].value()
        y = ctx.vars[(nid, "y")].value()
        w = ctx.vars[(nid, "w")].value()
        h = ctx.vars[(nid, "h")].value()
        rec[nid] = (x, y, w, h)

    return rec, ctx


# ---------------------------------------------------------------------------
# Metrics

def iou(bb1: tuple[float, float, float, float], bb2: tuple[float, float, float, float]) -> float:
    x1, y1, w1, h1 = bb1
    x2, y2, w2, h2 = bb2
    if w1 <= 0 or h1 <= 0 or w2 <= 0 or h2 <= 0:
        return 0.0
    ix1 = max(x1, x2)
    iy1 = max(y1, y2)
    ix2 = min(x1 + w1, x2 + w2)
    iy2 = min(y1 + h1, y2 + h2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    union = w1 * h1 + w2 * h2 - inter
    if union <= 0:
        return 0.0
    return inter / union


# ---------------------------------------------------------------------------
# Main

def process_screen(conn: sqlite3.Connection, screen_id: int, writer: csv.writer) -> dict:
    log(screen_id, "load", "start")
    screen, nodes = load_screen(conn, screen_id)
    log(screen_id, "load", "ok", f"{len(nodes)} nodes")

    log(screen_id, "solve", "start")
    try:
        rec, ctx = reconstruct(screen, nodes)
    except Exception as exc:  # noqa: BLE001
        log(screen_id, "solve", "fail", str(exc))
        raise
    log(screen_id, "solve", "ok",
        f"{len(ctx.vars)} vars; {len(ctx.dropped_conflicts)} dropped")

    # Build helper: node by id.  "al_parent" flag means the immediate parent is
    # auto-layout, so the solver had enough structural information to place
    # this child locally.  "al_chain" means every proper ancestor up to (but
    # not including) the root is auto-layout — the strict version.
    node_by_id = {n["id"]: n for n in nodes}
    is_al_parent: dict[int, bool] = {}

    for n in nodes:
        pid = n["parent_id"]
        if pid is None:
            is_al_parent[n["id"]] = False
            continue
        parent = node_by_id.get(pid)
        is_al_parent[n["id"]] = (
            parent is not None
            and parent.get("layout_mode") in ("HORIZONTAL", "VERTICAL")
        )

    # Per-node metrics.
    ious: list[float] = []
    local_ious_al: list[float] = []
    local_ious_nonal: list[float] = []
    by_type: dict[str, list[float]] = {}
    ioubucket = {"gt95": 0, "85_95": 0, "70_85": 0, "lt70": 0}
    al_ious: list[float] = []
    non_al_ious: list[float] = []
    skipped_invisible = 0
    for n in nodes:
        nid = n["id"]
        visible_flag = n.get("visible", 1) != 0
        gt = (float(n["x"]), float(n["y"]), float(n["width"]), float(n["height"]))
        rx, ry, rw, rh = rec[nid]
        score = iou(gt, (rx, ry, rw, rh))
        # Invisible nodes are written to the CSV but excluded from aggregates.
        # They don't render, and Figma's auto-layout skips them on the parent
        # side — any "error" on them isn't meaningful.
        if not visible_flag:
            skipped_invisible += 1
            pid = n["parent_id"]
            local_iou_str = ""
            if pid is not None and pid in node_by_id:
                p = node_by_id[pid]
                gt_local = (gt[0] - p["x"], gt[1] - p["y"], gt[2], gt[3])
                prx, pry, _, _ = rec[pid]
                rec_local = (rx - prx, ry - pry, rw, rh)
                local_iou_str = f"{iou(gt_local, rec_local):.6f}"
            writer.writerow([
                screen_id, nid, n["figma_node_id"], n["node_type"],
                gt[0], gt[1], gt[2], gt[3],
                rx, ry, rw, rh,
                f"{score:.6f}",
                int(is_al_parent[nid]),
                local_iou_str,
                0,
            ])
            continue
        ious.append(score)
        by_type.setdefault(n["node_type"], []).append(score)
        if score > 0.95:
            ioubucket["gt95"] += 1
        elif score >= 0.85:
            ioubucket["85_95"] += 1
        elif score >= 0.70:
            ioubucket["70_85"] += 1
        else:
            ioubucket["lt70"] += 1

        # Parent-local reconstruction.  Translate both GT and reconstructed
        # child bbox into the frame of the GT parent.  This isolates the
        # solver's local skill from cascading error from higher up.
        pid = n["parent_id"]
        local_iou_str = ""
        if pid is not None and pid in node_by_id:
            p = node_by_id[pid]
            gt_local = (gt[0] - p["x"], gt[1] - p["y"], gt[2], gt[3])
            prx, pry, _, _ = rec[pid]
            rec_local = (rx - prx, ry - pry, rw, rh)
            local_iou = iou(gt_local, rec_local)
            local_iou_str = f"{local_iou:.6f}"
            if is_al_parent[nid]:
                local_ious_al.append(local_iou)
            else:
                local_ious_nonal.append(local_iou)

        writer.writerow([
            screen_id, nid, n["figma_node_id"], n["node_type"],
            gt[0], gt[1], gt[2], gt[3],
            rx, ry, rw, rh,
            f"{score:.6f}",
            int(is_al_parent[nid]),
            local_iou_str,
            1,
        ])
        if is_al_parent[nid]:
            al_ious.append(score)
        elif pid is not None:
            non_al_ious.append(score)

    mean_iou = sum(ious) / len(ious) if ious else 0.0
    al_mean = sum(al_ious) / len(al_ious) if al_ious else 0.0
    non_al_mean = sum(non_al_ious) / len(non_al_ious) if non_al_ious else 0.0
    local_al_mean = sum(local_ious_al) / len(local_ious_al) if local_ious_al else 0.0
    local_nonal_mean = sum(local_ious_nonal) / len(local_ious_nonal) if local_ious_nonal else 0.0
    log(screen_id, "metrics", "ok",
        f"mean_iou={mean_iou:.4f} al_mean={al_mean:.4f}"
        f" (n_al={len(al_ious)}) non_al_mean={non_al_mean:.4f}"
        f" local_al={local_al_mean:.4f} local_nonal={local_nonal_mean:.4f}"
        f" gt95={ioubucket['gt95']} skipped_invisible={skipped_invisible}")

    return {
        "screen_id": screen_id,
        "name": screen["name"],
        "node_count": len(nodes),
        "mean_iou": mean_iou,
        "al_mean": al_mean,
        "al_count": len(al_ious),
        "non_al_mean": non_al_mean,
        "non_al_count": len(non_al_ious),
        "local_al_mean": local_al_mean,
        "local_al_count": len(local_ious_al),
        "local_nonal_mean": local_nonal_mean,
        "local_nonal_count": len(local_ious_nonal),
        "gt95": ioubucket["gt95"],
        "b85_95": ioubucket["85_95"],
        "b70_85": ioubucket["70_85"],
        "lt70": ioubucket["lt70"],
        "by_type": by_type,
        "dropped_conflicts": ctx.dropped_conflicts,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screens-csv", default=str(OUT_DIR / "test_screens.csv"))
    ap.add_argument("--per-node-csv", default=str(OUT_DIR / "results_per_node.csv"))
    ap.add_argument("--summary-csv", default=str(OUT_DIR / "results_summary.csv"))
    ap.add_argument("--per-type-csv", default=str(OUT_DIR / "per_type_iou.csv"))
    ap.add_argument("--histogram", default=str(OUT_DIR / "iou_histogram.png"))
    args = ap.parse_args()

    ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    log("all", "run", "start")

    with open(args.screens_csv) as f:
        reader = csv.DictReader(f)
        screens = [int(r["screen_id"]) for r in reader]
    log("all", "screens", "ok", f"{len(screens)} screens")

    conn = sqlite3.connect(DB_PATH)

    # Per-node CSV
    pn_file = open(args.per_node_csv, "w", newline="")
    pn_writer = csv.writer(pn_file)
    pn_writer.writerow(
        ["screen_id", "node_id", "figma_node_id", "node_type",
         "gt_x", "gt_y", "gt_w", "gt_h",
         "rec_x", "rec_y", "rec_w", "rec_h", "iou",
         "al_reachable", "local_iou", "visible"]
    )

    summaries = []
    type_agg: dict[str, list[float]] = {}
    type_local_agg: dict[str, list[float]] = {}
    all_ious: list[float] = []

    for sid in screens:
        try:
            s = process_screen(conn, sid, pn_writer)
            summaries.append(s)
            for t, ious in s["by_type"].items():
                type_agg.setdefault(t, []).extend(ious)
        except Exception as exc:  # noqa: BLE001
            log(sid, "process", "fail", str(exc))
            print(f"screen {sid} failed: {exc}", file=sys.stderr)

    pn_file.close()

    # Re-read per-node CSV to get aggregate IoU values (saves memory hassle).
    # Invisible nodes (visible=0) are filtered from metrics — they are still
    # present in the CSV for completeness but don't contribute to aggregates.
    with open(args.per_node_csv) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if int(r.get("visible", 1)) == 0:
                continue
            all_ious.append(float(r["iou"]))
            if r.get("local_iou"):
                type_local_agg.setdefault(r["node_type"], []).append(float(r["local_iou"]))

    # Summary CSV
    with open(args.summary_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["screen_id", "name", "node_count",
                    "mean_iou", "al_mean", "al_count",
                    "non_al_mean", "non_al_count",
                    "local_al_mean", "local_al_count",
                    "local_nonal_mean", "local_nonal_count",
                    "gt95", "b85_95", "b70_85", "lt70",
                    "dropped_conflicts"])
        for s in summaries:
            w.writerow([
                s["screen_id"], s["name"], s["node_count"],
                f"{s['mean_iou']:.6f}",
                f"{s['al_mean']:.6f}", s["al_count"],
                f"{s['non_al_mean']:.6f}", s["non_al_count"],
                f"{s['local_al_mean']:.6f}", s["local_al_count"],
                f"{s['local_nonal_mean']:.6f}", s["local_nonal_count"],
                s["gt95"], s["b85_95"], s["b70_85"], s["lt70"],
                len(s["dropped_conflicts"]),
            ])
        grand = sum(all_ious) / len(all_ious) if all_ious else 0.0
        n_gt95 = sum(1 for v in all_ious if v > 0.95)
        n_85 = sum(1 for v in all_ious if 0.85 <= v <= 0.95)
        n_70 = sum(1 for v in all_ious if 0.70 <= v < 0.85)
        n_lt = sum(1 for v in all_ious if v < 0.70)
        # Aggregate al / non-al
        al_total = [s["al_mean"] * s["al_count"] for s in summaries]
        al_n = sum(s["al_count"] for s in summaries)
        al_grand = sum(al_total) / al_n if al_n else 0.0
        nal_total = [s["non_al_mean"] * s["non_al_count"] for s in summaries]
        nal_n = sum(s["non_al_count"] for s in summaries)
        nal_grand = sum(nal_total) / nal_n if nal_n else 0.0
        lal_total = [s["local_al_mean"] * s["local_al_count"] for s in summaries]
        lal_n = sum(s["local_al_count"] for s in summaries)
        lal_grand = sum(lal_total) / lal_n if lal_n else 0.0
        lnal_total = [s["local_nonal_mean"] * s["local_nonal_count"] for s in summaries]
        lnal_n = sum(s["local_nonal_count"] for s in summaries)
        lnal_grand = sum(lnal_total) / lnal_n if lnal_n else 0.0
        w.writerow(["GRAND", "all", len(all_ious),
                    f"{grand:.6f}",
                    f"{al_grand:.6f}", al_n,
                    f"{nal_grand:.6f}", nal_n,
                    f"{lal_grand:.6f}", lal_n,
                    f"{lnal_grand:.6f}", lnal_n,
                    n_gt95, n_85, n_70, n_lt, ""])

    # Per-type CSV
    with open(args.per_type_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_type", "count", "mean_iou",
                    "gt95_pct", "lt70_pct",
                    "mean_local_iou", "local_gt95_pct"])
        for t, ious in sorted(type_agg.items()):
            mean = sum(ious) / len(ious)
            gt95 = sum(1 for v in ious if v > 0.95) / len(ious)
            lt70 = sum(1 for v in ious if v < 0.70) / len(ious)
            local = type_local_agg.get(t, [])
            local_mean = sum(local) / len(local) if local else 0.0
            local_gt95 = sum(1 for v in local if v > 0.95) / len(local) if local else 0.0
            w.writerow([t, len(ious), f"{mean:.6f}",
                        f"{gt95:.4f}", f"{lt70:.4f}",
                        f"{local_mean:.6f}", f"{local_gt95:.4f}"])

    # Histograms: global (absolute) + local (parent-frame).
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        local_ious = []
        with open(args.per_node_csv) as f:
            for r in csv.DictReader(f):
                if int(r.get("visible", 1)) == 0:
                    continue
                if r.get("local_iou"):
                    local_ious.append(float(r["local_iou"]))

        fig, axs = plt.subplots(1, 2, figsize=(14, 5))
        axs[0].hist(all_ious, bins=20, range=(0.0, 1.0),
                    color="#3b82f6", edgecolor="#1e40af")
        axs[0].set_xlabel("IoU (global / absolute)")
        axs[0].set_ylabel("Node count")
        axs[0].set_title(f"Global IoU — cascading error included (N={len(all_ious)})")
        axs[0].grid(alpha=0.3)

        axs[1].hist(local_ious, bins=20, range=(0.0, 1.0),
                    color="#059669", edgecolor="#064e3b")
        axs[1].set_xlabel("IoU (parent-frame / local)")
        axs[1].set_title(f"Local IoU — solver placement given correct parent (N={len(local_ious)})")
        axs[1].grid(alpha=0.3)

        fig.suptitle("Cassowary layout reconstruction — structure-only intent")
        plt.tight_layout()
        plt.savefig(args.histogram, dpi=120)
        log("all", "histogram", "ok", args.histogram)
    except Exception as exc:  # noqa: BLE001
        log("all", "histogram", "skip", str(exc))

    log("all", "run", "ok", f"mean_iou={grand:.4f} N={len(all_ious)}")
    print(f"grand mean IoU: {grand:.4f} over {len(all_ious)} nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
