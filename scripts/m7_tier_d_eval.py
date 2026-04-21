"""Tier D — scale composition gated by the Tier C scorer.

Per docs/plan-burndown.md §Tier D: each existing composition
demo runs through the Tier C scorer + produces a FidelityReport.
The goal is not to BUILD new composition infra (S4.3 archetype
pipeline is already wired in prompt_parser.py); it's to VERIFY
composition output meets the ≥7/10 bar across scales and to
catalogue what still needs work for the catalog / scoring /
Mode-3 pipeline.

Runs 3 representative prompts across scales:
  D.2 subtree   — "add a simple confirmation toast"  (S4.2)
  D.3 screen    — "a login screen with email/password/button" (S4.3, archetype-matched)
  D.4 synthesis — "a 3D voxel cube visualizer page"  (S4.4, no archetype)

For each: compose → render → walk → score → report.

Usage::

    .venv/bin/python3 -m scripts.m7_tier_d_eval \\
        --db Dank-EXP-02.declarative.db \\
        [--skip-bridge]  # score only the structural dims
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


_PROMPTS = {
    "subtree": "A confirmation toast with a short message and a dismiss icon.",
    "screen_archetype": (
        "A login screen with an email input, a password input, a "
        "primary sign-in button, and a secondary 'Forgot password' "
        "link below."
    ),
    "screen_synthesis": (
        "A 3D voxel cube visualizer page with rotation controls, a "
        "color palette sidebar, and an export button."
    ),
}


@dataclass
class TierDResult:
    scope: str
    prompt: str
    compose_sec: float = 0.0
    walk_sec: float = 0.0
    score_ten: float = 0.0
    passed: bool = False
    dimensions: list[dict] = field(default_factory=list)
    bridge_ok: bool = False
    notes: str = ""


def run_one(
    scope: str, prompt: str, *, conn, client, use_bridge: bool,
) -> TierDResult:
    from dd.compose import generate_from_prompt
    from dd.prompt_parser import parse_prompt
    from dd.fidelity_score import score_fidelity

    result = TierDResult(scope=scope, prompt=prompt)

    # 1. Parse + compose
    t0 = time.monotonic()
    try:
        components = parse_prompt(prompt, client)
    except Exception as e:
        result.notes = f"parse_prompt failed: {e}"
        return result
    if isinstance(components, dict) and "_clarification_refusal" in components:
        result.notes = (
            f"LLM refusal: {components['_clarification_refusal'][:100]}"
        )
        return result
    if not components:
        result.notes = "empty component list"
        return result
    compose = generate_from_prompt(conn, components)
    result.compose_sec = time.monotonic() - t0
    spec = compose["spec"]
    script = compose["structure_script"]
    ir_elements = spec.get("elements") or {}

    # 2. Walk via bridge (optional) or structural-only
    walk_eid_map: dict = {}
    walk_errors: list = []
    if use_bridge:
        from dd.apply_render import BridgeError, walk_rendered_via_bridge
        t0 = time.monotonic()
        try:
            payload = walk_rendered_via_bridge(
                script=script, ws_port=9228, timeout=180.0,
            )
            walk_eid_map = payload.get("eid_map") or {}
            walk_errors = list(payload.get("errors") or [])
            result.bridge_ok = bool(payload.get("__ok"))
        except BridgeError as e:
            result.notes = f"bridge failed: {e}"[:150]
        result.walk_sec = time.monotonic() - t0

    # 3. Score
    report = score_fidelity(
        ir_elements=ir_elements,
        walk_eid_map=walk_eid_map,
        walk_errors=walk_errors,
    )
    result.score_ten = report.to_ten(mode="min")
    result.passed = report.to_ten() >= 7.0
    result.dimensions = [
        {
            "name": d.name,
            "value": round(d.value, 2),
            "passed": d.passed,
            "diagnostic": d.diagnostic[:140],
        }
        for d in report.dimensions
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--skip-bridge", action="store_true",
        help="Score on structural dims only (skip bridge walk).",
    )
    parser.add_argument(
        "--save-report", default=None,
        help="Write results JSON to this path.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    import anthropic
    from dd.db import get_connection

    client = anthropic.Anthropic()
    conn = get_connection(args.db)

    use_bridge = not args.skip_bridge
    results: list[TierDResult] = []
    try:
        for scope, prompt in _PROMPTS.items():
            print(f"\n=== {scope} ===")
            print(f"Prompt: {prompt}")
            r = run_one(
                scope, prompt, conn=conn, client=client,
                use_bridge=use_bridge,
            )
            results.append(r)
            print(
                f"  compose={r.compose_sec:.2f}s "
                f"walk={r.walk_sec:.2f}s "
                f"score={r.score_ten:.1f}/10 "
                f"passed={r.passed} "
                f"bridge_ok={r.bridge_ok}"
            )
            for d in r.dimensions:
                marker = "✓" if d["passed"] else "✗"
                print(
                    f"  {marker} {d['name']:30s} {d['value']:.2f} "
                    f"— {d['diagnostic']}"
                )
            if r.notes:
                print(f"  NOTE: {r.notes}")
    finally:
        conn.close()

    # Summary
    print("\n" + "=" * 60)
    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    print(
        f"Tier D eval: {passed_count}/{total} scored ≥7/10 "
        f"(bridge: {'ON' if use_bridge else 'OFF'})"
    )
    for r in results:
        print(
            f"  {r.scope:20s} score={r.score_ten:.1f}/10 "
            f"passed={r.passed}"
        )

    if args.save_report:
        payload = [
            {
                "scope": r.scope, "prompt": r.prompt,
                "compose_sec": round(r.compose_sec, 3),
                "walk_sec": round(r.walk_sec, 3),
                "score_ten": r.score_ten,
                "passed": r.passed,
                "bridge_ok": r.bridge_ok,
                "dimensions": r.dimensions,
                "notes": r.notes,
            }
            for r in results
        ]
        Path(args.save_report).write_text(
            json.dumps(payload, indent=2)
        )
        print(f"\nSaved report to {args.save_report}")

    return 0 if passed_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
