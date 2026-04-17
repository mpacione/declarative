"""Tests for the visual-sanity gate (auto-inspect before human rating).

The gate catches the failure mode diagnosed on 2026-04-16: structural
parity says "12/12 ok" but the output is categorically empty — 212 of
229 non-screen nodes at Figma's ``createFrame()`` default 100×100, almost
no visible content. A rule-based + optional VLM inspector produces a
``SanityReport`` that blocks human-rating escalation when more than half
the outputs are categorically broken.

Two inspectors compose:

- ``inspect_walk`` — pure function over ``walk.json`` dict. No I/O.
- ``inspect_screenshot`` — takes a screenshot PNG path and a VLM
  ``call_fn`` (injected for testability). Gemini 3.1 Pro in production.

Both produce a verdict in {``broken``, ``partial``, ``ok``}.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixtures — walk.json shapes drawn from the v3 artefacts and from a
# hypothetical healthy render.
# ---------------------------------------------------------------------------


def _walk_v3_like() -> dict[str, Any]:
    """Shape of a walk.json from Wave 1.5 v3 — text labels + default frames.

    Modelled on experiments/00c-vanilla-v3/artefacts/01-login/walk.json:
    one screen, 3 TEXT nodes with characters, 5 FRAME nodes at 100×100
    with no fills/strokes/effects.
    """
    return {
        "__ok": True,
        "errors": [],
        "rendered_root": "5756:662879",
        "eid_map": {
            "screen-1": {
                "type": "FRAME", "name": "screen-1",
                "width": 428, "height": 926,
                "fills": [{"type": "solid", "color": "#F6F6F6"}],
                "effectCount": 0,
            },
            "text-1": {
                "type": "TEXT", "name": "text-1",
                "width": 179, "height": 15,
                "characters": "Don't have an account? Sign up",
                "fills": [{"type": "solid", "color": "#000000"}],
                "effectCount": 0,
            },
            "link-1": {
                "type": "TEXT", "name": "link-1",
                "width": 102, "height": 15,
                "characters": "Forgot password?",
                "fills": [{"type": "solid", "color": "#000000"}],
                "effectCount": 0,
            },
            "heading-1": {
                "type": "TEXT", "name": "heading-1",
                "width": 39, "height": 22,
                "characters": "Sign In",
                "fills": [{"type": "solid", "color": "#000000"}],
                "effectCount": 0,
            },
            "card-1": {
                "type": "FRAME", "name": "card-1",
                "width": 100, "height": 300,
                "effectCount": 0,
            },
            "button-1": {
                "type": "FRAME", "name": "button-1",
                "width": 100, "height": 100,
                "effectCount": 0,
            },
            "text_input-1": {
                "type": "FRAME", "name": "text_input-1",
                "width": 100, "height": 100,
                "effectCount": 0,
            },
            "text_input-2": {
                "type": "FRAME", "name": "text_input-2",
                "width": 100, "height": 100,
                "effectCount": 0,
            },
        },
    }


def _walk_healthy() -> dict[str, Any]:
    """A render where most frames carry visible content.

    Proper sizes (not 100×100), fills/strokes/effects present, and
    text nodes with characters.
    """
    return {
        "__ok": True,
        "errors": [],
        "rendered_root": "root",
        "eid_map": {
            "screen-1": {
                "type": "FRAME", "name": "screen-1",
                "width": 428, "height": 926,
                "fills": [{"type": "solid", "color": "#FFFFFF"}],
                "effectCount": 0,
            },
            "header-1": {
                "type": "FRAME", "name": "header-1",
                "width": 428, "height": 64,
                "fills": [{"type": "solid", "color": "#F6F6F6"}],
                "effectCount": 0,
            },
            "heading-1": {
                "type": "TEXT", "name": "heading-1",
                "width": 180, "height": 28,
                "characters": "Welcome back",
                "fills": [{"type": "solid", "color": "#000000"}],
                "effectCount": 0,
            },
            "text_input-1": {
                "type": "FRAME", "name": "text_input-1",
                "width": 396, "height": 48,
                "fills": [{"type": "solid", "color": "#FFFFFF"}],
                "strokes": [{"type": "solid", "color": "#E1E1E1"}],
                "effectCount": 0,
            },
            "text_input-2": {
                "type": "FRAME", "name": "text_input-2",
                "width": 396, "height": 48,
                "fills": [{"type": "solid", "color": "#FFFFFF"}],
                "strokes": [{"type": "solid", "color": "#E1E1E1"}],
                "effectCount": 0,
            },
            "button-1": {
                "type": "FRAME", "name": "button-1",
                "width": 396, "height": 52,
                "fills": [{"type": "solid", "color": "#1E90FF"}],
                "effectCount": 0,
            },
            "link-1": {
                "type": "TEXT", "name": "link-1",
                "width": 120, "height": 16,
                "characters": "Forgot password?",
                "fills": [{"type": "solid", "color": "#1E90FF"}],
                "effectCount": 0,
            },
        },
    }


def _walk_partial() -> dict[str, Any]:
    """Halfway render — some visible content, some default frames."""
    return {
        "__ok": True,
        "errors": [],
        "rendered_root": "root",
        "eid_map": {
            "screen-1": {
                "type": "FRAME", "name": "screen-1",
                "width": 428, "height": 926,
                "fills": [{"type": "solid", "color": "#FFFFFF"}],
                "effectCount": 0,
            },
            "heading-1": {
                "type": "TEXT", "name": "heading-1",
                "width": 180, "height": 28,
                "characters": "Welcome back",
                "fills": [{"type": "solid", "color": "#000000"}],
                "effectCount": 0,
            },
            "text_input-1": {
                "type": "FRAME", "name": "text_input-1",
                "width": 396, "height": 48,
                "fills": [{"type": "solid", "color": "#FFFFFF"}],
                "effectCount": 0,
            },
            "button-1": {
                "type": "FRAME", "name": "button-1",
                "width": 100, "height": 100,
                "effectCount": 0,
            },
            "card-1": {
                "type": "FRAME", "name": "card-1",
                "width": 100, "height": 100,
                "effectCount": 0,
            },
        },
    }


# ---------------------------------------------------------------------------
# inspect_walk — rule-based gate
# ---------------------------------------------------------------------------


class TestInspectWalkCounts:
    """Verify the tally fields computed over a walk.json."""

    def test_counts_non_screen_non_text_nodes(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_v3_like())
        assert score.total_content_nodes == 4  # card, button, text_input x 2

    def test_counts_default_sized_frames(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_v3_like())
        assert score.default_sized_frame_nodes == 3  # card is 100x300 so not default

    def test_counts_visible_text_nodes(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_v3_like())
        assert score.visible_text_nodes == 3

    def test_counts_frames_with_visible_content(self):
        """Healthy walk has most frames carrying fills/strokes."""
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_healthy())
        # header, text_input x 2, button all have fills/strokes
        assert score.frames_with_visible_content >= 4


class TestInspectWalkVerdict:
    """Verdicts — broken / partial / ok."""

    def test_v3_like_is_broken(self):
        """Rule-based gate must label the v3 baseline as broken."""
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_v3_like())
        assert score.verdict == "broken"

    def test_healthy_is_ok(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_healthy())
        assert score.verdict == "ok"

    def test_partial_is_partial(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_partial())
        assert score.verdict == "partial"

    def test_empty_walk_is_broken(self):
        """A walk with just a screen root is broken."""
        from dd.visual_inspect import inspect_walk
        empty = {
            "__ok": True, "errors": [], "rendered_root": "root",
            "eid_map": {"screen-1": {"type": "FRAME", "width": 428, "height": 926}},
        }
        score = inspect_walk(empty)
        assert score.verdict == "broken"

    def test_walk_with_render_errors_is_broken(self):
        """Even if some content renders, a walk that reports __errors is broken."""
        from dd.visual_inspect import inspect_walk
        errored = _walk_healthy()
        errored["errors"] = [{"kind": "render_thrown", "id": "button-1"}]
        score = inspect_walk(errored)
        assert score.verdict == "broken"


class TestInspectWalkRatios:
    """Ratio metrics are in [0, 1] and monotonic with structure quality."""

    def test_ratios_are_between_zero_and_one(self):
        from dd.visual_inspect import inspect_walk
        for walk in (_walk_v3_like(), _walk_healthy(), _walk_partial()):
            score = inspect_walk(walk)
            assert 0.0 <= score.default_frame_ratio <= 1.0
            assert 0.0 <= score.visible_ratio <= 1.0

    def test_v3_has_high_default_ratio(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_v3_like())
        assert score.default_frame_ratio >= 0.5

    def test_healthy_has_low_default_ratio(self):
        from dd.visual_inspect import inspect_walk
        score = inspect_walk(_walk_healthy())
        assert score.default_frame_ratio == 0.0


# ---------------------------------------------------------------------------
# inspect_screenshot — VLM gate (mocked call_fn)
# ---------------------------------------------------------------------------


def _fake_call_ok(prompt: str, png_bytes: bytes) -> dict[str, Any]:
    """Gemini-shaped response claiming interpretable UI."""
    return {
        "candidates": [{
            "content": {"parts": [{
                "text": json.dumps({
                    "score": 8, "verdict": "ok",
                    "reason": "Clear login screen with inputs and CTA",
                }),
            }]},
        }],
    }


def _fake_call_broken(prompt: str, png_bytes: bytes) -> dict[str, Any]:
    return {
        "candidates": [{
            "content": {"parts": [{
                "text": json.dumps({
                    "score": 2, "verdict": "broken",
                    "reason": "Mostly empty grey frames with a few stray labels",
                }),
            }]},
        }],
    }


def _fake_call_malformed(prompt: str, png_bytes: bytes) -> dict[str, Any]:
    """Model returned free-text instead of JSON."""
    return {
        "candidates": [{
            "content": {"parts": [{"text": "Sure, here's my assessment..."}]},
        }],
    }


def _fake_call_error(prompt: str, png_bytes: bytes) -> dict[str, Any]:
    raise RuntimeError("API down")


@pytest.fixture
def tiny_png(tmp_path: Path) -> Path:
    """1×1 PNG so inspect_screenshot has a real file to open."""
    # 67-byte minimal PNG (1x1 transparent).
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c636000010000050001a5f645400000000049454e44"
        "ae426082"
    )
    p = tmp_path / "pic.png"
    p.write_bytes(png_bytes)
    return p


class TestInspectScreenshot:
    def test_interpretable_ui_returns_ok(self, tiny_png: Path):
        from dd.visual_inspect import inspect_screenshot
        result = inspect_screenshot(tiny_png, api_key="k", call_fn=_fake_call_ok)
        assert result.verdict == "ok"
        assert result.score == 8

    def test_broken_returns_broken(self, tiny_png: Path):
        from dd.visual_inspect import inspect_screenshot
        result = inspect_screenshot(tiny_png, api_key="k", call_fn=_fake_call_broken)
        assert result.verdict == "broken"
        assert result.score <= 3

    def test_malformed_response_degrades_to_unknown(self, tiny_png: Path):
        """Free-text response → verdict=unknown, not a crash."""
        from dd.visual_inspect import inspect_screenshot
        result = inspect_screenshot(tiny_png, api_key="k", call_fn=_fake_call_malformed)
        assert result.verdict == "unknown"

    def test_network_error_surfaces_as_unknown(self, tiny_png: Path):
        from dd.visual_inspect import inspect_screenshot
        result = inspect_screenshot(tiny_png, api_key="k", call_fn=_fake_call_error)
        assert result.verdict == "unknown"
        assert "error" in result.reason.lower() or "api" in result.reason.lower()

    def test_missing_file_raises(self, tmp_path: Path):
        from dd.visual_inspect import inspect_screenshot
        with pytest.raises(FileNotFoundError):
            inspect_screenshot(tmp_path / "nope.png", api_key="k", call_fn=_fake_call_ok)


# ---------------------------------------------------------------------------
# SanityReport — aggregator + gate verdict
# ---------------------------------------------------------------------------


class TestSanityReportGate:
    """>50% broken means gate fails. Exactly 50% passes."""

    def test_gate_passes_when_all_ok(self):
        from dd.visual_inspect import SanityReport
        report = SanityReport(
            per_prompt={f"p{i}": {"verdict": "ok"} for i in range(12)},
        )
        assert report.gate_passes is True
        assert report.broken == 0
        assert report.ok == 12

    def test_gate_fails_when_majority_broken(self):
        from dd.visual_inspect import SanityReport
        per_prompt = {f"p{i}": {"verdict": "broken"} for i in range(7)}
        per_prompt.update({f"p{i}": {"verdict": "ok"} for i in range(7, 12)})
        report = SanityReport(per_prompt=per_prompt)
        assert report.gate_passes is False
        assert report.broken == 7

    def test_gate_passes_at_exactly_50_percent(self):
        """Spec: '>50% fail' means gate fails. 50% exactly → passes."""
        from dd.visual_inspect import SanityReport
        per_prompt = {f"b{i}": {"verdict": "broken"} for i in range(6)}
        per_prompt.update({f"o{i}": {"verdict": "ok"} for i in range(6)})
        report = SanityReport(per_prompt=per_prompt)
        assert report.gate_passes is True

    def test_partial_does_not_count_as_broken(self):
        from dd.visual_inspect import SanityReport
        per_prompt = {f"p{i}": {"verdict": "partial"} for i in range(12)}
        report = SanityReport(per_prompt=per_prompt)
        assert report.gate_passes is True
        assert report.partial == 12
        assert report.broken == 0

    def test_empty_report_passes_vacuously(self):
        from dd.visual_inspect import SanityReport
        report = SanityReport(per_prompt={})
        assert report.gate_passes is True
        assert report.total == 0


# ---------------------------------------------------------------------------
# compile_sanity_report — end-to-end walk over an experiment directory
# ---------------------------------------------------------------------------


def _write_prompt_artefacts(
    root: Path,
    slug: str,
    walk: dict[str, Any],
    with_screenshot: bool = False,
) -> None:
    """Mirror the layout produced by run_walks_and_finalize.py."""
    d = root / "artefacts" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "walk.json").write_text(json.dumps(walk))
    if with_screenshot:
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c636000010000050001a5f645400000000049454e44"
            "ae426082"
        )
        (d / "screenshot.png").write_bytes(png_bytes)


class TestCompileSanityReport:
    def test_reads_all_prompt_dirs(self, tmp_path: Path):
        from dd.visual_inspect import compile_sanity_report
        _write_prompt_artefacts(tmp_path, "01-one", _walk_v3_like())
        _write_prompt_artefacts(tmp_path, "02-two", _walk_healthy())
        _write_prompt_artefacts(tmp_path, "03-three", _walk_partial())
        report = compile_sanity_report(tmp_path)
        assert report.total == 3
        verdicts = {s: e["verdict"] for s, e in report.per_prompt.items()}
        assert verdicts["01-one"] == "broken"
        assert verdicts["02-two"] == "ok"
        assert verdicts["03-three"] == "partial"

    def test_v3_style_directory_gates_fail(self, tmp_path: Path):
        """12 v3-like prompts → gate fails, matching the 2026-04-16 diagnosis."""
        from dd.visual_inspect import compile_sanity_report
        for i in range(12):
            _write_prompt_artefacts(tmp_path, f"{i:02d}-x", _walk_v3_like())
        report = compile_sanity_report(tmp_path)
        assert report.gate_passes is False
        assert report.broken == 12

    def test_ignores_directories_without_walk_json(self, tmp_path: Path):
        from dd.visual_inspect import compile_sanity_report
        (tmp_path / "artefacts" / "bogus").mkdir(parents=True)
        _write_prompt_artefacts(tmp_path, "01-real", _walk_healthy())
        report = compile_sanity_report(tmp_path)
        assert report.total == 1

    def test_vlm_is_skipped_when_api_key_missing(self, tmp_path: Path):
        """Without an API key the VLM pass is silently skipped — rule-only."""
        from dd.visual_inspect import compile_sanity_report
        _write_prompt_artefacts(tmp_path, "01-x", _walk_v3_like(), with_screenshot=True)
        report = compile_sanity_report(tmp_path, use_vlm=True, api_key=None)
        entry = report.per_prompt["01-x"]
        assert entry["verdict"] == "broken"  # still decided by rule-based
        assert entry.get("vlm") is None

    def test_vlm_opinion_escalates_ok_to_broken_when_rule_disagrees(
        self, tmp_path: Path,
    ):
        """If rule says ok but VLM says broken, the combined verdict is broken.

        Keeps the gate conservative: if either inspector thinks the
        output is categorically broken, we don't escalate to rating.
        """
        from dd.visual_inspect import compile_sanity_report
        _write_prompt_artefacts(tmp_path, "01-x", _walk_healthy(), with_screenshot=True)
        report = compile_sanity_report(
            tmp_path,
            use_vlm=True,
            api_key="k",
            call_fn=_fake_call_broken,
        )
        entry = report.per_prompt["01-x"]
        assert entry["verdict"] == "broken"
        assert entry["vlm"]["verdict"] == "broken"
