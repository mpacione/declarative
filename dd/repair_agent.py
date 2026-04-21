"""M7.5 verifier-as-agent — repair loop.

Plan §4 S3.4: verifier emits ``StructuredError`` entries with
optional ``hint`` text, an LLM receives those and proposes
corrective edits, apply → re-verify, ≤N iterations cap. Success
means "verifier said is_ok=True before the cap."

Deliberately generic over verifier + proposer. The loop doesn't
know about Figma, render, or the Anthropic API — a concrete
demo wires those in. This keeps the loop unit-testable with
stubs and re-usable across backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Protocol

from dd.boundary import StructuredError
from dd.markup_l3 import DDMarkupParseError, L3Document, apply_edits, parse_l3


@dataclass
class RepairReport:
    """Verifier output for a single iteration."""

    is_ok: bool
    errors: tuple[StructuredError, ...] = ()


@dataclass
class RepairOutcome:
    """End-of-loop diagnostics."""

    succeeded: bool
    iterations: int
    final_doc: Optional[L3Document] = None
    applied_edit_sources: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    last_report: Optional[RepairReport] = None


class Verifier(Protocol):
    def verify(self, doc: L3Document) -> RepairReport: ...


class Proposer(Protocol):
    def propose(
        self,
        errors: tuple[StructuredError, ...],
        doc: L3Document,
    ) -> Iterable[str]: ...


def run_repair_loop(
    *,
    doc: L3Document,
    initial_edits: Iterable[str] = (),
    verifier: Verifier,
    proposer: Proposer,
    max_iterations: int = 3,
) -> RepairOutcome:
    """Apply ``initial_edits`` → verify → if not ok, ask
    ``proposer`` for corrective edit sources, apply, re-verify,
    repeat up to ``max_iterations``.

    Returns a ``RepairOutcome`` recording iteration count, every
    applied edit source, any proposer-originated parse errors,
    and the final doc + verifier report."""
    outcome = RepairOutcome(succeeded=False, iterations=0)
    current = doc
    accumulated_edits: list[str] = []

    # Apply initial edits once, before the first verify call.
    for src in initial_edits:
        try:
            edits = list(parse_l3(src).edits)
            if edits:
                current = apply_edits(current, edits)
                accumulated_edits.append(src)
        except DDMarkupParseError as e:
            outcome.parse_errors.append(f"initial: {e}")

    for iteration in range(1, max_iterations + 1):
        outcome.iterations = iteration
        report = verifier.verify(current)
        outcome.last_report = report
        outcome.final_doc = current
        if report.is_ok:
            outcome.succeeded = True
            outcome.applied_edit_sources = list(accumulated_edits)
            return outcome

        # Ask the proposer for next-step edit sources.
        suggestions = list(proposer.propose(report.errors, current))
        if not suggestions:
            break

        # Try to apply each suggestion; record parse errors and
        # continue on recoverable ones. An apply_edits failure
        # (e.g. KIND_EID_NOT_FOUND) is treated like a parse
        # error: record and skip. We do NOT break when an
        # iteration applied nothing — the proposer may have had
        # a transient issue; let max_iterations bound the loop.
        for src in suggestions:
            try:
                edits = list(parse_l3(src).edits)
                if not edits:
                    continue
                current = apply_edits(current, edits)
                accumulated_edits.append(src)
            except DDMarkupParseError as e:
                outcome.parse_errors.append(
                    f"iter{iteration}: {e}"
                )
                continue

    outcome.final_doc = current
    outcome.applied_edit_sources = list(accumulated_edits)
    return outcome


# ---------------------------------------------------------------
# Convenience: LLM-driven proposer
# ---------------------------------------------------------------


def build_llm_proposer(
    client,
    *,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 800,
):
    """Return a :class:`Proposer` that asks Claude to turn an
    error list (with hints) into corrective L3 edit statements.

    The returned proposer has shape::

        class _LLMProposer:
            def propose(errors, doc) -> list[str]: ...

    Each string in the returned list is one L3 edit source. The
    repair loop parses + applies them sequentially.
    """
    from dd.markup_l3 import emit_l3

    tool_schema = {
        "name": "emit_corrective_edits",
        "description": (
            "Emit a list of L3 edit statement strings that would "
            "repair the structured errors. Each string must be a "
            "complete, parseable L3 edit (e.g. `set @X visible="
            "false` or `delete @Y`). Leave the list empty if no "
            "repair is possible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "string", "minLength": 3,
                    },
                },
                "rationale": {
                    "type": "string",
                },
            },
            "required": ["edits", "rationale"],
        },
    }

    class _LLMProposer:
        def propose(
            self,
            errors: tuple[StructuredError, ...],
            doc: L3Document,
        ) -> list[str]:
            if not errors:
                return []
            error_lines = []
            for e in errors[:20]:
                hint = f" — HINT: {e.hint}" if e.hint else ""
                error_lines.append(
                    f"- {e.kind} id={e.id} msg={e.error!r}{hint}"
                )
            user = (
                "### Current document (L3 markup)\n"
                "```\n" + emit_l3(doc)[:4000] + "\n```\n\n"
                "### Verifier errors\n" +
                "\n".join(error_lines) +
                "\n\nPropose a short list of L3 edit statements "
                "that would resolve the errors. Prefer small, "
                "targeted edits over restructuring. Each edit "
                "must be a single statement."
            )
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": tool_schema["name"]},
                messages=[{"role": "user", "content": user}],
            )
            for block in getattr(resp, "content", []) or []:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if getattr(block, "name", None) != tool_schema["name"]:
                    continue
                inp = getattr(block, "input", None)
                if isinstance(inp, dict):
                    return [
                        e for e in (inp.get("edits") or [])
                        if isinstance(e, str) and e.strip()
                    ]
            return []

    return _LLMProposer()
