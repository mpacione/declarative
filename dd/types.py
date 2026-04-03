"""Shared constants and type definitions for the DD pipeline."""

import enum


class DeviceClass(str, enum.Enum):
    """Device classification for screens."""
    IPHONE = "iphone"
    IPAD_11 = "ipad_11"
    IPAD_13 = "ipad_13"
    WEB = "web"
    COMPONENT_SHEET = "component_sheet"
    UNKNOWN = "unknown"


class BindingStatus(str, enum.Enum):
    """Status of node-token bindings."""
    UNBOUND = "unbound"
    PROPOSED = "proposed"
    BOUND = "bound"
    OVERRIDDEN = "overridden"


class Tier(str, enum.Enum):
    """Token tier classification."""
    EXTRACTED = "extracted"
    CURATED = "curated"
    ALIASED = "aliased"


class SyncStatus(str, enum.Enum):
    """Synchronization status between Figma and code."""
    PENDING = "pending"
    FIGMA_ONLY = "figma_only"
    CODE_ONLY = "code_only"
    SYNCED = "synced"
    DRIFTED = "drifted"


class RunStatus(str, enum.Enum):
    """Extraction run status."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScreenExtractionStatus(str, enum.Enum):
    """Screen extraction status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Severity(str, enum.Enum):
    """Validation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DTCGType(str, enum.Enum):
    """DTCG v2025.10 compatible types."""
    COLOR = "color"
    DIMENSION = "dimension"
    FONT_FAMILY = "fontFamily"
    FONT_WEIGHT = "fontWeight"
    NUMBER = "number"
    SHADOW = "shadow"
    BORDER = "border"
    TRANSITION = "transition"
    GRADIENT = "gradient"


class ComponentCategory(str, enum.Enum):
    """Intent-based categories for canonical UI component types."""
    ACTIONS = "actions"
    SELECTION_AND_INPUT = "selection_and_input"
    CONTENT_AND_DISPLAY = "content_and_display"
    NAVIGATION = "navigation"
    FEEDBACK_AND_STATUS = "feedback_and_status"
    CONTAINMENT_AND_OVERLAY = "containment_and_overlay"


VALID_CATEGORIES: frozenset[str] = frozenset(c.value for c in ComponentCategory)


class ClassificationSource(str, enum.Enum):
    """How a component instance was classified."""
    FORMAL = "formal"
    HEURISTIC = "heuristic"
    LLM = "llm"
    VISION = "vision"
    MANUAL = "manual"


# Device classification mapping
DEVICE_DIMENSIONS: dict[tuple[int, int], DeviceClass] = {
    (428, 926): DeviceClass.IPHONE,
    (834, 1194): DeviceClass.IPAD_11,
    (1536, 1152): DeviceClass.IPAD_13,
}

# Component sheet name heuristics (lowercase for case-insensitive comparison)
COMPONENT_SHEET_KEYWORDS: list[str] = [
    "buttons",
    "controls",
    "components",
    "modals",
    "popups",
    "icons",
    "website",
    "assets",
]

# Non-semantic node name prefixes (case-sensitive from Figma)
NON_SEMANTIC_PREFIXES: tuple[str, ...] = (
    "Frame",
    "Group",
    "Rectangle",
    "Vector",
)

# Semantic node types (always semantic)
SEMANTIC_NODE_TYPES: frozenset[str] = frozenset({"TEXT", "INSTANCE", "COMPONENT"})

# Property path patterns
FILL_COLOR_PATTERN = "fill.{}.color"
STROKE_COLOR_PATTERN = "stroke.{}.color"
EFFECT_FIELD_PATTERN = "effect.{}.{}"

# Property groupings
PADDING_PROPERTIES: tuple[str, ...] = (
    "padding.top",
    "padding.right",
    "padding.bottom",
    "padding.left",
)

SPACING_PROPERTIES: tuple[str, ...] = (
    "itemSpacing",
    "counterAxisSpacing",
)

TYPOGRAPHY_PROPERTIES: tuple[str, ...] = (
    "fontSize",
    "fontFamily",
    "fontWeight",
    "lineHeight",
    "letterSpacing",
)

DIMENSION_PROPERTIES: tuple[str, ...] = (
    "cornerRadius",
    "opacity",
)


def classify_device(width: float, height: float) -> DeviceClass:
    """
    Classify a screen's device type based on its dimensions.

    Args:
        width: Screen width (will be rounded to int)
        height: Screen height (will be rounded to int)

    Returns:
        DeviceClass corresponding to the dimensions
    """
    width_int = round(width)
    height_int = round(height)
    return DEVICE_DIMENSIONS.get((width_int, height_int), DeviceClass.UNKNOWN)


def is_component_sheet_name(name: str) -> bool:
    """
    Check if a frame name indicates a component sheet.

    Args:
        name: Frame name to check

    Returns:
        True if the name contains component sheet keywords
    """
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in COMPONENT_SHEET_KEYWORDS)