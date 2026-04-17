"""Dual fidelity scorer — prompt fidelity + render fidelity.

Separates two orthogonal signals that VLM scoring conflates:

- **prompt fidelity**: did the LLM output include the archetype's
  expected node-type bag? Jaccard-style coverage on the classified
  archetype skeleton. Range 0.0-1.0.

- **render fidelity**: did the generated Figma script emit the visual
  properties the PresentationTemplate promised for each IR element?
  Per-type coverage aggregated across the IR. Range 0.0-1.0.

A broken output with prompt=0.9 / render=0.3 is a renderer bug.
One with prompt=0.5 / render=1.0 is a prompt bug. Mode 3 at the
v0.1.5 Week 1 ship point sits around prompt≈0.9 / render≈0.3 — see
`docs/research/mode3-forensic-analysis.md` for the diagnosis.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from dd.composition.registry import ProviderRegistry
from dd.composition.providers.universal import UniversalCatalogProvider


# --------------------------------------------------------------------------- #
# Expected visual properties per catalog type                                 #
# --------------------------------------------------------------------------- #

# Renderer-relevant property keys the fidelity scorer checks against the
# generated script. Derived from PresentationTemplate.style and .layout.
_TEMPLATE_STYLE_KEYS = ("fill", "stroke", "radius", "shadow")


_REGISTRY: ProviderRegistry | None = None


def _registry() -> ProviderRegistry:
    """Universal-only registry, built once. Provenance-free — the
    fidelity scorer only needs catalog-level visual defaults."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry(providers=[UniversalCatalogProvider()])
    return _REGISTRY


def expected_visual_props_for_type(catalog_type: str) -> set[str]:
    """What visual properties should a node of ``catalog_type`` have?

    Derived from the ``UniversalCatalogProvider``'s PresentationTemplate
    for that type. Returns the subset of {fill, stroke, radius, shadow,
    padding} the template declares.
    """
    template, _errors = _registry().resolve(catalog_type, variant=None, context={})
    if template is None:
        return set()
    out: set[str] = set()
    style = template.style or {}
    for key in _TEMPLATE_STYLE_KEYS:
        if key in style:
            out.add(key)
    layout = template.layout or {}
    if "padding" in layout:
        out.add("padding")
    return out


# --------------------------------------------------------------------------- #
# Render fidelity (IR + generated script)                                     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RenderFidelityScore:
    """Aggregate render-fidelity result."""

    overall: float
    by_type: dict[str, dict[str, float]] = field(default_factory=dict)
    by_element: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "by_type": {
                t: {
                    "coverage": round(v["coverage"], 4),
                    "n_elements": v["n_elements"],
                }
                for t, v in self.by_type.items()
            },
            "by_element": self.by_element,
        }


def _find_frame_block(script: str, eid: str) -> str | None:
    """Return the block of property assignments for an eid's frame.

    Frames in generated scripts land as:
        const nN = figma.createFrame();   // or createText / createInstance
        nN.name = "<eid>";
        ...property assignments...
        M["<eid>"] = nN.id;

    We slice from the `createFrame()`/`createText()`/etc. that produces
    nN up through the `M["<eid>"] = nN.id;` tag.
    """
    # Find the M["<eid>"] = nN.id line
    m_tag = re.search(rf'M\["{re.escape(eid)}"\] = (n\d+)\.id;', script)
    if m_tag is None:
        return None
    var = m_tag.group(1)
    # Find the most recent creation line for var before the M tag
    # Match `const var = figma.createFrame();` OR createText / createInstance /
    # and the whole await-IIFE for missing-component placeholders.
    creation_re = re.compile(
        rf'^const {re.escape(var)} = (figma\.createFrame\(\)|figma\.createText\(\)|'
        rf'figma\.createRectangle\(\)|figma\.createVector\(\)|figma\.createEllipse\(\)|'
        rf'figma\.createLine\(\)|await \(async.*?\);)',
        re.MULTILINE,
    )
    # Find all occurrences of creation_re for var, pick the last one
    # before m_tag.start()
    last_start = None
    for match in creation_re.finditer(script):
        if match.start() < m_tag.start():
            last_start = match.start()
    if last_start is None:
        return None
    return script[last_start:m_tag.end()]


_PROP_DETECTORS = {
    # ``fills = [];`` is explicitly empty → NOT a fill emission.
    "fill": lambda block: bool(
        re.search(r"\.fills\s*=\s*\[[^\]]+\]", block)
        and not re.search(r"\.fills\s*=\s*\[\s*\]\s*;", block)
    ),
    "stroke": lambda block: bool(
        re.search(r"\.strokes\s*=\s*\[[^\]]+\]", block)
        and not re.search(r"\.strokes\s*=\s*\[\s*\]\s*;", block)
    ),
    "radius": lambda block: bool(re.search(r"\.cornerRadius\s*=", block)),
    "shadow": lambda block: bool(re.search(r"\.effects\s*=\s*\[[^\]]+\]", block)),
    "padding": lambda block: bool(re.search(r"\.paddingTop\s*=", block)),
}


def render_fidelity_from_script(ir: dict[str, Any], script: str) -> RenderFidelityScore:
    """Compute per-type + overall render fidelity.

    For each IR element with a known-template type, enumerate the
    template-declared visual properties; for each, check whether the
    corresponding property assignment is present in the script block
    for that element. Aggregate per-type and overall.
    """
    elements = ir.get("elements", {}) or {}
    by_type_totals: dict[str, list[float]] = {}
    by_element: dict[str, dict[str, Any]] = {}

    for eid, el in elements.items():
        comp_type = el.get("type")
        if not isinstance(comp_type, str):
            continue
        expected = expected_visual_props_for_type(comp_type)
        if not expected:
            continue
        block = _find_frame_block(script, eid)
        if block is None:
            coverage = 0.0
            present: set[str] = set()
        else:
            present = {p for p in expected if _PROP_DETECTORS[p](block)}
            coverage = len(present) / len(expected)
        by_type_totals.setdefault(comp_type, []).append(coverage)
        by_element[eid] = {
            "type": comp_type,
            "expected": sorted(expected),
            "present": sorted(present),
            "coverage": round(coverage, 4),
        }

    by_type: dict[str, dict[str, float]] = {}
    all_coverages: list[float] = []
    for t, covs in by_type_totals.items():
        by_type[t] = {
            "coverage": sum(covs) / len(covs),
            "n_elements": len(covs),
        }
        all_coverages.extend(covs)
    overall = sum(all_coverages) / len(all_coverages) if all_coverages else 0.0

    return RenderFidelityScore(overall=overall, by_type=by_type, by_element=by_element)


# --------------------------------------------------------------------------- #
# Prompt fidelity (skeleton vs LLM output)                                    #
# --------------------------------------------------------------------------- #

def type_bag(nodes: list[dict]) -> dict[str, int]:
    """Flatten a tree of component dicts into a Counter of types."""
    counter: Counter[str] = Counter()
    stack: list[dict] = list(nodes or [])
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        t = node.get("type")
        if isinstance(t, str):
            counter[t] += 1
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(children)
    return dict(counter)


def prompt_fidelity(
    archetype_skeleton: list[dict] | None,
    llm_output: list[dict],
) -> float:
    """Jaccard-style coverage of the skeleton's type bag.

    Returns 1.0 when ``archetype_skeleton`` is None (no expectation)
    or when the llm output covers the skeleton's bag fully. Extra
    types in llm_output don't penalise.
    """
    if not archetype_skeleton:
        return 1.0
    expected = type_bag(archetype_skeleton)
    actual = type_bag(llm_output)
    covered = 0
    total = 0
    for t, want in expected.items():
        total += want
        covered += min(want, actual.get(t, 0))
    return covered / total if total else 1.0
