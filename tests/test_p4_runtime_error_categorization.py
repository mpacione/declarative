"""P4 (Phase E Pattern 2 fix) — runtime-error categorization.

Phase E §7 found 1015 runtime errors across 67 screens, broken into 6
distinct error classes. P1 surfaced raw kinds in
`RenderReport.runtime_error_kinds` (Counter dict), but the sweep
summary still showed an opaque list of 31+ kinds. P4 adds a
diagnostic categorization layer that groups raw kinds into ~10
categories, so sweep summaries become actionable ("60% of runtime
errors are font_health → fix at the font layer").

This test pins:
1. `RenderReport.runtime_error_categories` exists and counts correctly
2. `RenderReport.is_runtime_clean` is the explicit channel
3. `dd/runtime_errors.py:RUNTIME_ERROR_KIND_TO_CATEGORY` covers every
   kind emitted by the renderer + walker (CONVENTION TEST — fails CI
   when a new __errors.push kind is added without a category)
4. The categorization map references only declared categories
5. Unknown kinds bucket as "uncategorized" without crashing
6. `categorize_runtime_error_kind` helper works at the kind level

Codex design review (2026-04-25, gpt-5.5 high reasoning):
- Central map > per-push-site tags
- Convention test enforces the map, not the call sites
- ast walk for _guarded_op + _guard_naked_prop_lines, regex for
  literal kind:'...' strings
- Include walker source for phase2_orphan (P3d kind originates there)
- Non-throwing in production (fallback to "uncategorized");
  failing in CI when repo source has an unmapped literal

Sonnet sanity-check (2026-04-25):
- 37 kinds verified, not 31 (Codex's first count missed phase1_mode*)
- phase2_orphan is in walker source, not renderer source
- phase1_mode*_prop_failed are INSTANCE-tree writes — moved into
  instance_materialization, not generic property_write_failed
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from dd.boundary import RenderReport, StructuredError, KIND_MISSING_CHILD
from dd.runtime_errors import (
    RUNTIME_ERROR_CATEGORIES,
    RUNTIME_ERROR_KIND_TO_CATEGORY,
    categorize_runtime_error_kind,
)

REPO = Path(__file__).resolve().parent.parent


def _empty_report(**kwargs) -> RenderReport:
    """Constructor helper. Defaults make a clean structural-parity
    report; pass overrides to test variations."""
    defaults = {
        "backend": "figma",
        "ir_node_count": 5,
        "rendered_node_count": 5,
        "errors": [],
    }
    defaults.update(kwargs)
    return RenderReport(**defaults)


class TestRuntimeErrorCategoriesProperty:
    """`RenderReport.runtime_error_categories` returns a Counter dict
    grouping runtime errors by their diagnostic category."""

    def test_empty_runtime_errors_yields_empty_categories(self):
        r = _empty_report()
        assert r.runtime_error_categories == {}

    def test_categories_count_correctly(self):
        """A canonical mix: 3 font_health + 2 escaped_artifact + 1
        instance_materialization should bucket cleanly."""
        r = _empty_report(
            runtime_errors=[
                {"kind": "font_load_failed", "family": "Akkurat"},
                {"kind": "font_load_failed", "family": "Akkurat-Bold"},
                {"kind": "font_load_failed", "family": "GT Walsheim"},
                {"kind": "phase2_orphan", "node_id": "9999:1"},
                {"kind": "phase2_orphan", "node_id": "9999:2"},
                {"kind": "not_an_instance", "eid": "x"},
            ],
        )
        cats = r.runtime_error_categories
        assert cats == {
            "font_health": 3,
            "escaped_artifact": 2,
            "instance_materialization": 1,
        }

    def test_unknown_kind_buckets_as_uncategorized(self):
        """Codex review: non-throwing in production. Old payloads or
        kinds added without map updates land in 'uncategorized' so
        callers don't crash; the convention test catches the gap in
        CI separately."""
        r = _empty_report(
            runtime_errors=[
                {"kind": "this_is_not_a_real_kind", "error": "x"},
                {"kind": "another_unknown", "error": "y"},
                {"kind": "font_load_failed", "family": "F"},
            ],
        )
        cats = r.runtime_error_categories
        assert cats.get("uncategorized") == 2
        assert cats.get("font_health") == 1

    def test_non_dict_entries_skipped(self):
        """Defensive — runtime_errors is typed list[dict], but if a
        malformed walk slipped a non-dict in, categorization
        shouldn't crash."""
        r = _empty_report(
            runtime_errors=[
                {"kind": "font_load_failed"},
                "malformed",  # type: ignore
                None,  # type: ignore
                {"kind": "phase2_orphan"},
            ],
        )
        cats = r.runtime_error_categories
        assert cats == {"font_health": 1, "escaped_artifact": 1}


class TestIsRuntimeCleanProperty:
    """P4 contract: explicit `is_runtime_clean` channel so callers
    don't have to write `runtime_error_count == 0` themselves."""

    def test_no_runtime_errors_is_clean(self):
        r = _empty_report()
        assert r.is_runtime_clean is True

    def test_any_runtime_error_breaks_clean(self):
        r = _empty_report(
            runtime_errors=[{"kind": "font_load_failed"}],
        )
        assert r.is_runtime_clean is False

    def test_strict_parity_decomposes_into_structural_and_runtime(self):
        """The headline P4 invariant — `is_parity` is now provably
        the AND of two named channels, not an inline conjunction.
        Any caller that decomposes one will decompose them all."""
        # All true
        r = _empty_report()
        assert r.is_structural_parity is True
        assert r.is_runtime_clean is True
        assert r.is_parity is True

        # Structural fails, runtime clean
        r = _empty_report(
            errors=[StructuredError(kind=KIND_MISSING_CHILD, id="e1")],
        )
        assert r.is_structural_parity is False
        assert r.is_runtime_clean is True
        assert r.is_parity is False

        # Structural OK, runtime dirty
        r = _empty_report(
            runtime_errors=[{"kind": "font_load_failed"}],
        )
        assert r.is_structural_parity is True
        assert r.is_runtime_clean is False
        assert r.is_parity is False


class TestCategorizationMapStructure:
    """The central map in `dd/runtime_errors.py` is the single source
    of truth. These tests pin its shape and consistency."""

    def test_every_value_is_a_declared_category(self):
        """Catches typos like 'instance_meterialization' vs
        'instance_materialization' that wouldn't otherwise surface."""
        for kind, category in RUNTIME_ERROR_KIND_TO_CATEGORY.items():
            assert category in RUNTIME_ERROR_CATEGORIES, (
                f"P4: kind {kind!r} maps to undeclared category "
                f"{category!r}. Declared categories: "
                f"{sorted(RUNTIME_ERROR_CATEGORIES)}"
            )

    def test_helper_returns_uncategorized_for_unknown(self):
        assert categorize_runtime_error_kind("not_real") == "uncategorized"

    def test_helper_returns_correct_category(self):
        assert categorize_runtime_error_kind(
            "font_load_failed"
        ) == "font_health"
        assert categorize_runtime_error_kind(
            "phase2_orphan"
        ) == "escaped_artifact"
        assert categorize_runtime_error_kind(
            "phase1_mode1_prop_failed"
        ) == "instance_materialization"

    def test_no_kind_maps_to_uncategorized_in_central_map(self):
        """`uncategorized` is the FALLBACK for unknown kinds, not a
        valid category to map known kinds to. If a kind genuinely
        doesn't fit any category, give it its own category."""
        for kind, category in RUNTIME_ERROR_KIND_TO_CATEGORY.items():
            assert category != "uncategorized", (
                f"P4: kind {kind!r} should not map to 'uncategorized' "
                f"in the central map — give it a real category"
            )


class TestConventionEnforcement:
    """The convention test. When a new `__errors.push({kind: '...'})`
    literal or `_guarded_op(..., 'kind')` argument is added in
    `dd/render_figma_ast.py`, `dd/renderers/figma.py`, or
    `render_test/walk_ref.js`, it MUST also be added to
    `RUNTIME_ERROR_KIND_TO_CATEGORY`. This test fails CI when the
    map drifts.

    Same shape as P2's orphan-detector test: walks the source,
    extracts the kinds, asserts membership.
    """

    @staticmethod
    def _scan_kinds() -> set[str]:
        """Discover every runtime-error kind emitted by the codebase.
        Combines:
        - regex over `kind: 'foo'` literals in JS-template strings
        - AST walk for `_guarded_op(..., 'kind')` and
          `_guard_naked_prop_lines(..., 'kind')` Python calls
        Both renderer files + the walker.
        """
        kinds: set[str] = set()
        files = [
            REPO / "dd/render_figma_ast.py",
            REPO / "dd/renderers/figma.py",
            REPO / "render_test/walk_ref.js",
        ]
        # Regex over literal kind:'...' or kind:"..." (with optional
        # backslash-escaping for kind values inside template strings).
        pat = re.compile(
            r"""kind\s*:\s*\\?['"]([a-z][a-z0-9_]*)\\?['"]"""
        )
        for f in files:
            text = f.read_text()
            for m in pat.finditer(text):
                kinds.add(m.group(1))

        # AST walk for the two Python helpers (the kind passes through
        # as a Python-side string and then gets templated into JS, so
        # the regex above misses these).
        guarded_helpers = {"_guarded_op", "_guard_naked_prop_lines"}
        for f in (
            REPO / "dd/render_figma_ast.py",
            REPO / "dd/renderers/figma.py",
        ):
            tree = ast.parse(f.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = None
                    if isinstance(fn, ast.Name):
                        name = fn.id
                    elif isinstance(fn, ast.Attribute):
                        name = fn.attr
                    if name in guarded_helpers and len(node.args) >= 3:
                        a = node.args[2]
                        if isinstance(a, ast.Constant) and isinstance(
                            a.value, str
                        ):
                            kinds.add(a.value)
        return kinds

    def test_every_emitted_kind_has_a_category(self):
        """The convention. Every kind the renderer or walker
        actually pushes into __errors must appear in the
        categorization map. Adding a new push site without
        updating the map fails this test in CI."""
        emitted = self._scan_kinds()
        # The literal "{kind}" is a template placeholder, not a real
        # kind — skip it. Any other interpolated kind is a bug; we'd
        # want CI to flag it (so we don't silently filter).
        emitted.discard("kind")  # defensive in case a stray label appears
        unmapped = sorted(
            k for k in emitted
            if k not in RUNTIME_ERROR_KIND_TO_CATEGORY
        )
        assert not unmapped, (
            "P4 convention violation: the following runtime-error "
            "kinds are emitted by dd/render_figma_ast.py / "
            "dd/renderers/figma.py / render_test/walk_ref.js but are "
            "not present in dd/runtime_errors.py:"
            "RUNTIME_ERROR_KIND_TO_CATEGORY. Add them to the map "
            "before this test will pass:\n  "
            + "\n  ".join(unmapped)
        )

    def test_no_orphaned_categorizations(self):
        """The reverse — every kind in the map should still be
        emitted somewhere. If a kind was renamed/deleted in the
        renderer, the map should be cleaned up too. This is a
        soft check: if a kind is in the map but not emitted, the
        map is stale (and the dead entry is harmless but confusing)."""
        emitted = self._scan_kinds()
        emitted.discard("kind")
        orphan_map_entries = sorted(
            k for k in RUNTIME_ERROR_KIND_TO_CATEGORY
            if k not in emitted
        )
        # A small allowlist for kinds that may legitimately exist in
        # the map but not in source (e.g. kinds that come from
        # external/historical walk payloads we still want to
        # categorize). Keep this list short.
        ALLOWED_ORPHAN_MAP_ENTRIES: set[str] = set()
        unexpected = [
            k for k in orphan_map_entries
            if k not in ALLOWED_ORPHAN_MAP_ENTRIES
        ]
        if unexpected:
            pytest.fail(
                "P4 map drift: the following kinds appear in "
                "RUNTIME_ERROR_KIND_TO_CATEGORY but are NOT emitted "
                "by any renderer or walker source. Either delete "
                "them from the map (preferred) or add to "
                "ALLOWED_ORPHAN_MAP_ENTRIES with a comment:\n  "
                + "\n  ".join(unexpected)
            )

    def test_scan_finds_known_kinds(self):
        """Smoke test for the scanner — make sure it finds the
        kinds we know exist. Catches regressions in the scanner
        itself (e.g. a regex change that breaks discovery)."""
        emitted = self._scan_kinds()
        for known in (
            "font_load_failed",
            "text_set_failed",
            "append_child_failed",
            "render_thrown",
            "phase2_orphan",  # walker
            "phase1_mode1_prop_failed",  # _guard_naked_prop_lines
        ):
            assert known in emitted, (
                f"P4 scanner regression: {known!r} should be discovered "
                f"by _scan_kinds() but wasn't. Update the regex or "
                f"AST walk."
            )


class TestVerifierJSONSurfaceRound:
    """Verify that `dd verify --json` includes the new P4 fields. The
    test feeds a synthetic rendered_ref through the verifier and
    asserts the report exposes both is_runtime_clean and
    runtime_error_categories (so the CLI's --json payload — which
    pulls from these properties — surfaces them too)."""

    def test_verifier_report_exposes_p4_fields(self):
        from dd.verify_figma import FigmaRenderVerifier
        rendered_ref = {
            "eid_map": {},
            "errors": [
                {"kind": "font_load_failed", "family": "Akkurat"},
                {"kind": "phase2_orphan", "node_id": "9999:1"},
            ],
        }
        report = FigmaRenderVerifier().verify({"elements": {}}, rendered_ref)
        # is_runtime_clean (P4)
        assert report.is_runtime_clean is False
        # runtime_error_categories (P4)
        assert report.runtime_error_categories == {
            "font_health": 1,
            "escaped_artifact": 1,
        }
        # Existing P1 fields still work
        assert report.runtime_error_count == 2
        assert report.runtime_error_kinds == {
            "font_load_failed": 1,
            "phase2_orphan": 1,
        }
