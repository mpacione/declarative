# Declarative Design Build -- Bootstrap Prompt

Copy everything below the line and paste it into a fresh Claude Code instance.

---

You are building Declarative Design, an autonomous wave-based build pipeline that constructs a Figma-to-SQLite extraction tool. The specs, build scripts, and pre-generated task packets are already in place. Your job is to set up the project in a fresh directory, initialize the repo, and execute the build wave by wave.

## Step 1: Set up the project

```
mkdir -p ~/declarative-build && cd ~/declarative-build
```

Copy the following from the existing Declarative folder into this new directory:

- All spec files: `Architecture.md`, `User Requirements Spec.md`, `Technical Design Spec.md`, `Probe Results.md`, `Tooling Comparison.md`, `schema.sql`
- The entire `build/` directory (contains scripts, task decomp guide, and pre-generated packets in `build/packets/`)

```
cp ~/MattPacione_Local/Declarative/Architecture.md .
cp ~/MattPacione_Local/Declarative/User\ Requirements\ Spec.md .
cp ~/MattPacione_Local/Declarative/Technical\ Design\ Spec.md .
cp ~/MattPacione_Local/Declarative/Probe\ Results.md .
cp ~/MattPacione_Local/Declarative/Tooling\ Comparison.md .
cp ~/MattPacione_Local/Declarative/schema.sql .
cp -r ~/MattPacione_Local/Declarative/build .
```

## Step 2: Initialize git and remote

```
git init
git add -A
git commit -m "chore: initial project scaffold with specs, build system, and task packets"
git remote add origin <REMOTE_URL>
git branch -M main
git push -u origin main
```

## Step 3: Run init.sh

```
bash build/init.sh
```

This creates the venv, installs all dependencies (anthropic, coloraide, pytest, pytest-xdist, pytest-timeout, pytest-cov), creates `dd/` and `tests/` directories, and verifies spec files are present. Commit the result:

```
git add -A
git commit -m "chore: run init.sh -- venv, directories, dependency check"
```

## Step 4: Validate packets

The task packets are already generated in `build/packets/`. Validate them before starting:

```
source build/.venv/bin/activate
python3 build/generate-packets.py --validate
```

If any wave fails validation, stop and report the issues. Do not proceed until all 8 waves pass.

## Step 5: Run the build, wave by wave

```
./build/run-wave.sh 0
```

This feeds each task packet to `claude --print` sequentially. After each successful task, it auto-commits to git. If a task fails, it stops and tells you where to resume.

After wave 0 completes, push and continue:

```
git push
./build/run-wave.sh 1
```

Continue through all 8 waves in order (0, 1, 2, 3, 4, 5, 6, 7). Push after each wave completes.

## Step 6: Final gate

After wave 7 completes, run the full test suite:

```
pytest tests/ -v --cov=dd --cov-report=term
```

Report the results. Push the final state:

```
git push
```

## Key rules

- **Do not skip waves.** Each wave depends on prior waves completing.
- **If a task fails:** check `build/logs/TASK-NNN.log`, fix the issue, then resume with `./build/run-wave.sh N TASK-NNN`.
- **If anything in a task packet is ambiguous:** read the spec files in the project root and the Task Decomposition Guide at `build/Task-Decomp-Guide.md` BEFORE asking the user. Also check other task packets in `build/packets/` for context on dependencies and produced artifacts. Only escalate to the user if the specs genuinely do not cover the question.
- **Do not modify task packets.** Execute them as-is. If a packet has issues, report them rather than silently fixing.
- **After each wave:** verify the tests pass for that wave before moving to the next. If tests fail, fix the code (not the tests) and re-run.

## Project structure

```
declarative-build/
  Architecture.md
  User Requirements Spec.md
  Technical Design Spec.md
  Probe Results.md
  Tooling Comparison.md
  schema.sql
  build/
    run-wave.sh             # Feeds packets to claude --print, auto-commits
    init.sh                 # One-time setup
    Task-Decomp-Guide.md    # 43 tasks across 8 waves (source of truth)
    instructions.md         # Usage reference
    packets/                # Pre-generated task packets (by wave)
      wave-0/               # TASK-001 through TASK-007
      wave-1/               # TASK-010 through TASK-016
      ...
    logs/                   # Execution logs (created during build)
  dd/                       # Production code (built by tasks)
  tests/                    # Test files (built by tasks)
```

## Wave summary (43 tasks total)

| Wave | Tasks | What it builds | Test levels |
|------|-------|---------------|-------------|
| 0 | TASK-001 to TASK-007 | Project scaffold + DB init + test infrastructure | unit |
| 1 | TASK-010 to TASK-016 | Extraction pipeline (inventory + screens) | unit + integration |
| 2 | TASK-020 to TASK-026 | Component extraction | unit + integration |
| 3 | TASK-030 to TASK-037 | Census views + clustering | unit + integration + e2e |
| 4 | TASK-040 to TASK-045 | Curation workflow + validation | unit + integration + e2e |
| 5 | TASK-050 to TASK-055 | Figma export (variables + rebinding) | unit + integration + e2e |
| 6 | TASK-060 to TASK-065 | Code export (CSS, Tailwind, DTCG) | unit + integration + e2e |
| 7 | TASK-070 to TASK-074 | Companion skill + drift detection | unit + e2e |

Begin with Step 1. Work through each step sequentially. Do not ask for confirmation between steps unless something fails.
