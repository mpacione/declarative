"""Tests for prompt→IR composition (Phase 4b)."""

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.compose import (
    build_template_visuals,
    collect_template_rebind_entries,
    compare_generated_vs_ground_truth,
    compose_screen,
    generate_from_prompt,
    resolve_type_aliases,
    validate_components,
)
from dd.db import init_db

# ---------------------------------------------------------------------------
# compose_screen tests
# ---------------------------------------------------------------------------

class TestComposeScreen:
    """Verify compose_screen builds a spec from a component list."""

    def test_produces_spec_with_root(self):
        spec = compose_screen([{"type": "header"}, {"type": "button"}])
        assert "root" in spec
        assert spec["root"] in spec["elements"]

    def test_root_has_children(self):
        spec = compose_screen([{"type": "header"}, {"type": "button"}])
        root = spec["elements"][spec["root"]]
        assert "children" in root
        assert len(root["children"]) == 2

    def test_elements_have_type(self):
        spec = compose_screen([{"type": "header"}, {"type": "card"}])
        types = {el["type"] for el in spec["elements"].values()}
        assert "header" in types
        assert "card" in types

    def test_elements_have_unique_ids(self):
        spec = compose_screen([{"type": "button"}, {"type": "button"}])
        button_ids = [eid for eid in spec["elements"] if eid.startswith("button")]
        assert len(button_ids) == 2
        assert button_ids[0] != button_ids[1]

    def test_props_passed_through(self):
        spec = compose_screen([{"type": "button", "props": {"text": "Save"}}])
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["props"]["text"] == "Save"

    def test_nested_children(self):
        spec = compose_screen([{
            "type": "card",
            "children": [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "text", "props": {"text": "Body"}},
            ],
        }])
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert len(card["children"]) == 2

    # -- ADR-008 v0.1.5 H1: template style must apply even when LLM
    # supplied the children --

    def test_card_with_llm_children_still_inherits_template_style(self):
        """Forensic finding: before H1, a card with LLM-supplied
        children never received the PresentationTemplate's fill /
        stroke / radius because the merge only ran inside
        _mode3_synthesise_children, which is gated on `no children`.

        After H1: the card element's `style` dict is populated
        regardless of whether children come from the LLM or from
        synthesis.
        """
        spec = compose_screen([{
            "type": "card",
            "children": [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "text", "props": {"text": "Body"}},
            ],
        }])
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert "style" in card
        # Universal provider defines fill/stroke/radius on card
        assert "fill" in card["style"]
        assert "radius" in card["style"]

    def test_card_with_llm_children_still_inherits_template_padding(self):
        """Layout.padding from the template is also preserved — not
        just the style block."""
        spec = compose_screen([{
            "type": "card",
            "children": [{"type": "text", "props": {"text": "x"}}],
        }])
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert "layout" in card
        assert "padding" in card["layout"]

    def test_component_key_path_does_not_receive_mode3_style(self):
        """A node with an explicit component_key is Mode-1 reuse; the
        PresentationTemplate style must NOT overlay — the project
        instance owns its visuals."""
        spec = compose_screen([{
            "type": "button",
            "component_key": "button/primary",
            "props": {"text": "Go"},
        }])
        btn = next(el for el in spec["elements"].values() if el["type"] == "button")
        # Mode-1 path preserves component_key
        assert btn.get("component_key") == "button/primary"
        # Style must NOT have been applied from the template
        assert "style" not in btn or not btn["style"].get("fill")

    def test_layout_from_templates(self):
        templates = {
            "header": [{"layout_mode": "HORIZONTAL", "width": 428.0, "height": 111.0,
                         "padding_top": 0, "padding_right": 0, "padding_bottom": 0, "padding_left": 0,
                         "item_spacing": None, "primary_align": None, "counter_align": None}],
        }
        spec = compose_screen([{"type": "header"}], templates=templates)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert header["layout"]["direction"] == "horizontal"
        assert header["layout"]["sizing"]["width"] == 428.0

    def test_empty_list_produces_empty_screen(self):
        spec = compose_screen([])
        root = spec["elements"][spec["root"]]
        assert root["children"] == []

    def test_version_present(self):
        spec = compose_screen([])
        assert spec["version"] == "1.0"


class TestComposePreservesPlannerEids:
    """Stage 0.4 — LLM-provided ``eid`` survives into ``spec['elements']``.

    Pre-Stage-0 the counter allocator discards whatever the planner named
    an entity and emits ``<type>-<N>``. That destroys downstream
    addressability: the edit grammar, session log, and drift check can
    no longer refer to ``product-showcase-section`` because compose
    silently renamed it to ``frame-1``.
    """

    def test_eid_on_top_level_node_survives(self):
        spec = compose_screen([{"type": "card", "eid": "product-showcase-section"}])
        assert "product-showcase-section" in spec["elements"]
        assert spec["elements"]["product-showcase-section"]["type"] == "card"

    def test_eid_on_nested_node_survives(self):
        spec = compose_screen([{
            "type": "card",
            "eid": "product-showcase-section",
            "children": [
                {"type": "heading", "eid": "section-title"},
                {"type": "text", "eid": "section-body"},
            ],
        }])
        assert "section-title" in spec["elements"]
        assert "section-body" in spec["elements"]
        card = spec["elements"]["product-showcase-section"]
        assert set(card["children"]) == {"section-title", "section-body"}

    def test_missing_eid_falls_back_to_counter(self):
        """Nodes without ``eid`` still get the legacy counter form so
        pre-Stage-0 callers aren't broken."""
        spec = compose_screen([{"type": "card"}, {"type": "card"}])
        card_ids = [eid for eid, el in spec["elements"].items() if el["type"] == "card"]
        assert len(card_ids) == 2
        assert all(eid.startswith("card-") for eid in card_ids)

    def test_eid_collision_falls_back_to_counter(self):
        """Two LLM nodes that claim the same ``eid`` keep it for the
        first; the second falls back to the counter form. Stage 0.6's
        drift check is expected to surface duplicate-eid as KIND_PLAN_DRIFT
        before we reach compose, but compose itself must not crash.
        """
        spec = compose_screen([
            {"type": "card", "eid": "my-card"},
            {"type": "card", "eid": "my-card"},
        ])
        assert "my-card" in spec["elements"]
        # Second one got a counter-allocated id
        card_ids = [eid for eid, el in spec["elements"].items() if el["type"] == "card"]
        assert len(card_ids) == 2

    def test_invalid_eid_falls_back_to_counter(self):
        """Non-string / empty / whitespace eids fall back silently.
        Validation of eid shape is the planner's job; compose is lenient.
        """
        spec = compose_screen([{"type": "card", "eid": ""}, {"type": "card", "eid": "   "}])
        card_ids = [eid for eid, el in spec["elements"].items() if el["type"] == "card"]
        assert len(card_ids) == 2
        assert all(eid.startswith("card-") for eid in card_ids)


# ---------------------------------------------------------------------------
# build_template_visuals tests
# ---------------------------------------------------------------------------

class TestBuildTemplateVisuals:
    """Verify build_template_visuals maps elements to template visual data."""

    def _make_templates(self):
        return {
            "button": [{"fills": '[{"type":"SOLID","color":{"r":0,"g":0.5,"b":1,"a":1}}]',
                         "strokes": None, "effects": None, "corner_radius": "10",
                         "opacity": 1.0, "stroke_weight": None,
                         "component_key": "key_btn_solid"}],
            "header": [{"fills": '[{"type":"SOLID","color":{"r":0.98,"g":0.98,"b":0.98,"a":1}}]',
                         "strokes": None, "effects": '[{"type":"BACKGROUND_BLUR","visible":true,"radius":15}]',
                         "corner_radius": None, "opacity": 0.95, "stroke_weight": None}],
        }

    def test_returns_visuals_dict(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        assert isinstance(visuals, dict)
        assert len(visuals) > 0

    def test_assigns_synthetic_node_ids(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        assert "_node_id_map" in spec
        for eid in spec["elements"]:
            assert eid in spec["_node_id_map"]

    def test_visuals_have_fills(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        assert visuals[nid]["fills"] is not None

    def test_visuals_have_bindings_list(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        for v in visuals.values():
            assert "bindings" in v
            assert v["bindings"] == []

    def test_unknown_type_gets_empty_visual(self):
        spec = compose_screen([{"type": "unknown_widget"}])
        visuals = build_template_visuals(spec, self._make_templates())
        unknown_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "unknown_widget")
        nid = spec["_node_id_map"][unknown_eid]
        assert visuals[nid]["fills"] is None

    def test_component_key_propagated(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        assert visuals[nid]["component_key"] == "key_btn_solid"

    def test_no_component_key_for_unknown_type(self):
        spec = compose_screen([{"type": "unknown_widget"}])
        visuals = build_template_visuals(spec, self._make_templates())
        eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "unknown_widget")
        nid = spec["_node_id_map"][eid]
        assert visuals[nid]["component_key"] is None

    def test_extracts_bound_variables_from_fills(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:5438:33630"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        bindings = visuals[nid]["bindings"]
        assert len(bindings) >= 1
        assert bindings[0]["property"] == "fill.0.color"
        assert bindings[0]["variable_id"] == "VariableID:5438:33630"

    def test_extracts_bound_variables_from_strokes(self):
        templates = {
            "card": [{
                "fills": None,
                "strokes": '[{"type":"SOLID","color":{"r":0.5,"g":0.5,"b":0.5,"a":1},'
                           '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:111:222"}}}]',
                "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "card"}])
        visuals = build_template_visuals(spec, templates)
        card_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "card")
        nid = spec["_node_id_map"][card_eid]
        bindings = visuals[nid]["bindings"]
        assert any(b["property"] == "stroke.0.color" for b in bindings)


# ---------------------------------------------------------------------------
# collect_template_rebind_entries tests
# ---------------------------------------------------------------------------

class TestCollectTemplateRebindEntries:
    """Verify rebind entries are collected from template boundVariables."""

    def test_collects_entries_from_fills(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:5438:33630"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        button_entries = [e for e in entries if e["element_id"].startswith("button")]
        assert len(button_entries) >= 1
        assert button_entries[0]["variable_id"] == "VariableID:5438:33630"

    def test_empty_when_no_bound_variables(self):
        templates = {
            "card": [{
                "fills": '[{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "card"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        card_entries = [e for e in entries if e["element_id"].startswith("card")]
        assert len(card_entries) == 0

    def test_entries_have_required_keys(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:1:2"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        for entry in entries:
            assert "element_id" in entry
            assert "property" in entry
            assert "variable_id" in entry


# ---------------------------------------------------------------------------
# generate_from_prompt tests
# ---------------------------------------------------------------------------

class TestGenerateFromPrompt:
    """Verify generate_from_prompt produces valid Figma JS."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        # Insert a template
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, padding_top, padding_right, padding_bottom, padding_left, "
            "item_spacing, fills, corner_radius, opacity) "
            "VALUES ('button', 'default', NULL, 10, "
            "'HORIZONTAL', 200, 48, 0, 16, 0, 16, "
            "10, '[{\"type\":\"SOLID\",\"color\":{\"r\":0,\"g\":0.5,\"b\":1,\"a\":1}}]', '10', 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, "
            "layout_mode, width, height, fills, opacity) "
            "VALUES ('heading', 'default', 5, "
            "NULL, 396, 28, NULL, 1.0)"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_produces_figma_script(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        assert "structure_script" in result
        assert "figma.createFrame()" in result["structure_script"]

    def test_script_has_visual_properties(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        script = result["structure_script"]
        assert "fills = [{" in script

    def test_script_has_layout(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        script = result["structure_script"]
        assert "layoutMode" in script
        assert "resize(" in script

    def test_element_count(self, db):
        result = generate_from_prompt(
            db,
            [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "button", "props": {"text": "Save"}},
            ],
        )
        assert result["element_count"] >= 3  # screen + heading + button

    def test_includes_template_rebind_entries(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Save"}}],
        )
        assert "template_rebind_entries" in result
        assert isinstance(result["template_rebind_entries"], list)


class TestF1ImportComponentByKey:
    """F1 regression: when component_templates resolves a component_key
    but ``component_key_registry`` lacks the figma_node_id (the common
    case on freshly-extracted DBs without a CKR build pass), the
    generated script must emit ``importComponentByKeyAsync(<key>)``
    rather than silently falling through to ``createFrame()``.

    Pre-fix behavior: 0 imports, every keyed element rendered as a
    generic frame (verified against the audit DB at
    ``audit/20260425-1042/sections/08-mode3-composition``).
    """

    @pytest.fixture
    def db_with_keyed_button(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        # Real component_key, no component_figma_id (simulates fresh DB
        # where CKR.figma_node_id is null)
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, padding_top, padding_right, "
            "padding_bottom, padding_left, item_spacing, fills, corner_radius, opacity) "
            "VALUES ('button', 'project/primary', 'real_button_key_abc', 50, "
            "'HORIZONTAL', 100, 40, 8, 16, 8, 16, 8, "
            "'[{\"type\":\"SOLID\",\"color\":{\"r\":0,\"g\":0.5,\"b\":1,\"a\":1}}]', "
            "'8', 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height) "
            "VALUES ('card', 'project/default', 'real_card_key_xyz', 100, "
            "'VERTICAL', 320, 200)"
        )
        # CKR table exists but figma_node_id is null (the broken state
        # this fix addresses).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry ("
            "component_key TEXT PRIMARY KEY, "
            "figma_node_id TEXT, "
            "name TEXT NOT NULL, "
            "instance_count INTEGER)"
        )
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES ('real_button_key_abc', NULL, 'project/primary', 50), "
            "       ('real_card_key_xyz', NULL, 'project/default', 100)"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_emits_import_component_by_key(self, db_with_keyed_button):
        """A keyed button should be emitted via importComponentByKeyAsync."""
        result = generate_from_prompt(
            db_with_keyed_button,
            [{"type": "button", "props": {"text": "Submit"}}],
        )
        script = result["structure_script"]
        assert 'importComponentByKeyAsync("real_button_key_abc")' in script
        # F1 regression guard: pre-fix this asserted == 0; the bug was
        # that the renderer silently fell through to createFrame.
        assert script.count("importComponentByKeyAsync") >= 1

    def test_emits_import_for_keyed_card_with_children(
        self, db_with_keyed_button,
    ):
        """A card with children must still resolve to its keyed instance.

        The pre-F1 behavior was to fall through to createFrame because
        the renderer's gate accepted component_key but no emission
        branch matched it. The instance subtree handles its own
        children — the LLM-supplied children are still spliced via the
        override tree path.
        """
        result = generate_from_prompt(
            db_with_keyed_button,
            [{
                "type": "card",
                "children": [
                    {"type": "heading", "props": {"text": "Title"}},
                    {"type": "button", "props": {"text": "Submit"}},
                ],
            }],
        )
        script = result["structure_script"]
        assert "importComponentByKeyAsync" in script
        # Both the card AND the button are keyed
        assert script.count("importComponentByKeyAsync") >= 2

    def test_falls_back_to_frame_when_no_key_at_all(self, db_with_keyed_button):
        """A type with no template at all still falls through to a frame
        (the F1 fix is component_key-aware, not a blanket override).
        """
        result = generate_from_prompt(
            db_with_keyed_button,
            [{"type": "frame", "children": []}],
        )
        script = result["structure_script"]
        # `frame` has no template row; renderer creates a Mode-2 frame.
        assert "figma.createFrame()" in script

    def test_universal_text_types_do_not_warn(self, db_with_keyed_button):
        """text/heading/link/frame are universal IR primitives — they
        render via createText() or createFrame() respectively and should
        NOT emit a "no template" warning even though they don't have a
        component_templates row. Pre-F1 the warning fired for `link`
        (a text type) which was misleading.
        """
        result = generate_from_prompt(
            db_with_keyed_button,
            [
                {"type": "link", "props": {"text": "Forgot password?"}},
                {"type": "frame", "children": []},
                {"type": "text", "props": {"text": "Hello"}},
            ],
        )
        warnings = result.get("warnings", [])
        misleading = [
            w for w in warnings
            if "Type 'link'" in w
            or "Type 'frame'" in w
            or "Type 'text'" in w
            or "Type 'heading'" in w
        ]
        assert misleading == [], (
            f"Universal types should not warn 'no template': {misleading}"
        )


class TestF9ComponentKeyNormalization:
    """F9 regression: the LLM is intentionally told it may emit
    ``"component_key": "<name>"`` (per ``dd/prompt_parser.py:65,204``)
    using names from the project's CKR vocabulary block. Without
    composer-side normalisation, those name-as-key values leak through
    to ``figma.importComponentByKeyAsync(...)``, which Figma rejects —
    100% of name-emitted instances degrade to wireframe placeholders.

    Pre-fix evidence (audit/20260425-1626-validation/sections/
    08-mode3-composition): 3 of 5 import args were CKR names
    (``"cards/_default"``, ``"buttons/button with icon"``,
    ``"icons/left chevron"``).

    The fix adds a ``_resolve_component_keys`` pre-pass between
    ``compose_screen`` and ``build_template_visuals`` that swaps each
    CKR name for its real 40-char hex key, drops unknown values with
    a warning, and is fully DB-driven (no hardcoded names).
    """

    _HEX_KEY_BUTTON = "a" * 40
    _HEX_KEY_CARD = "b" * 40

    @pytest.fixture
    def db_with_ckr_names(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Test')")
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height) "
            "VALUES ('card', 'cards/_default', ?, 100, 'VERTICAL', 320, 200)",
            (self._HEX_KEY_CARD,),
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height) "
            "VALUES ('button', 'buttons/button with icon', ?, 50, "
            "'HORIZONTAL', 120, 40)",
            (self._HEX_KEY_BUTTON,),
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry ("
            "component_key TEXT PRIMARY KEY, "
            "figma_node_id TEXT, "
            "name TEXT NOT NULL, "
            "instance_count INTEGER)"
        )
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES (?, NULL, 'cards/_default', 100), "
            "       (?, NULL, 'buttons/button with icon', 50)",
            (self._HEX_KEY_CARD, self._HEX_KEY_BUTTON),
        )
        conn.commit()
        yield conn
        conn.close()

    def test_ckr_name_component_key_is_normalized_to_real_key(
        self, db_with_ckr_names,
    ):
        """LLM emits ``component_key: "cards/_default"`` (a CKR name);
        the generated script must call ``importComponentByKeyAsync``
        with the real 40-char hex key, NOT with the name.
        """
        result = generate_from_prompt(
            db_with_ckr_names,
            [{"type": "card", "component_key": "cards/_default"}],
        )
        script = result["structure_script"]
        assert f'importComponentByKeyAsync("{self._HEX_KEY_CARD}")' in script
        assert 'importComponentByKeyAsync("cards/_default")' not in script

    def test_real_ckr_key_is_preserved(self, db_with_ckr_names):
        """LLM emits a real 40-char CKR hex key directly — pre-pass
        must not corrupt it.
        """
        result = generate_from_prompt(
            db_with_ckr_names,
            [{"type": "button", "component_key": self._HEX_KEY_BUTTON}],
        )
        script = result["structure_script"]
        assert f'importComponentByKeyAsync("{self._HEX_KEY_BUTTON}")' in script

    def test_unknown_component_key_name_is_not_imported(
        self, db_with_ckr_names,
    ):
        """LLM emits a name that doesn't exist in CKR — the field must
        be dropped (no rejected import call) and a warning surfaced so
        the LLM-loop / orchestrator can see what went unresolved.
        """
        result = generate_from_prompt(
            db_with_ckr_names,
            [{"type": "card", "component_key": "cards/missing"}],
        )
        script = result["structure_script"]
        warnings = result["warnings"]
        assert 'importComponentByKeyAsync("cards/missing")' not in script
        assert any(
            "unresolved component_key" in w and "cards/missing" in w
            for w in warnings
        ), f"missing unresolved-component_key warning in {warnings!r}"

    def test_template_key_not_overridden_by_ckr_name(
        self, db_with_ckr_names,
    ):
        """Belt-and-braces: when both ``variant`` AND ``component_key``
        point at the same CKR name, the import arg must still be the
        real hex key — not the name leaking through via either route.

        Pre-fix this was the dominant failure mode in
        ``dd/compose.py:1124`` where ``ir_component_key`` (a name)
        unconditionally overrode ``tmpl.component_key`` (the real key)
        on the way into ``visual_entry``.
        """
        result = generate_from_prompt(
            db_with_ckr_names,
            [{
                "type": "card",
                "variant": "cards/_default",
                "component_key": "cards/_default",
            }],
        )
        script = result["structure_script"]
        assert f'importComponentByKeyAsync("{self._HEX_KEY_CARD}")' in script
        assert 'importComponentByKeyAsync("cards/_default")' not in script


# ---------------------------------------------------------------------------
# Variant-aware template selection tests
# ---------------------------------------------------------------------------

class TestVariantAwareSelection:
    """Verify compose_screen uses variant to select specific templates."""

    def test_variant_passed_through_to_element(self):
        spec = compose_screen([
            {"type": "button", "variant": "button/large/translucent"},
        ])
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["variant"] == "button/large/translucent"

    def test_variant_selects_matching_template(self):
        templates = {
            "button": [
                {"variant": "button/small/solid", "layout_mode": "HORIZONTAL",
                 "width": 100, "height": 40, "instance_count": 500},
                {"variant": "button/large/translucent", "layout_mode": "HORIZONTAL",
                 "width": 152, "height": 52, "instance_count": 3606},
            ],
        }
        spec = compose_screen(
            [{"type": "button", "variant": "button/large/translucent"}],
            templates=templates,
        )
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["layout"]["sizing"]["width"] == 152

    def test_sizing_mode_from_template(self):
        templates = {
            "card": [{
                "layout_mode": "VERTICAL", "width": 428, "height": 194,
                "layout_sizing_h": "HUG", "layout_sizing_v": "HUG",
                "instance_count": 50,
            }],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["sizing"]["width"] == "hug"
        assert card["layout"]["sizing"]["height"] == "hug"

    def test_fixed_sizing_when_no_mode(self):
        templates = {
            "card": [{
                "layout_mode": "VERTICAL", "width": 428, "height": 194,
                "instance_count": 50,
            }],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["sizing"]["width"] == 428
        assert card["layout"]["sizing"]["height"] == 194

    def test_without_variant_uses_highest_count(self):
        templates = {
            "button": [
                {"variant": "button/small/solid", "layout_mode": "HORIZONTAL",
                 "width": 100, "height": 40, "instance_count": 500,
                 "component_key": "key_small"},
                {"variant": "button/large/translucent", "layout_mode": "HORIZONTAL",
                 "width": 152, "height": 52, "instance_count": 3606,
                 "component_key": "key_large"},
            ],
        }
        spec = compose_screen([{"type": "button"}], templates=templates)
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["layout"]["sizing"]["width"] == 152


# ---------------------------------------------------------------------------
# Ground truth comparison tests
# ---------------------------------------------------------------------------

class TestCompareGeneratedVsGroundTruth:
    """Verify automated ground truth comparison against real DB screens."""

    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_catalog(conn)

        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        file_id = conn.execute("SELECT id FROM files LIMIT 1").fetchone()[0]

        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height, screen_type) "
            "VALUES (?, '1:1', 'Test Screen', 428, 926, 'app_screen')",
            (file_id,),
        )
        screen_id = conn.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]

        # Add nodes at depth 0 (screen frame)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, width, height) "
            "VALUES (?, '1:1', 'Test Screen', 'FRAME', 0, 428, 926)",
            (screen_id,),
        )

        # Add classified instances
        for i, (ctype, comp_key) in enumerate([
            ("header", "key_header"),
            ("card", None),
            ("button", "key_btn1"),
            ("button", "key_btn2"),
            ("text", None),
            ("text", None),
            ("icon", "key_icon1"),
        ]):
            node_id_val = f"node_{i}"
            conn.execute(
                "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, width, height, component_key) "
                "VALUES (?, ?, ?, 'INSTANCE', 1, 100, 50, ?)",
                (screen_id, node_id_val, f"{ctype}-{i}", comp_key),
            )
            nid = conn.execute("SELECT id FROM nodes WHERE figma_node_id = ?", (node_id_val,)).fetchone()[0]
            conn.execute(
                "INSERT INTO screen_component_instances (screen_id, node_id, canonical_type, classification_source) VALUES (?, ?, ?, 'heuristic')",
                (screen_id, nid, ctype),
            )

        conn.commit()
        yield conn
        conn.close()

    def test_returns_structured_report(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "button"},
                {"type": "text"},
            ]},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "generated" in report
        assert "reference" in report
        assert "diff" in report

    def test_reports_element_counts(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert report["generated"]["element_count"] > 0
        assert report["reference"]["element_count"] == 7

    def test_reports_type_distribution(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
            {"type": "button"},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "button" in report["reference"]["type_distribution"]
        assert report["reference"]["type_distribution"]["button"] == 2

    def test_reports_mode_ratio(self, db):
        spec = compose_screen([{"type": "button"}])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "mode1_count" in report["reference"]
        assert "mode2_count" in report["reference"]
        assert report["reference"]["mode1_count"] == 4  # header + 2 buttons + icon have keys
        assert report["reference"]["mode2_count"] == 3  # card + 2 text

    def test_diff_shows_missing_and_extra_types(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
            {"type": "slider"},  # not in reference
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "button" in report["diff"]["missing_types"]
        assert "slider" in report["diff"]["extra_types"]

    def test_empty_spec_reports_all_missing(self, db):
        spec = compose_screen([])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert report["generated"]["element_count"] == 1  # just screen root
        assert len(report["diff"]["missing_types"]) > 0


# ---------------------------------------------------------------------------
# Type alias resolution tests
# ---------------------------------------------------------------------------

class TestResolveTypeAliases:
    """Verify unsupported types resolve to existing template types."""

    def test_toggle_becomes_container(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}]}
        components = [{"type": "toggle", "props": {"text": "Dark Mode"}}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "container"
        assert len(resolved[0]["children"]) == 2

    def test_toggle_has_text_and_icon_children(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}]}
        components = [{"type": "toggle", "props": {"text": "Dark Mode"}}]
        resolved = resolve_type_aliases(components, templates)
        child_types = {c["type"] for c in resolved[0]["children"]}
        assert "text" in child_types
        assert "icon" in child_types

    def test_toggle_label_gets_text_prop(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}]}
        components = [{"type": "toggle", "props": {"text": "Dark Mode"}}]
        resolved = resolve_type_aliases(components, templates)
        text_child = next(c for c in resolved[0]["children"] if c["type"] == "text")
        assert text_child["props"]["text"] == "Dark Mode"

    def test_toggle_container_is_horizontal(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}]}
        components = [{"type": "toggle"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0].get("layout_direction") == "horizontal"

    def test_checkbox_becomes_container(self):
        templates = {"icon": [{"variant": "icon/checkbox-empty"}], "text": [{"variant": "default"}]}
        components = [{"type": "checkbox", "props": {"text": "Accept"}}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "container"
        icon_child = next(c for c in resolved[0]["children"] if c["type"] == "icon")
        assert icon_child["variant"] == "icon/checkbox-empty"

    def test_supported_type_unchanged(self):
        templates = {"button": [{"variant": "default", "instance_count": 10}]}
        components = [{"type": "button"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "button"

    def test_unknown_type_left_unchanged(self):
        templates = {"button": [{"variant": "default"}]}
        components = [{"type": "slider"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "slider"

    def test_explicit_variant_uses_simple_alias(self):
        templates = {"icon": [{"variant": "icon/switch"}]}
        components = [{"type": "toggle", "variant": "custom-toggle"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["variant"] == "custom-toggle"

    def test_nested_children_resolved(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}], "card": [{"variant": "default"}]}
        components = [{"type": "card", "children": [{"type": "toggle", "props": {"text": "On"}}]}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["children"][0]["type"] == "container"

    def test_simple_alias_still_works(self):
        templates = {"tabs": [{"variant": "nav/tabs"}]}
        components = [{"type": "segmented_control"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "tabs"
        assert resolved[0]["variant"] == "nav/tabs"

    def test_toggle_without_text_still_has_icon(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}]}
        components = [{"type": "toggle"}]
        resolved = resolve_type_aliases(components, templates)
        assert resolved[0]["type"] == "container"
        icon_child = next(c for c in resolved[0]["children"] if c["type"] == "icon")
        assert icon_child["variant"] == "icon/switch"


class TestFontDataInComposition:
    """Verify font properties flow from templates into element styles."""

    def test_build_template_visuals_includes_font_data(self):
        templates = {
            "text": [{
                "fills": None, "strokes": None, "effects": None,
                "corner_radius": None, "opacity": 1.0,
                "font_family": "Inter Variable", "font_size": 16.0,
                "font_weight": 600, "font_style": "Regular",
                "line_height": '{"unit": "AUTO"}', "letter_spacing": None,
                "text_align": "LEFT",
            }],
        }
        spec = compose_screen([{"type": "text", "props": {"text": "Hello"}}])
        visuals = build_template_visuals(spec, templates)
        text_nid = next(nid for nid, v in visuals.items() if v.get("font"))
        assert visuals[text_nid]["font"]["font_family"] == "Inter Variable"
        assert visuals[text_nid]["font"]["font_size"] == 16.0
        assert visuals[text_nid]["font"]["font_weight"] == 600

    def test_no_font_data_when_template_lacks_fonts(self):
        templates = {
            "card": [{
                "fills": None, "strokes": None, "effects": None,
                "corner_radius": None, "opacity": 1.0,
            }],
        }
        spec = compose_screen([{"type": "card"}])
        visuals = build_template_visuals(spec, templates)
        card_nid = next(nid for nid, v in visuals.items()
                        if v.get("component_key") is None and nid != list(visuals.keys())[0])
        assert "font" not in visuals[card_nid] or not visuals[card_nid].get("font")

    def test_font_data_not_on_screen_element(self):
        templates = {
            "text": [{
                "fills": None, "strokes": None, "effects": None,
                "corner_radius": None, "opacity": 1.0,
                "font_family": "Inter", "font_size": 14.0, "font_weight": 400,
            }],
        }
        spec = compose_screen([{"type": "text", "props": {"text": "Hi"}}])
        visuals = build_template_visuals(spec, templates)
        screen_nid = spec["_node_id_map"]["screen-1"]
        assert not visuals[screen_nid].get("font")


class TestAutoLayoutScreenRoot:
    """Verify compose_screen uses vertical auto-layout for the screen root.

    ADR-008 PR #1 Part C: the screen root defaults to ``direction:
    vertical`` with padding, gap, and FILL-width children. The pre-
    ADR-008 ``absolute + y_cursor += 50`` path survives only when a
    screen template explicitly emits an unknown direction.
    """

    def test_root_direction_is_vertical(self):
        spec = compose_screen([{"type": "header"}])
        root = spec["elements"][spec["root"]]
        assert root["layout"]["direction"] == "vertical"

    def test_root_has_clips_content(self):
        spec = compose_screen([{"type": "header"}])
        root = spec["elements"][spec["root"]]
        assert root.get("clipsContent") is True

    def test_root_has_padding_and_gap(self):
        spec = compose_screen([{"type": "header"}])
        root = spec["elements"][spec["root"]]
        padding = root["layout"].get("padding") or {}
        for side in ("top", "right", "bottom", "left"):
            assert padding.get(side, 0) >= 0
        assert root["layout"].get("gap") is not None

    def test_children_have_no_absolute_positions(self):
        """Auto-layout children stack by tree order; no x/y computed."""
        templates = {
            "header": [{"layout_mode": "HORIZONTAL", "width": 428, "height": 111,
                        "instance_count": 10}],
            "card": [{"layout_mode": "VERTICAL", "width": 428, "height": 200,
                      "instance_count": 10}],
        }
        spec = compose_screen(
            [{"type": "header"}, {"type": "card"}],
            templates=templates,
        )
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert "position" not in header["layout"]
        assert "position" not in card["layout"]

    def test_children_span_screen_width_by_default(self):
        """Children inherit FILL width unless they already declared one."""
        spec = compose_screen([{"type": "header"}])
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert header["layout"]["sizing"]["width"] == "fill"

    def test_child_width_preserved_when_explicitly_set(self):
        """A child with its own width (from template or override) keeps it."""
        templates = {
            "button": [{"layout_mode": "HORIZONTAL", "width": 200, "height": 48,
                        "layout_sizing_h": "HUG", "layout_sizing_v": "HUG",
                        "instance_count": 10}],
        }
        spec = compose_screen([{"type": "button", "props": {"text": "x"}}], templates=templates)
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        # HUG sizing wins over the FILL default
        assert button["layout"]["sizing"]["width"] == "hug"

    def test_hug_card_uses_pixel_width_for_sizing(self):
        """Cards with HUG sizing should still get pixel width from template."""
        templates = {
            "card": [{"layout_mode": "VERTICAL", "width": 428, "height": 194,
                      "layout_sizing_h": "HUG", "layout_sizing_v": "HUG",
                      "instance_count": 10}],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        sizing = card["layout"]["sizing"]
        # Should have pixel width available even with HUG mode
        assert sizing.get("widthPixels") == 428 or sizing.get("width") == 428

    def test_children_positions_cleared_if_inherited(self):
        """Absolute `position` dict inherited from an earlier compose path
        must be cleared when the screen root is auto-layout."""
        templates = {
            "header": [{"layout_mode": "HORIZONTAL", "width": 428, "height": 111,
                        "instance_count": 10}],
        }
        spec = compose_screen([{"type": "header"}], templates=templates)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert "position" not in header["layout"]

    def test_children_have_pixel_dimensions_under_absolute(self):
        """Absolute-positioned children should have pixel width/height for resize."""
        templates = {
            "card": [{"layout_mode": "VERTICAL", "width": 428, "height": 194,
                      "layout_sizing_h": "HUG", "layout_sizing_v": "HUG",
                      "instance_count": 10}],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        sizing = card["layout"]["sizing"]
        # Renderer needs pixel values for resize() under absolute parent
        assert sizing.get("widthPixels") == 428
        assert sizing.get("heightPixels") == 194


class TestValidateComponentsWithAliases:
    """Verify validate_components resolves aliases before validation."""

    def test_toggle_no_longer_warned_when_icon_exists(self):
        templates = {"icon": [{"variant": "icon/switch"}], "text": [{"variant": "default"}], "container": [{"variant": "default"}]}
        components, warnings = validate_components(
            [{"type": "toggle"}], templates,
        )
        toggle_warnings = [w for w in warnings if "toggle" in w.lower()]
        assert not any("no template" in w.lower() for w in toggle_warnings)

    def test_truly_unsupported_type_still_warns(self):
        templates = {"button": [{"variant": "default"}]}
        components, warnings = validate_components(
            [{"type": "slider"}], templates,
        )
        assert any("slider" in w for w in warnings)
