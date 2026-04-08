"""Figma REST API client and node tree conversion.

Fetches file data via the Figma REST API and converts the response
into the dict format expected by parse_extraction_response().
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

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
    file_key: str, token: str, page_id: str | None = None, depth: int | None = None
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
    page_id: str | None = None,
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
    parent_idx: int | None = None,
    depth: int = 0,
    sort_order: int = 0,
    result: list | None = None,
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


def _reconstruct_logical_dimensions(
    bbox_w: float, bbox_h: float, rotation_rad: float
) -> tuple[float, float]:
    """Convert AABB dimensions back to logical (pre-rotation) dimensions.

    The REST API returns absoluteBoundingBox (axis-aligned bounding box),
    which is the post-rotation envelope.  For a rectangle (w, h) rotated
    by θ the AABB is:
        aabb_w = |w·cos θ| + |h·sin θ|
        aabb_h = |w·sin θ| + |h·cos θ|

    Inverting gives logical (w, h) when cos(2θ) ≠ 0.
    """
    EPSILON = 1e-6
    if abs(rotation_rad) < EPSILON:
        return bbox_w, bbox_h

    c = abs(math.cos(rotation_rad))
    s = abs(math.sin(rotation_rad))
    det = c * c - s * s  # cos(2θ)

    if abs(det) < EPSILON:
        return bbox_w, bbox_h

    w = round((bbox_w * c - bbox_h * s) / det, 2)
    h = round((bbox_h * c - bbox_w * s) / det, 2)

    if w < 0 or h < 0:
        return bbox_w, bbox_h

    return w, h


def _convert_single_node(
    api_node: dict, parent_idx: int | None, depth: int, sort_order: int
) -> dict:
    """Convert a single REST API node dict to extraction format."""
    bbox = api_node.get("absoluteBoundingBox")

    bbox_w = bbox["width"] if bbox else None
    bbox_h = bbox["height"] if bbox else None

    rotation_rad = api_node.get("rotation")
    if rotation_rad and bbox_w is not None and bbox_h is not None:
        bbox_w, bbox_h = _reconstruct_logical_dimensions(
            bbox_w, bbox_h, rotation_rad
        )

    node: dict[str, Any] = {
        "figma_node_id": api_node["id"],
        "name": api_node["name"],
        "node_type": api_node["type"],
        "parent_idx": parent_idx,
        "depth": depth,
        "sort_order": sort_order,
        "x": bbox["x"] if bbox else None,
        "y": bbox["y"] if bbox else None,
        "width": bbox_w,
        "height": bbox_h,
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

    # Stroke properties
    if api_node.get("strokeWeight") is not None:
        node["stroke_weight"] = api_node["strokeWeight"]
    individual = api_node.get("individualStrokeWeights")
    if individual:
        node["stroke_top_weight"] = individual.get("top")
        node["stroke_right_weight"] = individual.get("right")
        node["stroke_bottom_weight"] = individual.get("bottom")
        node["stroke_left_weight"] = individual.get("left")
    if api_node.get("strokeAlign"):
        node["stroke_align"] = api_node["strokeAlign"]
    if api_node.get("strokeCap"):
        node["stroke_cap"] = api_node["strokeCap"]
    if api_node.get("strokeJoin"):
        node["stroke_join"] = api_node["strokeJoin"]
    dash = api_node.get("strokeDashes") or api_node.get("dashPattern")
    if dash:
        node["dash_pattern"] = json.dumps(dash)

    # Vector geometry (SVG path data for VECTOR, BOOLEAN_OPERATION, etc.)
    fill_geom = api_node.get("fillGeometry")
    if fill_geom:
        node["fill_geometry"] = json.dumps(fill_geom)
    stroke_geom = api_node.get("strokeGeometry")
    if stroke_geom:
        node["stroke_geometry"] = json.dumps(stroke_geom)

    # Boolean operation type
    if api_node.get("booleanOperation"):
        node["boolean_operation"] = api_node["booleanOperation"]

    # Corner smoothing (iOS-style)
    cs = api_node.get("cornerSmoothing")
    if cs is not None and cs > 0:
        node["corner_smoothing"] = cs

    # Arc data
    arc = api_node.get("arcData")
    if arc:
        node["arc_data"] = json.dumps(arc)

    # Transform
    if api_node.get("rotation") is not None:
        node["rotation"] = api_node["rotation"]
    if "clipsContent" in api_node:
        node["clips_content"] = 1 if api_node["clipsContent"] else 0

    # Mask
    if api_node.get("isMask"):
        node["is_mask"] = 1

    # Constraints
    constraints = api_node.get("constraints")
    if constraints:
        node["constraint_h"] = constraints.get("horizontal")
        node["constraint_v"] = constraints.get("vertical")


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
    # layoutPositioning is on the CHILD, not the parent — capture regardless
    lp = api_node.get("layoutPositioning")
    if lp:
        node["layout_positioning"] = lp

    # layoutSizingH/V describe how this node sizes within its PARENT's layout
    # context — valid on any node inside an auto-layout parent, not just
    # auto-layout containers themselves.
    for api_key, db_key in (
        ("layoutSizingHorizontal", "layout_sizing_h"),
        ("layoutSizingVertical", "layout_sizing_v"),
    ):
        value = api_node.get(api_key)
        if value is not None:
            node[db_key] = value

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
        "layoutWrap": "layout_wrap",
        "minWidth": "min_width",
        "maxWidth": "max_width",
        "minHeight": "min_height",
        "maxHeight": "max_height",
    }

    for api_key, db_key in field_map.items():
        value = api_node.get(api_key)
        if value is not None:
            node[db_key] = value

    # Apply known defaults for REST API omitted values
    if "layout_wrap" not in node:
        node["layout_wrap"] = "NO_WRAP"

    # Grid layout properties
    if layout_mode == "GRID":
        grid_map = {
            "gridRowCount": "grid_row_count",
            "gridColumnCount": "grid_column_count",
            "gridRowGap": "grid_row_gap",
            "gridColumnGap": "grid_column_gap",
        }
        for api_key, db_key in grid_map.items():
            value = api_node.get(api_key)
            if value is not None:
                node[db_key] = value
        for api_key, db_key in [("gridRowSizes", "grid_row_sizes"), ("gridColumnSizes", "grid_column_sizes")]:
            value = api_node.get(api_key)
            if value is not None:
                node[db_key] = json.dumps(value)


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

    if style.get("fontPostScriptName"):
        # Extract style from fontPostScriptName (e.g. "Inter-BoldItalic" → "Bold Italic")
        # Or use the explicit style field if available
        pass
    if style.get("italic") is not None:
        font_style_parts = []
        if style.get("fontWeight", 400) >= 700:
            font_style_parts.append("Bold")
        if style.get("italic"):
            font_style_parts.append("Italic")
        if font_style_parts:
            node["font_style"] = " ".join(font_style_parts)

    if style.get("paragraphSpacing") is not None:
        node["paragraph_spacing"] = float(style["paragraphSpacing"])

    if style.get("textAlignHorizontal"):
        node["text_align"] = style["textAlignHorizontal"]

    if style.get("textAlignVertical"):
        node["text_align_v"] = style["textAlignVertical"]

    if style.get("textDecoration"):
        node["text_decoration"] = style["textDecoration"]

    if style.get("textCase"):
        node["text_case"] = style["textCase"]

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
    if api_node.get("type") == "INSTANCE":
        if api_node.get("componentId"):
            node["component_figma_id"] = api_node["componentId"]
        # Component key is available at the file level in the components map,
        # not directly on the instance node in REST API.
        # It gets populated via Plugin API extraction (mainComponent.key).
