"""Renderer package — platform-specific backends.

Each renderer transforms the renderer-agnostic visual dict (from dd.visual)
into platform-specific output (Figma JS, React JSX, SwiftUI, etc.).

The shared infrastructure lives in dd.visual:
  - build_visual_from_db — renderer-agnostic visual dict
  - _resolve_layout_sizing — pure sizing logic
  - resolve_style_value — token reference resolution

See docs/cross-platform-value-formats.md for how each platform
represents design properties.

Available renderers:
  - dd.renderers.figma — Figma Plugin API (JavaScript)
"""
