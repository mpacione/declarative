"""Plan B Stage 2 pilot — archetype `.dd` skeletons parse cleanly.

First archetype migrated from `.json` to `.dd`: `login.dd`. The
remaining 11 archetypes stay on JSON until their migrations land.

This test gates future migrations: any new `.dd` file under
`dd/archetype_library/skeletons/` must parse without errors,
round-trip through `emit_l3 → parse_l3` with structural equality,
and use only registered type keywords (no hard-fail on unknown
names — the parser MUST NOT hard-fail per grammar §2.7, but the
current impl does; pilot uses registered types only).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from dd.markup_l3 import emit_l3, parse_l3


SKELETONS_DIR = (
    Path(__file__).resolve().parent.parent
    / "dd" / "archetype_library" / "skeletons"
)


def _dd_files() -> list[Path]:
    if not SKELETONS_DIR.exists():
        return []
    return sorted(SKELETONS_DIR.glob("*.dd"))


@pytest.mark.parametrize(
    "path",
    _dd_files(),
    ids=lambda p: p.name,
)
def test_archetype_skeleton_parses(path: Path) -> None:
    """Every `.dd` skeleton must parse without raising."""
    src = path.read_text()
    doc = parse_l3(src)
    assert len(doc.top_level) >= 1, (
        f"{path.name}: parsed doc has no top-level items"
    )


@pytest.mark.parametrize(
    "path",
    _dd_files(),
    ids=lambda p: p.name,
)
def test_archetype_skeleton_round_trips(path: Path) -> None:
    """`parse_l3(emit_l3(parse_l3(src))) == parse_l3(src)` — the
    canonical round-trip invariant for all `.dd` documents."""
    src = path.read_text()
    doc = parse_l3(src)
    # Warnings don't round-trip through markup (they're compile-time
    # diagnostics, not source-level content).
    doc_stripped = replace(doc, warnings=())
    doc2 = parse_l3(emit_l3(doc))
    assert doc_stripped == doc2, (
        f"{path.name}: compress→emit→parse not idempotent"
    )


def test_login_archetype_structure() -> None:
    """`login.dd` — the Stage 2 pilot — has a `define login`
    declaration with the expected 3 top-level children (header,
    card, button)."""
    from dd.markup_l3 import Define, Node
    src = (SKELETONS_DIR / "login.dd").read_text()
    doc = parse_l3(src)
    assert len(doc.top_level) == 1
    define = doc.top_level[0]
    assert isinstance(define, Define)
    assert define.name == "login"
    assert define.body is not None
    # Top-level structure: header / card / button.
    top_level_nodes = [
        s for s in define.body.statements if isinstance(s, Node)
    ]
    assert len(top_level_nodes) == 3
    assert top_level_nodes[0].head.type_or_path == "header"
    assert top_level_nodes[1].head.type_or_path == "card"
    assert top_level_nodes[2].head.type_or_path == "button"
