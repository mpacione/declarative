"""P2 (Phase E Pattern 1 fix) — test-only-import detector.

Finds public symbols in `dd/` that are imported BY tests but NEVER
imported by any production `dd/` module. These are the canonical
shape of the "canonical-path drift" pattern Sonnet + Codex flagged
in their Pattern 1 analysis: feature ships in code, ships its own
test, but never gets wired to the canonical caller.

The two known instances are:
  - N1: `mode1_eids` skip-set in dd/renderers/figma.py — never
    ported to the AST renderer (dd/render_figma_ast.py)
  - C2: `cluster_stroke_weight()` in dd/cluster_misc.py — never
    imported by dd/cluster.py (the orchestrator)

Sonnet's analysis of pattern1-canonical-path-drift surfaced a
much bigger one — the ADR-007 RenderProtocol+Repair stack
(FigmaRenderer, FigmaRepairVerifier, run_repair_loop, etc., ~526
LOC) is entirely test-only. This detector should catch that and
any future regression of the same shape.

## Usage

    python3 tools/orphan_detector.py
    python3 tools/orphan_detector.py --verbose   # list every test
    python3 tools/orphan_detector.py --json      # machine output

## How it works (and limits)

This is intentionally a SHALLOW, low-false-positive detector — NOT a
full dead-code analyzer:

1. Walks `tests/**/*.py` AST; collects every `from dd.X import Y` and
   `import dd.X` and `dd.X.Y` reference.
2. Walks `dd/**/*.py` AST; collects same.
3. Reports `dd.X.Y` symbols that appear in (1) but NOT in (2).

What it CATCHES:
- N1-class drift (renderer feature in old path, missing in canonical)
- C2-class drift (cluster module written but not wired to orchestrator)
- ADR-007-class drift (stack of files only used by tests + scripts)

What it MISSES (intentionally — keep false-positive rate low):
- Symbols only used WITHIN their own `dd/` file (not orphans by this
  rule — they're internal helpers)
- Dynamically-imported symbols (`importlib`, `getattr(module, name)`)
- Symbols imported by `scripts/` (treated as test-equivalent)
- Symbols whose ONLY non-test caller is themselves (transitive
  orphans — rare)

If something is flagged here it's almost certainly real drift. If the
detector misses something, it'll get caught by the next manual review
or by `code-graph-mcp dead-code` (which is more aggressive but has
higher false-positive rate per Sonnet's experiment with intra-file
indexing gaps).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DD_DIR = REPO / "dd"
TESTS_DIR = REPO / "tests"
SCRIPTS_DIR = REPO / "scripts"

# Allowlist: symbols intentionally test-only. Each entry is a
# `dd.module.symbol` qualified name. Keep this list short and
# DOCUMENTED — every entry is a code-smell that explains itself.
#
# The ADR-007 RenderProtocol+Repair stack (FigmaRenderer, Renderer,
# WalkResult, FigmaRepairVerifier, run_repair_loop, etc.) used to
# live here as 13 P7-pending entries. The stack was retired in P7
# (Phase E Pattern 1 fix); the unified verification channel that
# ADR-007 introduced is still live in dd/boundary.py + dd/verify_figma.py
# + the renderer guards — only the unused multi-backend wrapper +
# the test-only repair loop were removed.
ALLOWLIST: dict[str, str] = {
}


def _collect_imports_from_file(path: Path) -> set[str]:
    """Parse a Python file; return every `dd.X.Y` qualified name
    referenced via import or attribute access. Conservative — when
    in doubt, include it as referenced (false negatives = orphans
    that look like they're used; false positives = orphans we
    correctly flag).
    """
    refs: set[str] = set()
    try:
        src = path.read_text()
        tree = ast.parse(src, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return refs

    for node in ast.walk(tree):
        # `from dd.X import Y, Z` → refs add dd.X.Y, dd.X.Z
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not mod.startswith("dd"):
                continue
            for alias in node.names:
                if alias.name == "*":
                    refs.add(f"{mod}.*")
                else:
                    refs.add(f"{mod}.{alias.name}")
        # `import dd.X` → refs add dd.X (any symbol could be accessed)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("dd"):
                    refs.add(f"{alias.name}.*")
        # `dd.X.Y` attribute access → conservative addition
        elif isinstance(node, ast.Attribute):
            # Only catch `dd.<module>.<symbol>` form
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "dd"
            ):
                refs.add(f"dd.{node.value.attr}.{node.attr}")

    return refs


def _collect_definitions_from_file(path: Path) -> set[str]:
    """Parse a `dd/` Python file; return every public symbol it
    DEFINES (top-level `def`, `class`, `name = ...`). Symbols
    starting with `_` are skipped — module-private, not subject
    to the canonical-wiring contract.
    """
    defs: set[str] = set()
    try:
        src = path.read_text()
        tree = ast.parse(src, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return defs

    # The module's qualified name: dd.module_name (no .py)
    rel = path.relative_to(REPO)
    parts = list(rel.with_suffix("").parts)  # ('dd', 'cluster_misc')
    mod_name = ".".join(parts)

    for node in ast.iter_child_nodes(tree):
        name: str | None = None
        if isinstance(node, ast.FunctionDef):
            name = node.name
        elif isinstance(node, ast.AsyncFunctionDef):
            name = node.name
        elif isinstance(node, ast.ClassDef):
            name = node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    defs.add(f"{mod_name}.{target.id}")
        if name and not name.startswith("_"):
            defs.add(f"{mod_name}.{name}")

    return defs


def _walk_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find dd/ symbols imported by tests but NOT by any other dd/ module."
    )
    ap.add_argument(
        "--verbose", action="store_true",
        help="List every test file that references each orphan.",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON instead of human text.",
    )
    ap.add_argument(
        "--include-allowlisted", action="store_true",
        help="Include allowlisted entries in output (default: hidden).",
    )
    args = ap.parse_args()

    # Collect all definitions in dd/
    dd_files = _walk_python_files(DD_DIR)
    all_definitions: set[str] = set()
    for f in dd_files:
        all_definitions |= _collect_definitions_from_file(f)

    # Collect all dd.* refs from dd/ itself (production-side imports)
    dd_refs: set[str] = set()
    for f in dd_files:
        dd_refs |= _collect_imports_from_file(f)

    # Wildcard expansion: `from dd.X import *` and `import dd.X` mark
    # the whole module as referenced (we can't tell which symbol was
    # used without semantic analysis).
    wild_modules: set[str] = {
        ref.rsplit(".*", 1)[0] for ref in dd_refs if ref.endswith(".*")
    }

    # Collect all dd.* refs from tests/ AND scripts/
    test_files = _walk_python_files(TESTS_DIR)
    if SCRIPTS_DIR.exists():
        test_files += _walk_python_files(SCRIPTS_DIR)
    test_refs_with_source: dict[str, list[str]] = {}
    for f in test_files:
        for ref in _collect_imports_from_file(f):
            test_refs_with_source.setdefault(ref, []).append(
                str(f.relative_to(REPO))
            )

    # An orphan is a symbol that:
    # (a) is defined in dd/
    # (b) is referenced by tests/scripts
    # (c) is NOT referenced by any other dd/ module
    # (d) its module is not wildcard-imported by dd/
    orphans: dict[str, list[str]] = {}
    for sym in all_definitions:
        if sym not in test_refs_with_source:
            continue  # not used by tests; not an orphan by this rule
        if sym in dd_refs:
            continue  # used by another dd/ module; not an orphan
        # Check if the module is wildcard-imported anywhere in dd/
        sym_module = sym.rsplit(".", 1)[0]
        if sym_module in wild_modules:
            continue  # module wildcard-imported; can't tell
        orphans[sym] = test_refs_with_source[sym]

    # Apply allowlist
    flagged = {
        sym: srcs for sym, srcs in orphans.items()
        if sym not in ALLOWLIST or args.include_allowlisted
    }
    allowlisted = {
        sym: ALLOWLIST[sym] for sym in orphans if sym in ALLOWLIST
    }

    if args.json:
        payload = {
            "orphans": {sym: sorted(srcs) for sym, srcs in flagged.items()},
            "allowlisted": allowlisted,
            "summary": {
                "total_orphans": len(flagged),
                "allowlisted_count": len(allowlisted),
                "dd_files_scanned": len(dd_files),
                "test_files_scanned": len(test_files),
                "definitions_in_dd": len(all_definitions),
            },
        }
        print(json.dumps(payload, indent=2))
        return 0 if not flagged else 1

    # Human output
    print(f"\nOrphan detector — Phase E P2")
    print(f"  Scanned: {len(dd_files)} dd/ files, {len(test_files)} test/script files")
    print(f"  dd/ definitions: {len(all_definitions)} public symbols")
    print(f"  Allowlisted (known OK): {len(allowlisted)}")
    print(f"  Flagged orphans: {len(flagged)}")
    print()

    if not flagged:
        print("✓ No new orphans detected.")
        return 0

    print("Flagged (test-only or script-only references; no dd/ caller):")
    print()
    for sym in sorted(flagged):
        srcs = flagged[sym]
        marker = " (ALLOWLISTED)" if sym in ALLOWLIST else ""
        print(f"  • {sym}{marker}")
        if args.verbose:
            for src in sorted(srcs):
                print(f"      ← {src}")
    print()
    print(
        f"To allowlist a symbol, add to ALLOWLIST in "
        f"{Path(__file__).relative_to(REPO)} with a one-line justification."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
