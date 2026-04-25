"""Tests for tools/audit_section_01_extract.py — Phase B Section 1 canonical extraction.

The point of these tests is regressions on the F4 workflow change:
Phase B audits MUST use ``dd extract-plugin``, NOT ``dd extract-supplement``.
Future edits to the module will trip these tests if anyone "helpfully"
reverts to the old supplement command.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.audit_section_01_extract import (
    assert_assets_populated,
    run_section_01_extract,
)


@pytest.mark.unit
class TestPhaseBSectionOneCommands:
    """The substep cmd lists must use extract-plugin, not extract-supplement."""

    def test_uses_extract_plugin_not_supplement(self, tmp_path, monkeypatch):
        captured: list[list[str]] = []

        def fake_run_step(*, section, name, cmd, **kwargs):
            captured.append(cmd)
            return {"exit_code": 0, "elapsed_ms": 1, "command": cmd}

        with patch(
            "tools.audit_section_01_extract.run_step", side_effect=fake_run_step
        ):
            run_section_01_extract(
                file_key="ABC123",
                db_path=str(tmp_path / "fresh.db"),
                bridge_port="9225",
            )

        all_args = [arg for cmd in captured for arg in cmd]
        assert "extract-plugin" in all_args, (
            "Phase B Section 1 must call `dd extract-plugin`. "
            f"Captured commands: {captured}"
        )
        assert "extract-supplement" not in all_args, (
            "F4 fix: Phase B Section 1 must NOT call `dd extract-supplement`. "
            f"Captured commands: {captured}"
        )

    def test_calls_extract_extract_plugin_and_status(self, tmp_path):
        captured_names: list[str] = []

        def fake_run_step(*, section, name, cmd, **kwargs):
            captured_names.append(name)
            return {"exit_code": 0, "elapsed_ms": 1, "command": cmd}

        with patch(
            "tools.audit_section_01_extract.run_step", side_effect=fake_run_step
        ):
            run_section_01_extract(
                file_key="ABC123",
                db_path=str(tmp_path / "fresh.db"),
                bridge_port="9225",
            )

        assert captured_names == ["dd-extract", "dd-extract-plugin", "dd-status"]

    def test_passes_bridge_port_to_extract_plugin(self, tmp_path):
        captured: list[list[str]] = []

        def fake_run_step(*, section, name, cmd, **kwargs):
            captured.append(cmd)
            return {"exit_code": 0, "elapsed_ms": 1, "command": cmd}

        with patch(
            "tools.audit_section_01_extract.run_step", side_effect=fake_run_step
        ):
            run_section_01_extract(
                file_key="ABC123",
                db_path=str(tmp_path / "fresh.db"),
                bridge_port="9999",
            )

        plugin_cmd = next(c for c in captured if "extract-plugin" in c)
        assert "--port" in plugin_cmd
        assert plugin_cmd[plugin_cmd.index("--port") + 1] == "9999"


@pytest.mark.unit
class TestAssertAssetsPopulated:
    """assert_assets_populated raises when the asset store wasn't materialised."""

    def _make_db(self, tmp_path: Path, *, assets_rows: int, ref_rows: int) -> str:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE assets (hash TEXT PRIMARY KEY, kind TEXT)")
        conn.execute(
            "CREATE TABLE node_asset_refs ("
            "  node_id INTEGER, asset_hash TEXT, role TEXT)"
        )
        for i in range(assets_rows):
            conn.execute(
                "INSERT INTO assets (hash, kind) VALUES (?, 'svg_path')",
                (f"hash_{i}",),
            )
        for i in range(ref_rows):
            conn.execute(
                "INSERT INTO node_asset_refs (node_id, asset_hash, role) "
                "VALUES (?, ?, 'icon')",
                (i, f"hash_{i % max(1, assets_rows)}"),
            )
        conn.commit()
        conn.close()
        return str(db_path)

    def test_passes_when_both_tables_populated(self, tmp_path):
        db = self._make_db(tmp_path, assets_rows=5, ref_rows=10)
        counts = assert_assets_populated(db)
        assert counts == {"assets": 5, "node_asset_refs": 10}

    def test_raises_on_empty_assets_table(self, tmp_path):
        db = self._make_db(tmp_path, assets_rows=0, ref_rows=0)
        with pytest.raises(AssertionError, match="assets table is empty"):
            assert_assets_populated(db)

    def test_raises_on_empty_node_asset_refs(self, tmp_path):
        db = self._make_db(tmp_path, assets_rows=5, ref_rows=0)
        with pytest.raises(AssertionError, match="node_asset_refs is empty"):
            assert_assets_populated(db)
