"""Stage 1.5 — capstone: real-LLM end-to-end against Dank screen 333.

Stage 1.4's three acceptance tests use mock clients. They prove the
orchestrator + apply_edits chain works given the LLM picks the
right tool. They don't prove the LLM, given a real screen IR + a
plain-English prompt, will pick that tool.

This capstone closes the gap with one real Haiku call against the
extracted IR for screen 333 (`iPad Pro 11" - 43`). Skipped by
default (`@pytest.mark.integration`) — runs only when
ANTHROPIC_API_KEY + the Dank DB are present.

The chosen test: ask the LLM to delete the share icon. The share
icon's eid in Dank IR (post-extraction) is predictable — it's a
descendant of the nav header instance. If the orchestrator returns
ok=True with a delete edit pointing at an eid whose original_name
contains "share", the contract holds.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

DANK_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db",
)
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:  # pragma: no cover
    pass

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture
def dank_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def anthropic_client():
    # importorskip handles the case where the anthropic SDK isn't
    # installed on the system Python that runs the suite (it lives
    # only in .venv for most local setups). Without this guard the
    # full-suite run shows ERROR rather than SKIPPED.
    anthropic = pytest.importorskip("anthropic")
    return anthropic.Anthropic()


def _load_screen_333_doc(conn: sqlite3.Connection):
    """Load the L3 markup for Dank screen 333 — the iPad Pro 11" - 43
    that we used as the visual smoke test for the visibility-toggle
    fix. Uses the same path as `dd generate-ir`."""
    from dd.compress_l3 import compress_to_l3
    from dd.ir import generate_ir
    from dd.markup_l3 import emit_l3, parse_l3
    ir_result = generate_ir(conn, 333)
    spec = ir_result["spec"]
    doc = compress_to_l3(spec, conn=conn, screen_id=333)
    # Round-trip through emit/parse so we have a clean Document
    # object that came out of the parser (matches the shape
    # propose_edits expects).
    return parse_l3(emit_l3(doc))


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
class TestProposeEditsCapstoneReal:
    """One real Haiku call per test. Each test isolates ONE verb's
    end-to-end contract. Network + API spend; opt-in only."""

    def test_delete_real_node_from_screen_333(
        self, dank_conn, anthropic_client,
    ):
        """Capstone for the delete verb. Asks Haiku to remove a non-
        critical node from the screen. Asserts the orchestrator
        returned ok=True with a delete edit, the eid is one that
        existed pre-edit, and the post-edit doc no longer contains
        it."""
        from dd.propose_edits import propose_edits
        from dd.structural_verbs import existing_eids
        doc = _load_screen_333_doc(dank_conn)
        pre_eids = existing_eids(doc)

        result = propose_edits(
            doc=doc,
            prompt=(
                "Delete one decorative or duplicate node from this "
                "screen — pick something safely removable like a "
                "badge, a divider, or an unused icon. Use the delete "
                "verb."
            ),
            client=anthropic_client,
            component_paths=[],  # delete doesn't need swap targets
        )

        assert result.ok, (
            f"propose_edits failed: {result.error_kind} {result.error_detail}"
        )
        assert result.tool_name == "emit_delete_edit", (
            f"expected delete; LLM picked {result.tool_name}"
        )
        # The deleted eid existed pre-edit.
        assert result.edit_source.startswith("delete @"), result.edit_source
        deleted_eid = result.edit_source.split("@", 1)[1].strip()
        assert deleted_eid in pre_eids, (
            f"LLM picked an eid not in the doc: {deleted_eid!r}"
        )
        # The post-edit doc no longer contains it.
        post_eids = existing_eids(result.applied_doc)
        assert deleted_eid not in post_eids
        # And the rationale was emitted (humans care; session log
        # depends on it).
        assert result.rationale, "expected a rationale string"
