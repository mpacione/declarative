"""Regression tests for honest help text on commands the audit found drift on.

F5 (2026-04-25): ``dd induce-variants`` help previously claimed "calls
Gemini 3.1 Pro to label each cluster" but the implementation passes an
empty image list so the VLM is never actually invoked. The help text
must honestly describe the v0.1 shell behaviour.

F8 (2026-04-25): ``dd classify --three-source`` help previously read as
if every node gets all three sources voting; in reality only nodes
that formal+heuristic skip fall through to the LLM/Vision tier (6.2%
of nodes on the audit's HGB run). The help text must describe the
cascade.

These tests pin the load-bearing phrases. They will trip if anyone
reverts the help text to the old over-promises.
"""

import subprocess
import sys

import pytest


def _capture_help(args: list[str]) -> str:
    """Run `dd <args> --help` and return stdout. Uses subprocess so we
    don't have to mess with argparse's SystemExit on --help."""
    proc = subprocess.run(
        [sys.executable, "-m", "dd", *args, "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, (
        f"dd {' '.join(args)} --help failed: {proc.stderr}"
    )
    return proc.stdout


def _capture_top_help() -> str:
    """Run `dd --help` and return stdout. The summary line for each
    subcommand appears here."""
    proc = subprocess.run(
        [sys.executable, "-m", "dd", "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, f"dd --help failed: {proc.stderr}"
    return proc.stdout


@pytest.mark.unit
class TestInduceVariantsHelpHonesty:
    """F5: induce-variants help text must reflect v0.1 shell reality.

    Two surfaces, both must be honest:

    1. ``dd --help`` (top-level subcommand summary) — comes from
       ``add_parser(..., help=...)``.
    2. ``dd induce-variants --help`` (subcommand-level full help) —
       comes from ``add_parser(..., description=...)``. argparse does
       NOT fall back from ``help`` to ``description``; if only
       ``help=`` is set, the subcommand's own --help shows ONLY
       ``--db`` with no honesty text. The original F5 fix only set
       ``help=``; this test pins both surfaces so future drift can't
       regress to the help-only state.
    """

    def _induce_block(self) -> str:
        """Slice of `dd --help` covering the induce-variants subcommand
        block (summary wraps over several indented lines)."""
        top = _capture_top_help().lower()
        # The subcommand-list entry is the LAST occurrence of
        # `induce-variants` followed by indented description lines —
        # earlier occurrences are the choices listing.
        marker = "    induce-variants"
        idx = top.find(marker)
        assert idx >= 0, "induce-variants block not found in dd --help"
        rest = top[idx:]
        # The next subcommand is `inspect-experiment`.
        end = rest.find("    inspect-experiment")
        if end < 0:
            end = len(rest)
        return rest[:end]

    def _subcommand_help(self) -> str:
        """Full output of ``dd induce-variants --help``. This exercises
        the ``description=`` path on add_parser, which is what the
        subcommand-level --help actually renders."""
        return _capture_help(["induce-variants"]).lower()

    def test_top_level_summary_signals_placeholder_or_v01_shell(self):
        """The summary shown in `dd --help` must hint at the v0.1-shell
        reality so users don't read it and assume Gemini actually runs."""
        induce_block = self._induce_block()
        assert any(
            phrase in induce_block
            for phrase in ("v0.1 shell", "placeholder", "not yet implemented")
        ), (
            "induce-variants summary in `dd --help` must signal v0.1-shell / "
            "placeholder reality. Got block: " + induce_block
        )

    def test_top_level_summary_does_not_overpromise_gemini(self):
        """The previous summary said 'Induce variant_token_binding rows
        for Mode 3'. New text must not promise Gemini calls."""
        induce_block = self._induce_block()
        assert "calls gemini" not in induce_block, (
            "induce-variants summary must NOT claim it calls Gemini — the "
            "v0.1 shell passes an empty image list so the VLM never runs. "
            "Got block: " + induce_block
        )

    def test_subcommand_help_signals_placeholder_or_v01_shell(self):
        """`dd induce-variants --help` itself must show honest text in
        its description block. argparse renders ``description=`` (NOT
        ``help=``) on the subcommand-level --help; without
        ``description=`` the user only sees ``--db`` with no warning
        that Gemini isn't actually called."""
        sub = self._subcommand_help()
        assert any(
            phrase in sub
            for phrase in ("v0.1 shell", "placeholder", "not yet implemented")
        ), (
            "`dd induce-variants --help` must signal v0.1-shell / "
            "placeholder reality in its description (set "
            "`description=` on add_parser). Got: " + sub
        )

    def test_subcommand_help_does_not_overpromise_gemini(self):
        """The full description on `dd induce-variants --help` must
        not promise Gemini is called when in v0.1 it isn't."""
        sub = self._subcommand_help()
        assert "calls gemini" not in sub, (
            "`dd induce-variants --help` must NOT claim it calls Gemini "
            "— the v0.1 shell passes an empty image list so the VLM "
            "never runs. Got: " + sub
        )


@pytest.mark.unit
class TestClassifyThreeSourceHelpHonesty:
    """F8: --three-source help text must describe cascade behaviour."""

    def _three_source_help(self) -> str:
        full = _capture_help(["classify"]).lower()
        # `--three-source` first appears in the usage line. Skip past
        # the usage block and look in the options block for the
        # description that follows the flag.
        options_idx = full.find("options:")
        assert options_idx >= 0, "options: header missing in classify --help"
        opts = full[options_idx:]
        marker = "--three-source"
        idx = opts.find(marker)
        assert idx >= 0, "--three-source flag not present in classify options"
        rest = opts[idx:]
        # The next flag in the parser is --classifier-v2.
        end = rest.find("--classifier-v2")
        if end < 0:
            end = len(rest)
        return rest[:end]

    def test_help_describes_cascade_nature(self):
        """The help text MUST mention the cascade behaviour — that
        formal/heuristic catch most nodes and only the remainder
        reaches LLM/Vision."""
        help_text = self._three_source_help()
        cascade_signals = ("fall through", "falls through", "cascade", "skip")
        assert any(signal in help_text for signal in cascade_signals), (
            "--three-source help must describe the cascade (formal+heuristic "
            "first, only unclassified nodes reach LLM/Vision). Got: "
            + help_text
        )

    def test_help_does_not_claim_all_nodes_get_three_verdicts(self):
        """Old text said 'on the same LLM candidate set' which read as
        'every node gets three verdicts'. New text must NOT claim that."""
        help_text = self._three_source_help()
        assert "on the same llm candidate set" not in help_text, (
            "--three-source help previously read as if every node gets all "
            "three sources voting. The reality is a cascade: only nodes "
            "formal+heuristic skip reach LLM/Vision. Got: " + help_text
        )
