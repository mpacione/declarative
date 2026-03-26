"""Tests for dd/cli.py — CLI entrypoint."""

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from dd.cli import main, resolve_token, run_extract


@pytest.mark.unit
class TestResolveToken:
    def test_flag_takes_precedence(self):
        with patch.dict(os.environ, {"FIGMA_ACCESS_TOKEN": "env_token"}):
            assert resolve_token("flag_token") == "flag_token"

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {"FIGMA_ACCESS_TOKEN": "env_token"}):
            assert resolve_token(None) == "env_token"

    def test_missing_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit):
                resolve_token(None)


@pytest.mark.integration
class TestRunExtract:
    def test_extract_creates_db_and_populates(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")

        mock_file_json = {
            "name": "Test File",
            "lastModified": "2025-03-25T00:00:00Z",
            "nodes": {
                "1:1": {
                    "document": {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Home",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                        ],
                    }
                }
            },
        }

        mock_screen_json = {
            "nodes": {
                "100:1": {
                    "document": {
                        "id": "100:1",
                        "name": "Home",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 0, "y": 0, "width": 428, "height": 926
                        },
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 1, "g": 1, "b": 1, "a": 1},
                            }
                        ],
                        "strokes": [],
                        "effects": [],
                        "children": [
                            {
                                "id": "100:2",
                                "name": "Title",
                                "type": "TEXT",
                                "absoluteBoundingBox": {
                                    "x": 16, "y": 20, "width": 200, "height": 24
                                },
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 0, "g": 0, "b": 0, "a": 1},
                                    }
                                ],
                                "strokes": [],
                                "effects": [],
                                "characters": "Home",
                                "style": {
                                    "fontFamily": "Inter",
                                    "fontWeight": 700,
                                    "fontSize": 24,
                                    "textAlignHorizontal": "LEFT",
                                    "letterSpacing": 0,
                                    "lineHeightPx": 32,
                                    "lineHeightPercent": 133,
                                    "lineHeightUnit": "PIXELS",
                                },
                            },
                        ],
                    }
                }
            },
        }

        def mock_request(method, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "/nodes" in url:
                ids = kwargs.get("params", {}).get("ids", "")
                if ids == "1:1":
                    resp.json.return_value = mock_file_json
                else:
                    resp.json.return_value = mock_screen_json
            resp.raise_for_status = MagicMock()
            return resp

        with patch("dd.figma_api.requests.request", side_effect=mock_request):
            run_extract(
                file_key="test-key",
                token="fake-token",
                page_id="1:1",
                db_path=db_path,
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        screens = conn.execute("SELECT COUNT(*) as c FROM screens").fetchone()
        assert screens["c"] == 1

        nodes = conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()
        assert nodes["c"] >= 2

        bindings = conn.execute("SELECT COUNT(*) as c FROM node_token_bindings").fetchone()
        assert bindings["c"] > 0

        conn.close()


@pytest.mark.integration
class TestRunCluster:
    def test_cluster_creates_tokens_from_seeded_db(self, tmp_path):
        from dd.db import init_db
        from dd.extract_bindings import create_bindings_for_screen
        from tests.fixtures import seed_post_extraction
        from dd.cli import run_cluster

        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_post_extraction(conn)
        conn.close()

        run_cluster(db_path=db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tokens = conn.execute("SELECT COUNT(*) as c FROM tokens").fetchone()["c"]
        assert tokens > 0
        conn.close()


@pytest.mark.integration
class TestRunAcceptAll:
    def test_accept_all_changes_status_to_bound(self, tmp_path):
        from dd.db import init_db
        from tests.fixtures import seed_post_extraction
        from dd.cli import run_cluster, run_accept_all

        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_post_extraction(conn)
        conn.close()

        run_cluster(db_path=db_path)
        run_accept_all(db_path=db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        proposed = conn.execute(
            "SELECT COUNT(*) as c FROM node_token_bindings WHERE binding_status = 'proposed'"
        ).fetchone()["c"]
        assert proposed == 0

        bound = conn.execute(
            "SELECT COUNT(*) as c FROM node_token_bindings WHERE binding_status = 'bound'"
        ).fetchone()["c"]
        assert bound > 0
        conn.close()


@pytest.mark.integration
class TestRunValidate:
    def test_validate_reports_results(self, tmp_path, capsys):
        from dd.db import init_db
        from tests.fixtures import seed_post_extraction
        from dd.cli import run_validate

        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_post_extraction(conn)
        conn.close()

        run_validate(db_path=db_path)

        captured = capsys.readouterr()
        assert "Validation" in captured.out or "errors" in captured.out.lower() or "pass" in captured.out.lower()


@pytest.mark.integration
class TestRunExportWithFileId:
    def test_export_css_writes_file(self, tmp_path):
        from dd.db import init_db
        from tests.fixtures import seed_post_extraction
        from dd.cli import run_cluster, run_accept_all, run_export

        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_post_extraction(conn)
        conn.close()

        run_cluster(db_path=db_path)
        run_accept_all(db_path=db_path)

        out_path = str(tmp_path / "tokens.css")
        run_export("css", db_path, out=out_path)

        assert os.path.exists(out_path)
        content = open(out_path).read()
        assert "--" in content

    def test_export_dtcg_writes_valid_json(self, tmp_path):
        from dd.db import init_db
        from tests.fixtures import seed_post_extraction
        from dd.cli import run_cluster, run_accept_all, run_export

        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_post_extraction(conn)
        conn.close()

        run_cluster(db_path=db_path)
        run_accept_all(db_path=db_path)

        out_path = str(tmp_path / "tokens.json")
        run_export("dtcg", db_path, out=out_path)

        assert os.path.exists(out_path)
        data = json.loads(open(out_path).read())
        assert isinstance(data, dict)


@pytest.mark.unit
class TestDbAutoDetect:
    def test_finds_single_db_in_cwd(self, tmp_path, monkeypatch):
        from dd.cli import detect_db_path

        db_file = tmp_path / "myfile.declarative.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)

        assert detect_db_path(None) == "myfile.declarative.db"

    def test_errors_when_no_db_found(self, tmp_path, monkeypatch):
        from dd.cli import detect_db_path

        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            detect_db_path(None)

    def test_explicit_path_takes_precedence(self, tmp_path):
        from dd.cli import detect_db_path

        explicit = str(tmp_path / "explicit.db")
        assert detect_db_path(explicit) == explicit


@pytest.mark.unit
class TestMainArgParsing:
    def test_extract_missing_file_key_exits(self):
        with pytest.raises(SystemExit):
            main(["extract"])

    def test_status_with_nonexistent_db(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            main(["status", "--db-path", str(tmp_path / "nope.db")])
