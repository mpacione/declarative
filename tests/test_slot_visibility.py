"""PR 2 — grammar-level slot visibility.

Tests for the `{empty}` SlotFill sentinel, PathOverride `.visible=...`
syntax, compressor emission of visibility overrides into markup,
renderer consumption of markup PathOverrides, and backend-neutrality
of the `.visible`-bearing markup.

Stages 1-5 cover incremental TDD cycles. Each stage adds a single
cycle's tests. Tests marked `skip` are intentionally kept red until
their production-side wiring lands — they read as the RED step of the
next TDD cycle.
"""

from __future__ import annotations

import pytest

from dd.markup_l3 import (
    Block,
    EmptyNode,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PathOverride,
    PropAssign,
    SlotFill,
    emit_l3,
    parse_l3,
)


# ---------------------------------------------------------------------------
# Stage 1 — `{empty}` SlotFill sentinel
# ---------------------------------------------------------------------------


class TestEmptySlotFillSentinel:
    """`{empty}` is a dd-markup keyword in value position for SlotFill
    that means "this slot is intentionally empty in this usage". Every
    backend lowers it natively:

    - Figma: emit `.visible = false` on the descendant bound to the slot.
    - React / HTML: skip the conditional render.
    - SwiftUI: `EmptyView()`.
    - Compose: null-slot.

    The markup is backend-neutral; the resolution is per-backend.
    """

    def test_parse_empty_slot_fill_inside_comp_ref(self) -> None:
        """`trailing_icon = {empty}` inside a CompRef block parses as a
        SlotFill whose `.node` is an `EmptyNode`, not a real Node."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        screen = doc.top_level[0]
        comp_ref = screen.block.statements[0]
        stmt = comp_ref.block.statements[0]
        assert isinstance(stmt, SlotFill)
        assert stmt.slot_name == "trailing_icon"
        assert isinstance(stmt.node, EmptyNode)

    def test_emit_empty_slot_fill_roundtrip(self) -> None:
        """emit_l3 serializes `{empty}` back to `{empty}` textually."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        emitted = emit_l3(doc)
        assert "= {empty}" in emitted

    def test_empty_slot_fill_roundtrip_preserves_equality(self) -> None:
        """parse(emit(parse(src))) == parse(src) — full structural
        equality across a round-trip. This is the Tier 1 grammar
        round-trip invariant."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        doc2 = parse_l3(emit_l3(doc))
        assert doc == doc2

    def test_empty_slot_fill_distinguishes_from_propgroup(self) -> None:
        """`{empty}` as a SlotFill RHS is DIFFERENT from a PropGroup
        value — the `empty` keyword must not be swallowed by the
        PropGroup parser (which expects `{IDENT = value ...}`)."""
        src = "screen #s { -> nav/top-nav #n { trailing_icon = {empty} } }"
        doc = parse_l3(src)
        stmt = doc.top_level[0].block.statements[0].block.statements[0]
        assert isinstance(stmt, SlotFill)
        # The RHS must be an EmptyNode sentinel, NOT a PropGroup.
        # A PropGroup value would fail `isinstance(stmt.node, EmptyNode)`.
        assert not hasattr(stmt.node, "entries")


# ---------------------------------------------------------------------------
# Stage 2 — PathOverride with `.visible=false`
# ---------------------------------------------------------------------------


class TestPathOverrideVisible:
    """`left.logo/dank.visible = false` is a PathOverride whose path
    targets a named slot + descendant. The parser treats `.visible` as
    a regular property path segment — no grammar change needed, but
    the path may now include a slot-name prefix separated by `.`.
    """

    def test_parse_path_override_visible_false(self) -> None:
        src = (
            "screen #s { -> nav/top-nav #n { "
            "left.logo.visible = false } }"
        )
        doc = parse_l3(src)
        comp_ref = doc.top_level[0].block.statements[0]
        overrides = [
            p for p in comp_ref.block.statements
            if isinstance(p, PathOverride)
        ]
        assert len(overrides) == 1
        po = overrides[0]
        assert po.path == "left.logo.visible"
        assert isinstance(po.value, Literal_)
        assert po.value.lit_kind == "bool"
        assert po.value.py is False

    def test_parse_path_override_visible_true_roundtrip(self) -> None:
        """visible=true also round-trips — this is the "show a master-
        default-hidden descendant" form."""
        src = (
            "screen #s { -> nav/top-nav #n { "
            "right.badge.visible = true } }"
        )
        doc = parse_l3(src)
        doc2 = parse_l3(emit_l3(doc))
        assert doc == doc2

    def test_path_override_visible_emit_then_parse(self) -> None:
        src = (
            "screen #s { -> nav/top-nav #n { "
            "trailing.share_icon.visible = false } }"
        )
        doc = parse_l3(src)
        emitted = emit_l3(doc)
        # Must survive the round-trip.
        assert "trailing.share_icon.visible = false" in emitted or \
               "trailing.share_icon.visible=false" in emitted
        doc2 = parse_l3(emitted)
        assert doc == doc2
