"""F13c — GROUP deferral in `dd/render_figma_ast.py`.

Phase D visual-diff exposed: HGB Customer Complete Info Tablet's
"Group 4746" logo rendered with vector children at the wrong positions
(offset by the group's own x/y) because the AST renderer silently
coerced GROUP→FRAME via the `_TYPE_TO_CREATE_CALL` fallback.

Root cause: the canonical AST renderer (`render_figma_ast.py`)
inherited a `_TYPE_TO_CREATE_CALL` map that has no entry for "group"
and falls through to `figma.createFrame()`. Children's stored x/y
come from extraction reading Plugin API `node.x` — which for a
GROUP-CHILD is reported in the GROUP'S PARENT coordinate space (per
`feedback_rest_plugin_coord_convention_divergence.md`). When emitted
into a FRAME (where x is interpreted as frame-local), every child gets
offset by the GROUP's own (x, y).

The OLD `dd/renderers/figma.py` (now dead) had a deferred-group path
at line 1505 — the AST renderer never had one. F13c ports the
correct semantics:

1. Phase 1 skips groups entirely (no create, no name, no visual,
   no layout, no M assign).
2. Phase 2's appendChild loop:
   - Skips groups (they don't exist as Figma nodes yet).
   - For non-groups whose parent is a deferred group, walks UP to
     the nearest non-deferred ancestor and appends THERE
     temporarily. Records the child's var in the immediate-parent
     group's `direct_children`.
3. Phase 2's POST-loop block walks deferred groups bottom-up
   (innermost first) and emits
   `figma.group([direct_children_vars], grandparent_var)`. Outer
   groups' direct_children includes inner groups' vars (registered
   during the appendChild loop).
4. Phase 3 emits ONLY position (x, y) and visibility for groups.
   No resize, no layoutSizing, no fills/strokes — Figma `GroupNode`
   doesn't support those.

Codex gpt-5.5 specified this shape (2026-04-25). Key decisions
they pushed back on:
- Do NOT replicate the OLD path's "register descendant in EVERY
  ancestor's children_vars" pattern — suspicious for nested groups.
  Use direct-AST-children only.
- Bottom-up by AST depth, not by deferral-map insertion order.
- Use `figma.group(nodes, parent)` + `parent.insertChild(idx, g)`
  for z-order; don't try the new optional `index` argument (not
  uniformly supported across Figma desktop versions).
- Empty groups: substitute a `createFrame()` placeholder so var_map
  + M[...] mapping survives. Figma's Plugin API rejects empty groups.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / "audit" / "20260425-1725-phaseD-fullsweep" / "audit-fresh.declarative.db"


def _has_audit_db() -> bool:
    return DB_PATH.exists()


def _generate(screen_id: int) -> str:
    result = subprocess.run(
        [
            ".venv/bin/python", "-m", "dd", "generate",
            "--db", str(DB_PATH), "--screen", str(screen_id),
        ],
        cwd=str(REPO),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"generate failed: {result.stderr}"
    return result.stdout


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestGroupDeferralEmitsFigmaGroup:
    """The renderer must emit `figma.group([...], parent)` for GROUP
    nodes — NOT `figma.createFrame()`."""

    def test_screen_2_emits_three_figma_group_calls(self):
        """Group 4746 contains Group 4744 + Group 4745 → 3 groups
        nested. Each must produce a figma.group() call."""
        script = _generate(2)
        # Count figma.group( occurrences — should be exactly 3 for
        # this screen (one per source GROUP).
        count = script.count("figma.group(")
        assert count == 3, (
            f"expected 3 figma.group() calls for the 3 nested GROUPs "
            f"on screen 2 (Group 4746, 4744, 4745); got {count}"
        )

    def test_screen_2_does_not_create_frames_named_group_4746(self):
        """If we still saw `const n87 = figma.createFrame()` followed
        by `n87.name = "Group 4746"`, the deferral didn't fire."""
        script = _generate(2)
        # Find the line that creates the variable for Group 4746.
        lines = script.split("\n")
        # The deferred-group block emits `const <var> = (function() {
        # try { return figma.group([...], ...); } catch ... })()`.
        # Make sure no `const nX = figma.createFrame()` precedes a
        # `nX.name = "Group 4746"` (which would be the bug shape).
        for i, line in enumerate(lines):
            if 'name = "Group 4746"' in line:
                # Walk backwards looking for the const declaration
                # of this var.
                # Extract the var from "try { nX.name = ..." pattern
                import re
                m = re.search(r"\b(n\d+)\.name = \"Group 4746\"", line)
                if not m:
                    continue
                var = m.group(1)
                # Find the matching const declaration earlier
                for j in range(i - 1, -1, -1):
                    if f"const {var} = " in lines[j]:
                        # Must be a figma.group(), NOT createFrame().
                        # Allowed: createFrame inside the catch
                        # fallback (the placeholder for failed groups).
                        decl = lines[j]
                        assert "figma.group(" in decl, (
                            f"Group 4746 must be created via "
                            f"figma.group(), not createFrame(). Got: "
                            f"{decl!r}"
                        )
                        break

    def test_groups_emit_in_bottom_up_order(self):
        """Inner groups (Group 4744, Group 4745) must be created
        BEFORE the outer Group 4746, because the outer's
        direct_children list contains the inner-group vars."""
        script = _generate(2)
        lines = script.split("\n")
        # Find the line index of each group's figma.group() call.
        idx_4744 = next(
            (i for i, line in enumerate(lines)
             if 'figma.group(' in line and 'group-2' in line),
            None,
        )
        idx_4745 = next(
            (i for i, line in enumerate(lines)
             if 'figma.group(' in line and 'group-3' in line),
            None,
        )
        idx_4746 = next(
            (i for i, line in enumerate(lines)
             if 'figma.group(' in line and 'group-1' in line),
            None,
        )
        assert idx_4744 is not None
        assert idx_4745 is not None
        assert idx_4746 is not None
        # Inner groups before outer.
        assert idx_4744 < idx_4746, (
            "Group 4744 (inner) must be created before Group 4746 (outer); "
            f"got 4744@{idx_4744}, 4746@{idx_4746}"
        )
        assert idx_4745 < idx_4746, (
            "Group 4745 (inner) must be created before Group 4746 (outer); "
            f"got 4745@{idx_4745}, 4746@{idx_4746}"
        )


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestGroupCreationShape:
    """The shape of the figma.group() call must wrap children in a
    try/catch that falls back to createFrame on failure."""

    def test_group_create_has_try_catch_fallback(self):
        """Per Codex F13c spec: figma.group can throw (empty array,
        nodes already detached, etc.). The wrapper must catch and
        substitute a createFrame placeholder so the rest of the
        script doesn't lose the var binding."""
        script = _generate(2)
        # Look for the canonical pattern.
        assert "kind:\"group_create_failed\"" in script, (
            "figma.group() emission must record group_create_failed "
            "in __errors on throw, with a createFrame fallback"
        )

    def test_group_writes_no_visual_properties(self):
        """Codex F13c: do NOT emit fills/strokes/cornerRadius for
        GROUPs — Figma `GroupNode` rejects them with 'object is not
        extensible'. Any visual that does sneak through is a bug."""
        script = _generate(2)
        lines = script.split("\n")
        # Find vars that are groups (created via figma.group)
        import re
        group_vars = set()
        for line in lines:
            m = re.search(r"const (n\d+) = \(function\(\)", line)
            if m and "figma.group(" in line:
                group_vars.add(m.group(1))
        # For each group var, scan for forbidden visual writes.
        forbidden = ["fills =", "strokes =", "cornerRadius =",
                     "topLeftRadius =", "layoutMode =",
                     "paddingTop =", "itemSpacing ="]
        for line in lines:
            for var in group_vars:
                for prop in forbidden:
                    bad = f"{var}.{prop.split(' ')[0]} ="
                    assert bad not in line, (
                        f"GROUP var {var} must not write {prop!r} "
                        f"(GroupNode doesn't support it). "
                        f"Got line: {line.strip()[:100]}"
                    )


@pytest.mark.skipif(not _has_audit_db(), reason="audit DB not present")
class TestGroupPositionInPhase3:
    """Group position (x, y) is set in Phase 3 AFTER appendChild and
    after figma.group() has auto-fit the bbox."""

    def test_group_emits_x_and_y_in_phase3(self):
        script = _generate(2)
        # The group's position must appear AFTER the figma.group()
        # call AND after the M[group-1] = ... assignment.
        group_call_idx = script.find('eid:"group-1", kind:"group_create_failed"')
        m_assign_idx = script.find('M["group-1"]')
        position_x_idx = script.find('n87.x = 19.259262084960938')
        position_y_idx = script.find('n87.y = 11.851802825927734')
        assert 0 <= group_call_idx < m_assign_idx < position_x_idx
        assert position_x_idx < position_y_idx
