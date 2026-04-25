"""Functional-audit harness — wraps subprocess.run, captures everything to disk.

Usage:
    from tools.audit_runner import run_step

    run_step(
        section="01-extract",
        name="dd-extract",
        cmd=[".venv/bin/python", "-m", "dd", "extract", "<file_key>", "--db", "audit-fresh.db"],
        timeout_s=600,
        pre_state_db="audit-fresh.db",   # optional: snapshot row counts before
        post_state_db="audit-fresh.db",  # optional: snapshot row counts after
    )

Each run produces, in audit/<date>/sections/<section>/:
    command.txt
    stdout.txt
    stderr.txt
    exit-code.txt
    wall-time-ms.txt
    pre-state.json       (if pre_state_db given)
    post-state.json      (if post_state_db given)
    side-effects.json    (file-system changes during the run)

Every record is purely observational. No retries. No fallbacks. First-attempt
exit code is what gets recorded.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

# Resolve audit dir from env (set once at session start) so subagents inherit
AUDIT_DIR = Path(os.environ.get("DD_AUDIT_DIR", "audit/20260425-1042"))


def db_state(db_path: str | None) -> dict:
    """Snapshot row counts for every table in a SQLite db. Returns {} if missing."""
    if not db_path or not Path(db_path).exists():
        return {"_db_missing": True, "_db_path": db_path}
    out: dict = {"_db_path": db_path, "_size_bytes": Path(db_path).stat().st_size, "tables": {}}
    try:
        conn = sqlite3.connect(db_path)
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                out["tables"][name] = cnt
            except sqlite3.Error as e:
                out["tables"][name] = {"_error": str(e)}
        conn.close()
    except sqlite3.Error as e:
        out["_error"] = str(e)
    return out


def fs_state(watch_dirs: list[str]) -> dict:
    """Snapshot mtime + size for every file under watch_dirs. Used to compute side-effects diff."""
    out: dict = {}
    for d in watch_dirs:
        if not Path(d).exists():
            out[d] = {"_missing": True}
            continue
        files = {}
        for p in Path(d).rglob("*"):
            if p.is_file():
                st = p.stat()
                files[str(p)] = {"mtime": st.st_mtime, "size": st.st_size}
        out[d] = files
    return out


def fs_diff(before: dict, after: dict) -> dict:
    """Compute file-system changes between two fs_state snapshots."""
    diff: dict = {"created": [], "modified": [], "deleted": []}
    for dir_key in set(before.keys()) | set(after.keys()):
        b = before.get(dir_key, {})
        a = after.get(dir_key, {})
        if isinstance(b, dict) and "_missing" in b:
            b = {}
        if isinstance(a, dict) and "_missing" in a:
            a = {}
        b_files = {k: v for k, v in b.items() if not k.startswith("_")}
        a_files = {k: v for k, v in a.items() if not k.startswith("_")}
        for path in set(a_files) - set(b_files):
            diff["created"].append({"path": path, "size": a_files[path]["size"]})
        for path in set(b_files) - set(a_files):
            diff["deleted"].append({"path": path, "size": b_files[path]["size"]})
        for path in set(a_files) & set(b_files):
            if (
                a_files[path]["mtime"] != b_files[path]["mtime"]
                or a_files[path]["size"] != b_files[path]["size"]
            ):
                diff["modified"].append(
                    {
                        "path": path,
                        "before_size": b_files[path]["size"],
                        "after_size": a_files[path]["size"],
                    }
                )
    return diff


def run_step(
    *,
    section: str,
    name: str,
    cmd: list[str],
    timeout_s: int = 300,
    pre_state_db: str | None = None,
    post_state_db: str | None = None,
    watch_dirs: list[str] | None = None,
    cwd: str | None = None,
    extra_env: dict | None = None,
) -> dict:
    """Run a single audit step, capture everything, return the verdict dict."""
    section_dir = AUDIT_DIR / "sections" / section
    section_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    pre_db = db_state(pre_state_db) if pre_state_db else None
    pre_fs = fs_state(watch_dirs) if watch_dirs else None

    env = {**os.environ, **(extra_env or {})}
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            cwd=cwd,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        timed_out = False
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        timed_out = True
        exit_code = -1
        stdout = e.stdout.decode() if e.stdout else ""
        stderr = (e.stderr.decode() if e.stderr else "") + f"\n[TIMEOUT after {timeout_s}s]"

    post_db = db_state(post_state_db) if post_state_db else None
    post_fs = fs_state(watch_dirs) if watch_dirs else None

    record = {
        "section": section,
        "name": name,
        "started_at": started_at,
        "ended_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "command": cmd,
        "cwd": cwd or os.getcwd(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_ms": elapsed_ms,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "pre_state_db": pre_db,
        "post_state_db": post_db,
        "side_effects": fs_diff(pre_fs, post_fs) if pre_fs is not None else None,
    }

    # Spread to per-step files for grep-ability
    base = section_dir / name
    (section_dir / f"{name}.command.txt").write_text(" ".join(cmd))
    (section_dir / f"{name}.stdout.txt").write_text(stdout)
    (section_dir / f"{name}.stderr.txt").write_text(stderr)
    (section_dir / f"{name}.exit-code.txt").write_text(str(exit_code))
    (section_dir / f"{name}.wall-time-ms.txt").write_text(str(elapsed_ms))
    (section_dir / f"{name}.record.json").write_text(json.dumps(record, indent=2, default=str))

    return record


def write_verdict(section: str, verdict: str, summary: str, evidence: list[str]) -> None:
    """Write audit/<date>/sections/<section>/verdict.md."""
    section_dir = AUDIT_DIR / "sections" / section
    section_dir.mkdir(parents=True, exist_ok=True)
    body = [
        f"# Section {section} — verdict",
        "",
        f"**Verdict:** {verdict}",
        "",
        "## Summary",
        summary,
        "",
        "## Evidence",
    ]
    for e in evidence:
        body.append(f"- {e}")
    (section_dir / "verdict.md").write_text("\n".join(body) + "\n")


VERDICTS = (
    "WORKS-CLEAN",
    "WORKS-DEGRADED",
    "WORKS-FOR-SUBSET",
    "BROKEN-RUNTIME",
    "BROKEN-CONTRACT",
    "BROKEN-MISSING-DEPENDENCY",
    "DEPRECATED-IN-CODE",
    "NEVER-SHIPPED",
    "OUT-OF-SCOPE",
)


if __name__ == "__main__":
    print("audit_runner — invoked as a module, not a CLI. Import run_step / write_verdict.")
    print(f"  AUDIT_DIR = {AUDIT_DIR}")
    print(f"  verdicts:  {VERDICTS}")
