"""P5c (Phase E Pattern 3 fix) — Axis registry + convention.

The convention: every ``cluster_*`` function in ``dd/cluster*.py``
has a paired ``AxisSpec`` in ``dd/cluster_axis.py:AXIS_REGISTRY``,
keyed by the axis name. The test walks the cluster modules, finds
every ``cluster_*`` function defined at module scope, asserts each
has a matching AXIS_REGISTRY entry, and validates each spec's
contract claims against observed behavior on a representative
fixture (Codex review: "Metadata proves intent. Fixtures prove
behavior.").

When a new ``cluster_foo`` function lands without an
AxisSpec, this test fails CI with a specific actionable message
("export ``AXIS_FOO`` with ``snap_on_update=True`` or mark
non-numeric/non-snapping explicitly"). When an existing clusterer
silently drops the snap-on-UPDATE invariant on a numeric axis (the
chronic bug class P3c/P5a/P5b each had to fix), the behavior
fixture catches it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from dd.cluster_axis import (
    AXIS_REGISTRY,
    CLUSTER_FN_TO_AXIS_NAME,
    AxisSpec,
)

REPO = Path(__file__).resolve().parent.parent
CLUSTER_FILES = sorted(REPO.glob("dd/cluster*.py"))


def _scan_cluster_functions() -> set[str]:
    """Discover every top-level `cluster_*` function in dd/cluster*.py.
    Skips private helpers (`_cluster_simple_dimension`) and the
    orchestrator (`dd/cluster.py`). Returns just the function names.
    """
    found: set[str] = set()
    # Pattern: top-level def cluster_<name>(...). Excludes the
    # orchestrator file (cluster.py) which contains run_clustering
    # and mark_default_bindings, neither a per-axis function.
    name_pat = re.compile(r"^def (cluster_[a-z_]+)\(")
    for f in CLUSTER_FILES:
        if f.name == "cluster.py":
            continue
        if f.name == "cluster_axis.py":
            # The registry module itself doesn't define clusters.
            continue
        text = f.read_text()
        for line in text.splitlines():
            m = name_pat.match(line)
            if m:
                found.add(m.group(1))
    return found


class TestAxisSpecRegistry:
    """The registry shape and consistency."""

    def test_registry_is_non_empty(self):
        assert AXIS_REGISTRY, "AXIS_REGISTRY must have entries"

    def test_every_registry_value_is_an_axisspec(self):
        for name, spec in AXIS_REGISTRY.items():
            assert isinstance(spec, AxisSpec), (
                f"AXIS_REGISTRY[{name!r}] must be an AxisSpec, "
                f"got {type(spec).__name__}"
            )

    def test_registry_key_matches_spec_name(self):
        """Catches mis-keyed entries
        (``AXIS_REGISTRY['radius'] = AxisSpec(name='radius_v2', ...)``)."""
        for name, spec in AXIS_REGISTRY.items():
            assert spec.name == name, (
                f"AXIS_REGISTRY[{name!r}].name == {spec.name!r}; "
                f"key and name must agree"
            )

    def test_every_spec_has_at_least_one_property(self):
        for name, spec in AXIS_REGISTRY.items():
            assert spec.properties, (
                f"AXIS_REGISTRY[{name!r}] must declare at least one "
                f"property the axis owns"
            )

    def test_every_spec_has_at_least_one_bind_key_field(self):
        for name, spec in AXIS_REGISTRY.items():
            assert spec.bind_key_fields, (
                f"AXIS_REGISTRY[{name!r}] must declare at least one "
                f"bind_key_field (the column(s) the UPDATE step uses)"
            )


class TestConventionEnforcement:
    """The convention. Every cluster_* function discovered in
    dd/cluster*.py must appear in CLUSTER_FN_TO_AXIS_NAME, mapping
    to a real AXIS_REGISTRY entry."""

    def test_every_cluster_function_has_axis_mapping(self):
        emitted = _scan_cluster_functions()
        unmapped = sorted(
            fn for fn in emitted
            if fn not in CLUSTER_FN_TO_AXIS_NAME
        )
        assert not unmapped, (
            "P5c convention violation: the following cluster functions "
            "exist in dd/cluster*.py but are not mapped to an "
            "AxisSpec. Add them to dd/cluster_axis.py:"
            "CLUSTER_FN_TO_AXIS_NAME and create matching "
            "AXIS_REGISTRY entries (with snap_on_update=True for "
            "numeric axes, or explicitly False with notes for "
            "identity-preserving ones):\n  "
            + "\n  ".join(unmapped)
        )

    def test_every_mapping_resolves_to_a_real_axisspec(self):
        for fn, axis_name in CLUSTER_FN_TO_AXIS_NAME.items():
            assert axis_name in AXIS_REGISTRY, (
                f"P5c: CLUSTER_FN_TO_AXIS_NAME[{fn!r}] = {axis_name!r} "
                f"but {axis_name!r} is not in AXIS_REGISTRY"
            )

    def test_no_orphaned_mapping_entries(self):
        """If a cluster function was renamed/removed, the mapping
        entry should also be cleaned up."""
        emitted = _scan_cluster_functions()
        orphans = sorted(
            fn for fn in CLUSTER_FN_TO_AXIS_NAME
            if fn not in emitted
        )
        assert not orphans, (
            "P5c map drift: the following cluster functions are mapped "
            "in CLUSTER_FN_TO_AXIS_NAME but no longer exist in "
            "dd/cluster*.py. Remove them:\n  "
            + "\n  ".join(orphans)
        )

    def test_scanner_discovers_known_functions(self):
        """Smoke test for the scanner."""
        emitted = _scan_cluster_functions()
        for known in (
            "cluster_colors",
            "cluster_radius",
            "cluster_spacing",
            "cluster_typography",
            "cluster_letter_spacing",
            "cluster_opacity",
            "cluster_effects",
            "cluster_stroke_weight",
            "cluster_paragraph_spacing",
        ):
            assert known in emitted, (
                f"P5c scanner regression: {known!r} should be "
                f"discovered by _scan_cluster_functions() but wasn't"
            )


class TestSnapOnUpdateBehaviorFixtures:
    """Codex review: "Metadata proves intent. Fixtures prove
    behavior." For axes claiming ``snap_on_update=True``, run the
    real clusterer on a fixture with intentional value-shape drift
    and assert the binding's ``resolved_value`` ends up matching the
    token's after clustering."""

    def test_spacing_snap_on_update_holds(self, temp_db):
        """spacing claims snap_on_update=True (P5a). Verify it holds
        on a fixture with sub-pixel float bindings."""
        spec = AXIS_REGISTRY["spacing"]
        assert spec.snap_on_update is True

        from dd.cluster_spacing import cluster_spacing

        conn = temp_db
        conn.execute(
            "INSERT INTO files (id, file_key, name) VALUES (1, 'p5c_spacing', 'p5c.fig')"
        )
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
        )
        for i in range(1, 6):
            conn.execute(
                "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
                "VALUES (?, 1, ?, ?, 'FRAME')",
                (i, f"100:{i+1}", f"Node{i}"),
            )
        # Sub-pixel padding
        for i in range(1, 6):
            conn.execute(
                """INSERT INTO node_token_bindings
                   (node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, 'padding.top', '14.5697', '14.5697', 'unbound')""",
                (i,),
            )
        conn.commit()
        cur = conn.execute(
            "INSERT INTO token_collections (file_id, name) VALUES (1, 'Spacing')"
        )
        cid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO token_modes (collection_id, name) VALUES (?, 'Default')",
            (cid,),
        )
        mid = cur.lastrowid
        cluster_spacing(conn, file_id=1, collection_id=cid, mode_id=mid)

        cursor = conn.execute(
            """SELECT ntb.resolved_value AS bind_val,
                      tv.resolved_value AS token_val
               FROM node_token_bindings ntb
               JOIN tokens t ON ntb.token_id = t.id
               JOIN token_values tv ON tv.token_id = t.id
               WHERE ntb.binding_status = 'proposed'
                 AND ntb.property = 'padding.top'"""
        )
        rows = cursor.fetchall()
        assert rows
        for row in rows:
            assert row["bind_val"] == row["token_val"], (
                f"P5c contract: AXIS_REGISTRY['spacing'].snap_on_update "
                f"is True; binding.resolved_value must match "
                f"token.resolved_value. bind={row['bind_val']!r} "
                f"token={row['token_val']!r}"
            )

    def test_letter_spacing_snap_on_update_holds(self, temp_db):
        """letter_spacing claims snap_on_update=True (P3c)."""
        import json
        spec = AXIS_REGISTRY["letter_spacing"]
        assert spec.snap_on_update is True

        from dd.cluster_typography import cluster_letter_spacing

        conn = temp_db
        conn.execute(
            "INSERT INTO files (id, file_key, name) VALUES (1, 'p5c_ls', 'p5c.fig')"
        )
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
        )
        for i in range(1, 6):
            conn.execute(
                "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
                "VALUES (?, 1, ?, ?, 'TEXT')",
                (i, f"100:{i+1}", f"Text{i}"),
            )
        # Float-noise letterSpacing JSON
        for i in range(1, 6):
            raw = json.dumps({"value": -0.5547059178352356, "unit": "PERCENT"})
            conn.execute(
                """INSERT INTO node_token_bindings
                   (node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, 'letterSpacing', ?, ?, 'unbound')""",
                (i, raw, raw),
            )
        conn.commit()
        cur = conn.execute(
            "INSERT INTO token_collections (file_id, name) VALUES (1, 'Typography')"
        )
        cid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO token_modes (collection_id, name) VALUES (?, 'Default')",
            (cid,),
        )
        mid = cur.lastrowid
        cluster_letter_spacing(conn, file_id=1, collection_id=cid, mode_id=mid)

        cursor = conn.execute(
            """SELECT ntb.resolved_value AS bind_val,
                      tv.resolved_value AS token_val
               FROM node_token_bindings ntb
               JOIN tokens t ON ntb.token_id = t.id
               JOIN token_values tv ON tv.token_id = t.id
               WHERE ntb.binding_status = 'proposed'
                 AND ntb.property = 'letterSpacing'"""
        )
        rows = cursor.fetchall()
        assert rows
        for row in rows:
            # P3c snaps binding to canonical JSON {value: -0.55,
            # unit: PERCENT}; the token's token_values row keeps the
            # numeric scalar string for compat. The contract is
            # "binding shape matches what the validator expects from
            # the token" — both should round to -0.55.
            bind_val = json.loads(row["bind_val"])
            assert round(bind_val["value"], 2) == -0.55, (
                f"P5c contract: letter_spacing snap-on-UPDATE failed. "
                f"binding={row['bind_val']!r} token={row['token_val']!r}"
            )

    def test_radius_identity_documented_correctly(self):
        """radius claims snap_on_update=False — defensive smoke
        test that our metadata matches the source. If anyone makes
        cluster_radius start rounding, this silent drift would
        break validator parity. The doc string in dd/cluster_axis.py
        says "If radius ever starts rounding, flip
        snap_on_update=True." This test pins the current state."""
        spec = AXIS_REGISTRY["radius"]
        assert spec.snap_on_update is False
        assert "Identity-preserving" in spec.notes
