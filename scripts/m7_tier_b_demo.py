"""Tier B — smallest Mode-3 demo.

Per plan-burndown.md §Tier B: smallest possible Mode-3 synthesis,
end-to-end, no scorer (Tier C builds that after observing what
actually breaks here). Prompt → Mode-3 compose → render → inspect.

Alexander's scale-agnostic-entry: component scale is the cheapest
test of the mechanism. Prompts here are deliberately single-
component ("a primary CTA button") so the output fits in one IR
element whose correctness is inspectable manually.

Usage::

    .venv/bin/python3 -m scripts.m7_tier_b_demo \\
        --db Dank-EXP-02.declarative.db \\
        --prompt "a primary CTA button labeled 'Sign up'" \\
        [--save-script /tmp/tier_b.js]
        [--save-walk /tmp/tier_b_walk.json]

The walk JSON (when bridge is available) + the saved script let
you inspect what Mode-3 produced + what the renderer emitted,
without relying on a live bridge succeeding.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _inspect_spec(spec: dict, target_eid: str | None = None) -> dict:
    """Count populated visual/layout fields across elements.

    Tier-B observation primitive: which elements get their template
    styles merged, and which silently drop them. Counts populated
    `style.fill`, `style.stroke`, `style.radius`, `style.shadow`,
    `layout.padding`, `layout.gap`. Same shape as the H1-verification
    probe — deliberately so Tier C's scorer has the baseline data.
    """
    elements = spec.get("elements") or {}
    out = {
        "total": 0, "fill": 0, "stroke": 0, "radius": 0,
        "shadow": 0, "padding": 0, "gap": 0, "any_style": 0,
        "per_eid": {},
    }
    for eid, elem in elements.items():
        if elem.get("type") in ("screen",):
            continue
        out["total"] += 1
        style = elem.get("style") or {}
        layout = elem.get("layout") or {}
        has_any = False
        ent = {}
        if style.get("fill"):
            out["fill"] += 1; ent["fill"] = style["fill"]; has_any = True
        if style.get("stroke"):
            out["stroke"] += 1; ent["stroke"] = style["stroke"]; has_any = True
        if style.get("radius"):
            out["radius"] += 1; ent["radius"] = style["radius"]; has_any = True
        if style.get("shadow"):
            out["shadow"] += 1; ent["shadow"] = style["shadow"]; has_any = True
        if layout.get("padding"):
            out["padding"] += 1; ent["padding"] = "set"; has_any = True
        if layout.get("gap"):
            out["gap"] += 1; ent["gap"] = "set"; has_any = True
        if has_any:
            out["any_style"] += 1
            out["per_eid"][eid] = {
                "type": elem.get("type"),
                **ent,
            }
    return out


def run_demo(
    db_path: str,
    *,
    prompt: str,
    save_script: str | None,
    save_walk: str | None,
    ws_port: int,
) -> int:
    from dd.compose import generate_from_prompt
    from dd.db import get_connection
    from dd.prompt_parser import parse_prompt

    conn = get_connection(db_path)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1
    import anthropic
    client = anthropic.Anthropic()

    print(f"Prompt: {prompt!r}")

    # 1. Parse the prompt → component list
    components = parse_prompt(prompt, client)
    if isinstance(components, dict) and "_clarification_refusal" in components:
        print(
            f"LLM refused / asked for clarification: "
            f"{components['_clarification_refusal']}",
            file=sys.stderr,
        )
        conn.close()
        return 1
    if not components:
        print("LLM returned empty component list.", file=sys.stderr)
        conn.close()
        return 1
    print(f"\nLLM components ({len(components)}):")
    print(json.dumps(components, indent=2)[:1500])

    # 2. Mode-3 compose → render
    result = generate_from_prompt(conn, components)
    script = result["structure_script"]
    spec = result["spec"]

    if save_script:
        Path(save_script).write_text(script)
        print(f"\nSaved render script to {save_script}")

    # 3. Inspect the IR: what visuals propagated?
    inspection = _inspect_spec(spec)
    print(f"\n### IR visual inventory (non-screen elements)")
    print(
        f"total={inspection['total']} "
        f"any_style={inspection['any_style']} "
        f"fill={inspection['fill']} "
        f"stroke={inspection['stroke']} "
        f"radius={inspection['radius']} "
        f"shadow={inspection['shadow']} "
        f"padding={inspection['padding']} "
        f"gap={inspection['gap']}"
    )
    print("\nPer-element detail:")
    for eid, ent in inspection["per_eid"].items():
        print(f"  {eid}: {ent}")

    # 4. Plugin bridge walk (optional, if bridge responsive).
    if save_walk:
        from dd.apply_render import BridgeError, walk_rendered_via_bridge
        try:
            rendered_ref = walk_rendered_via_bridge(
                script=script,
                ws_port=ws_port,
                timeout=300.0,
                keep_artifacts=False,
            )
            Path(save_walk).write_text(
                json.dumps(rendered_ref, indent=2)
            )
            print(f"\nBridge walk: {save_walk}")
            eid_ct = len(rendered_ref.get("eid_map", {}))
            err_ct = len(rendered_ref.get("errors", []))
            print(f"  rendered eids={eid_ct} errors={err_ct}")
        except BridgeError as e:
            print(
                f"\nBridge unavailable (skipping walk): {e}",
                file=sys.stderr,
            )

    print("\nTier B smoke complete.")
    print(
        "Inspect the IR inventory + saved script + walk (if any) "
        "to catalogue failure modes for `docs/learnings-tier-b-"
        "failure-modes.md`."
    )
    conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--prompt", required=True,
        help=(
            "Natural-language component-scale prompt. "
            "Example: 'a primary CTA button labeled Sign up'."
        ),
    )
    parser.add_argument("--save-script", default=None)
    parser.add_argument("--save-walk", default=None)
    parser.add_argument("--ws-port", type=int, default=9228)
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    return run_demo(
        args.db,
        prompt=args.prompt,
        save_script=args.save_script,
        save_walk=args.save_walk,
        ws_port=args.ws_port,
    )


if __name__ == "__main__":
    sys.exit(main())
