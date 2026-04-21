"""Tests for ``dd.repair_agent`` — M7.5 verifier-as-agent loop.

The repair loop runs ≤N iterations of
apply_edits → verify → fix-propose → append-edits, exiting as
soon as verify reports ``is_ok=True``. Tests operate on a small
synthetic verifier + fix-proposer so the loop can be exercised
without real LLM / DB / plugin bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from dd.boundary import StructuredError
from dd.markup_l3 import parse_l3
from dd.repair_agent import (
    RepairOutcome,
    RepairReport,
    run_repair_loop,
)


def _fixture_doc():
    src = (
        "screen #screen-1 {\n"
        "  frame #frame-1 {\n"
        "    text #title \"old\"\n"
        "    rectangle #badge\n"
        "  }\n"
        "}\n"
    )
    return parse_l3(src)


class _StubVerifier:
    """Verifier-under-test. Each call to ``verify(doc)`` returns
    the next report from the supplied queue."""

    def __init__(self, reports):
        self._reports = list(reports)
        self.calls = 0

    def verify(self, doc):
        self.calls += 1
        if self._reports:
            return self._reports.pop(0)
        return RepairReport(is_ok=True, errors=())


class _StubProposer:
    """Fix-proposer-under-test. Returns a list of L3 edit source
    strings for each call."""

    def __init__(self, suggestions):
        self._queue = list(suggestions)
        self.calls = 0

    def propose(self, errors, doc):
        self.calls += 1
        if self._queue:
            return self._queue.pop(0)
        return []


def test_first_iteration_parity_exits_without_invoking_proposer() -> None:
    doc = _fixture_doc()
    verifier = _StubVerifier([RepairReport(is_ok=True, errors=())])
    proposer = _StubProposer([])
    outcome = run_repair_loop(
        doc=doc, initial_edits=(), verifier=verifier,
        proposer=proposer, max_iterations=3,
    )
    assert isinstance(outcome, RepairOutcome)
    assert outcome.succeeded is True
    assert outcome.iterations == 1
    assert verifier.calls == 1
    assert proposer.calls == 0


def test_converges_after_one_repair() -> None:
    doc = _fixture_doc()
    verifier = _StubVerifier([
        RepairReport(
            is_ok=False,
            errors=(
                StructuredError(
                    kind="KIND_TEXT_STALE", id="title",
                    hint="rewrite title positional to 'new'",
                ),
            ),
        ),
        RepairReport(is_ok=True, errors=()),
    ])
    proposer = _StubProposer([
        ['set @title text="new"'],
    ])
    outcome = run_repair_loop(
        doc=doc, initial_edits=(), verifier=verifier,
        proposer=proposer, max_iterations=3,
    )
    assert outcome.succeeded is True
    assert outcome.iterations == 2
    # Proposer was asked once; verifier ran twice.
    assert proposer.calls == 1
    assert verifier.calls == 2
    # The final doc has the rewritten title.
    final = outcome.final_doc
    title = final.top_level[0].block.statements[0].block.statements[0]
    assert title.head.positional.py == "new"


def test_caps_at_max_iterations_without_parity() -> None:
    """Proposer keeps suggesting useless edits; the loop stops
    after max_iterations and returns succeeded=False."""
    doc = _fixture_doc()
    verifier = _StubVerifier([
        RepairReport(is_ok=False, errors=(
            StructuredError(kind="KIND_OTHER", id="x", hint="nope"),
        )),
    ] * 10)
    proposer = _StubProposer([
        ['set @badge visible=false'],
        ['set @badge visible=true'],
        ['set @badge visible=false'],
    ])
    outcome = run_repair_loop(
        doc=doc, initial_edits=(), verifier=verifier,
        proposer=proposer, max_iterations=3,
    )
    assert outcome.succeeded is False
    assert outcome.iterations == 3
    assert len(outcome.applied_edit_sources) == 3


def test_initial_edits_applied_before_first_verify() -> None:
    """If the caller provides initial_edits, they're applied
    before the first verify call (the repair loop builds ON the
    caller's plan, not instead of it)."""
    doc = _fixture_doc()
    verifier = _StubVerifier([RepairReport(is_ok=True, errors=())])
    proposer = _StubProposer([])
    outcome = run_repair_loop(
        doc=doc,
        initial_edits=('delete @badge',),
        verifier=verifier,
        proposer=proposer,
        max_iterations=3,
    )
    assert outcome.succeeded is True
    # The final doc has the badge removed.
    frame = outcome.final_doc.top_level[0].block.statements[0]
    eids = [
        s.head.eid for s in frame.block.statements if hasattr(s, "head")
    ]
    assert "badge" not in eids


def test_parse_error_in_proposer_output_is_recorded_and_loop_continues() -> None:
    """A corrupt edit source from the proposer doesn't crash the
    loop; it's logged in parse_errors and the loop moves to the
    next iteration (which may succeed with a different
    proposal)."""
    doc = _fixture_doc()
    verifier = _StubVerifier([
        RepairReport(is_ok=False, errors=(
            StructuredError(kind="KIND_OTHER", id="title"),
        )),
        RepairReport(is_ok=True, errors=()),
    ])
    proposer = _StubProposer([
        ['this is not valid dd grammar'],
        ['set @title text="fixed"'],
    ])
    outcome = run_repair_loop(
        doc=doc, initial_edits=(), verifier=verifier,
        proposer=proposer, max_iterations=3,
    )
    assert outcome.succeeded is True
    assert outcome.iterations == 2
    assert len(outcome.parse_errors) == 1


def test_proposer_returning_empty_list_fails_cleanly() -> None:
    """No edit to try → loop exits with succeeded=False;
    iterations still increments to show we attempted."""
    doc = _fixture_doc()
    verifier = _StubVerifier([
        RepairReport(is_ok=False, errors=(
            StructuredError(kind="KIND_OTHER", id="x"),
        )),
    ])
    proposer = _StubProposer([[]])
    outcome = run_repair_loop(
        doc=doc, initial_edits=(), verifier=verifier,
        proposer=proposer, max_iterations=3,
    )
    assert outcome.succeeded is False
    assert outcome.iterations == 1
    assert proposer.calls == 1


def test_initial_edits_parse_error_is_recorded_and_loop_continues() -> None:
    """A corrupt initial-edit source doesn't abort the loop — it's
    recorded in parse_errors and apply_edits proceeds with the
    rest. The loop then proceeds to verify/propose as normal.
    """
    doc = _fixture_doc()
    verifier = _StubVerifier([RepairReport(is_ok=True, errors=())])
    proposer = _StubProposer([])
    outcome = run_repair_loop(
        doc=doc,
        initial_edits=(
            'this is not valid grammar',
            'delete @badge',  # this one should still apply
        ),
        verifier=verifier, proposer=proposer, max_iterations=3,
    )
    assert outcome.succeeded is True
    assert len(outcome.parse_errors) == 1
    assert outcome.parse_errors[0].startswith("initial:")
    # The valid initial edit DID land (badge removed from frame).
    frame = outcome.final_doc.top_level[0].block.statements[0]
    eids = [
        s.head.eid for s in frame.block.statements
        if hasattr(s, "head")
    ]
    assert "badge" not in eids
