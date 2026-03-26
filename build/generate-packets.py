#!/usr/bin/env python3
"""
Declarative Design Task Packet Generator

Reads the spec suite and task decomposition guide, then calls Claude Opus 4.6
wave-by-wave to generate self-contained task packet markdown files.

Forked from ARIA/build/generate-packets.py, adapted for Declarative Design.

Usage:
  python3 generate-packets.py                  # Interactive: prompts for API key
  ANTHROPIC_API_KEY=sk-... python3 generate-packets.py  # From env
  python3 generate-packets.py --wave 0         # Generate only Wave 0
  python3 generate-packets.py --dry-run        # Print the prompt, don't call API
"""

import os
import sys
import re
import argparse
from pathlib import Path

# Defer anthropic import -- not needed for --list-waves or --dry-run
anthropic = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
# Specs live in the project root (one level up from build/)
SPECS_DIR = SCRIPT_DIR.parent
BUILD_DIR = SCRIPT_DIR
PACKETS_DIR = BUILD_DIR / "packets"

# Spec files to load (in order)
SPEC_FILES = [
    "Architecture.md",
    "User Requirements Spec.md",
    "Technical Design Spec.md",
    "Probe Results.md",
    "Tooling Comparison.md",
    "schema.sql",
]

MODEL = "claude-opus-4-6"  # Opus 4.6 -- 200K context (1M beta), $5/$25 per MTok
MAX_TOKENS = 32768  # Per wave output

# Wave definitions
WAVES = {
    "wave-0": {
        "name": "Wave 0: Project Scaffold + DB Initialization + Test Infrastructure",
        "tasks": ["TASK-001", "TASK-002", "TASK-003", "TASK-004", "TASK-005", "TASK-006", "TASK-007"],
        "testFirst": False,
        "testLevel": "unit",
    },
    "wave-1": {
        "name": "Wave 1: Extraction Pipeline -- Inventory + Screen Extraction",
        "tasks": ["TASK-010", "TASK-011", "TASK-012", "TASK-013", "TASK-014", "TASK-015", "TASK-016"],
        "testFirst": False,
        "testLevel": "unit+integration",
    },
    "wave-2": {
        "name": "Wave 2: Component Extraction + Advanced Normalization",
        "tasks": ["TASK-020", "TASK-021", "TASK-022", "TASK-023", "TASK-024", "TASK-025", "TASK-026"],
        "testFirst": False,
        "testLevel": "unit+integration",
    },
    "wave-3": {
        "name": "Wave 3: Census + Clustering",
        "tasks": ["TASK-030", "TASK-031", "TASK-032", "TASK-033", "TASK-034", "TASK-035", "TASK-036", "TASK-037"],
        "testFirst": True,
        "testLevel": "unit+integration+e2e",
    },
    "wave-4": {
        "name": "Wave 4: Curation Workflow + Pre-Export Validation",
        "tasks": ["TASK-040", "TASK-041", "TASK-042", "TASK-043", "TASK-044", "TASK-045"],
        "testFirst": True,
        "testLevel": "unit+integration+e2e",
    },
    "wave-5": {
        "name": "Wave 5: Figma Export (Variables + Rebinding)",
        "tasks": ["TASK-050", "TASK-051", "TASK-052", "TASK-053", "TASK-054", "TASK-055"],
        "testFirst": True,
        "testLevel": "unit+integration+e2e",
    },
    "wave-6": {
        "name": "Wave 6: Code Export (CSS, Tailwind, DTCG)",
        "tasks": ["TASK-060", "TASK-061", "TASK-062", "TASK-063", "TASK-064", "TASK-065"],
        "testFirst": True,
        "testLevel": "unit+integration+e2e",
    },
    "wave-7": {
        "name": "Wave 7: Companion Skill + Drift Detection",
        "tasks": ["TASK-070", "TASK-071", "TASK-072", "TASK-073", "TASK-074"],
        "testFirst": False,
        "testLevel": "unit+e2e",
    },
}

WAVE_ORDER = ["wave-0", "wave-1", "wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7"]


# ---------------------------------------------------------------------------
# Packet template
# ---------------------------------------------------------------------------

PACKET_TEMPLATE_EXAMPLE = """
Each task packet MUST follow this exact markdown format:

```markdown
---
taskId: TASK-NNN
title: "Short title"
wave: wave-N
testFirst: true|false
testLevel: unit|integration|e2e
dependencies: [TASK-XXX, TASK-YYY]
produces:
  - path/to/file.py
  - path/to/other.py
verify:
  - type: typecheck
    command: 'python -c "import dd"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_foo.py -v'
    passWhen: 'all tests pass'
contextProfile: standard|full|minimal
---

# TASK-NNN: Short title

## Spec Context

> Inlined spec content the agent needs. Extract the relevant sections from
> the referenced specs and paste them here verbatim. Use blockquotes to
> distinguish spec content from instructions. Include ONLY what this
> specific task needs -- not the entire spec document.
>
> If multiple spec sections are needed, use separate blockquote blocks
> with headers identifying the source:

### From Technical Design Spec -- Phase 2: Screen Extraction

> [relevant content from that section]

### From schema.sql -- nodes table

> [relevant CREATE TABLE statement]

## Task

[The implementation prompt. 15-40 lines of specific, step-by-step guidance.
Tell the agent exactly what to build, what patterns to follow, what to
name things, and what edge cases to handle. Reference the spec context
above rather than saying "read the spec."]

## Acceptance Criteria

- [ ] First machine-checkable criterion
- [ ] Second criterion
- [ ] python -c "import dd" exits 0
- [ ] [test-specific criteria if testFirst is true]

## Notes

[Optional. Gotchas, warnings, or context that doesn't fit above.
For example: "This file will be extended by TASK-023" or
"The coloraide library may not be available -- include fallback formulas."]
```
""".strip()


# ---------------------------------------------------------------------------
# System prompt for Opus
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are generating self-contained task packet files for building Declarative Design, a local extraction-and-structuring pipeline that converts hardcoded Figma files into a queryable SQLite database of tokens, components, compositions, and cross-tool mappings.

The tech stack is Python 3.11+ with SQLite. No web server, no CLI framework -- just Python modules that an agent calls.

Each task packet is a standalone markdown file that gives a build agent (Claude Code) everything it needs to execute one task without reading any other files. The agent receives ONLY this file -- no spec documents, no other task files, no conversation history.

CRITICAL RULES:

1. INLINE ALL SPEC CONTENT. Do not write "see Technical Design Spec Phase 2" -- instead, extract the relevant content from that section and paste it into the packet's Spec Context section. The agent cannot read spec files.

2. INLINE RELEVANT SCHEMA. If the task touches database tables, paste the CREATE TABLE statements from schema.sql into the Spec Context. The agent cannot read schema.sql.

3. THE PROMPT MUST BE SPECIFIC. Not "create the color normalization module" but "create dd/color.py with functions: rgba_to_hex(r, g, b, a) that converts Figma RGBA 0-1 floats to 6- or 8-digit hex strings using round(component * 255). If alpha == 1.0, return 6-digit (#RRGGBB). If alpha < 1.0, return 8-digit (#RRGGBBAA)."

4. ACCEPTANCE CRITERIA MUST BE MACHINE-CHECKABLE. Exit codes, file existence, specific function signatures, import checks, pytest pass. Never "works correctly" or "handles edge cases."

5. EACH PACKET IS INDEPENDENT. A fresh agent with zero context should be able to execute from this file alone. If the task depends on files from prior tasks, describe what those files export (functions, types) in the Spec Context section.

6. YAML SAFETY. Any frontmatter value containing a colon followed by a space (`: `) MUST be wrapped in single quotes. This applies to all `command` and `passWhen` values.

7. MCP-DEPENDENT CODE. Tasks that produce code which will be called by an agent with MCP access (extraction, Figma export, drift detection) should make this clear. The builder agent writes Python functions; a separate agent session with MCP tools invokes them. The functions should accept MCP responses as input parameters, not call MCP directly.

8. COLORAIDE FALLBACK. If a task uses OKLCH color math, include manual conversion formulas (sRGB -> linear RGB -> XYZ D65 -> OKLAB -> OKLCH) as a fallback in case coloraide is not installed. The agent should try `import coloraide` first, fall back to manual math.

9. TESTING LEVELS. Every test task must set the `testLevel` frontmatter key to one of: unit, integration, e2e. The test level determines what the test covers:
   - `unit`: isolated module tests with mocked dependencies. Use @pytest.mark.unit decorator.
   - `integration`: cross-module tests using fixture DBs with real pipeline output at the seam being tested. Only mock external dependencies (Figma MCP). Use @pytest.mark.integration decorator.
   - `e2e`: full pipeline tests from extraction through the current wave. Use @pytest.mark.e2e and @pytest.mark.slow decorators.

10. INTEGRATION TEST REQUIREMENTS. Integration test tasks (wave 1+) MUST:
   - Import and use fixture factory functions from `tests/fixtures.py` (created by TASK-007)
   - Test the actual boundary between current wave modules and prior wave outputs -- NOT re-mock what the prior wave produces
   - Verify FK integrity, data shape correctness, and state transitions across module boundaries
   - Use real DB connections (in-memory SQLite), not mock DB objects

11. E2E TEST REQUIREMENTS. E2E test tasks (wave 3+) MUST:
   - Run the real pipeline functions in sequence, not just assert on pre-seeded state
   - Start from `seed_post_extraction()` fixture at minimum, execute forward through current wave
   - Assert on final observable state (DB contents, export file contents) not intermediate calls
   - Be marked with both @pytest.mark.e2e and @pytest.mark.slow

12. PYTEST PLUGINS. All test tasks should assume these pytest plugins are available: pytest-xdist (parallel execution), pytest-timeout (30s default), pytest-cov (coverage reporting). Include appropriate markers and timeout decorations in test code.

13. TEST INFRASTRUCTURE DEPENDENCY. All integration and e2e test tasks MUST list TASK-007 (test infrastructure) in their dependencies. TASK-007 creates `tests/conftest.py` and `tests/fixtures.py` which provide shared fixtures and DB seeding factories.

""" + PACKET_TEMPLATE_EXAMPLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_file(path: Path) -> str:
    """Load a file and return its contents."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"  WARNING: File not found: {path}", file=sys.stderr)
        return ""


def load_specs(specs_dir: Path, spec_files: list[str]) -> str:
    """Load specific spec files into a single string with clear file headers."""
    specs = []
    for fname in spec_files:
        path = specs_dir / fname
        content = load_file(path)
        if content:
            specs.append(f"{'='*60}\nFILE: {fname}\n{'='*60}\n\n{content}")
    return "\n\n".join(specs)


def load_prior_packets(packets_dir: Path, prior_waves: list[str]) -> str:
    """Load packets from prior waves so Opus can reference them."""
    if not packets_dir.exists():
        return ""
    packets = []
    for wave_id in prior_waves:
        wave_dir = packets_dir / wave_id
        if not wave_dir.exists():
            continue
        for f in sorted(wave_dir.glob("*.md")):
            content = load_file(f)
            packets.append(f"--- Prior packet: {f.name} ---\n{content}")
    if not packets:
        return ""
    return (
        "\n\n" + "="*60 +
        "\nPRIOR WAVE PACKETS (for dependency context)\n" +
        "="*60 + "\n\n" +
        "\n\n".join(packets)
    )


def build_wave_prompt(wave_id: str, wave_info: dict, task_decomp: str, all_specs: str, prior_packets: str) -> str:
    """Build the user prompt for generating one wave's packets."""
    return f"""Generate self-contained task packet markdown files for {wave_info['name']}.

The tasks in this wave are: {', '.join(wave_info['tasks'])}
Default testFirst for this wave: {wave_info['testFirst']}
Required test levels for this wave: {wave_info.get('testLevel', 'unit')}

Below are the FULL SPEC DOCUMENTS (source of truth) and the TASK DECOMPOSITION GUIDE (which lists each task's description, produces, and dependencies).

Read the task table for this wave carefully. For each task:
1. Find the task row in the Task Decomposition Guide
2. Identify which spec sections it references
3. Extract those spec sections verbatim into the packet's Spec Context
4. For any task that touches the DB: extract the relevant CREATE TABLE / CREATE VIEW statements from schema.sql
5. Write a detailed implementation prompt (15-40 lines)
6. Write machine-checkable acceptance criteria
7. Set the correct frontmatter (verify chain, contextProfile, etc.)

Output each packet separated by a line containing only: ===PACKET_BOUNDARY===

Do NOT output anything except the packet contents and boundaries. No commentary, no explanations.

{'='*60}
TASK DECOMPOSITION GUIDE
{'='*60}

{task_decomp}

{'='*60}
FULL SPEC DOCUMENTS
{'='*60}

{all_specs}
{prior_packets}"""


def parse_packets(raw_output: str, wave_id: str, expected_tasks: list[str]) -> dict[str, str]:
    """Split Opus output into individual packet files."""
    chunks = re.split(r'===PACKET_BOUNDARY===', raw_output)
    packets = {}

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # Try to extract taskId from frontmatter
        match = re.search(r'taskId:\s*(TASK-\w+)', chunk)
        if match:
            task_id = match.group(1)
            packets[task_id] = chunk
        else:
            # Try to find it in heading
            match = re.search(r'#\s*(TASK-\w+)', chunk)
            if match:
                task_id = match.group(1)
                packets[task_id] = chunk

    # Warn about missing tasks
    for task_id in expected_tasks:
        if task_id not in packets:
            print(f"  WARNING: Expected {task_id} but not found in output", file=sys.stderr)

    return packets


def save_packets(packets: dict[str, str], wave_id: str, packets_dir: Path):
    """Save parsed packets to individual files."""
    wave_dir = packets_dir / wave_id
    wave_dir.mkdir(parents=True, exist_ok=True)

    for task_id, content in packets.items():
        filename = f"{task_id}.md"
        filepath = wave_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"  Saved: {filepath.relative_to(packets_dir.parent)}")


# ---------------------------------------------------------------------------
# Packet validation
# ---------------------------------------------------------------------------

REQUIRED_FRONTMATTER_KEYS = {"taskId", "title", "wave", "testFirst", "testLevel", "dependencies", "produces", "verify", "contextProfile"}
REQUIRED_BODY_SECTIONS = {"Spec Context", "Task", "Acceptance Criteria"}
VALID_CONTEXT_PROFILES = {"minimal", "standard", "full"}
VALID_TEST_LEVELS = {"unit", "integration", "e2e"}
MAX_FRONTMATTER_LINE = 22  # closing --- must appear by this line (allows up to ~6 produces + 2 verify)


def validate_packet(filepath: Path, wave_id: str, expected_task_id: str) -> list[str]:
    """Validate a single packet file. Returns list of issues (empty = pass)."""
    issues = []
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")

    # --- Frontmatter structure ---
    if not lines or lines[0].strip() != "---":
        issues.append("MISSING opening --- delimiter on line 1")
        return issues  # can't validate further

    # Find closing ---
    closing_line = None
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            closing_line = i
            break

    if closing_line is None:
        issues.append("MISSING closing --- delimiter (no frontmatter end found)")
        return issues

    if closing_line > MAX_FRONTMATTER_LINE:
        issues.append(f"FRONTMATTER TOO LONG: closing --- at line {closing_line} (max {MAX_FRONTMATTER_LINE}). "
                       "Multi-line commands in verify block?")

    # --- Parse frontmatter keys (lightweight, not full YAML) ---
    frontmatter_text = "\n".join(lines[1:closing_line - 1])
    found_keys = set()
    for line in lines[1:closing_line - 1]:
        key_match = re.match(r'^(\w+):', line)
        if key_match:
            found_keys.add(key_match.group(1))

    missing_keys = REQUIRED_FRONTMATTER_KEYS - found_keys
    if missing_keys:
        issues.append(f"MISSING frontmatter keys: {', '.join(sorted(missing_keys))}")

    # taskId match
    task_id_match = re.search(r'taskId:\s*(TASK-\d{3})', frontmatter_text)
    if task_id_match:
        actual_id = task_id_match.group(1)
        if actual_id != expected_task_id:
            issues.append(f"TASK ID MISMATCH: frontmatter says {actual_id}, expected {expected_task_id}")
    else:
        issues.append(f"TASK ID FORMAT: could not parse taskId (expected TASK-NNN)")

    # wave match
    wave_match = re.search(r'wave:\s*(wave-\d+)', frontmatter_text)
    if wave_match:
        actual_wave = wave_match.group(1)
        if actual_wave != wave_id:
            issues.append(f"WAVE MISMATCH: frontmatter says {actual_wave}, expected {wave_id}")

    # contextProfile
    cp_match = re.search(r'contextProfile:\s*(\w+)', frontmatter_text)
    if cp_match:
        cp = cp_match.group(1)
        if cp not in VALID_CONTEXT_PROFILES:
            issues.append(f"INVALID contextProfile: '{cp}' (expected one of {VALID_CONTEXT_PROFILES})")

    # testLevel
    tl_match = re.search(r'testLevel:\s*(\w+)', frontmatter_text)
    if tl_match:
        tl = tl_match.group(1)
        if tl not in VALID_TEST_LEVELS:
            issues.append(f"INVALID testLevel: '{tl}' (expected one of {VALID_TEST_LEVELS})")

    # --- Multi-line command detection in frontmatter ---
    in_command = False
    for line in lines[1:closing_line - 1]:
        stripped = line.strip()
        if re.match(r"command:\s*'", stripped) or re.match(r'command:\s*"', stripped):
            # Check if it opens and closes on the same line
            single_q = stripped.count("'")
            double_q = stripped.count('"')
            # A properly closed single-line command has balanced quotes
            if stripped.startswith("command: '") and single_q >= 2 and stripped.endswith("'"):
                continue  # single-line, fine
            if stripped.startswith('command: "') and double_q >= 2 and stripped.endswith('"'):
                continue  # single-line, fine
            in_command = True
        elif in_command:
            # Still inside a multi-line command
            if stripped.endswith("'") or stripped.endswith('"'):
                in_command = False
    if in_command:
        issues.append("UNCLOSED multi-line command string in frontmatter (unterminated quote)")

    # --- Body structure ---
    body = "\n".join(lines[closing_line:])

    # Check for heading with task ID
    heading_match = re.search(r'^#\s+TASK-\d{3}:', body, re.MULTILINE)
    if not heading_match:
        issues.append("MISSING # TASK-NNN: heading after frontmatter")

    # Required sections
    for section in REQUIRED_BODY_SECTIONS:
        if not re.search(r'^##\s+' + re.escape(section), body, re.MULTILINE):
            issues.append(f"MISSING required section: ## {section}")

    # Acceptance criteria should have checklist items
    ac_match = re.search(r'## Acceptance Criteria\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if ac_match:
        ac_content = ac_match.group(1)
        checkbox_count = len(re.findall(r'- \[ \]', ac_content))
        if checkbox_count == 0:
            issues.append("ACCEPTANCE CRITERIA has no checklist items (expected - [ ] items)")
        elif checkbox_count < 2:
            issues.append(f"ACCEPTANCE CRITERIA has only {checkbox_count} checklist item (expected >= 2)")

    # Spec Context should have blockquoted content or ### subsections
    sc_match = re.search(r'## Spec Context\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if sc_match:
        sc_content = sc_match.group(1)
        has_quotes = '> ' in sc_content
        has_subsections = '### ' in sc_content
        has_code = '```' in sc_content
        if not (has_quotes or has_subsections or has_code):
            issues.append("SPEC CONTEXT appears empty (no blockquotes, subsections, or code blocks)")

    # Task section should have meaningful content (> 5 lines)
    task_match = re.search(r'## Task\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if task_match:
        task_lines = [l for l in task_match.group(1).strip().split("\n") if l.strip()]
        if len(task_lines) < 5:
            issues.append(f"TASK section too short: {len(task_lines)} lines (expected >= 5)")

    # --- Content quality checks ---
    # Check for "see spec" or "refer to" anti-patterns (should be inlined)
    see_spec_patterns = [
        r'see\s+(the\s+)?specs?/',
        r'refer\s+to\s+.*\.md',
        r'see\s+schema\.sql',
        r'consult\s+.*\.md',
        r'check\s+.*\.md\s+for',
    ]
    for pattern in see_spec_patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            issues.append(f"EXTERNAL REFERENCE found: '{match.group(0)}' (spec content should be inlined)")

    # Check for unicode characters in frontmatter (ASCII-only rule)
    for i, line in enumerate(lines[:closing_line], start=1):
        if any(ord(c) > 127 for c in line):
            non_ascii = [c for c in line if ord(c) > 127]
            issues.append(f"NON-ASCII in frontmatter line {i}: {''.join(non_ascii[:5])}")

    # Overall length sanity
    if len(content) < 500:
        issues.append(f"SUSPICIOUSLY SHORT: {len(content)} chars (expected >= 500 for a complete packet)")
    if len(content) > 50000:
        issues.append(f"SUSPICIOUSLY LONG: {len(content)} chars (may exceed context window)")

    return issues


def validate_wave(wave_id: str, wave_info: dict, packets_dir: Path) -> bool:
    """Validate all packets in a wave. Returns True if all pass."""
    wave_dir = packets_dir / wave_id
    print(f"\n  Validating {wave_info['name']}...")

    all_pass = True
    expected_tasks = wave_info["tasks"]

    # Check all expected tasks exist as files
    for task_id in expected_tasks:
        filepath = wave_dir / f"{task_id}.md"
        if not filepath.exists():
            print(f"    FAIL  {task_id}: FILE MISSING")
            all_pass = False
            continue

        issues = validate_packet(filepath, wave_id, task_id)
        if issues:
            all_pass = False
            print(f"    FAIL  {task_id}:")
            for issue in issues:
                print(f"           - {issue}")
        else:
            print(f"    OK    {task_id}")

    # Check for unexpected files in the wave dir
    expected_files = {f"{t}.md" for t in expected_tasks}
    actual_files = {f.name for f in wave_dir.glob("TASK-*.md")}
    unexpected = actual_files - expected_files
    if unexpected:
        print(f"    WARN  Unexpected files: {', '.join(sorted(unexpected))}")

    # Cross-packet dependency check: deps should reference tasks that exist
    # (either in this wave or in prior waves)
    all_known_tasks = set()
    for wid in WAVE_ORDER[:WAVE_ORDER.index(wave_id) + 1]:
        all_known_tasks.update(WAVES[wid]["tasks"])

    for task_id in expected_tasks:
        filepath = wave_dir / f"{task_id}.md"
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        dep_match = re.search(r'dependencies:\s*\[([^\]]*)\]', content)
        if dep_match and dep_match.group(1).strip():
            deps = [d.strip() for d in dep_match.group(1).split(",")]
            for dep in deps:
                if dep and dep not in all_known_tasks:
                    print(f"    WARN  {task_id}: dependency {dep} not found in waves 0-{wave_id}")

    # Verify wave has required test levels covered
    wave_test_level = wave_info.get("testLevel", "unit")
    required_levels = set(wave_test_level.split("+"))
    found_levels = set()
    for task_id in expected_tasks:
        filepath = wave_dir / f"{task_id}.md"
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        tl_match = re.search(r'testLevel:\s*(\w+)', content)
        if tl_match:
            found_levels.add(tl_match.group(1))
    missing_levels = required_levels - found_levels - {"unit"}  # unit is implicit in non-test tasks
    # Only warn about missing integration/e2e -- not a hard failure (yet)
    if missing_levels:
        print(f"    WARN  Wave expects testLevel(s) {required_levels} but only found {found_levels or 'none'} in test packets")

    if all_pass:
        print(f"  PASSED  All {len(expected_tasks)} packets valid")
    else:
        print(f"  FAILED  Some packets have issues")

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Declarative Design task packets via Claude Opus")
    parser.add_argument("--wave", type=str, help="Generate only this wave (e.g., '0', '3')")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--list-waves", action="store_true", help="List all waves and their tasks")
    parser.add_argument("--no-prior", action="store_true", help="Skip loading prior wave packets")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--validate", action="store_true", help="Validate existing packets without generating")
    args = parser.parse_args()

    if args.validate:
        # Validate mode: check existing packets, no API calls
        if args.wave is not None:
            target = [f"wave-{args.wave}"]
        else:
            target = WAVE_ORDER
        all_pass = True
        for wave_id in target:
            if wave_id not in WAVES:
                print(f"ERROR: Unknown wave '{wave_id}'", file=sys.stderr)
                sys.exit(1)
            wave_dir = PACKETS_DIR / wave_id
            if not wave_dir.exists():
                print(f"  SKIP  {wave_id}: no packets directory")
                continue
            if not validate_wave(wave_id, WAVES[wave_id], PACKETS_DIR):
                all_pass = False
        sys.exit(0 if all_pass else 1)

    if args.list_waves:
        for wave_id in WAVE_ORDER:
            w = WAVES[wave_id]
            print(f"\n{w['name']} ({wave_id})")
            print(f"  Tasks: {', '.join(w['tasks'])}")
            print(f"  testFirst: {w['testFirst']}")
        return

    # Verify spec files exist
    missing = [f for f in SPEC_FILES if not (SPECS_DIR / f).exists()]
    if missing:
        print(f"ERROR: Missing spec files in {SPECS_DIR}:", file=sys.stderr)
        for f in missing:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        api_key = input("Enter your Anthropic API key: ").strip()
    if not api_key and not args.dry_run:
        print("ERROR: No API key provided.", file=sys.stderr)
        sys.exit(1)

    # Determine which waves to generate
    if args.wave is not None:
        wave_key = f"wave-{args.wave}"
        if wave_key not in WAVES:
            print(f"ERROR: Unknown wave '{args.wave}'. Use --list-waves to see options.", file=sys.stderr)
            sys.exit(1)
        target_waves = [wave_key]
    else:
        target_waves = WAVE_ORDER

    # Load source material
    print("Loading specs...")
    all_specs = load_specs(SPECS_DIR, SPEC_FILES)
    spec_tokens_est = len(all_specs) // 4
    print(f"  Loaded {len(SPEC_FILES)} spec files (~{spec_tokens_est:,} tokens)")

    print("Loading task decomposition guide...")
    task_decomp = load_file(BUILD_DIR / "Task-Decomp-Guide.md")
    print(f"  Loaded (~{len(task_decomp)//4:,} tokens)")

    # Create output directory
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)

    # Process each wave
    for wave_id in target_waves:
        wave_info = WAVES[wave_id]
        print(f"\n{'='*60}")
        print(f"Generating: {wave_info['name']}")
        print(f"Tasks: {len(wave_info['tasks'])}")
        print(f"{'='*60}")

        # Load prior wave packets for context
        prior_packets = ""
        if not args.no_prior:
            prior_wave_ids = WAVE_ORDER[:WAVE_ORDER.index(wave_id)]
            prior_packets = load_prior_packets(PACKETS_DIR, prior_wave_ids)
            if prior_packets:
                print(f"  Including {len(prior_wave_ids)} prior wave(s) for dependency context")
        else:
            print("  Skipping prior wave context (--no-prior)")

        # Build prompt
        user_prompt = build_wave_prompt(wave_id, wave_info, task_decomp, all_specs, prior_packets)
        total_input_est = (len(SYSTEM_PROMPT) + len(user_prompt)) // 4
        print(f"  Estimated input: ~{total_input_est:,} tokens")
        print(f"  Estimated cost: ~${total_input_est * 5 / 1_000_000 + MAX_TOKENS * 25 / 1_000_000:.2f}")

        # Save prompt for inspection
        dry_run_path = PACKETS_DIR / f"{wave_id}-dry-run-prompt.md"
        dry_run_path.write_text(
            f"SYSTEM PROMPT:\n{SYSTEM_PROMPT}\n\n{'='*60}\n\nUSER PROMPT:\n{user_prompt}",
            encoding="utf-8"
        )
        print(f"  Prompt saved: {dry_run_path.relative_to(PACKETS_DIR.parent)}")

        if args.dry_run:
            print(f"  Dry run: skipping API call")
            continue

        # Gate: confirm before spending tokens
        if args.yes:
            confirm = "y"
        else:
            confirm = input(f"  Send to API? (~${total_input_est * 5 / 1_000_000 + MAX_TOKENS * 25 / 1_000_000:.2f}) [y/N]: ").strip().lower()
        if confirm != "y":
            print("  Skipped.")
            continue

        # Call API -- lazy import so --list-waves and --dry-run work without the SDK
        global anthropic
        if anthropic is None:
            try:
                import anthropic as _anthropic
                anthropic = _anthropic
            except ImportError:
                print("ERROR: anthropic SDK not installed.", file=sys.stderr)
                print("  Run: source build/.venv/bin/activate", file=sys.stderr)
                sys.exit(1)

        print("  Calling Claude Opus 4.6 (1M context)...")
        client = anthropic.Anthropic(api_key=api_key)

        raw_output = ""
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
        ) as stream:
            for text in stream.text_stream:
                raw_output += text
                print(".", end="", flush=True)

        print()
        final = stream.get_final_message()
        input_tokens = final.usage.input_tokens
        output_tokens = final.usage.output_tokens
        stop_reason = final.stop_reason
        cost = (input_tokens * 5 + output_tokens * 25) / 1_000_000

        print(f"  Tokens: {input_tokens:,} in / {output_tokens:,} out")
        print(f"  Cost: ${cost:.2f}")

        if stop_reason == "max_tokens":
            print(f"  WARNING: Output was truncated! Increase MAX_TOKENS or split wave.", file=sys.stderr)

        # Parse and save
        packets = parse_packets(raw_output, wave_id, wave_info["tasks"])
        print(f"  Parsed {len(packets)} packets")
        save_packets(packets, wave_id, PACKETS_DIR)

        # Validate before moving to next wave
        wave_ok = validate_wave(wave_id, wave_info, PACKETS_DIR)
        if not wave_ok:
            print(f"\n  Wave {wave_id} has validation issues. Stopping before next wave.")
            print(f"  Fix the issues manually, then re-run: python3 build/generate-packets.py --validate --wave {wave_id.split('-')[1]}")
            print(f"  Or regenerate: python3 build/generate-packets.py --wave {wave_id.split('-')[1]}")
            sys.exit(1)

    print(f"\nDone. Packets saved to {PACKETS_DIR.relative_to(PACKETS_DIR.parent.parent)}/")


if __name__ == "__main__":
    main()
