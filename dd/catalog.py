"""Universal component type catalog (T5 Phase 0).

Defines ~48 canonical UI component types organized by user intent.
This vocabulary is the foundation for classification (Phase 1),
IR generation (Phase 2), and all downstream phases.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, TypedDict


class CatalogEntry(TypedDict, total=False):
    canonical_name: str
    aliases: list[str] | None
    category: str
    behavioral_description: str
    prop_definitions: dict[str, Any] | None
    slot_definitions: dict[str, Any] | None
    # DEPRECATED: vestigial ARIA-flavoured field from T5 Phase 0. Written
    # at seed time but read nowhere in compose/render/classify/verify.
    # Kept for schema stability until a dedicated cleanup PR; do not
    # rely on for new work. Mode-3 composition uses `canonical_name`
    # for semantic category. See ADR-008.
    semantic_role: str
    recognition_heuristics: dict[str, Any] | None
    related_types: list[str] | None
    # ADR-008 PR #0: standardised variant-axis declarations. Per-axis
    # shape: {axis_name: {"values": [...], "default": str | None}}.
    # Consumed by the Mode-3 composition providers + LLM vocabulary
    # builder. Optional — types without enum-able variants omit it.
    variant_axes: dict[str, Any] | None
    # Classifier v2.1 normalization (migration 016). Read by the
    # classifier prompt builder to disambiguate near-neighbor types
    # and by dataset-export callers for ecosystem alignment.
    clay_equivalent: str | None        # Google Research CLAY taxonomy
    aria_role: str | None              # W3C WAI-ARIA role
    disambiguation_notes: str | None   # "NOT a <neighbor> because..."


# ---------------------------------------------------------------------------
# The 48 canonical UI component types
# ---------------------------------------------------------------------------

CATALOG_ENTRIES: tuple[CatalogEntry, ...] = (
    # ── Actions (6) ──────────────────────────────────────────────────────
    {
        "canonical_name": "button",
        "aliases": ["btn", "cta", "previous", "next", "new folder"],
        "category": "actions",
        "behavioral_description": "Primary interactive control that triggers an action on press.",
        "prop_definitions": {"label": "text", "variant": "enum:primary|secondary|ghost|destructive", "size": "enum:sm|md|lg", "disabled": "boolean", "icon": "slot"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": False, "position": "start", "quantity": "single"}, "label": {"allowed": ["text"], "required": True, "position": "fill", "quantity": "single"}, "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"}},
        "semantic_role": "button",
        "recognition_heuristics": {"patterns": ["frame_with_text_label", "rounded_rect_with_center_text"], "min_children": 1, "typical_height_range": [32, 56]},
        "related_types": ["icon_button", "button_group"],
        "variant_axes": {
            "variant": {"values": ["default", "primary", "secondary", "ghost", "destructive"], "default": "default"},
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "state": {"values": ["default", "hover", "focus", "pressed", "disabled", "loading"], "default": "default"},
            "tone": {"values": ["default", "primary", "destructive", "success", "warning", "info"], "default": "default"},
        },
    },
    {
        "canonical_name": "icon_button",
        "aliases": ["icon_btn"],
        "category": "actions",
        "behavioral_description": "Icon-only button without a visible text label.",
        "prop_definitions": {"icon": "slot", "variant": "enum:primary|secondary|ghost", "size": "enum:sm|md|lg", "disabled": "boolean"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": True}},
        "semantic_role": "button",
        "recognition_heuristics": {"patterns": ["small_square_frame_with_icon"], "aspect_ratio": "~1:1", "typical_size_range": [24, 48]},
        "related_types": ["button"],
    },
    {
        "canonical_name": "fab",
        "aliases": ["floating_action_button"],
        "category": "actions",
        "behavioral_description": "Prominent floating button for the primary screen action.",
        "prop_definitions": {"icon": "slot", "label": "text", "extended": "boolean"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": True}, "label": {"allowed": ["text"], "required": False}},
        "semantic_role": "button",
        "recognition_heuristics": {"patterns": ["circular_or_pill_frame", "elevated_shadow"], "position": "bottom_right_or_center", "typical_size_range": [48, 72]},
        "related_types": ["button"],
    },
    {
        "canonical_name": "button_group",
        "aliases": ["btn_group", "button_bar", "button set - leading", "button set - trailing"],
        "category": "actions",
        "behavioral_description": "A row or column of related buttons presented as a unit.",
        "prop_definitions": {"orientation": "enum:horizontal|vertical", "size": "enum:sm|md|lg"},
        "slot_definitions": {"buttons": {"allowed": ["button", "icon_button"], "required": True, "multiple": True}},
        "semantic_role": "group",
        "recognition_heuristics": {"patterns": ["row_or_column_of_buttons"], "min_children": 2, "children_type": "button"},
        "related_types": ["button", "segmented_control"],
    },
    {
        "canonical_name": "menu",
        "aliases": ["dropdown_menu", "action_menu", "context_menu", "right_click_menu"],
        "category": "actions",
        "behavioral_description": "A list of actions revealed by a trigger element.",
        "prop_definitions": {"items": "array", "trigger": "slot", "trigger_mode": "enum:click|context"},
        "slot_definitions": {"trigger": {"allowed": ["button", "icon_button"], "required": True}, "items": {"allowed": ["text", "icon"], "required": True, "multiple": True}},
        "semantic_role": "menu",
        "recognition_heuristics": {"patterns": ["trigger_plus_dropdown_list"], "has_overlay": True},
        "related_types": ["select"],
        "variant_axes": {
            "trigger_mode": {"values": ["click", "context"], "default": "click"},
        },
    },
    # ── Selection & Input (14) ───────────────────────────────────────────
    {
        "canonical_name": "checkbox",
        "aliases": ["check"],
        "category": "selection_and_input",
        "behavioral_description": "A binary or tri-state selection control for non-exclusive choices.",
        "prop_definitions": {"label": "text", "checked": "boolean", "disabled": "boolean", "indeterminate": "boolean"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}},
        "semantic_role": "checkbox",
        "recognition_heuristics": {"patterns": ["small_square_plus_text"], "indicator_shape": "square_or_rounded", "typical_indicator_size": [16, 24]},
        "related_types": ["toggle", "radio"],
    },
    {
        "canonical_name": "radio",
        "aliases": ["radio_button"],
        "category": "selection_and_input",
        "behavioral_description": "A single option within a mutually exclusive set.",
        "prop_definitions": {"label": "text", "selected": "boolean", "value": "text", "disabled": "boolean"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}},
        "semantic_role": "radio",
        "recognition_heuristics": {"patterns": ["small_circle_plus_text"], "indicator_shape": "circle", "typical_indicator_size": [16, 24]},
        "related_types": ["radio_group", "segmented_control"],
    },
    {
        "canonical_name": "radio_group",
        "aliases": ["radio_set"],
        "category": "selection_and_input",
        "behavioral_description": "A set of mutually exclusive radio options.",
        "prop_definitions": {"value": "text", "name": "text"},
        "slot_definitions": {"items": {"allowed": ["radio"], "required": True, "multiple": True}},
        "semantic_role": "radiogroup",
        "recognition_heuristics": {"patterns": ["vertical_stack_of_radios"], "min_children": 2, "children_type": "radio"},
        "related_types": ["radio", "select"],
    },
    {
        "canonical_name": "toggle",
        "aliases": ["switch", "lightswitch", "toggle_group", "switch_group"],
        "category": "selection_and_input",
        "behavioral_description": "A binary choice control that takes effect immediately.",
        "prop_definitions": {"label": "text", "value": "boolean", "disabled": "boolean", "grouped": "boolean"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}},
        "semantic_role": "switch",
        "recognition_heuristics": {"patterns": ["pill_track_with_thumb"], "aspect_ratio": "~2:1", "has_circular_thumb": True},
        "related_types": ["checkbox"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "state": {"values": ["default", "focus", "disabled"], "default": "default"},
        },
    },
    {
        "canonical_name": "select",
        "aliases": ["picker", "dropdown"],
        "category": "selection_and_input",
        "behavioral_description": "A dropdown control for choosing one option from a list.",
        "prop_definitions": {"label": "text", "value": "text", "options": "array", "disabled": "boolean", "placeholder": "text"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}, "trigger": {"allowed": ["text", "icon"], "required": True}},
        "semantic_role": "listbox",
        "recognition_heuristics": {"patterns": ["bordered_frame_with_chevron"], "has_dropdown_indicator": True},
        "related_types": ["combobox", "radio_group"],
    },
    {
        "canonical_name": "combobox",
        "aliases": ["autocomplete", "typeahead"],
        "category": "selection_and_input",
        "behavioral_description": "A text input combined with a filterable options list.",
        "prop_definitions": {"value": "text", "options": "array", "allow_custom": "boolean"},
        "slot_definitions": {"input": {"allowed": ["text_input"], "required": True}, "options": {"allowed": ["text"], "required": True, "multiple": True}},
        "semantic_role": "combobox",
        "recognition_heuristics": {"patterns": ["input_with_dropdown_list"], "has_text_input": True, "has_dropdown": True},
        "related_types": ["select", "search_input"],
    },
    {
        "canonical_name": "date_picker",
        "aliases": ["datepicker", "calendar_picker"],
        "category": "selection_and_input",
        "behavioral_description": "A control for selecting a date, typically with a calendar view.",
        "prop_definitions": {"selected": "text", "format": "text", "min_date": "text", "max_date": "text"},
        "slot_definitions": {"trigger": {"allowed": ["text_input", "button"], "required": True}},
        "semantic_role": "dialog",
        "recognition_heuristics": {"patterns": ["input_with_calendar_grid", "7_column_grid"], "has_date_grid": True},
        "related_types": ["text_input"],
    },
    {
        "canonical_name": "slider",
        "aliases": ["range_slider"],
        "category": "selection_and_input",
        "behavioral_description": "A control for selecting a numeric value by dragging along a track.",
        "prop_definitions": {"min": "number", "max": "number", "value": "number", "step": "number", "disabled": "boolean"},
        "slot_definitions": {"track": {"allowed": [], "required": True}, "thumb": {"allowed": [], "required": True}},
        "semantic_role": "slider",
        "recognition_heuristics": {"patterns": ["horizontal_track_with_thumb"], "has_track": True, "has_thumb": True},
        "related_types": ["text_input"],
    },
    {
        "canonical_name": "segmented_control",
        "aliases": ["segment", "pill_toggle"],
        "category": "selection_and_input",
        "behavioral_description": "A horizontal set of mutually exclusive options displayed as connected segments.",
        "prop_definitions": {"items": "array", "selected_index": "number"},
        "slot_definitions": {"items": {"allowed": ["text", "icon"], "required": True, "multiple": True}},
        "semantic_role": "tablist",
        "recognition_heuristics": {"patterns": ["horizontal_equal_width_segments"], "min_children": 2, "max_children": 5, "has_pill_indicator": True},
        "related_types": ["tabs", "radio_group", "toggle_group"],
    },
    {
        "canonical_name": "text_input",
        "aliases": ["input", "text_field"],
        "category": "selection_and_input",
        "behavioral_description": "A single-line text entry field.",
        "prop_definitions": {"placeholder": "text", "value": "text", "type": "enum:text|email|password|number", "disabled": "boolean", "label": "text", "helper": "text"},
        "slot_definitions": {
            "label": {"allowed": ["text"], "required": False, "position": "top", "quantity": "single"},
            "leading": {"allowed": ["icon"], "required": False, "position": "start", "quantity": "single"},
            "input": {"allowed": ["text"], "required": True, "position": "fill", "quantity": "single"},
            "trailing": {"allowed": ["icon", "button", "icon_button"], "required": False, "position": "end", "quantity": "single"},
            "helper": {"allowed": ["text"], "required": False, "position": "bottom", "quantity": "single"},
        },
        "semantic_role": "textbox",
        "recognition_heuristics": {"patterns": ["bordered_rectangle_with_padding"], "has_border": True, "single_line": True, "typical_height_range": [36, 52]},
        "related_types": ["textarea", "search_input"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "state": {"values": ["default", "focus", "disabled", "invalid"], "default": "default"},
        },
    },
    {
        "canonical_name": "textarea",
        "aliases": ["multiline_input", "text_area"],
        "category": "selection_and_input",
        "behavioral_description": "A multi-line text entry field.",
        "prop_definitions": {"placeholder": "text", "value": "text", "rows": "number", "disabled": "boolean"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}},
        "semantic_role": "textbox",
        "recognition_heuristics": {"patterns": ["tall_bordered_rectangle"], "has_border": True, "multi_line": True, "min_height": 80},
        "related_types": ["text_input"],
    },
    {
        "canonical_name": "search_input",
        "aliases": ["search_field", "search_bar"],
        "category": "selection_and_input",
        "behavioral_description": "A text input specialized for search with icon and clear affordance.",
        "prop_definitions": {"value": "text", "placeholder": "text"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": True}, "input": {"allowed": ["text"], "required": True}, "clear": {"allowed": ["icon_button"], "required": False}},
        "semantic_role": "searchbox",
        "recognition_heuristics": {"patterns": ["input_with_magnifying_glass"], "has_search_icon": True},
        "related_types": ["text_input", "combobox"],
    },
    {
        "canonical_name": "file_upload",
        "aliases": ["file_input", "dropzone"],
        "category": "selection_and_input",
        "behavioral_description": "A control for selecting and uploading files.",
        "prop_definitions": {"multiple": "boolean", "accept": "text"},
        "slot_definitions": {"label": {"allowed": ["text", "icon"], "required": True}},
        "semantic_role": "button",
        "recognition_heuristics": {"patterns": ["dashed_border_drop_zone", "button_with_upload_icon"], "has_dashed_border": True},
        "related_types": ["button"],
    },
    # ── Content & Display (13) ───────────────────────────────────────────
    {
        "canonical_name": "card",
        "aliases": ["content_card", "tile"],
        "category": "content_and_display",
        "behavioral_description": "A bounded container grouping related content and actions.",
        "prop_definitions": {"variant": "enum:elevated|outlined|filled"},
        "slot_definitions": {
            "media": {"allowed": ["image", "video", "vector"], "required": False, "position": "start", "quantity": "single"},
            "header": {"allowed": ["heading", "text"], "required": False, "position": "start", "quantity": "single"},
            "title": {"allowed": ["heading", "text"], "required": False, "position": "start", "quantity": "single"},
            "subtitle": {"allowed": ["text"], "required": False, "position": "start", "quantity": "single"},
            "body": {"allowed": ["text", "any"], "required": False, "position": "fill", "quantity": "single"},
            "supporting": {"allowed": ["text"], "required": False, "position": "fill", "quantity": "single"},
            "actions": {"allowed": ["button", "icon_button", "link", "button_group"], "required": False, "position": "end", "quantity": "multiple"},
            "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"},
        },
        "semantic_role": "article",
        "recognition_heuristics": {"patterns": ["bordered_or_shadowed_container"], "has_border_or_shadow": True, "has_padding": True, "typical_children": ["image", "text", "button"]},
        "related_types": ["list_item"],
        "variant_axes": {
            "variant": {"values": ["elevated", "outlined", "filled"], "default": "outlined"},
            "state": {"values": ["default", "hover", "pressed", "disabled"], "default": "default"},
        },
    },
    {
        "canonical_name": "avatar",
        "aliases": ["profile_image", "user_icon"],
        "category": "content_and_display",
        "behavioral_description": "A small visual representation of a user or entity.",
        "prop_definitions": {"src": "asset", "initials": "text", "size": "enum:xs|sm|md|lg|xl"},
        "slot_definitions": {"image": {"allowed": ["image"], "required": False}, "fallback": {"allowed": ["text", "icon"], "required": False}},
        "semantic_role": "img",
        "recognition_heuristics": {"patterns": ["small_circle_with_image_or_text"], "shape": "circle", "typical_size_range": [24, 64]},
        "related_types": ["icon", "image"],
    },
    {
        "canonical_name": "badge",
        "aliases": ["chip", "tag", "label"],
        "category": "content_and_display",
        "behavioral_description": "A small status indicator or categorization label.",
        "prop_definitions": {"label": "text", "variant": "enum:default|primary|secondary|destructive", "icon": "slot"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": False}, "label": {"allowed": ["text"], "required": True}},
        "semantic_role": "status",
        "recognition_heuristics": {"patterns": ["small_rounded_frame_with_short_text"], "max_text_length": 20, "has_rounded_corners": True, "typical_height_range": [20, 32]},
        "related_types": ["alert"],
    },
    {
        "canonical_name": "image",
        "aliases": ["picture", "photo", "logo"],
        "category": "content_and_display",
        "behavioral_description": "A static raster or vector image.",
        "prop_definitions": {"src": "asset", "alt": "text", "aspect_ratio": "number"},
        "slot_definitions": {},
        "semantic_role": "img",
        "recognition_heuristics": {"patterns": ["frame_with_image_fill"], "has_image_fill": True},
        "related_types": ["avatar", "icon"],
    },
    {
        "canonical_name": "icon",
        "aliases": ["glyph", "symbol", ".icons"],
        "category": "content_and_display",
        "behavioral_description": "A small symbolic graphic conveying meaning or affordance.",
        "prop_definitions": {"name": "text", "size": "enum:xs|sm|md|lg", "color": "token_ref"},
        "slot_definitions": {},
        "semantic_role": "img",
        "recognition_heuristics": {"patterns": ["small_vector_or_instance"], "node_type": "VECTOR_or_INSTANCE", "typical_size_range": [12, 32]},
        "related_types": ["icon_button", "avatar"],
    },
    {
        "canonical_name": "table",
        "aliases": ["data_table", "grid"],
        "category": "content_and_display",
        "behavioral_description": "A structured grid of rows and columns displaying tabular data.",
        "prop_definitions": {"columns": "array", "rows": "array"},
        "slot_definitions": {"header": {"allowed": ["text"], "required": True, "multiple": True}, "body": {"allowed": ["text", "badge", "button"], "required": True, "multiple": True}},
        "semantic_role": "table",
        "recognition_heuristics": {"patterns": ["grid_of_equal_height_rows"], "has_repeating_row_pattern": True, "min_columns": 2},
        "related_types": ["list"],
    },
    {
        "canonical_name": "list",
        "aliases": ["item_list"],
        "category": "content_and_display",
        "behavioral_description": "A vertical sequence of related items.",
        "prop_definitions": {"items": "array"},
        "slot_definitions": {"items": {"allowed": ["list_item"], "required": True, "multiple": True}},
        "semantic_role": "list",
        "recognition_heuristics": {"patterns": ["vertical_stack_of_similar_children"], "layout": "vertical", "min_children": 2, "children_similar": True},
        "related_types": ["list_item", "table"],
    },
    {
        "canonical_name": "list_item",
        "aliases": ["row", "cell"],
        "category": "content_and_display",
        "behavioral_description": "A single entry within a list with leading media, overline / headline / supporting content, and trailing zones (Material three-line shape).",
        "prop_definitions": {"headline": "text", "overline": "text", "supporting": "text"},
        "slot_definitions": {
            "leading": {"allowed": ["icon", "avatar", "image"], "required": False, "position": "start", "quantity": "single"},
            "overline": {"allowed": ["text"], "required": False, "position": "content", "quantity": "single"},
            "headline": {"allowed": ["text", "heading"], "required": True, "position": "content", "quantity": "single"},
            "supporting": {"allowed": ["text"], "required": False, "position": "content", "quantity": "single"},
            "trailing_supporting": {"allowed": ["text"], "required": False, "position": "end", "quantity": "single"},
            "trailing": {"allowed": ["icon", "badge", "text", "icon_button"], "required": False, "position": "end", "quantity": "single"},
        },
        "semantic_role": "listitem",
        "recognition_heuristics": {"patterns": ["horizontal_leading_content_trailing"], "layout": "horizontal", "has_three_zones": True},
        "related_types": ["list", "card", "navigation_row"],
        "variant_axes": {
            "density": {"values": ["compact", "default", "comfortable"], "default": "default"},
            "state": {"values": ["default", "hover", "pressed", "selected", "disabled"], "default": "default"},
        },
    },
    {
        "canonical_name": "heading",
        "aliases": ["title", "headline"],
        "category": "content_and_display",
        "behavioral_description": "A text element establishing section hierarchy (H1-H6).",
        "prop_definitions": {"level": "enum:h1|h2|h3|h4|h5|h6", "text": "text"},
        "slot_definitions": {},
        "semantic_role": "heading",
        "recognition_heuristics": {"patterns": ["text_node_with_large_font"], "node_type": "TEXT", "font_size_min": 18, "font_weight_min": 600},
        "related_types": ["text"],
    },
    {
        "canonical_name": "text",
        "aliases": ["paragraph", "body_text", "caption"],
        "category": "content_and_display",
        "behavioral_description": "A block of body or descriptive text.",
        "prop_definitions": {"text": "text", "variant": "enum:body_lg|body_md|body_sm|caption"},
        "slot_definitions": {},
        "semantic_role": "paragraph",
        "recognition_heuristics": {"patterns": ["text_node_standard_size"], "node_type": "TEXT", "font_size_range": [10, 18]},
        "related_types": ["heading", "link"],
    },
    {
        "canonical_name": "link",
        "aliases": ["anchor", "hyperlink"],
        "category": "content_and_display",
        "behavioral_description": "Clickable text that navigates to another location.",
        "prop_definitions": {"href": "text", "text": "text"},
        "slot_definitions": {},
        "semantic_role": "link",
        "recognition_heuristics": {"patterns": ["text_with_underline_or_color"], "node_type": "TEXT", "has_underline_or_accent_color": True},
        "related_types": ["button", "text"],
    },
    {
        "canonical_name": "empty_state",
        "aliases": ["no_content", "placeholder_state"],
        "category": "content_and_display",
        "behavioral_description": "A message displayed when a view has no content to show.",
        "prop_definitions": {"title": "text", "description": "text"},
        "slot_definitions": {"icon": {"allowed": ["icon", "image"], "required": False}, "title": {"allowed": ["heading"], "required": True}, "description": {"allowed": ["text"], "required": False}, "action": {"allowed": ["button"], "required": False}},
        "semantic_role": "status",
        "recognition_heuristics": {"patterns": ["centered_stack_with_icon_and_text"], "layout": "vertical_centered", "has_large_icon": True},
        "related_types": ["skeleton"],
    },
    {
        "canonical_name": "skeleton",
        "aliases": ["placeholder", "shimmer"],
        "category": "content_and_display",
        "behavioral_description": "A placeholder shape indicating content is loading.",
        "prop_definitions": {"width": "dimension", "height": "dimension", "variant": "enum:text|avatar|card|rectangular"},
        "slot_definitions": {},
        "semantic_role": "progressbar",
        "recognition_heuristics": {"patterns": ["gray_rectangle_no_text"], "has_no_text_children": True, "fill_color": "gray_range"},
        "related_types": ["empty_state"],
    },
    # ── Navigation (9) ───────────────────────────────────────────────────
    {
        "canonical_name": "header",
        "aliases": ["app_bar", "top_bar", "nav_bar", "nav/top-nav"],
        "category": "navigation",
        "behavioral_description": "The top bar of a screen containing title, navigation, and actions.",
        "prop_definitions": {"title": "text"},
        "slot_definitions": {"leading": {"allowed": ["icon_button"], "required": False, "position": "start", "quantity": "single"}, "title": {"allowed": ["text", "heading"], "required": False, "position": "center", "quantity": "single"}, "trailing": {"allowed": ["icon_button", "avatar"], "required": False, "position": "end", "quantity": "multiple"}, "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"}},
        "semantic_role": "banner",
        "recognition_heuristics": {"position": "top_of_screen", "layout": "horizontal", "typical_height_range": [44, 64], "y_position_max": 60},
        "related_types": ["bottom_nav"],
    },
    {
        "canonical_name": "bottom_nav",
        "aliases": ["bottom_tab_bar", "tab_bar"],
        "category": "navigation",
        "behavioral_description": "A fixed bar at the screen bottom with primary navigation destinations.",
        "prop_definitions": {"items": "array", "active_index": "number"},
        "slot_definitions": {"items": {"allowed": ["icon", "text"], "required": True, "multiple": True}},
        "semantic_role": "navigation",
        "recognition_heuristics": {"position": "bottom_of_screen", "layout": "horizontal", "min_children": 3, "max_children": 5, "typical_height_range": [48, 83]},
        "related_types": ["header", "tabs"],
    },
    {
        "canonical_name": "drawer",
        "aliases": ["sidebar", "side_nav", "navigation_drawer"],
        "category": "navigation",
        "behavioral_description": "An off-canvas panel for navigation or settings.",
        "prop_definitions": {"is_open": "boolean", "position": "enum:left|right"},
        "slot_definitions": {"header": {"allowed": ["heading", "avatar"], "required": False}, "menu": {"allowed": ["navigation_row"], "required": True, "multiple": True}, "footer": {"allowed": ["text", "button"], "required": False}},
        "semantic_role": "navigation",
        "recognition_heuristics": {"position": "left_or_right_edge", "layout": "vertical", "typical_width_range": [240, 360]},
        "related_types": ["sheet"],
    },
    {
        "canonical_name": "navigation_row",
        "aliases": ["nav_item", "settings_row", "menu_item"],
        "category": "navigation",
        "behavioral_description": "A tappable row that navigates to a destination, typically with label and chevron.",
        "prop_definitions": {"label": "text", "has_chevron": "boolean"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": False}, "label": {"allowed": ["text"], "required": True}, "trailing": {"allowed": ["icon", "badge", "text"], "required": False}},
        "semantic_role": "link",
        "recognition_heuristics": {"patterns": ["horizontal_row_with_chevron"], "layout": "horizontal", "has_trailing_chevron": True},
        "related_types": ["list_item"],
    },
    {
        "canonical_name": "tabs",
        "aliases": ["tab_bar", "tab_group", "nav/tabs"],
        "category": "navigation",
        "behavioral_description": "A set of switchable content panels activated by tab labels.",
        "prop_definitions": {"items": "array", "active_tab": "text"},
        "slot_definitions": {"tabs": {"allowed": ["text", "icon"], "required": True, "multiple": True}, "panels": {"allowed": ["any"], "required": True, "multiple": True}},
        "semantic_role": "tablist",
        "recognition_heuristics": {"patterns": ["horizontal_labels_with_indicator"], "layout": "horizontal", "has_active_indicator": True, "min_children": 2},
        "related_types": ["segmented_control", "bottom_nav"],
    },
    {
        "canonical_name": "breadcrumbs",
        "aliases": ["breadcrumb_trail"],
        "category": "navigation",
        "behavioral_description": "A horizontal trail showing the user's location in a hierarchy.",
        "prop_definitions": {"items": "array"},
        "slot_definitions": {"items": {"allowed": ["link", "text"], "required": True, "multiple": True}},
        "semantic_role": "navigation",
        "recognition_heuristics": {"patterns": ["horizontal_text_with_separators"], "layout": "horizontal", "has_separator_chars": True},
        "related_types": ["tabs"],
    },
    {
        "canonical_name": "pagination",
        "aliases": ["page_nav", "pager"],
        "category": "navigation",
        "behavioral_description": "Controls for navigating between pages of content.",
        "prop_definitions": {"current_page": "number", "total_pages": "number"},
        "slot_definitions": {"items": {"allowed": ["button", "text"], "required": True, "multiple": True}},
        "semantic_role": "navigation",
        "recognition_heuristics": {"patterns": ["row_of_numbered_buttons_with_arrows"], "layout": "horizontal", "has_numbered_items": True},
        "related_types": ["stepper"],
    },
    {
        "canonical_name": "stepper",
        "aliases": ["step_indicator", "wizard_steps"],
        "category": "navigation",
        "behavioral_description": "A progress indicator showing steps in a multi-step flow.",
        "prop_definitions": {"steps": "array", "current_step": "number"},
        "slot_definitions": {"steps": {"allowed": ["text", "icon"], "required": True, "multiple": True}},
        "semantic_role": "navigation",
        "recognition_heuristics": {"patterns": ["horizontal_circles_with_connecting_lines"], "has_step_indicators": True, "has_connecting_lines": True},
        "related_types": ["pagination"],
    },
    {
        "canonical_name": "accordion",
        "aliases": ["collapsible", "disclosure", "expandable"],
        "category": "navigation",
        "behavioral_description": "A vertically stacked set of sections that expand and collapse.",
        "prop_definitions": {"items": "array", "allow_multiple": "boolean"},
        "slot_definitions": {"items": {"allowed": ["heading", "text"], "required": True, "multiple": True}},
        "semantic_role": "group",
        "recognition_heuristics": {"patterns": ["vertical_headers_with_expand_icons"], "layout": "vertical", "has_expand_collapse_icon": True},
        "related_types": ["tabs"],
    },
    # ── Feedback & Status (3) ────────────────────────────────────────────
    {
        "canonical_name": "alert",
        "aliases": ["banner", "notification_bar", "inline_message", "section_message"],
        "category": "feedback_and_status",
        "behavioral_description": "A persistent message communicating status, warning, or error.",
        "prop_definitions": {"severity": "enum:info|warning|error|success", "title": "text", "message": "text", "dismissible": "boolean"},
        "slot_definitions": {
            "icon": {"allowed": ["icon"], "required": False, "position": "start", "quantity": "single"},
            "title": {"allowed": ["text", "heading"], "required": False, "position": "content", "quantity": "single"},
            "message": {"allowed": ["text"], "required": True, "position": "content", "quantity": "single"},
            "action": {"allowed": ["button", "link"], "required": False, "position": "end", "quantity": "multiple"},
            "close": {"allowed": ["icon_button"], "required": False, "position": "end", "quantity": "single"},
        },
        "semantic_role": "alert",
        "recognition_heuristics": {"patterns": ["colored_frame_with_icon_and_text"], "has_status_color": True, "has_icon": True, "position": "inline_or_top"},
        "related_types": ["toast", "badge"],
        "variant_axes": {
            "tone": {"values": ["info", "warning", "error", "success"], "default": "info"},
            "variant": {"values": ["inline", "banner"], "default": "inline"},
        },
    },
    {
        "canonical_name": "toast",
        "aliases": ["snackbar", "notification", "flash_message"],
        "category": "feedback_and_status",
        "behavioral_description": "A brief, auto-dismissing message about a completed action.",
        "prop_definitions": {"message": "text", "duration": "number", "action": "slot"},
        "slot_definitions": {"message": {"allowed": ["text"], "required": True}, "action": {"allowed": ["button", "link"], "required": False}},
        "semantic_role": "status",
        "recognition_heuristics": {"patterns": ["small_floating_frame_at_edge"], "position": "bottom_or_top_corner", "has_shadow": True, "typical_width_range": [200, 400]},
        "related_types": ["alert"],
    },
    {
        "canonical_name": "tooltip",
        "aliases": ["hint", "info_tip"],
        "category": "feedback_and_status",
        "behavioral_description": "A small floating label that appears on hover or focus to explain an element.",
        "prop_definitions": {"text": "text", "position": "enum:top|bottom|left|right"},
        "slot_definitions": {"content": {"allowed": ["text"], "required": True}},
        "semantic_role": "tooltip",
        "recognition_heuristics": {"patterns": ["small_dark_frame_with_arrow"], "has_arrow_pointer": True, "position": "absolute", "typical_max_width": 200},
        "related_types": ["popover"],
    },
    # ── Containment & Overlay (3) ────────────────────────────────────────
    {
        "canonical_name": "dialog",
        "aliases": ["modal", "alert_dialog", "lightbox"],
        "category": "containment_and_overlay",
        "behavioral_description": "A focused overlay window requiring user attention or decision.",
        "prop_definitions": {"title": "text", "is_open": "boolean", "destructive": "boolean"},
        "slot_definitions": {"title": {"allowed": ["heading", "text"], "required": False}, "body": {"allowed": ["text", "any"], "required": True}, "footer": {"allowed": ["button"], "required": False, "multiple": True}},
        "semantic_role": "dialog",
        "recognition_heuristics": {"patterns": ["centered_frame_with_overlay_backdrop"], "position": "centered", "has_backdrop": True, "has_shadow": True},
        "related_types": ["sheet", "popover"],
    },
    {
        "canonical_name": "popover",
        "aliases": ["popup", "floating_panel"],
        "category": "containment_and_overlay",
        "behavioral_description": "A floating panel anchored to a trigger element.",
        "prop_definitions": {"is_open": "boolean", "placement": "enum:top|bottom|left|right"},
        "slot_definitions": {"trigger": {"allowed": ["button", "icon_button", "text"], "required": True}, "content": {"allowed": ["any"], "required": True}},
        "semantic_role": "dialog",
        "recognition_heuristics": {"patterns": ["floating_frame_near_trigger"], "position": "absolute", "has_shadow": True, "has_arrow_pointer": False},
        "related_types": ["tooltip", "menu", "dialog"],
    },
    {
        "canonical_name": "sheet",
        "aliases": ["bottom_sheet", "side_sheet", "action_sheet"],
        "category": "containment_and_overlay",
        "behavioral_description": "A panel that slides in from a screen edge.",
        "prop_definitions": {"is_open": "boolean", "position": "enum:bottom|right|left"},
        "slot_definitions": {"header": {"allowed": ["heading", "icon_button"], "required": False}, "content": {"allowed": ["any"], "required": True}},
        "semantic_role": "dialog",
        "recognition_heuristics": {"patterns": ["edge_anchored_panel_with_backdrop"], "position": "bottom_or_side_edge", "has_backdrop": True, "has_drag_handle": True},
        "related_types": ["dialog", "drawer"],
    },
    # ── ADR-008 PR #0 additions (7 new types) ────────────────────────────
    {
        "canonical_name": "divider",
        "aliases": ["separator", "hr", "rule"],
        "category": "content_and_display",
        "behavioral_description": "A thin line that groups or separates content.",
        "prop_definitions": {"orientation": "enum:horizontal|vertical", "variant": "enum:solid|dashed|dotted"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False, "position": "center", "quantity": "single"}},
        "semantic_role": "separator",
        "recognition_heuristics": {"patterns": ["thin_line_1_or_2_px"], "typical_stroke_weight": [1, 2]},
        "related_types": ["list_item"],
        "variant_axes": {
            "orientation": {"values": ["horizontal", "vertical"], "default": "horizontal"},
            "variant": {"values": ["solid", "dashed", "dotted"], "default": "solid"},
        },
    },
    {
        "canonical_name": "progress",
        "aliases": ["progress_bar", "progress_indicator"],
        "category": "feedback_and_status",
        "behavioral_description": "A bar or ring indicating the completion state of a task.",
        "prop_definitions": {"value": "number", "max": "number", "indeterminate": "boolean"},
        "slot_definitions": {
            "track": {"allowed": [], "required": True},
            "indicator": {"allowed": [], "required": True},
            "label": {"allowed": ["text"], "required": False},
        },
        "semantic_role": "progressbar",
        "recognition_heuristics": {"patterns": ["filled_portion_of_track"], "has_track": True, "has_fill": True},
        "related_types": ["spinner", "stepper"],
        "variant_axes": {
            "variant": {"values": ["linear", "circular", "ring"], "default": "linear"},
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
        },
    },
    {
        "canonical_name": "spinner",
        "aliases": ["loader", "loading_indicator", "loading_dots"],
        "category": "feedback_and_status",
        "behavioral_description": "An animated indicator that a process is working without known duration.",
        "prop_definitions": {"size": "enum:sm|md|lg"},
        "slot_definitions": {},
        "semantic_role": "progressbar",
        "recognition_heuristics": {"patterns": ["small_circular_animated_glyph"], "typical_size_range": [12, 48], "aspect_ratio": "~1:1"},
        "related_types": ["progress", "skeleton"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "tone": {"values": ["default", "primary", "inverse"], "default": "default"},
        },
    },
    {
        "canonical_name": "kbd",
        "aliases": ["keyboard_key", "key_cap"],
        "category": "content_and_display",
        "behavioral_description": "Inline marker representing a keyboard key or shortcut.",
        "prop_definitions": {"keys": "array"},
        "slot_definitions": {"key": {"allowed": ["text", "icon"], "required": True, "quantity": "multiple"}},
        "semantic_role": "text",
        "recognition_heuristics": {"patterns": ["small_bordered_monospace_text"], "has_monospace": True, "has_rounded_corners": True},
        "related_types": ["text", "badge"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "sm"},
        },
    },
    {
        "canonical_name": "number_input",
        "aliases": ["numeric_input", "spinbutton"],
        "category": "selection_and_input",
        "behavioral_description": "A numeric-only input with optional increment/decrement steppers.",
        "prop_definitions": {"value": "number", "min": "number", "max": "number", "step": "number", "precision": "number", "disabled": "boolean", "label": "text"},
        "slot_definitions": {
            "label": {"allowed": ["text"], "required": False, "position": "top"},
            "input": {"allowed": ["text"], "required": True, "position": "fill"},
            "stepper": {"allowed": ["icon_button", "button"], "required": False, "position": "end", "quantity": "multiple"},
            "helper": {"allowed": ["text"], "required": False, "position": "bottom"},
        },
        "semantic_role": "spinbutton",
        "recognition_heuristics": {"patterns": ["bordered_input_with_up_down_arrows"], "has_stepper_affordance": True},
        "related_types": ["text_input", "slider"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "state": {"values": ["default", "focus", "disabled", "invalid"], "default": "default"},
        },
    },
    {
        "canonical_name": "otp_input",
        "aliases": ["pin_input", "code_input", "input_otp"],
        "category": "selection_and_input",
        "behavioral_description": "A multi-cell input for one-time passwords, pins, or verification codes.",
        "prop_definitions": {"length": "number", "value": "text", "mask": "boolean", "disabled": "boolean"},
        "slot_definitions": {
            "cells": {"allowed": ["text_input"], "required": True, "quantity": "multiple"},
            "separator": {"allowed": ["text", "icon"], "required": False, "quantity": "multiple"},
        },
        "semantic_role": "textbox",
        "recognition_heuristics": {"patterns": ["row_of_equal_width_single_char_inputs"], "min_children": 4, "max_children": 8, "children_similar": True},
        "related_types": ["text_input"],
        "variant_axes": {
            "size": {"values": ["sm", "md", "lg"], "default": "md"},
            "state": {"values": ["default", "focus", "filled", "disabled", "invalid"], "default": "default"},
        },
    },
    {
        "canonical_name": "command",
        "aliases": ["command_menu", "command_palette", "spotlight", "cmdk"],
        "category": "actions",
        "behavioral_description": "A keyboard-first, filterable palette of actions and navigational items.",
        "prop_definitions": {"placeholder": "text", "groups": "array"},
        "slot_definitions": {
            "input": {"allowed": ["search_input", "text_input"], "required": True, "position": "top"},
            "groups": {"allowed": ["list"], "required": True, "position": "fill", "quantity": "multiple"},
            "items": {"allowed": ["list_item", "text"], "required": True, "position": "fill", "quantity": "multiple"},
            "shortcut": {"allowed": ["kbd"], "required": False, "position": "end", "quantity": "single"},
        },
        "semantic_role": "dialog",
        "recognition_heuristics": {"patterns": ["overlay_with_search_and_grouped_items"], "has_backdrop": True, "has_search_input": True},
        "related_types": ["menu", "search_input"],
        "variant_axes": {
            "size": {"values": ["md", "lg"], "default": "md"},
        },
    },
    # ── Design-tool primitives (classifier v2.1) ─────────────────────────
    {
        "canonical_name": "control_point",
        "aliases": ["handle", "control-handle", "vector-handle", "manipulator"],
        "category": "content_and_display",
        "behavioral_description": (
            "Design-tool manipulation handle — small circular or "
            "square marker that lets a user drag, resize, or rotate "
            "another element. Appears in editors (Figma, Sketch, "
            "design systems' canvas surfaces) attached to selection "
            "bounding boxes or vector control points."
        ),
        "semantic_role": "img",
        "recognition_heuristics": {
            "patterns": ["tiny_circle_or_square", "attached_to_selection_edge"],
            "typical_size_range": [6, 14],
        },
        "related_types": ["icon"],
    },
    {
        "canonical_name": "not_ui",
        "aliases": ["non_ui", "decorative", "artifact", "exclude"],
        "category": "content_and_display",
        "behavioral_description": (
            "Explicit non-UI marker — a frame / instance that exists in "
            "the Figma file but is NOT a semantic UI component. "
            "Examples: design-tool artifacts, decorative background "
            "elements, empty layout wrappers reviewers have confirmed "
            "carry no interactive or informational identity, test / "
            "scratch frames left by the designer. Downstream synthesis "
            "should exclude these from generated output rather than "
            "try to render them as a component."
        ),
        "semantic_role": "none",
        "recognition_heuristics": {
            "patterns": ["human_confirmed_exclusion"],
            "note": (
                "This type is almost always set by a human reviewer via "
                "the 'Not UI' button; automated classifiers should NOT "
                "pick it — prefer `container` or `unsure` unless a "
                "reviewer has explicitly confirmed exclusion."
            ),
        },
        "disambiguation_notes": (
            "NOT a `container` (which is a generic layout wrapper that "
            "still renders). NOT `unsure` (which means 'I don't know "
            "what this is'). `not_ui` means 'I know what this is — "
            "it's not UI and should be excluded.'"
        ),
        "related_types": ["container", "unsure"],
    },
)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Classifier v2.1 enrichments (migration 016)
# ---------------------------------------------------------------------------
# Maps canonical_name → enrichment dict. Merged into CATALOG_ENTRIES at
# seed time. Keeps the prose + ecosystem-alignment metadata collected
# in one reviewable block rather than scattered across 50+ entries.
#
# Prioritised for types most-often confused in the v1 corpus run:
# tooltip (29 override hits), button (29), icon, divider, checkbox,
# card, image, heading. Adding the `disambiguation_notes` is the big
# prompt-quality lever — the classifier gets "NOT a dialog because..."
# style cues that push it off wrong-neighbor picks.

_CATALOG_ENRICHMENTS: dict[str, dict[str, Any]] = {
    "button": {
        "clay_equivalent": "BUTTON",
        "aria_role": "button",
        "aliases": ["btn", "cta", "previous", "next", "new folder",
                    "Button"],
        "disambiguation_notes": (
            "NOT a `link` — buttons trigger actions, links navigate. "
            "NOT an `icon_button` — icon_button is icon-only with no "
            "visible text label. NOT a `fab` — fab is an elevated "
            "floating primary action, usually circular. "
            "If the node has a centered text label and a visible "
            "shape (rect/pill), it's a button."
        ),
    },
    "icon_button": {
        "clay_equivalent": "BUTTON",
        "aria_role": "button",
        "aliases": ["icon_btn", "icon button", "iconbutton",
                    "image_button"],
        "disambiguation_notes": (
            "NOT an `icon` — icon is the glyph itself; icon_button "
            "is the tappable container around the glyph with a "
            "hit-target (usually 32-48px square). NOT a `button` — "
            "button has a visible text label. NOT a `fab` — fab is "
            "elevated/floating, icon_button is flush. If the node "
            "is a small square frame containing only a single icon "
            "child with no label, classify icon_button."
        ),
    },
    "fab": {
        "clay_equivalent": "BUTTON",
        "aria_role": "button",
        "disambiguation_notes": (
            "NOT a `button` — fab is visually prominent, usually "
            "circular/pill with elevation, positioned floating "
            "(bottom-right or bottom-center). Reserved for the "
            "primary screen action."
        ),
    },
    "icon": {
        "clay_equivalent": "PICTOGRAM",
        "aria_role": None,  # icons are usually aria-hidden
        "aliases": ["glyph", "symbol", ".icons", "pictogram", "ico"],
        "disambiguation_notes": (
            "NOT an `icon_button` — icon is the glyph primitive "
            "itself; icon_button is the tappable container wrapping "
            "an icon. NOT an `image` — icons are symbolic/vector, "
            "small (≤32px typically), convey meaning or affordance; "
            "images are raster content. Decorative children like "
            "3 ellipses, 2 chevrons, 4 dots in a tight layout are "
            "a single `icon`, not a container of N things."
        ),
    },
    "image": {
        "clay_equivalent": "IMAGE",
        "aria_role": "img",
        "aliases": ["img", "photo", "picture", "image-box",
                    "image_box"],
        "disambiguation_notes": (
            "NOT an `icon` — images are raster content (photos, "
            "illustrations, screenshots), typically > 64px. "
            "NOT a `card` — image holds a single graphic; card is "
            "a bounded container with mixed content. NOT a "
            "`skeleton` — skeleton is the loading placeholder; "
            "image carries actual visual content."
        ),
    },
    "divider": {
        "clay_equivalent": None,
        "aria_role": "separator",
        "aliases": ["separator", "hr", "rule", "line", "vertical_rule",
                    "horizontal_rule"],
        "disambiguation_notes": (
            "A thin line (width OR height ≤ ~4px) that visually "
            "groups or separates content. NOT a `container` — "
            "containers hold children; dividers have none. NOT an "
            "`icon` — dividers are straight lines, not glyphs. "
            "Aspect ratio is extreme (>20:1 for horizontal, <1:20 "
            "for vertical)."
        ),
    },
    "heading": {
        "clay_equivalent": "LABEL",
        "aria_role": "heading",
        "aliases": ["title", "h1", "h2", "h3", "section-title"],
        "disambiguation_notes": (
            "NOT a `text` — heading carries structural weight; "
            "font is larger (≥18px typically) and/or bolder than "
            "body text. NOT a `label` — labels describe form "
            "controls; headings organise content. Appears at the "
            "top of a section or card."
        ),
    },
    "text": {
        "clay_equivalent": "TEXT",
        "aria_role": None,
        "aliases": ["body", "paragraph", "p", "text-content",
                    "description", "copy"],
        "disambiguation_notes": (
            "NOT a `heading` — text is body-weight content "
            "(typically 12-16px). NOT a `link` — links have hover/"
            "pressed states and trigger navigation. NOT a `label` — "
            "labels describe form controls specifically."
        ),
    },
    "card": {
        "clay_equivalent": "CARD_VIEW",
        "aria_role": None,
        "aliases": ["tile", "panel", "card-view"],
        "disambiguation_notes": (
            "NOT a `container` — cards have visible boundaries "
            "(fill + stroke + radius typically) AND mixed content "
            "(image + heading + actions). NOT a `dialog` — dialogs "
            "are modal; cards are inline within a feed/grid. NOT a "
            "`list_item` — list_items are row-oriented and usually "
            "stack vertically without individual borders. A bounded "
            "container with an image at top + heading + body text "
            "is a card."
        ),
    },
    "list_item": {
        "clay_equivalent": "LIST_ITEM",
        "aria_role": "listitem",
        "aliases": ["row", "list-row", "item", "list_row"],
        "disambiguation_notes": (
            "NOT a `card` — list_items are row-oriented and stack "
            "vertically; they share borders with siblings rather "
            "than having individual cards. NOT a `button` — "
            "list_items may be tappable but they carry content "
            "(text + optional icon/image), not just an action."
        ),
    },
    "checkbox": {
        "clay_equivalent": "CHECK_BOX",
        "aria_role": "checkbox",
        "aliases": ["check", "check-box", "check_box"],
        "disambiguation_notes": (
            "NOT a `toggle` — checkboxes are square; toggles are "
            "pill-shaped with a sliding knob. NOT a `radio` — "
            "radios are circular and mutually exclusive within a "
            "group. A square control with a check glyph (visible "
            "or hidden) = checkbox."
        ),
    },
    "radio": {
        "clay_equivalent": "RADIO_BUTTON",
        "aria_role": "radio",
        "aliases": ["radiobutton", "radio_button"],
        "disambiguation_notes": (
            "NOT a `checkbox` — radios are circular (not square). "
            "Radios come in groups where only one can be selected. "
            "A single circular control with an inner dot = radio."
        ),
    },
    "toggle": {
        "clay_equivalent": "SWITCH",
        "aria_role": "switch",
        "aliases": ["switch", "on_off"],
        "disambiguation_notes": (
            "NOT a `checkbox` — toggles are pill-shaped with a "
            "sliding knob (binary state). Apple-style: pill with "
            "knob slid left/right. Material-style: rail with knob. "
            "If the shape is a rounded pill with a circle inside, "
            "it's a toggle."
        ),
    },
    "tooltip": {
        "clay_equivalent": None,
        "aria_role": "tooltip",
        "aliases": ["hint", "info_tip", "help-text", "helptip",
                    "callout"],
        "disambiguation_notes": (
            "NOT a `dialog` — dialogs are modal and require user "
            "action. NOT a `popover` — popovers hold interactive "
            "content (buttons, forms); tooltips are text-only "
            "annotations. NOT a `toast` — toasts are transient "
            "notifications unanchored from content; tooltips point "
            "at an anchor element (arrow or adjacent positioning). "
            "Short-text floating annotations with an arrow or "
            "nearby alignment to another element = tooltip."
        ),
    },
    "toast": {
        "clay_equivalent": None,
        "aria_role": "status",
        "aliases": ["snackbar", "notification"],
        "disambiguation_notes": (
            "NOT a `tooltip` — toasts appear without an anchor, "
            "usually at screen edges. NOT an `alert` — alerts are "
            "modal/blocking; toasts are transient (auto-dismiss). "
            "Small floating bar with text + optional action button "
            "= toast."
        ),
    },
    "alert": {
        "clay_equivalent": None,
        "aria_role": "alert",
        "aliases": ["banner", "notice", "flash"],
        "disambiguation_notes": (
            "NOT a `toast` — alerts are often persistent until "
            "dismissed; toasts auto-expire. NOT a `dialog` — alerts "
            "are inline banners; dialogs are modal overlays. "
            "Horizontal bar with icon + message + optional "
            "dismiss/action = alert."
        ),
    },
    "dialog": {
        "clay_equivalent": None,
        "aria_role": "dialog",
        "aliases": ["modal", "dialog-box"],
        "disambiguation_notes": (
            "NOT a `sheet` — sheets slide up from the bottom; "
            "dialogs are centered overlays. NOT a `popover` — "
            "popovers anchor to a trigger element; dialogs "
            "command focus. NOT a `card` — dialogs are modal and "
            "block the background (overlay behind them)."
        ),
    },
    "sheet": {
        "clay_equivalent": None,
        "aria_role": "dialog",
        "aliases": ["bottom_sheet", "action_sheet", "half_sheet"],
        "disambiguation_notes": (
            "NOT a `dialog` — sheets slide from an edge (usually "
            "bottom); dialogs are centered. Rounded top corners + "
            "bottom-pinned = bottom sheet. Can hold interactive "
            "content (unlike tooltips)."
        ),
    },
    "drawer": {
        "clay_equivalent": "DRAWER",
        "aria_role": "dialog",
        "aliases": ["side_drawer", "nav_drawer"],
        "disambiguation_notes": (
            "NOT a `sheet` — drawers slide from a SIDE (left/right); "
            "sheets slide from top/bottom. Typically holds "
            "navigation links or settings."
        ),
    },
    "popover": {
        "clay_equivalent": None,
        "aria_role": "dialog",
        "aliases": ["flyout", "popup"],
        "disambiguation_notes": (
            "NOT a `tooltip` — popovers hold interactive content "
            "(buttons, forms, lists); tooltips are text-only. "
            "NOT a `dialog` — popovers anchor to a trigger element; "
            "dialogs are unanchored modal overlays."
        ),
    },
    "header": {
        "clay_equivalent": "TOOLBAR",
        "aria_role": "banner",
        "aliases": ["top_bar", "app_bar", "nav_bar", "title_bar",
                    "toolbar"],
        "disambiguation_notes": (
            "NOT a `bottom_nav` — headers sit at the TOP of the "
            "viewport (y ≤ 100px typically); bottom_nav sits at "
            "the bottom. Full-width frame containing title text + "
            "nav controls (back/menu/action icons)."
        ),
    },
    "bottom_nav": {
        "clay_equivalent": "NAVIGATION_BAR",
        "aria_role": "navigation",
        "aliases": ["tab_bar", "bottom_bar", "tabbar"],
        "disambiguation_notes": (
            "NOT a `header` — bottom_nav sits at the BOTTOM (y near "
            "screen height). NOT `tabs` — tabs usually sit below "
            "a header; bottom_nav is the screen's primary "
            "navigation. Full-width frame containing 3-5 icon+label "
            "tab items."
        ),
    },
    "tabs": {
        "clay_equivalent": None,
        "aria_role": "tablist",
        "aliases": ["tab_bar", "segmented_tabs"],
        "disambiguation_notes": (
            "NOT `bottom_nav` — tabs switch content within a "
            "screen; bottom_nav switches screens. Usually sits "
            "below a header or at the top of a content area. "
            "Horizontal row of text labels with an indicator under "
            "the active one."
        ),
    },
    "navigation_row": {
        "clay_equivalent": None,
        "aria_role": "navigation",
        "aliases": ["nav_row", "nav-item", "drawer-row"],
        "disambiguation_notes": (
            "A single-row entry inside a navigation surface (side "
            "drawer, settings list). Usually: leading icon + label "
            "+ optional trailing chevron. NOT a `list_item` — "
            "navigation_rows trigger route changes; list_items are "
            "content."
        ),
    },
    "breadcrumbs": {
        "clay_equivalent": None,
        "aria_role": "navigation",
        "aliases": ["crumbs", "path", "breadcrumb"],
        "disambiguation_notes": (
            "A row of link-like text separated by chevrons or "
            "slashes, showing the user's path through a hierarchy. "
            "NOT `tabs` — breadcrumbs show HIERARCHY; tabs show "
            "SIBLINGS."
        ),
    },
    "container": {
        "clay_equivalent": "CONTAINER",
        "aria_role": None,
        "disambiguation_notes": (
            "FALLBACK only — a generic layout frame with no "
            "specific component identity. Use `container` when the "
            "node has NO distinctive name, sample text, child "
            "pattern, or visual affordance. If the children "
            "themselves are all buttons, say `button_group`; if "
            "they're cards in a grid, say `list` or `card`; if the "
            "name is distinctive (`grabber`, `wordmark`, "
            "`filename`), use the specific type. `container` loses "
            "information downstream — prefer anything specific."
        ),
    },
    "skeleton": {
        "clay_equivalent": None,
        "aria_role": "status",
        "aliases": ["loading_placeholder", "shimmer"],
        "disambiguation_notes": (
            "A loading placeholder — multiple identical empty "
            "frames (no children, no text, same size) arranged in "
            "a grid or list. NOT a `container` — skeletons have "
            "the repetition pattern + empty-child signal. NOT "
            "`image` — images carry actual content; skeletons are "
            "placeholder rectangles awaiting data."
        ),
    },
    "search_input": {
        "clay_equivalent": "TEXT_INPUT",
        "aria_role": "searchbox",
        "aliases": ["search", "search_bar", "search-field"],
        "disambiguation_notes": (
            "NOT a `text_input` — search_input has a search icon "
            "(magnifying glass) and usually auto-complete/suggest "
            "affordances. Placeholder text often says 'Search...'."
        ),
    },
    "text_input": {
        "clay_equivalent": "TEXT_INPUT",
        "aria_role": "textbox",
        "aliases": ["input", "textfield", "text_field"],
        "disambiguation_notes": (
            "NOT a `search_input` — plain text input without a "
            "search icon. Rectangular frame with optional label + "
            "placeholder text + cursor."
        ),
    },
    "spinner": {
        "clay_equivalent": "SPINNER",
        "aria_role": "progressbar",
        "aliases": ["loader", "loading_indicator", "activity"],
        "disambiguation_notes": (
            "A circular/rotating loading indicator with no "
            "determinate progress. NOT a `progress` bar — spinner "
            "is indeterminate (shows activity, not completion %)."
        ),
    },
    "progress": {
        "clay_equivalent": "PROGRESS_BAR",
        "aria_role": "progressbar",
        "aliases": ["progress_bar", "progressbar", "loader-bar"],
        "disambiguation_notes": (
            "A determinate progress indicator — bar with a filled "
            "portion showing completion. NOT a `spinner` — spinners "
            "are indeterminate. NOT a `slider` — sliders are "
            "interactive; progress is read-only status."
        ),
    },
}


def _enriched(entry: CatalogEntry) -> dict[str, Any]:
    """Merge enrichments + base entry. Enrichments' `aliases` extend
    the base entry's aliases (deduped); other enrichment keys
    overwrite.
    """
    merged: dict[str, Any] = dict(entry)
    enrich = _CATALOG_ENRICHMENTS.get(entry["canonical_name"], {})
    for key, value in enrich.items():
        if key == "aliases" and merged.get("aliases"):
            existing = list(merged["aliases"])
            for alias in value:
                if alias not in existing:
                    existing.append(alias)
            merged["aliases"] = existing
        else:
            merged[key] = value
    return merged


def seed_catalog(conn: sqlite3.Connection) -> int:
    """Populate / reconcile ``component_type_catalog`` from CATALOG_ENTRIES.

    For each entry: INSERT OR IGNORE on `(canonical_name, category)` to
    preserve existing `id`s (keeping `screen_component_instances.catalog_type_id`
    foreign keys intact), then UPDATE the mutable metadata columns so
    re-seeding reconciles to the current CATALOG_ENTRIES state.

    Idempotent and id-stable. Returns the count of rows inserted (not
    updated) for compatibility with callers that tracked the install
    count.
    """
    cursor = conn.cursor()
    inserted = 0

    for base_entry in CATALOG_ENTRIES:
        entry = _enriched(base_entry)
        insert_result = cursor.execute(
            "INSERT OR IGNORE INTO component_type_catalog "
            "(canonical_name, category) VALUES (?, ?)",
            (entry["canonical_name"], entry["category"]),
        )
        if insert_result.rowcount > 0:
            inserted += 1

        cursor.execute(
            "UPDATE component_type_catalog SET "
            "category = ?, aliases = ?, behavioral_description = ?, "
            "prop_definitions = ?, slot_definitions = ?, "
            "semantic_role = ?, recognition_heuristics = ?, "
            "related_types = ?, variant_axes = ?, "
            "clay_equivalent = ?, aria_role = ?, "
            "disambiguation_notes = ? "
            "WHERE canonical_name = ?",
            (
                entry["category"],
                json.dumps(entry.get("aliases")) if entry.get("aliases") else None,
                entry.get("behavioral_description"),
                json.dumps(entry.get("prop_definitions")) if entry.get("prop_definitions") else None,
                json.dumps(entry.get("slot_definitions")) if entry.get("slot_definitions") else None,
                entry.get("semantic_role"),
                json.dumps(entry.get("recognition_heuristics")) if entry.get("recognition_heuristics") else None,
                json.dumps(entry.get("related_types")) if entry.get("related_types") else None,
                json.dumps(entry.get("variant_axes")) if entry.get("variant_axes") else None,
                entry.get("clay_equivalent"),
                entry.get("aria_role"),
                entry.get("disambiguation_notes"),
                entry["canonical_name"],
            ),
        )

    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _parse_json_field(value: str | None) -> list | dict | None:
    if value is None:
        return None
    return json.loads(value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for field in ("aliases", "prop_definitions", "slot_definitions",
                  "recognition_heuristics", "related_types", "variant_axes"):
        d[field] = _parse_json_field(d.get(field))
    return d


def get_catalog(
    conn: sqlite3.Connection,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Return catalog entries, optionally filtered by category.

    JSON columns are parsed into Python objects.
    """
    if category is not None:
        cursor = conn.execute(
            "SELECT * FROM component_type_catalog WHERE category = ? "
            "ORDER BY canonical_name",
            (category,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM component_type_catalog ORDER BY canonical_name"
        )
    return [_row_to_dict(row) for row in cursor.fetchall()]


def lookup_by_name(
    conn: sqlite3.Connection,
    name: str,
) -> dict[str, Any] | None:
    """Find a catalog entry by canonical name or alias (case-insensitive).

    Tries exact canonical_name match first, then scans aliases.
    Returns None if not found.
    """
    name_lower = name.lower()

    cursor = conn.execute(
        "SELECT * FROM component_type_catalog WHERE LOWER(canonical_name) = ?",
        (name_lower,),
    )
    row = cursor.fetchone()
    if row is not None:
        return _row_to_dict(row)

    cursor = conn.execute("SELECT * FROM component_type_catalog WHERE aliases IS NOT NULL")
    for row in cursor.fetchall():
        aliases = json.loads(row["aliases"])
        if name_lower in (a.lower() for a in aliases):
            return _row_to_dict(row)

    return None
