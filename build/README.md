# Build System

This project was built autonomously using a wave-based pipeline. Each wave feeds pre-generated task packets to `claude --print`, auto-committing after each successful task.

## How It Works

1. **Task packets** in `packets/wave-N/TASK-NNN.md` describe exactly what to build
2. **`run-wave.sh`** feeds each packet to Claude CLI sequentially
3. After each task succeeds, the script auto-commits to git
4. If a task fails, it stops and tells you where to resume

## Setup

```bash
# One-time: creates venv, installs deps, scaffolds directories
bash build/init.sh

# Activate venv
source build/.venv/bin/activate
```

## Running

```bash
# Validate all packets before starting
python3 build/generate-packets.py --validate

# Run a wave
./build/run-wave.sh 0              # All tasks in wave 0
./build/run-wave.sh 3 TASK-033     # Resume wave 3 from a specific task

# Dry run (shows what would execute)
DRY_RUN=1 ./build/run-wave.sh 0

# Skip auto-commit
NO_COMMIT=1 ./build/run-wave.sh 0
```

## Waves

| Wave | Tasks | What it builds | Test levels |
|------|-------|----------------|-------------|
| 0 | TASK-001 to TASK-007 | Project scaffold, DB init, test infrastructure | unit |
| 1 | TASK-010 to TASK-016 | Extraction pipeline (inventory + screens) | unit + integration |
| 2 | TASK-020 to TASK-026 | Component extraction + normalization | unit + integration |
| 3 | TASK-030 to TASK-037 | Census views + clustering | unit + integration + e2e |
| 4 | TASK-040 to TASK-045 | Curation workflow + validation | unit + integration + e2e |
| 5 | TASK-050 to TASK-055 | Figma export (variables + rebinding) | unit + integration + e2e |
| 6 | TASK-060 to TASK-065 | Code export (CSS, Tailwind, DTCG) | unit + integration + e2e |
| 7 | TASK-070 to TASK-074 | Companion skill + drift detection | unit + e2e |

**52 tasks, 505 tests, 89% code coverage.**

## If Something Fails

1. Check the log: `build/logs/TASK-NNN.log`
2. Fix the issue
3. Resume: `./build/run-wave.sh N TASK-NNN`

Do not skip waves — each wave depends on prior waves completing.

## Directory Layout

```
build/
├── init.sh                 # One-time setup
├── run-wave.sh             # Wave execution runner
├── generate-packets.py     # Task packet generator/validator
├── Task-Decomp-Guide.md   # 43 tasks across 8 waves (source of truth)
├── instructions.md         # Detailed usage reference
├── packets/                # Pre-generated task packets
│   ├── wave-0/
│   ├── wave-1/
│   └── ...
├── logs/                   # Execution logs (created during build)
└── memory/                 # Build context (decisions, lessons, facts)
```
