"""Exp 00g-mode3-v4 — archetype-library-live parse + compose pass.

v0.1.5 Week 1 Step 5 (partial). Runs each of the 12 canonical prompts
through Haiku parse + compose with the ADR-008 v0.1.5 archetype
classifier + SYSTEM_PROMPT injection LIVE, then measures structural
density per prompt.

Does NOT render or walk — that requires the Figma bridge on port
9231. Run ``run_experiment.py`` (same pattern as 00f) once the bridge
is connected to produce the full pipeline artefacts + sanity gate.

Per-prompt outputs in ``artefacts/NN-slug/``:
- prompt.txt — verbatim user prompt
- system_prompt.txt — the exact system prompt Haiku saw
- classified_archetype.txt — the classifier's route (may be 'none')
- llm_raw_response.txt — raw Haiku output
- component_list.json — extracted component dict list
- ir.json — composed IR (structure_script omitted at this stage)
- measures.json — the 9 matrix-measures on the output
- usage.json — Haiku token usage + latency
"""
from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

from anthropic import Anthropic

from dd.archetype_library import load_provenance
from dd.compose import generate_from_prompt
from dd.composition.archetype_classifier import classify_archetype
from dd.composition.archetype_injection import inject_archetype
from dd.composition.matrix_measures import compute_measures
from dd.db import get_connection
from dd.prompt_parser import (
    SYSTEM_PROMPT,
    build_project_vocabulary,
    extract_json,
)
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context
from dd.templates import build_component_key_registry, extract_templates


EXP_ROOT = Path(__file__).resolve().parent
ARTEFACTS = EXP_ROOT / "artefacts"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
SUMMARY = EXP_ROOT / "parse_compose_summary.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048
TEMPERATURE = 0.3  # production default after v0.1.5 side-fix 3796058

PROMPTS = (
    ("01-login", "a login screen with email, password, and a sign-in button"),
    ("02-profile-settings", "a profile settings page with avatar, name, email, notification toggles, and a save button"),
    ("03-meme-feed", "a feed of memes with upvote and share buttons under each"),
    ("04-dashboard", "a data dashboard with a line chart and a table of recent transactions"),
    ("05-paywall", "a paywall screen with three pricing tiers and a testimonial"),
    ("06-spa-minimal", "make something minimal and luxurious for a spa app"),
    ("07-search", "a search screen"),
    ("08-explicit-structure", "header with back button, title, share button. Then a card with a heading, 3 lines of body text, and a primary button. Then a secondary button below."),
    ("09-drawer-nav", "a drawer menu with 6 nav items"),
    ("10-onboarding-carousel", "an onboarding carousel with 3 slides, each with an illustration, headline, and subtext"),
    ("11-vague", "something cool"),
    ("12-round-trip-test", "rebuild iPhone 13 Pro Max - 109 from scratch"),
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _log(slug: str, stage: str, status: str, detail: str) -> None:
    line = f"{_now()} | {slug} | {stage} | {status} | {detail}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def build_base_system(conn) -> str:
    """Reproduce the baseline SYSTEM_PROMPT (without archetype injection)."""
    system = SYSTEM_PROMPT
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    if file_row:
        file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
        build_component_key_registry(conn)
        extract_templates(conn, file_id)
        archetypes = extract_screen_archetypes(conn, file_id)
        context = get_archetype_prompt_context(archetypes)
        if context:
            system = system + "\n\n" + context
    vocab = build_project_vocabulary(conn)
    if vocab:
        system = system + "\n\n" + vocab
    return system


def process_prompt(slug: str, prompt: str, client: Anthropic, conn, base_system: str) -> dict:
    out = ARTEFACTS / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt + "\n")

    # Stage 0 — classify
    matched = classify_archetype(prompt, client=client)
    (out / "classified_archetype.txt").write_text(f"{matched or 'none'}\n")

    # Inject archetype skeleton into SYSTEM_PROMPT (no-op when unmatched)
    system = inject_archetype(base_system, archetype=matched)
    (out / "system_prompt.txt").write_text(system)

    summary = {
        "slug": slug,
        "prompt": prompt,
        "matched_archetype": matched,
        "system_prompt_chars": len(system),
    }

    # Stage 1 — Haiku parse
    _log(slug, "parse", "start", f"archetype={matched}")
    try:
        t0 = time.time()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "latency_s": time.time() - t0,
        }
        (out / "llm_raw_response.txt").write_text(raw)
        (out / "usage.json").write_text(json.dumps(usage, indent=2))
        extracted = extract_json(raw)
        if isinstance(extracted, dict):
            (out / "component_list.json").write_text(
                json.dumps(extracted, indent=2)
            )
        else:
            (out / "component_list.json").write_text(
                json.dumps(extracted, indent=2)
            )
        measures = compute_measures(raw, extracted).to_dict()
        (out / "measures.json").write_text(json.dumps(measures, indent=2))
        summary["usage"] = usage
        summary["measures"] = measures
        summary["component_count"] = len(extracted) if isinstance(extracted, list) else 0
        _log(
            slug, "parse", "ok",
            f"components={summary['component_count']} "
            f"total_nodes={measures['total_node_count']} "
            f"container_cov={measures['container_coverage']}",
        )
    except Exception as e:
        _log(slug, "parse", "fail", str(e)[:200])
        summary["error"] = str(e)
        return summary

    # Stage 2 — compose (IR + warnings; no render)
    if not (isinstance(extracted, list) and len(extracted) > 0):
        _log(slug, "compose", "skip", "empty or refusal")
        return summary

    try:
        t0 = time.time()
        result = generate_from_prompt(conn, extracted, page_name=None)
        (out / "ir.json").write_text(json.dumps(result["spec"], indent=2))
        (out / "warnings.json").write_text(
            json.dumps(result.get("warnings", []), indent=2)
        )
        summary["compose"] = {
            "element_count": result.get("element_count", 0),
            "warnings": len(result.get("warnings", [])),
            "latency_s": time.time() - t0,
        }
        _log(
            slug, "compose", "ok",
            f"elements={summary['compose']['element_count']}",
        )
    except Exception as e:
        _log(slug, "compose", "fail", str(e)[:200])
        summary["compose_error"] = str(e)

    return summary


def main() -> None:
    ACTIVITY_LOG.write_text("")
    ARTEFACTS.mkdir(exist_ok=True)

    conn = get_connection(str(DB_PATH))
    base_system = build_base_system(conn)
    _log("_", "setup", "ok", f"base_system_chars={len(base_system)}")

    # Stash archetype provenance so readers can trace which routes
    # exist without cross-referencing the dd/ module.
    (EXP_ROOT / "archetype_provenance.json").write_text(
        json.dumps(load_provenance(), indent=2)
    )

    client = Anthropic()
    summaries: list[dict] = []
    t_start = time.time()
    for slug, prompt in PROMPTS:
        try:
            s = process_prompt(slug, prompt, client, conn, base_system)
        except Exception as e:
            _log(slug, "driver", "fail", str(e)[:200])
            s = {"slug": slug, "prompt": prompt, "driver_error": str(e)}
        summaries.append(s)
        SUMMARY.write_text(json.dumps(summaries, indent=2))

    conn.close()

    elapsed = time.time() - t_start
    matched = sum(1 for s in summaries if s.get("matched_archetype"))
    unmatched = len(summaries) - matched
    refused = sum(
        1 for s in summaries
        if s.get("measures", {}).get("clarification_refusal") == 1
    )
    _log(
        "_", "done", "ok",
        f"matched={matched} unmatched={unmatched} refused={refused} "
        f"elapsed={elapsed:.1f}s",
    )


if __name__ == "__main__":
    main()
