"""Tests for the plugin render-toggle client.

Self-hidden nodes (``visible=0``) can't be rendered via Figma REST —
the response is empty. The plugin bridge can temporarily flip
visibility to ``true``, export the screen, then restore the original
flag. This module wraps the bridge call so the bake-off can drop in
a "hidden node rendered in context" path.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from dd.plugin_render import (
    _build_render_script,
    render_screen_with_visible_nodes,
)


class TestBuildRenderScript:
    def test_includes_screen_figma_id(self):
        js = _build_render_script("123:456", ["123:789"], scale=2)
        assert "123:456" in js

    def test_includes_all_hidden_node_ids(self):
        js = _build_render_script(
            "123:456", ["123:700", "123:701", "123:702"], scale=2,
        )
        for nid in ("123:700", "123:701", "123:702"):
            assert nid in js

    def test_empty_hidden_list_still_produces_valid_script(self):
        """No hidden nodes to toggle → just renders the screen as-is.
        Shouldn't blow up when the toggle loop has no targets.
        """
        js = _build_render_script("123:456", [], scale=2)
        assert "123:456" in js
        # Should still include an exportAsync call.
        assert "exportAsync" in js

    def test_includes_restore_block(self):
        """Every render call must have a restore (or equivalent
        try/finally) for visibility state. Checking that the JS
        references the restoration path at all.
        """
        js = _build_render_script("123:456", ["123:700"], scale=2)
        assert "finally" in js or "restore" in js.lower()

    def test_scale_parameter_respected(self):
        js = _build_render_script("123:456", [], scale=4)
        assert "SCALE" in js
        assert "4" in js


class TestRenderScreenWithVisibleNodes:
    def test_returns_png_bytes_on_success(self):
        """Mocked subprocess returns a base64-encoded PNG + __ok=true;
        function decodes and returns the raw bytes.
        """
        dummy_png = b"\x89PNG\r\n\x1a\nfakebytes"
        b64 = base64.b64encode(dummy_png).decode("ascii")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "type": "PROXY_EXECUTE_RESULT",
            "result": {"success": True, "result": {"__ok": True, "b64": b64}},
        })
        mock_result.stderr = ""
        with patch("dd.plugin_render.subprocess.run", return_value=mock_result):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=["1:3"],
            )
        assert out == dummy_png

    def test_returns_none_when_plugin_reports_failure(self):
        """Plugin responded but __ok=false → caller should fall back
        to the next strategy, not raise.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "type": "PROXY_EXECUTE_RESULT",
            "result": {
                "success": True,
                "result": {"__ok": False, "reason": "screen not found"},
            },
        })
        with patch("dd.plugin_render.subprocess.run", return_value=mock_result):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=[],
            )
        assert out is None

    def test_returns_none_when_subprocess_nonzero(self):
        """Node subprocess fails (connection refused, timeout, …) →
        return None so the fallback ladder takes over. No raise.
        ECONNREFUSED is transient so the function retries once; both
        attempts fail here, so the net result is still None.
        """
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "connect ECONNREFUSED"
        with patch(
            "dd.plugin_render.subprocess.run", return_value=mock_result,
        ), patch("dd.plugin_render.time.sleep"):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=[],
            )
        assert out is None

    def test_returns_none_when_node_missing(self):
        """FileNotFoundError (no Node binary) → return None gracefully.
        """
        with patch(
            "dd.plugin_render.subprocess.run",
            side_effect=FileNotFoundError("node not found"),
        ):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=[],
            )
        assert out is None

    def test_retries_once_on_transient_connection_error(self):
        """Bridge sometimes drops the plugin connection mid-run
        ('Unable to establish connection'). A single retry recovers
        without blowing through the fallback cascade.
        """
        dummy_png = b"\x89PNG\r\n\x1a\nfakebytes"
        b64 = base64.b64encode(dummy_png).decode("ascii")

        # First call: bridge connection error. Second call: success.
        first = MagicMock()
        first.returncode = 0
        first.stdout = json.dumps({
            "type": "PROXY_EXECUTE_RESULT",
            "error": (
                "Error: Unable to establish connection to Figma after "
                "10 seconds. Please check your internet connection."
            ),
        })
        second = MagicMock()
        second.returncode = 0
        second.stdout = json.dumps({
            "type": "PROXY_EXECUTE_RESULT",
            "result": {"success": True, "result": {"__ok": True, "b64": b64}},
        })
        with patch(
            "dd.plugin_render.subprocess.run",
            side_effect=[first, second],
        ), patch("dd.plugin_render.time.sleep"):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=[],
            )
        assert out == dummy_png

    def test_no_retry_on_permanent_error(self):
        """A 'screen not found' error is permanent — retrying wastes
        time and doesn't recover. Only transient connection errors
        should trigger a retry.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "type": "PROXY_EXECUTE_RESULT",
            "result": {
                "success": True,
                "result": {"__ok": False, "reason": "screen not found"},
            },
        })
        sleep_mock = MagicMock()
        with patch(
            "dd.plugin_render.subprocess.run", return_value=mock_result,
        ), patch("dd.plugin_render.time.sleep", sleep_mock):
            out = render_screen_with_visible_nodes(
                screen_figma_id="1:2", hidden_node_figma_ids=[],
            )
        assert out is None
        # No retry → sleep never called.
        sleep_mock.assert_not_called()
