"""Visual-sanity gate — auto-inspect rendered output before human rating.

Catches the failure mode diagnosed on 2026-04-16: structural parity reports
12/12 success but the output is categorically empty (212/229 non-screen
nodes at Figma's 100×100 ``createFrame()`` default). The gate sits between
the structural verifier (ADR-007) and human rating: a render that fails
visual inspection never reaches a designer.

Two inspectors compose:

- :func:`inspect_walk` — pure, rule-based. Reads ``walk.json``. No I/O.
  Counts default-sized frames and visibly-empty content nodes.
- :func:`inspect_screenshot` — VLM-based. Takes a PNG and calls Gemini
  3.1 Pro (or any injected ``call_fn``) with a minimal rubric.

A :class:`SanityReport` aggregates per-prompt verdicts and exposes a
``gate_passes`` property that fails when more than half the prompts are
categorically broken.

The default VLM backend is Gemini 3.1 Pro via the public generative-
language endpoint; the dependency is stdlib only (``urllib.request``).
See ``feedback_auto_inspect_before_human_rate.md`` for the process rule
this enforces.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

Verdict = Literal["broken", "partial", "ok", "unknown"]

DEFAULT_FRAME_W = 100
DEFAULT_FRAME_H = 100

BROKEN_DEFAULT_FRAME_RATIO = 0.7
BROKEN_VISIBLE_RATIO = 0.3
OK_DEFAULT_FRAME_RATIO = 0.1
OK_VISIBLE_RATIO = 0.8

SEVERITY = {"broken": 0, "partial": 1, "ok": 2}

VLM_PROMPT = (
    "You are inspecting a rendered UI screenshot for visual plausibility. "
    "Ignore aesthetic quality — only judge whether the screen contains "
    "interpretable UI structure.\n\n"
    "Score 1-10 using this rubric:\n"
    "  1-3 (broken): mostly empty grey frames, a few stray labels, no UI structure.\n"
    "  4-6 (partial): some UI visible but missing major elements or malformed.\n"
    "  7-10 (ok): coherent screen a designer would recognise as a plausible starting point.\n\n"
    'Respond with JSON only: {"score": <1-10>, "verdict": "broken"|"partial"|"ok", "reason": "<one sentence>"}'
)


@dataclass(frozen=True)
class RuleBasedScore:
    """Rule-based visual-sanity score from walk.json."""

    total_content_nodes: int
    total_text_nodes: int
    default_sized_frame_nodes: int
    visible_text_nodes: int
    frames_with_visible_content: int
    default_frame_ratio: float
    visible_ratio: float
    verdict: Verdict
    had_render_errors: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_content_nodes": self.total_content_nodes,
            "total_text_nodes": self.total_text_nodes,
            "default_sized_frame_nodes": self.default_sized_frame_nodes,
            "visible_text_nodes": self.visible_text_nodes,
            "frames_with_visible_content": self.frames_with_visible_content,
            "default_frame_ratio": round(self.default_frame_ratio, 4),
            "visible_ratio": round(self.visible_ratio, 4),
            "verdict": self.verdict,
            "had_render_errors": self.had_render_errors,
        }


@dataclass(frozen=True)
class VlmScore:
    """VLM verdict on a rendered screenshot."""

    score: int
    verdict: Verdict
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "verdict": self.verdict, "reason": self.reason}


@dataclass(frozen=True)
class SanityReport:
    """Aggregate sanity verdict across many rendered prompts."""

    per_prompt: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.per_prompt)

    @property
    def broken(self) -> int:
        return sum(1 for e in self.per_prompt.values() if e.get("verdict") == "broken")

    @property
    def partial(self) -> int:
        return sum(1 for e in self.per_prompt.values() if e.get("verdict") == "partial")

    @property
    def ok(self) -> int:
        return sum(1 for e in self.per_prompt.values() if e.get("verdict") == "ok")

    @property
    def gate_passes(self) -> bool:
        """Gate passes when the majority of prompts are not broken.

        Spec: ">50% broken → gate fails". Exactly 50% passes.
        """
        if self.total == 0:
            return True
        return (self.broken * 2) <= self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "broken": self.broken,
            "partial": self.partial,
            "ok": self.ok,
            "gate_passes": self.gate_passes,
            "per_prompt": self.per_prompt,
        }


# ---------------------------------------------------------------------------
# Rule-based inspection
# ---------------------------------------------------------------------------


def _is_text(node: dict[str, Any]) -> bool:
    return node.get("type") == "TEXT"


def _is_screen_root(eid: str) -> bool:
    return eid.startswith("screen-")


def _has_characters(node: dict[str, Any]) -> bool:
    chars = node.get("characters")
    return isinstance(chars, str) and len(chars.strip()) > 0


def _has_visible_paint(node: dict[str, Any]) -> bool:
    """A node is visibly painted if it has fills, strokes, or effects."""
    if node.get("fills"):
        return True
    if node.get("strokes"):
        return True
    if node.get("effectCount", 0) > 0:
        return True
    if node.get("effects"):
        return True
    return False


def _is_default_sized(node: dict[str, Any]) -> bool:
    return (
        node.get("width") == DEFAULT_FRAME_W
        and node.get("height") == DEFAULT_FRAME_H
    )


def _classify(
    default_frame_ratio: float,
    visible_ratio: float,
    total_nodes: int,
    had_errors: bool,
) -> Verdict:
    if had_errors:
        return "broken"
    if total_nodes == 0:
        return "broken"
    if default_frame_ratio >= BROKEN_DEFAULT_FRAME_RATIO:
        return "broken"
    if visible_ratio < BROKEN_VISIBLE_RATIO:
        return "broken"
    if (
        default_frame_ratio <= OK_DEFAULT_FRAME_RATIO
        and visible_ratio >= OK_VISIBLE_RATIO
    ):
        return "ok"
    return "partial"


def inspect_walk(walk: dict[str, Any]) -> RuleBasedScore:
    """Rule-based inspection of a ``walk.json`` payload.

    Ignores the screen root (tagged ``screen-*``) because its default
    fill/size is always present — we only care about its descendants.
    """
    eid_map = walk.get("eid_map") or {}
    had_errors = bool(walk.get("errors"))

    total_content = 0
    total_text = 0
    default_sized = 0
    visible_text = 0
    frames_with_content = 0

    for eid, node in eid_map.items():
        if _is_screen_root(eid):
            continue
        if _is_text(node):
            total_text += 1
            if _has_characters(node):
                visible_text += 1
            continue
        total_content += 1
        if _is_default_sized(node):
            default_sized += 1
        if _has_visible_paint(node):
            frames_with_content += 1

    total_nodes = total_content + total_text
    default_frame_ratio = (
        default_sized / total_content if total_content > 0 else 0.0
    )
    visible_ratio = (
        (visible_text + frames_with_content) / total_nodes
        if total_nodes > 0
        else 0.0
    )

    verdict = _classify(default_frame_ratio, visible_ratio, total_nodes, had_errors)

    return RuleBasedScore(
        total_content_nodes=total_content,
        total_text_nodes=total_text,
        default_sized_frame_nodes=default_sized,
        visible_text_nodes=visible_text,
        frames_with_visible_content=frames_with_content,
        default_frame_ratio=default_frame_ratio,
        visible_ratio=visible_ratio,
        verdict=verdict,
        had_render_errors=had_errors,
    )


# ---------------------------------------------------------------------------
# VLM inspection — Gemini 3.1 Pro (or any Gemini-shaped callable)
# ---------------------------------------------------------------------------


GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.1-pro-preview:generateContent"
)


def _default_gemini_call(
    prompt: str,
    png_bytes: bytes,
    api_key: str,
    *,
    endpoint: str = GEMINI_ENDPOINT,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Default Gemini call using stdlib urllib.

    Injected ``call_fn`` signatures take (prompt, png_bytes); the API key
    is bound at ``inspect_screenshot`` call time via a partial.
    """
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(png_bytes).decode("ascii"),
                    },
                },
            ],
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }
    url = f"{endpoint}?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_text(raw: dict[str, Any]) -> str:
    return raw["candidates"][0]["content"]["parts"][0]["text"]


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _parse_vlm_response(raw: dict[str, Any]) -> VlmScore:
    try:
        text = _strip_code_fence(_extract_text(raw))
        data = json.loads(text)
        score = int(data["score"])
        verdict = data.get("verdict", "unknown")
        if verdict not in {"broken", "partial", "ok"}:
            verdict = "unknown"
        reason = str(data.get("reason", ""))[:500]
        return VlmScore(score=score, verdict=verdict, reason=reason)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, IndexError):
        return VlmScore(score=0, verdict="unknown", reason="Could not parse VLM response")


CallFn = Callable[[str, bytes], dict[str, Any]]


def inspect_screenshot(
    png_path: Path,
    *,
    api_key: str,
    call_fn: CallFn | None = None,
) -> VlmScore:
    """VLM-based inspection of a rendered screenshot.

    ``call_fn`` is injectable for tests; in production it defaults to a
    Gemini 3.1 Pro call. On any network or parse failure the verdict is
    ``unknown`` rather than propagating the exception — an unknown VLM
    verdict gets ignored when combined with the rule-based verdict.
    """
    if not png_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {png_path}")
    png_bytes = png_path.read_bytes()

    try:
        if call_fn is None:
            raw = _default_gemini_call(VLM_PROMPT, png_bytes, api_key)
        else:
            raw = call_fn(VLM_PROMPT, png_bytes)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as e:
        return VlmScore(score=0, verdict="unknown", reason=f"VLM API error: {e}")

    return _parse_vlm_response(raw)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def _combine_verdicts(rule_v: Verdict, vlm_v: Verdict | None) -> Verdict:
    """Pick the more pessimistic verdict when both are known.

    An ``unknown`` VLM verdict is treated as absent: we trust rule-based.
    """
    if vlm_v is None or vlm_v == "unknown":
        return rule_v
    if rule_v == "unknown":
        return vlm_v
    return rule_v if SEVERITY[rule_v] <= SEVERITY[vlm_v] else vlm_v


def compile_sanity_report(
    experiment_dir: Path,
    *,
    use_vlm: bool = False,
    api_key: str | None = None,
    call_fn: CallFn | None = None,
) -> SanityReport:
    """Walk ``<experiment_dir>/artefacts/*/walk.json`` and score each prompt.

    ``use_vlm`` enables the Gemini pass. If ``api_key`` is ``None`` the
    VLM pass is silently skipped — useful when the environment lacks a
    Google key but the rule-based gate is still meaningful.
    """
    artefacts = experiment_dir / "artefacts"
    per_prompt: dict[str, dict[str, Any]] = {}

    if not artefacts.is_dir():
        return SanityReport(per_prompt=per_prompt)

    for slug_dir in sorted(p for p in artefacts.iterdir() if p.is_dir()):
        walk_path = slug_dir / "walk.json"
        if not walk_path.exists():
            continue
        try:
            walk = json.loads(walk_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        rule = inspect_walk(walk)
        entry: dict[str, Any] = {
            "rule": rule.to_dict(),
            "verdict": rule.verdict,
            "vlm": None,
        }

        if use_vlm and api_key:
            screenshot = slug_dir / "screenshot.png"
            if screenshot.exists():
                vlm = inspect_screenshot(screenshot, api_key=api_key, call_fn=call_fn)
                entry["vlm"] = vlm.to_dict()
                entry["verdict"] = _combine_verdicts(rule.verdict, vlm.verdict)

        per_prompt[slug_dir.name] = entry

    return SanityReport(per_prompt=per_prompt)


def write_report(report: SanityReport, experiment_dir: Path) -> Path:
    """Write ``sanity_report.json`` into the experiment directory."""
    out = experiment_dir / "sanity_report.json"
    out.write_text(json.dumps(report.to_dict(), indent=2))
    return out


def render_memo_fragment(report: SanityReport, experiment_dir: Path) -> str:
    """Produce a short Markdown fragment summarising the gate result."""
    lines: list[str] = []
    lines.append(f"# Sanity gate — {experiment_dir.name}")
    lines.append("")
    verdict = "PASSES" if report.gate_passes else "FAILS"
    lines.append(
        f"**Gate {verdict}** — {report.broken} broken / {report.partial} "
        f"partial / {report.ok} ok (of {report.total})."
    )
    lines.append("")
    if not report.gate_passes:
        lines.append(
            "> More than half the prompts render as categorically empty. "
            "Do not produce a human-rating template until the pipeline "
            "regresses this rate below 50%."
        )
        lines.append("")
    lines.append("| slug | verdict | default_frame_ratio | visible_ratio | vlm |")
    lines.append("|---|---|---|---|---|")
    for slug in sorted(report.per_prompt):
        e = report.per_prompt[slug]
        rule = e.get("rule") or {}
        vlm = e.get("vlm")
        vlm_cell = f"{vlm['verdict']} ({vlm['score']})" if vlm else "—"
        lines.append(
            f"| {slug} | {e['verdict']} | "
            f"{rule.get('default_frame_ratio', 0):.2f} | "
            f"{rule.get('visible_ratio', 0):.2f} | {vlm_cell} |"
        )
    return "\n".join(lines) + "\n"
