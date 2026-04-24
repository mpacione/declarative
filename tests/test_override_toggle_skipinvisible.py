"""Substrate fix — `figma.skipInvisibleInstanceChildren` must be toggled
off around findOne-based override application.

The 2026-04-22 perf cycle (`feedback_phase1_perf_wins.md`) added
`figma.skipInvisibleInstanceChildren = true;` to the script preamble
to keep the 204-screen sweep at ~38.5s. The flag also (silently)
makes `instance.findOne(...)` skip every descendant whose master-
default `visible` is `false`, *and* the entire subtree below it.

`dd.renderers.figma._emit_override_tree` translates each child-target
override into:

    instance.findOne(n => n.id.endsWith(\";<fid>\"))

For master-default-hidden slots (e.g. the `nav/top-nav` Workshop /
share / chevron slots that the original screen unhides via
``instance_overrides:visible=true``), `findOne` returns `null` under
the perf flag — the unhide / swap / property override silently
no-ops. Visual evidence: screen 333 (iPad Pro 11" - 43) renders
without the Workshop button, share icon, dropdown chevron, and the
shape-picker buttons, yet ``is_parity=True`` (the verifier's walk is
*also* blind under the same flag, so missing-then-missing matches).

Fix shape: emit ``figma.skipInvisibleInstanceChildren = false;``
immediately before each override-application block produced by
``_emit_override_tree``, then restore to ``true`` after — guarded
with try/finally so an exception inside the block doesn't leave the
flag flipped for the rest of the script.
"""

from __future__ import annotations

from dd.renderers.figma import _emit_override_tree


def _emit(node: dict) -> tuple[list[str], list[str]]:
    """Run _emit_override_tree against one synthetic override-tree node.

    Returns (lines, deferred) so callers can introspect both channels.
    """
    lines: list[str] = []
    deferred: list[str] = []
    _emit_override_tree(node, "instance_var", {}, lines, deferred)
    return lines, deferred


class TestOverrideToggleAroundFindOne:
    """Each child-target override block (the ones that use findOne) must
    be wrapped in a `skipInvisibleInstanceChildren=false` toggle.

    Self-target overrides (which apply directly to the instance variable
    and never call findOne) don't need the toggle.
    """

    def test_child_target_override_block_emits_toggle_before_findone(self):
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";5749:84295",  # the share-button slot eid
                    "properties": [
                        {"property": "visible", "value": True},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        assert "skipInvisibleInstanceChildren = false" in joined, (
            "child-target override emission must toggle the perf flag off "
            "so findOne can reach master-default-hidden descendants"
        )
        assert "skipInvisibleInstanceChildren = true" in joined, (
            "the toggle must restore the flag back to true so unrelated "
            "later operations keep the perf benefit"
        )
        # Restore must come AFTER the findOne block (i.e. after the line
        # that references the flag-off behavior).
        toggle_off_idx = joined.find("skipInvisibleInstanceChildren = false")
        toggle_on_idx = joined.find("skipInvisibleInstanceChildren = true")
        find_one_idx = joined.find("findOne")
        assert toggle_off_idx < find_one_idx < toggle_on_idx, (
            "expected order: toggle-off, then findOne block, then toggle-on; "
            f"got off@{toggle_off_idx}, find@{find_one_idx}, on@{toggle_on_idx}"
        )

    def test_self_target_override_does_not_need_toggle(self):
        """Self-target overrides apply directly to the instance variable
        without findOne — no toggle needed. Avoid spamming flag flips."""
        node = {
            "target": ":self",
            "properties": [
                {"property": "visible", "value": True},
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # Self-target should NOT emit the toggle (no findOne to protect).
        assert "skipInvisibleInstanceChildren" not in joined

    def test_toggle_uses_try_finally_so_restore_runs_on_throw(self):
        """If an override application throws (e.g. findOne returns a
        node whose .visible setter is unsupported in this Figma build),
        the flag must still be restored. Otherwise the rest of the
        script runs with the wrong flag state and silently corrupts
        downstream walks. Implements Codex's risk note from the
        2026-04-23 fork decision."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";5749:84295",
                    "properties": [
                        {"property": "visible", "value": True},
                    ],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        # Look for the try/finally idiom — minimum: both keywords appear
        # AFTER the toggle-off and AROUND the toggle-on.
        assert "try" in joined and "finally" in joined, (
            "toggle restore must be guarded by try/finally so an exception "
            "inside the override block doesn't leak the flipped flag state"
        )

    def test_path_override_visible_block_also_toggles(self):
        """The second findOne-based override site lives in
        ``dd/render_figma_ast.py`` — the
        ``descendant_visibility_resolver`` path emits
        ``{instance}.findOne(... endsWith(';<fid>'))`` to apply
        ``PathOverride .visible`` flips. Same flag, same blindness, same
        fix needed. Verified by emitting a tiny doc through the renderer
        and asserting the toggle bracket appears around the findOne
        line."""
        # Build a synthetic resolver bucket + node to drive emission.
        # Easier path: import the helper used by render_figma's
        # head-properties pipe, give it a PathOverride, and check the
        # produced lines.
        from dd.markup_l3 import Literal_, Node, NodeHead, PathOverride
        from dd.render_figma_ast import _emit_visibility_path_overrides

        path_override = PathOverride(
            path="example-child.visible",
            value=Literal_(lit_kind="bool", raw="true", py=True),
        )
        # Resolver maps the override's path to the master child's
        # Figma id — same shape compress_l3 emits.
        resolver = {"button-1": {"example-child.visible": "5749:99999"}}
        head = NodeHead(
            head_kind="comp-ref",
            type_or_path="button/primary",
            eid="button-1",
            positional=None,
            properties=(path_override,),
        )
        # Minimal node — block stays None for a leaf head.
        node = Node(head=head, block=None)
        spec_key_map: dict[int, str] = {id(node): "button-1"}

        lines: list[str] = []
        _emit_visibility_path_overrides(
            node=node,
            var="instance_var",
            spec_key_map=spec_key_map,
            descendant_visibility_resolver=resolver,
            lines=lines,
        )
        joined = "\n".join(lines)
        assert "findOne" in joined, (
            "expected the path-override block to emit a findOne call"
        )
        assert "skipInvisibleInstanceChildren = false" in joined, (
            "path-override emission needs the same toggle-off as "
            "_emit_override_tree (same findOne blindness root cause)"
        )
        assert "skipInvisibleInstanceChildren = true" in joined, (
            "and the same toggle-on restore"
        )

    def test_multiple_child_overrides_each_get_their_own_toggle_block(self):
        """An override tree with N child targets emits N findOne blocks.
        Each must be wrapped — wrapping the whole tree once would still
        work, but per-block keeps the perf flag back on as soon as
        possible (minimising the perf-degraded window when the override
        block has been emitted but the next operation is unrelated)."""
        node = {
            "target": ":self",
            "children": [
                {
                    "target": ";a",
                    "properties": [{"property": "visible", "value": True}],
                },
                {
                    "target": ";b",
                    "properties": [{"property": "visible", "value": True}],
                },
            ],
        }
        lines, _ = _emit(node)
        joined = "\n".join(lines)
        toggle_offs = joined.count("skipInvisibleInstanceChildren = false")
        toggle_ons = joined.count("skipInvisibleInstanceChildren = true")
        assert toggle_offs == 2, (
            f"expected one toggle-off per child target (2), got {toggle_offs}"
        )
        assert toggle_ons == 2, (
            f"expected one toggle-on per child target (2), got {toggle_ons}"
        )
