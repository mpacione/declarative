"""Value normalization functions for converting Figma properties to binding rows."""

import json
from typing import Dict, List, Any, Optional, Union

from dd.color import rgba_to_hex


def normalize_fill(fills: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalize Figma fills to binding rows.

    Args:
        fills: Figma fills array

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    for i, fill in enumerate(fills):
        # Skip invisible fills (explicit False check)
        if fill.get("visible") is False:
            continue

        fill_type = fill.get("type")

        if fill_type == "SOLID":
            color = fill.get("color", {})
            paint_opacity = fill.get("opacity", 1.0)
            hex_color = rgba_to_hex(
                color.get("r", 0),
                color.get("g", 0),
                color.get("b", 0),
                paint_opacity
            )
            bindings.append({
                "property": f"fill.{i}.color",
                "raw_value": json.dumps(color),
                "resolved_value": hex_color
            })
        elif fill_type in ["GRADIENT_LINEAR", "GRADIENT_RADIAL", "GRADIENT_ANGULAR", "GRADIENT_DIAMOND"]:
            bindings.append({
                "property": f"fill.{i}.gradient",
                "raw_value": json.dumps(fill),
                "resolved_value": "gradient"
            })
        # Skip IMAGE fills entirely

    return bindings


def normalize_stroke(strokes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalize Figma strokes to binding rows.

    Args:
        strokes: Figma strokes array

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    for i, stroke in enumerate(strokes):
        # Skip invisible strokes (explicit False check)
        if stroke.get("visible") is False:
            continue

        stroke_type = stroke.get("type")

        if stroke_type == "SOLID":
            color = stroke.get("color", {})
            paint_opacity = stroke.get("opacity", 1.0)
            hex_color = rgba_to_hex(
                color.get("r", 0),
                color.get("g", 0),
                color.get("b", 0),
                paint_opacity
            )
            bindings.append({
                "property": f"stroke.{i}.color",
                "raw_value": json.dumps(color),
                "resolved_value": hex_color
            })
        # Skip gradients/images

    return bindings


def normalize_effect(effects: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalize Figma effects to binding rows.

    Args:
        effects: Figma effects array

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    for i, effect in enumerate(effects):
        # Skip invisible effects (explicit False check)
        if effect.get("visible") is False:
            continue

        effect_type = effect.get("type")

        if effect_type in ["DROP_SHADOW", "INNER_SHADOW"]:
            # Extract color
            color = effect.get("color", {})
            hex_color = rgba_to_hex(
                color.get("r", 0),
                color.get("g", 0),
                color.get("b", 0),
                color.get("a", 1)
            )
            bindings.append({
                "property": f"effect.{i}.color",
                "raw_value": json.dumps(color),
                "resolved_value": hex_color
            })

            # Extract radius
            radius = effect.get("radius", 0)
            bindings.append({
                "property": f"effect.{i}.radius",
                "raw_value": json.dumps(radius),
                "resolved_value": str(radius)
            })

            # Extract offset
            offset = effect.get("offset", {})
            offset_x = offset.get("x", 0)
            offset_y = offset.get("y", 0)
            bindings.append({
                "property": f"effect.{i}.offsetX",
                "raw_value": json.dumps(offset_x),
                "resolved_value": str(offset_x)
            })
            bindings.append({
                "property": f"effect.{i}.offsetY",
                "raw_value": json.dumps(offset_y),
                "resolved_value": str(offset_y)
            })

            # Extract spread
            spread = effect.get("spread", 0)
            bindings.append({
                "property": f"effect.{i}.spread",
                "raw_value": json.dumps(spread),
                "resolved_value": str(spread)
            })

        elif effect_type == "LAYER_BLUR":
            radius = effect.get("radius", 0)
            bindings.append({
                "property": f"effect.{i}.radius",
                "raw_value": json.dumps(radius),
                "resolved_value": str(radius)
            })

    return bindings


def normalize_typography(node: Dict[str, Any]) -> List[Dict[str, str]]:
    """Normalize Figma typography properties to binding rows.

    Args:
        node: Dict with typography properties (font_family, font_weight, font_size, line_height, letter_spacing)

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    # fontSize
    font_size = node.get("font_size")
    if font_size is not None and font_size != "MIXED":
        bindings.append({
            "property": "fontSize",
            "raw_value": json.dumps(font_size),
            "resolved_value": str(font_size)
        })

    # fontFamily
    font_family = node.get("font_family")
    if font_family is not None and font_family != "MIXED":
        bindings.append({
            "property": "fontFamily",
            "raw_value": json.dumps(font_family),
            "resolved_value": str(font_family)
        })

    # fontWeight
    font_weight = node.get("font_weight")
    if font_weight is not None and font_weight != "MIXED":
        bindings.append({
            "property": "fontWeight",
            "raw_value": json.dumps(font_weight),
            "resolved_value": str(font_weight)
        })

    # lineHeight
    line_height = node.get("line_height")
    if line_height is not None and line_height != "MIXED":
        if isinstance(line_height, dict):
            if line_height.get("unit") == "AUTO":
                resolved = "AUTO"
            else:
                # PIXELS or PERCENT
                resolved = str(line_height.get("value", 0))
        else:
            # Raw number
            resolved = str(line_height)
        bindings.append({
            "property": "lineHeight",
            "raw_value": json.dumps(line_height),
            "resolved_value": resolved
        })

    # letterSpacing
    letter_spacing = node.get("letter_spacing")
    if letter_spacing is not None and letter_spacing != "MIXED":
        if isinstance(letter_spacing, dict):
            if letter_spacing.get("unit") == "AUTO":
                resolved = "AUTO"
            else:
                # PIXELS or PERCENT
                resolved = str(letter_spacing.get("value", 0))
        else:
            # Raw number
            resolved = str(letter_spacing)
        bindings.append({
            "property": "letterSpacing",
            "raw_value": json.dumps(letter_spacing),
            "resolved_value": resolved
        })

    return bindings


def normalize_spacing(node: Dict[str, Any]) -> List[Dict[str, str]]:
    """Normalize Figma spacing properties to binding rows.

    Args:
        node: Dict with spacing properties (padding_*, item_spacing, counter_axis_spacing)

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    # Padding properties
    padding_map = {
        "padding_top": "padding.top",
        "padding_right": "padding.right",
        "padding_bottom": "padding.bottom",
        "padding_left": "padding.left"
    }

    for key, prop_name in padding_map.items():
        value = node.get(key)
        if value is not None and value != 0:  # Skip zero values
            bindings.append({
                "property": prop_name,
                "raw_value": json.dumps(value),
                "resolved_value": str(value)
            })

    # Item spacing
    item_spacing = node.get("item_spacing")
    if item_spacing is not None and item_spacing != 0:
        bindings.append({
            "property": "itemSpacing",
            "raw_value": json.dumps(item_spacing),
            "resolved_value": str(item_spacing)
        })

    # Counter axis spacing
    counter_axis_spacing = node.get("counter_axis_spacing")
    if counter_axis_spacing is not None and counter_axis_spacing != 0:
        bindings.append({
            "property": "counterAxisSpacing",
            "raw_value": json.dumps(counter_axis_spacing),
            "resolved_value": str(counter_axis_spacing)
        })

    return bindings


def normalize_radius(corner_radius: Optional[Union[float, int, str, Dict[str, Any]]]) -> List[Dict[str, str]]:
    """Normalize Figma corner radius to binding rows.

    Args:
        corner_radius: Either a number (uniform radius) or dict with per-corner values

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    if corner_radius is None or corner_radius == 0:
        return bindings

    # Handle JSON string
    if isinstance(corner_radius, str):
        try:
            corner_radius = json.loads(corner_radius)
        except (json.JSONDecodeError, ValueError):
            return bindings

    if isinstance(corner_radius, (int, float)):
        # Uniform radius
        if corner_radius > 0:
            bindings.append({
                "property": "cornerRadius",
                "raw_value": json.dumps(corner_radius),
                "resolved_value": str(corner_radius)
            })
    elif isinstance(corner_radius, dict):
        # Per-corner values
        corner_map = {
            "tl": "topLeftRadius",
            "tr": "topRightRadius",
            "bl": "bottomLeftRadius",
            "br": "bottomRightRadius"
        }

        for key, prop_name in corner_map.items():
            value = corner_radius.get(key, 0)
            if value > 0:
                bindings.append({
                    "property": prop_name,
                    "raw_value": json.dumps(value),
                    "resolved_value": str(value)
                })

    return bindings