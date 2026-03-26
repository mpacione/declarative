"""Pytest configuration and shared fixtures."""

import pytest
import sqlite3
from typing import Generator

from dd import db as dd_db


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
    config.addinivalue_line("markers", "slow: slow tests (e2e)")


@pytest.fixture
def db() -> Generator[sqlite3.Connection, None, None]:
    """
    Provide an in-memory SQLite connection with full schema initialized.
    Auto-closes after each test.
    """
    conn = dd_db.init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db_with_file(db: sqlite3.Connection) -> sqlite3.Connection:
    """
    Provide a DB with a default file row inserted.
    """
    db.execute(
        "INSERT INTO files (id, file_key, name, node_count, screen_count) VALUES (?, ?, ?, ?, ?)",
        (1, "test_file_key_abc123", "Test File", 100, 5)
    )
    db.commit()
    return db


@pytest.fixture
def temp_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Provide an in-memory SQLite connection with full schema initialized.
    Alias for 'db' fixture for backward compatibility.
    Auto-closes after each test.
    """
    conn = dd_db.init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def set_timeout():
    """Apply a 30-second timeout to all tests."""
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError("Test exceeded 30 second timeout")

    # Set the signal handler
    signal.signal(signal.SIGALRM, timeout_handler)

    # Set 30 second alarm
    signal.alarm(30)

    yield

    # Cancel the alarm after test completes
    signal.alarm(0)