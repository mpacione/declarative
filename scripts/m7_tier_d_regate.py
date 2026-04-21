"""Tier D re-gate — structural scorer vs VLM vs eye check.

The Tier C scorer (``dd/fidelity_score.py``) is scoped to structural
failures F1-F4 observed in Tier B. It has an optional VLM dimension
but the standard eval (``m7_tier_d_eval.py``) never invokes it —
passing the gate at ≥7/10 on structural dims alone is the claim.

This script re-runs the same 3 prompts with:

1. **Save script** — persist the generated JS per prompt.
2. **Screenshot via bridge** — use ``render_test/batch_screenshot.js``
   to export a PNG of the rendered root.
3. **VLM score** — ``dd.visual_inspect.inspect_screenshot`` (Gemini
   3.1 Pro) returns a 1-10 score + verdict (ok/partial/broken).
4. **Combined report** — structural score vs VLM score, side-by-side,
   so a divergence is immediately visible.

Writes artefacts to ``tmp/tier_d_regate/<scope>/`` so the screenshots
+ scripts are inspectable afterward.

Usage::

    .venv/bin/python3 -m scripts.m7_tier_d_regate \\
        --db Dank-EXP-02.declarative.db \\
        --ws-port 9223
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# Same three prompts the standard eval uses, so this compares
# apples-to-apples.
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
class RegateResult:
    scope: str
    prompt: str
    # structural
    struct_score: float = 0.0
    struct_passed: bool = False
    struct_dims: list[dict] = field(default_factory=list)
    # visual
    screenshot_path: str = ""
    screenshot_ok: bool = False
    vlm_score: int = 0
    vlm_verdict: str = "unknown"
    vlm_reason: str = ""
    # SoM component coverage (D2 per scorer-calibration research)
    som_ran: bool = False
    som_precision: float = 0.0
    som_recall: float = 0.0
    som_classifications: list[dict] = field(default_factory=list)
    som_note: str = ""
    # timing
    compose_sec: float = 0.0
    walk_sec: float = 0.0
    screenshot_sec: float = 0.0
    vlm_sec: float = 0.0
    som_sec: float = 0.0
    # diagnostics
    notes: str = ""


def _screenshot_via_bridge(
    script_path: Path, out_png: Path, ws_port: int,
) -> tuple[bool, str]:
    """Invoke render_test/batch_screenshot.js for a single script.
    Returns (ok, err_msg)."""
    manifest_path = out_png.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps([{
        "script_path": str(script_path.resolve()),
        "out_png_path": str(out_png.resolve()),
    }]))
    try:
        result = subprocess.run(
            [
                "node", "render_test/batch_screenshot.js",
                str(manifest_path), str(ws_port),
            ],
            capture_output=True, text=True, timeout=240,
        )
    except subprocess.TimeoutExpired:
        return False, "screenshot timed out after 240s"
    except FileNotFoundError:
        return False, "node binary not found"
    if result.returncode != 0:
        return False, (
            f"batch_screenshot.js rc={result.returncode}; "
            f"stderr={result.stderr[:300]}"
        )
    if not out_png.exists():
        return False, f"expected PNG not written: {out_png}"
    return True, ""


def run_one_regate(
    scope: str, prompt: str, *,
    conn, client, out_dir: Path, ws_port: int,
    gemini_api_key: str | None,
    use_som: bool = True,
) -> RegateResult:
    from dd.compose import generate_from_prompt
    from dd.prompt_parser import parse_prompt
    from dd.fidelity_score import score_fidelity
    from dd.apply_render import BridgeError, walk_rendered_via_bridge

    result = RegateResult(scope=scope, prompt=prompt)
    scope_dir = out_dir / scope
    scope_dir.mkdir(parents=True, exist_ok=True)

    # -------------------- parse + compose --------------------
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
    root_eid = spec.get("root")

    # Persist artefacts early so they survive any downstream crash.
    script_path = scope_dir / "script.js"
    script_path.write_text(script)
    (scope_dir / "spec.json").write_text(json.dumps(spec, indent=2))
    (scope_dir / "ir_elements.json").write_text(
        json.dumps(ir_elements, indent=2)
    )

    # -------------------- walk via bridge (scoring) --------------------
    walk_eid_map: dict = {}
    walk_errors: list = []
    t0 = time.monotonic()
    try:
        payload = walk_rendered_via_bridge(
            script=script, ws_port=ws_port, timeout=180.0,
        )
        walk_eid_map = payload.get("eid_map") or {}
        walk_errors = list(payload.get("errors") or [])
        (scope_dir / "walk.json").write_text(json.dumps(payload, indent=2))
    except BridgeError as e:
        result.notes = f"walk bridge failed: {e}"[:200]
    result.walk_sec = time.monotonic() - t0

    # -------------------- screenshot via bridge --------------------
    # Shot first so SoM can consume the PNG. Structural score runs
    # without the shot; we attach SoM dims to the report afterwards.
    png_path = scope_dir / "screenshot.png"
    t0 = time.monotonic()
    ok, err = _screenshot_via_bridge(script_path, png_path, ws_port)
    result.screenshot_sec = time.monotonic() - t0
    result.screenshot_ok = ok
    result.screenshot_path = str(png_path.relative_to(out_dir.parent.parent)) \
        if png_path.exists() else ""
    if not ok:
        result.notes = (result.notes + " | " if result.notes else "") + \
            f"screenshot: {err}"

    # -------------------- SoM coverage (D2) --------------------
    som_classifications: list[dict] | None = None
    if use_som and ok and walk_eid_map:
        from dd.classify_vision_som import classify_screen_som
        from dd.catalog import get_catalog
        from dd.fidelity_score import build_som_annotations

        t0 = time.monotonic()
        try:
            annotations, id_to_eid = build_som_annotations(
                ir_elements, walk_eid_map,
            )
            (scope_dir / "som_annotations.json").write_text(
                json.dumps({
                    "annotations": annotations,
                    "id_to_eid": id_to_eid,
                }, indent=2)
            )
            if annotations:
                catalog = get_catalog(conn)
                # screen_width/height = rendered root's dims (anchors
                # SoM's scale factor against the PNG).
                root_walk = walk_eid_map.get(root_eid) or {}
                scr_w = float(root_walk.get("width") or 428)
                scr_h = float(root_walk.get("height") or 926)
                png_bytes = png_path.read_bytes()
                som_classifications = classify_screen_som(
                    screen_png=png_bytes,
                    annotations=annotations,
                    client=client,
                    catalog=catalog,
                    screen_width=scr_w,
                    screen_height=scr_h,
                )
                (scope_dir / "som_classifications.json").write_text(
                    json.dumps(som_classifications, indent=2)
                )
                result.som_ran = True
                result.som_classifications = [
                    {**c, "eid": id_to_eid.get(c.get("mark_id", -1))}
                    for c in som_classifications
                ]
            else:
                result.som_note = "no annotations built (only excluded types in IR)"
        except Exception as e:  # noqa: BLE001
            result.som_note = f"SoM error: {e}"[:300]
        result.som_sec = time.monotonic() - t0
    elif not use_som:
        result.som_note = "SoM skipped via flag"

    # -------------------- structural + SoM score --------------------
    report = score_fidelity(
        ir_elements=ir_elements,
        walk_eid_map=walk_eid_map,
        walk_errors=walk_errors,
        root_eid=root_eid,
        som_classifications=som_classifications,
    )
    result.struct_score = report.to_ten(mode="min")
    result.struct_passed = report.to_ten() >= 7.0
    result.struct_dims = [
        {
            "name": d.name,
            "value": round(d.value, 2),
            "passed": d.passed,
            "diagnostic": d.diagnostic[:200],
        }
        for d in report.dimensions
    ]
    # Surface SoM precision + recall at the top level for fast scan.
    for d in report.dimensions:
        if d.name == "component_precision":
            result.som_precision = round(d.value, 2)
        if d.name == "component_recall":
            result.som_recall = round(d.value, 2)

    # -------------------- VLM 1-10 score (legacy comparator) --------
    if ok and gemini_api_key:
        from dd.visual_inspect import inspect_screenshot
        t0 = time.monotonic()
        try:
            vlm = inspect_screenshot(png_path, api_key=gemini_api_key)
            result.vlm_score = vlm.score
            result.vlm_verdict = vlm.verdict
            result.vlm_reason = vlm.reason[:500]
        except Exception as e:  # noqa: BLE001
            result.vlm_verdict = "unknown"
            result.vlm_reason = f"VLM error: {e}"[:500]
        result.vlm_sec = time.monotonic() - t0
    elif not gemini_api_key:
        result.vlm_reason = "GOOGLE_API_KEY not set — VLM skipped"

    return result


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--ws-port", type=int, default=9223)
    parser.add_argument(
        "--out-dir", default="tmp/tier_d_regate",
        help="Where to write per-scope artefacts.",
    )
    parser.add_argument(
        "--scopes", nargs="*", default=None,
        help="Subset of scopes to run (default: all 3).",
    )
    parser.add_argument(
        "--no-som", action="store_true",
        help="Skip the SoM component-coverage pass (D2).",
    )
    parser.add_argument(
        "--no-vlm", action="store_true",
        help="Skip the legacy Gemini 1-10 VLM rating.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    gemini_key = os.environ.get("GOOGLE_API_KEY") if not args.no_vlm else None
    if gemini_key is None and not args.no_vlm:
        print(
            "WARN: GOOGLE_API_KEY not set — legacy VLM rating will be skipped.",
            file=sys.stderr,
        )

    import anthropic
    from dd.db import get_connection

    client = anthropic.Anthropic()
    conn = get_connection(args.db)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scopes = args.scopes or list(_PROMPTS.keys())
    results: list[RegateResult] = []
    try:
        for scope in scopes:
            if scope not in _PROMPTS:
                print(f"Unknown scope: {scope}", file=sys.stderr)
                continue
            prompt = _PROMPTS[scope]
            print(f"\n=== {scope} ===")
            print(f"Prompt: {prompt}")
            r = run_one_regate(
                scope, prompt, conn=conn, client=client,
                out_dir=out_dir, ws_port=args.ws_port,
                gemini_api_key=gemini_key,
                use_som=not args.no_som,
            )
            results.append(r)
            print(
                f"  compose={r.compose_sec:.1f}s "
                f"walk={r.walk_sec:.1f}s "
                f"shot={r.screenshot_sec:.1f}s "
                f"som={r.som_sec:.1f}s "
                f"vlm={r.vlm_sec:.1f}s"
            )
            print(
                f"  struct={r.struct_score:.1f}/10 passed={r.struct_passed}"
            )
            if r.som_ran:
                print(
                    f"  SoM: precision={r.som_precision:.2f} "
                    f"recall={r.som_recall:.2f}"
                )
            elif r.som_note:
                print(f"  SoM: {r.som_note}")
            print(
                f"  VLM(1-10): score={r.vlm_score}/10 "
                f"verdict={r.vlm_verdict}"
            )
            if r.notes:
                print(f"  NOTE: {r.notes}")
            if r.vlm_reason:
                print(f"  VLM: {r.vlm_reason[:200]}")
    finally:
        conn.close()

    # -------------------- summary --------------------
    print("\n" + "=" * 84)
    print(
        f"{'scope':20s} {'struct':>8s} {'SoM-P':>6s} {'SoM-R':>6s} "
        f"{'VLM':>6s} {'verdict':>10s} {'shot':>6s}"
    )
    print("-" * 84)
    for r in results:
        shot = "ok" if r.screenshot_ok else "FAIL"
        som_p = f"{r.som_precision:.2f}" if r.som_ran else "  — "
        som_r = f"{r.som_recall:.2f}" if r.som_ran else "  — "
        print(
            f"{r.scope:20s} {r.struct_score:>7.1f} {som_p:>6s} "
            f"{som_r:>6s} {r.vlm_score:>4}/10 "
            f"{r.vlm_verdict:>10s} {shot:>6s}"
        )

    # -------------------- divergence diagnostic --------------------
    print("\nDIVERGENCE DIAGNOSTIC (structural vs visual):")
    for r in results:
        if not r.screenshot_ok:
            print(f"  {r.scope}: cannot compare — no screenshot")
            continue
        if r.struct_passed and r.vlm_verdict == "broken":
            print(
                f"  {r.scope}: ⚠ STRUCT-PASS + VLM-BROKEN — "
                "scorer is out of calibration"
            )
        elif r.struct_passed and r.vlm_verdict == "partial":
            print(
                f"  {r.scope}: ~ STRUCT-PASS + VLM-PARTIAL — "
                "scorer is optimistic"
            )
        elif r.struct_passed and r.vlm_verdict == "ok":
            print(
                f"  {r.scope}: ✓ STRUCT-PASS + VLM-OK — both agree"
            )
        elif not r.struct_passed and r.vlm_verdict == "ok":
            print(
                f"  {r.scope}: ⚠ STRUCT-FAIL + VLM-OK — "
                "scorer is pessimistic (false negative)"
            )
        else:
            print(
                f"  {r.scope}: ✗ STRUCT-FAIL + VLM-{r.vlm_verdict.upper()} — "
                "both say broken (expected)"
            )

    report_path = Path(args.out_dir) / "report.json"
    report_path.write_text(json.dumps(
        [asdict(r) for r in results], indent=2,
    ))
    print(f"\nFull report: {report_path}")
    print(f"Screenshots in: {args.out_dir}/<scope>/screenshot.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
