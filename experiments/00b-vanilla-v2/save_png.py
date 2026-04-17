"""Decode base64 PNG and write to file.

Usage: python save_png.py <b64_string> <out_path>
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path


def main() -> None:
    b64 = sys.argv[1]
    out = Path(sys.argv[2])
    out.write_bytes(base64.b64decode(b64))
    print(f"wrote {out} ({len(b64)} b64 chars)")


if __name__ == "__main__":
    main()
