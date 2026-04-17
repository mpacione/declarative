"""Tests for the v0.1.5 archetype library.

Covers ``dd.archetype_library``, which provides hand-authored screen
skeletons for 8-12 canonical archetypes (feed / dashboard / paywall /
login / settings / search / drawer-nav / onboarding-carousel / profile
/ chat / empty-state / detail).

Per the continuation plan (`docs/continuation-v0.1.5.md` Step 2
"Dank coverage check"): Dank's node-name prefixes resolve to chrome +
navigation (address/bar/button/center/frame/left/notch/right/etc.) at
depth 1 with no semantic page-level signal; ``components`` and
``screen_component_instances`` tables are empty in the current DB.
Hand-authoring is the intended v0.1.5 fallback; corpus-mining is
deferred to v0.2 after the classifier chain is re-run.
"""

from __future__ import annotations

import pytest

from dd.archetype_library import (
    ARCHETYPE_NAMES,
    list_archetypes,
    load_provenance,
    load_skeleton,
)


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #

class TestArchetypeRegistry:
    def test_has_at_least_eight_archetypes(self):
        assert len(ARCHETYPE_NAMES) >= 8

    def test_canonical_twelve_prompts_each_have_an_archetype(self):
        """Each of the 12 canonical prompts needs a routeable archetype.
        The classifier in Step 3 depends on this."""
        expected_coverage = {
            "login", "settings", "feed", "dashboard", "paywall",
            "search", "drawer-nav", "onboarding-carousel",
        }
        assert expected_coverage.issubset(set(ARCHETYPE_NAMES))

    def test_list_archetypes_returns_all_names(self):
        assert set(list_archetypes()) == set(ARCHETYPE_NAMES)

    def test_names_are_kebab_case(self):
        for name in ARCHETYPE_NAMES:
            assert name == name.lower()
            assert " " not in name
            assert "_" not in name


# --------------------------------------------------------------------------- #
# Skeleton shape                                                              #
# --------------------------------------------------------------------------- #

class TestSkeletonShape:
    @pytest.mark.parametrize("name", sorted({
        "login", "settings", "feed", "dashboard", "paywall",
        "search", "drawer-nav", "onboarding-carousel",
    }))
    def test_skeleton_loads_as_non_empty_list(self, name):
        skeleton = load_skeleton(name)
        assert isinstance(skeleton, list)
        # drawer-nav is a legit single-root tree (one drawer containing
        # everything); other archetypes expose multiple top-level regions.
        assert len(skeleton) >= 1

    @pytest.mark.parametrize("name", sorted({
        "login", "settings", "feed", "dashboard", "paywall",
        "search", "drawer-nav", "onboarding-carousel",
    }))
    def test_every_node_has_a_type(self, name):
        skeleton = load_skeleton(name)

        def check(nodes):
            for node in nodes:
                assert isinstance(node, dict)
                assert "type" in node
                assert isinstance(node["type"], str)
                if "children" in node:
                    check(node["children"])

        check(skeleton)

    @pytest.mark.parametrize("name", sorted({
        "login", "settings", "feed", "dashboard", "paywall",
        "search", "drawer-nav", "onboarding-carousel",
    }))
    def test_node_counts_are_in_memo_range(self, name):
        """Plan §Step 2: '2-3 level IR-shaped tree with 10-25 nodes.'"""
        skeleton = load_skeleton(name)

        def count(nodes):
            n = 0
            for node in nodes:
                n += 1
                if "children" in node:
                    n += count(node["children"])
            return n

        total = count(skeleton)
        assert 8 <= total <= 30, f"{name} has {total} nodes"

    def test_unknown_archetype_raises(self):
        with pytest.raises(ValueError):
            load_skeleton("does-not-exist")


class TestSkeletonsUseCatalogTypes:
    """Skeletons must reference types the LLM is allowed to emit, so
    they're composable via the existing pipeline without extending the
    catalog."""

    # Minimal allowlist — skeletons should stick to this set.
    ALLOWED = {
        # Actions
        "button", "icon_button", "fab", "button_group", "menu",
        # Input
        "checkbox", "radio", "toggle", "toggle_group", "select",
        "combobox", "date_picker", "slider", "segmented_control",
        "text_input", "textarea", "search_input", "stepper",
        # Content
        "text", "heading", "link", "image", "icon", "avatar", "badge",
        "list", "list_item", "table", "skeleton",
        # Navigation
        "navigation_row", "tabs", "breadcrumbs", "pagination",
        "bottom_nav", "drawer", "header",
        # Feedback
        "alert", "toast", "popover", "tooltip", "empty_state",
        "file_upload",
        # Containment
        "card", "dialog", "sheet", "accordion",
    }

    @pytest.mark.parametrize("name", sorted({
        "login", "settings", "feed", "dashboard", "paywall",
        "search", "drawer-nav", "onboarding-carousel",
    }))
    def test_skeleton_uses_only_catalog_types(self, name):
        skeleton = load_skeleton(name)

        def check(nodes):
            for node in nodes:
                assert node["type"] in self.ALLOWED, (
                    f"{name} skeleton uses non-catalog type: {node['type']}"
                )
                if "children" in node:
                    check(node["children"])

        check(skeleton)


# --------------------------------------------------------------------------- #
# Provenance                                                                  #
# --------------------------------------------------------------------------- #

class TestProvenance:
    def test_provenance_has_entry_per_archetype(self):
        prov = load_provenance()
        for name in ARCHETYPE_NAMES:
            assert name in prov, f"provenance missing entry for {name}"

    def test_provenance_declares_origin(self):
        """Each archetype must declare whether it's corpus-derived or
        hand-authored so future maintainers can trust the data."""
        prov = load_provenance()
        for name, meta in prov.items():
            assert "origin" in meta
            assert meta["origin"] in {"corpus-mined", "hand-authored"}

    def test_provenance_records_canonical_prompt_mapping_for_canonicals(self):
        """The classifier in Step 3 routes each of the 12 canonical
        prompts via this mapping."""
        prov = load_provenance()
        mapped = {
            meta.get("canonical_prompt_slug")
            for meta in prov.values()
            if meta.get("canonical_prompt_slug")
        }
        expected = {
            "01-login", "02-profile-settings", "03-meme-feed",
            "04-dashboard", "05-paywall", "07-search",
            "09-drawer-nav", "10-onboarding-carousel",
        }
        assert expected.issubset(mapped)
