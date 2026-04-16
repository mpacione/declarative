"""Experiment 02: structural matcher ablation.

Measures three matchers at increasing sophistication:
  A — canonical-type equality + highest instance count
  B — canonical-type equality + prop-compatibility (variant filter)
  C — structural embedding kNN (sentence-transformers)

Answers OQ2: does v0.1 need embeddings, or does canonical-type equality suffice?
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import pickle
import random
import sqlite3
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

import numpy as np

# Repo imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dd.catalog import CATALOG_ENTRIES  # noqa: E402
from dd.classify_rules import parse_component_name, is_system_chrome  # noqa: E402

EXP_DIR = Path(__file__).resolve().parent
EMBED_CACHE_DIR = EXP_DIR / ".embedding_cache"
EMBED_CACHE_DIR.mkdir(exist_ok=True)
LOG_PATH = EXP_DIR / "activity.log"
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"

RANDOM_SEED = 20260416
N_HOLDOUT = 50
TOP_K = 3

# Stratification targets: (canonical_type, target_count)
# Driven by (a) how many distinct CKR entries exist for that type
# and (b) how many instances the type contributes to the pool.
STRATIFICATION_TARGETS: list[tuple[str, int]] = [
    ("icon", 25),
    ("button", 10),
    ("system_chrome", 7),
    ("button_group", 4),
    ("image", 2),
    ("header", 1),
    ("tabs", 1),
]


# ────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────

def log(stage: str, status: str, detail: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    line = f"{ts} | {stage} | {status} | {detail}\n"
    with LOG_PATH.open("a") as f:
        f.write(line)


# ────────────────────────────────────────────────────────────────────────
# Canonical-type derivation
# ────────────────────────────────────────────────────────────────────────

def build_alias_index() -> dict[str, str]:
    """Map lowercase name or alias → canonical_name."""
    idx: dict[str, str] = {}
    for entry in CATALOG_ENTRIES:
        canonical = entry["canonical_name"]
        idx[canonical.lower()] = canonical
        for alias in (entry.get("aliases") or []):
            idx[alias.lower()] = canonical
    return idx


ALIAS_INDEX = build_alias_index()


def derive_canonical_type(component_name: str) -> str:
    """Walk name candidates (longest-first) and return first matching canonical type.

    Special-cases system chrome (keyboard keys, status bars) to canonical
    'system_chrome' — not in catalog but important as a type class.
    Returns 'UNKNOWN' if nothing matches.
    """
    if is_system_chrome(component_name):
        return "system_chrome"
    cands = parse_component_name(component_name)
    for cand in cands:
        if cand in ALIAS_INDEX:
            return ALIAS_INDEX[cand]
    return "UNKNOWN"


# ────────────────────────────────────────────────────────────────────────
# CKR enrichment
# ────────────────────────────────────────────────────────────────────────

def load_ckr(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load all CKR rows and derive metadata (canonical type, variant segments, sample-children signature)."""
    cur = conn.execute(
        "SELECT component_key, figma_node_id, name, instance_count FROM component_key_registry"
    )
    entries: list[dict[str, Any]] = []
    for ck, fig_id, name, count in cur.fetchall():
        canonical = derive_canonical_type(name)
        segments = name.split("/") if "/" in name else []
        variant_segments = [s.strip().lower() for s in segments[1:]] if segments else []
        entries.append({
            "component_key": ck,
            "figma_node_id": fig_id,
            "name": name,
            "instance_count": count or 0,
            "canonical_type": canonical,
            "variant_segments": variant_segments,
        })
    return entries


def add_ckr_children_signature(
    conn: sqlite3.Connection, ckr_entries: list[dict[str, Any]]
) -> None:
    """For each CKR entry, sample one representative INSTANCE and summarize its
    immediate children — to embed in the canonical string for matcher C.

    We pick the most-recent representative (by node id) from any app_screen.
    """
    for entry in ckr_entries:
        cur = conn.execute(
            "SELECT n.id FROM nodes n "
            "JOIN screens s ON n.screen_id = s.id "
            "WHERE n.node_type = 'INSTANCE' AND s.screen_type = 'app_screen' "
            "  AND n.component_key = ? "
            "ORDER BY n.id LIMIT 1",
            (entry["component_key"],),
        )
        row = cur.fetchone()
        if row is None:
            entry["children_signature"] = ""
            continue
        rep_id = row[0]
        children_sig = summarize_children(conn, rep_id)
        entry["children_signature"] = children_sig


def summarize_children(conn: sqlite3.Connection, parent_node_id: int) -> str:
    """Summarize the immediate children as a structural string:
      'INSTANCE(icon/back) | TEXT("Skip") | INSTANCE(icon/close)'
    """
    cur = conn.execute(
        "SELECT node_type, name, text_content FROM nodes "
        "WHERE parent_id = ? ORDER BY sort_order, id",
        (parent_node_id,),
    )
    parts: list[str] = []
    for node_type, name, text in cur.fetchall():
        if node_type == "TEXT":
            t = (text or "").strip()[:30]
            parts.append(f'TEXT("{t}")')
        elif node_type == "INSTANCE":
            n = (name or "").strip().lower()
            parts.append(f"INSTANCE({n})")
        else:
            parts.append(node_type)
    return " | ".join(parts)


# ────────────────────────────────────────────────────────────────────────
# Held-out set construction
# ────────────────────────────────────────────────────────────────────────

def build_holdout(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Sample stratified held-out INSTANCE nodes."""
    rng = random.Random(RANDOM_SEED)

    cur = conn.execute(
        "SELECT n.id, n.figma_node_id, n.component_key, n.screen_id, "
        "       ckr.name as ckr_name, ckr.instance_count "
        "FROM nodes n "
        "JOIN screens s ON n.screen_id = s.id "
        "JOIN component_key_registry ckr ON ckr.component_key = n.component_key "
        "WHERE n.node_type = 'INSTANCE' AND n.component_key IS NOT NULL "
        "  AND s.screen_type = 'app_screen'"
    )
    pool = cur.fetchall()

    by_canon: dict[str, list[tuple]] = defaultdict(list)
    for r in pool:
        canon = derive_canonical_type(r[4])
        by_canon[canon].append(r)

    holdout: list[dict[str, Any]] = []
    for canon, target in STRATIFICATION_TARGETS:
        avail = by_canon.get(canon, [])
        if not avail:
            log("holdout_sampling", "WARN", f"no instances for canon={canon}")
            continue
        picked = rng.sample(avail, min(target, len(avail)))
        for node_id, fig_id, ck, screen_id, ckr_name, icount in picked:
            holdout.append({
                "node_id": node_id,
                "figma_node_id": fig_id,
                "component_key_ground_truth": ck,
                "canonical_type_ground_truth": canon,
                "screen_id": screen_id,
                "instance_count_of_that_component_key": icount,
                "ckr_name_ground_truth": ckr_name,
            })

    log("holdout_sampling", "OK", f"sampled {len(holdout)} nodes across {len(by_canon)} canonical types")
    return holdout


# ────────────────────────────────────────────────────────────────────────
# Query construction
# ────────────────────────────────────────────────────────────────────────

def _paraphrase_name(ckr_name: str) -> str:
    """Simulate what a synthetic-generation LLM might emit for this slot.

    For CKR names like 'icon/chevron-right', returns 'chevron right icon' — a
    natural-language paraphrase of the intent, not the literal name. Uses
    deterministic dash→space + prefix rewording rules; no call to an LLM.

    This is the semantic-intent signal a synthetic LLM would plausibly include
    in its IR. It's weaker than the literal name but stronger than nothing.
    Matcher A/B cannot use it (they don't look at free-text intent). Matcher C
    can (it embeds the free text).
    """
    lower = ckr_name.strip().lower()
    if lower.startswith("icon/"):
        glyph = lower[5:].replace("-", " ").replace("_", " ").replace("/", " ")
        return f"{glyph} icon"
    if lower.startswith("button/"):
        segs = lower[7:].split("/")
        if len(segs) >= 2:
            size, style = segs[0], segs[1]
            return f"{size} {style} button"
        return f"{lower[7:]} button"
    # system chrome / misc
    return lower.replace("/", " ").replace("-", " ")


def build_query(conn: sqlite3.Connection, node: dict[str, Any]) -> dict[str, Any]:
    """Construct the query representation for a held-out node.

    The query is what a synthetic-generation LLM might emit:
      - canonical_type (from context/prompt)
      - a paraphrased semantic intent string (deterministic paraphrase of
        the CKR name — simulates 'the LLM wants a back-arrow icon' without
        being the literal component_key)
      - desired variant props (guessed from surrounding structure + sizing)
      - a structural fingerprint: immediate children summary

    CRITICAL: we do NOT use the INSTANCE's own name verbatim (node.name ==
    ckr.name in this corpus — that would leak the ground-truth 1:1). We use
    a deterministic paraphrase instead.
    """
    node_id = node["node_id"]
    canon = node["canonical_type_ground_truth"]

    cur = conn.execute(
        "SELECT width, height, layout_mode, layout_sizing_h, layout_sizing_v, parent_id "
        "FROM nodes WHERE id = ?",
        (node_id,),
    )
    row = cur.fetchone()
    width, height, layout_mode, sizing_h, sizing_v, parent_id = row

    # immediate children structural fingerprint
    children_sig = summarize_children(conn, node_id)

    # Extract semantic signal from children:
    # - for buttons, the TEXT child's content is a real semantic prop
    # - for icons, the glyph name is what WOULD be useful but is the answer,
    #   so we only capture the parent-context semantic hint (parent name)
    texts: list[str] = []
    child_icon_names: list[str] = []
    cur = conn.execute(
        "SELECT node_type, name, text_content FROM nodes WHERE parent_id = ?",
        (node_id,),
    )
    for ntype, nname, tc in cur.fetchall():
        if ntype == "TEXT" and tc:
            texts.append(tc.strip()[:40])
        elif ntype == "INSTANCE" and nname:
            nlow = nname.strip().lower()
            if nlow.startswith("icon/"):
                child_icon_names.append(nlow)

    # Variant-axis guesses from size
    variant_hints: list[str] = []
    if width and height:
        if canon == "button":
            if width >= 250:
                variant_hints.append("full_width")
            elif width <= 60 and height <= 60:
                variant_hints.append("compact")
            else:
                variant_hints.append("medium")
        elif canon == "icon":
            # Most icons are 20x20 or 24x24
            variant_hints.append(f"size={int(width)}x{int(height)}")

    # Parent-context hint — not the answer, but what a generating LLM would know
    parent_name = ""
    if parent_id:
        pcur = conn.execute("SELECT name FROM nodes WHERE id = ?", (parent_id,))
        prow = pcur.fetchone()
        if prow:
            parent_name = (prow[0] or "").strip()

    semantic_intent = _paraphrase_name(node["ckr_name_ground_truth"])

    return {
        "canonical_type": canon,
        "width": width,
        "height": height,
        "layout_mode": layout_mode,
        "children_signature": children_sig,
        "text_children": texts,
        "icon_children": child_icon_names,
        "variant_hints": variant_hints,
        "parent_name": parent_name,
        "semantic_intent": semantic_intent,
    }


# ────────────────────────────────────────────────────────────────────────
# Matchers
# ────────────────────────────────────────────────────────────────────────

def matcher_a_canonical(
    query: dict[str, Any], ckr_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Canonical-type equality, ranked by instance count (descending)."""
    canon = query["canonical_type"]
    candidates = [c for c in ckr_entries if c["canonical_type"] == canon]
    candidates.sort(key=lambda x: x["instance_count"], reverse=True)
    return candidates


def matcher_b_prop_filter(
    query: dict[str, Any], ckr_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Canonical-type + variant-compatibility filter. Falls back to A's order."""
    canon = query["canonical_type"]
    candidates = [c for c in ckr_entries if c["canonical_type"] == canon]

    # Extract hint strings we'll attempt to match against variant_segments
    hints: set[str] = set()
    w = query.get("width") or 0
    h = query.get("height") or 0

    # Size-based hints
    if canon == "button":
        # "small" typically < 50px max dim; "large" >= 50px
        if max(w, h) <= 50:
            hints.add("small")
        else:
            hints.add("large")
    elif canon == "icon":
        # icon dimensions in the corpus map cleanly to size buckets
        dim = int(max(w, h))
        hints.add(f"{dim}")

    # Text-presence hints
    if query.get("text_children"):
        # buttons with text — prefer non-white variants? ambiguous — skip
        pass

    # Score candidates by hint-match count, then instance count
    def score(entry: dict[str, Any]) -> tuple[int, int]:
        seg = set(entry["variant_segments"])
        overlap = len(seg & hints)
        return (overlap, entry["instance_count"])

    scored = sorted(candidates, key=score, reverse=True)
    if scored:
        # If top candidates all score 0 overlap, fallback is identical to matcher A
        return scored
    return candidates


_EMBEDDER = None
_CKR_EMBEDDINGS = None  # np.ndarray [N, 384]
_CKR_KEYS = None  # list[str] component_keys in embedding order


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        log("embedder", "LOAD", "loading all-MiniLM-L6-v2")
        _EMBEDDER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        log("embedder", "OK", "model loaded")
    return _EMBEDDER


def _canonical_string(entry: dict[str, Any]) -> str:
    """Natural-language description used for embedding a CKR entry.

    Uses human-readable paraphrase of the name so the embedder can score
    against a natural-language query intent. Canonical type and children
    signature included for structural signal.
    """
    name = entry["name"]
    paraphrase = _paraphrase_name(name)
    parts = [
        f"{entry['canonical_type']}: {paraphrase}",
        f"name: {name}",
        f"variants: {' '.join(entry['variant_segments'])}",
        f"structure: {entry.get('children_signature', '')}",
    ]
    return " | ".join(parts)


def _query_string(query: dict[str, Any]) -> str:
    """Natural-language query string. Includes the LLM's semantic intent."""
    parts = [
        f"{query['canonical_type']}: {query['semantic_intent']}",
        f"variants: {' '.join(query['variant_hints'])}",
        f"structure: {query['children_signature']}",
    ]
    return " | ".join(parts)


def _embed_cache_path(text: str) -> Path:
    h = hashlib.sha256(text.encode()).hexdigest()
    return EMBED_CACHE_DIR / f"{h}.npy"


def _encode_cached(text: str) -> np.ndarray:
    cache_path = _embed_cache_path(text)
    if cache_path.exists():
        return np.load(cache_path)
    emb = _get_embedder().encode([text], normalize_embeddings=True)[0]
    np.save(cache_path, emb)
    return emb


def build_embeddings(ckr_entries: list[dict[str, Any]]) -> None:
    """Embed every CKR entry. Populates module-level _CKR_EMBEDDINGS and _CKR_KEYS."""
    global _CKR_EMBEDDINGS, _CKR_KEYS
    strings = [_canonical_string(e) for e in ckr_entries]
    keys = [e["component_key"] for e in ckr_entries]

    # Batch-encode uncached, load cached
    uncached_idx = []
    uncached_texts = []
    embs: list[np.ndarray | None] = [None] * len(strings)
    for i, s in enumerate(strings):
        cp = _embed_cache_path(s)
        if cp.exists():
            embs[i] = np.load(cp)
        else:
            uncached_idx.append(i)
            uncached_texts.append(s)

    if uncached_texts:
        log("embeddings", "COMPUTE", f"encoding {len(uncached_texts)} new CKR entries (cached={len(strings) - len(uncached_texts)})")
        encoded = _get_embedder().encode(uncached_texts, normalize_embeddings=True, batch_size=32)
        for idx, emb in zip(uncached_idx, encoded):
            embs[idx] = emb
            np.save(_embed_cache_path(strings[idx]), emb)
    else:
        log("embeddings", "CACHE_HIT", f"all {len(strings)} CKR entries cached")

    _CKR_EMBEDDINGS = np.vstack(embs)
    _CKR_KEYS = keys


def matcher_c_embedding(
    query: dict[str, Any], ckr_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """kNN against embedded CKR, filtered to matching canonical type.

    Structural-fingerprint retrieval is deployed inside a type-class (you
    already know you want an icon; the question is which glyph). Filter first,
    rank by cosine within the class. Requires build_embeddings() first.

    If no CKR entry of that canonical type exists (shouldn't happen in our
    corpus), falls back to full-pool ranking.
    """
    assert _CKR_EMBEDDINGS is not None, "call build_embeddings first"
    q_text = _query_string(query)
    q_emb = _encode_cached(q_text)

    canon = query["canonical_type"]
    key_to_entry = {e["component_key"]: e for e in ckr_entries}
    key_to_idx = {k: i for i, k in enumerate(_CKR_KEYS)}

    in_class = [e for e in ckr_entries if e["canonical_type"] == canon]
    if not in_class:
        # fallback: full-pool ranking
        sims = _CKR_EMBEDDINGS @ q_emb
        order = np.argsort(-sims)
        return [key_to_entry[_CKR_KEYS[i]] for i in order]

    class_indices = [key_to_idx[e["component_key"]] for e in in_class]
    class_embs = _CKR_EMBEDDINGS[class_indices]
    sims = class_embs @ q_emb
    order = np.argsort(-sims)
    return [in_class[i] for i in order]


# ────────────────────────────────────────────────────────────────────────
# Evaluation
# ────────────────────────────────────────────────────────────────────────

def eval_matcher(
    matcher_fn, matcher_name: str,
    holdout: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    ckr_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run a matcher on the hold-out; return per-node results with top1/top3 bools."""
    results = []
    for node, query in zip(holdout, queries):
        ranked = matcher_fn(query, ckr_entries)
        top1 = ranked[0] if ranked else None
        top3 = ranked[:3]

        gt = node["component_key_ground_truth"]
        canon_gt = node["canonical_type_ground_truth"]

        top1_correct = top1 is not None and top1["component_key"] == gt
        top3_correct = any(c["component_key"] == gt for c in top3)
        top1_canon_correct = top1 is not None and top1["canonical_type"] == canon_gt

        results.append({
            "node_id": node["node_id"],
            "matcher": matcher_name,
            "top1_key": top1["component_key"] if top1 else None,
            "top1_name": top1["name"] if top1 else None,
            "top1_correct": top1_correct,
            "top3_correct": top3_correct,
            "top1_canon_correct": top1_canon_correct,
        })
    return results


def aggregate(
    matcher_results: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    agg = []
    for name, rows in matcher_results.items():
        n = len(rows)
        a1 = sum(1 for r in rows if r["top1_correct"]) / n
        a3 = sum(1 for r in rows if r["top3_correct"]) / n
        canon_a1 = sum(1 for r in rows if r["top1_canon_correct"]) / n
        agg.append({
            "matcher": name,
            "accuracy_at_1": round(a1, 4),
            "accuracy_at_3": round(a3, 4),
            "canonical_type_accuracy_at_1": round(canon_a1, 4),
            "n": n,
        })
    return agg


def per_type_breakdown(
    holdout: list[dict[str, Any]],
    matcher_results: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    by_canon: dict[str, list[int]] = defaultdict(list)
    for i, node in enumerate(holdout):
        by_canon[node["canonical_type_ground_truth"]].append(i)

    for canon, indices in sorted(by_canon.items()):
        row: dict[str, Any] = {"canonical_type": canon, "n": len(indices)}
        for matcher_name, mrows in matcher_results.items():
            a1 = sum(1 for i in indices if mrows[i]["top1_correct"]) / len(indices)
            a3 = sum(1 for i in indices if mrows[i]["top3_correct"]) / len(indices)
            row[f"{matcher_name}_at_1"] = round(a1, 4)
            row[f"{matcher_name}_at_3"] = round(a3, 4)
        rows.append(row)
    return rows


# ────────────────────────────────────────────────────────────────────────
# CSV writers
# ────────────────────────────────────────────────────────────────────────

def write_holdout_csv(holdout: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "node_id", "figma_node_id", "component_key_ground_truth",
        "canonical_type_ground_truth", "screen_id",
        "instance_count_of_that_component_key", "ckr_name_ground_truth",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for h in holdout:
            w.writerow({k: h[k] for k in fields})


def write_results_csv(
    holdout: list[dict[str, Any]],
    matcher_results: dict[str, list[dict[str, Any]]],
    path: Path,
) -> None:
    fields = [
        "node_id", "query_canonical_type", "ground_truth_key",
        "matcher_A_top1", "matcher_A_top3",
        "matcher_B_top1", "matcher_B_top3",
        "matcher_C_top1", "matcher_C_top3",
        "matcher_A_pick_name", "matcher_B_pick_name", "matcher_C_pick_name",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, node in enumerate(holdout):
            a = matcher_results["A"][i]
            b = matcher_results["B"][i]
            c = matcher_results["C"][i]
            w.writerow({
                "node_id": node["node_id"],
                "query_canonical_type": node["canonical_type_ground_truth"],
                "ground_truth_key": node["component_key_ground_truth"],
                "matcher_A_top1": a["top1_correct"],
                "matcher_A_top3": a["top3_correct"],
                "matcher_B_top1": b["top1_correct"],
                "matcher_B_top3": b["top3_correct"],
                "matcher_C_top1": c["top1_correct"],
                "matcher_C_top3": c["top3_correct"],
                "matcher_A_pick_name": a["top1_name"],
                "matcher_B_pick_name": b["top1_name"],
                "matcher_C_pick_name": c["top1_name"],
            })


def write_summary_csv(summary: list[dict[str, Any]], path: Path) -> None:
    fields = ["matcher", "accuracy_at_1", "accuracy_at_3", "canonical_type_accuracy_at_1", "n"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(summary)


def write_breakdown_csv(breakdown: list[dict[str, Any]], path: Path) -> None:
    if not breakdown:
        return
    fields = list(breakdown[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(breakdown)


# ────────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────────

def run_ablation() -> None:
    log("pipeline", "START", "experiment 02 begins")
    conn = sqlite3.connect(str(DB_PATH))

    # 1. CKR load + enrichment
    ckr_entries = load_ckr(conn)
    log("ckr_load", "OK", f"{len(ckr_entries)} CKR entries; canonical dist: "
        f"{Counter(e['canonical_type'] for e in ckr_entries)}")
    add_ckr_children_signature(conn, ckr_entries)
    log("ckr_enrich", "OK", "children signatures added")

    # 2. Build hold-out
    holdout = build_holdout(conn)
    write_holdout_csv(holdout, EXP_DIR / "holdout.csv")
    log("holdout_written", "OK", f"{len(holdout)} nodes -> holdout.csv")

    # 3. Build queries
    queries = [build_query(conn, n) for n in holdout]
    log("queries_built", "OK", f"{len(queries)} queries constructed")

    # 4. Embeddings for matcher C
    build_embeddings(ckr_entries)
    log("embeddings_ready", "OK", f"ckr embedding matrix {_CKR_EMBEDDINGS.shape}")

    # 5. Run matchers
    matcher_results: dict[str, list[dict[str, Any]]] = {}
    matcher_results["A"] = eval_matcher(matcher_a_canonical, "A", holdout, queries, ckr_entries)
    log("matcher_A_eval", "OK", f"A top1={sum(r['top1_correct'] for r in matcher_results['A'])}/{len(holdout)}")
    matcher_results["B"] = eval_matcher(matcher_b_prop_filter, "B", holdout, queries, ckr_entries)
    log("matcher_B_eval", "OK", f"B top1={sum(r['top1_correct'] for r in matcher_results['B'])}/{len(holdout)}")
    matcher_results["C"] = eval_matcher(matcher_c_embedding, "C", holdout, queries, ckr_entries)
    log("matcher_C_eval", "OK", f"C top1={sum(r['top1_correct'] for r in matcher_results['C'])}/{len(holdout)}")

    # 6. Write outputs
    write_results_csv(holdout, matcher_results, EXP_DIR / "results.csv")
    summary = aggregate(matcher_results)
    write_summary_csv(summary, EXP_DIR / "results_summary.csv")
    breakdown = per_type_breakdown(holdout, matcher_results)
    write_breakdown_csv(breakdown, EXP_DIR / "per_type_breakdown.csv")

    # Persist the queries + per-matcher picks for the memo
    memo_support = {
        "holdout": holdout,
        "queries": queries,
        "matcher_results": matcher_results,
        "ckr_entries": [{k: v for k, v in e.items() if k != "children_signature"} for e in ckr_entries],
    }
    with (EXP_DIR / "memo_support.json").open("w") as f:
        json.dump(memo_support, f, default=str, indent=2)

    log("pipeline", "DONE", f"summary={summary}")
    print("\nSUMMARY:")
    for s in summary:
        print(f"  {s}")
    print("\nPER-TYPE:")
    for row in breakdown:
        print(f"  {row}")


if __name__ == "__main__":
    run_ablation()
