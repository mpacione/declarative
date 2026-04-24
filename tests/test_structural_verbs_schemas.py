"""Tool-use schema contracts for the 7 edit verbs.

Stage 1 of `docs/plan-authoring-loop.md` pivots the LLM contract from
"emit a plan" to "emit edits against a current tree state." The 7
verbs are split into two surfaces:

- `dd.structural_verbs` — per-verb tool schemas the LLM can be
  asked to call. M7.4 shipped 4 (delete / append / insert / move).
  Stage 1 adds the missing 3 (set / swap / replace).

- `dd.propose_edits` (Stage 1.2) — a single unified tool that wraps
  all 7 with `oneOf` dispatch. Built on top of the 7 individual
  schemas tested here.

These tests pin the schema *shape* — the things downstream code
(prompt builders, response parsers, verifiers) depend on. Drift here
silently breaks the LLM-in-loop contract; the existing demos /
repair loop don't fail loudly when a schema changes shape, they just
stop producing valid edits.
"""

from __future__ import annotations

from dd.structural_verbs import (
    build_append_tool_schema,
    build_delete_tool_schema,
    build_insert_tool_schema,
    build_move_tool_schema,
    build_replace_tool_schema,
    build_set_tool_schema,
    build_swap_tool_schema,
)


# --------------------------------------------------------------------------- #
# Existing 4 (regression pins)                                                #
# --------------------------------------------------------------------------- #

class TestExistingSchemaShapes:
    """Pin the M7.4 schemas so the new ones can be added without
    drifting their conventions out from under the existing demos."""

    def test_delete_schema_top_level_keys(self):
        s = build_delete_tool_schema(["btn-1", "card-2"])
        assert s["name"] == "emit_delete_edit"
        assert "input_schema" in s
        ip = s["input_schema"]
        assert ip["type"] == "object"
        assert set(ip["required"]) == {"target_eid", "rationale"}
        assert ip["properties"]["target_eid"]["enum"] == ["btn-1", "card-2"]

    def test_append_schema_constrains_child_type(self):
        s = build_append_tool_schema(["frame-1"])
        ip = s["input_schema"]
        assert "frame" in ip["properties"]["child_type"]["enum"]
        assert "card" not in ip["properties"]["child_type"]["enum"], (
            "_APPENDABLE_TYPES is deliberately narrow — card swaps go "
            "through the swap verb (M7.2 territory), not append"
        )

    def test_insert_schema_uses_pair_index(self):
        pairs = [{"parent_eid": "f", "anchor_eid": "t"}]
        s = build_insert_tool_schema(pairs)
        ip = s["input_schema"]
        assert ip["properties"]["pair_index"]["enum"] == [0]

    def test_move_schema_position_is_first_or_last(self):
        pairs = [{"target_eid": "x", "dest_eid": "y"}]
        s = build_move_tool_schema(pairs)
        ip = s["input_schema"]
        assert set(ip["properties"]["position"]["enum"]) == {"first", "last"}


# --------------------------------------------------------------------------- #
# New 3 — set / swap / replace                                                #
# --------------------------------------------------------------------------- #

class TestSetToolSchema:
    """Stage 1.1: `set @<eid> <prop>=<value>` — the most-common edit
    in repair / variant flows. The schema must constrain ``target_eid``
    to the doc's actual eid set (no hallucination), gate ``property``
    to a closed key set per parent type, and accept a literal value.
    """

    def test_returns_tool_schema_with_emit_set_edit_name(self):
        s = build_set_tool_schema(["btn-1", "card-2"])
        assert s["name"] == "emit_set_edit"
        assert "input_schema" in s

    def test_target_eid_is_enum_constrained(self):
        s = build_set_tool_schema(["btn-1"])
        assert s["input_schema"]["properties"]["target_eid"]["enum"] == ["btn-1"]

    def test_required_fields_minimal(self):
        s = build_set_tool_schema(["btn-1"])
        required = set(s["input_schema"]["required"])
        # property + value are both load-bearing; rationale per
        # convention from the other 4.
        assert {"target_eid", "property", "value", "rationale"}.issubset(required)

    def test_property_is_string_with_pattern(self):
        s = build_set_tool_schema(["btn-1"])
        prop_schema = s["input_schema"]["properties"]["property"]
        assert prop_schema["type"] == "string"
        # Stage 1 keeps property OPEN to support the closed
        # capability table at apply time (per principle in plan §1.4).
        # Pattern restricts to safe identifier shape; runtime
        # validation against capability table is apply_edits's job.
        assert "pattern" in prop_schema

    def test_value_accepts_string_or_number_or_token_ref(self):
        """Property values can be strings ("disabled"), numbers (16),
        or token refs ({color.brand.600}). Schema permissiveness is
        intentional — apply_edits + the capability table do the
        rejection at apply time, not at schema-validation time."""
        s = build_set_tool_schema(["btn-1"])
        v_schema = s["input_schema"]["properties"]["value"]
        # Permits strings (most common — variant=disabled, label="Save").
        # Accept any-of OR string here; both shapes are legitimate.
        assert v_schema.get("type") in ("string", None)


class TestSwapToolSchema:
    """Stage 1.1: `swap @<eid> with=-> <component_path>` — pivots an
    existing instance to a different component master (Mode-1 swap).
    Distinct from `replace` (which substitutes whole subtrees).
    Component_path must be enum-constrained to the project's CKR.
    """

    def test_returns_tool_schema_with_emit_swap_edit_name(self):
        s = build_swap_tool_schema(["icon-1"], ["icon/back", "icon/close"])
        assert s["name"] == "emit_swap_edit"
        assert "input_schema" in s

    def test_target_eid_enum_constrained(self):
        s = build_swap_tool_schema(["icon-1"], ["icon/back"])
        assert s["input_schema"]["properties"]["target_eid"]["enum"] == ["icon-1"]

    def test_with_component_enum_constrained_to_ckr(self):
        """The swap target MUST be a known CKR component. Without the
        enum, the LLM hallucinates names like 'icon/menu-v2'."""
        s = build_swap_tool_schema(["icon-1"], ["icon/back", "icon/close"])
        with_schema = s["input_schema"]["properties"]["with_component"]
        assert with_schema["type"] == "string"
        assert set(with_schema["enum"]) == {"icon/back", "icon/close"}

    def test_required_fields(self):
        s = build_swap_tool_schema(["icon-1"], ["icon/back"])
        assert set(s["input_schema"]["required"]) >= {
            "target_eid", "with_component", "rationale",
        }


class TestReplaceToolSchema:
    """Stage 1.1: `replace @<eid> { ...subtree... }` — wholesale
    subtree substitution. The replacement subtree follows the same
    flat-row shape as plan emission (Stage 0.3), so the schema reuses
    the catalog type + new-eid constraints from the append/insert
    pattern.
    """

    def test_returns_tool_schema_with_emit_replace_edit_name(self):
        s = build_replace_tool_schema(["card-1"])
        assert s["name"] == "emit_replace_edit"
        assert "input_schema" in s

    def test_target_eid_enum_constrained(self):
        s = build_replace_tool_schema(["card-1", "frame-2"])
        assert s["input_schema"]["properties"]["target_eid"]["enum"] == [
            "card-1", "frame-2",
        ]

    def test_replacement_root_type_enum_constrained(self):
        """The replacement subtree's root type must be from the
        appendable set — same constraint as append/insert. Otherwise
        the LLM swaps in a `screen` mid-tree."""
        s = build_replace_tool_schema(["card-1"])
        rt = s["input_schema"]["properties"]["replacement_root_type"]
        assert rt["type"] == "string"
        # Reuse the same _APPENDABLE_TYPES from append/insert.
        assert "frame" in rt["enum"]

    def test_replacement_root_eid_pattern(self):
        """The new root eid must match the kebab-case pattern used by
        the append/insert schemas."""
        s = build_replace_tool_schema(["card-1"])
        eid = s["input_schema"]["properties"]["replacement_root_eid"]
        assert eid["pattern"].startswith("^[a-z]")

    def test_required_fields(self):
        s = build_replace_tool_schema(["card-1"])
        required = set(s["input_schema"]["required"])
        assert {
            "target_eid", "replacement_root_type",
            "replacement_root_eid", "rationale",
        }.issubset(required)
