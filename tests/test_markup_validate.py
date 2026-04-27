"""dd markup — validation (Mode E structural; Mode S/R stubs).

Per `docs/decisions/v0.3-grammar-modes.md`:
  - Mode E (Extract): structural soundness only; raw values permitted
  - Mode S (Synthesis): token-only on clusterable axes (stub until
    ADR-001 capability sync)
  - Mode R (Render): backend-capability-gated (stub)
"""

from __future__ import annotations

import pytest

from dd.markup import validate


class TestModeE:
    def test_valid_minimal_spec(self) -> None:
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {"type": "screen"},
            },
            "tokens": {},
            "_node_id_map": {},
        }
        assert validate(spec, mode="E") == []

    def test_missing_version_flagged(self) -> None:
        spec = {"root": "", "elements": {}}
        errors = validate(spec, mode="E")
        kinds = [e["kind"] for e in errors]
        assert "missing_top_level" in kinds

    def test_missing_root_flagged(self) -> None:
        spec = {"version": "1.0", "elements": {}}
        errors = validate(spec, mode="E")
        assert any(
            e["kind"] == "missing_top_level" and e["path"] == "root"
            for e in errors
        )

    def test_missing_elements_flagged(self) -> None:
        spec = {"version": "1.0", "root": ""}
        errors = validate(spec, mode="E")
        assert any(
            e["kind"] == "missing_top_level" and e["path"] == "elements"
            for e in errors
        )

    def test_root_not_in_elements_flagged(self) -> None:
        spec = {
            "version": "1.0",
            "root": "ghost",
            "elements": {"real": {"type": "frame"}},
        }
        errors = validate(spec, mode="E")
        assert any(e["kind"] == "root_not_in_elements" for e in errors)

    def test_element_missing_type_flagged(self) -> None:
        spec = {
            "version": "1.0",
            "root": "e",
            "elements": {"e": {"children": []}},
        }
        errors = validate(spec, mode="E")
        assert any(e["kind"] == "element_missing_type" for e in errors)

    def test_child_eid_unknown_flagged(self) -> None:
        spec = {
            "version": "1.0",
            "root": "parent",
            "elements": {
                "parent": {"type": "frame", "children": ["missing"]},
            },
        }
        errors = validate(spec, mode="E")
        assert any(e["kind"] == "child_eid_unknown" for e in errors)

    def test_valid_nested_spec_no_errors(self) -> None:
        spec = {
            "version": "1.0",
            "root": "root-1",
            "elements": {
                "root-1": {"type": "screen", "children": ["child-1"]},
                "child-1": {"type": "frame", "children": ["child-2"]},
                "child-2": {"type": "rect"},
            },
        }
        assert validate(spec, mode="E") == []


class TestModeSStub:
    def test_mode_s_emits_stub_warning(self) -> None:
        spec = {
            "version": "1.0",
            "root": "e",
            "elements": {"e": {"type": "frame"}},
        }
        errors = validate(spec, mode="S")
        assert any(e["kind"] == "validator_stub" for e in errors)

    def test_mode_r_emits_stub_warning(self) -> None:
        spec = {
            "version": "1.0",
            "root": "e",
            "elements": {"e": {"type": "frame"}},
        }
        errors = validate(spec, mode="R")
        assert any(e["kind"] == "validator_stub" for e in errors)


class TestInvalidMode:
    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown validation mode"):
            validate({}, mode="Q")
