"""C5 — project_vocabulary module + --use-project-vocab CLI flag.

Per docs/plan-synth-gen-demo.md C5: snap Mode 2 emissions to project-
canonical literal values so demo variants look native to the source
design system.

Tests verify:
  - Vocabulary extraction returns top-K per dimension on the real
    Dank fresh DB.
  - Chromatic vs neutral split via OKLCH chroma threshold.
  - Snap rules apply correct thresholds (color ΔE, radius abs/rel,
    spacing abs/rel, fontSize abs/rel).
  - Token references (strings starting with `{`) are skipped.
  - SnapReport counts match the actual number of snaps.
  - The --use-project-vocab CLI flag is wired on design / resume /
    lateral parsers.
  - snap_ir_to_vocabulary does not mutate input.
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from dd.project_vocabulary import (
    ProjectVocabulary,
    SnapReport,
    build_project_vocabulary,
    snap_ir_to_vocabulary,
)


# --------------------------------------------------------------------------- #
# Vocabulary extraction                                                       #
# --------------------------------------------------------------------------- #


_DANK_DB = "/tmp/dank-fresh-20260427.db"


@pytest.fixture(scope="module")
def dank_conn():
    """Connection to the fresh Dank DB. Skips if the test fixture
    isn't present on this machine."""
    if not Path(_DANK_DB).exists():
        pytest.skip(f"{_DANK_DB} not present; skipping live-DB tests.")
    conn = sqlite3.connect(_DANK_DB)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestBuildVocabularyFromDank:
    """Live-DB extraction returns non-empty top-K within caps."""

    def test_build_project_vocabulary_from_dank(self, dank_conn):
        vocab = build_project_vocabulary(dank_conn, file_id=1)

        assert isinstance(vocab, ProjectVocabulary)
        assert len(vocab.chromatic_fills) > 0
        assert len(vocab.neutral_fills) > 0
        assert len(vocab.radii) > 0
        assert len(vocab.spacings) > 0
        assert len(vocab.font_sizes) > 0

        # Caps from Codex round-13 lock.
        assert len(vocab.chromatic_fills) <= 16
        assert len(vocab.neutral_fills) <= 8
        assert len(vocab.radii) <= 8
        assert len(vocab.spacings) <= 12
        assert len(vocab.font_sizes) <= 8

        # All hex strings are normalized (uppercase, # prefix, 6 digits).
        for hex_str in vocab.chromatic_fills + vocab.neutral_fills:
            assert hex_str.startswith("#"), hex_str
            assert len(hex_str) == 7, hex_str
            assert hex_str.upper() == hex_str, hex_str

    def test_invalid_file_id_raises(self, dank_conn):
        """A bogus file_id must raise ValueError loudly — silent
        empty-vocab would hide a misconfigured demo."""
        with pytest.raises(ValueError, match="file_id"):
            build_project_vocabulary(dank_conn, file_id=99999)


class TestChromaticNeutralSplit:
    """Synthetic DB rows: gray/white/black land in neutrals; brand
    colors land in chromatic."""

    @pytest.fixture
    def synth_conn(self, tmp_path):
        """Build a tiny in-memory project DB with hand-picked fills."""
        db_path = tmp_path / "synth.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE screens (id INTEGER PRIMARY KEY, file_id INTEGER);
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                screen_id INTEGER,
                fills TEXT,
                corner_radius TEXT,
                font_size REAL
            );
            CREATE TABLE node_token_bindings (
                id INTEGER PRIMARY KEY,
                node_id INTEGER,
                property TEXT,
                resolved_value TEXT,
                token_name TEXT,
                binding_status TEXT
            );
            INSERT INTO files (id, name) VALUES (1, 'synth');
            INSERT INTO screens (id, file_id) VALUES (1, 1);
            """
        )
        # Insert distinct fills: 5x neutral grey, 5x white, 5x black,
        # 10x brand purple, 10x brand red.
        for i in range(5):
            conn.execute(
                "INSERT INTO nodes (screen_id, fills) VALUES (1, ?)",
                ('[{"type":"SOLID","color":{"r":0.5,"g":0.5,"b":0.5,"a":1.0}}]',),
            )
        for i in range(5):
            conn.execute(
                "INSERT INTO nodes (screen_id, fills) VALUES (1, ?)",
                ('[{"type":"SOLID","color":{"r":1.0,"g":1.0,"b":1.0,"a":1.0}}]',),
            )
        for i in range(5):
            conn.execute(
                "INSERT INTO nodes (screen_id, fills) VALUES (1, ?)",
                ('[{"type":"SOLID","color":{"r":0.0,"g":0.0,"b":0.0,"a":1.0}}]',),
            )
        # Brand purple #6F40FF (R=0.435 G=0.251 B=1.0).
        for i in range(10):
            conn.execute(
                "INSERT INTO nodes (screen_id, fills) VALUES (1, ?)",
                ('[{"type":"SOLID","color":{"r":0.435,"g":0.251,"b":1.0,"a":1.0}}]',),
            )
        # Brand red #FF1515.
        for i in range(10):
            conn.execute(
                "INSERT INTO nodes (screen_id, fills) VALUES (1, ?)",
                ('[{"type":"SOLID","color":{"r":1.0,"g":0.082,"b":0.082,"a":1.0}}]',),
            )
        conn.commit()
        yield conn
        conn.close()

    def test_chromatic_neutral_split(self, synth_conn):
        vocab = build_project_vocabulary(synth_conn, file_id=1)

        # Neutrals: gray/white/black should all land here.
        # Their hex strings are #808080, #FFFFFF, #000000.
        neutrals_set = set(vocab.neutral_fills)
        assert "#808080" in neutrals_set
        assert "#FFFFFF" in neutrals_set
        assert "#000000" in neutrals_set

        # Chromatic: brand red and purple should land here.
        chromatic_set = set(vocab.chromatic_fills)
        # Brand red is exactly #FF1515.
        assert "#FF1515" in chromatic_set


# --------------------------------------------------------------------------- #
# Snap thresholds                                                              #
# --------------------------------------------------------------------------- #


def _vocab(
    chromatic=("#6366F1", "#FF1515"),
    neutral=("#000000", "#FFFFFF", "#808080"),
    radii=(4.0, 8.0, 16.0, 24.0),
    spacings=(4.0, 8.0, 12.0, 16.0, 24.0),
    font_sizes=(12.0, 14.0, 16.0, 18.0, 24.0),
):
    """Test-friendly vocab factory with sensible defaults."""
    return ProjectVocabulary(
        chromatic_fills=tuple(chromatic),
        neutral_fills=tuple(neutral),
        radii=tuple(radii),
        spacings=tuple(spacings),
        font_sizes=tuple(font_sizes),
    )


class TestSnapColors:
    """Color snapping — chromatic vs neutral, threshold rules."""

    def test_snap_color_within_threshold(self):
        """A color near #6366F1 (the canonical chromatic) snaps to it."""
        vocab = _vocab(chromatic=("#6366F1",), neutral=("#000000",))
        # #6470F1 is a few RGB points off — small ΔE.
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [{"type": "solid", "color": "#6470F1"}],
                    },
                },
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        snapped_color = new_spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
        assert snapped_color == "#6366F1"
        assert report.fills_snapped == 1

    def test_snap_color_outside_threshold_unchanged(self):
        """A color very far from any vocab entry is NOT snapped."""
        vocab = _vocab(chromatic=("#FF0000",), neutral=("#000000",))
        # #00FF00 (pure green) — far from #FF0000 in OKLCH.
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [{"type": "solid", "color": "#00FF00"}],
                    },
                },
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        unchanged_color = new_spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
        assert unchanged_color == "#00FF00"
        assert report.fills_snapped == 0

    def test_snap_color_token_ref_skipped(self):
        """Token references (`{color.brand.primary}`) are not snapped."""
        vocab = _vocab()
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [
                            {"type": "solid", "color": "{color.brand.primary}"},
                        ],
                    },
                },
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        unchanged = new_spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
        assert unchanged == "{color.brand.primary}"
        assert report.fills_snapped == 0

    def test_snap_skips_gradient_fills(self):
        """Gradients are not snapped — only SOLID fills are touched."""
        vocab = _vocab()
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [
                            {
                                "type": "gradient-linear",
                                "stops": [
                                    {"color": "#000000", "position": 0.0},
                                    {"color": "#FFFFFF", "position": 1.0},
                                ],
                            },
                        ],
                    },
                },
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        gradient = new_spec["elements"]["btn-1"]["visual"]["fills"][0]
        assert gradient["type"] == "gradient-linear"
        assert report.fills_snapped == 0


class TestSnapNumerics:
    """Radius / spacing / fontSize threshold rules."""

    def test_snap_radius_within_abs_threshold(self):
        """cornerRadius=14 with vocab containing 16 → snaps (abs Δ=2)."""
        vocab = _vocab(radii=(16.0,))
        spec = {
            "elements": {
                "card-1": {"visual": {"cornerRadius": 14.0}},
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec["elements"]["card-1"]["visual"]["cornerRadius"] == 16.0
        assert report.radii_snapped == 1

    def test_snap_radius_outside_abs_and_rel_threshold(self):
        """cornerRadius=100 with vocab containing 16 → not snapped
        (abs Δ=84 > 2; rel Δ=84% > 20%)."""
        vocab = _vocab(radii=(16.0,))
        spec = {
            "elements": {
                "card-1": {"visual": {"cornerRadius": 100.0}},
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec["elements"]["card-1"]["visual"]["cornerRadius"] == 100.0
        assert report.radii_snapped == 0

    def test_snap_spacing_via_padding(self):
        """layout.padding side values get snapped."""
        vocab = _vocab(spacings=(8.0, 16.0))
        spec = {
            "elements": {
                "frame-1": {
                    "layout": {
                        "padding": {
                            "top": 9.0,    # snaps to 8
                            "right": 17.0, # snaps to 16
                            "bottom": 8.0, # already canonical, no change
                            "left": 100.0, # too far, no snap
                        },
                    },
                },
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        padding = new_spec["elements"]["frame-1"]["layout"]["padding"]
        assert padding["top"] == 8.0
        assert padding["right"] == 16.0
        assert padding["bottom"] == 8.0
        assert padding["left"] == 100.0
        # 2 changes: top and right.
        assert report.spacing_snapped == 2

    def test_snap_spacing_via_gap(self):
        """layout.gap (itemSpacing) gets snapped."""
        vocab = _vocab(spacings=(12.0,))
        spec = {
            "elements": {
                "row-1": {"layout": {"gap": 13.0}},
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec["elements"]["row-1"]["layout"]["gap"] == 12.0
        assert report.spacing_snapped == 1

    def test_snap_font_size_via_visual(self):
        """visual.fontSize gets snapped (LLM head-emitted form)."""
        vocab = _vocab(font_sizes=(16.0,))
        spec = {
            "elements": {
                "txt-1": {"visual": {"fontSize": 17.0}},
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec["elements"]["txt-1"]["visual"]["fontSize"] == 16.0
        assert report.font_size_snapped == 1


# --------------------------------------------------------------------------- #
# Report counts + immutability                                                 #
# --------------------------------------------------------------------------- #


class TestSnapReportAndImmutability:
    def test_snap_report_counts_match(self):
        """Mixed snaps across dimensions: report tallies are correct."""
        vocab = _vocab(
            chromatic=("#6366F1",),
            radii=(8.0, 16.0),
            spacings=(12.0,),
            font_sizes=(16.0,),
        )
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [
                            {"type": "solid", "color": "#6470F1"},  # → snap
                        ],
                        "cornerRadius": 9.0,                          # → 8
                    },
                    "layout": {"gap": 13.0},                          # → 12
                },
                "btn-2": {
                    "visual": {
                        "fills": [
                            {"type": "solid", "color": "#6271F0"},  # → snap
                        ],
                        "cornerRadius": 17.0,                         # → 16
                        "fontSize": 17.0,                             # → 16
                    },
                },
            },
        }
        _, report = snap_ir_to_vocabulary(spec, vocab)
        assert report.fills_snapped == 2
        assert report.radii_snapped == 2
        assert report.spacing_snapped == 1
        assert report.font_size_snapped == 1
        assert report.total() == 6

    def test_snap_does_not_mutate_input(self):
        """The original spec dict is untouched after snap_ir_to_vocabulary."""
        vocab = _vocab(chromatic=("#6366F1",))
        spec = {
            "elements": {
                "btn-1": {
                    "visual": {
                        "fills": [{"type": "solid", "color": "#6470F1"}],
                    },
                },
            },
        }
        # Capture pre-snap state.
        original_color = spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
        original_id = id(spec["elements"]["btn-1"]["visual"]["fills"][0])

        new_spec, _ = snap_ir_to_vocabulary(spec, vocab)

        # Original spec unchanged.
        assert spec["elements"]["btn-1"]["visual"]["fills"][0]["color"] == original_color
        assert id(spec["elements"]["btn-1"]["visual"]["fills"][0]) == original_id
        # New spec is distinct.
        assert new_spec is not spec
        assert (
            new_spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
            != spec["elements"]["btn-1"]["visual"]["fills"][0]["color"]
        )

    def test_snap_empty_spec_yields_zero_report(self):
        vocab = _vocab()
        spec = {"elements": {}}
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec == {"elements": {}}
        assert report.total() == 0

    def test_snap_handles_missing_visual_layout_keys(self):
        """Elements without visual / layout / style sections are
        handled defensively — no crash, no change."""
        vocab = _vocab()
        spec = {
            "elements": {
                "frame-1": {"type": "frame"},  # no visual / layout / style
            },
        }
        new_spec, report = snap_ir_to_vocabulary(spec, vocab)
        assert new_spec["elements"]["frame-1"] == {"type": "frame"}
        assert report.total() == 0


# --------------------------------------------------------------------------- #
# CLI flag wiring                                                             #
# --------------------------------------------------------------------------- #


class TestUseProjectVocabFlagInHelp:
    """The --use-project-vocab flag is wired in argparse on all three
    `dd design` parsers (top-level + resume + lateral)."""

    def test_design_help_mentions_use_project_vocab(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--use-project-vocab" in result.stdout

    def test_design_resume_help_mentions_use_project_vocab(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "resume", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--use-project-vocab" in result.stdout

    def test_design_lateral_help_mentions_use_project_vocab(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "lateral", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--use-project-vocab" in result.stdout

    def test_run_design_brief_default_false(self):
        from dd.cli import _run_design_brief
        import inspect

        sig = inspect.signature(_run_design_brief)
        assert sig.parameters["use_project_vocab"].default is False

    def test_run_design_resume_default_false(self):
        from dd.cli import _run_design_resume
        import inspect

        sig = inspect.signature(_run_design_resume)
        assert sig.parameters["use_project_vocab"].default is False

    def test_run_design_lateral_default_false(self):
        from dd.cli import _run_design_lateral
        import inspect

        sig = inspect.signature(_run_design_lateral)
        assert sig.parameters["use_project_vocab"].default is False

    def test_render_session_to_figma_default_false(self):
        from dd.cli import _render_session_to_figma
        import inspect

        sig = inspect.signature(_render_session_to_figma)
        assert sig.parameters["use_project_vocab"].default is False
