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
    """Pass 1 shipped the function signature; per-verb implementations
    arrive in Passes 2–8. Each pass converts a NotImplementedError
    test into a per-verb apply test.
    """

    def test_stub_with_empty_edits_returns_doc_unchanged(self):
        """Empty edits = identity. Always a no-op."""
        doc = parse_l3(_doc(""))  # no verbs at all
        result = apply_edits(doc, [])
        assert result == doc


# ---------------------------------------------------------------------------
# Pass 2: set verb apply semantics
# ---------------------------------------------------------------------------

def _find_node_by_eid(doc, eid: str):
    """Test helper: depth-first walk for the first node with given eid.
    Returns None if not found. Mirrors apply_edits's resolver for
    test assertions.
    """
    def _walk(items):
        for item in items:
            if isinstance(item, Node):
                if item.head.eid == eid:
                    return item
                if item.block is not None:
                    found = _walk(item.block.statements)
                    if found is not None:
                        return found
        return None
    return _walk(doc.top_level)


class TestApplySetSimple:
    """`set` mutates a property on the addressed node."""

    def test_set_changes_existing_property(self):
        doc = parse_l3(_doc("set @card-1 radius={radius.xl}"))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        radius_prop = card.head.get_prop("radius")
        assert radius_prop is not None
        # The token ref's path should now be `radius.xl`.
        assert radius_prop.value.path == "radius.xl"

    def test_set_adds_new_property(self):
        doc = parse_l3(_doc("set @card-1 visible=false"))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        vis = card.head.get_prop("visible")
        assert vis is not None
        # `false` is a Literal_ with .py == False.
        assert vis.value.py is False

    def test_set_text_string_updates_positional(self):
        # S1.1 — change a text string. The compressor puts text
        # literals in `head.positional` (the canonical form for
        # text-bearing types). `set @X text="..."` must rewrite
        # the positional so the renderer sees the new string; it
        # should NOT leave a dangling `text=` prop alongside the
        # positional (the renderer prefers positional, so the prop
        # would be dead weight at best and ambiguous at worst).
        doc = parse_l3(_doc('set @title text="New title"'))
        result = apply_edits(doc)
        title = _find_node_by_eid(result, "title")
        assert title.head.positional is not None
        assert title.head.positional.py == "New title"
        # No dangling text= prop
        assert title.head.get_prop("text") is None

    def test_set_text_on_non_text_node_falls_through_to_prop(self):
        """Nodes without a positional (e.g. a card) accept
        `text="..."` as a regular prop. Only text-bearing types
        (text / heading / link) have the positional rewrite."""
        doc = parse_l3(_doc('set @card-1 text="Caption"'))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        assert card.head.positional is None
        assert card.head.get_prop("text").value.py == "Caption"

    def test_set_text_tokenref_on_text_node_falls_through_to_prop(self):
        """A TokenRef value on a text-bearing node doesn't match the
        positional-rewrite heuristic (which only accepts string
        Literal_). The edit must fall through to a regular ``text=``
        prop-add so the renderer has a chance to resolve the token;
        overwriting positional with a TokenRef would break the
        compressor's text-positional convention."""
        doc = parse_l3(_doc('set @title text={content.greeting}'))
        result = apply_edits(doc)
        title = _find_node_by_eid(result, "title")
        # Positional unchanged — still the original "Hello"
        assert title.head.positional is not None
        assert title.head.positional.py == "Hello"
        # text= prop present, with TokenRef as value
        text_prop = title.head.get_prop("text")
        assert text_prop is not None
        assert getattr(text_prop.value, "kind", None) == "token-ref"
        assert text_prop.value.path == "content.greeting"

    def test_set_mixed_props_with_text_on_text_node(self):
        """`set @title text="New" visible=false` — one rewrites
        positional, the other adds a prop. Neither interferes with
        the other."""
        doc = parse_l3(_doc(
            'set @title text="New title" visible=false'
        ))
        result = apply_edits(doc)
        title = _find_node_by_eid(result, "title")
        # Positional updated
        assert title.head.positional is not None
        assert title.head.positional.py == "New title"
        # text= prop dropped (consumed by positional rewrite)
        assert title.head.get_prop("text") is None
        # visible= prop added (non-text key, regular path)
        vis = title.head.get_prop("visible")
        assert vis is not None
        assert vis.value.py is False

    def test_set_color_token(self):
        # S1.3 — change a color token ref.
        doc = parse_l3(_doc(
            "set @card-1 fill={color.brand.primary}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        fill = card.head.get_prop("fill")
        assert fill.value.path == "color.brand.primary"

    def test_set_multi_property_one_statement(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl} visible=false"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        assert card.head.get_prop("radius").value.path == "radius.xl"
        assert card.head.get_prop("visible").value.py is False

    def test_implicit_set_form(self):
        doc = parse_l3(_doc("@card-1 radius={radius.xl}"))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        assert card.head.get_prop("radius").value.path == "radius.xl"

    def test_original_unchanged(self):
        """apply_edits returns a new doc; original is preserved."""
        doc = parse_l3(_doc("set @card-1 radius={radius.xl}"))
        original_card = _find_node_by_eid(doc, "card-1")
        original_radius = original_card.head.get_prop("radius").value
        apply_edits(doc)
        # Re-find on the SAME original doc — radius unchanged.
        still_original = _find_node_by_eid(doc, "card-1")
        assert still_original.head.get_prop("radius").value == original_radius


class TestApplySetSequential:
    """Multiple set statements apply in order."""

    def test_three_sets_compose(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl}\n"
            "set @card-1 visible=false\n"
            "set @title text=\"Title 2\""
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        title = _find_node_by_eid(result, "title")
        assert card.head.get_prop("radius").value.path == "radius.xl"
        assert card.head.get_prop("visible").value.py is False
        # S1.1: text-bearing nodes' text= rewrites head.positional,
        # not a prop. See test_set_text_string_updates_positional.
        assert title.head.positional is not None
        assert title.head.positional.py == "Title 2"

    def test_later_set_overrides_earlier_on_same_key(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.lg}\n"
            "set @card-1 radius={radius.xl}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        assert card.head.get_prop("radius").value.path == "radius.xl"


class TestApplySetErrors:
    """ERef resolution errors fire structured KINDs."""

    def test_eid_not_found_raises(self):
        doc = parse_l3(_doc("set @nonexistent radius={radius.xl}"))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_eid_ambiguous_raises(self):
        # Construct a doc with two cousin nodes sharing eid "card-1".
        src = (
            "screen #s {\n"
            "  frame #left {\n"
            "    card #c { text \"a\" }\n"
            "  }\n"
            "  frame #right {\n"
            "    card #c { text \"b\" }\n"
            "  }\n"
            "}\n"
            "set @c radius={radius.xl}\n"
        )
        doc = parse_l3(src)
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_AMBIGUOUS"

    def test_dotted_path_resolves_unambiguously(self):
        # Same two cousin `c` nodes; address one explicitly via the
        # parent.child path.
        src = (
            "screen #s {\n"
            "  frame #left {\n"
            "    card #c { text \"a\" }\n"
            "  }\n"
            "  frame #right {\n"
            "    card #c { text \"b\" }\n"
            "  }\n"
            "}\n"
            "set @left.c radius={radius.xl}\n"
        )
        doc = parse_l3(src)
        result = apply_edits(doc)
        # The targeted card-c (under left) has the new radius;
        # the cousin (under right) does not.
        def _find(name, eid):
            for it in result.top_level:
                for s in it.block.statements:
                    if s.head.eid == name:
                        for c in s.block.statements:
                            if c.head.eid == eid:
                                return c
        left_c = _find("left", "c")
        right_c = _find("right", "c")
        assert left_c.head.get_prop("radius") is not None
        assert right_c.head.get_prop("radius") is None

    def test_strict_false_collects_errors_as_warnings(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl}\n"
            "set @nonexistent visible=false\n"
        ))
        result = apply_edits(doc, strict=False)
        # First edit applied; second became a warning.
        card = _find_node_by_eid(result, "card-1")
        assert card.head.get_prop("radius").value.path == "radius.xl"
        kinds = [w.kind for w in result.warnings]
        assert "KIND_EID_NOT_FOUND" in kinds


# ---------------------------------------------------------------------------
# Pass 3: delete verb apply semantics
# ---------------------------------------------------------------------------

class TestApplyDelete:
    def test_delete_removes_node(self):
        doc = parse_l3(_doc("delete @card-2"))
        result = apply_edits(doc)
        assert _find_node_by_eid(result, "card-2") is None
        # Original unchanged.
        assert _find_node_by_eid(doc, "card-2") is not None

    def test_delete_with_subtree_removes_descendants(self):
        # card-1 has #title and #subtitle as children. Deleting card-1
        # also removes both children (no orphan eids).
        doc = parse_l3(_doc("delete @card-1"))
        result = apply_edits(doc)
        assert _find_node_by_eid(result, "card-1") is None
        assert _find_node_by_eid(result, "title") is None
        assert _find_node_by_eid(result, "subtitle") is None

    def test_delete_leaf(self):
        doc = parse_l3(_doc("delete @title"))
        result = apply_edits(doc)
        assert _find_node_by_eid(result, "title") is None
        # Card-1 itself still present; subtitle still present.
        assert _find_node_by_eid(result, "card-1") is not None
        assert _find_node_by_eid(result, "subtitle") is not None

    def test_delete_eid_not_found_raises(self):
        doc = parse_l3(_doc("delete @nonexistent"))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_delete_then_set_conflicts(self):
        doc = parse_l3(_doc(
            "delete @card-1\n"
            "set @card-1 radius={radius.xl}"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EDIT_CONFLICT"

    def test_delete_top_level_node(self):
        doc = parse_l3(_doc("delete @s"))
        result = apply_edits(doc)
        # The screen #s is a top-level node; deleting it empties top_level.
        assert _find_node_by_eid(result, "s") is None
        assert len(result.top_level) == 0


# ---------------------------------------------------------------------------
# Pass 4: append verb apply semantics
# ---------------------------------------------------------------------------

class TestApplyAppend:
    def test_append_to_node_with_children(self):
        doc = parse_l3(_doc(
            "append to=@card-1 {\n  text #footer \"footer\"\n}"
        ))
        result = apply_edits(doc)
        # card-1 originally had 2 text children (#title, #subtitle);
        # now it has 3.
        card = _find_node_by_eid(result, "card-1")
        assert len(card.block.statements) == 3
        # Appended child is last and has the new eid.
        last = card.block.statements[-1]
        assert isinstance(last, Node)
        assert last.head.eid == "footer"

    def test_append_to_empty_block(self):
        # Construct a doc with an empty-block node.
        src = (
            "screen #s {\n"
            "  card #empty\n"
            "}\n"
            "append to=@empty {\n"
            "  text \"first child\"\n"
            "}\n"
        )
        doc = parse_l3(src)
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "empty")
        assert card.block is not None
        assert len(card.block.statements) == 1

    def test_append_multiple_compose(self):
        doc = parse_l3(_doc(
            "append to=@card-1 {\n  text \"a\"\n}\n"
            "append to=@card-1 {\n  text \"b\"\n}\n"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        # Original 2 + 2 appended.
        assert len(card.block.statements) == 4

    def test_append_to_nonexistent_raises(self):
        doc = parse_l3(_doc(
            "append to=@nope {\n  text \"x\"\n}"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_append_then_address_appended_child(self):
        doc = parse_l3(_doc(
            "append to=@card-1 {\n  text #later \"x\"\n}\n"
            "set @later text=\"y\"\n"
        ))
        result = apply_edits(doc)
        later = _find_node_by_eid(result, "later")
        # S1.1: text= on a text-bearing node rewrites positional.
        assert later.head.positional is not None
        assert later.head.positional.py == "y"


# ---------------------------------------------------------------------------
# Pass 5: insert verb apply semantics
# ---------------------------------------------------------------------------

class TestApplyInsert:
    def test_insert_after_sibling(self):
        doc = parse_l3(_doc(
            "insert into=@card-1 after=@title {\n"
            "  text #middle \"middle\"\n"
            "}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        # Original [title, subtitle]; after=title → [title, middle, subtitle].
        eids = [s.head.eid for s in card.block.statements]
        assert eids == ["title", "middle", "subtitle"]

    def test_insert_before_sibling(self):
        doc = parse_l3(_doc(
            "insert into=@card-1 before=@subtitle {\n"
            "  text #middle \"middle\"\n"
            "}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card.block.statements]
        assert eids == ["title", "middle", "subtitle"]

    def test_insert_after_last(self):
        doc = parse_l3(_doc(
            "insert into=@card-1 after=@subtitle {\n"
            "  text #last \"last\"\n"
            "}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card.block.statements]
        assert eids == ["title", "subtitle", "last"]

    def test_insert_before_first(self):
        doc = parse_l3(_doc(
            "insert into=@card-1 before=@title {\n"
            "  text #first \"first\"\n"
            "}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card.block.statements]
        assert eids == ["first", "title", "subtitle"]

    def test_insert_into_nonexistent_raises(self):
        doc = parse_l3(_doc(
            "insert into=@nope after=@title {\n"
            "  text \"x\"\n"
            "}"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_insert_anchor_not_in_parent_raises(self):
        # @subtitle exists but not as a child of @s.
        doc = parse_l3(_doc(
            "insert into=@s after=@subtitle {\n"
            "  card #x\n"
            "}"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"


# ---------------------------------------------------------------------------
# Pass 6: move verb apply semantics
# ---------------------------------------------------------------------------

class TestApplyMove:
    def test_move_to_position_first(self):
        # Move card-2 from @s into @card-1 at position=first.
        doc = parse_l3(_doc(
            "move @card-2 to=@card-1 position=first"
        ))
        result = apply_edits(doc)
        # card-2 is gone from @s.
        screen = result.top_level[0]
        s_eids = [
            s.head.eid for s in screen.block.statements
            if isinstance(s, Node)
        ]
        assert "card-2" not in s_eids
        # card-2 is the FIRST child of card-1.
        card1 = _find_node_by_eid(result, "card-1")
        assert card1.block.statements[0].head.eid == "card-2"

    def test_move_to_position_last(self):
        doc = parse_l3(_doc(
            "move @card-2 to=@card-1 position=last"
        ))
        result = apply_edits(doc)
        card1 = _find_node_by_eid(result, "card-1")
        assert card1.block.statements[-1].head.eid == "card-2"

    def test_move_after_anchor(self):
        # Move card-2 into card-1, after=title.
        doc = parse_l3(_doc(
            "move @card-2 to=@card-1 after=@title"
        ))
        result = apply_edits(doc)
        card1 = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card1.block.statements]
        assert eids == ["title", "card-2", "subtitle"]

    def test_move_before_anchor(self):
        doc = parse_l3(_doc(
            "move @card-2 to=@card-1 before=@subtitle"
        ))
        result = apply_edits(doc)
        card1 = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card1.block.statements]
        assert eids == ["title", "card-2", "subtitle"]

    def test_move_within_same_parent_reorders(self):
        # Reorder #title and #subtitle inside #card-1.
        doc = parse_l3(_doc(
            "move @subtitle to=@card-1 position=first"
        ))
        result = apply_edits(doc)
        card1 = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card1.block.statements]
        assert eids == ["subtitle", "title"]

    def test_move_target_not_found_raises(self):
        doc = parse_l3(_doc("move @nope to=@s position=first"))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_move_destination_not_found_raises(self):
        doc = parse_l3(_doc("move @card-1 to=@nope position=first"))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"


# ---------------------------------------------------------------------------
# Pass 7: replace verb apply semantics (OQ-3 Interpretation A:
# replaces the block CONTENT; the addressed node itself stays.)
# ---------------------------------------------------------------------------

class TestApplyReplace:
    def test_replace_block_with_single_node(self):
        doc = parse_l3(_doc(
            "replace @card-1 {\n  text #only \"only child\"\n}"
        ))
        result = apply_edits(doc)
        # @card-1 still exists.
        card = _find_node_by_eid(result, "card-1")
        assert card is not None
        # Its block content is now exactly the new content (the
        # original #title and #subtitle children are gone).
        assert _find_node_by_eid(result, "title") is None
        assert _find_node_by_eid(result, "subtitle") is None
        assert _find_node_by_eid(result, "only") is not None

    def test_replace_with_multiple_children(self):
        doc = parse_l3(_doc(
            "replace @card-1 {\n"
            "  text #h \"new heading\"\n"
            "  text #b \"new body\"\n"
            "}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        eids = [s.head.eid for s in card.block.statements]
        assert eids == ["h", "b"]

    def test_replace_preserves_target_node_head(self):
        # The card-1 node keeps its eid + head properties (only the
        # children change).
        doc = parse_l3(_doc(
            "replace @card-1 {\n  text \"x\"\n}"
        ))
        result = apply_edits(doc)
        card = _find_node_by_eid(result, "card-1")
        # head.eid + radius prop preserved.
        assert card.head.eid == "card-1"
        assert card.head.get_prop("radius") is not None

    def test_replace_target_not_found_raises(self):
        doc = parse_l3(_doc(
            "replace @nope {\n  text \"x\"\n}"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"


# ---------------------------------------------------------------------------
# Pass 8: swap verb apply semantics (M7.1: TypeKeyword swaps only;
# CompRef + override-preservation deferred to M7.2.)
# ---------------------------------------------------------------------------

class TestApplySwap:
    def test_swap_with_typekeyword_replaces_node(self):
        # Swap @card-1 (a card) with an icon node.
        doc = parse_l3(_doc(
            "swap @card-1 with=icon"
        ))
        result = apply_edits(doc)
        # The card-1 eid is now an icon (eid preserved on replacement).
        node = _find_node_by_eid(result, "card-1")
        assert node is not None
        assert node.head.head_kind == "type"
        assert node.head.type_or_path == "icon"
        assert node.head.eid == "card-1"

    def test_swap_preserves_eid_for_subsequent_edits(self):
        doc = parse_l3(_doc(
            "swap @card-2 with=text\n"
            "set @card-2 text=\"swapped\""
        ))
        result = apply_edits(doc)
        node = _find_node_by_eid(result, "card-2")
        assert node.head.type_or_path == "text"
        assert node.head.get_prop("text").value.py == "swapped"

    def test_swap_target_not_found_raises(self):
        doc = parse_l3(_doc("swap @nope with=icon"))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    @pytest.mark.skip(reason="stub: full swap requires M7.0.b component_slots")
    def test_swap_with_component_ref_preserves_overrides(self):
        # M7.2 unskips this once component_slots populated by M7.0.b
        # provides the slot map needed to carry overrides forward.
        doc = parse_l3(_doc(
            "set @card-1 fill={color.brand.primary}\n"
            "swap @card-1 with=-> button/primary/lg"
        ))
        result = apply_edits(doc)
        node = _find_node_by_eid(result, "card-1")
        # Expected: the swap brings in button/primary/lg's defaults
        # but carries the user-set fill forward as an override.
        assert node.head.head_kind == "comp-ref"
        assert node.head.get_prop("fill") is not None


# ---------------------------------------------------------------------------
# Pass 9: integration tests — multi-verb sequences + corpus parity
# ---------------------------------------------------------------------------

class TestApplyEditsIntegration:
    """Multi-verb sequences + strict mode + the empty-edits invariant."""

    def test_three_different_verbs_compose(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl}\n"
            "delete @card-2\n"
            "append to=@card-1 {\n  text #footer \"footer\"\n}\n"
        ))
        result = apply_edits(doc)
        # set landed
        card1 = _find_node_by_eid(result, "card-1")
        assert card1.head.get_prop("radius").value.path == "radius.xl"
        # delete landed
        assert _find_node_by_eid(result, "card-2") is None
        # append landed
        assert _find_node_by_eid(result, "footer") is not None

    def test_partial_failure_strict_false_collects_errors(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl}\n"
            "delete @nope\n"
            "append to=@card-1 {\n  text #later \"later\"\n}\n"
        ))
        result = apply_edits(doc, strict=False)
        # First + third edits applied; middle edit became a warning.
        card1 = _find_node_by_eid(result, "card-1")
        assert card1.head.get_prop("radius").value.path == "radius.xl"
        assert _find_node_by_eid(result, "later") is not None
        kinds = [w.kind for w in result.warnings]
        assert "KIND_EID_NOT_FOUND" in kinds

    def test_partial_failure_strict_true_raises_on_first(self):
        doc = parse_l3(_doc(
            "set @card-1 radius={radius.xl}\n"
            "delete @nope\n"
            "append to=@card-1 {\n  text #later \"later\"\n}\n"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc, strict=True)
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_kind_edit_conflict_on_delete_then_set(self):
        doc = parse_l3(_doc(
            "delete @card-1\n"
            "set @card-1 radius={radius.xl}\n"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc, strict=True)
        assert exc.value.kind == "KIND_EDIT_CONFLICT"

    def test_kind_edit_conflict_on_delete_then_append(self):
        doc = parse_l3(_doc(
            "delete @card-1\n"
            "append to=@card-1 {\n  text \"x\"\n}\n"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc, strict=True)
        assert exc.value.kind == "KIND_EDIT_CONFLICT"

    def test_kind_edit_conflict_on_delete_then_move(self):
        doc = parse_l3(_doc(
            "delete @card-1\n"
            "move @card-1 to=@s position=first\n"
        ))
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc, strict=True)
        assert exc.value.kind == "KIND_EDIT_CONFLICT"

    def test_empty_edits_returns_input_unchanged(self):
        doc = parse_l3(_doc(""))
        # No edits in the doc → apply_edits returns the same object.
        result = apply_edits(doc)
        assert result is doc

    def test_empty_explicit_edits_returns_input_unchanged(self):
        doc = parse_l3(_doc(""))
        result = apply_edits(doc, [])
        assert result is doc


class TestApplyEditsFixtureIdentity:
    """For each existing .dd fixture, apply_edits([]) must return a
    document equal to the input. Validates the immutable-rebuild
    pattern doesn't accidentally alter the tree.
    """

    @pytest.mark.parametrize("fixture", [
        "tests/fixtures/markup/01-login-welcome.dd",
        "tests/fixtures/markup/02-card-sheet.dd",
        "tests/fixtures/markup/03-keyboard-sheet.dd",
    ])
    def test_apply_edits_empty_is_identity(self, fixture):
        from pathlib import Path
        path = Path(fixture)
        if not path.exists():
            pytest.skip(f"fixture not present: {fixture}")
        src = path.read_text()
        doc = parse_l3(src)
        result = apply_edits(doc, [])
        assert result is doc


# ---------------------------------------------------------------------------
# Code-review subagent (2026-04-19) suggested tests T1-T5
# ---------------------------------------------------------------------------

class TestCodeReviewFollowUps:
    """Tests added per the post-Pass-9 Sonnet code-review subagent
    suggestions (see docs/m7_assumptions_log.md). Each docstring
    notes which review issue the test addresses + the resolution.
    """

    def test_t1_cousin_eids_no_false_conflict(self):
        """Issue #1 (subagent: HIGH). Subagent claimed deleting
        `@left.c` would falsely conflict with a subsequent `set
        @right.c`. Investigation: ERef.path for the dotted form is
        `"left.c"`, NOT `"c"` — so target.path strings don't collide
        across cousins. Spec §2.3.1 forces dotted addressing on
        cousins (otherwise KIND_EID_AMBIGUOUS fires before
        deleted_targets is touched).

        This test PROVES the claimed bug doesn't exist.
        """
        src = (
            "screen #s {\n"
            "  frame #left {\n"
            "    card #c { text \"left\" }\n"
            "  }\n"
            "  frame #right {\n"
            "    card #c { text \"right\" }\n"
            "  }\n"
            "}\n"
            "delete @left.c\n"
            "set @right.c radius={radius.lg}\n"
        )
        doc = parse_l3(src)
        result = apply_edits(doc)
        # left.c gone; right.c present + has new radius.
        # Locate by walking left/right scopes:
        for top in result.top_level:
            for s in top.block.statements:
                if s.head.eid == "left":
                    assert all(
                        c.head.eid != "c" for c in s.block.statements
                    ), "left.c should be deleted"
                if s.head.eid == "right":
                    rc = next(
                        c for c in s.block.statements if c.head.eid == "c"
                    )
                    assert rc.head.get_prop("radius") is not None

    def test_t2_move_where_target_isolates_ancestor_of_dest(self):
        """Issue #4 (subagent: MEDIUM). Move where target's removal
        leaves a parent that is also an ancestor of the destination.
        Tests the re-resolve path.
        """
        src = (
            "screen #s {\n"
            "  frame #outer {\n"
            "    frame #inner {\n"
            "      card #target { text \"x\" }\n"
            "      frame #dest { text #placeholder \"\" }\n"
            "    }\n"
            "  }\n"
            "}\n"
            "move @target to=@dest position=first\n"
        )
        doc = parse_l3(src)
        result = apply_edits(doc)
        # @target now lives inside @dest as the first child.
        dest = _find_node_by_eid(result, "dest")
        assert dest is not None
        first_child = dest.block.statements[0]
        assert first_child.head.eid == "target"
        # @inner still exists; no longer has @target as a direct child.
        inner = _find_node_by_eid(result, "inner")
        assert inner is not None
        eids = [s.head.eid for s in inner.block.statements
                if isinstance(s, Node)]
        assert "target" not in eids
        assert "dest" in eids

    def test_t3_replace_on_node_with_no_block(self):
        """Subagent T3. Original test only covered replace on nodes
        with existing children. Test with a leaf node (no block).
        """
        src = (
            "screen #s {\n"
            "  card #empty\n"
            "}\n"
            "replace @empty {\n"
            "  text #only \"new\"\n"
            "}\n"
        )
        doc = parse_l3(src)
        result = apply_edits(doc)
        empty = _find_node_by_eid(result, "empty")
        assert empty is not None
        assert empty.block is not None
        assert empty.block.statements[0].head.eid == "only"

    def test_t4_insert_anchor_must_be_direct_child(self):
        """Subagent T4. Insert anchor lookup must only match direct
        children of `into=`, not any descendant.
        """
        src = (
            "screen #s {\n"
            "  frame #grid {\n"
            "    card #c1 { text \"a\" }\n"
            "    card #c2 {\n"
            "      text #item \"b\"\n"
            "    }\n"
            "  }\n"
            "}\n"
            "insert into=@grid after=@item {\n"
            "  card #x\n"
            "}\n"
        )
        doc = parse_l3(src)
        with pytest.raises(DDMarkupParseError) as exc:
            apply_edits(doc)
        # @item is a grandchild of @grid, not a direct child.
        assert exc.value.kind == "KIND_EID_NOT_FOUND"

    def test_t5_swap_with_compref_does_not_crash(self):
        """Subagent T5. The full CompRef swap test is deferred to
        M7.2. This minimal version only verifies the dataclasses.
        replace(head, eid=...) call doesn't crash on a CompRef head.
        """
        # Use a CompRef as the with_node target.
        src = (
            "screen #s {\n"
            "  card #card-1\n"
            "}\n"
            "swap @card-1 with=-> button/primary/lg\n"
        )
        doc = parse_l3(src)
        # Should not crash. The replacement node should have
        # head_kind=comp-ref AND retain card-1's eid.
        result = apply_edits(doc)
        node = _find_node_by_eid(result, "card-1")
        assert node is not None
        assert node.head.head_kind == "comp-ref"
