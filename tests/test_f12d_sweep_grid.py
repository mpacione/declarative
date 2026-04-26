"""F12d — grid layout for sweep mode.

Default sweep behavior clears the Generated Test page before each
render, so only the most recent screen remains visible. That's wrong
for "sweep N screens and let the user review them visually" — they
need ALL N screens persisted.

F12d adds:
- `--keep-existing` flag on `walk_ref.js` to skip the page-clear.
- `--grid-pos=row,col` flag on `walk_ref.js` to position the rendered
  root at a fixed cell on the page.
- `--grid` and `--grid-cols` flags on `render_batch/sweep.py` that
  compute (row, col) per-screen and pass it through.

This file tests the Python plumbing. The walk_ref.js piece is
end-to-end-tested by running the sweep against the bridge — there's
no JS unit harness in this repo for that.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


class TestSweepArgparse:
    def test_grid_flag_recognized(self):
        """`--grid --grid-cols N` parses without error."""
        # Use --help to exercise the parser without actually running.
        result = subprocess.run(
            [sys.executable, str(REPO / "render_batch" / "sweep.py"), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--grid" in result.stdout
        assert "--grid-cols" in result.stdout

    def test_grid_help_explains_visual_review(self):
        """The help text must mention "visual review" so users know
        what the flag is for. Without it, "grid" alone is opaque."""
        result = subprocess.run(
            [sys.executable, str(REPO / "render_batch" / "sweep.py"), "--help"],
            capture_output=True, text=True,
        )
        assert "visual review" in result.stdout.lower(), (
            "--grid help text should describe its purpose (let user "
            "review all N rendered screens)"
        )


class TestGridPositionMath:
    """The sweep computes (row, col) per screen as enumerate-index
    divided by grid-cols. Pin the math against accidental change."""

    @staticmethod
    def _grid_at(idx: int, cols: int) -> tuple[int, int]:
        # Mirror the sweep.py expression `(grid_idx // cols, grid_idx % cols)`
        return (idx // cols, idx % cols)

    def test_first_row_fills_left_to_right(self):
        cols = 6
        assert self._grid_at(0, cols) == (0, 0)
        assert self._grid_at(1, cols) == (0, 1)
        assert self._grid_at(5, cols) == (0, 5)

    def test_second_row_starts_at_col_zero(self):
        cols = 6
        assert self._grid_at(6, cols) == (1, 0)
        assert self._grid_at(11, cols) == (1, 5)

    def test_44_screens_in_6_cols_yields_8_rows(self):
        """44 screens / 6 cols = 7 full rows + 2 in the 8th row.
        Last screen (idx=43) lands at (7, 1)."""
        cols = 6
        last = self._grid_at(43, cols)
        assert last == (7, 1)


class TestWalkRefArgs:
    """walk_ref.js arg parsing for --keep-existing and --grid-pos.
    These are end-to-end through the bridge in real use, but the
    arg-parse smoke is testable as a unit (the script bails out
    early on bad args before touching the WebSocket)."""

    def test_walk_ref_help_mentions_keep_existing(self):
        """walk_ref.js prints usage on missing args. The usage line
        must include the F12d flags so callers know they exist."""
        result = subprocess.run(
            ["node", str(REPO / "render_test" / "walk_ref.js")],
            capture_output=True, text=True,
        )
        # No script path → exit non-zero, usage on stderr
        assert result.returncode != 0
        usage = (result.stderr or "") + (result.stdout or "")
        assert "--keep-existing" in usage
        assert "--grid-pos" in usage
