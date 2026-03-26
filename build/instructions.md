# Declarative Design -- Build Instructions

## Setup (once)

```bash
cd ~/MattPacione_Local/Declarative
bash build/init.sh
```

init.sh does everything: creates a venv at `build/.venv`, installs anthropic +
coloraide + pytest + pytest-xdist + pytest-timeout + pytest-cov, creates the
`dd/` and `tests/` directories, and checks that all spec files are present.

## Activate Venv

```bash
source build/.venv/bin/activate
```

Do this before running any python command below. run-wave.sh activates it
automatically, but generate-packets.py needs it for API calls.

(--list-waves and --dry-run work without the venv.)

## Generate Packets

```bash
# See what waves exist and their tasks
python3 build/generate-packets.py --list-waves

# Preview what will be sent to the API (no cost)
python3 build/generate-packets.py --dry-run

# Generate one wave at a time (recommended -- review packets before moving on)
ANTHROPIC_API_KEY=sk-... python3 build/generate-packets.py --wave 0

# Or generate all waves in one shot (~$8 total, auto-confirm)
ANTHROPIC_API_KEY=sk-... python3 build/generate-packets.py -y

# Regenerate a single wave (overwrites existing packets)
ANTHROPIC_API_KEY=sk-... python3 build/generate-packets.py --wave 3
```

After generating, review the packets before running them:

```bash
cat build/packets/wave-0/TASK-001.md
```

## Run Tasks via Claude Code

```bash
# Run all tasks in a wave (activates venv, auto-commits after each task)
./build/run-wave.sh 0

# Resume from a specific task if one failed
./build/run-wave.sh 0 TASK-003

# Preview without executing
DRY_RUN=1 ./build/run-wave.sh 0

# Run without auto-committing
NO_COMMIT=1 ./build/run-wave.sh 0
```

run-wave.sh feeds each packet to `claude --print`, runs them sequentially,
stops on first failure, auto-commits after each successful task, and logs
output to `build/logs/TASK-NNN.log`. Each task's agent is instructed to
consult the spec files and other task packets before asking the user for
clarification.

## Wave Order

Run waves in order. Each wave depends on the previous one completing.

| Wave | What it builds | Tasks | Test levels |
|------|---------------|-------|-------------|
| 0 | Project scaffold + DB init + test infra | TASK-001 to TASK-007 | unit |
| 1 | Extraction pipeline (inventory + screens) | TASK-010 to TASK-016 | unit + integration |
| 2 | Component extraction | TASK-020 to TASK-026 | unit + integration |
| 3 | Census views + clustering | TASK-030 to TASK-037 | unit + integration + e2e |
| 4 | Curation workflow + validation | TASK-040 to TASK-045 | unit + integration + e2e |
| 5 | Figma export (variables + rebinding) | TASK-050 to TASK-055 | unit + integration + e2e |
| 6 | Code export (CSS, Tailwind, DTCG) | TASK-060 to TASK-065 | unit + integration + e2e |
| 7 | Companion skill + drift detection | TASK-070 to TASK-074 | unit + e2e |

## Running Tests

After each wave completes, run the test suite:

```bash
# All tests for the project so far
pytest tests/ -v

# Just unit tests (fast)
pytest tests/ -m unit -v

# Just integration tests
pytest tests/ -m integration -v

# Just e2e tests (slower)
pytest tests/ -m e2e -v

# Skip slow e2e tests during development
pytest tests/ -m "not slow" -v

# With coverage report
pytest tests/ --cov=dd --cov-report=term -v

# Parallel execution (faster on multi-core)
pytest tests/ -n auto -v
```

## If Something Breaks

1. Check the log: `cat build/logs/TASK-NNN.log`
2. Fix the issue manually or edit the packet in `build/packets/wave-N/TASK-NNN.md`
3. Resume: `./build/run-wave.sh N TASK-NNN`

## File Layout

```
Declarative/
  build/
    .venv/                  # Python venv (created by init.sh)
    packets/                # Generated task packets (by wave)
    logs/                   # Claude Code execution logs
    memory/                 # decisions.md, lessons.md, facts.md
    generate-packets.py     # Calls Opus to create packets from specs
    run-wave.sh             # Feeds packets to Claude Code sequentially
    init.sh                 # One-time setup
    Task-Decomp-Guide.md    # Wave/task decomposition (input to generator)
    instructions.md         # This file
  dd/                       # Production code (built by tasks)
  tests/                    # Test files (built by tasks)
  schema.sql                # DB schema (source of truth)
  *.md                      # Spec documents
```
