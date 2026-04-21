"""Unit tests for dd.structural_verbs helpers (M7.4 scaffolding)."""

from __future__ import annotations

import pytest

from dd.markup_l3 import apply_edits, parse_l3
from dd.structural_verbs import (
    collect_insert_candidates,
    collect_move_candidates,
    collect_parent_candidates,
    collect_removable_candidates,
    unique_eids,
    verify_appended,
    verify_deleted,
    verify_inserted,
    verify_moved,
)


def _fixture_doc():
    src = (
        "screen #screen-1 {\n"
        "  frame #frame-1 {\n"
        "    text #title \"hello\"\n"
        "    text #subtitle \"sub\"\n"
        "    rectangle #badge\n"
        "  }\n"
        "  frame #archive\n"
        "}\n"
    )
    return parse_l3(src)


def test_unique_eids_returns_eids_appearing_exactly_once() -> None:
    doc = _fixture_doc()
    eids = set(unique_eids(doc))
    # All eids are globally unique in this fixture.
    assert eids == {
        "screen-1", "frame-1", "title", "subtitle", "badge",
        "archive",
    }


def test_collect_removable_excludes_root() -> None:
    doc = _fixture_doc()
    out = collect_removable_candidates(doc)
    eids = {c["eid"] for c in out}
    assert "screen-1" not in eids
    # frame-1 / archive / title / subtitle / badge all removable.
    assert eids == {"frame-1", "archive", "title", "subtitle", "badge"}


def test_collect_parent_finds_nodes_with_blocks() -> None:
    doc = _fixture_doc()
    parents = collect_parent_candidates(doc)
    eids = {p["eid"] for p in parents}
    # screen-1 + frame-1 both have blocks; archive is an empty
    # container-type so it's allowed too.
    assert {"screen-1", "frame-1", "archive"}.issubset(eids)


def test_collect_insert_pairs_are_parent_anchor() -> None:
    doc = _fixture_doc()
    pairs = collect_insert_candidates(doc)
    assert any(
        p["parent_eid"] == "frame-1" and p["anchor_eid"] == "title"
        for p in pairs
    )


def test_collect_move_pairs_target_and_dest_differ() -> None:
    doc = _fixture_doc()
    pairs = collect_move_candidates(doc)
    assert all(p["target_eid"] != p["dest_eid"] for p in pairs)


def test_verify_deleted_after_apply() -> None:
    doc = _fixture_doc()
    applied = apply_edits(doc, list(parse_l3("delete @badge").edits))
    assert verify_deleted(applied, "badge") is True
    assert verify_deleted(applied, "title") is False


def test_verify_appended_after_apply() -> None:
    doc = _fixture_doc()
    applied = apply_edits(
        doc,
        list(
            parse_l3(
                'append to=@frame-1 {\n  text #new-child "x"\n}'
            ).edits
        ),
    )
    assert verify_appended(applied, "frame-1", "new-child") is True
    # A non-appended eid still fails the check.
    assert verify_appended(applied, "frame-1", "badge") is False


def test_verify_inserted_after_apply() -> None:
    doc = _fixture_doc()
    applied = apply_edits(
        doc,
        list(
            parse_l3(
                'insert into=@frame-1 after=@title {\n'
                '  text #between "x"\n}'
            ).edits
        ),
    )
    assert verify_inserted(
        applied, "frame-1", "title", "between"
    ) is True


def test_verify_moved_after_apply() -> None:
    doc = _fixture_doc()
    applied = apply_edits(
        doc,
        list(
            parse_l3(
                "move @badge to=@archive position=first"
            ).edits
        ),
    )
    assert verify_moved(applied, "badge", "archive", "first") is True
    # And not in its old home.
    assert verify_deleted(
        apply_edits(
            doc,
            list(
                parse_l3(
                    "move @badge to=@archive position=first"
                ).edits
            ),
        ),
        "frame-1",
    ) is False
