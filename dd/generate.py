"""Backward-compatible re-exports.

All rendering logic has moved to dd/renderers/figma.py.
All shared visual infrastructure has moved to dd/visual.py.

This file re-exports everything for backward compatibility.
New code should import from the specific modules directly:
  from dd.visual import build_visual_from_db, resolve_style_value
  from dd.renderers.figma import generate_figma_script, generate_screen
"""

# Shared infrastructure (renderer-agnostic)
from dd.visual import (  # noqa: F401
    build_visual_from_db,
    resolve_style_value,
    _resolve_layout_sizing,
)

# Figma renderer (platform-specific)
from dd.renderers.figma import (  # noqa: F401
    collect_fonts,
    font_weight_to_style,
    normalize_font_style,
    hex_to_figma_rgba,
    format_js_value,
    emit_from_registry,
    generate_figma_script,
    generate_screen,
    build_rebind_script_from_result,
    _emit_fills,
    _emit_effects,
    _GRADIENT_EMIT_MAP,
    _FIGMA_HANDLERS,
    _register_figma_handlers,
)
