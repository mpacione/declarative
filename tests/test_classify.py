"""Tests for component classification (T5 Phase 1a)."""

import sqlite3

import pytest

from dd.db import init_db
from dd.catalog import seed_catalog
from dd.classify import build_alias_index, parse_component_prefix, classify_formal
from dd.types import ClassificationSource


# ---------------------------------------------------------------------------
# Step 1: Schema + enum tests
# ---------------------------------------------------------------------------

class TestClassificationSchema:
    """Verify classification tables exist with correct structure."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        yield conn
        conn.close()

    def test_screen_component_instances_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='screen_component_instances'"
        )
        assert cursor.fetchone() is not None

    def test_sci_has_expected_columns(self, db: sqlite3.Connection):
        cursor = db.execute("PRAGMA table_info(screen_component_instances)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id", "screen_id", "node_id", "catalog_type_id",
            "canonical_type", "confidence", "classification_source",
            "parent_instance_id", "slot_name", "created_at",
        }
        assert columns == expected

    def test_sci_rejects_invalid_source(self, db: sqlite3.Connection):
        self._seed_screen_and_node(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO screen_component_instances "
                "(screen_id, node_id, canonical_type, classification_source) "
                "VALUES (1, 1, 'button', 'bogus')"
            )

    def test_sci_unique_screen_node(self, db: sqlite3.Connection):
        self._seed_screen_and_node(db)
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, classification_source) "
            "VALUES (1, 1, 'button', 'formal')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO screen_component_instances "
                "(screen_id, node_id, canonical_type, classification_source) "
                "VALUES (1, 1, 'icon', 'heuristic')"
            )

    def test_sci_screen_index_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sci_screen'"
        )
        assert cursor.fetchone() is not None

    def test_screen_skeletons_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='screen_skeletons'"
        )
        assert cursor.fetchone() is not None

    def test_skeletons_unique_screen(self, db: sqlite3.Connection):
        self._seed_screen_and_node(db)
        db.execute(
            "INSERT INTO screen_skeletons (screen_id, skeleton_notation) "
            "VALUES (1, 'stack(header, content)')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO screen_skeletons (screen_id, skeleton_notation) "
                "VALUES (1, 'stack(content)')"
            )

    @staticmethod
    def _seed_screen_and_node(db: sqlite3.Connection):
        db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F')")
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 'n1', 'Screen 1', 428, 926)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, 1, 'n2', 'button/primary', 'INSTANCE', 1, 0)"
        )
        db.commit()


class TestClassificationSourceEnum:
    """Verify ClassificationSource enum."""

    def test_has_five_members(self):
        assert len(ClassificationSource) == 5

    def test_is_str_enum(self):
        assert isinstance(ClassificationSource.FORMAL, str)
        assert ClassificationSource.FORMAL == "formal"

    def test_all_values(self):
        expected = {"formal", "heuristic", "llm", "vision", "manual"}
        assert {c.value for c in ClassificationSource} == expected


# ---------------------------------------------------------------------------
# Step 2: Alias index + name parser tests
# ---------------------------------------------------------------------------

class TestAliasIndex:
    """Verify alias index building and name parsing."""

    @pytest.fixture
    def seeded_db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        yield conn
        conn.close()

    def test_build_alias_index_returns_dict(self, seeded_db):
        index = build_alias_index(seeded_db)
        assert isinstance(index, dict)
        assert len(index) > 48  # canonical names + aliases

    def test_index_has_canonical_names(self, seeded_db):
        index = build_alias_index(seeded_db)
        assert "button" in index
        assert "toggle" in index
        assert "card" in index

    def test_index_has_aliases(self, seeded_db):
        index = build_alias_index(seeded_db)
        assert "switch" in index  # alias for toggle
        assert "modal" in index   # alias for dialog
        assert "btn" in index     # alias for button

    def test_alias_maps_to_canonical(self, seeded_db):
        index = build_alias_index(seeded_db)
        assert index["switch"]["canonical_name"] == "toggle"
        assert index["btn"]["canonical_name"] == "button"
        assert index["modal"]["canonical_name"] == "dialog"


class TestParseComponentPrefix:
    """Verify component name prefix extraction."""

    def test_slash_delimited(self):
        assert parse_component_prefix("button/large/translucent") == "button"

    def test_single_word(self):
        assert parse_component_prefix("Sidebar") == "sidebar"

    def test_rejects_generic_frame(self):
        assert parse_component_prefix("Frame 359") is None

    def test_rejects_generic_group(self):
        assert parse_component_prefix("Group 12") is None

    def test_rejects_generic_rectangle(self):
        assert parse_component_prefix("Rectangle 4") is None

    def test_accepts_named_frame(self):
        assert parse_component_prefix("card/sheet/success") == "card"

    def test_lowercases(self):
        assert parse_component_prefix("Button/Primary") == "button"

    def test_nav_prefix(self):
        assert parse_component_prefix("nav/top-nav") == "nav"

    def test_ios_prefix(self):
        assert parse_component_prefix("ios/status-bar") == "ios"

    def test_dot_prefix(self):
        assert parse_component_prefix(".icons/chevron") == ".icons"


# ---------------------------------------------------------------------------
# Step 3: Formal matching tests
# ---------------------------------------------------------------------------

def _seed_classifiable_screen(db: sqlite3.Connection) -> None:
    """Insert a file, screen, catalog, and several typed nodes for classification tests."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    nodes = [
        (1, 1, "n1", "button/large/translucent", "INSTANCE", 1, 0, 0, 800),
        (2, 1, "n2", "icon/back", "INSTANCE", 1, 1, 0, 0),
        (3, 1, "n3", "nav/top-nav", "INSTANCE", 1, 2, 0, 0),
        (4, 1, "n4", "card/sheet/success", "FRAME", 1, 3, 0, 200),
        (5, 1, "n5", "Frame 359", "FRAME", 1, 4, 0, 100),
        (6, 1, "n6", "ios/status-bar", "INSTANCE", 1, 5, 0, 0),
        (7, 1, "n7", "logo/dank", "INSTANCE", 1, 6, 0, 50),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, y, height) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    db.commit()


class TestFormalMatching:
    """Verify classify_formal() maps named nodes to catalog types."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_classifiable_screen(conn)
        yield conn
        conn.close()

    def test_classifies_button_instance(self, db: sqlite3.Connection):
        result = classify_formal(db, screen_id=1)
        assert result["classified"] > 0

        cursor = db.execute(
            "SELECT canonical_type, classification_source, confidence "
            "FROM screen_component_instances WHERE node_id = 1"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "button"
        assert row[1] == "formal"
        assert row[2] == 1.0

    def test_classifies_icon_instance(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 2"
        )
        assert cursor.fetchone()[0] == "icon"

    def test_classifies_card_frame(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 4"
        )
        assert cursor.fetchone()[0] == "card"

    def test_skips_generic_frame(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT id FROM screen_component_instances WHERE node_id = 5"
        )
        assert cursor.fetchone() is None

    def test_skips_unrecognized_prefix(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        # ios/status-bar prefix "ios" is not in catalog
        cursor = db.execute(
            "SELECT id FROM screen_component_instances WHERE node_id = 6"
        )
        assert cursor.fetchone() is None

    def test_returns_count(self, db: sqlite3.Connection):
        result = classify_formal(db, screen_id=1)
        assert isinstance(result, dict)
        assert result["classified"] >= 3  # button, icon, card at minimum

    def test_idempotent(self, db: sqlite3.Connection):
        first = classify_formal(db, screen_id=1)
        second = classify_formal(db, screen_id=1)
        assert second["classified"] == 0

    def test_sets_catalog_type_id(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT catalog_type_id FROM screen_component_instances WHERE node_id = 1"
        )
        row = cursor.fetchone()
        assert row[0] is not None  # should be set to the button's catalog ID
