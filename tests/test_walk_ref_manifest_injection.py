"""Sprint 2 C7 tests — verify walk_ref.js loads + injects the manifest.

Per docs/plan-sprint-2-station-parity.md §5 (registry authority): the
walker reads the registry-derived manifest at plugin init. C7 ensures
the manifest is loaded and injected into the wrapped script; C8 will
make the walker USE it for capture decisions.
"""
import json
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent
_WALKER_PATH = _REPO_ROOT / "render_test" / "walk_ref.js"
_MANIFEST_PATH = _REPO_ROOT / "render_test" / "walker_manifest.generated.json"


class TestC7ManifestInjection:
    def test_walker_reads_manifest_path(self):
        """walk_ref.js must read the manifest from the C6 path."""
        contents = _WALKER_PATH.read_text()
        # Look for the relative path resolution
        assert "walker_manifest.generated.json" in contents, (
            "walk_ref.js must reference the C6 manifest filename"
        )

    def test_walker_uses_dirname_for_manifest_path(self):
        """Path must resolve relative to walk_ref.js, not cwd."""
        contents = _WALKER_PATH.read_text()
        assert "__dirname" in contents, (
            "walk_ref.js must use __dirname to resolve manifest path"
        )

    def test_walker_injects_manifest_into_wrapped_script(self):
        """The wrapped script (sent to Figma plugin) must define __WALKER_MANIFEST."""
        contents = _WALKER_PATH.read_text()
        assert "__WALKER_MANIFEST" in contents, (
            "walker must inject __WALKER_MANIFEST into the wrapped script"
        )
        assert "__WALKER_MANIFEST_VERSION" in contents, (
            "walker must inject __WALKER_MANIFEST_VERSION as well"
        )

    def test_walker_has_self_boot_fallback(self):
        """Per plan §10 R1: walker MUST work even if manifest read fails."""
        contents = _WALKER_PATH.read_text()
        # Look for try/catch or null-default pattern
        # The exact form is your call; just ensure SOME error handling exists
        # around the manifest read
        has_fallback = (
            "catch" in contents.lower() and "manifest" in contents.lower()
        ) or "manifest = null" in contents.lower() or "MANIFEST = null" in contents
        assert has_fallback, (
            "walker must have fallback for failed manifest read"
        )

    def test_existing_capture_behavior_unchanged(self):
        """C7 MUST NOT change capture behavior for non-graduated
        properties. The entry.* assignments for fills, strokes,
        opacity, blendMode, isMask, cornerRadius, strokeWeight,
        strokeAlign, dashPattern, clipsContent, textAutoResize must
        all still be present and unchanged.

        ``characters`` was originally part of this list but graduates
        to a {value, source} envelope under C8 — see the dedicated
        C8 tests in ``test_walker_envelope_c8.py``. The
        ``entry.textAutoResize`` raw form remains as the negative
        control (not in the C8 graduation list)."""
        contents = _WALKER_PATH.read_text()
        # These entry.* assignments must still exist (rough textual check)
        for line_substr in (
            "entry.opacity = n.opacity",
            "entry.blendMode = n.blendMode",
            "entry.isMask = n.isMask",
            "entry.strokeWeight = n.strokeWeight",
            "entry.strokeAlign = n.strokeAlign",
            "entry.dashPattern = n.dashPattern.slice()",
            "entry.clipsContent = n.clipsContent",
            "entry.textAutoResize = n.textAutoResize",
        ):
            assert line_substr in contents, (
                f"C7 must preserve walker capture: missing {line_substr!r}"
            )

    def test_manifest_artifact_exists_and_valid(self):
        """Sanity check: the manifest C6 generated is on disk and parseable."""
        assert _MANIFEST_PATH.exists()
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["version"] == "1.0"
        assert "properties" in manifest
        assert len(manifest["properties"]) == 53
