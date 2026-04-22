"""Tier C.3 — Alexander's force-resolution guard.

Principle (plan-synthetic-gen §1.2, item 2): "the same CARD
pattern applied to a product listing and to a user profile
should produce different results because the forces are
different."

Test: compose the SAME component type ("button") under TWO
different prompt contexts — a destructive confirmation (forces:
irreversible, risky, needs attention) vs a primary CTA (forces:
wanted, friendly, call-to-action). The generated IRs MUST differ
on at least one visual property (ideally variant, failing that
fill/radius/content).

If they produce IDENTICAL concrete output, the mechanism is
Gang-of-Four lookup pretending to be generative — Alexander's
explicit failure mode.

Usage::

    .venv/bin/python3 -m scripts.force_resolution_test \\
        --db Dank-EXP-02.declarative.db

Exit 0 on pass, 1 on force-resolution failure.

Costs ~$0.02 in Claude Haiku calls (2 parse_prompt invocations).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


_PROMPT_DESTRUCTIVE = (
    "A confirmation button for DELETING a user's account. "
    "Clicking this is irreversible and permanently removes all "
    "their data. Label it 'Delete account'."
)

_PROMPT_PRIMARY_CTA = (
    "A sign-up button on a marketing landing page. This is the "
    "primary call-to-action inviting new users to join. Label it "
    "'Start free trial'."
)


def _inspect_button(components: list) -> dict:
    """Drill into a component list and extract the first
    button's (variant, text, any style hints) as the fingerprint
    we compare across prompts."""
    def find(items):
        for c in items:
            if c.get("type") == "button":
                return c
            kids = c.get("children") or []
            if kids:
                r = find(kids)
                if r is not None:
                    return r
        return None

    btn = find(components)
    if btn is None:
        return {"_no_button": True}
    return {
        "type": btn.get("type"),
        "variant": btn.get("variant"),
        "text": (btn.get("props") or {}).get("text"),
    }


def _inspect_ir(spec: dict) -> dict:
    """From the composed spec, find the button element and
    surface its style token refs. These are what the template
    propagation supplies via `_apply_template_to_parent` — if
    force-resolution picks a different variant, the tokens
    differ."""
    elements = spec.get("elements") or {}
    for eid, elem in elements.items():
        if elem.get("type") == "button":
            style = elem.get("style") or {}
            return {
                "eid": eid,
                "fill": style.get("fill"),
                "fg": style.get("fg"),
                "radius": style.get("radius"),
            }
    return {"_no_button_in_ir": True}


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    import anthropic
    from dd.compose import generate_from_prompt
    from dd.db import get_connection
    from dd.prompt_parser import parse_prompt

    client = anthropic.Anthropic()
    conn = get_connection(args.db)
    try:
        print("=== Force-resolution test (Tier C.3) ===\n")
        print(f"PROMPT A — destructive:\n  {_PROMPT_DESTRUCTIVE}\n")
        a_components = parse_prompt(_PROMPT_DESTRUCTIVE, client)
        if isinstance(a_components, dict) and "_clarification_refusal" in a_components:
            print(f"A: refusal — {a_components}", file=sys.stderr)
            return 1
        a_button = _inspect_button(a_components)
        print(f"  LLM button: {a_button}")

        result_a = generate_from_prompt(conn, a_components)
        a_ir = _inspect_ir(result_a["spec"])
        print(f"  IR button style: {a_ir}\n")

        print(f"PROMPT B — primary CTA:\n  {_PROMPT_PRIMARY_CTA}\n")
        b_components = parse_prompt(_PROMPT_PRIMARY_CTA, client)
        if isinstance(b_components, dict) and "_clarification_refusal" in b_components:
            print(f"B: refusal — {b_components}", file=sys.stderr)
            return 1
        b_button = _inspect_button(b_components)
        print(f"  LLM button: {b_button}")

        result_b = generate_from_prompt(conn, b_components)
        b_ir = _inspect_ir(result_b["spec"])
        print(f"  IR button style: {b_ir}\n")

        print("=== Verdict ===")
        # Alexander's force-resolution guard: it's not enough that
        # the LLM *varies* — the variation must be in the RIGHT
        # DIRECTION. A delete-confirmation should pick from the
        # destructive / danger variant family; a CTA should pick
        # primary. If the LLM picks secondary for both prompts,
        # they "differ" versus each other but neither matches the
        # semantic context — that's Gang-of-Four lookup with jitter.
        #
        # Expected-bucket table: maps semantic context to a set of
        # acceptable variant names. When a prompt's variant isn't
        # in its bucket, it's a contextual miss even if the two
        # prompts differ.
        expected_buckets = {
            "destructive": {"destructive", "danger", "warning"},
            "primary_cta": {"primary"},
        }

        a_variant = (a_button.get("variant") or "").lower()
        b_variant = (b_button.get("variant") or "").lower()
        a_in_bucket = a_variant in expected_buckets["destructive"]
        b_in_bucket = b_variant in expected_buckets["primary_cta"]
        variant_differs = a_variant != b_variant
        fill_differs = a_ir.get("fill") != b_ir.get("fill")
        text_differs = a_button.get("text") != b_button.get("text")

        print(f"  A variant={a_variant!r} in destructive bucket? {a_in_bucket}")
        print(f"  B variant={b_variant!r} in primary_cta bucket? {b_in_bucket}")
        print(f"  variant differs: {variant_differs}")
        print(f"  fill differs:    {fill_differs} "
              f"(A={a_ir.get('fill')!r} vs B={b_ir.get('fill')!r})")
        print(f"  text differs:    {text_differs}")

        # Two gates:
        #   - strict: both variants land in their expected buckets
        #   - relaxed: variants differ AND fills differ (old behavior,
        #     confirms the mechanism isn't fully degenerate)
        strict_pass = a_in_bucket and b_in_bucket
        relaxed_pass = variant_differs and fill_differs

        if strict_pass:
            print(
                "\nPASS (strict): each variant landed in its "
                "expected contextual bucket. Force-resolution is "
                "semantically sharp."
            )
            return 0
        if relaxed_pass:
            print(
                "\nPARTIAL (relaxed): the mechanism varies along "
                "multiple axes (variant + fill) but at least one "
                "prompt missed its expected bucket. The LLM is "
                "force-sensitive but the catalog may lack the right "
                "variant (e.g., no `destructive` variant) or the "
                "system prompt isn't steering toward it.\n"
                "Flag for Tier D: extend catalog with missing "
                "variants AND/OR add semantic guidance to the "
                "composition system prompt."
            )
            return 0
        if variant_differs or text_differs or fill_differs:
            print(
                "\nFAIL: concrete varies BUT neither prompt lands "
                "in its expected bucket AND the visual differentiation "
                "is weak. Mechanism responds to prompt but not to "
                "force-resolution.",
                file=sys.stderr,
            )
            return 1
        print(
            "\nFAIL: same donor + different forces → IDENTICAL "
            "concrete. Alexander's Gang-of-Four trap.",
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
