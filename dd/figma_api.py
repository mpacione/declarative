"""Figma REST API client and node tree conversion.

Fetches file data via the Figma REST API and converts the response
into the dict format expected by parse_extraction_response().
"""

import json
import time
from typing import Any, Optional

import requests

FIGMA_API_BASE = "https://api.figma.com/v1"
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with exponential backoff on 429 rate limits."""
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        retry_after = float(resp.headers.get("Retry-After", backoff))
        wait = max(retry_after, backoff)
        print(f"  Rate limited, waiting {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
        time.sleep(wait)
        backoff *= 2
    resp.raise_for_status()
    return resp


def get_file_tree(
    file_key: str, token: str, page_id: Optional[str] = None, depth: Optional[int] = None
) -> dict:
    """Fetch file structure from Figma REST API.

    When page_id is given, uses the /nodes endpoint scoped to that page.
    Otherwise fetches the full file.
    """
    headers = {"X-Figma-Token": token}

    if page_id and depth is not None:
        resp = _request_with_retry("GET",
            f"{FIGMA_API_BASE}/files/{file_key}/nodes",
            headers=headers,
            params={"ids": page_id, "depth": depth},
        )
    elif depth is not None:
        resp = _request_with_retry("GET",
            f"{FIGMA_API_BASE}/files/{file_key}",
            headers=headers,
            params={"depth": depth},
        )
    else:
        resp = _request_with_retry("GET",
            f"{FIGMA_API_BASE}/files/{file_key}",
            headers=headers,
        )

    return resp.json()


def get_screen_nodes(
    file_key: str, token: str, screen_ids: list[str]
) -> dict:
    """Fetch full node trees for one or more screens.

    Uses GET /v1/files/:key/nodes with the ids parameter.
    """
    headers = {"X-Figma-Token": token}
    ids_param = ",".join(screen_ids)

    resp = _request_with_retry("GET",
        f"{FIGMA_API_BASE}/files/{file_key}/nodes",
        headers=headers,
        params={"ids": ids_param},
    )
    return resp.json()


def extract_top_level_frames(
    file_json: dict,
    page_id: Optional[str] = None,
    from_nodes_endpoint: bool = False,
) -> list[dict]:
    """Extract top-level frame metadata from a file or nodes response.

    Returns list of dicts matching the populate_screens() contract:
    {figma_node_id, name, width, height}
    """
    if from_nodes_endpoint:
        node_key = page_id if page_id else next(iter(file_json["nodes"]))
        page = file_json["nodes"][node_key]["document"]
    else:
        pages = file_json["document"]["children"]
        if page_id:
            page = next((p for p in pages if p["id"] == page_id), None)
            if page is None:
                raise ValueError(f"Page {page_id} not found in file")
        else:
            page = pages[0]

    frames = []
    for child in page.get("children", []):
        if child["type"] not in ("FRAME", "COMPONENT", "COMPONENT_SET"):
            continue

        bbox = child.get("absoluteBoundingBox", {})
        frames.append({
            "figma_node_id": child["id"],
            "name": child["name"],
            "width": bbox.get("width", 0),
            "height": bbox.get("height", 0),
        })

    return frames


def convert_node_tree(
    api_node: dict,
    parent_idx: Optional[int] = None,
    depth: int = 0,
    sort_order: int = 0,
    result: Optional[list] = None,
) -> list[dict]:
    """Recursively convert a Figma REST API node tree to extraction format.

    Each node becomes a dict matching the contract of parse_extraction_response().
    """
    if result is None:
        result = []

    my_idx = len(result)

    node = _convert_single_node(api_node, parent_idx, depth, sort_order)
    result.append(node)

    for i, child in enumerate(api_node.get("children", [])):
        convert_node_tree(child, parent_idx=my_idx, depth=depth + 1, sort_order=i, result=result)

    return result


def _convert_single_node(
    api_node: dict, parent_idx: Optional[int], depth: int, sort_order: int
) -> dict:
    """Convert a single REST API node dict to extraction format."""
    bbox = api_node.get("absoluteBoundingBox")

    node: dict[str, Any] = {
        "figma_node_id": api_node["id"],
        "name": api_node["name"],
        "node_type": api_node["type"],
        "parent_idx": parent_idx,
        "depth": depth,
        "sort_order": sort_order,
        "x": bbox["x"] if bbox else None,
        "y": bbox["y"] if bbox else None,
        "width": bbox["width"] if bbox else None,
        "height": bbox["height"] if bbox else None,
    }

    _add_visual_properties(node, api_node)
    _add_layout_properties(node, api_node)
    _add_typography_properties(node, api_node)
    _add_component_reference(node, api_node)

    return node


def _add_visual_properties(node: dict, api_node: dict) -> None:
    fills = api_node.get("fills", [])
    if fills:
        node["fills"] = json.dumps(fills)

    strokes = api_node.get("strokes", [])
    if strokes:
        node["strokes"] = json.dumps(strokes)

    effects = api_node.get("effects", [])
    if effects:
        node["effects"] = json.dumps(effects)

    _add_corner_radius(node, api_node)

    if "opacity" in api_node:
        node["opacity"] = api_node["opacity"]

    if api_node.get("blendMode"):
        node["blend_mode"] = api_node["blendMode"]

    node["visible"] = api_node.get("visible", True)


def _add_corner_radius(node: dict, api_node: dict) -> None:
    mixed = api_node.get("rectangleCornerRadii")
    uniform = api_node.get("cornerRadius")

    if mixed and not all(v == mixed[0] for v in mixed):
        node["corner_radius"] = json.dumps({
            "tl": mixed[0],
            "tr": mixed[1],
            "bl": mixed[3],
            "br": mixed[2],
        })
    elif uniform is not None and uniform != 0:
        node["corner_radius"] = uniform


def _add_layout_properties(node: dict, api_node: dict) -> None:
    layout_mode = api_node.get("layoutMode")
    if not layout_mode or layout_mode == "NONE":
        return

    node["layout_mode"] = layout_mode

    field_map = {
        "paddingTop": "padding_top",
        "paddingRight": "padding_right",
        "paddingBottom": "padding_bottom",
        "paddingLeft": "padding_left",
        "itemSpacing": "item_spacing",
        "counterAxisSpacing": "counter_axis_spacing",
        "primaryAxisAlignItems": "primary_align",
        "counterAxisAlignItems": "counter_align",
        "layoutSizingHorizontal": "layout_sizing_h",
        "layoutSizingVertical": "layout_sizing_v",
    }

    for api_key, db_key in field_map.items():
        value = api_node.get(api_key)
        if value is not None:
            node[db_key] = value


def _add_typography_properties(node: dict, api_node: dict) -> None:
    if api_node.get("type") != "TEXT":
        return

    style = api_node.get("style", {})
    if not style:
        return

    if style.get("fontFamily"):
        node["font_family"] = style["fontFamily"]

    if style.get("fontWeight") is not None:
        node["font_weight"] = int(style["fontWeight"])

    if style.get("fontSize") is not None:
        node["font_size"] = float(style["fontSize"])

    if style.get("textAlignHorizontal"):
        node["text_align"] = style["textAlignHorizontal"]

    if api_node.get("characters") is not None:
        node["text_content"] = api_node["characters"]

    _add_line_height(node, style)
    _add_letter_spacing(node, style)


def _add_line_height(node: dict, style: dict) -> None:
    unit = style.get("lineHeightUnit")
    if not unit:
        return

    if unit == "INTRINSIC_%":
        node["line_height"] = json.dumps({"unit": "AUTO"})
    elif unit == "PIXELS":
        node["line_height"] = json.dumps({
            "value": style.get("lineHeightPx", 0),
            "unit": "PIXELS",
        })
    elif unit == "FONT_SIZE_%":
        node["line_height"] = json.dumps({
            "value": style.get("lineHeightPercent", 100),
            "unit": "PERCENT",
        })


def _add_letter_spacing(node: dict, style: dict) -> None:
    spacing = style.get("letterSpacing")
    if spacing is None:
        return

    node["letter_spacing"] = json.dumps({
        "value": spacing,
        "unit": "PIXELS",
    })


def _add_component_reference(node: dict, api_node: dict) -> None:
    if api_node.get("type") == "INSTANCE" and api_node.get("componentId"):
        node["component_figma_id"] = api_node["componentId"]
