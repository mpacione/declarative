"""Tests for per-op guard coverage in render_figma_ast Phase 1.

Twin of ``test_render_phase2_guards.py``. The Figma script wraps
Phases 1+2+3 in a single outer try/catch in
``_emit_end_wrapper`` — a throw inside Phase 1 lands in the
outer block as ``kind:"render_thrown"`` and, before this fix,
cascaded through the rest of the script including the final
``_page.appendChild(root_var)``. Nodes already created by Phase 1
stay orphaned on ``figma.currentPage`` and the CLI reports
success.

Demo-B postmortem (2026-04-24): 38 orphan nodes on page
``design session 01KQ12Z5 / 01KQ12ZEH5FP`` traced to this exact
failure mode. Fix: wrap every naked prop assignment in Phase 1
(name, fills, clipsContent, visible, layout, text, vector) in the
same per-op try/catch shape Phase 2 uses. Converts cascading
abort to per-op structured ``__errors`` entries; root attach
still happens.

The ``const var = createCall();`` line itself is NOT guarded —
that statement defines the var; if it throws there's no var to
assign to. The outer end-wrapper captures the throw as
``render_thrown`` and that's sufficient for that single rare
case.
"""

from __future__ import annotations

from dd.markup_l3 import parse_l3
from dd.render_figma_ast import render_figma


def _iter_nodes(nodes):
    for n in nodes:
        yield n
        if getattr(n, "block", None):
            yield from _iter_nodes(n.block.statements)


def _render(src: str) -> str:
    doc = parse_l3(src)
    spec_key_map = {
        id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
    }
    original_name_map = {
        id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
    }
    script, _refs = render_figma(
        doc, conn=None, nid_map={},
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
    )
    return script


_MINIMAL_DOC = """screen #screen-1 {
  frame #card-1 {
    text #title-1 "hello"
  }
}"""


def _phase1_body(script: str) -> str:
    """Slice the script to just the Phase 1 region so Phase 2/3 ops
    aren't inspected. Phase 1 is delimited by the ``// Phase 1:``
    comment and the ``// Phase 2:`` comment.
    """
    start_marker = "// Phase 1: Materialize"
    end_marker = "// Phase 2: Compose"
    start = script.find(start_marker)
    end = script.find(end_marker)
    assert start >= 0, "Phase 1 marker missing"
    assert end > start, "Phase 2 marker missing after Phase 1"
    return script[start:end]


class TestPhase1PropertyWriteGuards:
    """Every ``{var}.{prop} = ...`` assignment in Phase 1 must be
    wrapped in its own try/catch so a single throw doesn't cascade
    through the remaining Phase 1 ops AND the Phase 2 root-attach.
    """

    def test_name_assignment_is_guarded(self) -> None:
        script = _render(_MINIMAL_DOC)
        phase1 = _phase1_body(script)
        naked = [
            line for line in phase1.split("\n")
            if ".name = " in line
            and not line.lstrip().startswith("try")
            and not line.lstrip().startswith("//")
        ]
        assert not naked, (
            "Phase 1 has naked `.name =` assignments (render_thrown "
            "cascade risk):\n" + "\n".join(naked[:5])
        )

    def test_fills_clear_is_guarded(self) -> None:
        script = _render(_MINIMAL_DOC)
        phase1 = _phase1_body(script)
        naked = [
            line for line in phase1.split("\n")
            if ".fills = " in line
            and not line.lstrip().startswith("try")
            and not line.lstrip().startswith("//")
        ]
        assert not naked, (
            "Phase 1 has naked `.fills =` assignments "
            "(render_thrown cascade risk):\n"
            + "\n".join(naked[:5])
        )

    def test_clips_content_is_guarded(self) -> None:
        script = _render(_MINIMAL_DOC)
        phase1 = _phase1_body(script)
        naked = [
            line for line in phase1.split("\n")
            if ".clipsContent = " in line
            and not line.lstrip().startswith("try")
            and not line.lstrip().startswith("//")
        ]
        assert not naked, (
            "Phase 1 has naked `.clipsContent =` assignments "
            "(render_thrown cascade risk):\n"
            + "\n".join(naked[:5])
        )

    def test_phase1_property_writes_are_guarded(self) -> None:
        """Mirrors Phase 2's cumulative guard test. Any
        ``<var>.<something> = <value>;`` inside Phase 1 — EXCEPT
        the `const nN = figma.createX();` creation calls and the
        ``M["..."] = nN.id;`` bookkeeping writes — must be
        wrapped in ``try { ... } catch (__e) { __errors.push... }``.
        """
        script = _render(_MINIMAL_DOC)
        phase1 = _phase1_body(script)

        naked: list[str] = []
        for raw in phase1.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("//"):
                continue
            if line.startswith("try"):
                continue
            # `const nN = figma.createFrame();` — creation, load-bearing
            if line.startswith("const "):
                continue
            # Bookkeeping on the M dict, not a figma op.
            if line.startswith("M["):
                continue
            # __errors / __perf / __mark diagnostics — not a figma op.
            if line.startswith("__errors") or line.startswith("__perf") \
                    or line.startswith("__mark"):
                continue
            # Property-assignment shape: ``something.foo = ...;``.
            if "=" in line and "." in line.split("=", 1)[0]:
                naked.append(raw)

        assert not naked, (
            "Phase 1 has naked per-prop writes (render_thrown cascade "
            "risk when one throws — cascades through remaining Phase 1 "
            "ops and the final root appendChild, orphaning nodes on "
            "figma.currentPage). First offenders:\n"
            + "\n".join(naked[:10])
        )

    def test_guarded_ops_push_structured_errors_with_eid(self) -> None:
        """The guard catch block must push ``{eid, kind, error}`` into
        ``__errors``. Proposer agents and the CLI surface consume this.
        """
        script = _render(_MINIMAL_DOC)
        phase1 = _phase1_body(script)
        # At least one guarded prop-write with eid pattern.
        assert "__errors.push" in phase1, (
            "Phase 1 has no __errors.push — guards aren't emitting "
            "structured diagnostics"
        )
        # At least one per-op guard includes an eid field.
        assert 'eid:"' in phase1, (
            "Phase 1 guards are missing the eid field — proposer can't "
            "attribute the failure to the source node"
        )
