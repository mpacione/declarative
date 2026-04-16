"""Unit tests for the unified Plugin-API extraction pass.

Consolidation of supplement + 4x targeted walks (perf pt 6 #3). The
script generator must:

- Emit every Plugin-only field set from the old passes exactly once.
- Keep the top-level keys namespace-scoped so the existing apply_*
  dispatchers can be reused unchanged.
- Gate per-node-type checks (TEXT-only fields on TEXT nodes, VECTOR-only
  geometry on vector types) so the walker runtime doesn't waste calls.
- Default to skipping the expensive getMainComponentAsync per INSTANCE;
  opt-in restores the old behaviour for callers that didn't run REST
  ingest with the components map.
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.mark.unit
class TestUnifiedScriptGenerator:
    def test_script_is_generated_and_valid_js_shape(self):
        from dd.extract_plugin import generate_plugin_script

        script = generate_plugin_script(["1:1", "2:2"])

        # Smoke check that the screen IDs are embedded.
        assert '"1:1"' in script
        assert '"2:2"' in script

        # Single walker function (not four).
        assert script.count("async function walkNode") == 1

        # Single top-level loop over screenIds.
        assert script.count("for (const sid of screenIds)") == 1

    def test_all_field_slices_present(self):
        """Every pass's field keys must appear in the unified script."""
        from dd.extract_plugin import generate_plugin_script

        script = generate_plugin_script(["1:1"])

        expected_keys = [
            # supplement slice
            "entry.lp", "entry.gr", "entry.gc", "entry.gt", "entry.ov",
            # properties slice (gated assignments, matched via flag setters)
            "entry.m = 1", "entry.bo", "entry.cs", "entry.ad",
            # sizing slice
            "entry.lsh", "entry.lsv", "entry.lw",
            "entry.tar", "entry.fst", "entry.tc", "entry.td", "entry.ps",
            # transforms slice
            "entry.w", "entry.h", "entry.rt", "entry.vp", "entry.ot",
            # vector-geometry slice
            "entry.fg", "entry.sg",
        ]
        for key in expected_keys:
            assert key in script, f"expected field {key!r} to be emitted by unified script"

    def test_component_key_lookup_off_by_default(self):
        """Default: skip getMainComponentAsync per INSTANCE (REST handles it)."""
        from dd.extract_plugin import generate_plugin_script

        script = generate_plugin_script(["1:1"])

        # The async call appears ONLY in the override swap-detection code,
        # not for populating entry.ck on the top-level instance.
        assert "entry.ck = main.key" not in script

    def test_component_key_lookup_opt_in(self):
        """Explicit opt-in restores the old per-INSTANCE lookup."""
        from dd.extract_plugin import generate_plugin_script

        script = generate_plugin_script(["1:1"], collect_component_key=True)

        assert "entry.ck = main.key" in script

    def test_single_screen_mode(self):
        """Auto-halving retry eventually drops to a 1-element batch."""
        from dd.extract_plugin import generate_plugin_script

        script = generate_plugin_script(["5749:100629"])
        assert '"5749:100629"' in script

    def test_slice_light_omits_heavy_fields(self):
        """'light' slice excludes rt/vp/fg/sg/ot so the result JSON fits
        under Figma's ~64KB PROXY_EXECUTE buffer."""
        from dd.extract_plugin import generate_plugin_script, SLICE_LIGHT

        script = generate_plugin_script(["1:1"], slice=SLICE_LIGHT)

        # Light fields present.
        assert "entry.lsh" in script
        assert "entry.m = 1" in script
        assert "entry.fst" in script

        # Heavy fields absent.
        assert "entry.rt" not in script
        assert "entry.vp" not in script
        assert "entry.fg" not in script
        assert "entry.sg" not in script
        assert "entry.ot" not in script

    def test_slice_heavy_omits_light_fields(self):
        """'heavy' slice excludes sizing/typography/overrides/etc."""
        from dd.extract_plugin import generate_plugin_script, SLICE_HEAVY

        script = generate_plugin_script(["1:1"], slice=SLICE_HEAVY)

        # Heavy fields present.
        assert "entry.rt" in script
        assert "entry.vp" in script
        assert "entry.fg" in script
        assert "entry.sg" in script

        # Light fields absent.
        assert "entry.lsh" not in script
        assert "entry.lp" not in script
        assert "entry.m = 1" not in script
        assert "entry.fst" not in script

    def test_slice_all_is_default_and_unions(self):
        from dd.extract_plugin import generate_plugin_script, SLICE_ALL

        default_script = generate_plugin_script(["1:1"])
        all_script = generate_plugin_script(["1:1"], slice=SLICE_ALL)

        assert default_script == all_script
        # Light + heavy fields both present.
        assert "entry.lsh" in all_script
        assert "entry.rt" in all_script


def _make_empty_nodes_schema(conn: sqlite3.Connection) -> None:
    """Minimal schema subset that apply_plugin touches."""
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            figma_node_id TEXT UNIQUE,
            screen_id INTEGER NOT NULL,
            parent_id INTEGER,
            name TEXT NOT NULL,
            node_type TEXT NOT NULL,
            depth INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_semantic INTEGER NOT NULL DEFAULT 0,
            -- columns the apply_* functions write to
            layout_positioning TEXT,
            component_key TEXT,
            grid_row_count INTEGER,
            grid_column_count INTEGER,
            grid_row_gap REAL,
            grid_column_gap REAL,
            grid_row_sizes TEXT,
            grid_column_sizes TEXT,
            is_mask INTEGER,
            boolean_operation TEXT,
            corner_smoothing REAL,
            arc_data TEXT,
            layout_sizing_h TEXT,
            layout_sizing_v TEXT,
            text_auto_resize TEXT,
            font_style TEXT,
            text_case TEXT,
            text_decoration TEXT,
            paragraph_spacing REAL,
            layout_wrap TEXT,
            width REAL,
            height REAL,
            relative_transform TEXT,
            opentype_features TEXT,
            vector_paths TEXT,
            fill_geometry TEXT,
            stroke_geometry TEXT,
            fills TEXT
        );
        CREATE TABLE instance_overrides (
            id INTEGER PRIMARY KEY,
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            property_type TEXT NOT NULL,
            property_name TEXT NOT NULL,
            override_value TEXT,
            UNIQUE(node_id, property_name)
        );
    """)
    conn.commit()


@pytest.mark.unit
class TestApplyPluginDispatch:
    """Unified results dispatch to their correct target columns."""

    def test_empty_payload_returns_zero_counts(self):
        from dd.extract_plugin import apply_plugin

        conn = sqlite3.connect(":memory:")
        _make_empty_nodes_schema(conn)

        counts = apply_plugin(conn, {})

        assert counts["total_nodes_touched"] == 0
        # Zero of every slice.
        for key in (
            "component_key", "layout_positioning", "grid", "overrides",
            "is_mask", "boolean_operation", "corner_smoothing", "arc_data",
            "layout_sizing_h", "layout_sizing_v", "text_auto_resize", "font_style",
            "text_decoration", "layout_wrap",
            "relative_transform", "opentype_features", "width_height", "vector_paths",
            "fill_geometry", "stroke_geometry",
        ):
            assert counts[key] == 0, f"expected 0 for {key}, got {counts[key]}"

    def test_run_plugin_extract_builds_vector_asset_store(self, monkeypatch):
        """Regression guard: the unified pass must rebuild the
        content-addressed asset store after collecting fill/stroke
        geometries. Without this, VECTOR nodes render as
        KIND_MISSING_ASSET even though nodes.fill_geometry is populated.

        The old ``extract_targeted --mode vector-geometry`` ran
        ``process_vector_geometry`` as its last step; the unified pass
        must do the same.
        """
        from dd.extract_plugin import run_plugin_extract
        import dd.extract_plugin as mod
        import dd.extract_assets as assets_mod

        called = {"count": 0}

        def fake_process(conn):
            called["count"] += 1
            return 42

        monkeypatch.setattr(assets_mod, "process_vector_geometry", fake_process)

        conn = sqlite3.connect(":memory:")
        _make_empty_nodes_schema(conn)
        # Need a screens table for the query in run_plugin_extract
        conn.executescript("""
            CREATE TABLE screens (
                id INTEGER PRIMARY KEY,
                figma_node_id TEXT,
                name TEXT,
                screen_type TEXT
            );
            INSERT INTO screens (figma_node_id, name, screen_type)
            VALUES ('1:1', 'Test', 'app_screen');
        """)
        conn.commit()

        def fake_exec(script):
            return {}  # no nodes touched

        totals = run_plugin_extract(conn, fake_exec, batch_size=1, delay=0.0)

        assert called["count"] == 1, (
            "process_vector_geometry must be called exactly once "
            "after run_plugin_extract finishes."
        )
        assert totals.get("vector_assets_built") == 42

    def test_full_slice_payload_writes_to_expected_columns(self):
        from dd.extract_plugin import apply_plugin

        conn = sqlite3.connect(":memory:")
        _make_empty_nodes_schema(conn)
        conn.execute(
            "INSERT INTO nodes (figma_node_id, screen_id, name, node_type) "
            "VALUES (?, ?, ?, ?)",
            ("1:42", 1, "button/primary", "INSTANCE"),
        )
        conn.commit()

        data = {
            "1:42": {
                # supplement
                "lp": "ABSOLUTE",
                "ck": "key-abc",
                # properties
                "m": 1,
                "cs": 0.6,
                # sizing
                "lsh": "FILL",
                "lsv": "HUG",
                "lw": "WRAP",
                # transforms
                "w": 320.0,
                "h": 48.0,
                "rt": [[1.0, 0.0, 10.0], [0.0, 1.0, 20.0]],
            }
        }

        counts = apply_plugin(conn, data)

        row = conn.execute(
            "SELECT layout_positioning, component_key, is_mask, corner_smoothing, "
            "layout_sizing_h, layout_sizing_v, layout_wrap, width, height, relative_transform "
            "FROM nodes WHERE figma_node_id = ?", ("1:42",),
        ).fetchone()

        assert row[0] == "ABSOLUTE"
        assert row[1] == "key-abc"
        assert row[2] == 1
        assert row[3] == 0.6
        assert row[4] == "FILL"
        assert row[5] == "HUG"
        assert row[6] == "WRAP"
        assert row[7] == 320.0
        assert row[8] == 48.0
        assert "1.0" in (row[9] or "")

        # Counters across slices.
        assert counts["layout_positioning"] == 1
        assert counts["component_key"] == 1
        assert counts["is_mask"] == 1
        assert counts["corner_smoothing"] == 1
        assert counts["layout_sizing_h"] == 1
        assert counts["layout_wrap"] == 1
        assert counts["width_height"] == 1
        assert counts["relative_transform"] == 1
        assert counts["total_nodes_touched"] == 1
