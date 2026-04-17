"""Resize captured PNGs to 1024px longest side; overwrite in place.

Gemini inline_data cost scales with byte size. Native iPad 12.9" PNGs
are ~1MB each; reducing to 1024px longest side cuts payload 4-6x while
keeping text legible for a VLM.
"""

import datetime as dt
import csv
from pathlib import Path
from PIL import Image

EXP = Path("/Users/mattpacione/declarative-build/experiments/E-principles-induction")
LOG = EXP / "activity.log"
SAMPLE_CSV = EXP / "sample.csv"
TARGET = 1024


def log(stage: str, status: str, detail: str = "") -> None:
    ts = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    LOG.open("a").write(f"{ts} | {stage} | {status} | {detail}\n")


def main() -> None:
    rows = list(csv.DictReader(SAMPLE_CSV.open()))
    before_total = 0
    after_total = 0
    for row in rows:
        p = EXP / row["file_path"]
        before = p.stat().st_size
        before_total += before
        img = Image.open(p)
        w, h = img.size
        longest = max(w, h)
        if longest > TARGET:
            ratio = TARGET / longest
            new = (round(w * ratio), round(h * ratio))
            img = img.resize(new, Image.LANCZOS)
            img.save(p, format="PNG", optimize=True)
        after = p.stat().st_size
        after_total += after
        log("resize", "ok", f"screen_id={row['screen_id']} {w}x{h} -> {img.size[0]}x{img.size[1]} bytes {before}->{after}")
    log("resize", "summary", f"total bytes {before_total}->{after_total} ({100*after_total/before_total:.0f}%)")
    print(f"total bytes {before_total}->{after_total} ({100*after_total/before_total:.0f}%)")


if __name__ == "__main__":
    main()
