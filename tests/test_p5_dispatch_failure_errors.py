"""P5 (Phase E follow-on, post-rextract audit #2 findings 1 + 5) —
explicit dispatch-failure errors instead of silent fall-through.

Forensic audit #2 (2026-04-26) found two anti-pattern sites in
``dd/render_figma_ast.py`` where a dispatch precondition fails and
the renderer silently takes a degraded path:

1. **Mode-1 dispatch fall-through** (``render_figma_ast.py:840-883``).
   Upstream sets ``use_mode1=True`` because ``head_kind == "comp-ref"``
   indicates the markup expected a Mode-1 (createInstance) path. The
   inner gate then re-checks for component identifiers
   (``component_figma_id``/``instance_figma_node_id``/``component_key``)
   and, when none are present, the ``if`` body is skipped — the loop
   then falls through to the generic ``createFrame()`` path with no
   diagnostic. The verifier never learns Mode-1 was expected and
   missed; failures show up as silent ``DRIFT`` on screens that
   should have rendered as instances. The 17 newly-revealed DRIFT
   screens in the post-rextract sweep are this bug surfacing once
   CKR coverage hit 100%.

2. **Override target missing** (``render_figma_ast.py:1509``).
   ``_emit_visibility_path_overrides`` resolves each PathOverride
   path via ``descendant_visibility_resolver`` and silently
   ``continue``s when ``resolver_bucket.get(prop.path)`` returns
   ``None``. The JS-side ``_t = _targets.get(...); if (_t) ...;``
   tail is also silent when the runtime ``findAll`` doesn't surface
   the node. Either way, ``.visible=true/false`` overrides are
   dropped without trace.

Distinct from existing kinds:
- ``degraded_to_mode2`` (already in the map under ``mode_fallback``)
  fires when ``is_db_instance=True`` but no IDs were available —
  i.e. the renderer KNEW Mode-1 wasn't possible and intentionally
  fell back. ``mode1_dispatch_failed`` is the unintentional case:
  ``use_mode1=True`` but the gate failed unexpectedly. Codex review
  (gpt-5.5 high reasoning, 2026-04-26): keep them distinct so the
  intentional-fallback signal isn't conflated with the
  precondition-failure signal.
- ``not_an_instance`` / ``no_main_component`` / ``missing_component_node``
  fire INSIDE the Mode-1 IIFE at runtime when the createInstance
  call itself can't proceed. ``mode1_dispatch_failed`` fires at
  COMPILE TIME when we never even got into the IIFE.
- ``override_target_missing`` is a write-on-instance-tree failure
  (same family as ``phase1_mode*_prop_failed``); per Codex it
  belongs under ``instance_materialization``.
"""

from __future__ import annotations

from dd.markup_l3 import Literal_, Node, NodeHead, PathOverride, parse_l3
from dd.render_figma_ast import _emit_visibility_path_overrides, render_figma
from dd.runtime_errors import (
    RUNTIME_ERROR_KIND_TO_CATEGORY,
    categorize_runtime_error_kind,
)


def _iter_nodes(nodes):
    for n in nodes:
        yield n
        if getattr(n, "block", None):
            yield from _iter_nodes(n.block.statements)


def _render_minimal(src: str) -> str:
    """Render an L3 doc with no DB visuals — comp-ref heads will hit
    the dispatch site without component identifiers in raw_visual."""
    doc = parse_l3(src)
    spec_key_map = {
        id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
    }
    original_name_map = {
        id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
    }
    script, _refs = render_figma(
        doc,
        conn=None,
        nid_map={},
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
    )
    return script


class TestMode1DispatchFailedKindIsRegistered:
    """The new kind must be in the categorization map and helper."""

    def test_mode1_dispatch_failed_in_map(self):
        assert "mode1_dispatch_failed" in RUNTIME_ERROR_KIND_TO_CATEGORY

    def test_mode1_dispatch_failed_categorized_as_component_resolution(self):
        """Codex (gpt-5.5 2026-04-26): the failure mode is missing
        Mode-1 identity/resolution data, so ``component_resolution`` is
        the correct bucket. NOT ``mode_fallback`` (that's intentional
        fallback) and NOT ``instance_materialization`` (that's runtime
        write failure on a successfully-created instance)."""
        assert (
            categorize_runtime_error_kind("mode1_dispatch_failed")
            == "component_resolution"
        )

    def test_override_target_missing_in_map(self):
        assert "override_target_missing" in RUNTIME_ERROR_KIND_TO_CATEGORY

    def test_override_target_missing_categorized_as_instance_materialization(
        self,
    ):
        """Codex (gpt-5.5 2026-04-26): override application is an
        instance-tree property write that didn't land. Same family as
        the existing ``phase1_mode*_prop_failed`` kinds, which already
        live in ``instance_materialization``."""
        assert (
            categorize_runtime_error_kind("override_target_missing")
            == "instance_materialization"
        )


class TestMode1DispatchFailedEmission:
    """When ``use_mode1=True`` (because ``head_kind=="comp-ref"``) but
    the inner gate fails (no component identifiers in raw_visual), the
    renderer must push ``mode1_dispatch_failed`` into ``__errors``
    instead of silently falling through to ``createFrame()``."""

    def test_comp_ref_without_db_visuals_emits_mode1_dispatch_failed(self):
        """A ``-> button/primary`` comp-ref head with NO db_visuals
        triggers ``use_mode1=True`` (head_kind=="comp-ref") but the
        inner gate (``component_figma_id or instance_figma_node_id or
        component_key``) fails because raw_visual is empty. Before P5
        this fell through silently. After P5 it must emit
        ``mode1_dispatch_failed`` with the eid."""
        src = (
            "screen #screen-1 {\n"
            "  -> button/primary #button-7\n"
            "}\n"
        )
        script = _render_minimal(src)
        assert 'kind:"mode1_dispatch_failed"' in script, (
            "expected the renderer to push mode1_dispatch_failed when a "
            "comp-ref head has no component identifiers; got a silent "
            "fall-through to createFrame() instead.\nScript:\n" + script
        )
        # The eid must be carried so the verifier can attribute the
        # failure to the right node.
        assert 'eid:"button-7"' in script, (
            "mode1_dispatch_failed must carry the eid of the failed "
            "head node so verifier-side attribution works"
        )

    def test_mode1_dispatch_failed_includes_reason(self):
        """The reason field should explain WHY the gate failed —
        same shape as the existing degraded_to_mode2 emission. Lets a
        reader see at a glance which identifier was missing."""
        src = (
            "screen #screen-1 {\n"
            "  -> icon/heart #icon-3\n"
            "}\n"
        )
        script = _render_minimal(src)
        # Expect a reason: substring (don't pin the exact words —
        # the renderer-side message format may evolve, but it must
        # carry something).
        assert "reason:" in script.split('mode1_dispatch_failed')[1][:200], (
            "mode1_dispatch_failed should include a reason: field "
            "matching the convention used by degraded_to_mode2"
        )

    def test_plain_type_head_does_not_emit_mode1_dispatch_failed(self):
        """A plain ``frame`` / ``rectangle`` head was never expected
        to hit Mode-1 — ``use_mode1`` stays False and no
        ``mode1_dispatch_failed`` should appear. Regression guard
        against over-broad emission that would spam every
        non-instance node."""
        src = (
            "screen #screen-1 {\n"
            "  frame #frame-1 {\n"
            "    rectangle #rect-1\n"
            "  }\n"
            "}\n"
        )
        script = _render_minimal(src)
        assert "mode1_dispatch_failed" not in script, (
            "plain type heads should never emit mode1_dispatch_failed; "
            "use_mode1 was False so dispatch wasn't expected at all"
        )


class TestOverrideTargetMissingEmission:
    """When ``_emit_visibility_path_overrides`` finds a PathOverride
    whose path doesn't resolve to a fig_child_id (resolver_bucket
    misses), the renderer must push ``override_target_missing``
    instead of silently dropping the override."""

    def test_unresolved_path_emits_override_target_missing(self):
        """A PathOverride with a path the resolver doesn't know about
        — the override is silently dropped pre-P5. After P5 it must
        emit ``override_target_missing`` with eid + path so the
        verifier can flag the dropped override."""
        path_override = PathOverride(
            path="ghost-child.visible",  # resolver bucket has no entry for this
            value=Literal_(lit_kind="bool", raw="true", py=True),
        )
        head = NodeHead(
            head_kind="comp-ref",
            type_or_path="button/primary",
            eid="button-9",
            positional=None,
            properties=(path_override,),
        )
        node = Node(head=head, block=None)
        spec_key_map: dict[int, str] = {id(node): "button-9"}
        # Resolver has a bucket for this instance but no entry for
        # the path the override references — the silent-no-op trigger.
        resolver = {"button-9": {"some-other-child.visible": "5749:1234"}}

        lines: list[str] = []
        _emit_visibility_path_overrides(
            node=node,
            var="instance_var",
            spec_key_map=spec_key_map,
            descendant_visibility_resolver=resolver,
            lines=lines,
        )
        joined = "\n".join(lines)
        assert 'kind:"override_target_missing"' in joined, (
            "expected the path-override emitter to push "
            "override_target_missing when the resolver has no entry "
            "for the override's path; got silent drop instead.\n"
            "Lines:\n" + joined
        )
        assert 'eid:"button-9"' in joined, (
            "override_target_missing must carry the eid of the "
            "instance head whose override was dropped"
        )
        assert "ghost-child.visible" in joined, (
            "override_target_missing should carry the unresolved path "
            "so a reader can identify which override dropped"
        )

    def test_resolved_path_does_not_emit_compile_time_push(self):
        """When the resolver DOES carry the path, no compile-time
        ``override_target_missing`` push should appear. The runtime
        else-branch (covered by the next test) is a separate
        invariant — it stays in the JS but only fires when _t is
        undefined at runtime.

        This test pins that the COMPILE-TIME silent-drop site is no
        longer silent: only the ``if not fig_child_id`` block in
        Python emits override_target_missing at compile time, and
        that block must NOT fire when the resolver has the path.
        """
        path_override = PathOverride(
            path="real-child.visible",
            value=Literal_(lit_kind="bool", raw="true", py=True),
        )
        head = NodeHead(
            head_kind="comp-ref",
            type_or_path="button/primary",
            eid="button-1",
            positional=None,
            properties=(path_override,),
        )
        node = Node(head=head, block=None)
        spec_key_map: dict[int, str] = {id(node): "button-1"}
        resolver = {"button-1": {"real-child.visible": "5749:99999"}}

        lines: list[str] = []
        _emit_visibility_path_overrides(
            node=node,
            var="instance_var",
            spec_key_map=spec_key_map,
            descendant_visibility_resolver=resolver,
            lines=lines,
        )
        joined = "\n".join(lines)
        # The runtime else-branch is in the lines (it fires only when
        # _t is undefined at runtime), so the substring will appear.
        # The compile-time-only push happens BEFORE the toggle window;
        # check it didn't happen by counting occurrences.
        # Pre-toggle (compile-time): no occurrences when resolver hits.
        # Post-toggle (runtime else): one occurrence per target.
        # With one resolved target, expect exactly one occurrence
        # (the runtime else branch), not two (which would mean the
        # compile-time silent-drop ALSO fired).
        count = joined.count("override_target_missing")
        assert count == 1, (
            f"resolved-path success: expected exactly 1 occurrence "
            f"(the runtime else branch), got {count}. "
            f"More means the compile-time silent-drop ALSO emitted, "
            f"which means the resolver lookup didn't actually hit. "
            f"Lines:\n{joined}"
        )
        # And specifically the resolved-target line must use the
        # success branch (`_t.visible = ...`).
        assert "_t.visible = true" in joined

    def test_runtime_lookup_miss_emits_override_target_missing(self):
        """The JS-side ``_t = _targets.get(esc_fid)`` may return
        undefined even when the resolver SAID the fig_child_id is
        present — e.g. ``findAll`` skipped a hidden subtree that the
        toggle didn't open. The else branch of the ``if (_t)`` guard
        must push ``override_target_missing`` so this case isn't
        silent either."""
        path_override = PathOverride(
            path="real-child.visible",
            value=Literal_(lit_kind="bool", raw="true", py=True),
        )
        head = NodeHead(
            head_kind="comp-ref",
            type_or_path="button/primary",
            eid="button-2",
            positional=None,
            properties=(path_override,),
        )
        node = Node(head=head, block=None)
        spec_key_map: dict[int, str] = {id(node): "button-2"}
        resolver = {"button-2": {"real-child.visible": "5749:11111"}}

        lines: list[str] = []
        _emit_visibility_path_overrides(
            node=node,
            var="instance_var",
            spec_key_map=spec_key_map,
            descendant_visibility_resolver=resolver,
            lines=lines,
        )
        joined = "\n".join(lines)
        # The JS-side guard must push override_target_missing in its
        # else branch when _t is undefined at runtime.
        assert 'kind:"override_target_missing"' in joined, (
            "the JS-side `if (_t) _t.visible = ...; else __errors.push(...)` "
            "guard must surface runtime lookup misses as "
            "override_target_missing"
        )
