"""Tests for the component type catalog (T5 Phase 0)."""

import json
import re
import sqlite3

import pytest

from dd.catalog import CATALOG_ENTRIES, get_catalog, lookup_by_name, seed_catalog
from dd.db import init_db
from dd.types import VALID_CATEGORIES, ComponentCategory

# ---------------------------------------------------------------------------
# Step 1: Schema tests
# ---------------------------------------------------------------------------

class TestCatalogSchema:
    """Verify component_type_catalog table exists with correct structure."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        yield conn
        conn.close()

    def test_table_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='component_type_catalog'"
        )
        assert cursor.fetchone() is not None

    def test_has_expected_columns(self, db: sqlite3.Connection):
        cursor = db.execute("PRAGMA table_info(component_type_catalog)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id", "canonical_name", "aliases", "category",
            "behavioral_description", "prop_definitions", "slot_definitions",
            "semantic_role", "recognition_heuristics", "related_types",
            "variant_axes",  # ADR-008 PR #0
            # CLAY / ARIA alignment + disambiguation (migration 016)
            "clay_equivalent", "aria_role", "disambiguation_notes",
            "created_at",
        }
        assert columns == expected

    def test_canonical_name_unique(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO component_type_catalog (canonical_name, category) "
            "VALUES ('button', 'actions')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO component_type_catalog (canonical_name, category) "
                "VALUES ('button', 'actions')"
            )

    def test_rejects_invalid_category(self, db: sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO component_type_catalog (canonical_name, category) "
                "VALUES ('button', 'bogus_category')"
            )

    def test_accepts_all_valid_categories(self, db: sqlite3.Connection):
        valid = [
            "actions", "selection_and_input", "content_and_display",
            "navigation", "feedback_and_status", "containment_and_overlay",
        ]
        for i, cat in enumerate(valid):
            db.execute(
                "INSERT INTO component_type_catalog (canonical_name, category) "
                "VALUES (?, ?)",
                (f"test_{i}", cat),
            )
        cursor = db.execute("SELECT COUNT(*) FROM component_type_catalog")
        assert cursor.fetchone()[0] == 6

    def test_created_at_defaults(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO component_type_catalog (canonical_name, category) "
            "VALUES ('button', 'actions')"
        )
        cursor = db.execute(
            "SELECT created_at FROM component_type_catalog WHERE canonical_name = 'button'"
        )
        row = cursor.fetchone()
        assert row[0] is not None
        assert "T" in row[0]  # ISO 8601 format

    def test_category_index_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ctc_category'"
        )
        assert cursor.fetchone() is not None

    def test_semantic_role_index_exists(self, db: sqlite3.Connection):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ctc_semantic_role'"
        )
        assert cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# Step 2: ComponentCategory enum tests
# ---------------------------------------------------------------------------

class TestComponentCategory:
    """Verify ComponentCategory enum and VALID_CATEGORIES constant."""

    def test_has_six_members(self):
        assert len(ComponentCategory) == 6

    def test_is_str_enum(self):
        assert isinstance(ComponentCategory.ACTIONS, str)
        assert ComponentCategory.ACTIONS == "actions"

    def test_all_values(self):
        expected = {
            "actions", "selection_and_input", "content_and_display",
            "navigation", "feedback_and_status", "containment_and_overlay",
        }
        assert {c.value for c in ComponentCategory} == expected

    def test_valid_categories_frozenset(self):
        assert isinstance(VALID_CATEGORIES, frozenset)
        assert len(VALID_CATEGORIES) == 6

    def test_valid_categories_matches_enum(self):
        assert frozenset(c.value for c in ComponentCategory) == VALID_CATEGORIES


# ---------------------------------------------------------------------------
# Steps 3+4: Catalog data validation + seed_catalog()
# ---------------------------------------------------------------------------

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


class TestCatalogData:
    """Verify CATALOG_ENTRIES constant has correct shape and contents."""

    def test_is_tuple(self):
        assert isinstance(CATALOG_ENTRIES, tuple)

    def test_count_in_range(self):
        # ADR-008 PR #0: 48 base - 2 demoted (toggle_group, context_menu)
        # + 7 new (divider, progress, spinner, kbd, number_input, otp_input,
        # command) = 53. 2026-04-20: control_point + not_ui + 7 CLAY /
        # Ferret-UI-2 audit types (chip, carousel, pager_indicator,
        # chart, rating, video_player, grabber) = 62. 2026-04-21 AM:
        # +3 (magnifier, mouse_cursor, coach_mark) = 65. +3 (keyboard,
        # control_box, text_cursor) from adjudication = 68. +13 from
        # Material 3 / Apple HIG / design-tool audit (sidebar, toolbar,
        # bottom_sheet, color_picker, color_swatch, ruler, stepper_input,
        # banner, snackbar, action_sheet, progress_ring, eyedropper,
        # edit_menu) = 81. Tolerance 55-100.
        assert 55 <= len(CATALOG_ENTRIES) <= 100

    def test_all_have_required_fields(self):
        for entry in CATALOG_ENTRIES:
            assert "canonical_name" in entry, f"Missing canonical_name: {entry}"
            assert "category" in entry, f"Missing category in {entry.get('canonical_name')}"

    def test_all_categories_valid(self):
        for entry in CATALOG_ENTRIES:
            assert entry["category"] in VALID_CATEGORIES, (
                f"{entry['canonical_name']} has invalid category: {entry['category']}"
            )

    def test_names_are_snake_case(self):
        for entry in CATALOG_ENTRIES:
            name = entry["canonical_name"]
            assert SNAKE_CASE_RE.match(name), f"Name not snake_case: {name}"

    def test_no_duplicate_names(self):
        names = [e["canonical_name"] for e in CATALOG_ENTRIES]
        assert len(names) == len(set(names))

    def test_all_six_categories_represented(self):
        categories = {e["category"] for e in CATALOG_ENTRIES}
        assert categories == VALID_CATEGORIES

    def test_all_have_behavioral_description(self):
        for entry in CATALOG_ENTRIES:
            assert entry.get("behavioral_description"), (
                f"{entry['canonical_name']} missing behavioral_description"
            )

    def test_all_have_semantic_role(self):
        for entry in CATALOG_ENTRIES:
            assert entry.get("semantic_role"), (
                f"{entry['canonical_name']} missing semantic_role"
            )

    def test_aliases_are_lists_or_none(self):
        for entry in CATALOG_ENTRIES:
            aliases = entry.get("aliases")
            if aliases is not None:
                assert isinstance(aliases, list), (
                    f"{entry['canonical_name']} aliases should be list, got {type(aliases)}"
                )

    def test_specific_entries_exist(self):
        names = {e["canonical_name"] for e in CATALOG_ENTRIES}
        for expected in ("button", "text_input", "card", "dialog", "tabs", "alert"):
            assert expected in names, f"Missing expected type: {expected}"


class TestSeedCatalog:
    """Verify seed_catalog() populates the database correctly."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        yield conn
        conn.close()

    def test_populates_correct_count(self, db: sqlite3.Connection):
        count = seed_catalog(db)
        assert count == len(CATALOG_ENTRIES)

        cursor = db.execute("SELECT COUNT(*) FROM component_type_catalog")
        assert cursor.fetchone()[0] == len(CATALOG_ENTRIES)

    def test_idempotent(self, db: sqlite3.Connection):
        first = seed_catalog(db)
        second = seed_catalog(db)
        assert first == len(CATALOG_ENTRIES)
        assert second == 0

        cursor = db.execute("SELECT COUNT(*) FROM component_type_catalog")
        assert cursor.fetchone()[0] == len(CATALOG_ENTRIES)

    def test_json_columns_parse(self, db: sqlite3.Connection):
        seed_catalog(db)
        cursor = db.execute(
            "SELECT aliases, prop_definitions, slot_definitions, "
            "recognition_heuristics, related_types FROM component_type_catalog"
        )
        for row in cursor.fetchall():
            for col_val in row:
                if col_val is not None:
                    parsed = json.loads(col_val)
                    assert isinstance(parsed, (list, dict)), (
                        f"JSON column should be list or dict, got {type(parsed)}"
                    )

    def test_button_entry_correct(self, db: sqlite3.Connection):
        seed_catalog(db)
        cursor = db.execute(
            "SELECT canonical_name, category, semantic_role "
            "FROM component_type_catalog WHERE canonical_name = 'button'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "actions"
        assert row[2] == "button"

    def test_all_categories_seeded(self, db: sqlite3.Connection):
        seed_catalog(db)
        cursor = db.execute(
            "SELECT DISTINCT category FROM component_type_catalog ORDER BY category"
        )
        categories = {row[0] for row in cursor.fetchall()}
        assert categories == VALID_CATEGORIES


# ---------------------------------------------------------------------------
# Step 5: Query helper tests
# ---------------------------------------------------------------------------

class TestCatalogQueries:
    """Verify get_catalog() and lookup_by_name() query helpers."""

    @pytest.fixture
    def seeded_db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        yield conn
        conn.close()

    def test_get_catalog_returns_all(self, seeded_db: sqlite3.Connection):
        results = get_catalog(seeded_db)
        assert len(results) == len(CATALOG_ENTRIES)

    def test_get_catalog_parses_json(self, seeded_db: sqlite3.Connection):
        results = get_catalog(seeded_db)
        button = next(r for r in results if r["canonical_name"] == "button")
        assert isinstance(button["aliases"], list)
        assert "btn" in button["aliases"]
        assert isinstance(button["related_types"], list)

    def test_get_catalog_filters_by_category(self, seeded_db: sqlite3.Connection):
        actions = get_catalog(seeded_db, category="actions")
        # Count grows with each catalog addition; check non-empty + tag
        # consistency instead of hard-coded count.
        assert len(actions) >= 6
        assert all(r["category"] == "actions" for r in actions)
        names = {r["canonical_name"] for r in actions}
        assert "button" in names and "icon_button" in names

    def test_get_catalog_empty_category_returns_empty(self, seeded_db: sqlite3.Connection):
        results = get_catalog(seeded_db, category="nonexistent")
        assert results == []

    def test_lookup_by_canonical_name(self, seeded_db: sqlite3.Connection):
        result = lookup_by_name(seeded_db, "button")
        assert result is not None
        assert result["canonical_name"] == "button"

    def test_lookup_by_alias(self, seeded_db: sqlite3.Connection):
        result = lookup_by_name(seeded_db, "switch")
        assert result is not None
        assert result["canonical_name"] == "toggle"

    def test_lookup_case_insensitive(self, seeded_db: sqlite3.Connection):
        result = lookup_by_name(seeded_db, "Button")
        assert result is not None
        assert result["canonical_name"] == "button"

    def test_lookup_nonexistent_returns_none(self, seeded_db: sqlite3.Connection):
        result = lookup_by_name(seeded_db, "nonexistent_widget")
        assert result is None


# ---------------------------------------------------------------------------
# Step 6: CLI tests
# ---------------------------------------------------------------------------

class TestSeedCatalogCLI:
    """Verify seed-catalog CLI command works end-to-end."""

    def test_seed_catalog_command(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        init_db(db_path).close()

        from dd.cli import main
        main(["seed-catalog", "--db", db_path])

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT COUNT(*) FROM component_type_catalog")
        assert cursor.fetchone()[0] == len(CATALOG_ENTRIES)
        conn.close()


# ---------------------------------------------------------------------------
# Step 7: Enriched definitions tests
# ---------------------------------------------------------------------------

class TestCatalogEnrichment:
    """Verify prop_definitions, slot_definitions, and recognition_heuristics
    are populated for all entries."""

    def test_all_entries_have_prop_definitions(self):
        for entry in CATALOG_ENTRIES:
            props = entry.get("prop_definitions")
            assert props is not None, (
                f"{entry['canonical_name']} missing prop_definitions"
            )
            assert isinstance(props, dict), (
                f"{entry['canonical_name']} prop_definitions should be dict"
            )

    def test_all_entries_have_slot_definitions(self):
        for entry in CATALOG_ENTRIES:
            slots = entry.get("slot_definitions")
            assert slots is not None, (
                f"{entry['canonical_name']} missing slot_definitions"
            )
            assert isinstance(slots, dict), (
                f"{entry['canonical_name']} slot_definitions should be dict"
            )

    def test_all_entries_have_recognition_heuristics(self):
        for entry in CATALOG_ENTRIES:
            heuristics = entry.get("recognition_heuristics")
            assert heuristics is not None, (
                f"{entry['canonical_name']} missing recognition_heuristics"
            )
            assert isinstance(heuristics, dict), (
                f"{entry['canonical_name']} recognition_heuristics should be dict"
            )

    def test_button_has_variant_prop(self):
        button = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "button")
        props = button["prop_definitions"]
        assert "variant" in props

    def test_card_has_content_slots(self):
        card = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "card")
        slots = card["slot_definitions"]
        assert "title" in slots
        assert "body" in slots

    def test_header_has_position_heuristic(self):
        header = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "header")
        heuristics = header["recognition_heuristics"]
        assert "position" in heuristics or "layout" in heuristics

    def test_toggle_has_on_prop(self):
        toggle = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "toggle")
        props = toggle["prop_definitions"]
        assert "on" in props or "checked" in props or "value" in props

    def test_header_slots_have_position(self):
        header = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "header")
        slots = header["slot_definitions"]
        assert slots["leading"]["position"] == "start"
        assert slots["title"]["position"] == "center"
        assert slots["trailing"]["position"] == "end"

    def test_card_slots_have_position(self):
        # ADR-008 PR #0: card's `image` slot renamed to `media` to accept
        # {image, video, vector} per Stream A's ontology survey.
        card = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "card")
        slots = card["slot_definitions"]
        assert slots["media"]["position"] == "start"
        assert slots["actions"]["position"] == "end"

    def test_button_slots_have_position(self):
        button = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "button")
        slots = button["slot_definitions"]
        assert slots["icon"]["position"] == "start"
        assert slots["label"]["position"] == "fill"

    def test_key_slots_have_quantity(self):
        header = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "header")
        assert header["slot_definitions"]["leading"]["quantity"] == "single"
        assert header["slot_definitions"]["trailing"]["quantity"] == "multiple"

    def test_default_slot_on_key_types(self):
        card = next(e for e in CATALOG_ENTRIES if e["canonical_name"] == "card")
        assert "_default" in card["slot_definitions"]
        assert card["slot_definitions"]["_default"]["allowed"] == ["any"]
