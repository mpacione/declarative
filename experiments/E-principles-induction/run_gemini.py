"""Call Gemini 3.1 Pro with the 25 Dank screenshots and the induction prompt.

Writes:
  outputs/raw-response.json — full API response
  outputs/voice.md
  outputs/intent-conventions.md
  outputs/exclusions.md
  outputs/lineage.md
  outputs/merged-draft.md — all four sections formatted for drop-in to design.md

One-shot. Temperature 0.3. No retries for quality reasons per experiment spec.
"""

import base64
import csv
import datetime as dt
import json
import os
import time
from pathlib import Path

import urllib.request
import urllib.error

EXP = Path("/Users/mattpacione/declarative-build/experiments/E-principles-induction")
LOG = EXP / "activity.log"
PROMPT_PATH = EXP / "prompt.txt"
SAMPLE_CSV = EXP / "sample.csv"
OUT = EXP / "outputs"

MODEL = "gemini-3-pro-preview"  # primary; spec says 3.1 Pro but actual model id is 3-pro-preview
# The user spec calls out "gemini-3.1-pro-preview"; some tenants expose it under
# "gemini-3-pro-preview" or "gemini-3.1-pro". We'll try the exact spec name first
# and fall back to the canonical one on 404.
PRIMARY_MODEL = "gemini-3.1-pro-preview"
FALLBACK_MODELS = ("gemini-3-pro-preview", "gemini-3.0-pro-preview")
ENDPOINT_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def log(stage: str, status: str, detail: str = "") -> None:
    ts = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    LOG.open("a").write(f"{ts} | {stage} | {status} | {detail}\n")
    print(f"{ts} | {stage} | {status} | {detail}")


def build_parts(prompt: str, sample_rows: list[dict]) -> list[dict]:
    parts: list[dict] = [{"text": prompt}]
    # Intro text tying each image to its index so the model can reference "image 3"
    for i, row in enumerate(sample_rows, 1):
        img_path = EXP / row["file_path"]
        with img_path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        parts.append({
            "text": f"\n\n[Image {i}/{len(sample_rows)}: screen_id={row['screen_id']} — {row['name']} ({row['device_class']})]",
        })
        parts.append({
            "inline_data": {"mime_type": "image/png", "data": b64},
        })
    return parts


def call_gemini(parts: list[dict], model: str, api_key: str) -> dict:
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    url = ENDPOINT_TMPL.format(model=model) + f"?key={api_key}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
            return {"status": resp.status, "body": json.loads(raw), "ms": int((time.monotonic() - t0) * 1000), "model": model}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode("utf-8", errors="replace"), "ms": int((time.monotonic() - t0) * 1000), "model": model}


def extract_text(body: dict) -> str | None:
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None


def main() -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_API_KEY not set; source .env first")

    prompt = PROMPT_PATH.read_text().strip()
    rows = list(csv.DictReader(SAMPLE_CSV.open()))
    log("gemini", "build_parts", f"n_images={len(rows)}")
    parts = build_parts(prompt, rows)

    # Pick model: spec names gemini-3.1-pro-preview; try that first then fallbacks.
    candidates = [PRIMARY_MODEL] + list(FALLBACK_MODELS)
    result = None
    for m in candidates:
        log("gemini", "call", f"model={m}")
        r = call_gemini(parts, m, api_key)
        if r.get("status") == 200:
            result = r
            break
        log("gemini", "try-fail", f"model={m} status={r.get('status')} err={(r.get('error') or '')[:200]}")
    if result is None:
        raise SystemExit("all model candidates failed; see activity.log")

    body = result["body"]
    text = extract_text(body) or ""
    usage = body.get("usageMetadata", {})
    finish = ((body.get("candidates") or [{}])[0].get("finishReason"))

    log("gemini", "ok", f"model={result['model']} ms={result['ms']} finish={finish} usage={json.dumps(usage)}")

    # Save raw response
    (OUT / "raw-response.json").write_text(json.dumps({
        "model": result["model"],
        "status": result["status"],
        "ms": result["ms"],
        "usage_metadata": usage,
        "finish_reason": finish,
        "body": body,
        "text_reply": text,
    }, indent=2))

    # Parse the inner JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        # Fallback: try to strip any accidental markdown fence
        s = text.strip()
        if s.startswith("```"):
            s = s.strip("`").lstrip("json").strip()
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            log("gemini", "parse-fail", f"err={e}")
            (OUT / "voice.md").write_text("# Voice\n\n(Unparseable model output — see raw-response.json)\n")
            (OUT / "intent-conventions.md").write_text("# Intent conventions\n\n(Unparseable)\n")
            (OUT / "exclusions.md").write_text("# Exclusions\n\n(Unparseable)\n")
            (OUT / "lineage.md").write_text("# Style lineage\n\n(Unparseable)\n")
            (OUT / "merged-draft.md").write_text(text)
            return

    voice = (parsed.get("voice") or "").strip()
    intent = [s.strip() for s in (parsed.get("intent_conventions") or []) if s and s.strip()]
    excl = [s.strip() for s in (parsed.get("exclusions") or []) if s and s.strip()]
    lineage = [s.strip() for s in (parsed.get("style_lineage") or []) if s and s.strip()]

    # Individual section files
    (OUT / "voice.md").write_text(f"# Voice\n\n{voice}\n" if voice else "# Voice\n\n(empty)\n")
    (OUT / "intent-conventions.md").write_text(
        "# Intent conventions\n\n" + ("\n".join(f"- {x}" for x in intent) if intent else "(empty)") + "\n"
    )
    (OUT / "exclusions.md").write_text(
        "# Exclusions\n\n" + ("\n".join(f"- {x}" for x in excl) if excl else "(empty)") + "\n"
    )
    (OUT / "lineage.md").write_text(
        "# Style lineage\n\n" + ("\n".join(f"- {x}" for x in lineage) if lineage else "(empty)") + "\n"
    )

    # Merged draft matching design.md TODO block structure
    merged = []
    merged.append("## Designer-authored sections (auto-induced v1)\n")
    merged.append("### Voice")
    merged.append(voice if voice else "(empty)")
    merged.append("")
    merged.append("### Intent conventions")
    for x in intent:
        merged.append(f"- {x}")
    if not intent:
        merged.append("(empty)")
    merged.append("")
    merged.append("### Exclusions")
    for x in excl:
        merged.append(f"- {x}")
    if not excl:
        merged.append("(empty)")
    merged.append("")
    merged.append("### Style lineage")
    for x in lineage:
        merged.append(f"- {x}")
    if not lineage:
        merged.append("(empty)")
    merged.append("")
    (OUT / "merged-draft.md").write_text("\n".join(merged))

    log("gemini", "saved", f"voice_chars={len(voice)} intent={len(intent)} excl={len(excl)} lineage={len(lineage)}")


if __name__ == "__main__":
    main()
