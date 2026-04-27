"""Seed `Dank-Test-v0.4` Figma file with the components and screens the
v0.4 demos depend on. Idempotent — running twice is safe.

Status: SKELETON (W0.C Day 1).
    Days 2-4 of W0.C will fill in the actual Figma writes (PROXY_EXECUTE
    JS payloads to create the file, page, components, and seed screens).
    For now this module documents the seeding plan and `--print-plan`
    surfaces it as JSON for review.

Provenance / sibling file:
    Source corpus: file_key drxXOUOdYEBBQ09mrXJeYu (Dank Experimental).
    Test fixture:  Dank-Test-v0.4 (same team, NEW file, single page
                   `Test/v0.4`).

The corpus only carries `size` and `style` axes for buttons (no
`state` axis was recorded), so the seeding plan reflects that. Per
`tests/.fixtures/demo_screen_audit.json`, the four anchors needed are:
  - Demo A: button/large/translucent  (CKR 689e60bd...)
  - Demo B: any node bound to color.border.tertiary on screen 333
  - Demo C: Battery Icon GROUP on screen 118
  - Demo D: button/toolbar FRAME on screen 311 + appended
            button/small/translucent (CKR 74a7396e...)
            (Anchor moved 243 -> 311 mid-Phase 0 to escape the
            iPad-translucent-cluster drift set per
            feedback_ipad_component_frame_inlining.md.)

Usage:
    python3 tools/dd-test-fixture-create.py --print-plan
    python3 tools/dd-test-fixture-create.py --bridge-port 9228   # NOOP today
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


# Subset of the source corpus needed for the four demo smoke fixtures.
# Component keys (CKRs) are 40-char hex strings produced by Figma's
# component_key registry; matched against component_key_registry in the
# source DB.
SEEDING_PLAN: dict[str, list[dict[str, Any]]] = {
    "components": [
        {
            "name": "button/large/translucent",
            "ckr": "689e60bd3db9ef304a9304eb585566a888a18237",
            "variant_axes": {"size": "large", "style": "translucent"},
            "used_by": ["demo_a"],
            "corpus_instance_count": 3891,
        },
        {
            "name": "button/small/translucent",
            "ckr": "74a7396ef95439c83d69e125077ecd6afcde1fb4",
            "variant_axes": {"size": "small", "style": "translucent"},
            "used_by": ["demo_d"],
            "corpus_instance_count": 2604,
        },
        {
            "name": "button/small/solid",
            "ckr": "19938af1e04e52479d070fa2faa926da4d66eb9f",
            "variant_axes": {"size": "small", "style": "solid"},
            "used_by": ["demo_d_variant_axis_smoke"],
            "corpus_instance_count": 837,
        },
        # Most-used icons on screen 333.
        {"name": "icon/back",   "ckr": "e5b52e4647bd0d968f22a0ce2c09cd14cf2af3ac", "variant_axes": {}, "used_by": ["demo_a", "demo_b"], "corpus_instance_count": 3808},
        {"name": "icon/wallet", "ckr": "e7ceb36e2404d52c18768fc9b53fec8a07419c65", "variant_axes": {}, "used_by": ["demo_a"], "corpus_instance_count": 837},
        {"name": "icon/delete", "ckr": "5decf04810fcb9d8494f7d41858574031763196a", "variant_axes": {}, "used_by": ["demo_a"], "corpus_instance_count": 685},
    ],
    "screens": [
        {"src_screen_id": 333, "src_name": 'iPad Pro 11" - 43',  "device_class": "ipad_11", "used_by": ["demo_a", "demo_b"]},
        {"src_screen_id": 118, "src_name": 'iPad Pro 12.9" - 7', "device_class": "ipad_13", "used_by": ["demo_c"]},
        {"src_screen_id": 311, "src_name": 'iPad Pro 12.9" - 25', "device_class": "ipad_13", "used_by": ["demo_d"]},
    ],
    "tokens": [
        # Auto-clustered names (role + lightness rank). Demo briefs reference these.
        {"name": "color.border.tertiary", "value": "#047AFF", "used_by": ["demo_b"]},
        {"name": "color.border.primary",  "value": "#FFFFFF", "used_by": ["demo_c"]},
        {"name": "radius.11", "value": "10", "used_by": ["demo_a"]},
        {"name": "radius.12", "value": "12", "used_by": ["demo_a"]},
        {"name": "space.10",  "value": "10", "used_by": ["demo_a"]},
        {"name": "space.13",  "value": "14", "used_by": ["demo_a"]},
    ],
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--print-plan", action="store_true", help="Print SEEDING_PLAN as JSON and exit (no Figma writes).")
    p.add_argument("--bridge-port", type=int, default=9228, help="figma-console-mcp bridge port (unused in skeleton).")
    args = p.parse_args(argv)

    if args.print_plan:
        json.dump(SEEDING_PLAN, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print("[skeleton] dd-test-fixture-create: NO-OP today.", file=sys.stderr)
    print(f"[skeleton]   bridge_port={args.bridge_port} (wired but unused)", file=sys.stderr)
    print(f"[skeleton]   plan covers {len(SEEDING_PLAN['components'])} components, "
          f"{len(SEEDING_PLAN['screens'])} screens, {len(SEEDING_PLAN['tokens'])} tokens", file=sys.stderr)
    print("[skeleton] Days 2-4 of W0.C will implement Figma writes via PROXY_EXECUTE.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
