"""SYSTEM_PROMPT injection for the archetype library.

Builds the few-shot fragment that prepends to the LLM's instructions
when the classifier matches a canonical archetype, and handles the
passthrough case when no match is found.
"""

from __future__ import annotations

import json

from dd.archetype_library import ARCHETYPE_NAMES, load_skeleton


_FRAMING_TEMPLATE = """

A canonical skeleton for the "{archetype}" archetype — use as inspiration, \
modify for the specific prompt. Do NOT copy verbatim; adapt the types, \
counts, and text to what the user actually asked for.

```json
{skeleton}
```

Remember: the skeleton shows structure (types + nesting). Fill in text, \
labels, icons, and variants from the prompt.""".lstrip("\n")


def build_archetype_injection(archetype: str) -> str:
    """Build the SYSTEM_PROMPT fragment for ``archetype``.

    Raises ``ValueError`` if the archetype isn't in the library.
    """
    if archetype not in ARCHETYPE_NAMES:
        raise ValueError(f"unknown archetype: {archetype!r}")
    skeleton = load_skeleton(archetype)
    return _FRAMING_TEMPLATE.format(
        archetype=archetype,
        skeleton=json.dumps(skeleton, indent=2),
    )


def inject_archetype(system_prompt: str, *, archetype: str | None) -> str:
    """Return ``system_prompt`` with the archetype fragment appended.

    If ``archetype`` is ``None`` or not in the library, returns
    ``system_prompt`` unchanged — degrades rather than crashes so the
    classifier can emit speculative matches without breaking the run.
    """
    if archetype is None:
        return system_prompt
    if archetype not in ARCHETYPE_NAMES:
        return system_prompt
    return system_prompt + "\n\n" + build_archetype_injection(archetype)
