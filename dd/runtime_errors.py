"""P4 (Phase E Pattern 2 fix) — runtime-error categorization.

Phase E §7 surfaced 1015 runtime errors across 67 screens, broken into
6 distinct error classes (4 NEW vs Phase D HGB). The flat
``runtime_error_kinds`` Counter that P1 added was an improvement over
"opaque single integer" but still left the sweep summary with a long
list of unrelated kinds. ``font_load_failed`` and ``not_an_instance``
are different *failure modes* with different *fixes* — burying both in
one undifferentiated list of 31+ entries makes the sweep summary
readable but not *diagnostic*.

P4 adds a categorization layer that groups raw kinds into ~10
diagnostic categories. The category names are chosen to answer the
user's first question ("what should I look at?"):

- ``font_health`` — fonts unavailable or unloadable. Fix at the
  font-installation/licensing layer; no code change needed.
- ``component_resolution`` — component-key cascade or DB-state
  failures upstream of materialization. Fix at extract or compose.
- ``instance_materialization`` — INSTANCE creation or property writes
  on instance-rooted subtrees rejected the op (the Class N1 bug
  from Phase E §7). Fix in dd/render_figma_ast.py mode-1/mode-2 paths.
- ``text_op_failed`` — text content/style ops failed. Often a
  cascade from font_health, but the symptom surfaces here.
- ``layout_op_failed`` — autolayout direction/spacing/padding/align
  ops failed. Almost always Figma rejecting an autolayout property
  on a non-autolayout target (or vice versa).
- ``geometry_op_failed`` — resize/position/constraint/visibility ops
  failed. Usually Figma normalization (e.g. resize on a node with a
  layoutSizing FILL parent is silently no-op'd; we record the throw
  on stricter targets).
- ``child_attach_failed`` — appendChild rejected. Sonnet's name beats
  the original "tree_topology" because it tells you what the verb
  was (attach), not just where (the topology).
- ``property_write_failed`` — generic property write rejected.
  Includes group-name failures.
- ``escaped_artifact`` — node landed at the page root instead of
  inside the IR rooted-tree (P3d). Almost always a downstream
  consequence of child_attach_failed.
- ``render_thrown`` — outer try/catch fired; the script truncated
  early. Different severity from per-eid kinds: this is "the whole
  render aborted," not "one op failed."
- ``mode_fallback`` — Mode-1 → Mode-2 control-flow fallback signal.
  Recorded in __errors but is not a *failure* in the same sense
  (the renderer chose a degraded path on purpose). Kept as its own
  category so it doesn't inflate "instance_materialization" counts.

Codex design review (2026-04-25, gpt-5.5 high reasoning) chose the
central-map shape over per-push-site categorization tags: every
``__errors.push`` site already carries the kind string; tagging at
emission would change every call site. Central map keeps the contract
in one place and lets the convention test fail CI on missed kinds.

Sonnet sanity-check (2026-04-25) caught: 37 kinds total (not 31 as
Codex first counted — _guard_naked_prop_lines emits 2 more); rename
``tree_topology`` → ``child_attach_failed``; move
``phase1_mode*_prop_failed`` from generic ``property_write_failed``
into ``instance_materialization`` because they're INSTANCE-tree writes
specifically.

Convention: when a new ``__errors.push({kind: '...'})`` literal or
``_guarded_op(..., 'kind')`` argument is added in
``dd/render_figma_ast.py`` / ``dd/renderers/figma.py`` /
``render_test/walk_ref.js``, it MUST also be added to this map.
``tests/test_p4_runtime_error_categorization.py`` enforces the
mapping at CI time.
"""

from __future__ import annotations

# Single source of truth. Adding a new __errors.push kind without
# updating this map will fail the convention test.
RUNTIME_ERROR_KIND_TO_CATEGORY: dict[str, str] = {
    # font_health
    "font_load_failed": "font_health",

    # component_resolution
    "ckr_unbuilt": "component_resolution",
    "prefetch_failed": "component_resolution",
    "component_missing": "component_resolution",
    "missing_component_node": "component_resolution",
    "missing_instance_node": "component_resolution",
    "missing_component_key": "component_resolution",
    "no_main_component": "component_resolution",
    "import_component_failed": "component_resolution",

    # instance_materialization
    # Sonnet's correction: phase1_mode*_prop_failed are INSTANCE-tree
    # property writes (Mode-1 swap-with-existing, Mode-2
    # created-from-component), not arbitrary writes. Group them with
    # the instance class so the diagnostic points at the right code
    # path (dd/render_figma_ast.py mode-1/mode-2).
    "not_an_instance": "instance_materialization",
    "create_instance_failed": "instance_materialization",
    "phase1_mode1_prop_failed": "instance_materialization",
    "phase1_mode2_prop_failed": "instance_materialization",

    # mode_fallback (control-flow signal, not a failure per se)
    "degraded_to_mode2": "mode_fallback",

    # text_op_failed
    "text_set_failed": "text_op_failed",
    "text_auto_resize_failed": "text_op_failed",

    # layout_op_failed
    "layout_sizing_failed": "layout_op_failed",
    "layout_mode_failed": "layout_op_failed",
    "layout_wrap_failed": "layout_op_failed",
    "item_spacing_failed": "layout_op_failed",
    "counter_axis_spacing_failed": "layout_op_failed",
    "padding_failed": "layout_op_failed",
    "primary_axis_align_failed": "layout_op_failed",
    "counter_axis_align_failed": "layout_op_failed",

    # geometry_op_failed
    "resize_failed": "geometry_op_failed",
    "position_failed": "geometry_op_failed",
    "constraint_failed": "geometry_op_failed",
    "visibility_failed": "geometry_op_failed",

    # child_attach_failed
    # Sonnet's rename: "tree_topology" was structure-shaped, not
    # diagnostic-shaped. "child_attach_failed" tells you the verb.
    "append_child_failed": "child_attach_failed",
    "root_append_failed": "child_attach_failed",
    "leaf_type_append_skipped": "child_attach_failed",
    "group_empty_append_failed": "child_attach_failed",
    "group_create_failed": "child_attach_failed",
    "group_insert_failed": "child_attach_failed",

    # property_write_failed (after the instance-write kinds were
    # peeled off, this is just generic name-write failures today)
    "group_name_failed": "property_write_failed",

    # escaped_artifact (P3d walker addition)
    "phase2_orphan": "escaped_artifact",

    # render_thrown (script-level, severity-different from per-eid)
    "render_thrown": "render_thrown",
}


# The 11 categories. Listed here so order/membership is documented
# and the convention test can validate every value in the map appears
# in this set (catches typos like "instance_meterialization").
RUNTIME_ERROR_CATEGORIES: frozenset[str] = frozenset({
    "font_health",
    "component_resolution",
    "instance_materialization",
    "mode_fallback",
    "text_op_failed",
    "layout_op_failed",
    "geometry_op_failed",
    "child_attach_failed",
    "property_write_failed",
    "escaped_artifact",
    "render_thrown",
})


def categorize_runtime_error_kind(kind: str) -> str:
    """Map a raw __errors kind to its diagnostic category.

    Returns ``"uncategorized"`` for kinds not in the central map.
    Old reports, external walk payloads, and renderer guards added
    after this map was last updated will land in the uncategorized
    bucket — they're surfaced via the convention test (which fails CI
    when a repo-source literal is missing) but don't crash callers.

    Codex's review note: non-throwing at runtime, failing in tests.
    Defensive in production; loud in CI.
    """
    return RUNTIME_ERROR_KIND_TO_CATEGORY.get(kind, "uncategorized")
