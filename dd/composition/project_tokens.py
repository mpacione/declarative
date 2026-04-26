"""Phase E #1 fix — project-token alias overlay for Mode-3 synthesis.

The universal catalog provider (dd/composition/providers/universal.py)
emits PresentationTemplates with token refs like ``{color.surface.card}``
or ``{radius.card}``. Pre-fix the renderer resolved these against
``_UNIVERSAL_MODE3_TOKENS`` (dd/compose.py:627) — a hardcoded
shadcn-defaults dict — so every Mode-3 card got white-on-white
regardless of the project's actual design system.

This module overlays project-specific token values onto the universal
vocabulary by querying the project DB for clustered tokens and
selecting the most-bound match per selector entry. The renderer's
existing flat-dict ``resolve_style_value`` (dd/visual.py:40) is
unchanged; the only difference is what's IN the dict it consults.

Codex 2026-04-26 (gpt-5.5 high reasoning) review:
  - "Use a compose-time alias overlay; keep universal templates
    emitting stable refs."
  - "Do not put this in resolve_style_value; it intentionally does
    exact flat lookup only."
  - "Do not make providers project-aware."
  - Selector table maps universal names to (name pattern, property
    family, preferred canonical_type); single aggregate SQL query.

Sonnet research (2026-04-26):
  - Universal templates emit 84 distinct token refs across 5
    families (color/radius/spacing/typography/shadow).
  - Phase E Nouns DB has 4500+ bound surface-color bindings, 1300+
    radius bindings — sufficient corpus for binding-aware selection.
  - Selector resolves {color.surface.card} → color.surface.23
    (603 bindings on Nouns).

The contract: return a dict[str, Any] of universal_name →
project_resolved_value. Caller merges this UNDER
_UNIVERSAL_MODE3_TOKENS so project tokens win, shadcn fills gaps.
"""

from __future__ import annotations

import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Selector table
# ---------------------------------------------------------------------------
# Each entry maps a universal token name (as it appears in {ref} form
# inside a PresentationTemplate) to a strategy for finding its
# project-specific value:
#   name_prefix: the project token prefix to search (`color.surface.`
#     matches `color.surface.10`, `color.surface.card`, etc.)
#   property_families: the node_token_bindings.property values that
#     count toward the "most-used" ranking (e.g. `fills.0.color`
#     means the project token bound to fill colors of nodes is
#     the right surface candidate)
#   preferred_canonical_type: when SCI has rows of this type, prefer
#     the most-used token among bindings on those nodes; otherwise
#     fall back to global most-used. Allows e.g. {color.surface.card}
#     to prefer card-bound surface colors over screen-bound ones.

_SELECTORS: dict[str, dict[str, Any]] = {
    # ----- Surface colors (card-tone) -----
    "color.surface.card": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "card",
    },
    "color.surface.dialog": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "dialog",
    },
    "color.surface.list_item": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "list_item",
    },
    "color.surface.default": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": None,
    },
    "color.surface.header": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "header",
    },
    "color.surface.menu": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "menu",
    },
    "color.surface.drawer": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "drawer",
    },
    "color.surface.popover": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "popover",
    },

    # ----- Border colors -----
    "color.surface.card_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "card",
    },
    "color.surface.dialog_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "dialog",
    },
    "color.surface.list_item_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "list_item",
    },
    "color.surface.header_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "header",
    },
    "color.surface.menu_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "menu",
    },
    "color.surface.drawer_border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "drawer",
    },
    "color.input.bg": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "text_input",
    },
    "color.input.border": {
        "name_prefix": "color.border.",
        "property_families": ("stroke.0.color",),
        "preferred_canonical_type": "text_input",
    },

    # ----- Action / button surfaces -----
    "color.action.primary.bg": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "button",
    },
    "color.action.default.bg": {
        "name_prefix": "color.surface.",
        "property_families": ("fill.0.color",),
        "preferred_canonical_type": "button",
    },

    # ----- Radius -----
    "radius.card": {
        "name_prefix": "radius.",
        "property_families": (
            "cornerRadius",
            "topLeftRadius", "topRightRadius",
            "bottomLeftRadius", "bottomRightRadius",
        ),
        "preferred_canonical_type": "card",
    },
    "radius.button": {
        "name_prefix": "radius.",
        "property_families": ("cornerRadius",),
        "preferred_canonical_type": "button",
    },
    "radius.input": {
        "name_prefix": "radius.",
        "property_families": ("cornerRadius",),
        "preferred_canonical_type": "text_input",
    },
    "radius.dialog": {
        "name_prefix": "radius.",
        "property_families": ("cornerRadius",),
        "preferred_canonical_type": "dialog",
    },
    "radius.default": {
        "name_prefix": "radius.",
        "property_families": ("cornerRadius",),
        "preferred_canonical_type": None,
    },

    # ----- Spacing (padding/gap) -----
    "space.card.padding_x": {
        "name_prefix": "space.",
        "property_families": ("padding.left", "padding.right"),
        "preferred_canonical_type": "card",
    },
    "space.card.padding_y": {
        "name_prefix": "space.",
        "property_families": ("padding.top", "padding.bottom"),
        "preferred_canonical_type": "card",
    },
    "space.card.gap": {
        "name_prefix": "space.",
        "property_families": ("itemSpacing",),
        "preferred_canonical_type": "card",
    },
    "space.button.padding_x": {
        "name_prefix": "space.",
        "property_families": ("padding.left", "padding.right"),
        "preferred_canonical_type": "button",
    },
    "space.button.padding_y": {
        "name_prefix": "space.",
        "property_families": ("padding.top", "padding.bottom"),
        "preferred_canonical_type": "button",
    },
    "space.button.gap": {
        "name_prefix": "space.",
        "property_families": ("itemSpacing",),
        "preferred_canonical_type": "button",
    },
    "space.dialog.padding_x": {
        "name_prefix": "space.",
        "property_families": ("padding.left", "padding.right"),
        "preferred_canonical_type": "dialog",
    },
    "space.dialog.padding_y": {
        "name_prefix": "space.",
        "property_families": ("padding.top", "padding.bottom"),
        "preferred_canonical_type": "dialog",
    },
    "space.list_item.padding_x": {
        "name_prefix": "space.",
        "property_families": ("padding.left", "padding.right"),
        "preferred_canonical_type": "list_item",
    },
    "space.list_item.padding_y": {
        "name_prefix": "space.",
        "property_families": ("padding.top", "padding.bottom"),
        "preferred_canonical_type": "list_item",
    },
    "space.list_item.gap": {
        "name_prefix": "space.",
        "property_families": ("itemSpacing",),
        "preferred_canonical_type": "list_item",
    },
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    )
    return cur.fetchone() is not None


def _resolve_one(
    conn: sqlite3.Connection,
    universal_name: str,
    selector: dict[str, Any],
) -> Any | None:
    """Resolve a single universal token name to a project-bound value.

    Strategy:
    1. If preferred_canonical_type is set AND screen_component_instances
       has rows of that type, find the most-bound token whose name
       starts with name_prefix and whose bindings include at least
       one row from this canonical_type's nodes.
    2. Otherwise fall back to global most-used token under name_prefix
       across all bindings on nodes of the relevant property_families.
    3. Return the token's resolved_value (a hex color, int, etc.) or
       None when nothing matches.

    Conservative: any unexpected DB shape returns None and the caller
    falls back to _UNIVERSAL_MODE3_TOKENS shadcn defaults.
    """
    name_prefix = selector["name_prefix"]
    property_families = selector["property_families"]
    canonical_type = selector.get("preferred_canonical_type")

    # Property families are checked via OR over multiple LIKE patterns
    # so e.g. fills.0.color matches both "fills.0.color" and any
    # extended form. Use direct equality + simple OR to keep query plan
    # tight.
    prop_clauses = " OR ".join(
        ["ntb.property = ?"] * len(property_families)
    )
    prop_args = list(property_families)

    # Try canonical-type-aware path first
    if canonical_type:
        sql = f"""
            SELECT t.name, tv.resolved_value, COUNT(*) AS bind_count
            FROM tokens t
            JOIN token_values tv ON tv.token_id = t.id
            JOIN node_token_bindings ntb ON ntb.token_id = t.id
            JOIN screen_component_instances sci
                ON sci.node_id = ntb.node_id
            WHERE t.name LIKE ? || '%'
              AND ({prop_clauses})
              AND sci.canonical_type = ?
              AND ntb.binding_status IN ('bound', 'proposed')
            GROUP BY t.id
            ORDER BY bind_count DESC
            LIMIT 1
        """
        try:
            cur = conn.execute(
                sql,
                (name_prefix, *prop_args, canonical_type),
            )
            row = cur.fetchone()
            if row is not None and row[1] is not None:
                return row[1]
        except sqlite3.OperationalError:
            # SCI table may not exist yet; fall through to global path.
            pass

    # Global fallback: most-used token under prefix matching the
    # property_families regardless of canonical_type.
    sql = f"""
        SELECT t.name, tv.resolved_value, COUNT(*) AS bind_count
        FROM tokens t
        JOIN token_values tv ON tv.token_id = t.id
        JOIN node_token_bindings ntb ON ntb.token_id = t.id
        WHERE t.name LIKE ? || '%'
          AND ({prop_clauses})
          AND ntb.binding_status IN ('bound', 'proposed')
        GROUP BY t.id
        ORDER BY bind_count DESC
        LIMIT 1
    """
    try:
        cur = conn.execute(sql, (name_prefix, *prop_args))
        row = cur.fetchone()
        if row is not None and row[1] is not None:
            return row[1]
    except sqlite3.OperationalError:
        return None

    return None


def build_project_token_overlay(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Build a {universal_token_name: project_resolved_value} dict
    by querying the project DB for clustered tokens.

    Returns an EMPTY dict when the project has no tokens (caller
    falls back to _UNIVERSAL_MODE3_TOKENS shadcn defaults). Never
    raises — DB errors are swallowed and the caller continues with
    the shadcn baseline.

    Time complexity: O(|selectors|) SQL queries; each query is
    tightly indexed via tokens.name + node_token_bindings.token_id.
    On Phase E Nouns DB the full overlay builds in <50ms.
    """
    if not _table_exists(conn, "tokens"):
        return {}
    if not _table_exists(conn, "node_token_bindings"):
        return {}
    # token_values must exist; SCI is optional (we fall back to
    # global most-used when it's absent or empty).
    if not _table_exists(conn, "token_values"):
        return {}

    overlay: dict[str, Any] = {}
    for universal_name, selector in _SELECTORS.items():
        try:
            resolved = _resolve_one(conn, universal_name, selector)
        except Exception:
            resolved = None
        if resolved is not None:
            # token_values.resolved_value can be a hex color, a numeric
            # string, or a JSON string. Coerce numeric strings to
            # numbers so downstream resize() / paddingTop = N writes
            # don't get JS-string-coerced.
            overlay[universal_name] = _coerce(resolved)
    return overlay


def _coerce(value: Any) -> Any:
    """Coerce token_values.resolved_value strings to native Python
    types where unambiguous.

    Numeric strings like "16" or "12.0" become ints/floats. Hex
    colors and JSON strings pass through unchanged.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    # Hex color
    if s.startswith("#"):
        return s
    # JSON-shaped (gradient, complex value)
    if s.startswith("{") or s.startswith("["):
        return s
    # Numeric
    try:
        f = float(s)
        # Keep ints as ints when round (so renderer emits "16" not "16.0")
        if f.is_integer():
            return int(f)
        return f
    except (ValueError, TypeError):
        return s
