"""Color normalization utilities for Figma design tokens."""

import math


def rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    """Convert RGBA 0-1 floats to hex string.

    Args:
        r: Red component (0.0 to 1.0)
        g: Green component (0.0 to 1.0)
        b: Blue component (0.0 to 1.0)
        a: Alpha component (0.0 to 1.0), defaults to 1.0

    Returns:
        6-digit hex string (#RRGGBB) if alpha = 1.0,
        8-digit hex string (#RRGGBBAA) otherwise.
    """
    # Clamp all components to [0.0, 1.0]
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))
    a = max(0.0, min(1.0, a))

    # Convert to 0-255 range
    r_byte = round(r * 255)
    g_byte = round(g * 255)
    b_byte = round(b * 255)
    a_byte = round(a * 255)

    if a == 1.0:
        # Return 6-digit hex for full opacity
        return f"#{r_byte:02X}{g_byte:02X}{b_byte:02X}"
    else:
        # Return 8-digit hex with alpha
        return f"#{r_byte:02X}{g_byte:02X}{b_byte:02X}{a_byte:02X}"


def hex_to_oklch(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color to OKLCH color space.

    Args:
        hex_color: Hex color string (#RGB, #RRGGBB, or #RRGGBBAA)

    Returns:
        Tuple of (L, C, h) where L is lightness (0-1),
        C is chroma (0-0.4 typical), h is hue in degrees (0-360).
    """
    try:
        from coloraide import Color
        c = Color(hex_color)
        oklch = c.convert("oklch")
        # Handle NaN hue for achromatic colors
        hue = oklch['hue']
        if hue is None or (isinstance(hue, float) and math.isnan(hue)):
            hue = 0.0
        return (oklch['lightness'], oklch['chroma'], hue)
    except ImportError:
        # Fall back to manual conversion
        return _srgb_to_oklch(hex_color)


def oklch_delta_e(color1: tuple[float, float, float], color2: tuple[float, float, float]) -> float:
    """Compute perceptual distance between two OKLCH colors.

    Uses Euclidean distance in OKLAB space for robustness.
    Scaled by 100 to match traditional delta-E scale where 2.0 is the JND threshold.

    Args:
        color1: (L, C, h) tuple for first color
        color2: (L, C, h) tuple for second color

    Returns:
        Delta-E distance (values < 2.0 are imperceptible).
    """
    L1, C1, h1 = color1
    L2, C2, h2 = color2

    # Convert OKLCH to OKLAB
    h1_rad = math.radians(h1)
    h2_rad = math.radians(h2)

    a1 = C1 * math.cos(h1_rad)
    b1 = C1 * math.sin(h1_rad)

    a2 = C2 * math.cos(h2_rad)
    b2 = C2 * math.sin(h2_rad)

    # Euclidean distance in OKLAB space
    dL = L1 - L2
    da = a1 - a2
    db = b1 - b2

    # Scale by 100 to match traditional delta-E scale
    return 100 * math.sqrt(dL * dL + da * da + db * db)


def oklch_invert_lightness(L: float, C: float, h: float) -> tuple[float, float, float]:
    """Invert lightness and clamp chroma for dark mode scaffolding.

    Args:
        L: Lightness (0-1)
        C: Chroma (0-0.4 typical)
        h: Hue in degrees (0-360)

    Returns:
        Tuple of (inverted_L, clamped_C, h).
    """
    new_L = 1.0 - L
    new_C = min(C, 0.4)  # Clamp chroma to prevent out-of-gamut
    return (new_L, new_C, h)


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Parse hex string to RGB 0-1 floats.

    Args:
        hex_color: Hex color string (#RGB, #RRGGBB, or #RRGGBBAA)

    Returns:
        Tuple of (r, g, b) as 0-1 floats.
    """
    # Strip leading # if present
    hex_str = hex_color.lstrip('#')

    # Handle different hex formats
    if len(hex_str) == 3:  # #RGB format
        # Expand each nibble: #F0A -> #FF00AA
        r = int(hex_str[0] * 2, 16) / 255.0
        g = int(hex_str[1] * 2, 16) / 255.0
        b = int(hex_str[2] * 2, 16) / 255.0
    elif len(hex_str) >= 6:  # #RRGGBB or #RRGGBBAA format
        r = int(hex_str[0:2], 16) / 255.0
        g = int(hex_str[2:4], 16) / 255.0
        b = int(hex_str[4:6], 16) / 255.0
    else:
        raise ValueError(f"Invalid hex color format: {hex_color}")

    return (r, g, b)


def _srgb_to_oklch(hex_color: str) -> tuple[float, float, float]:
    """Manual conversion from sRGB hex to OKLCH.

    Args:
        hex_color: Hex color string

    Returns:
        Tuple of (L, C, h) in OKLCH space.
    """
    # Get RGB components as 0-1 floats
    r, g, b = _hex_to_rgb(hex_color)

    # sRGB to Linear RGB
    def srgb_to_linear(c: float) -> float:
        if c <= 0.04045:
            return c / 12.92
        else:
            return ((c + 0.055) / 1.055) ** 2.4

    r_lin = srgb_to_linear(r)
    g_lin = srgb_to_linear(g)
    b_lin = srgb_to_linear(b)

    # Linear RGB to XYZ (D65)
    X = 0.4124564 * r_lin + 0.3575761 * g_lin + 0.1804375 * b_lin
    Y = 0.2126729 * r_lin + 0.7151522 * g_lin + 0.0721750 * b_lin
    Z = 0.0193339 * r_lin + 0.0658762 * g_lin + 0.7827228 * b_lin

    # XYZ to OKLAB
    l_ = 0.8189330101 * X + 0.3618667424 * Y - 0.1288597137 * Z
    m_ = 0.0329845436 * X + 0.9293118715 * Y + 0.0361456387 * Z
    s_ = 0.0482003018 * X + 0.2643662691 * Y + 0.6338517070 * Z

    # Cube root
    l = math.cbrt(l_)
    m = math.cbrt(m_)
    s = math.cbrt(s_)

    # To OKLAB
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    b = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s

    # OKLAB to OKLCH
    C = math.sqrt(a * a + b * b)

    # For achromatic colors (C near 0), set hue to 0
    # Also handle the case where both a and b are exactly 0 (atan2(0,0) is undefined)
    if C < 0.001 or (a == 0.0 and b == 0.0):
        h = 0.0
    else:
        h = math.degrees(math.atan2(b, a))
        # Ensure hue is in [0, 360) range
        if h < 0:
            h += 360.0

    return (L, C, h)