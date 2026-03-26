---
taskId: TASK-001
title: "Create project directory structure and Python module"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: []
produces:
  - dd/__init__.py
  - dd/db.py
  - dd/config.py
  - pyproject.toml
  - requirements.txt
verify:
  - type: typecheck
    command: 'python -c "import dd; print(dd.__version__)"'
    passWhen: 'exits 0'
  - type: file_exists
    command: 'python -c "import os; assert all(os.path.exists(p) for p in [\"dd/__init__.py\", \"dd/db.py\", \"dd/config.py\", \"pyproject.toml\", \"requirements.txt\", \"tests/__init__.py\", \"schema.sql\"])"'
    passWhen: 'exits 0'
contextProfile: minimal
---

# TASK-001: Create project directory structure and Python module

## Spec Context

### From Architecture.md -- Module Map

> All production code lives under `dd/`. Tests under `tests/`.
>
> ```
> declarative/                      <- project root
> |-- dd/
> |   |-- __init__.py
> |   |-- config.py                 <- file paths, DB name convention
> |   |-- db.py                     <- get_connection, init_db, backup_db
> |   |-- types.py                  <- enums, constants, property paths
> |   |-- color.py                  <- OKLCH conversion, delta_e, hex normalization
> |   |-- normalize.py              <- value normalization per property type
> |   ...
> |-- tests/
> |   |-- conftest.py
> |   |-- fixtures.py
> |   ...
> |-- schema.sql
> |-- pyproject.toml
> |-- requirements.txt
> ```

### From Architecture.md -- Technology Stack

> | Layer | Technology | Rationale |
> |-------|-----------|-----------|
> | Language | Python 3.11+ | Rapid iteration, strong SQLite/JSON support, OKLCH libs available |
> | Database | SQLite (WAL mode) | Portable, zero-config, matches NFR-1 |
> | Color science | `coloraide` or manual OKLCH | Perceptual clustering for delta-E calculations |
> | Testing | pytest | Standard, fast, good SQLite fixture support |
> | Packaging | Single directory, no pip package | Keep it simple -- `dd/` module with `__init__.py` |

### From User Requirements Spec -- Constraints

> - C-8: DB filename convention: `*.declarative.db` (e.g., `dank.declarative.db`). The companion skill auto-discovers files matching this pattern.

## Task

Create the project scaffold for Declarative Design. This is the foundation that all subsequent tasks build on.

1. **Create `dd/__init__.py`**:
   - Set `__version__ = "0.1.0"`
   - Import nothing else (downstream modules don't exist yet)

2. **Create `dd/config.py`**:
   - Define `DB_SUFFIX = ".declarative.db"` -- the file naming convention for DB files
   - Define `SCHEMA_PATH` that resolves to `schema.sql` at the project root (use `pathlib.Path(__file__).parent.parent / "schema.sql"`)
   - Define `PROJECT_ROOT` as `pathlib.Path(__file__).parent.parent`
   - Define `BACKUP_DIR` as `PROJECT_ROOT / "backups"`
   - Define `MAX_BACKUPS = 5` (rotation limit per NFR-9)
   - Define `LOCK_TIMEOUT_MINUTES = 10` (advisory lock expiry)
   - Define `MAX_TOKENS_PER_CALL = 100` (Figma API limit per C-3)
   - Define `MAX_BINDINGS_PER_SCRIPT = 500` (rebind script batch size)
   - Define `USE_FIGMA_CODE_LIMIT = 50000` (character limit per C-1)
   - Define a function `db_path(name: str) -> pathlib.Path` that returns `PROJECT_ROOT / f"{name}{DB_SUFFIX}"`

3. **Create `dd/db.py`**:
   - Add a stub docstring: `"""Database connection and initialization. See TASK-002 for full implementation."""`
   - Define an empty placeholder: `def get_connection(db_name: str): ...` with a pass body and a `# TODO: TASK-002` comment.

4. **Create `pyproject.toml`**:
   - Set `[project]` name = "declarative-design", version = "0.1.0", requires-python = ">=3.11"
   - Set `[project.optional-dependencies]` with `dev = ["pytest", "pytest-xdist", "pytest-timeout", "pytest-cov"]` and `color = ["coloraide"]`

5. **Create `requirements.txt`**:
   - Include: `coloraide>=0.15`, `pytest>=7.0`, `pytest-xdist`, `pytest-timeout`, `pytest-cov`

6. **Create `tests/__init__.py`** as an empty file.

7. **Verify that `schema.sql` exists at the project root.** If it doesn't exist, create a placeholder file with a comment `-- schema.sql: see TASK-002 for population`. (The real schema will be used by TASK-002.)

## Acceptance Criteria

- [ ] `python -c "import dd; print(dd.__version__)"` exits 0 and prints `0.1.0`
- [ ] `python -c "from dd.config import DB_SUFFIX, SCHEMA_PATH, PROJECT_ROOT, db_path; print(DB_SUFFIX)"` exits 0 and prints `.declarative.db`
- [ ] `python -c "from dd.config import db_path; p = db_path('test'); assert str(p).endswith('test.declarative.db')"` exits 0
- [ ] `python -c "from dd.db import get_connection"` exits 0
- [ ] File `dd/__init__.py` exists
- [ ] File `dd/config.py` exists
- [ ] File `dd/db.py` exists
- [ ] File `pyproject.toml` exists
- [ ] File `requirements.txt` exists
- [ ] File `tests/__init__.py` exists
- [ ] File `schema.sql` exists at the project root

## Notes

- `dd/db.py` is a stub in this task. TASK-002 will implement the full `get_connection`, `init_db`, and `backup_db` functions.
- The `schema.sql` file should already exist at the project root from the spec documents. If the build agent is starting from scratch, it should create a placeholder -- TASK-002 will use the real schema content.
- All config constants use UPPER_SNAKE_CASE. The `db_path` function is the only callable.