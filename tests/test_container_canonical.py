"""Phase E #6 fix — `container` is a first-class CatalogEntry.

Pre-fix `container` was BOTH:
- An alias of `frame` (dd/catalog.py CATALOG_ENTRIES "frame" entry's
  aliases list)
- A first-class canonical via `_CATALOG_ENRICHMENTS["container"]`
  (clay_equivalent, disambiguation_notes) — but the enrichment was
  DEAD because `_enriched()` keys on canonical_name, and there was
  no canonical "container" entry to merge into.

Meanwhile the runtime treated `container` as a real semantic bucket
distinct from `frame`:
- dd/classify_rules.py:232 emits canonical_type="container"
- dd/classify_llm.py:85, 573 specials-cases container
- dd/classify_v2.py:288 special-cases container
- dd/compose.py:1448 emits container as a Mode-3 generated type
- dd/fidelity_score.py:566 lists container alongside screen/frame/unsure
- dd/markup_l3.py:1500 grammar keyword
- dd/structural_verbs.py:119 grammar list
- dd/renderers/figma.py:940 maps container→FRAME

Codex 2026-04-26 (gpt-5.5 high reasoning) review:
"the codebase already treats container as a real semantic bucket,
not merely an alias for frame... keeping container as an alias of
frame is the actual inconsistency."

The Phase E #6 fix:
1. Add `container` as a canonical CatalogEntry (matches what the
   runtime already believes).
2. Remove `container` from frame's aliases.
3. Future seedings get the new entry; existing DBs need a re-seed.
4. The dead enrichment now becomes live (clay_equivalent: CONTAINER,
   disambiguation_notes: "FALLBACK only" prose).

These tests pin the post-fix state.
"""

from __future__ import annotations

import sqlite3

from dd.catalog import (
    CATALOG_ENTRIES,
    _enriched,
    lookup_by_name,
    seed_catalog,
)
from dd import db as dd_db


class TestContainerIsCanonical:
    """The headline fix — `container` is a canonical CatalogEntry,
    not an alias of frame."""

    def test_container_in_catalog_entries(self):
        names = [e["canonical_name"] for e in CATALOG_ENTRIES]
        assert "container" in names, (
            "Phase E #6 fix: `container` must be a canonical "
            "CatalogEntry. Pre-fix it was only an alias of `frame`."
        )

    def test_frame_no_longer_lists_container_as_alias(self):
        frame_entry = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "frame"
        )
        aliases = frame_entry.get("aliases") or []
        assert "container" not in aliases, (
            "Phase E #6 fix: `container` removed from frame's "
            "aliases. The two are semantically distinct in the "
            "runtime. Keeping container as an alias of frame "
            "made the alias lookup ambiguous (two routes to the "
            "same canonical, but the canonical was wrong)."
        )


class TestContainerEnrichmentNowLive:
    """Pre-fix _CATALOG_ENRICHMENTS["container"] was dead because
    _enriched() keyed on canonical_name. Post-fix the merge fires
    and the enrichment metadata appears on the container entry."""

    def test_container_entry_has_enriched_metadata(self):
        container = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "container"
        )
        # _enriched() merges in the _CATALOG_ENRICHMENTS dict
        merged = _enriched(container)
        # The pre-existing enrichment had clay_equivalent + disambiguation_notes
        assert merged.get("clay_equivalent") == "CONTAINER", (
            "Phase E #6 fix: _CATALOG_ENRICHMENTS['container']'s "
            "clay_equivalent should now appear on the container "
            "entry via _enriched(). Pre-fix this was dead."
        )
        assert "FALLBACK only" in (merged.get("disambiguation_notes") or ""), (
            "Phase E #6 fix: _CATALOG_ENRICHMENTS['container']'s "
            "disambiguation_notes should now appear on the "
            "container entry."
        )


class TestLookupResolvesContainerCorrectly:
    """`lookup_by_name("container")` should resolve to the container
    entry (canonical match), NOT to frame's alias scan."""

    def test_lookup_container_returns_container_canonical(self):
        conn = dd_db.init_db(":memory:")
        seed_catalog(conn)
        result = lookup_by_name(conn, "container")
        assert result is not None, (
            "Phase E #6 fix: `container` must be findable by "
            "lookup_by_name. Pre-fix this would have returned "
            "frame (via alias scan), masking the schism."
        )
        assert result["canonical_name"] == "container", (
            f"Phase E #6 fix: lookup_by_name('container') must "
            f"return the container canonical, not frame. "
            f"Got: {result.get('canonical_name')}"
        )

    def test_lookup_frame_still_returns_frame(self):
        """Defensive: frame's canonical lookup is unaffected."""
        conn = dd_db.init_db(":memory:")
        seed_catalog(conn)
        result = lookup_by_name(conn, "frame")
        assert result is not None
        assert result["canonical_name"] == "frame"

    def test_lookup_wrapper_alias_returns_frame(self):
        """`wrapper` is still an alias of `frame` (Phase E #6
        only removed `container` from frame's aliases; the others
        — wrapper / section / group / stack / row — stay)."""
        conn = dd_db.init_db(":memory:")
        seed_catalog(conn)
        result = lookup_by_name(conn, "wrapper")
        assert result is not None
        assert result["canonical_name"] == "frame", (
            "wrapper is still an alias of frame; only `container` "
            "was removed from frame's aliases in Phase E #6."
        )


class TestSeedingPicksUpContainer:
    """Seeding the catalog from a fresh DB now produces a
    `container` row in component_type_catalog."""

    def test_seed_catalog_creates_container_row(self):
        conn = dd_db.init_db(":memory:")
        seed_catalog(conn)
        cursor = conn.execute(
            "SELECT canonical_name, category, clay_equivalent "
            "FROM component_type_catalog WHERE canonical_name = ?",
            ("container",),
        )
        row = cursor.fetchone()
        assert row is not None, (
            "Phase E #6 fix: seed_catalog must create a `container` "
            "row in component_type_catalog."
        )
        # Phase E #6 expects category="structural" (matches frame).
        assert row[1] == "structural"
        # Enrichment merged: clay_equivalent should be populated.
        assert row[2] == "CONTAINER"
