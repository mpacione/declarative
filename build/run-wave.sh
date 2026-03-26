#!/bin/bash
# Declarative Design -- Wave Runner
# Feeds task packets to Claude Code one at a time, sequentially.
# Auto-commits after each successful task. Stops on first failure.
#
# Usage:
#   ./build/run-wave.sh 0              # Run all tasks in wave 0
#   ./build/run-wave.sh 3              # Run all tasks in wave 3
#   ./build/run-wave.sh 0 TASK-003     # Resume wave 0 starting from TASK-003
#   DRY_RUN=1 ./build/run-wave.sh 0    # Print what would run, don't execute
#   NO_COMMIT=1 ./build/run-wave.sh 0  # Skip auto-commit after each task

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PACKETS_DIR="$SCRIPT_DIR/packets"
LOGS_DIR="$SCRIPT_DIR/logs"
SPECS_DIR="$PROJECT_DIR"

WAVE="${1:?Usage: run-wave.sh <wave-number> [start-from-task]}"
START_FROM="${2:-}"
DRY_RUN="${DRY_RUN:-0}"
NO_COMMIT="${NO_COMMIT:-0}"

WAVE_DIR="$PACKETS_DIR/wave-$WAVE"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$WAVE_DIR" ]; then
    echo "ERROR: No packets found at $WAVE_DIR"
    echo "Run: source build/.venv/bin/activate && python3 build/generate-packets.py --wave $WAVE"
    exit 1
fi

# Activate venv if it exists (so tasks can use coloraide, pytest, etc.)
if [ -d "$VENV_DIR" ] && [ -z "${VIRTUAL_ENV:-}" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Activated venv: $VENV_DIR"
fi

mkdir -p "$LOGS_DIR"

# Collect packets in sorted order
PACKETS=($(ls "$WAVE_DIR"/TASK-*.md 2>/dev/null | sort))

if [ ${#PACKETS[@]} -eq 0 ]; then
    echo "ERROR: No TASK-*.md files in $WAVE_DIR"
    exit 1
fi

echo "============================================================"
echo "Declarative Design -- Wave $WAVE Runner"
echo "============================================================"
echo "Packets: ${#PACKETS[@]}"
echo "Project: $PROJECT_DIR"
echo ""

SKIP=0
if [ -n "$START_FROM" ]; then
    SKIP=1
    echo "Resuming from $START_FROM"
    echo ""
fi

PASSED=0
FAILED=0
SKIPPED=0
START_TIME=$(date +%s)

for PACKET in "${PACKETS[@]}"; do
    TASK_ID=$(basename "$PACKET" .md)

    # Skip until we reach the start-from task
    if [ "$SKIP" -eq 1 ]; then
        if [ "$TASK_ID" = "$START_FROM" ]; then
            SKIP=0
        else
            echo "  SKIP  $TASK_ID (before $START_FROM)"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi
    fi

    echo "------------------------------------------------------------"
    echo "  TASK  $TASK_ID"
    echo "------------------------------------------------------------"

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry run] Would execute: claude --print \"$(head -1 "$PACKET")\""
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    TASK_START=$(date +%s)
    LOG_FILE="$LOGS_DIR/${TASK_ID}.log"

    # Build the disambiguation preamble: tell the agent where to look
    # for context before asking the user for clarification
    PREAMBLE="IMPORTANT CONTEXT RULES:
If anything in this task is ambiguous or unclear, resolve it yourself by reading these files BEFORE asking the user:
- Spec files in the project root: Architecture.md, User Requirements Spec.md, Technical Design Spec.md, Probe Results.md, Tooling Comparison.md, schema.sql
- Task Decomposition Guide: build/Task-Decomp-Guide.md
- Other task packets in this wave: build/packets/wave-${WAVE}/
- Prior wave packets: build/packets/wave-*/
Only ask the user if the specs genuinely do not cover the question.

TASK PACKET FOLLOWS:
"

    # Feed the preamble + packet to Claude Code
    # --print sends the prompt and exits (non-interactive)
    if claude --print "${PREAMBLE}$(cat "$PACKET")" \
        --cwd "$PROJECT_DIR" \
        2>&1 | tee "$LOG_FILE"; then

        TASK_END=$(date +%s)
        DURATION=$((TASK_END - TASK_START))
        echo ""
        echo "  PASS  $TASK_ID (${DURATION}s)"
        PASSED=$((PASSED + 1))

        # Auto-commit after successful task
        if [ "$NO_COMMIT" -eq 0 ]; then
            cd "$PROJECT_DIR"
            if [ -n "$(git status --porcelain)" ]; then
                git add -A
                git commit -m "build($TASK_ID): complete task from wave-$WAVE

Automated commit by run-wave.sh after successful task execution."
                echo "  COMMIT  $TASK_ID"
            else
                echo "  COMMIT  $TASK_ID (no changes to commit)"
            fi
            cd - > /dev/null
        fi
    else
        TASK_END=$(date +%s)
        DURATION=$((TASK_END - TASK_START))
        echo ""
        echo "  FAIL  $TASK_ID (${DURATION}s)"
        echo "  Log:  $LOG_FILE"
        FAILED=$((FAILED + 1))

        echo ""
        echo "============================================================"
        echo "STOPPED: $TASK_ID failed. Fix and re-run:"
        echo "  ./build/run-wave.sh $WAVE $TASK_ID"
        echo "============================================================"
        exit 1
    fi
done

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

echo ""
echo "============================================================"
echo "Wave $WAVE Complete"
echo "============================================================"
echo "  Passed:  $PASSED"
echo "  Failed:  $FAILED"
echo "  Skipped: $SKIPPED"
echo "  Time:    ${TOTAL_DURATION}s"
echo "============================================================"
