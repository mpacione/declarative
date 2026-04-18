"""Plan B Stage 1.3/1.4 — compressor tests.

Tests `dd.compress_l3.compress_to_l3` end-to-end on each of the three
reference Dank screens. Verifies:

1. Compression produces a valid `L3Document` AST
2. The output emits cleanly via `emit_l3`
3. `parse_l3(emit_l3(doc)) == doc` — the grammar-level round-trip invariant

Skipped when the corpus DB is absent (matches `test_script_parity.py`'s
guard, so clean checkouts don't fail).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3, derive_comp_slash_path, normalize_to_eid
from dd.ir import generate_ir
from dd.markup_l3 import (
    Block,
    L3Document,
    Node,
    NodeTrailer,
    emit_l3,
    parse_l3,
)


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# EID sanitization unit tests — L0↔L3 §2.3.1 examples
# ---------------------------------------------------------------------------


class TestNormalizeToEid:
    @pytest.mark.parametrize("raw,expected", [
        # Spec examples
        ("iPhone 13 Pro Max - 119", "iphone-13-pro-max-119"),
        ("nav/top-nav", "nav-top-nav"),
        ("Safari - Bottom", "safari-bottom"),
        ("Frame 354", "frame-354"),
        # Digit start → empty (caller uses auto-id)
        ("123", ""),
        # Empty string → empty
        ("", ""),
        # Parens stripped
        ("(internal spacer)", "internal-spacer"),
        # Multiple consecutive separators collapse
        ("foo  /  bar", "foo-bar"),
        # Leading/trailing separators trimmed
        ("  foo-bar  ", "foo-bar"),
        ("-foo-", "foo"),
    ])
    def test_normalization(self, raw: str, expected: str) -> None:
        assert normalize_to_eid(raw) == expected


class TestDeriveCompSlashPath:
    """Slash-path derivation from component master names — L0↔L3 §2.7.1."""

    @pytest.mark.parametrize("name,expected", [
        ("nav/top-nav", "nav/top-nav"),
        ("button/small/translucent", "button/small/translucent"),
        ("Safari - Bottom", "safari-bottom"),         # single-segment
        ("iOS/StatusBar", "ios/statusbar"),
        ("ios/alpha-keyboard", "ios/alpha-keyboard"),
        (".icons/safari/lock", "icons/safari/lock"),
    ])
    def test_component_names(self, name: str, expected: str) -> None:
        assert derive_comp_slash_path(name) == expected


# ---------------------------------------------------------------------------
# End-to-end compression on reference screens
# ---------------------------------------------------------------------------


REFERENCE_SCREENS = [
    (181, "01-login-welcome"),
    (222, "02-card-sheet"),
    (237, "03-keyboard-sheet"),
]


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_produces_valid_l3_document(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """The compressor produces a well-formed L3Document for each
    reference screen."""
    ir = generate_ir(db_conn, screen_id, semantic=True, filter_chrome=False)
    spec = ir["spec"]
    assert len(spec["elements"]) > 0, (
        f"screen {screen_id} has no elements — DB extraction issue"
    )

    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)
    assert isinstance(doc, L3Document)
    assert len(doc.top_level) == 1, (
        f"expected 1 top-level node (screen root), got {len(doc.top_level)}"
    )

    root = doc.top_level[0]
    assert isinstance(root, Node)
    assert root.head.type_or_path == "screen"


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_emits_valid_markup(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """The compressor's output emits cleanly via `emit_l3`."""
    spec = generate_ir(db_conn, screen_id, semantic=True, filter_chrome=False)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)

    emitted = emit_l3(doc)
    assert len(emitted) > 100, "emitted output suspiciously short"
    assert "screen" in emitted
    assert f"(extracted src={screen_id})" in emitted


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_output_round_trips(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """`parse_l3(emit_l3(compress(ir))) == compress(ir)` — the Tier 1
    grammar-level round-trip invariant."""
    spec = generate_ir(db_conn, screen_id, semantic=True, filter_chrome=False)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)

    emitted = emit_l3(doc)
    doc2 = parse_l3(emitted)
    assert doc == doc2, (
        f"screen {screen_id}: compress→emit→parse not idempotent"
    )


def test_provenance_trailer_on_root(db_conn: sqlite3.Connection) -> None:
    """The compressor attaches `(extracted src=N)` to the screen root."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    root = doc.top_level[0]
    assert root.head.trailer is not None
    assert isinstance(root.head.trailer, NodeTrailer)
    assert root.head.trailer.kind == "extracted"
    attrs = dict(root.head.trailer.attrs)
    assert "src" in attrs
    assert attrs["src"].py == 181


def test_eid_derived_from_original_name(db_conn: sqlite3.Connection) -> None:
    """Screen 181's root name `"iPhone 13 Pro Max - 119"` sanitizes
    to `#iphone-13-pro-max-119` per L0↔L3 §2.3.1."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    assert doc.top_level[0].head.eid == "iphone-13-pro-max-119"


# ---------------------------------------------------------------------------
# Synthetic screen-wrapper collapse — `dd.ir.generate_ir` wraps the real
# Figma canvas FRAME in a synthetic `screen-1` parent. The compressor
# collapses the two into a single top-level node.
# ---------------------------------------------------------------------------


def test_collapse_requires_synthetic_screen_key_pattern(
    db_conn: sqlite3.Connection,
) -> None:
    """The collapse heuristic requires the root key to start with
    `screen-` (the synthetic-wrapper pattern `dd.ir.generate_ir`
    produces). A user-authored root with a single same-named child
    (e.g. `frame-1 → frame-1-inner` both named `"Card"`) must NOT
    collapse — that'd silently flatten real hierarchies."""
    from dd.compress_l3 import _collapse_synthetic_screen_wrapper

    # Hand-authored spec that looks like the pattern but uses a
    # non-synthetic root key.
    spec = {
        "root": "card-root",
        "elements": {
            "card-root": {
                "type": "screen",
                "_original_name": "Card",
                "children": ["card-inner"],
            },
            "card-inner": {
                "type": "frame",
                "_original_name": "Card",
                "visual": {"fills": [{"type": "solid", "color": "#000"}]},
                "children": [],
            },
        },
        "_node_id_map": {"card-root": 1, "card-inner": 2},
    }
    out = _collapse_synthetic_screen_wrapper(spec)
    # Spec passes through unchanged — no collapse.
    assert out["elements"]["card-root"]["children"] == ["card-inner"]
    assert "visual" not in out["elements"]["card-root"]


def test_collapse_requires_root_type_screen(self=None) -> None:
    """Even with a `screen-N` key, the root's `type` must be `"screen"`
    for the collapse to fire. A frame-typed root that happens to be
    keyed `"screen-1"` is not a synthetic wrapper."""
    from dd.compress_l3 import _collapse_synthetic_screen_wrapper

    spec = {
        "root": "screen-1",
        "elements": {
            "screen-1": {
                "type": "frame",         # NOT "screen"
                "_original_name": "X",
                "children": ["frame-1"],
            },
            "frame-1": {
                "type": "frame",
                "_original_name": "X",
                "children": [],
            },
        },
    }
    out = _collapse_synthetic_screen_wrapper(spec)
    # No collapse because root.type != "screen".
    assert out["elements"]["screen-1"]["children"] == ["frame-1"]


def test_synthetic_screen_wrapper_collapsed(
    db_conn: sqlite3.Connection,
) -> None:
    """The compressor collapses the synthetic `screen` wrapper into the
    real canvas FRAME. The top-level Node has exactly one child per
    DB-level grand-child — no redundant intermediate `frame` line."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    root = doc.top_level[0]
    # Type stays `screen` (the dd-markup keyword).
    assert root.head.type_or_path == "screen"
    # No child node is a `frame` with the SAME eid as the screen —
    # that's the double-wrapper pattern we're eliminating.
    screen_eid = root.head.eid
    assert root.block is not None
    redundant_wrappers = [
        s for s in root.block.statements
        if isinstance(s, Node)
        and s.head.head_kind == "type"
        and s.head.type_or_path == "frame"
        and s.head.eid == screen_eid
    ]
    assert redundant_wrappers == [], (
        f"screen `#{screen_eid}` still has a redundant `frame "
        f"#{screen_eid}` wrapper in its block: {redundant_wrappers}"
    )


def test_collapsed_screen_hoists_canvas_fill(
    db_conn: sqlite3.Connection,
) -> None:
    """The canvas FRAME's fill (#F6F6F6 on the reference screens)
    hoists onto the collapsed `screen` node. Otherwise we'd lose the
    canvas background."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    props = doc.top_level[0].head.properties
    fill_props = [p for p in props if p.key == "fill"]
    assert len(fill_props) == 1, (
        f"expected exactly 1 `fill` on collapsed screen root; got "
        f"{len(fill_props)}: {fill_props}"
    )


def test_collapsed_screen_preserves_grandchildren(
    db_conn: sqlite3.Connection,
) -> None:
    """After collapsing the wrapper, the screen's children equal the
    canvas FRAME's children — not wrapped in an intermediate frame."""
    spec = generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"]
    # Expected children = canvas FRAME's children in the raw spec.
    raw_root = spec["elements"][spec["root"]]
    assert len(raw_root.get("children") or []) == 1
    canvas_key = raw_root["children"][0]
    canvas = spec["elements"][canvas_key]
    expected_child_count = len(canvas.get("children") or [])
    assert expected_child_count > 0, "reference screen has no canvas children"

    doc = compress_to_l3(spec, db_conn, screen_id=181)
    # One Node-child per canvas grand-child. (Statements may also
    # include a PropAssign etc. — we count only Nodes.)
    assert doc.top_level[0].block is not None
    node_children = [
        s for s in doc.top_level[0].block.statements if isinstance(s, Node)
    ]
    assert len(node_children) == expected_child_count


# ---------------------------------------------------------------------------
# Slice C — CompRef emission via CKR lookup
# ---------------------------------------------------------------------------


def test_comp_refs_emitted_for_mode1_instances(
    db_conn: sqlite3.Connection,
) -> None:
    """Mode-1-eligible INSTANCE nodes emit as `-> slash/path` CompRefs
    at their highest level — the master component provides all children
    at render time per L0↔L3 §2.7. Deeply nested Mode-1 instances (e.g.
    an `icon/back` inside a `button` inside a `nav`) are covered by the
    OUTER CompRef and don't emit their own CompRef lines.

    Screen 181 has ~4 top-level CompRefs (the CTA button + 3 content-
    row icons) at the level where the spec's 3-tier row structure
    surfaces individual icons. That's the correct count — not 56.
    """
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    emitted = emit_l3(doc)
    arrow_count = emitted.count("-> ")
    # Sanity: at least 3 CompRefs (nav/top-nav + CTA button + content icons).
    assert arrow_count >= 3, (
        f"expected ≥3 CompRefs on screen 181; got {arrow_count}"
    )


def test_compref_path_matches_ckr_master_name(
    db_conn: sqlite3.Connection,
) -> None:
    """CompRef slash-path derives from `component_key_registry.name`
    (NOT from the instance layer name) per L0↔L3 §2.7.1."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=181,
    )
    emitted = emit_l3(doc)
    # nav/top-nav appears at the top level so it emits as a CompRef
    assert "-> nav/top-nav" in emitted
    # The CTA button is a `button/large/translucent` instance at root
    assert "-> button/large/translucent" in emitted


def test_compref_without_conn_falls_back_to_frame(
    db_conn: sqlite3.Connection,
) -> None:
    """With `conn=None`, CKR lookup is skipped; Mode-1-eligible nodes
    fall back to inline `frame` / type keyword."""
    spec = generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"]
    doc = compress_to_l3(spec, conn=None, screen_id=181)
    emitted = emit_l3(doc)
    # No CompRefs should appear without the CKR lookup.
    assert "-> " not in emitted, (
        "expected no CompRefs when conn is None; fallback to inline"
    )


def test_compref_roundtrips_at_grammar_level(
    db_conn: sqlite3.Connection,
) -> None:
    """CompRef emission must satisfy the same Tier 1 round-trip
    invariant as the rest of the compressor."""
    doc = compress_to_l3(
        generate_ir(db_conn, 222, semantic=True, filter_chrome=False)["spec"],
        db_conn,
        screen_id=222,
    )
    emitted = emit_l3(doc)
    doc2 = parse_l3(emitted)
    assert doc == doc2


# ---------------------------------------------------------------------------
# Stage 1.4 Part 1 — JSON / PropGroup `:self` override handlers
# ---------------------------------------------------------------------------
#
# Covers `:self:fills`, `:self:strokes`, `:self:effects`,
# `:self:primaryAxisAlignItems`, and `:self:padding{Left,Right,Top,Bottom}`
# — overrides whose `override_value` is JSON or requires coalescing.
# ---------------------------------------------------------------------------


class TestSelfOverrideRawPaintNormalization:
    """`_normalize_raw_paint` converts Figma-raw paint dicts (as they
    live in `instance_overrides`) into the spec-normalized form
    consumed by `_fill_to_value`."""

    def test_solid_rgb_to_hex(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "SOLID", "visible": True, "opacity": 1,
            "color": {"r": 1.0, "g": 0.5, "b": 0.0},
        }
        assert _normalize_raw_paint(raw) == {
            "type": "solid", "color": "#FF8000",
        }

    def test_solid_with_alpha(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "SOLID", "visible": True, "opacity": 1,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.5},
        }
        assert _normalize_raw_paint(raw) == {
            "type": "solid", "color": "#00000080",
        }

    def test_solid_folds_paint_opacity_into_alpha(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        # Paint-level opacity multiplies into the color's alpha.
        raw = {
            "type": "SOLID", "visible": True, "opacity": 0.5,
            "color": {"r": 1.0, "g": 1.0, "b": 1.0},
        }
        out = _normalize_raw_paint(raw)
        assert out is not None
        assert out["color"] == "#FFFFFF80"

    def test_hidden_paint_returns_none(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "SOLID", "visible": False,
            "color": {"r": 1.0, "g": 0, "b": 0},
        }
        assert _normalize_raw_paint(raw) is None

    def test_gradient_opacity_folds_into_each_stop(self) -> None:
        """Figma stores paint-level `opacity` multiplicatively on top
        of each stop's per-color alpha — must fold both into the
        hex-alpha byte, not just ignore paint opacity on gradients."""
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "GRADIENT_LINEAR", "visible": True, "opacity": 0.5,
            "gradientStops": [
                {"color": {"r": 1.0, "g": 0, "b": 0, "a": 1.0}, "position": 0},
                {"color": {"r": 0, "g": 0, "b": 1.0, "a": 0.8}, "position": 1},
            ],
        }
        out = _normalize_raw_paint(raw)
        assert out is not None
        assert out["type"] == "gradient-linear"
        # 0.5 paint opacity × 1.0 stop alpha → 0x80
        # 0.5 paint opacity × 0.8 stop alpha = 0.4 → 0x66
        assert out["stops"][0]["color"] == "#FF000080"
        assert out["stops"][1]["color"] == "#0000FF66"

    def test_gradient_linear_normalized(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "GRADIENT_LINEAR", "visible": True,
            "gradientStops": [
                {"color": {"r": 1.0, "g": 0, "b": 0}, "position": 0},
                {"color": {"r": 0, "g": 1.0, "b": 0}, "position": 1},
            ],
        }
        out = _normalize_raw_paint(raw)
        assert out == {
            "type": "gradient-linear",
            "stops": [{"color": "#FF0000"}, {"color": "#00FF00"}],
        }

    def test_radial_gradient_unsupported(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {"type": "GRADIENT_RADIAL", "visible": True, "gradientStops": []}
        assert _normalize_raw_paint(raw) is None

    def test_image_normalized(self) -> None:
        from dd.compress_l3 import _normalize_raw_paint
        raw = {
            "type": "IMAGE", "visible": True,
            "imageHash": "a" * 39 + "1",
        }
        out = _normalize_raw_paint(raw)
        assert out == {
            "type": "image",
            "asset_hash": "a" * 39 + "1",
        }


class TestSelfOverrideCorpusCoverage:
    """Sanity-check that the new `:self` handlers actually fire on the
    Dank corpus (i.e. we're not just testing dead code)."""

    def test_shadow_all_hidden_diagnostic_roundtrips(self) -> None:
        """`$ext.shadow_all_hidden=true` must tokenize/parse/re-emit
        as a plain bool-valued ext-prop. Exercises the emitter and
        parser's ext-prop path — important because the 204-screen
        corpus only hits this shape via CompRef overrides (all-hidden
        :self:effects), and a regression in the parser's ext-prop
        handling would otherwise pass the corpus sweep."""
        from dd.markup_l3 import (
            Block, L3Document, Literal_, Node, NodeHead,
            PropAssign, emit_l3, parse_l3,
        )
        doc = L3Document(
            top_level=(Node(head=NodeHead(
                head_kind="type",
                type_or_path="frame",
                eid="f",
                properties=(PropAssign(
                    key="$ext.shadow_all_hidden",
                    value=Literal_(lit_kind="bool", raw="true", py=True),
                ),),
            )),),
        )
        emitted = emit_l3(doc)
        assert "$ext.shadow_all_hidden=true" in emitted
        parsed = parse_l3(emitted)
        assert parsed == doc

    def test_shadow_all_hidden_suppresses_inherited_shadow_corpus(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """For corpus CompRefs where `:self:effects` is all-hidden, the
        emitted output must NOT also carry a spec-path `shadow=...`
        PropAssign — the suppress-set handshake would be toothless
        otherwise, and the renderer would still apply the master's
        shadow despite the designer's intent to hide it."""
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir
        from dd.markup_l3 import emit_l3

        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id FROM instance_overrides io "
            "JOIN nodes n ON n.id = io.node_id "
            "WHERE io.property_name = ':self:effects' LIMIT 1"
        ).fetchone()
        assert row is not None
        spec = generate_ir(
            db_conn, row[0], semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=row[0])
        emitted = emit_l3(doc)

        # Any line carrying the diagnostic must NOT also carry a
        # `shadow=shadow(...)` PropAssign on the same head.
        for ln in emitted.splitlines():
            if "$ext.shadow_all_hidden" in ln:
                assert "shadow=shadow(" not in ln, (
                    f"shadow suppression regression — line still has "
                    f"inherited shadow alongside diagnostic: {ln!r}"
                )

    def test_self_effects_surfaces_diagnostic_from_fetch(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """All 391 `:self:effects` rows in the Dank corpus consist of
        DROP_SHADOW entries with `visible=false` (Figma's idiom for
        "turn off the master's shadow"). `_effects_to_shadow` skips
        those, so if the override handler doesn't surface a diagnostic,
        the compressor silently drops the override — indistinguishable
        at round-trip from "inherit the master's shadow". Assert the
        `$ext.shadow_all_hidden=true` diagnostic fires via the direct
        `_fetch_self_overrides` return, not via substring search on
        emitted markup (which is polluted by spec-derived `shadow=`
        PropAssigns from `_visual_props`)."""
        from dd.compress_l3 import _fetch_self_overrides
        from dd.ir import generate_ir

        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id FROM instance_overrides io "
            "JOIN nodes n ON n.id = io.node_id "
            "WHERE io.property_name = ':self:effects' LIMIT 1"
        ).fetchone()
        assert row is not None
        spec = generate_ir(
            db_conn, row[0], semantic=True, filter_chrome=False,
        )["spec"]
        node_id_map = spec.get("_node_id_map") or {}
        props_by_eid, _, _ = _fetch_self_overrides(
            db_conn, node_id_map, list(node_id_map.keys()),
        )
        found = False
        for plist in props_by_eid.values():
            for p in plist:
                if p.key == "$ext.shadow_all_hidden":
                    assert p.value.py is True
                    found = True
                    break
            if found:
                break
        assert found, (
            f"_fetch_self_overrides did not emit "
            f"$ext.shadow_all_hidden=true for any eid on screen "
            f"{row[0]} (known all-hidden EFFECTS overrides)"
        )

    def test_self_padding_returns_propgroup_from_fetch(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Directly assert `_fetch_self_overrides` (the override path
        under test) returns a `padding=PropGroup(...)` for at least one
        real corpus eid. `_spatial_props` also emits `padding={...}`
        from spec-layout data, so a corpus-wide substring search on
        emitted markup is a false-positive-prone signal — we probe the
        internal return dict instead so a regression that silently
        drops the override branch would fail the test."""
        from dd.compress_l3 import _fetch_self_overrides
        from dd.markup_l3 import PropGroup
        from dd.ir import generate_ir

        # Pick a screen with :self:paddingLeft overrides.
        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id FROM instance_overrides io "
            "JOIN nodes n ON n.id = io.node_id "
            "WHERE io.property_name = ':self:paddingLeft' LIMIT 1"
        ).fetchone()
        assert row is not None, (
            ":self:paddingLeft corpus rows vanished unexpectedly"
        )
        spec = generate_ir(
            db_conn, row[0], semantic=True, filter_chrome=False,
        )["spec"]
        node_id_map = spec.get("_node_id_map") or {}
        props_by_eid, _, _ = _fetch_self_overrides(
            db_conn, node_id_map, list(node_id_map.keys()),
        )
        # At least one eid on this screen must have a `padding=`
        # PropAssign whose value is a PropGroup (the coalesced form).
        found = False
        for plist in props_by_eid.values():
            for p in plist:
                if p.key == "padding" and isinstance(p.value, PropGroup):
                    found = True
                    break
            if found:
                break
        assert found, (
            f"_fetch_self_overrides should return a padding=PropGroup "
            f"for at least one eid on screen {row[0]}; got "
            f"{props_by_eid}"
        )


class TestOverrideMergeSemantics:
    """Spec §2.7.2 — override IS the authoritative value. For scalar
    properties: full replace. For side/corner-addressable PropGroups
    (padding, radius): per-entry patch so a partial override preserves
    the spec-derived entries it doesn't touch."""

    def test_padding_override_patches_left_preserves_top_right_bottom(
        self,
    ) -> None:
        """A `:self:paddingLeft` override on an instance whose spec-
        derived layout already emits a full 4-side padding must yield
        the spec's `top`/`right`/`bottom` entries + the override's
        `left`. Wholesale replace would drop 3 of 4 sides."""
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign, PropGroup

        def n(raw: str) -> Literal_:
            return Literal_(lit_kind="number", raw=raw, py=int(raw))

        spec_padding = PropAssign(
            key="padding",
            value=PropGroup(entries=(
                PropAssign(key="top", value=n("16")),
                PropAssign(key="right", value=n("16")),
                PropAssign(key="bottom", value=n("16")),
                PropAssign(key="left", value=n("16")),
            )),
        )
        override_padding = PropAssign(
            key="padding",
            value=PropGroup(entries=(
                PropAssign(key="left", value=n("24")),
            )),
        )
        merged = _merge_override_prop([spec_padding], override_padding)
        assert len(merged) == 1
        assert merged[0].key == "padding"
        entries = merged[0].value.entries
        keys = [e.key for e in entries]
        # Canonical §7.6 order preserved.
        assert keys == ["top", "right", "bottom", "left"]
        assert entries[0].value.py == 16          # top from spec
        assert entries[1].value.py == 16          # right from spec
        assert entries[2].value.py == 16          # bottom from spec
        assert entries[3].value.py == 24          # left from override

    def test_scalar_override_still_wholesale_replaces(self) -> None:
        """Non-PropGroup overrides (e.g. `visible`, `opacity`, `fill`)
        still fully replace the spec-derived value."""
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign

        spec = PropAssign(
            key="fill",
            value=Literal_(lit_kind="hex-color", raw="#000000", py="#000000"),
        )
        override = PropAssign(
            key="fill",
            value=Literal_(lit_kind="hex-color", raw="#FF0000", py="#FF0000"),
        )
        merged = _merge_override_prop([spec], override)
        assert len(merged) == 1
        assert merged[0].value.raw == "#FF0000"

    def test_override_without_existing_prop_appends(self) -> None:
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign

        override = PropAssign(
            key="opacity",
            value=Literal_(lit_kind="number", raw="0.5", py=0.5),
        )
        merged = _merge_override_prop([], override)
        assert merged == [override]

    def test_radius_propgroup_merge_per_corner(self) -> None:
        """Spec §7.6 radius PropGroup: override patches one corner,
        other three corners preserved in canonical order
        top-left, top-right, bottom-right, bottom-left."""
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign, PropGroup

        def n(raw: str) -> Literal_:
            return Literal_(lit_kind="number", raw=raw, py=int(raw))

        spec_radius = PropAssign(
            key="radius",
            value=PropGroup(entries=(
                PropAssign(key="top-left", value=n("8")),
                PropAssign(key="top-right", value=n("8")),
                PropAssign(key="bottom-right", value=n("8")),
                PropAssign(key="bottom-left", value=n("8")),
            )),
        )
        override_radius = PropAssign(
            key="radius",
            value=PropGroup(entries=(
                PropAssign(key="top-left", value=n("20")),
            )),
        )
        merged = _merge_override_prop([spec_radius], override_radius)
        assert len(merged) == 1
        keys = [e.key for e in merged[0].value.entries]
        assert keys == [
            "top-left", "top-right", "bottom-right", "bottom-left",
        ]
        values = [e.value.py for e in merged[0].value.entries]
        assert values == [20, 8, 8, 8]

    def test_scalar_radius_existing_with_propgroup_override_replaces(
        self,
    ) -> None:
        """When the spec emits `radius=N` (scalar Literal_) and the
        override arrives as `radius=PropGroup(...)`, the merge falls
        through to wholesale replace (no per-entry merge possible —
        existing has no entries). Per Figma semantics, a per-corner
        override on a uniform-radius instance replaces uniformly."""
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign, PropGroup

        def n(raw: str) -> Literal_:
            return Literal_(lit_kind="number", raw=raw, py=int(raw))

        spec = PropAssign(key="radius", value=n("10"))
        override = PropAssign(
            key="radius",
            value=PropGroup(entries=(
                PropAssign(key="top-left", value=n("20")),
            )),
        )
        merged = _merge_override_prop([spec], override)
        assert len(merged) == 1
        assert merged[0] is override      # wholesale replaced

    def test_padding_override_preserves_left_right_when_patching_top_bottom(
        self,
    ) -> None:
        """Partial side combo: override patches only top+bottom while
        spec had all four sides. Left/right from spec must survive
        and canonical order is unaffected."""
        from dd.compress_l3 import _merge_override_prop
        from dd.markup_l3 import Literal_, PropAssign, PropGroup

        def n(raw: str) -> Literal_:
            return Literal_(lit_kind="number", raw=raw, py=int(raw))

        spec_padding = PropAssign(
            key="padding",
            value=PropGroup(entries=(
                PropAssign(key="top", value=n("10")),
                PropAssign(key="right", value=n("12")),
                PropAssign(key="bottom", value=n("10")),
                PropAssign(key="left", value=n("12")),
            )),
        )
        override_padding = PropAssign(
            key="padding",
            value=PropGroup(entries=(
                PropAssign(key="top", value=n("24")),
                PropAssign(key="bottom", value=n("24")),
            )),
        )
        merged = _merge_override_prop([spec_padding], override_padding)
        entries = merged[0].value.entries
        assert [e.key for e in entries] == [
            "top", "right", "bottom", "left",
        ]
        assert [e.value.py for e in entries] == [24, 12, 24, 12]


class TestMainAxisEnumNormalization:
    """Grammar §7.4 — `mainAxis` values are
    `start|end|center|space-between|space-around|space-evenly`.
    Figma's raw enum is `MIN|CENTER|MAX|SPACE_BETWEEN|...`; the spec
    IR lowercases these. The compressor must map both to the grammar's
    canonical form before emission."""

    def test_mainAxis_min_maps_to_start(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """No corpus screen should emit `mainAxis=min` — that's not in
        the §7.4 legal set."""
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir
        from dd.markup_l3 import emit_l3

        for sid in [181, 222, 237]:
            spec = generate_ir(
                db_conn, sid, semantic=True, filter_chrome=False,
            )["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            out = emit_l3(doc)
            assert "mainAxis=min" not in out
            assert "mainAxis=max" not in out
            assert "mainAxis=space_between" not in out  # underscore variant

    def test_primary_align_space_around_and_space_evenly_map_correctly(
        self,
    ) -> None:
        """`SPACE_AROUND`/`SPACE_EVENLY` are in `_PRIMARY_AXIS_MAP` but
        may have no corpus coverage. Assert the map itself contains the
        grammar-§7.4-legal forms. (Directly tests the map because the
        corpus won't exercise these otherwise.)"""
        from dd.compress_l3 import _PRIMARY_AXIS_MAP
        assert _PRIMARY_AXIS_MAP["SPACE_AROUND"] == "space-around"
        assert _PRIMARY_AXIS_MAP["SPACE_EVENLY"] == "space-evenly"
        # All 6 §7.4 legal values covered.
        legal = {
            "start", "end", "center",
            "space-between", "space-around", "space-evenly",
        }
        assert set(_PRIMARY_AXIS_MAP.values()) == legal

    def test_primary_align_self_override_emits_grammar_enum(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """`:self:primaryAxisAlignItems` override rows must normalize
        through `_PRIMARY_AXIS_MAP` to a §7.4 legal keyword."""
        from dd.compress_l3 import _fetch_self_overrides
        from dd.ir import generate_ir
        from dd.markup_l3 import Literal_

        # Find a screen with PRIMARY_ALIGN overrides.
        row = db_conn.execute(
            "SELECT DISTINCT n.screen_id FROM instance_overrides io "
            "JOIN nodes n ON n.id = io.node_id "
            "WHERE io.property_name = ':self:primaryAxisAlignItems' "
            "LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no :self:primaryAxisAlignItems rows in corpus")

        spec = generate_ir(
            db_conn, row[0], semantic=True, filter_chrome=False,
        )["spec"]
        node_id_map = spec.get("_node_id_map") or {}
        props_by_eid, _, _ = _fetch_self_overrides(
            db_conn, node_id_map, list(node_id_map.keys()),
        )
        legal_values = {
            "start", "end", "center",
            "space-between", "space-around", "space-evenly",
        }
        found_mainaxis = False
        for plist in props_by_eid.values():
            for p in plist:
                if p.key != "mainAxis":
                    continue
                found_mainaxis = True
                assert isinstance(p.value, Literal_)
                assert p.value.py in legal_values, (
                    f"mainAxis override emitted non-grammar value "
                    f"{p.value.py!r} (legal: {legal_values})"
                )
        assert found_mainaxis, (
            "_fetch_self_overrides did not produce a mainAxis "
            "PropAssign despite :self:primaryAxisAlignItems rows"
        )


# ---------------------------------------------------------------------------
# Full-corpus Tier 1 sweep — the headline proof for Stage 1.3/1.4
# ---------------------------------------------------------------------------


def test_full_corpus_tier1_round_trip(db_conn: sqlite3.Connection) -> None:
    """Every app_screen in the Dank corpus round-trips through
    compress → emit → parse with structural equality. Tier 1 per
    L0↔L3 §4.1.

    This is the headline invariant for Stage 1.3/1.4. Runs in under
    10s on the 204-screen corpus.
    """
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    assert len(screens) > 0, "no app_screens in DB"

    failures: list[tuple[int, str]] = []
    for sid in screens:
        try:
            spec = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            emitted = emit_l3(doc)
            doc2 = parse_l3(emitted)
            # Warnings are compile-time diagnostics, not round-tripped markup.
            doc_stripped = replace(doc, warnings=())
            if doc_stripped != doc2:
                failures.append((sid, "structural-equality mismatch"))
        except Exception as e:
            failures.append((sid, f"{type(e).__name__}: {str(e)[:100]}"))

    if failures:
        # Report first 10 failures
        details = "\n".join(f"  screen {sid}: {reason}" for sid, reason in failures[:10])
        pytest.fail(
            f"{len(failures)}/{len(screens)} screens failed Tier 1 round-trip:\n{details}"
        )


# ---------------------------------------------------------------------------
# Golden-file snapshots — L0↔L3 §2.11
# ---------------------------------------------------------------------------
#
# Each reference screen gets a frozen snapshot of its compressor output.
# On first run the snapshot is WRITTEN and the test passes (with a
# notice); on subsequent runs the current output is compared byte-wise.
# Regressions surface as diffs in the test output.
#
# Set `COMPRESS_L3_UPDATE_SNAPSHOTS=1` to rewrite all snapshots.


SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "markup"


def _snapshot_path(slug: str) -> Path:
    return SNAPSHOT_DIR / f"{slug}.stage1-expected.dd"


# ---------------------------------------------------------------------------
# Regression tests — review-agent findings (lock in the BLOCKER fixes)
# ---------------------------------------------------------------------------


class TestRegressionFromReview:
    """Tests that would have caught the agent-found bugs. Lock in the
    fixes from the a29ac50 commit so future edits don't regress."""

    def test_text_content_is_emitted_on_text_nodes(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Agent-2 Finding #2 / agent-3 Finding #5: text content was
        silently dropped because the compressor read the wrong field
        path. Regression: assert that known-present strings appear in
        the emitted output for screen 181."""
        doc = compress_to_l3(
            generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=181,
        )
        emitted = emit_l3(doc)
        # Screen 181 has these text strings on heading/text nodes per
        # the L0 summary.
        assert '"Recent Images"' in emitted
        assert '"More"' in emitted

    def test_compref_has_no_child_block(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Agent-2 Finding #6: CompRefs used to emit a full child-block
        expansion (180-line nav-bar trees). Correct behavior per L0↔L3
        §2.7: CompRefs emit WITHOUT a child block — the master provides
        the subtree at render time. Regression: assert CompRef output
        lines don't end with `{`."""
        doc = compress_to_l3(
            generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=181,
        )
        emitted = emit_l3(doc)
        for line in emitted.splitlines():
            stripped = line.strip()
            if stripped.startswith("-> "):
                assert not stripped.endswith("{"), (
                    f"CompRef has a child block — should not: {stripped!r}"
                )

    def test_y_zero_not_dropped_when_x_nonzero(self) -> None:
        """Agent-1 Finding #5 / agent-3 Finding #4: `x=5, y=0` used to
        silently drop `y=0`. Regression: the position logic should
        emit BOTH coordinates when either is non-zero."""
        # Construct a minimal spec directly rather than pulling from DB
        fake_spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {"sizing": {"width": 100, "height": 100}},
                    "children": ["frame-1"],
                },
                "frame-1": {
                    "type": "frame",
                    "layout": {
                        "position": {"x": 5, "y": 0},
                        "sizing": {"width": 50, "height": 50},
                    },
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }
        doc = compress_to_l3(fake_spec, conn=None)
        emitted = emit_l3(doc)
        # Both x and y should appear since x is non-zero
        assert "x=5" in emitted
        assert "y=0" in emitted

    def test_float_imprecision_is_rounded(self) -> None:
        """Agent-2 Finding #3: Figma coordinate residuals like
        `6.000001430511475` should round to clean integers; values with
        real sub-pixel precision should preserve it."""
        fake_spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {
                        "sizing": {
                            "width": 6.000001430511475,     # → 6
                            "height": 15.556350708007812,   # → 15.5564
                        },
                    },
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }
        doc = compress_to_l3(fake_spec, conn=None)
        emitted = emit_l3(doc)
        # Residual snapped to integer
        assert "width=6" in emitted
        assert "6.0" not in emitted  # no trailing .0
        # Sub-pixel value preserved (4 decimal places)
        assert "height=15.5564" in emitted

    def test_bad_input_does_not_crash(self) -> None:
        """Agent-3 Finding #7: `spec["elements"] is None` used to crash
        with AttributeError. Regression: guard against bad input
        shapes; return an empty L3Document instead of raising."""
        bad_inputs = [
            {"elements": None, "root": "x"},
            {"elements": {}, "root": None},
            {"elements": {}, "root": "ghost"},
            {},                                 # missing both keys
            "not-a-dict",                       # type error
        ]
        for bad in bad_inputs:
            doc = compress_to_l3(bad, conn=None)  # type: ignore[arg-type]
            assert isinstance(doc, L3Document)
            assert len(doc.top_level) == 0

    def test_radius_uniform_emitted_from_nodes_table(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Uniform `corner_radius` on DB nodes surfaces as `radius=<N>`
        on the emitted output. Screen 181 has many radius values
        (Safari chrome, home indicator, button corners) — should see
        ≥5 `radius=` occurrences."""
        doc = compress_to_l3(
            generate_ir(db_conn, 181, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=181,
        )
        emitted = emit_l3(doc)
        assert emitted.count("radius=") >= 5

    def test_circular_reference_does_not_recurse_infinitely(self) -> None:
        """A spec with cyclic `children` references should gracefully
        drop the cycle — not raise RecursionError."""
        fake_spec = {
            "version": "1.0",
            "root": "a",
            "elements": {
                "a": {
                    "type": "frame",
                    "layout": {"sizing": {"width": 100, "height": 100}},
                    "children": ["b"],
                },
                "b": {
                    "type": "frame",
                    "layout": {"sizing": {"width": 50, "height": 50}},
                    "children": ["a"],    # cycle: a → b → a
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }
        # Should return a valid document, with `a` having `b` as a
        # child whose OWN `a`-child recursion was short-circuited.
        doc = compress_to_l3(fake_spec, conn=None)
        assert isinstance(doc, L3Document)
        assert len(doc.top_level) == 1

    def test_instance_swap_self_override_changes_slash_path(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """A `:self` INSTANCE_SWAP override replaces the CompRef's
        target component. Screen 325 has 46 such swaps; after Slice B
        the emitted output should show varied slash-paths reflecting
        the swap targets."""
        doc = compress_to_l3(
            generate_ir(db_conn, 325, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=325,
        )
        emitted = emit_l3(doc)
        # Count unique comp-ref paths in the output
        import re
        paths = set(re.findall(r"-> ([a-z0-9_./-]+)", emitted))
        assert len(paths) >= 3, (
            f"expected ≥3 distinct CompRef paths on screen 325; got {paths}"
        )

    def test_bounded_sizing_emitted(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Nodes with `min_width` / `max_width` / `min_height` /
        `max_height` bounds emit as `width=fill(min=N, max=N)` per
        grammar §4.4. Screen 334 has 29 bounded nodes in the DB."""
        doc = compress_to_l3(
            generate_ir(db_conn, 334, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=334,
        )
        emitted = emit_l3(doc)
        # At least 10 bounded sizing occurrences on this screen.
        bounded_count = (
            emitted.count("fill(min=") + emitted.count("fill(max=")
            + emitted.count("hug(min=") + emitted.count("hug(max=")
        )
        assert bounded_count >= 10, (
            f"expected ≥10 bounded sizings on screen 334; got {bounded_count}"
        )

    def test_radius_per_corner_emitted_as_propgroup(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Per-corner `corner_radius` (JSON dict in DB) emits as
        PropGroup with canonical `top-left, top-right, bottom-right,
        bottom-left` ordering per §7.6."""
        # Screen 222's meme-editor has card/sheet/success with per-
        # corner radii.
        doc = compress_to_l3(
            generate_ir(db_conn, 222, semantic=True, filter_chrome=False)["spec"],
            db_conn,
            screen_id=222,
        )
        emitted = emit_l3(doc)
        # If any per-corner radii exist, they should appear in canonical
        # order.
        if "top-left=" in emitted:
            # Verify canonical ordering in at least one PropGroup
            import re
            for m in re.finditer(
                r"radius=\{[^}]*\}", emitted,
            ):
                group_body = m.group(0)
                # Extract the order of the keys
                keys = re.findall(
                    r"(top-left|top-right|bottom-right|bottom-left)=",
                    group_body,
                )
                canonical = [
                    "top-left", "top-right", "bottom-right", "bottom-left",
                ]
                # Keys should be a subsequence of canonical order
                canonical_idx = 0
                for k in keys:
                    while (canonical_idx < len(canonical)
                           and canonical[canonical_idx] != k):
                        canonical_idx += 1
                    if canonical_idx >= len(canonical):
                        pytest.fail(
                            f"radius PropGroup not in canonical order: "
                            f"{group_body}"
                        )
                    canonical_idx += 1

    def test_eid_collision_appends_dash_n_suffix(self) -> None:
        """Agent-1 Finding #1: two siblings with the same sanitized
        name should produce `#nav-top-nav` and `#nav-top-nav-2`, NOT
        `#nav-top-nav` and `#frame-2`."""
        fake_spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {"sizing": {"width": 100, "height": 100}},
                    "children": ["frame-1", "frame-2"],
                },
                "frame-1": {
                    "type": "frame",
                    "_original_name": "Shared Name",
                    "layout": {"sizing": {"width": 50, "height": 50}},
                },
                "frame-2": {
                    "type": "frame",
                    "_original_name": "Shared Name",
                    "layout": {"sizing": {"width": 50, "height": 50}},
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }
        doc = compress_to_l3(fake_spec, conn=None)
        emitted = emit_l3(doc)
        assert "#shared-name " in emitted
        assert "#shared-name-2 " in emitted


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_stage1_expected_snapshot(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """Freeze the compressor's current output per reference screen.

    Regressions manifest as diff between the fresh emit and the
    committed `stage1-expected.dd` snapshot. This is the Stage 1
    regression baseline until the Stage 3 synthetic-token pass lands
    — see L0↔L3 §2.11 for the two-track oracle model.
    """
    import os
    spec = generate_ir(db_conn, screen_id, semantic=True, filter_chrome=False)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)
    emitted = emit_l3(doc)
    path = _snapshot_path(slug)

    if os.environ.get("COMPRESS_L3_UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.write_text(emitted)
        if not path.exists():                  # shouldn't happen, but guard
            pytest.skip(f"wrote new snapshot: {path}")
        return

    expected = path.read_text()
    if emitted != expected:
        # Produce a short diff hint for humans
        e_lines = expected.splitlines()
        a_lines = emitted.splitlines()
        diff = []
        for i, (e, a) in enumerate(zip(e_lines, a_lines)):
            if e != a:
                diff.append(f"  line {i+1}:")
                diff.append(f"    expected: {e}")
                diff.append(f"    actual:   {a}")
                if len(diff) > 15:
                    break
        if len(a_lines) != len(e_lines):
            diff.append(f"  line count: expected {len(e_lines)}, got {len(a_lines)}")
        pytest.fail(
            f"snapshot drift on screen {screen_id} ({slug}):\n" +
            "\n".join(diff) +
            "\n(run with COMPRESS_L3_UPDATE_SNAPSHOTS=1 to accept)"
        )
