"""F13b — text nodes in non-autolayout parents get resize() + textAutoResize.

Phase D visual-diff exposed: the letter body text on HGB Customer
Complete Info Desktop rendered 1319px wide instead of source 560px,
and `textAutoResize` was the default `WIDTH_AND_HEIGHT` instead of the
source's `HEIGHT`. Layout consequence cascaded into wrapped lines and
shifted downstream content.

Root cause:
- `_emit_phase1` skips `_emit_layout` for text nodes (line 855), so
  no `resize()` is emitted for text in Phase 1.
- `_emit_phase3` (Phase 2 in plain English — post-appendChild) had a
  resize block at line 1597 for non-autolayout-parent nodes, but it
  read `widthPixels`/`heightPixels` ONLY. Text-node IR uses literal
  numeric `width: 560.0, height: 345.0` (no `*Pixels` keys), so the
  lookup missed and no resize was emitted at all.
- Even if a resize were emitted, `textAutoResize` defaults to
  `WIDTH_AND_HEIGHT` and would re-expand the width when characters
  are set. Renderer never emitted `textAutoResize` to lock the mode.

F13b shipping the Codex-specified shape:
- `_emit_phase3` reads the canonical RESOLVED element via
  `resolve_element` (matches Phase 1 line 694) so AST head + spec +
  db_visuals merge correctly here too.
- Sizing lookup falls back to numeric `width`/`height` when
  `widthPixels`/`heightPixels` absent — matches `_emit_layout`'s
  tolerant lookup at `dd/renderers/figma.py:2255-2262`.
- For text nodes, after `resize()` emit `textAutoResize = <stored>`
  to lock the source mode — but ONLY when stored mode is NOT
  `WIDTH_AND_HEIGHT` (Codex catch: emitting WIDTH_AND_HEIGHT after
  resize re-enables natural-width and undoes the lock).
- Same `textAutoResize` lock added to autolayout-parent path at
  Phase 2 line 1478 (mirrors OLD path's `text_autoresize_deferred`
  pattern).

Order is `appendChild → characters → layoutSizing/resize →
textAutoResize` per `feedback_text_layout_invariants.md`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / "audit" / "20260425-1725-phaseD-fullsweep" / "audit-fresh.declarative.db"


def _has_audit_db() -> bool:
    return DB_PATH.exists()


def _generate(screen_id: int) -> str:
    """Run `dd generate` and return the script."""
    result = subprocess.run(
        [
            ".venv/bin/python", "-m", "dd", "generate",
            "--db", str(DB_PATH), "--screen", str(screen_id),
        ],
        cwd=str(REPO),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"generate failed: {result.stderr}"
    return result.stdout


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestNonAutolayoutTextResize:
    """Text nodes in non-autolayout parents must get resize() emitted
    so they don't default to WIDTH_AND_HEIGHT natural-width."""

    def test_letter_body_text_gets_resize(self):
        """HGB Customer Complete Info Desktop letter body — exact case
        the user reported. n4 corresponds to heading-1 (letter body)
        whose source is 560×345 in a non-autolayout screen FRAME."""
        script = _generate(1)
        # The resize must use the source dimensions, not n4.width
        # (which would be the default 100 from createText()).
        assert "n4.resize(560, 345)" in script, (
            "non-autolayout text node must emit resize() with stored "
            "dimensions; without it the text grows to natural single-"
            "line width (Bug B)"
        )

    def test_letter_body_text_gets_textautoresize_lock(self):
        """The HEIGHT mode must be emitted to lock the resized width."""
        script = _generate(1)
        assert 'n4.textAutoResize = "HEIGHT"' in script, (
            "text node with stored HEIGHT mode must lock textAutoResize "
            "after resize; otherwise default WIDTH_AND_HEIGHT re-expands "
            "the width when characters are set"
        )

    def test_text_resize_order_is_characters_resize_textautoresize(self):
        """Order is critical per feedback_text_layout_invariants.md:
        characters → resize → textAutoResize. Setting textAutoResize=
        HEIGHT before characters wraps at 0px width."""
        script = _generate(1)
        chars_idx = script.find("n4.characters =")
        resize_idx = script.find("n4.resize(560, 345)")
        autoresize_idx = script.find('n4.textAutoResize = "HEIGHT"')
        assert 0 <= chars_idx < resize_idx < autoresize_idx, (
            f"order must be characters → resize → textAutoResize; got "
            f"chars@{chars_idx}, resize@{resize_idx}, autoresize@{autoresize_idx}"
        )


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestNonAutolayoutFrameResize:
    """The same non-autolayout parent + numeric-width fallback also
    fixes Bug C (the bordered table on HGB Transactions Selected)."""

    def test_table_with_border_gets_resize_with_widthPixels(self):
        """Bug C: bordered table source 1400×950 was rendered 100×950
        because Phase 3 read spec_elements directly (which has only
        `width: hug` not `widthPixels`). F13a fixed the merge;
        F13b's resolve_element call at Phase 3 makes the resolved
        widthPixels reach the lookup."""
        script = _generate(20)
        assert "n3.resize(1400.0, 950.0)" in script, (
            "non-autolayout parent table must emit resize() with "
            "stored widthPixels/heightPixels (Bug C)"
        )

    def test_table_with_border_does_not_get_textautoresize(self):
        """Non-text nodes must NOT get textAutoResize emitted —
        that property is text-only and would throw 'object is not
        extensible' on a FRAME."""
        script = _generate(20)
        # Walk lines that contain n3 and assert none mention
        # textAutoResize (n3 is the table, a FRAME).
        lines_with_n3 = [
            line for line in script.split("\n") if "n3." in line
        ]
        n3_text_resize = [
            line for line in lines_with_n3 if "textAutoResize" in line
        ]
        assert n3_text_resize == [], (
            "non-text node must not emit textAutoResize; that property "
            f"is TEXT-only. Got: {n3_text_resize!r}"
        )


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestF13bDoesNotEmitWidthAndHeightLock:
    """Codex F13b spec: `textAutoResize = "WIDTH_AND_HEIGHT"` must NOT
    be emitted after resize — that mode is the default and re-emitting
    it would re-enable natural-width behavior, undoing the lock."""

    def test_no_width_and_height_lock_emitted_anywhere(self):
        """Sweep multiple screens; assert WIDTH_AND_HEIGHT never
        appears as a textAutoResize value being set after resize.
        (It may legitimately appear as a default value being
        overridden FROM, but the renderer should never set TO it.)"""
        for sid in (1, 20, 22):
            script = _generate(sid)
            # Search for the literal `textAutoResize = "WIDTH_AND_HEIGHT"`
            # assignment.
            assert (
                'textAutoResize = "WIDTH_AND_HEIGHT"' not in script
            ), (
                f"screen {sid}: emitter should never set textAutoResize "
                "to WIDTH_AND_HEIGHT — that's the default and re-emitting "
                "it after resize re-enables natural-width behavior"
            )
