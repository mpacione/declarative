"""M7.5 S3.4 verifier-as-agent demo — repair loop end-to-end.

Seeds a deliberately-broken edit on a donor doc and lets the
repair loop (``dd.repair_agent.run_repair_loop``) converge on a
passing verifier in ≤3 iterations.

Scenario: a ``TextExpectationVerifier`` asserts the positional
text of specific eids matches a target. We seed the error by
applying ``set @X text="..."`` with a wrong value as the
``initial_edits`` step; the LLM proposer then emits a corrective
``set`` that puts the expected text back.

Usage::

    .venv/bin/python3 -m scripts.repair_demo \\
        --db Dank-EXP-02.declarative.db [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from dd.boundary import StructuredError
from dd.repair_agent import (
    RepairReport,
    build_llm_proposer,
    run_repair_loop,
)


@dataclass
class TextExpectationVerifier:
    """Pass when every required (eid → expected_text) pair matches
    the doc's positional content."""

    expectations: dict[str, str]

    def verify(self, doc) -> RepairReport:
        errors = []
        for eid, expected in self.expectations.items():
            actual = self._find_positional(doc, eid)
            if actual != expected:
                errors.append(StructuredError(
                    kind="KIND_TEXT_STALE",
                    id=eid,
                    error=(
                        f"positional text at @{eid} is "
                        f"{actual!r}, expected {expected!r}"
                    ),
                    hint=(
                        f'Emit `set @{eid} text="{expected}"` to '
                        "restore the target text."
                    ),
                ))
        return RepairReport(is_ok=not errors, errors=tuple(errors))

    def _find_positional(self, doc, eid: str) -> Optional[str]:
        def go(ns):
            for n in ns:
                if hasattr(n, "head") and n.head.eid == eid:
                    pos = n.head.positional
                    if pos is not None:
                        return getattr(pos, "py", None)
                if getattr(n, "block", None):
                    r = go(n.block.statements)
                    if r is not None:
                        return r
            return None

        return go(doc.top_level)


class _DryRunProposer:
    """Dry-run proposer that directly emits the hint as the edit
    source. Useful for CI smoke-testing without real API costs."""

    def propose(self, errors, doc):
        out = []
        for e in errors:
            if not e.hint:
                continue
            # The TextExpectationVerifier hint happens to be a
            # ready-to-go edit source; strip the surrounding
            # narration.
            if "`set @" in e.hint:
                # Extract the backtick-quoted source.
                lo = e.hint.find("`set @") + 1
                hi = e.hint.find("`", lo)
                if hi > lo:
                    out.append(e.hint[lo:hi])
        return out


def run_demo(db_path, *, screen_id, dry_run):
    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.db import get_connection
    from dd.ir import generate_ir

    conn = get_connection(db_path)
    try:
        if screen_id is None:
            # Screen 186 has a single heading with positional text
            # we can reliably assert against.
            screen_id = 186
        print(f"Donor screen: {screen_id}")
        ir = generate_ir(conn, screen_id, semantic=True)
        spec = ir.get("spec") if "spec" in ir else ir
        doc, _ = compress_to_l3_with_nid_map(
            spec, conn, screen_id=screen_id,
        )

        # Find a globally-unique text-bearing eid with non-empty
        # positional. Ambiguous ones can't be addressed with a
        # bare `@X` in the seeded initial edit.
        from collections import Counter
        counts: Counter = Counter()

        def count_walk(ns):
            for n in ns:
                if hasattr(n, "head") and n.head.eid:
                    counts[n.head.eid] += 1
                if getattr(n, "block", None):
                    count_walk(n.block.statements)

        count_walk(doc.top_level)

        text_eid = None
        expected_text = None

        def find(ns):
            nonlocal text_eid, expected_text
            if text_eid is not None:
                return
            for n in ns:
                if (
                    hasattr(n, "head")
                    and n.head.eid
                    and counts[n.head.eid] == 1
                    and n.head.type_or_path in (
                        "text", "heading", "link",
                    )
                    and n.head.positional is not None
                    and isinstance(n.head.positional.py, str)
                    and n.head.positional.py.strip()
                ):
                    text_eid = n.head.eid
                    expected_text = n.head.positional.py
                    return
                if getattr(n, "block", None):
                    find(n.block.statements)

        find(doc.top_level)
        if text_eid is None:
            print(
                "No text candidate found on donor; try a different "
                "screen.", file=sys.stderr,
            )
            return 1
        print(
            f"Target: @{text_eid} expected_text={expected_text!r}"
        )

        verifier = TextExpectationVerifier(
            expectations={text_eid: expected_text},
        )
        # Seed the error: set a wrong text so the verifier fires.
        seeded = (
            f'set @{text_eid} text="[intentionally broken]"',
        )

        if dry_run:
            proposer = _DryRunProposer()
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print(
                    "ANTHROPIC_API_KEY not set.", file=sys.stderr,
                )
                return 1
            import anthropic
            proposer = build_llm_proposer(
                anthropic.Anthropic(),
            )

        outcome = run_repair_loop(
            doc=doc,
            initial_edits=seeded,
            verifier=verifier,
            proposer=proposer,
            max_iterations=3,
        )

        print(
            f"\nRepair outcome: succeeded={outcome.succeeded} "
            f"iterations={outcome.iterations} "
            f"applied_edits={len(outcome.applied_edit_sources)} "
            f"parse_errors={len(outcome.parse_errors)}"
        )
        print("\nApplied edit sources:")
        for src in outcome.applied_edit_sources:
            print(f"  {src}")

        if outcome.succeeded:
            print("\nM7.5 SUCCESS: repair loop converged.")
            return 0
        print("\nM7.5 FAIL: repair loop did not converge.",
              file=sys.stderr)
        if outcome.last_report and outcome.last_report.errors:
            for e in outcome.last_report.errors[:5]:
                print(
                    f"  {e.kind} {e.id} {e.error}"
                    f" hint={e.hint!r}",
                    file=sys.stderr,
                )
        return 1
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    return run_demo(
        args.db, screen_id=args.screen_id, dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
