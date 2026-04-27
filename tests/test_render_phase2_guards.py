"""Tests for per-op guard coverage in render_figma_ast Phase 2.

Per docs/learnings-tier-b-failure-modes.md F3 (cascading Phase-2
abort): the script wraps Phases 1+2+3 in ONE outer try/catch.
If any naked op throws mid-Phase-2, every subsequent op is
skipped — including the final `_rootPage.appendChild(root_var)`,
which orphans the entire rendered subtree from the page. The
user sees "no nesting hierarchy" because the tree isn't attached
to anything.

Fix (per the Tier E audit subagent report): wrap each naked
op in Phase 2 with the same per-op try/catch pattern that
`characters=` already uses. Convert cascading abort into
per-op structured `__errors` entries.
"""

from __future__ import annotations

from dd.markup_l3 import parse_l3
from dd.render_figma_ast import render_figma


def _render(src: str) -> str:
    """Minimal render: empty conn, empty maps, basic fonts."""
    doc = parse_l3(src)
    nid_map: dict[int, int] = {}
    spec_key_map: dict[int, str] = {}
    for node in _iter_nodes(doc.top_level):
        spec_key_map[id(node)] = node.head.eid or ""
    script, _refs = render_figma(
        doc, conn=None, nid_map=nid_map,
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map={
            id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
        },
    )
    return script


def _iter_nodes(nodes):
    for n in nodes:
        yield n
        if getattr(n, "block", None):
            yield from _iter_nodes(n.block.statements)


_NESTED_DOC = """screen #screen-1 {
  frame #card-1 {
    text #title-1 "hello"
    text #body-1 "world"
  }
}"""


class TestAppendChildGuards:
    """Every `parent.appendChild(child)` call in Phase 2 must be
    wrapped in its own try/catch so a single throw doesn't
    cascade through the rest of the wiring."""

    def test_parent_child_appendchild_is_guarded(self) -> None:
        script = _render(_NESTED_DOC)
        # Pattern: try { n0.appendChild(n1); } catch (__e) { ... }
        # Not pattern: bare "n0.appendChild(n1);" without try
        append_lines = [
            line for line in script.split("\n")
            if ".appendChild(" in line
        ]
        # Count guarded vs naked
        naked = [l for l in append_lines if not l.strip().startswith("try")
                 and ".appendChild(" in l
                 and "__errors" not in l]
        # Helper-defined appendChild calls (inside
        # _missingComponentPlaceholder helper) are OK — they're
        # in their own try. Filter to only Phase 2 appendChild
        # lines (`nN.appendChild(nM)` pattern).
        phase2_naked = [
            l for l in naked
            if "n" in l
            and not l.lstrip().startswith("//")
            and not ("f.appendChild" in l or "n.appendChild" in l)
        ]
        # Every Phase-2 appendChild should be wrapped — none naked.
        assert not phase2_naked, (
            "Phase 2 has naked appendChild calls (F3 cascade risk): "
            + "\n".join(phase2_naked[:5])
        )

    def test_root_appendchild_is_guarded(self) -> None:
        """The final `_rootPage.appendChild(root_var)` is THE
        critical op — if it throws or is skipped, the screen is
        orphaned and invisible."""
        script = _render(_NESTED_DOC)
        # Look for the rootPage append line
        root_lines = [
            line for line in script.split("\n")
            if "_rootPage.appendChild" in line
            or "_page.appendChild" in line
        ]
        assert root_lines, "No root appendChild emitted"
        for line in root_lines:
            assert "try" in line and "catch" in line, (
                f"Root appendChild is naked (F3 catastrophic): {line}"
            )
            # Structured diagnostic on failure
            assert "root_append_failed" in line or (
                "__errors" in line and "kind" in line
            ), f"Root appendChild catch lacks structured error: {line}"

    def test_append_failure_emits_structured_error(self) -> None:
        """When the guarded appendChild catches, it must push a
        structured __errors entry with eid + parent_eid + kind.
        Proposer agents consume this."""
        script = _render(_NESTED_DOC)
        # At least one append_child_failed pattern should exist.
        assert "append_child_failed" in script, (
            "Expected kind:'append_child_failed' pattern in script"
        )


class TestLayoutSizingGuards:
    """Phase 2 emits `layoutSizingHorizontal`/`Vertical` on every
    auto-layout child. Known-fragile per
    `feedback_text_layout_invariants.md` (evaluation against
    empty-sibling widths, resize flip quirks). Must be per-op
    guarded."""

    def test_layout_sizing_is_guarded(self) -> None:
        # Build a doc where parent is explicitly auto-layout so
        # the sizing branch fires.
        src = """screen #screen-1 layout_direction=vertical {
  frame #card-1 layout_direction=vertical {
    text #title-1 "hello"
  }
}"""
        script = _render(src)
        sizing_lines = [
            line for line in script.split("\n")
            if "layoutSizingHorizontal" in line
            or "layoutSizingVertical" in line
        ]
        # If no sizing lines emit, the test is fine — nothing to
        # verify. If they do emit, they must be guarded.
        for line in sizing_lines:
            stripped = line.strip()
            assert stripped.startswith("try"), (
                f"layoutSizing op is naked (Phase 2 cascade risk): "
                f"{stripped[:120]}"
            )


class TestRootPositionGuards:
    """Root position assignments (x/y when canvas_position is set)
    don't fire in the default path, but when they do they should
    be per-op guarded."""

    def test_root_position_is_guarded_when_emitted(self) -> None:
        from dd.markup_l3 import parse_l3
        from dd.render_figma_ast import render_figma

        doc = parse_l3(_NESTED_DOC)
        spec_key_map = {
            id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
        }
        script, _ = render_figma(
            doc, conn=None, nid_map={},
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            canvas_position=(100.0, 200.0),
        )
        # root_var.x = 100.0; root_var.y = 200.0; must be guarded
        pos_lines = [
            line for line in script.split("\n")
            if ".x = 100" in line or ".y = 200" in line
        ]
        assert pos_lines, "canvas_position provided but no x/y lines emitted"
        for line in pos_lines:
            assert line.strip().startswith("try"), (
                f"root position op is naked: {line.strip()[:120]}"
            )
