"""Universal component type catalog (T5 Phase 0).

Defines ~48 canonical UI component types organized by user intent.
This vocabulary is the foundation for classification (Phase 1),
IR generation (Phase 2), and all downstream phases.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional, TypedDict


class CatalogEntry(TypedDict, total=False):
    canonical_name: str
    aliases: Optional[List[str]]
    category: str
    behavioral_description: str
    prop_definitions: Optional[Dict[str, Any]]
    slot_definitions: Optional[Dict[str, Any]]
    semantic_role: str
    recognition_heuristics: Optional[Dict[str, Any]]
    related_types: Optional[List[str]]


# ---------------------------------------------------------------------------
# The 48 canonical UI component types
# ---------------------------------------------------------------------------

CATALOG_ENTRIES: tuple[CatalogEntry, ...] = (
    # ── Actions (6) ──────────────────────────────────────────────────────
    {
        "canonical_name": "button",
        "aliases": ["btn", "cta"],
        "category": "actions",
        "behavioral_description": "Primary interactive control that triggers an action on press.",
        "prop_definitions": {"label": "text", "variant": "enum:primary|secondary|ghost|destructive", "size": "enum:sm|md|lg", "disabled": "boolean", "icon": "slot"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": False, "position": "start", "quantity": "single"}, "label": {"allowed": ["text"], "required": True, "position": "fill", "quantity": "single"}, "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"}},
        "semantic_role": "button",
        "recognition_heuristics": {"patterns": ["frame_with_text_label", "rounded_rect_with_center_text"], "min_children": 1, "typical_height_range": [32, 56]},
        "related_types": ["icon_button", "button_group"],
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
        "aliases": ["btn_group", "button_bar"],
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
        "aliases": ["dropdown_menu", "action_menu"],
        "category": "actions",
        "behavioral_description": "A list of actions revealed by a trigger element.",
        "prop_definitions": {"items": "array", "trigger": "slot"},
        "slot_definitions": {"trigger": {"allowed": ["button", "icon_button"], "required": True}, "items": {"allowed": ["text", "icon"], "required": True, "multiple": True}},
        "semantic_role": "menu",
        "recognition_heuristics": {"patterns": ["trigger_plus_dropdown_list"], "has_overlay": True},
        "related_types": ["context_menu", "select"],
    },
    {
        "canonical_name": "context_menu",
        "aliases": ["right_click_menu"],
        "category": "actions",
        "behavioral_description": "A menu triggered by secondary interaction on an element.",
        "prop_definitions": {"items": "array"},
        "slot_definitions": {"items": {"allowed": ["text", "icon"], "required": True, "multiple": True}},
        "semantic_role": "menu",
        "recognition_heuristics": {"patterns": ["floating_list_overlay"], "has_overlay": True, "position": "absolute"},
        "related_types": ["menu"],
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
        "aliases": ["switch", "lightswitch"],
        "category": "selection_and_input",
        "behavioral_description": "A binary choice control that takes effect immediately.",
        "prop_definitions": {"label": "text", "value": "boolean", "disabled": "boolean"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}},
        "semantic_role": "switch",
        "recognition_heuristics": {"patterns": ["pill_track_with_thumb"], "aspect_ratio": "~2:1", "has_circular_thumb": True},
        "related_types": ["checkbox", "toggle_group"],
    },
    {
        "canonical_name": "toggle_group",
        "aliases": ["switch_group"],
        "category": "selection_and_input",
        "behavioral_description": "Multiple toggles where one or more can be selected.",
        "prop_definitions": {"type": "enum:exclusive|multiple"},
        "slot_definitions": {"items": {"allowed": ["toggle"], "required": True, "multiple": True}},
        "semantic_role": "group",
        "recognition_heuristics": {"patterns": ["row_or_column_of_toggles"], "min_children": 2, "children_type": "toggle"},
        "related_types": ["toggle", "segmented_control"],
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
        "prop_definitions": {"placeholder": "text", "value": "text", "type": "enum:text|email|password|number", "disabled": "boolean", "label": "text"},
        "slot_definitions": {"label": {"allowed": ["text"], "required": False}, "leading": {"allowed": ["icon"], "required": False}, "trailing": {"allowed": ["icon", "button"], "required": False}},
        "semantic_role": "textbox",
        "recognition_heuristics": {"patterns": ["bordered_rectangle_with_padding"], "has_border": True, "single_line": True, "typical_height_range": [36, 52]},
        "related_types": ["textarea", "search_input"],
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
        "slot_definitions": {"image": {"allowed": ["image"], "required": False, "position": "start", "quantity": "single"}, "title": {"allowed": ["heading", "text"], "required": False, "position": "start", "quantity": "single"}, "subtitle": {"allowed": ["text"], "required": False, "position": "start", "quantity": "single"}, "body": {"allowed": ["text"], "required": False, "position": "fill", "quantity": "single"}, "actions": {"allowed": ["button", "icon_button", "link"], "required": False, "position": "end", "quantity": "multiple"}, "_default": {"allowed": ["any"], "position": "fill", "quantity": "multiple"}},
        "semantic_role": "article",
        "recognition_heuristics": {"patterns": ["bordered_or_shadowed_container"], "has_border_or_shadow": True, "has_padding": True, "typical_children": ["image", "text", "button"]},
        "related_types": ["list_item"],
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
        "aliases": ["glyph", "symbol"],
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
        "behavioral_description": "A single entry within a list, typically with leading, content, and trailing zones.",
        "prop_definitions": {"label": "text", "description": "text"},
        "slot_definitions": {"leading": {"allowed": ["icon", "avatar", "image"], "required": False}, "content": {"allowed": ["text", "heading"], "required": True}, "trailing": {"allowed": ["icon", "badge", "text"], "required": False}},
        "semantic_role": "listitem",
        "recognition_heuristics": {"patterns": ["horizontal_leading_content_trailing"], "layout": "horizontal", "has_three_zones": True},
        "related_types": ["list", "card", "navigation_row"],
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
        "aliases": ["banner", "notification_bar", "inline_message"],
        "category": "feedback_and_status",
        "behavioral_description": "A persistent message communicating status, warning, or error.",
        "prop_definitions": {"severity": "enum:info|warning|error|success", "title": "text", "message": "text", "dismissible": "boolean"},
        "slot_definitions": {"icon": {"allowed": ["icon"], "required": False}, "title": {"allowed": ["text"], "required": False}, "message": {"allowed": ["text"], "required": True}, "action": {"allowed": ["button", "link"], "required": False}},
        "semantic_role": "alert",
        "recognition_heuristics": {"patterns": ["colored_frame_with_icon_and_text"], "has_status_color": True, "has_icon": True, "position": "inline_or_top"},
        "related_types": ["toast", "badge"],
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
)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_catalog(conn: sqlite3.Connection) -> int:
    """Populate component_type_catalog from CATALOG_ENTRIES.

    Uses INSERT OR IGNORE for idempotency. Returns count of rows inserted.
    """
    cursor = conn.cursor()
    inserted = 0

    for entry in CATALOG_ENTRIES:
        result = cursor.execute(
            "INSERT OR IGNORE INTO component_type_catalog "
            "(canonical_name, aliases, category, behavioral_description, "
            "prop_definitions, slot_definitions, semantic_role, "
            "recognition_heuristics, related_types) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["canonical_name"],
                json.dumps(entry.get("aliases")) if entry.get("aliases") else None,
                entry["category"],
                entry.get("behavioral_description"),
                json.dumps(entry.get("prop_definitions")) if entry.get("prop_definitions") else None,
                json.dumps(entry.get("slot_definitions")) if entry.get("slot_definitions") else None,
                entry.get("semantic_role"),
                json.dumps(entry.get("recognition_heuristics")) if entry.get("recognition_heuristics") else None,
                json.dumps(entry.get("related_types")) if entry.get("related_types") else None,
            ),
        )
        if result.rowcount > 0:
            inserted += 1

    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _parse_json_field(value: str | None) -> list | dict | None:
    if value is None:
        return None
    return json.loads(value)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for field in ("aliases", "prop_definitions", "slot_definitions",
                  "recognition_heuristics", "related_types"):
        d[field] = _parse_json_field(d.get(field))
    return d


def get_catalog(
    conn: sqlite3.Connection,
    category: str | None = None,
) -> List[Dict[str, Any]]:
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
) -> Dict[str, Any] | None:
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
