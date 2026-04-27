"""Variant inducer — Stream B v0.1 (ADR-008 PR #1).

Cluster-then-label pipeline that learns per-(catalog_type, variant,
slot) → token bindings from the extracted corpus. Persisted to the
``variant_token_binding`` table for consumption by the ``ProjectCKRProvider``
at Mode-3 resolution time.

Algorithm for v0.1 (full implementation deferred; the shape of the
public API is fixed by ADR-008 and the contract tests):

1. For each catalog type with ≥ 5 classified instances in
   ``screen_component_instances``, collect a feature vector per instance
   (fill, stroke, radius, dimensions, icon-presence, adjacency).
2. K-means in OKLCH + normalised dimensions; silhouette score picks K.
3. For each cluster, send ≤ 10 rendered thumbnails plus adjacency
   context to Gemini 3.1 Pro via an injected ``vlm_call`` callable with
   a closed vocabulary of variant names.
4. Persist one row per (catalog_type, variant, slot) with the cluster's
   representative token value.

The v0.1 shell below implements the schema-level contract and the
unknown-label ``custom_N`` fallback path. The richer cluster-analysis
and VLM-prompting logic lands incrementally; tests pin the contract.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any, Optional


# Closed vocabulary from ADR-008. VLM labels not in this set persist as
# ``custom_N`` so the LLM generator retains them in prompt vocabulary.
STANDARD_VARIANTS = (
    "primary",
    "secondary",
    "destructive",
    "ghost",
    "link",
    "disabled",
)

# Slot names we attempt to bind tokens for at v0.1. Broader per-type slot
# grammars (Material's 6-slot list_item, card's new media/header split)
# are consumed by providers; the inducer focuses on the four high-value
# visual slots common to nearly every interactive type.
CORE_SLOTS = ("bg", "fg", "border", "radius")

# Confidence threshold for accepting a VLM verdict over the
# cluster-only `custom_N` fallback. Anything lower keeps the
# honest custom_N label per Phase E #4 "honest labels" contract.
DEFAULT_VLM_CONFIDENCE_THRESHOLD = 0.75

# VLM call signature: (prompt: str, images: list[bytes]) → verdict dict.
# A verdict has shape:
#   {
#     "verdict": str — variant name in STANDARD_VARIANTS or "unknown"
#     "confidence": float in [0, 1]
#     "reason": str | None — human-readable rationale (logged for triage)
#   }
VlmCall = Callable[[str, list[bytes]], dict[str, Any]]

# Image provider signature: takes a list of node_ids; returns parallel
# list of PNG bytes (or None where rendering failed/unavailable).
# A `null_image_provider` returns all-empty so the VLM relabel path
# short-circuits (cluster-only behavior is preserved). Bridge-backed
# image rendering is deferred to a Phase E #4-followon-on commit per
# Codex review (the bridge integration is the riskiest part of the
# pipeline; the VLM contract + relabel logic ships in this commit
# without it).
ImageProvider = Callable[[list[int]], list[Optional[bytes]]]


def null_vlm_call(prompt: str, images: list[bytes]) -> dict[str, Any]:
    """Default VLM call that returns 'unknown' — preserves the
    cluster-only behavior when no real VLM is wired."""
    return {"verdict": "unknown", "confidence": 0.0, "reason": "no VLM configured"}


def null_image_provider(node_ids: list[int]) -> list[Optional[bytes]]:
    """Default image provider that returns all-None — preserves the
    cluster-only behavior. Bridge-backed PNG rendering is the
    follow-on commit (Codex deferred it as the riskiest part of the
    pipeline)."""
    return [None] * len(node_ids)


# Imported lazily so tests that don't exercise the bridge path don't
# pull in the plugin_render module's subprocess machinery.
def _import_render_node_thumbnails():
    from dd.plugin_render import render_node_thumbnails
    return render_node_thumbnails


# Sentinel re-export so tests can patch
# `dd.cluster_variants.render_node_thumbnails`. Using ``__getattr__`` would
# keep the import lazy but ``patch()`` can't reach it; this is the
# pragmatic shape.
from dd.plugin_render import render_node_thumbnails  # noqa: E402


def build_bridge_image_provider(
    *,
    conn: "sqlite3.Connection",
    port: int,
    scale: int = 2,
) -> ImageProvider:
    """Build an ImageProvider closure that renders cluster-member
    thumbnails via the Figma plugin bridge.

    Translates the contract:
      ImageProvider = Callable[[list[int]], list[Optional[bytes]]]
    where input is DB ``nodes.id`` (int) and output is parallel
    PNG bytes (or None on per-node failure).

    Caches PNG bytes by ``nodes.id`` across calls within the
    closure's lifetime — induce-variants typically samples members
    from overlapping clusters; one bridge call per node is
    sufficient.

    Per Codex 2026-04-26 (gpt-5.5 high reasoning) review:
      - Toggle path is reused via ``render_node_thumbnails`` (no
        duplication of visibility-flip + finally-restore logic)
      - Hidden / nested-instance nodes still render (the bridge
        primitive walks the parent chain)
      - Bridge failures degrade to per-node None, never raise
      - Unknown DB ids degrade to None at that index

    Network calls are NOT auto-enabled by env var. The caller
    chooses to wire this provider; ``GEMINI_API_KEY`` detection
    happens at the CLI layer with explicit ``--vlm`` opt-in.
    """
    cache: dict[int, Optional[bytes]] = {}

    def _provider(node_ids: list[int]) -> list[Optional[bytes]]:
        if not node_ids:
            return []

        # Identify which node ids haven't been resolved yet.
        uncached_ids = [nid for nid in node_ids if nid not in cache]
        if uncached_ids:
            # Look up DB → figma_node_id for the uncached batch only.
            rows = conn.execute(
                f"SELECT id, figma_node_id FROM nodes WHERE id IN "
                f"({','.join('?' * len(uncached_ids))})",
                uncached_ids,
            ).fetchall()
            # Some ids may not exist in the DB at all.
            id_to_fid: dict[int, str] = {}
            for r in rows:
                # Row may be sqlite3.Row or tuple; index-access works
                # for both.
                nid = r[0]
                fid = r[1]
                if fid:
                    id_to_fid[nid] = fid

            # Mark missing ids as None in the cache so we don't
            # re-query them on subsequent calls.
            for nid in uncached_ids:
                if nid not in id_to_fid:
                    cache[nid] = None

            # Batch-render the resolvable ids via the bridge.
            resolvable_ids = [nid for nid in uncached_ids if nid in id_to_fid]
            if resolvable_ids:
                fids = [id_to_fid[nid] for nid in resolvable_ids]
                pngs = render_node_thumbnails(
                    figma_node_ids=fids,
                    port=port,
                    scale=scale,
                )
                # render_node_thumbnails returns parallel-by-fid
                for nid, png in zip(resolvable_ids, pngs):
                    cache[nid] = png

        # Build output preserving input order.
        return [cache.get(nid) for nid in node_ids]

    return _provider


def build_variant_label_prompt(
    catalog_type: str,
    cluster_index: int,
    n_clusters: int,
    variants: tuple[str, ...] = STANDARD_VARIANTS,
) -> str:
    """Build the VLM prompt for a single cluster.

    Asks the model to classify the cluster into one of the standard
    variant names (or 'unknown') based on the visual evidence.
    Returns a JSON-shaped verdict per the VlmCall contract.
    """
    variant_list = ", ".join(f'"{v}"' for v in variants)
    return (
        f"You are classifying visual variants of a UI {catalog_type} component. "
        f"This is cluster {cluster_index + 1} of {n_clusters} clusters extracted "
        f"from a design corpus. The images show representative instances of "
        f"this cluster's visual style.\n\n"
        f"Classify this cluster into ONE of the following variant names, "
        f"or return 'unknown' if none fit:\n"
        f"  Allowed variants: {variant_list}, \"unknown\"\n\n"
        f"Naming guidance:\n"
        f"  - 'primary': the dominant/main action style (often filled, "
        f"high-contrast)\n"
        f"  - 'secondary': supporting action style (often outlined or muted)\n"
        f"  - 'destructive': red/warning style for delete/remove actions\n"
        f"  - 'ghost': minimal style (often borderless, subtle background)\n"
        f"  - 'link': text-only link-styled (often underlined or accent color)\n"
        f"  - 'disabled': greyed-out / muted state\n"
        f"  - 'unknown': none of the above clearly fits\n\n"
        f"Respond ONLY with valid JSON of shape:\n"
        f'  {{"verdict": "<one of the allowed names>", '
        f'"confidence": <float 0..1>, "reason": "<short rationale>"}}'
    )


_GEMINI_VARIANT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "verdict": {
            "type": "STRING",
            "enum": list(STANDARD_VARIANTS) + ["unknown"],
        },
        "confidence": {"type": "NUMBER"},
        "reason": {"type": "STRING"},
    },
    "required": ["verdict", "confidence"],
}


def build_gemini_vlm_call(
    api_key: str,
    model: str = "gemini-2.5-flash",
) -> VlmCall:
    """Build a Gemini-backed VLM caller that satisfies the
    `VlmCall` protocol.

    Reuses dd.classify_vision_gemini._default_gemini_call (which
    already supports multi-image content blocks and JSON response
    schemas — the right plumbing per Codex's recommendation).

    Returns a closure: (prompt, images) → verdict dict in the
    standard shape. Empty images list → returns 'unknown' without
    calling the API (avoids the previous v0.1 bug where the VLM
    was invoked with no visual evidence).
    """
    from dd.classify_vision_gemini import _default_gemini_call

    def _call(prompt: str, images: list[bytes]) -> dict[str, Any]:
        if not images:
            return {
                "verdict": "unknown",
                "confidence": 0.0,
                "reason": "no images provided",
            }
        try:
            raw = _default_gemini_call(
                prompt=prompt,
                images=images,
                api_key=api_key,
                model=model,
                response_schema=_GEMINI_VARIANT_RESPONSE_SCHEMA,
            )
            text = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text")
            )
            if not text:
                return {
                    "verdict": "unknown",
                    "confidence": 0.0,
                    "reason": "no text in response",
                }
            parsed = json.loads(text)
            return {
                "verdict": str(parsed.get("verdict", "unknown")).lower(),
                "confidence": float(parsed.get("confidence", 0.0)),
                "reason": parsed.get("reason"),
            }
        except Exception as e:
            return {
                "verdict": "unknown",
                "confidence": 0.0,
                "reason": f"gemini call failed: {e!r}",
            }

    return _call


def _apply_vlm_labels(
    clusters: list[dict[str, Any]],
    catalog_type: str,
    vlm_call: VlmCall,
    image_provider: ImageProvider,
    threshold: float = DEFAULT_VLM_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Relabel clusters from `custom_N` to standard variant names
    using a VLM verdict.

    Codex review (2026-04-26, gpt-5.5 high reasoning) shape:
    - Only call VLM when image provider returns >= 1 PNG
    - Only relabel if verdict in STANDARD_VARIANTS AND confidence >= threshold
    - If verdict is 'unknown', invalid, duplicate, or low-confidence,
      keep `custom_N` and source='cluster'
    - On relabel: source='vlm'; representative_values from the medoid
      stay unchanged (cluster-derived, not VLM-derived)

    Per-cluster VLM call: each cluster gets its own call so the
    model's verdict is cluster-scoped (not corpus-scoped).
    """
    if not clusters:
        return clusters

    n = len(clusters)
    used_verdicts: set[str] = set()  # Avoid duplicate VLM-assigned variants
    relabeled: list[dict[str, Any]] = []

    for idx, cluster in enumerate(clusters):
        member_ids = cluster.get("members", [])
        if len(member_ids) < 2:
            # Singleton clusters skip VLM (no visual evidence cluster
            # to discriminate). Keep as-is.
            relabeled.append(cluster)
            continue

        # Sample the medoid + a few neighbors for VLM input. The
        # image_provider decides which subset; for now we send up
        # to 4 (the medoid plus 3 nearby).
        sample_ids = member_ids[:4]
        images = image_provider(sample_ids)
        # Drop None entries (image_provider failed for some); keep
        # the bytes that came through.
        valid_images = [img for img in images if img]
        if not valid_images:
            # No images → no VLM input → keep custom_N
            relabeled.append(cluster)
            continue

        prompt = build_variant_label_prompt(
            catalog_type, cluster_index=idx, n_clusters=n,
        )
        verdict = vlm_call(prompt, valid_images)

        v_label = (verdict.get("verdict") or "unknown").lower()
        v_conf = float(verdict.get("confidence", 0.0))

        # Relabel guards (Codex spec):
        # - verdict must be in STANDARD_VARIANTS
        # - confidence must clear threshold
        # - verdict must not be already used (duplicate prevention)
        if (
            v_label in STANDARD_VARIANTS
            and v_conf >= threshold
            and v_label not in used_verdicts
        ):
            new_cluster = dict(cluster)
            new_cluster["variant"] = v_label
            new_cluster["source"] = "vlm"
            new_cluster["confidence"] = v_conf
            new_cluster["vlm_reason"] = verdict.get("reason")
            used_verdicts.add(v_label)
            relabeled.append(new_cluster)
        else:
            # Keep cluster-only label; record VLM verdict for triage
            # but don't change the source/variant.
            new_cluster = dict(cluster)
            new_cluster["vlm_verdict"] = v_label
            new_cluster["vlm_confidence"] = v_conf
            new_cluster["vlm_reason"] = verdict.get("reason")
            relabeled.append(new_cluster)

    return relabeled


def _collect_instances(
    conn: sqlite3.Connection, catalog_type: str,
) -> list[dict[str, Any]]:
    """Return feature-vector-ready dicts for every instance of a type.

    Joins ``screen_component_instances`` → ``nodes`` and pulls the
    columns needed to build a clustering feature vector. A type with
    no classified instances returns an empty list.
    """
    rows = conn.execute(
        "SELECT sci.node_id, n.width, n.height, n.corner_radius, "
        "       n.fills, n.strokes, n.effects "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON n.id = sci.node_id "
        "WHERE sci.canonical_type = ?",
        (catalog_type,),
    ).fetchall()
    return [
        {
            "node_id": r[0],
            "width": r[1],
            "height": r[2],
            "corner_radius": r[3],
            "fills": r[4],
            "strokes": r[5],
            "effects": r[6],
        }
        for r in rows
    ]


def _cluster_and_label(
    instances: list[dict[str, Any]],
    vlm_call: VlmCall,
    catalog_type: str,
) -> list[dict[str, Any]]:
    """Return clustered variants for a catalog type.

    Phase E #4 fix (2026-04-26): cluster-only induction (no VLM).
    Pre-fix this was a v0.1 shell that treated every type as one
    cluster, called the VLM with an empty images list, and persisted
    a single ``custom_1`` row with all-NULL values — pure schema
    padding. The injected ``vlm_call`` is now ignored entirely.

    Codex 2026-04-26 (gpt-5.5 high reasoning) review:
    "Mode-3 does not need human-perfect variant names to become
    valuable; it needs real grouped instances and real representative
    values. custom_1, custom_2, etc. are acceptable if they honestly
    mean 'observed visual variant cluster.'"

    Algorithm:
    1. Build feature vectors per instance: OKLCH from primary fill,
       normalized dims, radius. Missing fields → NaN-aware distances.
    2. Pick K via silhouette over 2..min(8, n) with K=1 fallback for
       tiny/cohesive sets.
    3. K-means via simple iterative centroid assignment.
    4. For each cluster, pick the medoid (instance closest to
       centroid) as representative — produces real observed token
       values, not averages.
    5. Emit clusters with variant=custom_N, source="cluster",
       confidence proportional to cluster cohesion.

    The ``vlm_call`` parameter is retained for ABI stability but
    unused. ADR-008 Stream B's VLM-driven labeling lands when
    thumbnail rendering + Gemini integration get plumbed.

    Output shape per cluster dict:
      ``{"variant": str, "members": list[int], "representative_values": dict, ...}``
    """
    if not instances:
        return []

    # Tiny inputs: stable single-cluster output.
    if len(instances) < 2:
        return _single_cluster(instances, variant_index=1)

    # Build feature vectors. Each instance becomes a list of floats;
    # NaN where a feature is missing (e.g. no fill).
    features = [_feature_vector(inst) for inst in instances]

    # Normalize feature dimensions so e.g. width (in 100s of pixels)
    # doesn't dominate L* (in 0..1). Per-dimension z-score with
    # NaN-aware mean/std.
    normalized = _normalize_features(features)

    # Pick K via silhouette over 2..min(8, n). Smaller K wins on tie.
    k_candidates = list(range(2, min(8, len(instances)) + 1))
    if not k_candidates:
        return _single_cluster(instances, variant_index=1)

    best_k = 1
    best_score = -1.0
    best_assignments: list[int] = [0] * len(instances)

    for k in k_candidates:
        assignments, _ = _kmeans(normalized, k)
        score = _silhouette(normalized, assignments, k)
        if score > best_score + 1e-6:
            best_score = score
            best_k = k
            best_assignments = assignments

    # If no K beat the K=1 baseline (silhouette < 0.1 typically means
    # the data is barely clusterable), fall back to single cluster.
    if best_score < 0.1:
        return _single_cluster(instances, variant_index=1)

    # Build clusters from assignments.
    clusters: list[dict[str, Any]] = []
    for cluster_idx in range(best_k):
        member_indices = [
            i for i, a in enumerate(best_assignments) if a == cluster_idx
        ]
        if not member_indices:
            continue
        members = [instances[i] for i in member_indices]
        # Medoid: the member whose feature vector is closest to the
        # cluster centroid. Real observed values, not averages.
        cluster_features = [normalized[i] for i in member_indices]
        centroid = _centroid(cluster_features)
        distances = [
            _euclidean(cluster_features[j], centroid)
            for j in range(len(cluster_features))
        ]
        medoid_idx = distances.index(min(distances))
        medoid_inst = members[medoid_idx]

        # Confidence ~ cohesion (1.0 = single point, lower = looser).
        # Use silhouette-derived score scaled to a confidence band.
        cohesion = max(0.5, min(0.95, 0.6 + 0.4 * best_score))

        clusters.append({
            "variant": f"custom_{cluster_idx + 1}",
            "confidence": cohesion,
            "members": [m["node_id"] for m in members],
            "source": "cluster",
            "representative_values": _representative_values(medoid_inst),
        })

    return clusters or _single_cluster(instances, variant_index=1)


def _single_cluster(
    instances: list[dict[str, Any]],
    variant_index: int,
) -> list[dict[str, Any]]:
    """Emit a single-cluster output (used for tiny/cohesive sets).

    Picks the FIRST instance as medoid since there's no clustering
    structure to optimize.
    """
    medoid_inst = instances[0] if instances else None
    return [{
        "variant": f"custom_{variant_index}",
        "confidence": 0.5 if instances else 0.0,
        "members": [inst["node_id"] for inst in instances],
        "source": "cluster",
        "representative_values": (
            _representative_values(medoid_inst)
            if medoid_inst is not None
            else {"bg": None, "fg": None, "border": None, "radius": None}
        ),
    }]


def _feature_vector(instance: dict[str, Any]) -> list[float]:
    """Extract a numeric feature vector for K-means.

    Features (in order):
      0: L* (lightness from primary fill OKLCH; NaN when no fill)
      1: C  (chroma from primary fill OKLCH)
      2: h  (hue from primary fill OKLCH; mapped to 0..1)
      3: corner_radius (px; NaN when None)
      4: width (px; clipped at 1000 for cluster-balance)
      5: height (px; clipped at 1000)

    NaN values short-circuit distance contributions per dimension —
    instances missing fills don't get punished for "having no color"
    against instances with fills.
    """
    import math

    fills = instance.get("fills")
    primary_color = _primary_solid_hex(fills)
    if primary_color:
        from dd.color import hex_to_oklch
        try:
            L, C, h = hex_to_oklch(primary_color)
        except Exception:
            L, C, h = math.nan, math.nan, math.nan
    else:
        L, C, h = math.nan, math.nan, math.nan

    radius = instance.get("corner_radius")
    radius_f = (
        float(radius)
        if isinstance(radius, (int, float))
        else math.nan
    )

    width = float(instance.get("width") or 0.0)
    height = float(instance.get("height") or 0.0)
    width = min(width, 1000.0)
    height = min(height, 1000.0)

    h_norm = (h % 360) / 360.0 if not math.isnan(h) else math.nan

    return [L, C, h_norm, radius_f, width, height]


def _primary_solid_hex(fills_json: Any) -> str | None:
    """Return the first SOLID fill's hex color from the JSON-encoded
    fills array, or None.
    """
    if not fills_json:
        return None
    if isinstance(fills_json, str):
        try:
            fills = json.loads(fills_json)
        except (ValueError, TypeError):
            return None
    elif isinstance(fills_json, list):
        fills = fills_json
    else:
        return None
    for f in fills:
        if not isinstance(f, dict):
            continue
        if f.get("type") == "SOLID":
            color = f.get("color")
            if isinstance(color, dict):
                # Figma plugin format: {r, g, b, a} in 0..1
                r = int(round(color.get("r", 0) * 255))
                g = int(round(color.get("g", 0) * 255))
                b = int(round(color.get("b", 0) * 255))
                return f"#{r:02X}{g:02X}{b:02X}"
            if isinstance(color, str) and color.startswith("#"):
                return color
    return None


def _normalize_features(
    features: list[list[float]],
) -> list[list[float]]:
    """Per-dimension z-score normalization; NaN-aware (NaN stays NaN).

    Z-score: (x - mean) / std. Computed per dimension across all
    instances. Missing values (NaN) are excluded from mean/std and
    remain NaN in the output (the distance function treats NaN as
    "unknown — no contribution this dim").
    """
    import math
    if not features:
        return []
    n_dims = len(features[0])
    means: list[float] = []
    stds: list[float] = []
    for d in range(n_dims):
        valid = [
            row[d] for row in features
            if not math.isnan(row[d])
        ]
        if not valid:
            means.append(0.0)
            stds.append(1.0)
            continue
        m = sum(valid) / len(valid)
        var = sum((x - m) ** 2 for x in valid) / len(valid)
        s = math.sqrt(var) if var > 1e-12 else 1.0
        means.append(m)
        stds.append(s)
    return [
        [
            ((row[d] - means[d]) / stds[d])
            if not math.isnan(row[d])
            else math.nan
            for d in range(n_dims)
        ]
        for row in features
    ]


def _euclidean(a: list[float], b: list[float]) -> float:
    """NaN-aware Euclidean distance: dimensions where either operand
    is NaN are skipped. Average over the dims that DID compare so
    distances are comparable across instances with different
    coverage."""
    import math
    valid = [
        (a[i] - b[i]) ** 2
        for i in range(len(a))
        if not math.isnan(a[i]) and not math.isnan(b[i])
    ]
    if not valid:
        return 0.0
    return math.sqrt(sum(valid) / len(valid))


def _centroid(features: list[list[float]]) -> list[float]:
    """Per-dimension mean; NaN-aware (NaN values excluded)."""
    import math
    if not features:
        return []
    n_dims = len(features[0])
    out: list[float] = []
    for d in range(n_dims):
        valid = [
            row[d] for row in features
            if not math.isnan(row[d])
        ]
        out.append(
            sum(valid) / len(valid) if valid else math.nan
        )
    return out


def _kmeans(
    features: list[list[float]],
    k: int,
    max_iter: int = 50,
) -> tuple[list[int], list[list[float]]]:
    """Simple K-means with deterministic seeding.

    Seeds the first K points as initial centroids (deterministic for
    reproducibility — no random module use). Returns (assignments,
    final_centroids). For the small N (corpus instances per type
    typically < 100) this is fine.
    """
    if not features or k < 1:
        return [], []
    if k >= len(features):
        return list(range(len(features))), [list(f) for f in features]

    # Deterministic seed: pick K points spread across the input by
    # index step. (Simpler than k-means++ and adequate for small N.)
    step = max(1, len(features) // k)
    centroids = [list(features[i * step]) for i in range(k)]

    assignments = [0] * len(features)
    for _ in range(max_iter):
        # Assign each point to nearest centroid.
        new_assignments = []
        for f in features:
            distances = [_euclidean(f, c) for c in centroids]
            new_assignments.append(distances.index(min(distances)))
        if new_assignments == assignments:
            break
        assignments = new_assignments
        # Recompute centroids.
        for ci in range(k):
            members = [
                features[i] for i, a in enumerate(assignments) if a == ci
            ]
            if members:
                centroids[ci] = _centroid(members)
    return assignments, centroids


def _silhouette(
    features: list[list[float]],
    assignments: list[int],
    k: int,
) -> float:
    """Average silhouette score across all points.

    s(i) = (b - a) / max(a, b) where:
      a = mean intra-cluster distance for point i
      b = mean nearest-other-cluster distance for point i
    Output range [-1, 1]; higher = better separation.
    """
    if k <= 1 or not features:
        return 0.0
    n = len(features)
    silhouettes: list[float] = []
    for i in range(n):
        cluster_i = assignments[i]
        same_cluster = [
            features[j] for j, a in enumerate(assignments)
            if a == cluster_i and j != i
        ]
        if not same_cluster:
            silhouettes.append(0.0)
            continue
        a_i = sum(
            _euclidean(features[i], f) for f in same_cluster
        ) / len(same_cluster)

        # Mean distance to nearest OTHER cluster
        b_i = float("inf")
        for ck in range(k):
            if ck == cluster_i:
                continue
            other_cluster = [
                features[j] for j, a in enumerate(assignments)
                if a == ck
            ]
            if not other_cluster:
                continue
            d = sum(
                _euclidean(features[i], f) for f in other_cluster
            ) / len(other_cluster)
            if d < b_i:
                b_i = d
        if b_i == float("inf"):
            silhouettes.append(0.0)
            continue
        denom = max(a_i, b_i)
        silhouettes.append((b_i - a_i) / denom if denom > 0 else 0.0)
    return sum(silhouettes) / len(silhouettes) if silhouettes else 0.0


def _representative_values(instance: dict[str, Any]) -> dict[str, Any]:
    """Extract observed slot values from a medoid instance.

    Returns dict with keys: bg, fg, border, radius. Each is a real
    observed value (hex color, integer radius, etc.) or None when
    absent. The medoid is a real instance from the cluster — these
    are observed values, not averages.
    """
    bg = _primary_solid_hex(instance.get("fills"))
    border = _primary_solid_hex(instance.get("strokes"))
    radius_raw = instance.get("corner_radius")
    radius_val: Any
    if isinstance(radius_raw, (int, float)):
        radius_val = (
            int(radius_raw)
            if float(radius_raw).is_integer()
            else float(radius_raw)
        )
    else:
        radius_val = None
    # `fg` is harder to infer without per-text-child analysis; the
    # medoid's strokes are sometimes a proxy for fg-on-bg, but for
    # v1 cluster-only we leave fg=None. Phase E #4 follow-on (VLM
    # Stream B) can fill it.
    return {
        "bg": bg,
        "fg": None,
        "border": border,
        "radius": radius_val,
    }


def _persist_bindings(
    conn: sqlite3.Connection,
    catalog_type: str,
    clusters: list[dict[str, Any]],
) -> int:
    """Write one row per (catalog_type, variant, slot) to
    ``variant_token_binding``. Returns the number of rows written."""
    written = 0
    for cluster in clusters:
        variant = cluster["variant"]
        confidence = cluster["confidence"]
        source = cluster["source"]
        values = cluster["representative_values"]
        for slot in CORE_SLOTS:
            conn.execute(
                "INSERT OR REPLACE INTO variant_token_binding "
                "(catalog_type, variant, slot, token_id, literal_value, "
                " confidence, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    catalog_type,
                    variant,
                    slot,
                    None,
                    json.dumps(values.get(slot)) if values.get(slot) else None,
                    confidence,
                    source,
                ),
            )
            written += 1
    conn.commit()
    return written


def induce_variants(
    conn: sqlite3.Connection,
    vlm_call: VlmCall,
    catalog_types: list[str] | None = None,
    *,
    image_provider: ImageProvider | None = None,
) -> dict[str, int]:
    """Induce variant bindings for each catalog type and persist.

    Returns a dict ``{catalog_type: rows_written}`` for every type that
    had at least one instance. Types below the 5-instance threshold are
    short-circuited — if there is nothing to cluster, a single
    ``custom_1`` placeholder row is still written so providers have a
    fallback binding shape (keeps the LLM vocabulary complete).

    Phase E #4 follow-on (2026-04-26): when ``vlm_call`` is non-null
    AND ``image_provider`` returns real PNG bytes for cluster
    members, _apply_vlm_labels relabels custom_N → standard variant
    names (primary, secondary, destructive, etc.). When images are
    unavailable (default ``null_image_provider``), the cluster-only
    custom_N labels are preserved.

    Codex 2026-04-26 (gpt-5.5 high reasoning) review: ship VLM
    labeling contract + Gemini adapter NOW; thumbnail rendering via
    bridge is a separate follow-on commit. Default behavior is
    cluster-only (matches Phase E #4 shipped behavior); VLM
    relabeling is opt-in via the image_provider parameter.
    """
    written: dict[str, int] = {}
    if image_provider is None:
        image_provider = null_image_provider

    if catalog_types is None:
        rows = conn.execute(
            "SELECT DISTINCT canonical_type FROM screen_component_instances"
        ).fetchall()
        catalog_types = [r[0] for r in rows]
        if not catalog_types:
            # Empty SCI (classify stage hasn't run). Fall back to the full
            # catalog so every known type gets at least a custom_1
            # placeholder row — gives ProjectCKRProvider something to
            # query at Mode-3 resolution time.
            from dd.catalog import CATALOG_ENTRIES
            catalog_types = [entry["canonical_name"] for entry in CATALOG_ENTRIES]

    for catalog_type in catalog_types:
        instances = _collect_instances(conn, catalog_type)

        # Below-threshold types still produce a placeholder binding so
        # downstream consumers have a row to query.
        if len(instances) < 5:
            clusters = [
                {
                    "variant": "custom_1",
                    "confidence": 0.0,
                    "members": [inst["node_id"] for inst in instances],
                    "source": "cluster",
                    "representative_values": {slot: None for slot in CORE_SLOTS},
                },
            ]
        else:
            clusters = _cluster_and_label(instances, vlm_call, catalog_type)

        # Phase E #4 follow-on: apply VLM labels when wired.
        # _apply_vlm_labels short-circuits each cluster individually
        # if the image_provider returns no images for that cluster's
        # members, so partial coverage degrades gracefully to
        # cluster-only labels for the unimaged clusters.
        clusters = _apply_vlm_labels(
            clusters, catalog_type, vlm_call, image_provider,
        )

        written[catalog_type] = _persist_bindings(conn, catalog_type, clusters)

    return written
