"""Tests for Gemini 2.5 Flash vision classifier — side-channel to the
Anthropic PS/CS passes. Mirrors classify_crops_batch contract.
"""

from __future__ import annotations

import json

import pytest

from dd.classify_vision_gemini import (
    build_gemini_crops_prompt,
    build_response_schema,
    classify_crops_gemini,
)


def _png_stub(tag: str = "png") -> bytes:
    return f"{tag}-bytes".encode("utf-8")


def _candidate(screen_id: int, node_id: int, **overrides) -> dict:
    base = {
        "screen_id": screen_id,
        "node_id": node_id,
        "name": "Primary CTA",
        "node_type": "INSTANCE",
        "total_children": 1,
        "child_type_dist": {"TEXT": 1},
        "sample_text": "Continue",
        "parent_classified_as": "container",
    }
    base.update(overrides)
    return base


class _FakeCall:
    """Injected call_fn that records args and returns a canned payload."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self.payload


def _gemini_response(classifications: list[dict]) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [
                {"text": json.dumps({"classifications": classifications})}
            ]}}
        ]
    }


def test_empty_candidates_returns_empty():
    result = classify_crops_gemini(
        [], {}, api_key="stub", call_fn=_FakeCall(_gemini_response([])),
    )
    assert result == []


def test_candidates_with_no_matching_crops_returns_empty():
    candidate = _candidate(1, 10)
    call = _FakeCall(_gemini_response([]))
    result = classify_crops_gemini(
        [candidate], {}, api_key="stub", call_fn=call,
    )
    assert result == []
    # No API call should be made when nothing has a crop.
    assert call.calls == []


def test_valid_response_parsed_into_classification_dicts():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([
        {"screen_id": 1, "node_id": 10,
         "canonical_type": "button", "confidence": 0.92,
         "reason": "pill shape, primary fill, label 'Continue'"},
    ]))
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert len(result) == 1
    assert result[0]["screen_id"] == 1
    assert result[0]["node_id"] == 10
    assert result[0]["canonical_type"] == "button"
    assert result[0]["confidence"] == 0.92
    assert "pill" in result[0]["reason"]


def test_malformed_json_returns_empty():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall({
        "candidates": [{"content": {"parts": [{"text": "not json {["}]}}]
    })
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert result == []


def test_missing_candidates_block_returns_empty():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall({"candidates": []})
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert result == []


def test_prompt_contains_catalog_and_node_descriptors():
    candidate = _candidate(1, 10, name="Login button")
    crops = {(1, 10): _png_stub()}
    catalog = [
        {"canonical_name": "button", "category": "interactive",
         "behavioral_description": "Interactive tappable control"},
        {"canonical_name": "heading", "category": "text",
         "behavioral_description": "Large prominent label"},
    ]
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", catalog=catalog, call_fn=call,
    )
    assert len(call.calls) == 1
    prompt = call.calls[0]["prompt"]
    assert "button" in prompt
    assert "heading" in prompt
    assert "Login button" in prompt
    assert "node_id=10" in prompt


def test_images_sent_in_candidate_order():
    cand_a = _candidate(1, 10)
    cand_b = _candidate(1, 20)
    cand_c = _candidate(2, 30)
    crops = {
        (1, 10): _png_stub("a"),
        (1, 20): _png_stub("b"),
        (2, 30): _png_stub("c"),
    }
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [cand_a, cand_b, cand_c], crops, api_key="stub", call_fn=call,
    )
    images = call.calls[0]["images"]
    assert images == [_png_stub("a"), _png_stub("b"), _png_stub("c")]


def test_candidates_without_crops_are_filtered_before_call():
    cand_a = _candidate(1, 10)
    cand_b = _candidate(1, 20)
    crops = {(1, 10): _png_stub("a")}  # only a has a crop
    call = _FakeCall(_gemini_response([
        {"screen_id": 1, "node_id": 10, "canonical_type": "button",
         "confidence": 0.9, "reason": "pill shape"},
    ]))
    result = classify_crops_gemini(
        [cand_a, cand_b], crops, api_key="stub", call_fn=call,
    )
    assert len(call.calls[0]["images"]) == 1
    assert len(result) == 1
    assert result[0]["node_id"] == 10


def test_default_model_is_flash():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert call.calls[0]["model"] == "gemini-2.5-flash"


def test_model_override_passed_through():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", model="gemini-2.5-pro",
        call_fn=call,
    )
    assert call.calls[0]["model"] == "gemini-2.5-pro"


def test_build_gemini_crops_prompt_orders_nodes_same_as_input():
    cand_a = _candidate(1, 10, name="Alpha")
    cand_b = _candidate(1, 20, name="Bravo")
    prompt = build_gemini_crops_prompt([cand_a, cand_b], catalog=[])
    alpha_pos = prompt.index("Alpha")
    bravo_pos = prompt.index("Bravo")
    assert alpha_pos < bravo_pos


def test_code_fenced_json_still_parses():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    fenced = (
        "```json\n"
        + json.dumps({"classifications": [
            {"screen_id": 1, "node_id": 10,
             "canonical_type": "button", "confidence": 0.88,
             "reason": "pill shape"}
        ]})
        + "\n```"
    )
    call = _FakeCall({
        "candidates": [{"content": {"parts": [{"text": fenced}]}}]
    })
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert len(result) == 1
    assert result[0]["canonical_type"] == "button"


# ---------------------------------------------------------------------------
# v2 tests: escape hatch, few-shot, response schema, v2 prompt rules
# ---------------------------------------------------------------------------


def test_new_type_verdict_preserves_new_type_label():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([
        {"screen_id": 1, "node_id": 10,
         "canonical_type": "new_type",
         "new_type_label": "segmented_control",
         "confidence": 0.9,
         "reason": "two mutually-exclusive pills in a rounded container"},
    ]))
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert len(result) == 1
    assert result[0]["canonical_type"] == "new_type"
    assert result[0]["new_type_label"] == "segmented_control"


def test_new_type_label_omitted_when_canonical_type_is_catalog():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([
        {"screen_id": 1, "node_id": 10,
         "canonical_type": "button",
         "new_type_label": None,
         "confidence": 0.95,
         "reason": "pill with 'Continue' label"},
    ]))
    result = classify_crops_gemini(
        [candidate], crops, api_key="stub", call_fn=call,
    )
    assert "new_type_label" not in result[0]


def test_few_shot_block_appears_in_prompt():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    few_shot = (
        "## Examples from human review on this project\n"
        "- name=\"Submit\" parent=container → reviewer classified as "
        "**`button`** (reviewed)."
    )
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub",
        few_shot_block=few_shot, call_fn=call,
    )
    prompt = call.calls[0]["prompt"]
    assert "Examples from human review" in prompt
    assert "reviewed" in prompt


def test_prompt_includes_layout_slot_rule():
    prompt = build_gemini_crops_prompt([_candidate(1, 10)], catalog=[])
    assert "Layout-slot" in prompt or "layout wrappers" in prompt.lower()


def test_prompt_includes_wordmark_rule():
    prompt = build_gemini_crops_prompt([_candidate(1, 10)], catalog=[])
    assert "wordmark" in prompt.lower()
    assert "image" in prompt.lower()


def test_prompt_includes_skeleton_rule_with_example():
    prompt = build_gemini_crops_prompt([_candidate(1, 10)], catalog=[])
    assert "skeleton" in prompt.lower()
    # Strengthened rule should name at least one placeholder frame.
    assert "Frame 352" in prompt or "Skeleton" in prompt


def test_prompt_includes_escape_hatch_instructions():
    prompt = build_gemini_crops_prompt([_candidate(1, 10)], catalog=[])
    assert "new_type" in prompt
    assert "new_type_label" in prompt


def test_build_response_schema_constrains_canonical_type_to_enum():
    catalog = [
        {"canonical_name": "button", "category": "interactive",
         "behavioral_description": "tap"},
        {"canonical_name": "heading", "category": "text",
         "behavioral_description": "label"},
    ]
    schema = build_response_schema(catalog)
    enum = schema["properties"]["classifications"]["items"][
        "properties"]["canonical_type"]["enum"]
    assert "button" in enum
    assert "heading" in enum
    assert "unsure" in enum
    assert "new_type" in enum


def test_response_schema_passed_to_call_fn_when_catalog_present():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    catalog = [
        {"canonical_name": "button", "category": "interactive",
         "behavioral_description": "tap"},
    ]
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", catalog=catalog, call_fn=call,
    )
    assert "response_schema" in call.calls[0]
    enum = call.calls[0]["response_schema"]["properties"][
        "classifications"]["items"]["properties"][
            "canonical_type"]["enum"]
    assert "button" in enum
    assert "new_type" in enum


def test_response_schema_suppressed_when_catalog_empty():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", catalog=[], call_fn=call,
    )
    assert "response_schema" not in call.calls[0]


def test_response_schema_disabled_when_flag_off():
    candidate = _candidate(1, 10)
    crops = {(1, 10): _png_stub()}
    catalog = [
        {"canonical_name": "button", "category": "interactive",
         "behavioral_description": "tap"},
    ]
    call = _FakeCall(_gemini_response([]))
    classify_crops_gemini(
        [candidate], crops, api_key="stub", catalog=catalog,
        use_response_schema=False, call_fn=call,
    )
    assert "response_schema" not in call.calls[0]
