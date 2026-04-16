"""Measure token size of design.md, section by section.

Outputs a markdown fragment for size-analysis.md and a JSON blob with the
raw numbers that can be consumed by downstream experiments.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text))

    TOKENIZER_NAME = "cl100k_base (tiktoken)"
except ImportError:  # pragma: no cover
    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    TOKENIZER_NAME = "len(text)/4 (approximation)"


SECTION_RE = re.compile(r"^(## .+)$", re.MULTILINE)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split on level-2 markdown headings; preserve the preamble as 'header'."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return [("(all)", text)]
    sections: list[tuple[str, str]] = []
    # Preamble (everything before the first ## heading) is the header.
    pre = text[: matches[0].start()].strip()
    if pre:
        first_line = pre.splitlines()[0].lstrip("# ").strip()
        sections.append((first_line, pre))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(1).lstrip("# ").strip()
        sections.append((title, text[start:end].strip()))
    return sections


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="design.md")
    parser.add_argument("--out", default="size-analysis.md")
    parser.add_argument("--json-out", default="size-analysis.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    content = input_path.read_text(encoding="utf-8")
    total_chars = len(content)
    total_tokens = count_tokens(content)

    section_stats: list[dict[str, int | str]] = []
    for title, body in split_sections(content):
        section_stats.append(
            {
                "title": title,
                "chars": len(body),
                "tokens": count_tokens(body),
            }
        )

    section_stats.sort(key=lambda s: -s["tokens"])

    verdict = (
        "**prompt-cache** (< 50K tokens)"
        if total_tokens < 50_000
        else (
            "**retrieval-chunked** (> 200K tokens)"
            if total_tokens > 200_000
            else "**consider retrieval** (50K–200K tokens band)"
        )
    )

    lines: list[str] = []
    lines.append(f"# design.md size analysis")
    lines.append("")
    lines.append(f"- Source file: `{input_path.name}`")
    lines.append(f"- Tokenizer: {TOKENIZER_NAME}")
    lines.append(f"- Total characters: {total_chars:,}")
    lines.append(f"- **Total tokens: {total_tokens:,}**")
    lines.append(f"- Verdict: {verdict}")
    lines.append("")
    lines.append("## Section breakdown (largest first)")
    lines.append("")
    lines.append("| Section | Chars | Tokens | % of total |")
    lines.append("| --- | --- | --- | --- |")
    for s in section_stats:
        pct = s["tokens"] / total_tokens if total_tokens else 0
        lines.append(
            f"| {s['title']} | {s['chars']:,} | {s['tokens']:,} | {pct:.1%} |",
        )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    lines.append(
        "With a design.md under **50K tokens**, the entire artefact fits "
        "comfortably inside a single Claude / GPT prompt cache entry and we "
        "should treat it as a **static prefix** — prompt-cached once per file, "
        "invalidated only when the designer edits the TODO sections or when a "
        "fresh extraction materially changes the CKR / token palette.",
    )
    lines.append("")
    lines.append(
        "Retrieval-chunking is not warranted at this size; the retrieval "
        "index should instead point at individual *subtree exemplars* from "
        "the IR, not at substrings of this file.",
    )
    lines.append("")
    lines.append(
        "If a **new project** had substantially more CKR entries (say, "
        "a design system like Carbon or Primer with ~500 shared components), "
        "the Component-inventory section would dominate and could push the "
        "total toward the 50K–200K band. In that regime the natural split is "
        "section-level: cache the tokens / typography / spacing / adjacency "
        "sections as a stable prefix, and retrieve the component-inventory "
        "rows relevant to each prompt.",
    )
    lines.append("")
    lines.append(
        "### Sanity numbers for extrapolation",
    )
    lines.append("")
    lines.append(
        "- Average component-inventory row: "
        f"{(section_stats[0]['tokens'] / 129):.1f} tokens (129 CKR entries "
        f"in this file).",
    )
    lines.append(
        "- At 500 CKR entries (a mid-sized public design system) the inventory "
        "alone would land near "
        f"{int((section_stats[0]['tokens'] / 129) * 500):,} tokens, "
        "pushing total into the retrieval band.",
    )
    lines.append(
        "- At 2,000 CKR entries (Material Design class) it would exceed "
        f"{int((section_stats[0]['tokens'] / 129) * 2000):,} tokens — "
        "retrieval-chunked is the only tractable option.",
    )
    lines.append("")
    lines.append("### Concrete wiring recommendation")
    lines.append("")
    lines.append(
        "- Store the full design.md under a **stable cache key** derived from "
        "`(file_key, extraction_run_id, design_md_revision)`.",
    )
    lines.append(
        "- Put the designer-authored TODO sections at the *end* so their "
        "edits don't bust the prefix cache for the deterministic sections.",
    )
    lines.append(
        "- Expose the section map (from `size-analysis.json`) so the "
        "generator prompt can cheaply reason about how much of the budget "
        "each section will consume.",
    )
    lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps(
            {
                "tokenizer": TOKENIZER_NAME,
                "total_chars": total_chars,
                "total_tokens": total_tokens,
                "sections": section_stats,
                "verdict": verdict,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"design.md: {total_chars:,} chars / {total_tokens:,} tokens. "
        f"Wrote {args.out} and {args.json_out}.",
    )


if __name__ == "__main__":
    main()
