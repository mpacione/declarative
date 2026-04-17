"""Exp 00g-matrix — v0.1.5 generation-density matrix runner.

Design memo: ``docs/research/generation-density-design.md`` §3.
Plan reference: ``docs/research/v0.1.5-plan.md`` Week 1 Step 1.

Runs (3 temperatures × 5 SYSTEM_PROMPT contracts × 12 prompts × 1 sample)
plus a variance slice (T=1.0 × S0 × 12 prompts × 5 samples) = 240 Haiku
calls. Structural measures only — no render, no VLM. VLM deferred to
a ~60-call confirmation on the winning cell.

Output: ``matrix_results.json`` — one row per call with (cell id,
prompt, sample, usage, raw text, extracted result, structural
measures). ``analyze.py`` reads this and writes the 3×5 heatmaps +
stopping-criterion memo.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from anthropic import Anthropic

from dd.composition.matrix_contracts import CONTRACT_IDS, build_contract_prompt
from dd.composition.matrix_measures import compute_measures
from dd.db import get_connection
from dd.prompt_parser import build_project_vocabulary, extract_json
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context
from dd.templates import build_component_key_registry, extract_templates


EXP_ROOT = Path(__file__).resolve().parent
OUTPUT = EXP_ROOT / "matrix_results.json"
ACTIVITY_LOG = EXP_ROOT / "activity.log"
SYSTEM_PROMPTS_DIR = EXP_ROOT / "system_prompts"
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "Dank-EXP-02.declarative.db"

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048
MAX_WORKERS = 10

TEMPERATURES: tuple[float, ...] = (0.0, 0.5, 1.0)

PROMPTS: tuple[tuple[str, str], ...] = (
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

VARIANCE_SLICE_SAMPLES = 5  # T=1.0 × S0 × 12 prompts × 5 samples = 60 calls
VARIANCE_TEMPERATURE = 1.0
VARIANCE_CONTRACT = "S0"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _log(msg: str) -> None:
    line = f"{_now()} | {msg}\n"
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line)
    sys.stderr.write(line)


def build_project_context() -> tuple[str, str]:
    """Build archetype + vocab contexts once per run (identical across
    all 240 cells — only the variant wrapper differs)."""
    conn = get_connection(str(DB_PATH))
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    if file_row:
        file_id = file_row[0] if isinstance(file_row, tuple) else file_row["id"]
        build_component_key_registry(conn)
        extract_templates(conn, file_id)
        archetypes = extract_screen_archetypes(conn, file_id)
        archetype_context = get_archetype_prompt_context(archetypes) or ""
    else:
        archetype_context = ""
    vocab_context = build_project_vocabulary(conn) or ""
    conn.close()
    return archetype_context, vocab_context


def persist_system_prompts(archetype: str, vocab: str) -> None:
    SYSTEM_PROMPTS_DIR.mkdir(exist_ok=True)
    for cid in CONTRACT_IDS:
        prompt = build_contract_prompt(cid, archetype=archetype, vocab=vocab)
        (SYSTEM_PROMPTS_DIR / f"{cid}.txt").write_text(prompt)


def _call_one(
    *,
    client: Anthropic,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> dict:
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = resp.content[0].text
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "stop_reason": resp.stop_reason,
            "latency_s": time.time() - t0,
        }
        return {"ok": True, "raw_text": raw_text, "usage": usage}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "raw_text": "",
            "usage": {"latency_s": time.time() - t0},
            "error": f"{type(exc).__name__}: {exc!s}"[:500],
        }


def _cell_id(contract: str, temperature: float, slug: str, sample: int) -> str:
    t_str = f"t{str(temperature).replace('.', '_')}"
    return f"{contract}__{t_str}__{slug}__s{sample}"


def _build_call_plan(contracts_by_variant: dict[str, str]) -> list[dict]:
    """One dict per planned Haiku call."""
    plan: list[dict] = []

    # Main matrix: 3T × 5S × 12 prompts × 1 sample = 180
    for temperature in TEMPERATURES:
        for contract in CONTRACT_IDS:
            for slug, user_prompt in PROMPTS:
                plan.append({
                    "cell_id": _cell_id(contract, temperature, slug, 0),
                    "contract": contract,
                    "temperature": temperature,
                    "slug": slug,
                    "user_prompt": user_prompt,
                    "sample": 0,
                    "section": "matrix",
                    "system_prompt": contracts_by_variant[contract],
                })

    # Variance slice: T=1.0 × S0 × 12 prompts × 5 samples = 60
    for slug, user_prompt in PROMPTS:
        for sample in range(VARIANCE_SLICE_SAMPLES):
            plan.append({
                "cell_id": _cell_id(VARIANCE_CONTRACT, VARIANCE_TEMPERATURE, slug, sample),
                "contract": VARIANCE_CONTRACT,
                "temperature": VARIANCE_TEMPERATURE,
                "slug": slug,
                "user_prompt": user_prompt,
                "sample": sample,
                "section": "variance",
                "system_prompt": contracts_by_variant[VARIANCE_CONTRACT],
            })

    return plan


def _execute_cell(plan_entry: dict, client: Anthropic) -> dict:
    call_result = _call_one(
        client=client,
        system_prompt=plan_entry["system_prompt"],
        user_prompt=plan_entry["user_prompt"],
        temperature=plan_entry["temperature"],
    )

    if call_result["ok"]:
        extracted = extract_json(call_result["raw_text"])
        measures = compute_measures(call_result["raw_text"], extracted).to_dict()
        if isinstance(extracted, dict):
            # ``_clarification_refusal`` dict — persist just the prose.
            extracted_payload: list | dict | str = {
                "_clarification_refusal": extracted["_clarification_refusal"][:2000]
            }
        else:
            extracted_payload = extracted
    else:
        extracted_payload = None
        measures = None

    return {
        "cell_id": plan_entry["cell_id"],
        "section": plan_entry["section"],
        "contract": plan_entry["contract"],
        "temperature": plan_entry["temperature"],
        "slug": plan_entry["slug"],
        "sample": plan_entry["sample"],
        "ok": call_result["ok"],
        "usage": call_result["usage"],
        "raw_text": call_result["raw_text"][:8000],  # truncate for file size
        "extracted": extracted_payload,
        "measures": measures,
        "error": call_result.get("error"),
    }


def main() -> None:
    ACTIVITY_LOG.write_text("")
    _log(f"start db={DB_PATH} workers={MAX_WORKERS}")

    archetype, vocab = build_project_context()
    _log(f"project_context archetype_chars={len(archetype)} vocab_chars={len(vocab)}")

    contracts_by_variant = {
        cid: build_contract_prompt(cid, archetype=archetype, vocab=vocab)
        for cid in CONTRACT_IDS
    }
    persist_system_prompts(archetype, vocab)
    for cid, sp in contracts_by_variant.items():
        _log(f"contract={cid} system_prompt_chars={len(sp)}")

    plan = _build_call_plan(contracts_by_variant)
    _log(f"plan_size total={len(plan)} matrix={sum(1 for p in plan if p['section']=='matrix')} variance={sum(1 for p in plan if p['section']=='variance')}")

    client = Anthropic()
    results: list[dict] = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_execute_cell, p, client): p for p in plan}
        done_count = 0
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            done_count += 1
            if done_count % 20 == 0 or done_count == len(plan):
                elapsed = time.time() - t_start
                ok = sum(1 for r in results if r["ok"])
                _log(f"progress {done_count}/{len(plan)} ok={ok} elapsed={elapsed:.1f}s")

    # Sort results deterministically by section then cell_id for readability
    results.sort(key=lambda r: (r["section"], r["cell_id"]))

    # Aggregate cost + summary for the header
    total_in = sum((r["usage"].get("input_tokens") or 0) for r in results if r["ok"])
    total_out = sum((r["usage"].get("output_tokens") or 0) for r in results if r["ok"])
    # Haiku 4.5: $1 / MTok input, $5 / MTok output (assume uncached worst case)
    cost_usd = (total_in / 1_000_000) * 1.0 + (total_out / 1_000_000) * 5.0
    n_ok = sum(1 for r in results if r["ok"])
    n_fail = len(results) - n_ok
    elapsed = time.time() - t_start

    payload = {
        "meta": {
            "timestamp": _now(),
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "temperatures": list(TEMPERATURES),
            "contract_ids": list(CONTRACT_IDS),
            "prompts": [{"slug": s, "prompt": p} for s, p in PROMPTS],
            "variance_slice": {
                "contract": VARIANCE_CONTRACT,
                "temperature": VARIANCE_TEMPERATURE,
                "samples_per_prompt": VARIANCE_SLICE_SAMPLES,
            },
            "n_calls_ok": n_ok,
            "n_calls_fail": n_fail,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "cost_usd_uncached_worst_case": round(cost_usd, 4),
            "elapsed_s": round(elapsed, 1),
            "project_context_chars": {
                "archetype": len(archetype),
                "vocab": len(vocab),
            },
        },
        "results": results,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    _log(f"done n_ok={n_ok} n_fail={n_fail} cost=${cost_usd:.3f} elapsed={elapsed:.1f}s out={OUTPUT}")


if __name__ == "__main__":
    main()
