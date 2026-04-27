"""Sprint 2 C9 — A1.1 descendant-path override routing.

Per docs/plan-sprint-2-station-parity.md §8 row 6 (orthogonal Figma-extract
bug, prerequisite for the text-content graduation): the IR's
``_build_overrides_sidecar`` filtered ``if target != ":self": continue``,
which dropped descendant-path override rows like ``;157:1425`` from the
side-car. The result: a TEXT override on an instance descendant rendered
as the master default ("Send to Client") instead of the override value
("Reject") — the user-observed HGB button bug.

C9 closes this by adding a two-pass IR build in
``build_composition_spec``:
  Pass 1: walk all nodes, build descendant_routings keyed by the
          DESCENDANT's figma_node_id.
  Pass 2: merge routed figma_names into each descendant's
          ``element["_overrides"]`` side-car.

The renderer + verifier code paths don't change — they keep reading
``element["_overrides"]`` per node.

Codex 5.5 round-8 locked option (i) two-pass + (β) strict id construction
helper that handles nested instance heads correctly.

C10 will then wire registry-driven dispatch so the verifier compares
``characters`` etc. on these descendants. Until C10, the rail is in
place but the comparator doesn't fire.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------
# C9 — _expected_descendant_id helper
# ---------------------------------------------------------------------


class TestExpectedDescendantId:
    """Per Codex round-8 option (β): construct the expected descendant
    figma_node_id from the instance head's id + the override target
    path. Strict construction (not suffix matching) keeps nested
    instances unambiguous."""

    def test_top_level_instance_text_child(self):
        """Standard case: head ``512:28223`` with override target
        ``;157:1425`` → descendant ``I512:28223;157:1425``."""
        from dd.ir import _expected_descendant_id

        assert _expected_descendant_id("512:28223", ";157:1425") == "I512:28223;157:1425"

    def test_top_level_instance_nested_target(self):
        """Multi-segment target (e.g. icon's stroke):
        head ``512:28223``, target ``;157:1424;64:299`` →
        ``I512:28223;157:1424;64:299``."""
        from dd.ir import _expected_descendant_id

        assert _expected_descendant_id("512:28223", ";157:1424;64:299") == \
            "I512:28223;157:1424;64:299"

    def test_nested_instance_head(self):
        """Nested instance: head's figma_node_id ALREADY starts with I
        (e.g. ``I512:28223;157:1424``). Helper must not double-prefix
        with II — must return ``I512:28223;157:1424;64:299``."""
        from dd.ir import _expected_descendant_id

        # Head id is itself an instance descendant (nested instance scenario)
        nested_head = "I512:28223;157:1424"
        target = ";64:299"
        result = _expected_descendant_id(nested_head, target)
        # Must be I-prefixed once, not I-prefixed twice
        assert not result.startswith("II")
        assert result == "I512:28223;157:1424;64:299"


# ---------------------------------------------------------------------
# C9 — build_descendant_routings function
# ---------------------------------------------------------------------


class TestBuildDescendantRoutings:
    """Pass 1 of the C9 two-pass: scan all nodes, build a map from
    descendant figma_node_id → set of figma_names that should land
    on that descendant's _overrides side-car."""

    def _make_node(self, figma_id, canonical_type="instance",
                   instance_overrides=None):
        return {
            "figma_node_id": figma_id,
            "canonical_type": canonical_type,
            "instance_overrides": instance_overrides or [],
        }

    def test_self_targets_are_excluded(self):
        """Pass 1 should NOT include :self overrides — those are
        handled by the existing _build_overrides_sidecar path."""
        from dd.ir import build_descendant_routings

        head = self._make_node(
            "512:28223",
            instance_overrides=[
                {"target": ":self", "property": "FILLS", "value": "[...]"},
            ],
        )
        routings = build_descendant_routings([head])
        assert routings == {}

    def test_text_override_routes_to_text_child(self):
        """The HGB button bug: TEXT override on descendant ``;157:1425``
        should produce a routing entry for ``I512:28223;157:1425``
        with figma_name ``characters``."""
        from dd.ir import build_descendant_routings

        head = self._make_node(
            "512:28223",
            instance_overrides=[
                {"target": ":self", "property": "FILLS", "value": "[...]"},
                {"target": ";157:1425", "property": "TEXT", "value": "Reject"},
            ],
        )
        routings = build_descendant_routings([head])
        assert "I512:28223;157:1425" in routings
        assert routings["I512:28223;157:1425"] == {"characters"}

    def test_multi_segment_target_routes_correctly(self):
        """Multi-segment target ``;157:1424;64:299`` (icon's stroke)
        routes to ``I512:28223;157:1424;64:299``."""
        from dd.ir import build_descendant_routings

        head = self._make_node(
            "512:28223",
            instance_overrides=[
                {"target": ";157:1424;64:299", "property": "STROKES",
                 "value": "[...]"},
            ],
        )
        routings = build_descendant_routings([head])
        assert "I512:28223;157:1424;64:299" in routings
        assert routings["I512:28223;157:1424;64:299"] == {"strokes"}

    def test_multiple_overrides_on_same_descendant(self):
        """A descendant can have multiple property overrides; the
        routing collects ALL of them as a set."""
        from dd.ir import build_descendant_routings

        head = self._make_node(
            "512:28223",
            instance_overrides=[
                {"target": ";157:1425", "property": "TEXT", "value": "Reject"},
                {"target": ";157:1425", "property": "FILLS",
                 "value": "[...]"},
            ],
        )
        routings = build_descendant_routings([head])
        assert routings["I512:28223;157:1425"] == {"characters", "fills"}

    def test_unmapped_property_dropped(self):
        """Override property types not in _INSTANCE_OVERRIDE_TO_FIGMA_NAME
        (e.g. INSTANCE_SWAP, BOOLEAN) are silently dropped per the
        existing fail-open convention."""
        from dd.ir import build_descendant_routings

        head = self._make_node(
            "512:28223",
            instance_overrides=[
                {"target": ";157:1425", "property": "BOOLEAN", "value": "true"},
                {"target": ";157:1425", "property": "INSTANCE_SWAP",
                 "value": "X"},
                {"target": ";157:1425", "property": "TEXT",
                 "value": "Reject"},
            ],
        )
        routings = build_descendant_routings([head])
        # Only TEXT (→ characters) routed; BOOLEAN + INSTANCE_SWAP dropped
        assert routings["I512:28223;157:1425"] == {"characters"}

    def test_non_instance_nodes_skipped(self):
        """Only instance heads can have descendant overrides — non-
        instance nodes are skipped even if they happen to have an
        instance_overrides field."""
        from dd.ir import build_descendant_routings

        non_instance = self._make_node(
            "999:999",
            canonical_type="frame",
            instance_overrides=[
                {"target": ";157:1425", "property": "TEXT", "value": "X"},
            ],
        )
        routings = build_descendant_routings([non_instance])
        assert routings == {}

    def test_empty_instance_overrides_safe(self):
        """No instance_overrides field, or empty list, yields no routings."""
        from dd.ir import build_descendant_routings

        nodes = [
            self._make_node("1:1", instance_overrides=None),
            self._make_node("2:2", instance_overrides=[]),
            {"figma_node_id": "3:3", "canonical_type": "instance"},  # missing field
        ]
        routings = build_descendant_routings(nodes)
        assert routings == {}

    def test_nested_instance_head_routings(self):
        """A nested instance head (figma_node_id already I-prefixed)
        routes its descendant overrides correctly without
        double-I-prefixing."""
        from dd.ir import build_descendant_routings

        nested_head = self._make_node(
            "I512:28223;157:1424",  # nested instance inside another instance
            instance_overrides=[
                {"target": ";64:299", "property": "STROKES",
                 "value": "[...]"},
            ],
        )
        routings = build_descendant_routings([nested_head])
        # Result should have single I prefix
        assert "I512:28223;157:1424;64:299" in routings
        # Defensive: no II-prefix bug
        assert not any(k.startswith("II") for k in routings)


# ---------------------------------------------------------------------
# C9 — build_composition_spec integration
# ---------------------------------------------------------------------


class TestBuildCompositionSpecRoutesDescendantOverrides:
    """End-to-end: build_composition_spec applies the routings during
    its node walk, so descendant elements get _overrides side-cars
    populated from the ancestor instance's instance_overrides rows.
    """

    def _make_data(self, screen_id=1, root_node_id=100):
        return {
            "screen_id": screen_id,
            "root_node_id": root_node_id,
            "screen_name": "test",
            "screen_type": "app_screen",
            "nodes": [],
            "tokens": {},
        }

    def test_descendant_text_node_gets_characters_override(self):
        """The HGB button bug fix end-to-end: an instance head with
        a descendant TEXT override produces an IR where the text
        descendant element has ``_overrides`` containing ``characters``."""
        from dd.ir import build_composition_spec

        data = self._make_data()
        # Two nodes: an instance head + its text descendant
        # Per dd/ir.py:_resolve_element_type, canonical_type='instance'
        # gives element_type='instance'; canonical_type='text' gives 'text'.
        data["nodes"] = [
            {
                "node_id": 100,
                "parent_id": None,
                "figma_node_id": "512:28223",
                "canonical_type": "instance",
                "name": "buttons/button outlined with icon",
                "node_type": "INSTANCE",
                "depth": 0,
                "sort_order": 0,
                "instance_overrides": [
                    {"target": ":self", "property": "FILLS",
                     "value": "[...]"},
                    {"target": ";157:1425", "property": "TEXT",
                     "value": "Reject"},
                ],
                "bindings": [],
            },
            {
                "node_id": 200,
                "parent_id": 100,
                "figma_node_id": "I512:28223;157:1425",
                "canonical_type": "text",
                "name": "Send to Client",
                "node_type": "TEXT",
                "depth": 1,
                "sort_order": 0,
                "text_content": "Reject",
                "bindings": [],
            },
        ]

        spec = build_composition_spec(data)
        elements = spec.get("elements", {})

        # Find the text element by node_id
        text_element = None
        for el in elements.values():
            # The text descendant should be the only "text" type element
            if el.get("type") == "text":
                text_element = el
                break

        assert text_element is not None, (
            "expected a text element in IR; got "
            f"{[(eid, el.get('type')) for eid, el in elements.items()]}"
        )
        # The graduation: characters is now in _overrides on the
        # text descendant
        assert "_overrides" in text_element
        assert "characters" in text_element["_overrides"]

    def test_descendant_with_no_overrides_unchanged(self):
        """A descendant of an instance head that has NO override row
        targeting it gets no _overrides side-car (no false positive)."""
        from dd.ir import build_composition_spec

        data = self._make_data()
        data["nodes"] = [
            {
                "node_id": 100,
                "parent_id": None,
                "figma_node_id": "512:28223",
                "canonical_type": "instance",
                "name": "btn",
                "node_type": "INSTANCE",
                "depth": 0,
                "sort_order": 0,
                "instance_overrides": [],  # no overrides at all
                "bindings": [],
            },
            {
                "node_id": 200,
                "parent_id": 100,
                "figma_node_id": "I512:28223;157:1425",
                "canonical_type": "text",
                "name": "label",
                "node_type": "TEXT",
                "depth": 1,
                "sort_order": 0,
                "text_content": "ok",
                "bindings": [],
            },
        ]
        spec = build_composition_spec(data)
        elements = spec.get("elements", {})

        text_element = next(
            (el for el in elements.values() if el.get("type") == "text"),
            None,
        )
        assert text_element is not None
        # No _overrides because no override row targets this text node
        assert "_overrides" not in text_element

    def test_self_overrides_still_land_on_head(self):
        """Regression check: the existing :self path still works.
        An instance head's :self override (FILLS) lands in the head's
        own _overrides, not redirected anywhere."""
        from dd.ir import build_composition_spec

        data = self._make_data()
        data["nodes"] = [
            {
                "node_id": 100,
                "parent_id": None,
                "figma_node_id": "512:28223",
                "canonical_type": "instance",
                "name": "btn",
                "node_type": "INSTANCE",
                "depth": 0,
                "sort_order": 0,
                "instance_overrides": [
                    {"target": ":self", "property": "FILLS",
                     "value": "[...]"},
                ],
                "bindings": [],
            },
        ]
        spec = build_composition_spec(data)
        elements = spec.get("elements", {})

        instance_element = next(
            (el for el in elements.values()
             if el.get("type") == "instance"),
            None,
        )
        assert instance_element is not None
        assert "_overrides" in instance_element
        assert "fills" in instance_element["_overrides"]
