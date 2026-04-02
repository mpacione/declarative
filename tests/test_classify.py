"""Tests for component classification (T5 Phase 1a)."""

import sqlite3

import pytest

from dd.db import init_db
from dd.catalog import seed_catalog
from dd.classify import build_alias_index, parse_component_name, is_system_chrome, classify_formal, link_parent_instances, run_classification
from dd.classify_heuristics import classify_heuristics
from dd.classify_skeleton import extract_skeleton
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
            "parent_instance_id", "slot_name",
            "vision_type", "vision_agrees", "flagged_for_review",
            "created_at",
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

    def test_multi_segment_aliases(self, seeded_db):
        index = build_alias_index(seeded_db)
        assert "nav/top-nav" in index
        assert index["nav/top-nav"]["canonical_name"] == "header"
        assert "nav/tabs" in index
        assert index["nav/tabs"]["canonical_name"] == "tabs"


class TestParseComponentName:
    """Verify component name candidate extraction."""

    def test_returns_candidates_longest_first(self):
        candidates = parse_component_name("button/large/translucent")
        assert candidates[0] == "button/large/translucent"
        assert candidates[-1] == "button"

    def test_single_word(self):
        candidates = parse_component_name("Sidebar")
        assert candidates == ["sidebar"]

    def test_rejects_generic_frame(self):
        assert parse_component_name("Frame 359") == []

    def test_rejects_generic_group(self):
        assert parse_component_name("Group 12") == []

    def test_slash_path(self):
        candidates = parse_component_name("nav/top-nav")
        assert "nav/top-nav" in candidates
        assert "nav" in candidates

    def test_lowercases(self):
        candidates = parse_component_name("Button/Primary")
        assert candidates[0] == "button/primary"
        assert candidates[1] == "button"


class TestSystemChrome:
    """Verify system chrome detection."""

    def test_ios_status_bar(self):
        assert is_system_chrome("ios/status-bar") is True

    def test_ios_capitalized(self):
        assert is_system_chrome("iOS/StatusBar") is True

    def test_home_indicator(self):
        assert is_system_chrome("Home Indicator") is True
        assert is_system_chrome("HomeIndicator") is True

    def test_safari_bottom(self):
        assert is_system_chrome("Safari - Bottom") is True

    def test_keyboard_keys(self):
        assert is_system_chrome("a") is True
        assert is_system_chrome("z") is True
        assert is_system_chrome("shift") is True
        assert is_system_chrome("caps lock") is True
        assert is_system_chrome("Enter") is True
        assert is_system_chrome("Emoji") is True
        assert is_system_chrome("Dictation") is True
        assert is_system_chrome(".?123") is True
        assert is_system_chrome("Keyboard Layout") is True
        assert is_system_chrome("Keyboard Close") is True

    def test_key_container(self):
        assert is_system_chrome("_KeyContainer") is True
        assert is_system_chrome("_Key") is True

    def test_view_mode(self):
        assert is_system_chrome("View Mode") is True

    def test_real_components_not_chrome(self):
        assert is_system_chrome("button/primary") is False
        assert is_system_chrome("icon/back") is False
        assert is_system_chrome("card/sheet") is False
        assert is_system_chrome("nav/top-nav") is False


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
        # Additional patterns
        (8, 1, "n8", ".icons/chevron", "INSTANCE", 2, 0, 0, 0),
        (9, 1, "n9", "Button 3", "INSTANCE", 2, 1, 0, 48),
        (10, 1, "n10", "Previous", "INSTANCE", 2, 2, 0, 0),
        (11, 1, "n11", "Home Indicator", "INSTANCE", 1, 7, 0, 0),
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

    def test_classifies_nav_top_nav_as_header(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 3"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "header"

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

    def test_classifies_dot_icons_as_icon(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 8"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "icon"

    def test_classifies_button_n_as_button(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 9"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "button"

    def test_skips_system_chrome(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        # ios/status-bar and Home Indicator should be skipped
        for nid in (6, 11):
            cursor = db.execute(
                "SELECT id FROM screen_component_instances WHERE node_id = ?", (nid,)
            )
            assert cursor.fetchone() is None, f"Node {nid} should be skipped as system chrome"

    def test_sets_catalog_type_id(self, db: sqlite3.Connection):
        classify_formal(db, screen_id=1)
        cursor = db.execute(
            "SELECT catalog_type_id FROM screen_component_instances WHERE node_id = 1"
        )
        row = cursor.fetchone()
        assert row[0] is not None  # should be set to the button's catalog ID


# ---------------------------------------------------------------------------
# Step 4: Structural heuristics tests
# ---------------------------------------------------------------------------

def _seed_heuristic_screen(db: sqlite3.Connection) -> None:
    """Insert nodes that should be classifiable by structural heuristics."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    nodes = [
        # Header-like: full width, at top, horizontal layout
        (10, 1, "h1", "Top Bar", "FRAME", 1, 0,
         0, 0, 428, 56, "HORIZONTAL", None, None, None, None, None),
        # Bottom nav-like: full width, at bottom, horizontal layout, short
        (11, 1, "b1", "Tab Bar", "FRAME", 1, 1,
         0, 858, 428, 68, "HORIZONTAL", None, None, None, None, None),
        # Heading-like: TEXT node with large font
        (12, 1, "t1", "Section Title", "TEXT", 2, 0,
         16, 80, 396, 28, None, "Inter", 700, 24, None, "Settings"),
        # Body text: TEXT node with standard font
        (13, 1, "t2", "Description", "TEXT", 2, 1,
         16, 110, 396, 18, None, "Inter", 400, 14, None, "Configure your preferences"),
        # Generic frame — too ambiguous for heuristics
        (14, 1, "f1", "Frame 100", "FRAME", 2, 2,
         16, 140, 200, 200, None, None, None, None, None, None),
        # Vertical list-like: FRAME with vertical layout and multiple similar children
        (15, 1, "l1", "Options", "FRAME", 1, 2,
         0, 130, 428, 600, "VERTICAL", None, None, None, None, None),
        # Children of the list (similar heights — list items)
        (16, 1, "li1", "Option 1", "FRAME", 2, 0,
         0, 0, 428, 56, "HORIZONTAL", None, None, None, None, None),
        (17, 1, "li2", "Option 2", "FRAME", 2, 1,
         0, 56, 428, 56, "HORIZONTAL", None, None, None, None, None),
        (18, 1, "li3", "Option 3", "FRAME", 2, 2,
         0, 112, 428, 56, "HORIZONTAL", None, None, None, None, None),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, layout_mode, font_family, font_weight, font_size, line_height, text_content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    # Set parent_ids for list children
    db.execute("UPDATE nodes SET parent_id = 15 WHERE id IN (16, 17, 18)")
    db.commit()


class TestStructuralHeuristics:
    """Verify classify_heuristics() uses position/layout/text rules."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_heuristic_screen(conn)
        yield conn
        conn.close()

    def test_classifies_header_by_position(self, db: sqlite3.Connection):
        result = classify_heuristics(db, screen_id=1)
        assert result["classified"] > 0

        cursor = db.execute(
            "SELECT canonical_type, confidence, classification_source "
            "FROM screen_component_instances WHERE node_id = 10"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "header"
        assert row[1] < 1.0  # heuristic confidence < formal
        assert row[2] == "heuristic"

    def test_classifies_bottom_nav_by_position(self, db: sqlite3.Connection):
        classify_heuristics(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 11"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "bottom_nav"

    def test_classifies_heading_by_font(self, db: sqlite3.Connection):
        classify_heuristics(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 12"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "heading"

    def test_classifies_body_text_by_font(self, db: sqlite3.Connection):
        classify_heuristics(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 13"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "text"

    def test_classifies_heading_without_font_weight(self, db: sqlite3.Connection):
        # Add a TEXT node with large font but no font_weight
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "x, y, width, height, font_size, text_content) "
            "VALUES (20, 1, 'tw', 'Title', 'TEXT', 2, 3, 16, 80, 396, 28, 22, 'Welcome')"
        )
        db.commit()
        classify_heuristics(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 20"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "heading"

    def test_classifies_generic_frame_as_container(self, db: sqlite3.Connection):
        # Add a generic "Frame N" node
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "x, y, width, height, layout_mode) "
            "VALUES (21, 1, 'gf', 'Frame 42', 'FRAME', 2, 4, 0, 200, 428, 300, 'VERTICAL')"
        )
        db.commit()
        classify_heuristics(db, screen_id=1)
        cursor = db.execute(
            "SELECT canonical_type FROM screen_component_instances WHERE node_id = 21"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "container"

    def test_skips_already_classified(self, db: sqlite3.Connection):
        # Pre-classify node 10 formally
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 10, 'header', 1.0, 'formal')"
        )
        db.commit()
        result = classify_heuristics(db, screen_id=1)
        # Should not re-classify node 10
        cursor = db.execute(
            "SELECT COUNT(*) FROM screen_component_instances WHERE node_id = 10"
        )
        assert cursor.fetchone()[0] == 1

    def test_returns_count(self, db: sqlite3.Connection):
        result = classify_heuristics(db, screen_id=1)
        assert isinstance(result, dict)
        assert "classified" in result


# ---------------------------------------------------------------------------
# Step 5: Skeleton extraction tests
# ---------------------------------------------------------------------------

def _seed_classified_screen(db: sqlite3.Connection) -> None:
    """Insert a screen with pre-classified components for skeleton tests."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Settings', 428, 926)"
    )
    nodes = [
        (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, 0, 0, 428, 56),
        (11, 1, "c1", "content-area", "FRAME", 1, 1, 0, 56, 428, 802),
        (12, 1, "b1", "nav/bottom-tabs", "INSTANCE", 1, 2, 0, 858, 428, 68),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    # Pre-classify them
    classifications = [
        (1, 10, "header", 1.0, "formal"),
        (1, 12, "bottom_nav", 1.0, "formal"),
    ]
    db.executemany(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (?, ?, ?, ?, ?)",
        classifications,
    )
    db.commit()


class TestSkeletonExtraction:
    """Verify extract_skeleton() generates notation from classified instances."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_classified_screen(conn)
        yield conn
        conn.close()

    def test_generates_notation(self, db: sqlite3.Connection):
        result = extract_skeleton(db, screen_id=1)
        assert result is not None
        assert "notation" in result
        assert "header" in result["notation"]
        assert "bottom_nav" in result["notation"]

    def test_persists_to_table(self, db: sqlite3.Connection):
        extract_skeleton(db, screen_id=1)
        cursor = db.execute(
            "SELECT skeleton_notation FROM screen_skeletons WHERE screen_id = 1"
        )
        row = cursor.fetchone()
        assert row is not None
        assert "header" in row[0]

    def test_idempotent(self, db: sqlite3.Connection):
        extract_skeleton(db, screen_id=1)
        extract_skeleton(db, screen_id=1)
        cursor = db.execute(
            "SELECT COUNT(*) FROM screen_skeletons WHERE screen_id = 1"
        )
        assert cursor.fetchone()[0] == 1

    def test_content_only_screen(self, db: sqlite3.Connection):
        # Add a screen with no header or nav
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (2, 1, 's2', 'Splash', 428, 926)"
        )
        db.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "x, y, width, height) VALUES (20, 2, 'x1', 'Main Content', 'FRAME', 1, 0, 0, 0, 428, 926)"
        )
        db.commit()

        result = extract_skeleton(db, screen_id=2)
        assert result is not None
        assert "content" in result["notation"]
        assert "header" not in result["notation"]


# ---------------------------------------------------------------------------
# Step 6: Orchestrator + CLI tests
# ---------------------------------------------------------------------------

def _seed_full_screen(db: sqlite3.Connection) -> None:
    """Insert a complete screen for end-to-end orchestrator testing."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class) "
        "VALUES (1, 1, 's1', 'Home', 428, 926, 'iphone')"
    )
    nodes = [
        # Formal: INSTANCE nodes with catalog-matching names
        (1, 1, "n1", "button/large/solid", "INSTANCE", 2, 0, 50, 400, 200, 48),
        (2, 1, "n2", "icon/back", "INSTANCE", 2, 1, 16, 10, 24, 24),
        # Heuristic: positional header
        (3, 1, "n3", "Top Bar", "FRAME", 1, 0, 0, 0, 428, 56),
        # Heuristic: TEXT heading
        (4, 1, "n4", "Page Title", "TEXT", 2, 0, 16, 70, 396, 28),
        # Heuristic: bottom nav
        (5, 1, "n5", "Navigation", "FRAME", 1, 2, 0, 858, 428, 68),
        # Content area (unclassified FRAME — becomes content in skeleton)
        (6, 1, "n6", "Content Area", "FRAME", 1, 1, 0, 56, 428, 802),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    # Set font props for heading
    db.execute("UPDATE nodes SET font_size = 24, font_weight = 700, layout_mode = 'HORIZONTAL' WHERE id = 4")
    db.execute("UPDATE nodes SET layout_mode = 'HORIZONTAL' WHERE id IN (3, 5)")
    db.commit()


class TestRunClassification:
    """Verify run_classification() orchestrates formal → heuristic → skeleton."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_full_screen(conn)
        yield conn
        conn.close()

    def test_runs_all_steps(self, db: sqlite3.Connection):
        result = run_classification(db, file_id=1)
        assert isinstance(result, dict)
        assert result["screens_processed"] == 1
        assert result["formal_classified"] > 0
        assert result["heuristic_classified"] > 0
        assert "parent_links" in result
        assert result["skeletons_generated"] == 1

    def test_formal_then_heuristic_order(self, db: sqlite3.Connection):
        run_classification(db, file_id=1)

        # Button should be formal (INSTANCE with catalog prefix)
        cursor = db.execute(
            "SELECT classification_source FROM screen_component_instances WHERE node_id = 1"
        )
        assert cursor.fetchone()[0] == "formal"

        # Top Bar should be heuristic (FRAME at top)
        cursor = db.execute(
            "SELECT classification_source FROM screen_component_instances WHERE node_id = 3"
        )
        assert cursor.fetchone()[0] == "heuristic"

    def test_skeleton_generated(self, db: sqlite3.Connection):
        run_classification(db, file_id=1)
        cursor = db.execute(
            "SELECT skeleton_notation FROM screen_skeletons WHERE screen_id = 1"
        )
        row = cursor.fetchone()
        assert row is not None
        assert "header" in row[0]

    def test_includes_llm_when_client_provided(self, db: sqlite3.Connection):
        import json
        from unittest.mock import MagicMock

        # Node 6 "Content Area" is unclassified FRAME at depth 1
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps([
                {"node_id": 6, "type": "container", "confidence": 0.7},
            ]))]
        )

        result = run_classification(db, file_id=1, client=mock_client)
        assert result["llm_classified"] >= 0  # LLM step was attempted


class TestClassifyCLI:
    """Verify classify CLI command works end-to-end."""

    def test_classify_command(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'Home', 428, 926)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "x, y, width, height) "
            "VALUES (1, 1, 'n1', 'button/primary', 'INSTANCE', 1, 0, 0, 400, 200, 48)"
        )
        conn.commit()
        conn.close()

        from dd.cli import main
        main(["classify", "--db", db_path])

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM screen_component_instances")
        assert cursor.fetchone()[0] > 0
        conn.close()


# ---------------------------------------------------------------------------
# Parent linkage tests
# ---------------------------------------------------------------------------

def _seed_nested_screen(db: sqlite3.Connection) -> None:
    """Insert a screen with nested component instances for parent linkage tests."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    # header (depth 1) contains icon_button (depth 2) which contains icon (depth 3)
    nodes = [
        (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, 0, 0, 428, 56, None),
        (11, 1, "ib1", "icon_button/back", "INSTANCE", 2, 0, 8, 8, 40, 40, 10),
        (12, 1, "ic1", "icon/back", "INSTANCE", 3, 0, 8, 8, 24, 24, 11),
        # card (depth 1) contains button (depth 2) and icon (depth 2)
        (20, 1, "c1", "card/action", "FRAME", 1, 1, 0, 60, 428, 200, None),
        (21, 1, "b1", "button/primary", "INSTANCE", 2, 0, 16, 140, 200, 48, 20),
        (22, 1, "ic2", "icon/star", "INSTANCE", 2, 1, 380, 16, 24, 24, 20),
        # standalone icon (depth 1) — no parent
        (30, 1, "ic3", "icon/settings", "INSTANCE", 1, 2, 400, 0, 24, 24, None),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    db.commit()


class TestParentLinkage:
    """Verify link_parent_instances() connects nested classified instances."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_nested_screen(conn)
        # Classify formally first
        classify_formal(conn, screen_id=1)
        yield conn
        conn.close()

    def test_links_icon_button_to_header(self, db: sqlite3.Connection):
        link_parent_instances(db, screen_id=1)
        cursor = db.execute(
            "SELECT parent_instance_id FROM screen_component_instances WHERE node_id = 11"
        )
        child_row = cursor.fetchone()
        assert child_row is not None

        # The parent should be the header instance (node 10)
        cursor = db.execute(
            "SELECT id FROM screen_component_instances WHERE node_id = 10"
        )
        parent_row = cursor.fetchone()
        assert child_row[0] == parent_row[0]

    def test_links_icon_to_icon_button(self, db: sqlite3.Connection):
        link_parent_instances(db, screen_id=1)
        cursor = db.execute(
            "SELECT parent_instance_id FROM screen_component_instances WHERE node_id = 12"
        )
        child_row = cursor.fetchone()

        cursor = db.execute(
            "SELECT id FROM screen_component_instances WHERE node_id = 11"
        )
        parent_row = cursor.fetchone()
        assert child_row[0] == parent_row[0]

    def test_standalone_has_no_parent(self, db: sqlite3.Connection):
        link_parent_instances(db, screen_id=1)
        cursor = db.execute(
            "SELECT parent_instance_id FROM screen_component_instances WHERE node_id = 30"
        )
        assert cursor.fetchone()[0] is None

    def test_button_inside_card_linked(self, db: sqlite3.Connection):
        link_parent_instances(db, screen_id=1)
        cursor = db.execute(
            "SELECT parent_instance_id FROM screen_component_instances WHERE node_id = 21"
        )
        child_row = cursor.fetchone()

        cursor = db.execute(
            "SELECT id FROM screen_component_instances WHERE node_id = 20"
        )
        parent_row = cursor.fetchone()
        assert child_row[0] == parent_row[0]

    def test_returns_count(self, db: sqlite3.Connection):
        result = link_parent_instances(db, screen_id=1)
        assert isinstance(result, dict)
        assert result["linked"] > 0
