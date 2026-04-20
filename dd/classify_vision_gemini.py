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

v2 (post-bake-off): the catalog is enforced as an enum in Gemini's
``responseSchema``, and the prompt carries an escape hatch
(``canonical_type: "new_type"`` + ``new_type_label``) so the model
can flag a real component the catalog is missing instead of
shoehorning the crop into a close-but-wrong catalog entry. Few-shot
examples from user reviews prime the judgment.

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

# Catalog-neutral sentinel values that are ALWAYS valid in addition
# to the 54 project-specific canonical types.
_ALWAYS_VALID_TYPES = ("unsure", "new_type")


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
    *,
    few_shot_block: str = "",
) -> str:
    """v2 prompt with the 10 improvements from the first bake-off:

    - Layout-slot-naming rule (generic wrappers → container)
    - Wordmark / logo guidance (decorative brand → image)
    - Anchored confidence examples per bucket
    - Strengthened skeleton pattern rule with a positive example
    - Escape hatch ``new_type`` with ``new_type_label`` output field
    - Optional few-shot block prepended when caller supplies one
    """
    catalog_block = _format_catalog_for_prompt(catalog) if catalog else ""
    node_descriptions = "\n".join(
        _describe_candidate_compact(c) for c in candidates
    )
    n = len(candidates)
    fs = few_shot_block.strip()
    fs_section = f"\n{fs}\n" if fs else ""
    return f"""You are classifying UI nodes. Each node is shown as a spotlighted CROP — the target region is at full brightness with its bbox outlined in magenta; surrounding context is dimmed. Classify each node against a fixed catalog. This feeds a design-system compiler — accuracy matters.

## Canonical types (pick exactly one per node)

Use the behavioral description to disambiguate. The UI component that matches the *function* shown in the cropped region wins, not one that merely looks similar.
{catalog_block}
{fs_section}
## Rules

1. **One canonical type per node.** Prefer a specific catalog type when the evidence is strong. `container` and `unsure` are valid; so is `new_type` when the catalog is genuinely missing a category (see rule 8).

2. **Layout-slot names default to `container`.** Frames named `Left`, `Right`, `Center`, `Titles`, `Frame 267`, `Group 4`, etc. are almost always pure layout wrappers — classify them as `container` unless the crop shows unambiguous interactive or informational content (e.g. a pill-shaped button with a label, a clear tab indicator, an icon row). Auto-generated names like `Frame NNN` / `Group NNN` should only pick a specific type when the visual is unmistakable.

3. **Wordmarks and logos → `image`.** A frame named `wordmark`, `logo`, `brand`, `logomark` (or that shows a stylized brand name rendered as vector/text artwork at the top of a screen) is treated as an `image` — the compiler renders these as assets, not as editable text. They are NOT `heading`, `text`, `navigation_row`, or `icon_button`.

4. **Empty-frame placeholders → `skeleton`.** If the crop shows a stack of empty rounded rectangles, shimmer blocks, or repeating grey placeholder rows (a frame named `Frame 352`/`Skeleton`/`Loading` is a strong hint), classify as `skeleton`. This is NOT a `dialog` or `drawer` — it is a placeholder pattern that the renderer replaces at runtime.

5. **Trust the crop.** The bbox outline shows exactly what to classify. Surrounding dimmed context is for reference, not the target. Don't over-weight context.

6. **Reasons are evidence-based.** Cite visual signals (shape, content, affordances in the crop) AND structural context (parent, sample text, layout, child count).

7. **Confidence is calibrated and ANCHORED.**
   - **0.95+ — unambiguous.** *Example:* pill-shaped rectangle with a primary fill color and the label `Continue` — this is a `button` at 0.98.
   - **0.85–0.94 — strong signal + one minor alternative.** *Example:* a flat rectangular region with a single line of sentence-case text 14-16px in the page body — very likely `text`, could arguably be `heading` at the smallest sizes, at 0.88.
   - **0.75–0.84 — real evidence + plausible alternative.** *Example:* a small square icon with a horizontal-line glyph — could be `menu` (hamburger) OR `close` (equal sign) depending on exact stroke count; at 0.78.
   - **Below 0.75 — prefer `unsure` with a reason.** If you cannot reliably distinguish two catalog types, `unsure` beats a coin flip.
   - If more than ~70% of your verdicts are ≥0.95, you are miscalibrated — lower your confidence.

8. **Escape hatch: `new_type`.** If the crop shows a distinct, reusable UI component that you can describe and name, but NOTHING in the catalog fits, return `canonical_type: "new_type"` AND populate `new_type_label` with a snake_case noun for the new type (e.g. `segmented_control`, `chip_group`, `availability_pill`). Use `new_type` ONLY when you're confident the component is real and the catalog is missing it — use `unsure` when the crop itself is ambiguous. Do not invent labels for frames that are just layout wrappers (those are `container`).

9. **Every (screen_id, node_id) in the input must appear in the output exactly once.** {n} nodes total.

## Nodes to classify

Each node below is paired with ONE image block, in the same order.

{node_descriptions}

## Output format

Return a single JSON object with one key, `classifications`, mapping to an array. Each array element is an object with these fields:
- `screen_id` (integer)
- `node_id` (integer)
- `canonical_type` (string — one of the catalog types above, or `unsure`, or `new_type`)
- `new_type_label` (string, snake_case — ONLY populated when `canonical_type == "new_type"`, otherwise omit or set to null)
- `confidence` (number between 0.0 and 1.0)
- `reason` (string — one short sentence of evidence)

Return JSON only. No prose, no code fences."""


def _canonical_types_from_catalog(
    catalog: list[dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in catalog:
        name = entry.get("canonical_name")
        if isinstance(name, str) and name and name not in seen:
            seen.add(name)
            out.append(name)
    for special in _ALWAYS_VALID_TYPES:
        if special not in seen:
            out.append(special)
    return out


def build_response_schema(
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Gemini responseSchema with canonical_type constrained to the
    catalog's 54 types plus `unsure` and `new_type`. This is the
    structured-output equivalent of "pick from the list".
    """
    return {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "screen_id": {"type": "integer"},
                        "node_id": {"type": "integer"},
                        "canonical_type": {
                            "type": "string",
                            "enum": _canonical_types_from_catalog(catalog),
                        },
                        "new_type_label": {
                            "type": "string",
                            "nullable": True,
                        },
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "screen_id", "node_id", "canonical_type",
                        "confidence", "reason",
                    ],
                },
            },
        },
        "required": ["classifications"],
    }


def _default_gemini_call(
    *,
    prompt: str,
    images: list[bytes],
    api_key: str,
    model: str,
    response_schema: Optional[dict[str, Any]] = None,
    timeout: float = 60.0,
    retries: int = 2,
) -> dict[str, Any]:
    """Default HTTP poster. Mirrors visual_inspect._default_gemini_call
    but supports multi-image content blocks (one per candidate) and
    optional ``response_schema`` for catalog-enum constraints.
    """
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for img in images:
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(img).decode("ascii"),
            }
        })
    generation_config: dict[str, Any] = {
        "response_mime_type": "application/json",
        "temperature": 0.0,
    }
    if response_schema is not None:
        generation_config["response_schema"] = response_schema
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
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
        entry: dict[str, Any] = {
            "screen_id": sid,
            "node_id": nid,
            "canonical_type": ctype,
            "confidence": float(c.get("confidence", 0.5)),
            "reason": str(c.get("reason", ""))[:500],
        }
        label = c.get("new_type_label")
        if ctype == "new_type" and isinstance(label, str) and label:
            entry["new_type_label"] = label
        out.append(entry)
    return out


def classify_crops_gemini(
    candidates: list[dict[str, Any]],
    crops: dict[tuple[int, int], bytes],
    *,
    api_key: str,
    catalog: Optional[list[dict[str, Any]]] = None,
    model: str = DEFAULT_MODEL,
    few_shot_block: str = "",
    use_response_schema: bool = True,
    call_fn: Optional[Callable[..., dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Classify pre-cropped UI nodes via a single Gemini call.

    Contract matches ``dd.classify_vision_batched.classify_crops_batch``:
    ``candidates`` is a list of node dicts; ``crops`` maps
    ``(screen_id, node_id)`` to PNG bytes. Candidates without a matching
    crop are filtered before the API call.

    ``few_shot_block`` is a pre-formatted string (see
    ``dd.classify_few_shot.format_few_shot_block``). When non-empty,
    it's injected after the catalog listing.

    ``use_response_schema`` toggles the catalog-enum structured-output
    constraint. Disable for tests / providers that don't support it.

    Returns a list of classification dicts (screen_id, node_id,
    canonical_type, confidence, reason, and optionally new_type_label
    when canonical_type == "new_type").
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

    prompt = build_gemini_crops_prompt(
        [c for c, _ in paired], catalog,
        few_shot_block=few_shot_block,
    )
    images = [img for _, img in paired]
    poster = call_fn if call_fn is not None else _default_gemini_call
    call_kwargs: dict[str, Any] = dict(
        prompt=prompt, images=images, api_key=api_key, model=model,
    )
    if use_response_schema and catalog:
        call_kwargs["response_schema"] = build_response_schema(catalog)
    raw = poster(**call_kwargs)
    return _parse_classifications(raw)
