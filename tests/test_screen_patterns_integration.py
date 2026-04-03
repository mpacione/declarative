"""Screen patterns integration tests against real Dank DB.

Verifies archetype extraction and LLM prompt enrichment with
project-specific screen patterns. Auto-skips if Dank DB not present.
"""

import os
import sqlite3

import pytest

from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestDankArchetypes:
    """Verify archetype extraction from real Dank DB."""

    def test_extracts_archetypes(self, dank_db):
        archetypes = extract_screen_archetypes(dank_db, file_id=1)
        assert len(archetypes) >= 3

    def test_dominant_archetype_is_header_card_button(self, dank_db):
        archetypes = extract_screen_archetypes(dank_db, file_id=1)
        dominant = archetypes[0]
        assert dominant["screen_count"] >= 100
        assert "header" in dominant["component_types"]
        assert "button" in dominant["component_types"]

    def test_all_archetypes_have_header(self, dank_db):
        archetypes = extract_screen_archetypes(dank_db, file_id=1)
        for arch in archetypes:
            assert "header" in arch["component_types"], (
                f"Archetype missing header: {arch['signature']}"
            )

    def test_total_screens_covered(self, dank_db):
        archetypes = extract_screen_archetypes(dank_db, file_id=1)
        total = sum(a["screen_count"] for a in archetypes)
        assert total >= 200

    def test_prompt_context_has_content(self, dank_db):
        archetypes = extract_screen_archetypes(dank_db, file_id=1)
        context = get_archetype_prompt_context(archetypes)
        assert "header" in context
        assert "button" in context
        assert "card" in context
        assert "pattern" in context.lower()
