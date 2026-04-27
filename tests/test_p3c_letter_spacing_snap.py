"""P3c (Phase E C1 fix) — cluster_letter_spacing snap-on-UPDATE pattern.

Phase E §2 found 7 binding_token_consistency warnings on Nouns. Both
analysts found this is THREE distinct bugs with the same shape; P3c
addresses the dominant one (4 of 7 warnings, 67 of 99 bindings):
`cluster_letter_spacing` had a storage-shape mismatch.

Pre-P3c:
- token_values.resolved_value stored as `str(rounded)`, e.g. `"-0.55"`
- node_token_bindings.resolved_value stayed as raw JSON
  `{"value": -0.5547..., "unit": "PIXELS"}` even after being assigned
  to the token (the UPDATE matched WHERE resolved_value=raw, but didn't
  SET resolved_value=canonical)
- Validator's `_normalize_numeric` saw `-0.5547... != -0.55` →
  `binding_token_consistency` warning

cluster_colors solved this correctly (line 289-295): the UPDATE
includes `resolved_value = ?` setting binding's resolved_value to
the bucket representative, so post-merge values are consistent.

P3c ports the snap-on-UPDATE pattern, with two additions:
- Bucket census by `(rounded, unit)` pair, not just rounded value —
  PIXELS and PERCENT letterSpacing are NOT interchangeable. Codex
  catch.
- Snap binding.resolved_value to canonical JSON
  `{"value": rounded, "unit": original_unit}` — preserves binding
  shape (downstream readers expect JSON), uses rounded value
  (validator sees match).

float-noise-sibling collapse:
- Pre-P3c, two raw bindings -0.5547 and -0.5495 each got their own
  token (tracking.snug2 + tracking.snug3) because they were
  separate census rows.
- Post-P3c, both round to -0.55 with the same unit → same bucket →
  one token + both bindings snap to the canonical resolved_value.
"""

from __future__ import annotations

import json

import pytest

from dd.cluster_typography import cluster_letter_spacing, ensure_typography_collection


@pytest.fixture
def letter_spacing_db(temp_db):
    """Seed a temp DB with letter-spacing bindings that exercise the
    bug class: float-noise siblings, mixed units, and a zero (which
    must be skipped per existing logic)."""
    conn = temp_db
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'p3c_test', 'p3c.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
    )
    for i in range(1, 21):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (?, 1, ?, ?, 'TEXT')",
            (i, f"100:{i+1}", f"Text{i}"),
        )
    # Float-noise siblings — three different raw values that all round
    # to -0.55 with PIXELS unit. Pre-P3c: 3 separate tokens. Post-P3c:
    # 1 bucket / 1 token / all 6 bindings snap.
    siblings_pixels = [
        (1, '{"value": -0.5547059178352356, "unit": "PIXELS"}'),
        (2, '{"value": -0.5547059178352356, "unit": "PIXELS"}'),
        (3, '{"value": -0.5495, "unit": "PIXELS"}'),
        (4, '{"value": -0.5495, "unit": "PIXELS"}'),
        (5, '{"value": -0.5510, "unit": "PIXELS"}'),
        (6, '{"value": -0.5510, "unit": "PIXELS"}'),
    ]
    # Same rounded value (-0.55) but different unit → MUST stay in
    # separate bucket. Codex sharp catch.
    siblings_percent = [
        (7, '{"value": -0.5510, "unit": "PERCENT"}'),
        (8, '{"value": -0.5510, "unit": "PERCENT"}'),
    ]
    # Distinct positive value to exercise the wide-label path.
    pos = [
        (9, '{"value": 1.5, "unit": "PIXELS"}'),
        (10, '{"value": 1.5, "unit": "PIXELS"}'),
    ]
    # Zero → must be skipped (default; existing behavior preserved).
    zeros = [
        (11, '{"value": 0, "unit": "PIXELS"}'),
        (12, '{"value": 0, "unit": "PIXELS"}'),
    ]
    for nid, raw in siblings_pixels + siblings_percent + pos + zeros:
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'letterSpacing', ?, ?, 'unbound')""",
            (nid, raw, raw),
        )
    conn.commit()
    yield conn


class TestFloatNoiseSiblingsCollapse:
    """The headline P3c outcome: raw values that round to the same
    (value, unit) get collapsed into ONE token, not N tokens."""

    def test_three_raw_pixel_values_become_one_token(self, letter_spacing_db):
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        result = cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # Pre-P3c: 3 different raw PIXEL values → 3 tokens (snug, snug2,
        # snug3 with idx-driven labels). Post-P3c: 1 bucket → 1 token.
        # Plus 1 token for the PERCENT bucket and 1 for the +1.5 PIXEL
        # bucket = 3 total tokens.
        assert result["tokens_created"] == 3, (
            f"P3c float-noise-sibling collapse: expected 3 tokens "
            f"(1 PIXEL bucket for -0.55, 1 PERCENT bucket for -0.55, "
            f"1 PIXEL bucket for +1.5). Got: {result!r}"
        )

    def test_all_pixel_siblings_assigned_to_same_token(self, letter_spacing_db):
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # All 6 PIXEL siblings (nodes 1-6) should share the SAME token_id.
        cursor = letter_spacing_db.execute(
            """SELECT DISTINCT token_id FROM node_token_bindings
               WHERE node_id IN (1, 2, 3, 4, 5, 6)
                 AND property = 'letterSpacing'
                 AND token_id IS NOT NULL"""
        )
        token_ids = [row[0] for row in cursor.fetchall()]
        assert len(token_ids) == 1, (
            f"P3c: all 6 PIXEL siblings should share one token. "
            f"Got distinct token_ids: {token_ids}"
        )


class TestSnapOnUpdate:
    """The validator-fix part of P3c: binding.resolved_value is now
    canonical JSON `{"value": rounded, "unit": original_unit}` — not
    raw float JSON."""

    def test_binding_resolved_value_snapped_to_canonical(
        self, letter_spacing_db,
    ):
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # Read back the resolved_value of any node 1-6 (PIXEL siblings).
        cursor = letter_spacing_db.execute(
            "SELECT resolved_value FROM node_token_bindings "
            "WHERE node_id = 1 AND property = 'letterSpacing'"
        )
        row = cursor.fetchone()
        assert row is not None
        snapped = json.loads(row[0])
        # Canonical: value is the rounded -0.55, unit is PIXELS.
        assert snapped == {"value": -0.55, "unit": "PIXELS"}, (
            f"P3c: binding.resolved_value should be snapped to canonical "
            f"JSON {{'value': -0.55, 'unit': 'PIXELS'}}. Got: {snapped!r}"
        )

    def test_unit_preserved_per_bucket(self, letter_spacing_db):
        """Pixels-bucket and percent-bucket bindings get DIFFERENT
        canonical JSON (same rounded value, different unit). Codex's
        unit-aware-bucketing catch."""
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # Node 1 is PIXELS, node 7 is PERCENT — both round to -0.55.
        c1 = letter_spacing_db.execute(
            "SELECT resolved_value FROM node_token_bindings "
            "WHERE node_id = 1 AND property = 'letterSpacing'"
        ).fetchone()[0]
        c7 = letter_spacing_db.execute(
            "SELECT resolved_value FROM node_token_bindings "
            "WHERE node_id = 7 AND property = 'letterSpacing'"
        ).fetchone()[0]
        s1 = json.loads(c1)
        s7 = json.loads(c7)
        assert s1["unit"] == "PIXELS"
        assert s7["unit"] == "PERCENT"
        # And rounded value matches.
        assert s1["value"] == s7["value"] == -0.55

    def test_pixel_and_percent_get_separate_tokens(self, letter_spacing_db):
        """Same rounded value, different unit → must NOT cross-bind."""
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        pixel_token = letter_spacing_db.execute(
            "SELECT token_id FROM node_token_bindings "
            "WHERE node_id = 1 AND property = 'letterSpacing'"
        ).fetchone()[0]
        percent_token = letter_spacing_db.execute(
            "SELECT token_id FROM node_token_bindings "
            "WHERE node_id = 7 AND property = 'letterSpacing'"
        ).fetchone()[0]
        assert pixel_token != percent_token, (
            "P3c: PIXELS and PERCENT letterSpacing must get DIFFERENT "
            "tokens even when rounded values match. Codex catch: "
            "they're not interchangeable."
        )


class TestBackwardCompatPreservesExistingBehavior:
    """Existing behavior must be preserved:
    - Zero values are skipped (no token).
    - token_values.resolved_value stays as str(rounded), not JSON."""

    def test_zero_values_skipped(self, letter_spacing_db):
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # Nodes 11-12 have value=0; their bindings should remain
        # unbound (no token assigned).
        cursor = letter_spacing_db.execute(
            "SELECT binding_status, token_id FROM node_token_bindings "
            "WHERE node_id IN (11, 12) AND property = 'letterSpacing'"
        )
        for row in cursor.fetchall():
            assert row[0] == "unbound", (
                "P3c: zero-value letterSpacing bindings must stay "
                "unbound (downstream mark_default_bindings handles them)."
            )
            assert row[1] is None

    def test_token_values_resolved_value_stays_numeric_string(
        self, letter_spacing_db,
    ):
        """token_values.resolved_value should remain a plain numeric
        string for downstream readers (export-css etc.)."""
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        cursor = letter_spacing_db.execute(
            """SELECT t.name, tv.resolved_value FROM token_values tv
               JOIN tokens t ON tv.token_id = t.id
               WHERE t.collection_id = ?
                 AND t.name LIKE 'type.tracking.%'""",
            (coll_id,),
        )
        rows = cursor.fetchall()
        # Each token's resolved_value should be parseable as float
        # (i.e., not a JSON object). The actual numeric values are
        # -0.55 (twice — pixel bucket and percent bucket) and 1.5
        # (pixel positive bucket).
        for name, rv in rows:
            try:
                float(rv)
            except ValueError:
                pytest.fail(
                    f"P3c: token '{name}' resolved_value should be a "
                    f"numeric string for downstream readers; got: {rv!r}"
                )


class TestValidatorBindingConsistencyClean:
    """The whole point of P3c: after clustering, the validator's
    `_values_match` / `binding_token_consistency` view should report
    NO mismatches for letterSpacing bindings.

    This is the end-to-end test: simulate what `dd validate` does
    for letterSpacing bindings."""

    def test_no_binding_token_consistency_mismatches(self, letter_spacing_db):
        coll_id, mode_id = ensure_typography_collection(
            letter_spacing_db, file_id=1,
        )
        cluster_letter_spacing(
            letter_spacing_db, file_id=1,
            collection_id=coll_id, mode_id=mode_id,
        )
        # For each PROPOSED binding, fetch its token's resolved_value
        # and compare via the same logic the validator uses
        # (_normalize_numeric in dd/validate.py). For P3c to be working,
        # every (binding.resolved_value, token.resolved_value) pair
        # should normalize to the same numeric value.
        cursor = letter_spacing_db.execute(
            """SELECT ntb.resolved_value AS binding_rv,
                      tv.resolved_value AS token_rv
               FROM node_token_bindings ntb
               JOIN token_values tv ON tv.token_id = ntb.token_id
               WHERE ntb.binding_status = 'proposed'
                 AND ntb.property = 'letterSpacing'"""
        )
        for binding_rv, token_rv in cursor.fetchall():
            # Binding is canonical JSON; pull the value.
            binding_value = json.loads(binding_rv)["value"]
            # Token is a plain numeric string.
            token_value = float(token_rv)
            assert binding_value == token_value, (
                f"P3c validator-clean: binding.resolved_value's numeric "
                f"value ({binding_value}) must match token.resolved_value "
                f"({token_value}) so the validator sees them as "
                f"equivalent. Mismatch indicates the snap-on-UPDATE "
                f"pattern didn't fire correctly."
            )
