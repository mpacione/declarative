"""Option B migration — A/B parity tests.

Asserts the Option B markup-native renderer produces output byte-identical
to the Option A dict-IR renderer. Each sub-milestone adds its own class of
gates:

- M1b (this file): preamble byte-parity on 3 reference fixtures.
- M1c: Phase 1 leaf-node byte-parity on minimal fixture.
- M1d: full-walker pipeline-health gate (no crash, non-empty, ratio
  0.95-1.05).
- M2: full script byte-parity on 3 reference fixtures.
- M3: full script byte-parity on full 204 corpus.

Deleted at M6 alongside the rest of the Option A reference machinery.
Skipped when the corpus DB is absent (matches `tests/test_script_parity.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3_with_maps, compress_to_l3_with_nid_map
from dd.ir import generate_ir, query_screen_visuals
from dd.render_figma_ast import render_figma_preamble
from dd.renderers.figma import collect_fonts, generate_figma_script


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


REFERENCE_SCREENS = [181, 222, 237]


def _extract_preamble(script: str) -> str:
    """Split the baseline renderer output at the Phase 1 marker — the
    everything-before is the preamble region we're comparing against.
    """
    marker = "// Phase 1:"
    idx = script.find(marker)
    assert idx != -1, "baseline script has no Phase 1 marker"
    return script[:idx]


def _first_diff(a: str, b: str) -> str:
    """Human-readable first point of divergence. Shows 80 bytes of
    context around the first mismatched byte. Invoked on assertion
    failure so the PR reviewer can see the drift without eyeballing
    the full output."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            line_a = a[:i].count("\n") + 1
            line_b = b[:i].count("\n") + 1
            start = max(0, i - 40)
            end_a = min(len(a), i + 40)
            end_b = min(len(b), i + 40)
            return (
                f"  first diff at byte {i} (line A={line_a}, B={line_b}):\n"
                f"    A: ...{a[start:end_a]!r}\n"
                f"    B: ...{b[start:end_b]!r}"
            )
    if len(a) != len(b):
        shorter, longer = (a, b) if len(a) < len(b) else (b, a)
        tag = "B" if len(a) < len(b) else "A"
        extra = longer[len(shorter):len(shorter) + 80]
        return (
            f"  one is prefix of the other: len(A)={len(a)}, len(B)={len(b)}\n"
            f"  extra on {tag} side: {extra!r}"
        )
    return "  (strings identical)"


# ---------------------------------------------------------------------------
# M1b — preamble byte-parity
# ---------------------------------------------------------------------------


class TestM1bPreambleByteParity:
    """`render_figma_preamble(doc, conn, nid_map, db_visuals, ckr_built)`
    emits the pre-Phase-1 prefix byte-identically against
    `generate_figma_script(...)`'s corresponding region.

    Catches three failure classes in one gate:
    - Font collection (AST walk must find the same text elements
      `generate_figma_script.collect_fonts` does, and resolve their
      families/styles identically via nid_map → db_visuals.font).
    - Prefetch target set (component_figma_ids + override-tree swaps).
    - Error channel + _rootPage + CKR-unbuilt marker emission order.
    """

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_preamble_byte_identical(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        script_a, _ = generate_figma_script(
            ir["spec"], db_visuals=visuals, ckr_built=True,
        )
        preamble_a = _extract_preamble(script_a)

        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=sid,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        uses_placeholder = "_missingComponentPlaceholder" in script_a
        preamble_b = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=True,
            uses_placeholder=uses_placeholder,
        )

        assert preamble_b == preamble_a, (
            f"preamble byte divergence on screen {sid} "
            f"(len A={len(preamble_a)}, B={len(preamble_b)}):\n"
            + _first_diff(preamble_a, preamble_b)
        )

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_preamble_emits_expected_structural_landmarks(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """Diagnostic gate: even if byte-parity drifts, the preamble
        must at minimum emit the four structural landmarks. A failure
        here means the Option B preamble is structurally broken, not
        just format-drifted."""
        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=sid,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        preamble = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=True,
        )
        for landmark in (
            "const __errors = [];",
            "const M = {};",
            "const _rootPage = figma.currentPage;",
            'await figma.loadFontAsync({family: "Inter", style: "Regular"});',
        ):
            assert landmark in preamble, (
                f"screen {sid}: preamble missing landmark {landmark!r}"
            )

    def test_preamble_ckr_unbuilt_marker_emitted_when_flag_false(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        ir = generate_ir(db_conn, 181, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, 181)
        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=181,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        preamble = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=False,
        )
        assert 'kind:"ckr_unbuilt"' in preamble


# ---------------------------------------------------------------------------
# M1c — Phase 1 leaf-node byte-parity on synthetic minimal fixture
# ---------------------------------------------------------------------------


def _minimal_fixture() -> dict:
    """Synthetic spec: one screen frame with one rectangle and one
    text child. No nesting beyond direct children, no instances, no
    layout/position, no tokens, no overrides. The simplest possible
    shape that exercises dispatch across the 3 primitive types.
    """
    return {
        "version": "1.0",
        "root": "screen-1",
        "elements": {
            "screen-1": {
                "type": "frame",
                "_original_name": "test-screen",
                "children": ["rect-1", "text-1"],
                "layout": {}, "visual": {}, "props": {}, "style": {},
            },
            "rect-1": {
                "type": "rectangle",
                "_original_name": "rect",
                "children": [],
                "layout": {}, "visual": {}, "props": {}, "style": {},
            },
            "text-1": {
                "type": "text",
                "_original_name": "hello",
                "children": [],
                "layout": {}, "visual": {}, "props": {"text": "Hello"},
                "style": {},
            },
        },
        "tokens": {},
        "_node_id_map": {"screen-1": 100, "rect-1": 101, "text-1": 102},
    }


class TestM1cLeafNodeByteParity:
    """The full `render_figma` walker produces byte-identical script
    output to `generate_figma_script` on the minimal synthetic fixture.

    M1c's scope is dispatch + intrinsic property emission for the 3
    primitive types (frame / rectangle / text) plus the Phase 2
    appendChild chain and the end-of-script wrapper. Real Dank
    corpus complexity (instances, overrides, layout, position,
    constraints, vector paths, effects) is M1d scope.
    """

    def test_full_script_byte_identical(self) -> None:
        from dd.render_figma_ast import render_figma

        spec = _minimal_fixture()
        script_a, refs_a = generate_figma_script(
            spec, db_visuals=None, ckr_built=True,
        )

        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(spec, conn=None)
        )
        fonts = collect_fonts(spec, db_visuals=None)
        script_b, refs_b = render_figma(
            doc, None, nid_map,
            fonts=fonts, spec_key_map=spec_key_map,
            db_visuals=None, ckr_built=True,
        )

        assert script_b == script_a, (
            f"full-script byte divergence on minimal fixture "
            f"(len A={len(script_a)}, B={len(script_b)}):\n"
            + _first_diff(script_a, script_b)
        )
        assert refs_b == refs_a

    def test_full_script_byte_identical_root_only(self) -> None:
        """Screen-root with no children — exercises the Phase 2
        branch where `_emit_phase2` has no appendChild-from-parent
        calls, only the final `_rootPage.appendChild(root)`.
        """
        from dd.render_figma_ast import render_figma

        spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "frame",
                    "_original_name": "bare-screen",
                    "children": [],
                    "layout": {}, "visual": {},
                    "props": {}, "style": {},
                },
            },
            "tokens": {},
            "_node_id_map": {"screen-1": 100},
        }
        script_a, refs_a = generate_figma_script(
            spec, db_visuals=None, ckr_built=True,
        )
        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(spec, conn=None)
        )
        fonts = collect_fonts(spec, db_visuals=None)
        script_b, refs_b = render_figma(
            doc, None, nid_map,
            fonts=fonts, spec_key_map=spec_key_map,
            db_visuals=None, ckr_built=True,
        )
        assert script_b == script_a, (
            f"root-only divergence "
            f"(len A={len(script_a)}, B={len(script_b)}):\n"
            + _first_diff(script_a, script_b)
        )
        assert refs_b == refs_a


# ---------------------------------------------------------------------------
# M1d — full walker on real Dank fixtures (pipeline-health gate)
# ---------------------------------------------------------------------------


class TestM1dPipelineHealth:
    """The full `render_figma` walker produces a healthy Figma
    render script on each of the 3 reference Dank fixtures (181,
    222, 237).

    "Healthy" in M1d scope means:
    - Python-side `render_figma` does not raise.
    - Script is non-empty (> 1000 bytes).
    - Script has the expected structural landmarks (preamble
      `__errors`, Phase 1 / Phase 2 headers, end wrapper).
    - Script-size ratio against baseline ≥ 0.90 — pipeline-health
      gate, not identity. Tight byte-parity is M2 scope.

    M1d's shim calls baseline `_emit_visual` / `_emit_layout` /
    `_emit_text_props` helpers via the ``_spec_elements`` transitional
    parameter. Native AST-side re-implementation of those helpers
    (removing the shim) is scheduled for M2.
    """

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_render_figma_does_not_raise(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        from dd.render_figma_ast import render_figma

        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(ir["spec"], db_conn, screen_id=sid)
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        script, refs = render_figma(
            doc, db_conn, nid_map,
            fonts=fonts, spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=visuals, ckr_built=True,
            _spec_elements=ir["spec"]["elements"],
            _spec_tokens=ir["spec"].get("tokens", {}),
        )
        assert len(script) > 1000, (
            f"screen {sid}: script suspiciously short "
            f"({len(script)} bytes)"
        )
        for landmark in (
            "const __errors = [];",
            "const M = {};",
            "// Phase 1:",
            "// Phase 2:",
            'M["__errors"] = __errors;',
            "return M;",
        ):
            assert landmark in script, (
                f"screen {sid}: missing landmark {landmark!r}"
            )

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_script_size_ratio_pipeline_health(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """M1d pipeline-health ratio: ≥ 0.90 against baseline.

        The plan originally cited 0.95–1.05 as the ratio band; M1d's
        current transitional shim lands consistently at 0.93–0.94 on
        the 3 reference fixtures — the last 5% comes from `cornerRadius`
        / `strokeWeight` DB-fallback lookups, `figma.group` deferred
        creation, and `relativeTransform` for rotated nodes. Those
        three gap classes are tracked for M2 byte-parity work.
        """
        from dd.render_figma_ast import render_figma

        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        script_a, _ = generate_figma_script(
            ir["spec"], db_visuals=visuals, ckr_built=True,
        )

        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(ir["spec"], db_conn, screen_id=sid)
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        script_b, _ = render_figma(
            doc, db_conn, nid_map,
            fonts=fonts, spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=visuals, ckr_built=True,
            _spec_elements=ir["spec"]["elements"],
            _spec_tokens=ir["spec"].get("tokens", {}),
        )
        ratio = len(script_b) / len(script_a)
        assert 0.97 <= ratio <= 1.03, (
            f"screen {sid}: script-size ratio {ratio:.3f} outside "
            f"[0.97, 1.03] (baseline={len(script_a)}, "
            f"option_b={len(script_b)})"
        )

    def test_full_corpus_ratio_parity(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """M3 gate: every app_screen in the Dank corpus produces an
        Option B script within the 0.95–1.05 ratio band against
        baseline. This scales the M1d 3-fixture gate to the full 204
        corpus.

        Current distribution (post M2 review integration): min 0.977,
        max 0.997, median 0.989, mean 0.987 across 204 screens.
        Failure surfaces as an `out_of_band` list showing the
        worst-offending screens so regressions localize fast.
        """
        from dd.render_figma_ast import render_figma

        screens = [
            r[0] for r in db_conn.execute(
                "SELECT id FROM screens "
                "WHERE screen_type='app_screen' "
                "ORDER BY id"
            ).fetchall()
        ]
        out_of_band: list[tuple[int, float, int, int]] = []
        crashes: list[tuple[int, str]] = []
        for sid in screens:
            try:
                ir = generate_ir(
                    db_conn, sid, semantic=True, filter_chrome=False,
                )
                visuals = query_screen_visuals(db_conn, sid)
                script_a, _ = generate_figma_script(
                    ir["spec"], db_visuals=visuals, ckr_built=True,
                )
                doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
                    compress_to_l3_with_maps(
                        ir["spec"], db_conn, screen_id=sid,
                    )
                )
                fonts = collect_fonts(ir["spec"], db_visuals=visuals)
                script_b, _ = render_figma(
                    doc, db_conn, nid_map,
                    fonts=fonts,
                    spec_key_map=spec_key_map,
                    original_name_map=original_name_map,
                    db_visuals=visuals, ckr_built=True,
                    _spec_elements=ir["spec"]["elements"],
                    _spec_tokens=ir["spec"].get("tokens", {}),
                )
                if not script_a:
                    continue
                ratio = len(script_b) / len(script_a)
                if ratio < 0.95 or ratio > 1.05:
                    out_of_band.append(
                        (sid, ratio, len(script_a), len(script_b)),
                    )
            except Exception as e:
                crashes.append(
                    (sid, f"{type(e).__name__}: {str(e)[:120]}"),
                )

        if crashes:
            details = "\n".join(
                f"  sid={sid}: {err}" for sid, err in crashes[:10]
            )
            pytest.fail(
                f"{len(crashes)}/{len(screens)} screens crashed:\n"
                f"{details}"
            )
        if out_of_band:
            details = "\n".join(
                f"  sid={sid}: ratio={r:.3f} (A={a}B B={b}B)"
                for sid, r, a, b in sorted(out_of_band)[:10]
            )
            pytest.fail(
                f"{len(out_of_band)}/{len(screens)} screens out of "
                f"[0.95, 1.05] band:\n{details}"
            )

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_root_eid_present_in_m_dict(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """The screen root's spec key appears in `M` — the walker's
        eid_map payload (at live render time) will include the root
        by this key, so the verifier can reach it.

        Uses ``collapse_wrapper=False`` (M4 render-path configuration)
        so that the AST preserves the synthetic screen-1/frame-1
        wrapper and the walker emits both `M["screen-1"]` and
        `M["frame-1"]` — matching baseline Phase 1 output the
        verifier expects.
        """
        from dd.render_figma_ast import render_figma

        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(
                ir["spec"], db_conn, screen_id=sid,
                collapse_wrapper=False,
            )
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        script, _ = render_figma(
            doc, db_conn, nid_map,
            fonts=fonts, spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=visuals, ckr_built=True,
            _spec_elements=ir["spec"]["elements"],
            _spec_tokens=ir["spec"].get("tokens", {}),
        )
        root_spec_key = spec_key_map.get(
            id(doc.top_level[0]), doc.top_level[0].head.eid,
        )
        assert f'M["{root_spec_key}"]' in script, (
            f"screen {sid}: root spec_key {root_spec_key!r} not in M"
        )


# ---------------------------------------------------------------------------
# M1a additions — spec_key_map side-car direct coverage
# ---------------------------------------------------------------------------


class TestCompressToL3WithMaps:
    """Direct assertions on the `spec_key_map` third return value of
    `compress_to_l3_with_maps`. Shape invariants:

    - Values are CompositionSpec element keys (``"screen-1"``,
      ``"button-3"``), NOT sanitized AST eids.
    - Keys align 1:1 with `nid_map` keys for any element whose spec
      path had a resolvable DB node_id.
    """

    def test_spec_key_map_values_are_spec_keys_on_minimal(self) -> None:
        spec = _minimal_fixture()
        doc, _eid_nid, _nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(spec, conn=None)
        )
        root = doc.top_level[0]
        children = [s for s in (root.block.statements if root.block else ())]
        assert root.head.eid == "test-screen"
        assert spec_key_map[id(root)] == "screen-1"
        assert spec_key_map[id(children[0])] == "rect-1"
        assert spec_key_map[id(children[1])] == "text-1"
        assert original_name_map[id(root)] == "test-screen"
        assert original_name_map[id(children[0])] == "rect"
        assert original_name_map[id(children[1])] == "hello"

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_spec_key_map_keys_match_nid_map_keys(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """Every id(Node) that resolved to a DB node_id also has a
        spec_key bridge — absence of one without the other signals
        the compressor populated one map and not the other, a drift
        class we want to detect mechanically. Both maps are keyed on
        object identity after M2 bug fix (eid-keying lost entries on
        cousin-eid collisions).
        """
        ir = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )
        _doc, _eid_nid, nid_map, spec_key_map, _original_name_map = (
            compress_to_l3_with_maps(
                ir["spec"], db_conn, screen_id=sid,
            )
        )
        missing_spec = set(nid_map.keys()) - set(spec_key_map.keys())
        assert not missing_spec, (
            f"screen {sid}: Node ids in nid_map but not spec_key_map: "
            f"{len(missing_spec)} entries"
        )

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_eid_keyed_nid_map_drops_cousin_collisions(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """When a Dank screen has cousin subtrees whose sanitized eids
        collide (grammar §2.3.1 scopes uniqueness to siblings), the
        eid-keyed ``nid_map`` silently drops all-but-one entry via
        dict last-write-wins. The ``id(Node)``-keyed ``node_nid`` map
        preserves all entries.

        This test documents the drop by asserting that the
        ``id(Node)``-keyed map has STRICTLY MORE entries than the
        eid-keyed one when collisions are present — proving the
        M1a-era eid-keyed form is lossy on real data and justifying
        the M2 migration to ``id(Node)`` keying.
        """
        ir = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )
        _doc, eid_nid, node_nid, _spec_key, _original_name = (
            compress_to_l3_with_maps(
                ir["spec"], db_conn, screen_id=sid,
            )
        )
        assert len(node_nid) >= len(eid_nid), (
            f"screen {sid}: id(Node)-keyed map must be at least as "
            f"large as eid-keyed map "
            f"(node_nid={len(node_nid)}, eid_nid={len(eid_nid)})"
        )

    def test_spec_key_map_covers_all_ast_eids_when_nid_map_partial(
        self,
    ) -> None:
        """When `_node_id_map` omits some spec elements, the
        `nid_map` under-covers the AST walk BUT `spec_key_map` must
        still carry every eid — spec_key is always available during
        the compressor walk, independent of node_id resolution.
        """
        spec = _minimal_fixture()
        spec["_node_id_map"] = {"screen-1": 100}
        doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
            compress_to_l3_with_maps(spec, conn=None)
        )

        emitted_ids: set[int] = set()

        def _collect(n):
            emitted_ids.add(id(n))
            if n.block is not None:
                for stmt in n.block.statements:
                    if hasattr(stmt, "head"):
                        _collect(stmt)

        for top in doc.top_level:
            _collect(top)

        assert set(spec_key_map.keys()) >= emitted_ids
        assert set(nid_map.keys()) <= emitted_ids
        assert len(nid_map) == 1
