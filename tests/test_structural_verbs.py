"""Unit tests for dd.structural_verbs helpers (M7.4 scaffolding)."""

from __future__ import annotations

import pytest

from dd.markup_l3 import apply_edits, parse_l3
from dd.structural_verbs import (
    collect_insert_candidates,
    collect_move_candidates,
    collect_parent_candidates,
    collect_removable_candidates,
    existing_eids,
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


def test_verify_moved_position_last() -> None:
    """Position='last' branch — target lands at end of dest block."""
    # Archive already has title + subtitle; move badge there to
    # be last.
    src = (
        "screen #screen-1 {\n"
        "  frame #frame-1 {\n"
        "    rectangle #badge\n"
        "  }\n"
        "  frame #archive {\n"
        "    text #note \"existing\"\n"
        "  }\n"
        "}\n"
    )
    doc = parse_l3(src)
    applied = apply_edits(
        doc,
        list(
            parse_l3(
                "move @badge to=@archive position=last"
            ).edits
        ),
    )
    assert verify_moved(applied, "badge", "archive", "last") is True
    # And NOT at 'first' — the check is position-sensitive.
    assert verify_moved(applied, "badge", "archive", "first") is False


def test_unique_eids_on_empty_doc_returns_empty_list() -> None:
    """Edge case: a doc with no top-level nodes returns [] without
    raising. Useful for the structural-verb helpers that call this
    before iterating."""
    from dd.markup_l3 import L3Document
    empty = L3Document(namespace=None, top_level=())
    assert unique_eids(empty) == []
    assert existing_eids(empty) == set()


def test_existing_eids_includes_cousin_duplicates() -> None:
    """existing_eids returns every eid (not filtered by uniqueness).
    Grammar §2.3.1 allows cousin eids to collide (same eid under
    different parents); collision guard must flag those when a
    new-eid proposal picks the same name."""
    src = (
        "screen #screen-1 {\n"
        "  frame #left {\n"
        "    text #twin \"a\"\n"
        "  }\n"
        "  frame #right {\n"
        "    text #twin \"b\"\n"
        "  }\n"
        "}\n"
    )
    doc = parse_l3(src)
    eids = existing_eids(doc)
    assert "twin" in eids
    # unique_eids filters it out (twin appears twice globally).
    assert "twin" not in unique_eids(doc)
    # existing_eids is what the collision-guard checks against:
    # even cousin duplicates count.
    assert {"screen-1", "left", "right", "twin"}.issubset(eids)
