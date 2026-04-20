"""Gemini 2.5 Flash vision classifier — side-channel to Anthropic PS/CS.

Mirrors the ``classify_crops_batch`` contract in
``dd.classify_vision_batched`` so a bake-off can drop in alongside the
existing pipeline without touching ``run_classification_v2``. Chosen
over Pro after ``feedback_vlm_transient_retries.md`` — Flash is faster,
more reliable for batched runs, and enough for categorical output
against a fixed catalog.

HTTP plumbing reuses the same stdlib pattern as
``dd.visual_inspect._default_gemini_call``: no google-sdk dependency.
Function calling is swapped for ``response_mime_type: application/json``
+ explicit JSON schema instructions in the prompt.

The ``call_fn`` parameter is injectable for tests and any future
transport swap (e.g. batched generateContent, different auth).
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from dd.classify_llm import _format_catalog_for_prompt


DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
_RETRY_BACKOFF_S = 2.0


def _describe_candidate_compact(c: dict[str, Any]) -> str:
    parts = [
        f"node_id={c['node_id']}",
        f"screen_id={c['screen_id']}",
        f'name="{c["name"]}"',
        f"type={c['node_type']}",
    ]
    total = c.get("total_children")
    if total:
        dist = c.get("child_type_dist") or {}
        parts.append(
            f"children={total}"
            f" ({', '.join(f'{k}:{v}' for k, v in dist.items())})"
        )
    if c.get("sample_text"):
        t = str(c["sample_text"])[:60]
        parts.append(f'sample_text="{t}"')
    if c.get("parent_classified_as"):
        parts.append(f"parent={c['parent_classified_as']}")
    if c.get("ckr_registered_name"):
        parts.append(f'component_key="{c["ckr_registered_name"]}"')
    return "  - " + "; ".join(parts)


def build_gemini_crops_prompt(
    candidates: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> str:
    catalog_block = _format_catalog_for_prompt(catalog) if catalog else ""
    node_descriptions = "\n".join(
        _describe_candidate_compact(c) for c in candidates
    )
    n = len(candidates)
    return f"""You are classifying UI nodes. Each node is shown as a spotlighted CROP — the target region is at full brightness with its bbox outlined in magenta; surrounding context is dimmed. Classify each node against a fixed catalog. This feeds a design-system compiler — accuracy matters, and "unsure" is a valid answer.

## Canonical types (pick exactly one per node)

Use the behavioral description to disambiguate. The UI component that matches the *function* shown in the cropped region wins, not one that merely looks similar.
{catalog_block}

## Rules

1. **One canonical type per node.** `container` and `unsure` are valid; prefer a specific type when evidence supports it.

2. **Confidence is calibrated.**
   - **0.95+** — unambiguous.
   - **0.85–0.94** — strong signal + minor alternative.
   - **0.75–0.84** — real evidence + plausible alternative.
   - **Below 0.75** — prefer `unsure` with a reason.

3. **Trust the crop.** The bbox outline shows exactly what to classify. Surrounding dimmed context is for reference, not the target.

4. **Don't regress to `container` when specific evidence exists.** Distinctive name, characteristic glyph, sample text, known pattern → classify specifically.

5. **Empty-frame grid → `skeleton`.** Decorative-child pattern (3 ellipses, 2 chevrons, 4 dots) → single `icon`.

6. **Reasons are evidence-based.** Cite visual signals (shape, content, affordances in the crop) AND structural context (parent, sample text, layout, child count).

7. **Every (screen_id, node_id) in the input must appear in the output exactly once.** {n} nodes total.

## Nodes to classify

Each node below is paired with ONE image block, in the same order.

{node_descriptions}

## Output format

Return a single JSON object with one key, `classifications`, mapping to an array. Each array element is an object with these fields:
- `screen_id` (integer)
- `node_id` (integer)
- `canonical_type` (string — one of the canonical types above)
- `confidence` (number between 0.0 and 1.0)
- `reason` (string — one short sentence of evidence)

Return JSON only. No prose, no code fences."""


def _default_gemini_call(
    *,
    prompt: str,
    images: list[bytes],
    api_key: str,
    model: str,
    timeout: float = 60.0,
    retries: int = 2,
) -> dict[str, Any]:
    """Default HTTP poster. Mirrors visual_inspect._default_gemini_call
    but supports multi-image content blocks (one per candidate).
    """
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for img in images:
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(img).decode("ascii"),
            }
        })
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }
    endpoint = GEMINI_ENDPOINT_TEMPLATE.format(model=model)
    url = f"{endpoint}?key={api_key}"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt < retries:
                time.sleep(_RETRY_BACKOFF_S ** (attempt + 1))
                continue
            raise
    raise RuntimeError(  # pragma: no cover
        f"Gemini call exhausted retries: {last_error}"
    )


def _extract_text(raw: dict[str, Any]) -> Optional[str]:
    try:
        return raw["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _parse_classifications(raw: dict[str, Any]) -> list[dict[str, Any]]:
    text = _extract_text(raw)
    if not text:
        return []
    try:
        data = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError:
        return []
    classifications = data.get("classifications") if isinstance(data, dict) else None
    if not isinstance(classifications, list):
        return []
    out: list[dict[str, Any]] = []
    for c in classifications:
        if not isinstance(c, dict):
            continue
        sid = c.get("screen_id")
        nid = c.get("node_id")
        ctype = c.get("canonical_type")
        if not (isinstance(sid, int) and isinstance(nid, int)
                and isinstance(ctype, str)):
            continue
        out.append({
            "screen_id": sid,
            "node_id": nid,
            "canonical_type": ctype,
            "confidence": float(c.get("confidence", 0.5)),
            "reason": str(c.get("reason", ""))[:500],
        })
    return out


def classify_crops_gemini(
    candidates: list[dict[str, Any]],
    crops: dict[tuple[int, int], bytes],
    *,
    api_key: str,
    catalog: Optional[list[dict[str, Any]]] = None,
    model: str = DEFAULT_MODEL,
    call_fn: Optional[Callable[..., dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Classify pre-cropped UI nodes via a single Gemini call.

    Contract matches ``dd.classify_vision_batched.classify_crops_batch``:
    ``candidates`` is a list of node dicts; ``crops`` maps
    ``(screen_id, node_id)`` to PNG bytes. Candidates without a matching
    crop are filtered before the API call. Returns a list of
    classification dicts (screen_id, node_id, canonical_type,
    confidence, reason).
    """
    if not candidates:
        return []
    if catalog is None:
        catalog = []
    paired: list[tuple[dict[str, Any], bytes]] = []
    for c in candidates:
        key = (c["screen_id"], c["node_id"])
        img = crops.get(key)
        if img is not None:
            paired.append((c, img))
    if not paired:
        return []

    prompt = build_gemini_crops_prompt([c for c, _ in paired], catalog)
    images = [img for _, img in paired]
    poster = call_fn if call_fn is not None else _default_gemini_call
    raw = poster(
        prompt=prompt, images=images, api_key=api_key, model=model,
    )
    return _parse_classifications(raw)
