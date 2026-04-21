"""Tests for ``dd.forces`` — M7.0.d compositional-role labeling.

Per plan-synthetic-gen.md §5.1 M7.0.d: Claude labels each
``screen_component_instances`` row's compositional role (e.g.
"main-cta in login-form"), Alexander's forces guard. The module
gathers per-instance context, batches rows into a single tool-use
call, and persists the returned flat-string labels.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.forces import (
    BatchForcesResult,
    ForcesContext,
    _TARGETED_TYPES,
    collect_instance_context,
    fetch_labeling_candidates,
    label_instances_batch,
    run_forces_labeling,
)


def _minimal_schema(conn: sqlite3.Connection) -> None:
    """Build the minimum schema forces.py queries against."""
    conn.executescript(
        """
        CREATE TABLE screens (
            id INTEGER PRIMARY KEY,
            file_id TEXT,
            name TEXT,
            screen_type TEXT
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            parent_id INTEGER,
            name TEXT,
            node_type TEXT,
            component_key TEXT
        );
        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            canonical_type TEXT,
            classification_source TEXT,
            consensus_method TEXT,
            compositional_role TEXT
        );
        """
    )
    conn.commit()


def _seed_login_screen(conn: sqlite3.Connection) -> None:
    """Canonical mini-login fixture: a screen with a form whose
    bottom button is the login action + a secondary sign-up link."""
    conn.executescript(
        """
        INSERT INTO screens (id, file_id, name, screen_type)
            VALUES (1, 'f1', 'Login', 'app_screen');
        INSERT INTO nodes
            (id, screen_id, parent_id, name, node_type, component_key)
        VALUES
            (10, 1, NULL, 'LoginScreen', 'FRAME', NULL),
            (11, 1, 10, 'form', 'FRAME', NULL),
            (12, 1, 11, 'email-input', 'INSTANCE', 'ck-input'),
            (13, 1, 11, 'password-input', 'INSTANCE', 'ck-input'),
            (14, 1, 11, 'Sign in', 'INSTANCE', 'ck-btn-primary'),
            (15, 1, 10, 'Sign up', 'INSTANCE', 'ck-btn-text');
        INSERT INTO screen_component_instances
            (id, screen_id, node_id, canonical_type,
             classification_source, consensus_method)
        VALUES
            (100, 1, 12, 'field_input', 'llm', 'unanimous'),
            (101, 1, 13, 'field_input', 'llm', 'unanimous'),
            (102, 1, 14, 'button', 'llm', 'unanimous'),
            (103, 1, 15, 'button', 'llm', 'two_source_unanimous');
        """
    )
    conn.commit()


class TestCollectInstanceContext:
    def test_returns_typed_context_with_parent_and_siblings(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        ctx = collect_instance_context(conn, sci_id=102)
        assert isinstance(ctx, ForcesContext)
        assert ctx.sci_id == 102
        assert ctx.canonical_type == "button"
        assert ctx.node_name == "Sign in"
        assert ctx.parent_name == "form"
        # Siblings within the parent: form has (email, password,
        # Sign in). Exclude self.
        sibling_names = {s["name"] for s in ctx.siblings}
        assert "email-input" in sibling_names
        assert "password-input" in sibling_names
        assert "Sign in" not in sibling_names

    def test_missing_sci_returns_none(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)
        assert collect_instance_context(conn, sci_id=9999) is None


class TestFetchLabelingCandidates:
    def test_targets_load_bearing_types_only(self) -> None:
        """Labeling is scoped to the interesting types — container /
        icon / text / unsure are too generic to benefit from a forces
        label in the initial shipment. Verify the default filter
        reflects that."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        candidates = fetch_labeling_candidates(conn, limit=10)
        # Only the 2 buttons should come back (field_input is
        # targeted too per _TARGETED_TYPES, but the test asserts
        # that general non-targeted types stay out).
        types = {c["canonical_type"] for c in candidates}
        assert types.issubset(_TARGETED_TYPES)
        # Field inputs in the fixture qualify since they're
        # load-bearing.
        assert "button" in types
        assert "field_input" in types

    def test_respects_trust_filter(self) -> None:
        """Only trusted consensus rows (the same set the swap demo
        uses — formal / heuristic / unanimous / two_source_unanimous)
        get labeled. An unsure / three_way_disagreement row would
        have unreliable context."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)
        # Demote one row to `three_way_disagreement`
        conn.execute(
            "UPDATE screen_component_instances SET consensus_method="
            "'three_way_disagreement' WHERE id = 103"
        )
        conn.commit()
        candidates = fetch_labeling_candidates(conn, limit=10)
        ids = {c["id"] for c in candidates}
        assert 103 not in ids

    def test_skips_already_labeled(self) -> None:
        """Incremental labeling — rows with a non-null
        compositional_role stay untouched."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)
        conn.execute(
            "UPDATE screen_component_instances SET compositional_role="
            "'main-cta in login-form' WHERE id = 102"
        )
        conn.commit()
        candidates = fetch_labeling_candidates(conn, limit=10)
        ids = {c["id"] for c in candidates}
        assert 102 not in ids


class TestLabelInstancesBatch:
    def test_happy_path_returns_labels_keyed_on_sci_id(self) -> None:
        """Mock the Anthropic client — assert that the batched tool
        response is parsed into a dict keyed on sci_id.
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        client = MagicMock()
        # Anthropic tool-use response shape. `name` is a special
        # attribute on MagicMock (display name) — must be set
        # explicitly rather than via kwargs.
        tool_block = MagicMock(type="tool_use")
        tool_block.name = "emit_forces_labels"
        tool_block.input = {
            "labels": [
                {
                    "sci_id": 102,
                    "role": "main-cta",
                    "context": "login-form",
                },
                {
                    "sci_id": 103,
                    "role": "secondary-action",
                    "context": "login-screen",
                },
            ]
        }
        response = MagicMock()
        response.content = [tool_block]
        client.messages.create.return_value = response

        contexts = [
            collect_instance_context(conn, 102),
            collect_instance_context(conn, 103),
        ]
        result = label_instances_batch(client, contexts)
        assert isinstance(result, BatchForcesResult)
        assert result.labels[102] == "main-cta in login-form"
        assert result.labels[103] == "secondary-action in login-screen"

    def test_no_tool_call_returns_empty_labels(self) -> None:
        """If the LLM returned only a text block (no tool use), the
        batch returns empty labels rather than raising — caller
        decides whether to retry."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)
        client = MagicMock()
        response = MagicMock()
        response.content = [MagicMock(type="text", text="no tool use")]
        client.messages.create.return_value = response
        ctx = collect_instance_context(conn, 102)
        result = label_instances_batch(client, [ctx])
        assert result.labels == {}
        assert result.missing_count == 1

    def test_ignores_foreign_sci_id_in_llm_response(self) -> None:
        """Defence-in-depth: the tool schema pins ``sci_id`` to an
        enum, but if the LLM emits a foreign id anyway (or future
        SDK behavior shifts), label_instances_batch must drop it
        silently rather than apply it to a non-candidate row."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        client = MagicMock()
        tool_block = MagicMock(type="tool_use")
        tool_block.name = "emit_forces_labels"
        tool_block.input = {"labels": [
            {"sci_id": 9999, "role": "stray", "context": "ghost"},
            {"sci_id": 102, "role": "main-cta",
             "context": "login-form"},
        ]}
        response = MagicMock()
        response.content = [tool_block]
        client.messages.create.return_value = response
        result = label_instances_batch(
            client, [collect_instance_context(conn, 102)],
        )
        assert result.labels == {102: "main-cta in login-form"}
        # The foreign id did not leak into the label map.
        assert 9999 not in result.labels

    def test_sanitises_roles_and_contexts(self) -> None:
        """The LLM can return quoted / leading-@ / whitespacey
        strings. Normalise to kebab-case alphanumerics so downstream
        queries like `WHERE compositional_role LIKE '%main-cta%'`
        stay clean."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        client = MagicMock()
        tool_block = MagicMock(type="tool_use")
        tool_block.name = "emit_forces_labels"
        tool_block.input = {"labels": [
            {"sci_id": 102, "role": "  Main-CTA  ",
             "context": '"login-FORM"'},
        ]}
        response = MagicMock()
        response.content = [tool_block]
        client.messages.create.return_value = response
        result = label_instances_batch(
            client, [collect_instance_context(conn, 102)],
        )
        assert result.labels[102] == "main-cta in login-form"


class TestRunForcesLabeling:
    def test_dry_run_does_not_write_labels(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        summary = run_forces_labeling(
            conn, limit=5, dry_run=True, client=None,
        )
        assert summary.labeled == 0
        assert summary.candidates > 0
        # Column stays NULL
        row = conn.execute(
            "SELECT compositional_role FROM screen_component_instances "
            "WHERE id = 102"
        ).fetchone()
        assert row[0] is None

    def test_per_batch_exception_is_counted_and_loop_continues(
        self,
    ) -> None:
        """A client failure in one batch shouldn't take the whole
        run down. The orchestrator catches broad Exception,
        increments summary.errors, and moves to the next batch.
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        client = MagicMock()
        call_count = {"n": 0}

        def fake_create(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated API failure")
            # Second batch succeeds normally.
            messages = kwargs["messages"]
            user = messages[-1]["content"]
            labels = []
            for sci_id in (100, 101, 102, 103):
                if f"sci_id={sci_id}" in user:
                    labels.append({
                        "sci_id": sci_id,
                        "role": "role", "context": "ctx",
                    })
            tool_block = MagicMock(type="tool_use")
            tool_block.name = "emit_forces_labels"
            tool_block.input = {"labels": labels}
            return MagicMock(content=[tool_block])

        client.messages.create.side_effect = fake_create

        summary = run_forces_labeling(
            conn, limit=10, dry_run=False, client=client,
            batch_size=2,
        )
        # First batch failed → errors=1. Second batch succeeded
        # and labeled 2 rows.
        assert summary.errors == 1
        assert summary.labeled == 2

    def test_live_path_writes_and_is_idempotent(self) -> None:
        """With a mocked client, run_forces_labeling writes the
        returned labels. A second pass on the same DB labels 0 new
        rows (all already labeled)."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema(conn)
        _seed_login_screen(conn)

        client = MagicMock()

        def fake_create(*args, **kwargs):
            messages = kwargs["messages"]
            user = messages[-1]["content"]
            labels = []
            for sci_id in (100, 101, 102, 103):
                if f"sci_id={sci_id}" in user:
                    labels.append({
                        "sci_id": sci_id,
                        "role": f"role-{sci_id}",
                        "context": f"ctx-{sci_id}",
                    })
            tool_block = MagicMock(type="tool_use")
            tool_block.name = "emit_forces_labels"
            tool_block.input = {"labels": labels}
            return MagicMock(content=[tool_block])
        client.messages.create.side_effect = fake_create

        summary1 = run_forces_labeling(
            conn, limit=10, dry_run=False, client=client,
            batch_size=2,
        )
        assert summary1.labeled > 0

        # Every targeted SCI now has a label.
        rows = conn.execute(
            "SELECT id, compositional_role FROM screen_component_instances"
        ).fetchall()
        labeled = [r for r in rows if r["compositional_role"]]
        assert len(labeled) == summary1.labeled

        # Re-run — zero new candidates.
        summary2 = run_forces_labeling(
            conn, limit=10, dry_run=False, client=client,
        )
        assert summary2.candidates == 0
        assert summary2.labeled == 0
