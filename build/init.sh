#!/bin/bash
# Declarative Design -- Build System Init
# Run once before using generate-packets.py or run-wave.sh.
#
# Usage: bash build/init.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Declarative Design -- Build System Init"
echo "========================================"
echo "Project: $PROJECT_DIR"
echo ""

# Initialize git repo if needed
if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "Initializing git repo..."
    cd "$PROJECT_DIR"
    git init
    git add -A
    git commit -m "chore: initial commit before build system"
    cd -
else
    echo "Git repo already exists."
fi

# Create build directories
echo "Creating build directories..."
mkdir -p "$SCRIPT_DIR/packets"
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/memory"

# Initialize empty memory files
touch "$SCRIPT_DIR/memory/decisions.md"
touch "$SCRIPT_DIR/memory/lessons.md"
touch "$SCRIPT_DIR/memory/facts.md"

# Create project source directories
echo "Creating project source directories..."
mkdir -p "$PROJECT_DIR/dd"
mkdir -p "$PROJECT_DIR/tests"

# Create dd/__init__.py if it doesn't exist
if [ ! -f "$PROJECT_DIR/dd/__init__.py" ]; then
    echo '"""Declarative Design -- Figma to SQLite extraction pipeline."""' > "$PROJECT_DIR/dd/__init__.py"
fi

# Create tests/__init__.py if it doesn't exist
if [ ! -f "$PROJECT_DIR/tests/__init__.py" ]; then
    touch "$PROJECT_DIR/tests/__init__.py"
fi

# Create venv and install dependencies
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "  Created: build/.venv"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet anthropic coloraide pytest pytest-xdist pytest-timeout pytest-cov
echo "  OK  anthropic, coloraide, pytest, pytest-xdist, pytest-timeout, pytest-cov installed"

# Verify prerequisites
echo ""
echo "Checking prerequisites..."

check_cmd() {
    if command -v "$1" >/dev/null 2>&1; then
        echo "  OK  $1 ($(command -v "$1"))"
        return 0
    else
        echo "  MISSING  $1"
        return 1
    fi
}

MISSING=0
check_cmd python3 || MISSING=1
check_cmd git || MISSING=1
check_cmd claude || { echo "  NOTE  claude CLI not found -- run-wave.sh requires it"; }

# Check Python version
if command -v python3 >/dev/null 2>&1; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        echo "  OK  Python $PY_VERSION (>= 3.11)"
    else
        echo "  WARN  Python $PY_VERSION (3.11+ recommended)"
    fi
fi

# Verify venv has what we need
if "$VENV_DIR/bin/python" -c "import anthropic" 2>/dev/null; then
    echo "  OK  anthropic SDK (in venv)"
else
    echo "  MISSING  anthropic SDK in venv"
    MISSING=1
fi

# Verify spec files exist
echo ""
echo "Checking spec files..."
SPECS=("Architecture.md" "User Requirements Spec.md" "Technical Design Spec.md" "Probe Results.md" "Tooling Comparison.md" "schema.sql")
for spec in "${SPECS[@]}"; do
    if [ -f "$PROJECT_DIR/$spec" ]; then
        echo "  OK  $spec"
    else
        echo "  MISSING  $spec"
        MISSING=1
    fi
done

echo ""
if [ "$MISSING" -eq 0 ]; then
    echo "Build system initialized. Next steps:"
    echo ""
    echo "  1. Activate venv:     source build/.venv/bin/activate"
    echo "  2. Generate packets:  python3 build/generate-packets.py --dry-run"
    echo "  3. Review dry run:    ls build/packets/"
    echo "  4. Generate for real: ANTHROPIC_API_KEY=sk-... python3 build/generate-packets.py"
    echo "  5. Run a wave:        ./build/run-wave.sh 0"
else
    echo "Some prerequisites are missing. Fix them and re-run."
    exit 1
fi
