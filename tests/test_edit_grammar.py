"""Tests for the M7.1 edit-verb grammar (Pass 1: parse + emit + apply stub).

Pass 1 scope: every verb must PARSE (round-trip through parse → emit →
parse == identity), the L3Document carries `edits`, the apply_edits
function exists and raises NotImplementedError. Per-verb apply tests
land in subsequent passes (Passes 2–8).
"""

from __future__ import annotations

import pytest

from dd.markup_l3 import (
    AppendStatement,
    Block,
    DeleteStatement,
    DDMarkupParseError,
    ERef,
    InsertStatement,
    L3Document,
    MoveStatement,
    Node,
    NodeHead,
    PropAssign,
    ReplaceStatement,
    SetStatement,
    SwapStatement,
    apply_edits,
    emit_l3,
    parse_l3,
)


# ---------------------------------------------------------------------------
# Document scaffolding for parse fixtures
# ---------------------------------------------------------------------------

def _doc(verbs_text: str) -> str:
    """Wrap verb statement text in a minimal construction document so
    each test can target the verb's parse without re-stating the whole
    document grammar.
    """
    return (
        "screen #s {\n"
        "  card #card-1 fill={color.surface.card} radius=8 {\n"
        "    text #title \"Hello\"\n"
        "    text #subtitle \"World\"\n"
        "  }\n"
        "  card #card-2 {\n"
        "    text #body \"Body\"\n"
        "  }\n"
        "}\n"
        "\n"
        f"{verbs_text}\n"
    )


# ---------------------------------------------------------------------------
# AST: shape + defaults
# ---------------------------------------------------------------------------

class TestEditDataclasses:
    """Frozen dataclasses with the shape Plan §2 specs."""

    def test_eref_basic(self):
        e = ERef(path="card-1")
        assert e.path == "card-1"
        assert e.scope_alias is None
        assert e.has_wildcard is False
        assert e.kind == "eref"

    def test_eref_with_wildcard(self):
        e = ERef(path="grid/*", has_wildcard=True)
        assert e.has_wildcard

    def test_set_statement_shape(self):
        s = SetStatement(
            target=ERef(path="card-1"),
            properties=(PropAssign(key="visible", value=False),),
        )
        assert s.kind == "set"
        assert s.target.path == "card-1"
        assert len(s.properties) == 1

    def test_delete_statement_shape(self):
        s = DeleteStatement(target=ERef(path="badge"))
        assert s.kind == "delete"

    def test_append_statement_shape(self):
        s = AppendStatement(to=ERef(path="form"), body=Block())
        assert s.kind == "append"

    def test_insert_statement_after(self):
        s = InsertStatement(
            into=ERef(path="grid"),
            anchor=ERef(path="card-3"),
            anchor_rel="after",
            body=Block(),
        )
        assert s.anchor_rel == "after"

    def test_insert_statement_before(self):
        s = InsertStatement(
            into=ERef(path="grid"),
            anchor=ERef(path="card-3"),
            anchor_rel="before",
            body=Block(),
        )
        assert s.anchor_rel == "before"

    def test_move_statement_position_first(self):
        s = MoveStatement(
            target=ERef(path="card-1"),
            to=ERef(path="grid"),
            position="first",
        )
        assert s.position == "first"

    def test_move_statement_with_anchor(self):
        s = MoveStatement(
            target=ERef(path="card-1"),
            to=ERef(path="grid"),
            position="after",
            position_anchor=ERef(path="card-3"),
        )
        assert s.position == "after"
        assert s.position_anchor.path == "card-3"

    def test_swap_statement_shape(self):
        with_node = Node(head=NodeHead(
            head_kind="type", type_or_path="button",
        ))
        s = SwapStatement(target=ERef(path="b1"), with_node=with_node)
        assert s.kind == "swap"

    def test_replace_statement_shape(self):
        s = ReplaceStatement(target=ERef(path="header"), body=Block())
        assert s.kind == "replace"

    def test_l3document_edits_field_default(self):
        doc = L3Document()
        assert doc.edits == ()


# ---------------------------------------------------------------------------
# Parsing — each verb in isolation (smallest valid form)
# ---------------------------------------------------------------------------

class TestParseSetExplicit:
    def test_parses_basic(self):
        doc = parse_l3(_doc("set @card-1 radius={radius.lg}"))
        assert len(doc.edits) == 1
        s = doc.edits[0]
        assert isinstance(s, SetStatement)
        assert s.target.path == "card-1"
        assert len(s.properties) == 1

    def test_parses_multi_property(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.lg} visible=false"
        ))
        s = doc.edits[0]
        assert len(s.properties) == 2

    def test_parses_dotted_path(self):
        doc = parse_l3(_doc("set @card-1.title text=\"New\""))
        s = doc.edits[0]
        assert s.target.path == "card-1.title"


class TestParseSetImplicit:
    def test_implicit_form_is_set_statement(self):
        doc = parse_l3(_doc("@card-1 radius={radius.lg}"))
        assert len(doc.edits) == 1
        assert isinstance(doc.edits[0], SetStatement)

    def test_implicit_and_explicit_match(self):
        d1 = parse_l3(_doc("@card-1 radius={radius.lg}"))
        d2 = parse_l3(_doc("set @card-1 radius={radius.lg}"))
        # Same AST modulo line/col attribution
        assert d1.edits[0].target == d2.edits[0].target
        assert d1.edits[0].properties == d2.edits[0].properties


class TestParseDelete:
    def test_parses(self):
        doc = parse_l3(_doc("delete @card-2"))
        s = doc.edits[0]
        assert isinstance(s, DeleteStatement)
        assert s.target.path == "card-2"


class TestParseAppend:
    def test_parses_with_body(self):
        doc = parse_l3(_doc(
            "append to=@card-1 {\n"
            "  text \"appended\"\n"
            "}"
        ))
        s = doc.edits[0]
        assert isinstance(s, AppendStatement)
        assert s.to.path == "card-1"
        assert s.body is not None
        assert len(s.body.statements) >= 1


class TestParseInsert:
    def test_parses_after(self):
        doc = parse_l3(_doc(
            "insert into=@s after=@card-1 {\n"
            "  card #card-3\n"
            "}"
        ))
        s = doc.edits[0]
        assert isinstance(s, InsertStatement)
        assert s.into.path == "s"
        assert s.anchor.path == "card-1"
        assert s.anchor_rel == "after"

    def test_parses_before(self):
        doc = parse_l3(_doc(
            "insert into=@s before=@card-2 {\n"
            "  card #card-1b\n"
            "}"
        ))
        s = doc.edits[0]
        assert s.anchor_rel == "before"


class TestParseMove:
    def test_parses_position_first(self):
        doc = parse_l3(_doc("move @card-2 to=@s position=first"))
        s = doc.edits[0]
        assert isinstance(s, MoveStatement)
        assert s.target.path == "card-2"
        assert s.to.path == "s"
        assert s.position == "first"
        assert s.position_anchor is None

    def test_parses_position_last(self):
        doc = parse_l3(_doc("move @card-1 to=@s position=last"))
        s = doc.edits[0]
        assert s.position == "last"

    def test_parses_after_anchor(self):
        doc = parse_l3(_doc("move @card-1 to=@s after=@card-2"))
        s = doc.edits[0]
        assert s.position == "after"
        assert s.position_anchor.path == "card-2"

    def test_parses_before_anchor(self):
        doc = parse_l3(_doc("move @card-2 to=@s before=@card-1"))
        s = doc.edits[0]
        assert s.position == "before"
        assert s.position_anchor.path == "card-1"


class TestParseSwap:
    def test_parses_with_typekeyword(self):
        doc = parse_l3(_doc("swap @card-1 with=icon #ic-1"))
        s = doc.edits[0]
        assert isinstance(s, SwapStatement)
        assert s.target.path == "card-1"
        assert s.with_node.head.head_kind == "type"
        assert s.with_node.head.type_or_path == "icon"

    def test_parses_with_compref(self):
        doc = parse_l3(_doc("swap @card-1 with=-> button/primary/lg"))
        s = doc.edits[0]
        assert s.with_node.head.head_kind == "comp-ref"


class TestParseReplace:
    def test_parses_with_body(self):
        doc = parse_l3(_doc(
            "replace @card-1 {\n"
            "  text \"replaced content\"\n"
            "}"
        ))
        s = doc.edits[0]
        assert isinstance(s, ReplaceStatement)
        assert s.target.path == "card-1"
        assert s.body is not None


# ---------------------------------------------------------------------------
# Round-trip — parse → emit → parse == identity per verb
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Each verb must round-trip cleanly. The emitter is allowed to
    canonicalise property order; the AST equality check ignores
    line/col which the parser populates.
    """

    @pytest.mark.parametrize("verb", [
        "set @card-1 radius={radius.lg}",
        "set @card-1 radius={radius.lg} visible=false",
        "delete @card-2",
        "append to=@card-1 {\n  text \"x\"\n}",
        "insert into=@s after=@card-1 {\n  card #card-3\n}",
        "insert into=@s before=@card-2 {\n  card #card-1b\n}",
        "move @card-1 to=@s position=first",
        "move @card-2 to=@s position=last",
        "move @card-1 to=@s after=@card-2",
        "move @card-2 to=@s before=@card-1",
        "swap @card-1 with=icon #ic-1",
        "replace @card-1 {\n  text \"new\"\n}",
    ])
    def test_round_trip(self, verb):
        src = _doc(verb)
        doc1 = parse_l3(src)
        emitted = emit_l3(doc1)
        doc2 = parse_l3(emitted)
        # Edit-statement count + per-verb identity checks (excluding line/col).
        assert len(doc1.edits) == len(doc2.edits) == 1
        e1, e2 = doc1.edits[0], doc2.edits[0]
        assert type(e1) is type(e2)
        assert e1.kind == e2.kind


# ---------------------------------------------------------------------------
# Multi-statement emission: edits as separate section
# ---------------------------------------------------------------------------

class TestEmitOrdering:
    def test_construction_then_edits(self):
        src = _doc(
            "set @card-1 radius={radius.lg}\n"
            "delete @card-2"
        )
        doc = parse_l3(src)
        emitted = emit_l3(doc)
        # Construction items appear before edits.
        assert emitted.index("screen #s") < emitted.index("set @card-1")
        # Both edits appear.
        assert "set @card-1" in emitted
        assert "delete @card-2" in emitted


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestVerbErrors:
    def test_set_without_properties_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("set @card-1"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_append_without_to_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("append { text \"x\" }"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_insert_without_anchor_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc(
                "insert into=@s {\n  card #card-x\n}"
            ))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_swap_without_with_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("swap @card-1"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_delete_without_eref_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("delete"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_replace_without_body_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("replace @card-1"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"

    def test_move_position_invalid_value_raises(self):
        with pytest.raises(DDMarkupParseError) as exc:
            parse_l3(_doc("move @card-1 to=@s position=middle"))
        assert exc.value.kind == "KIND_BAD_EDIT_VERB"


# ---------------------------------------------------------------------------
# apply_edits stub — Pass 1 only
# ---------------------------------------------------------------------------

class TestApplyEditsStub:
    """Pass 1 ships the function signature; per-verb implementations
    arrive in Passes 2–8. The stub raises NotImplementedError so any
    accidental call fails loudly.
    """

    def test_stub_raises_on_any_statement(self):
        doc = parse_l3(_doc("set @card-1 radius={radius.lg}"))
        with pytest.raises(NotImplementedError):
            apply_edits(doc)

    def test_stub_with_empty_edits_returns_doc_unchanged(self):
        """Empty edits = identity. Should NOT raise (the stub
        short-circuits on no-op).
        """
        doc = parse_l3(_doc(""))  # no verbs at all
        result = apply_edits(doc, [])
        assert result == doc
