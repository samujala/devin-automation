"""SQLite layer for the orchestrator.

Extends the scanner's schema (batches + findings tables) with:
  - orchestrator_status column on batches
  - devin_sessions table
  - session_events table
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


_MIGRATION_ADD_STATUS = """\
ALTER TABLE batches ADD COLUMN orchestrator_status TEXT NOT NULL DEFAULT 'unprocessed';
"""

_MIGRATION_ADD_MERGED_AT = """\
ALTER TABLE devin_sessions ADD COLUMN merged_at TEXT;
"""

_HEARTBEAT_DDL = """\
CREATE TABLE IF NOT EXISTS orchestrator_heartbeat (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    started_at   TEXT NOT NULL,
    last_poll_at TEXT NOT NULL,
    poll_count   INTEGER NOT NULL DEFAULT 0
);
"""

_DDL = """\
CREATE TABLE IF NOT EXISTS batches (
    fingerprint           TEXT PRIMARY KEY,
    batch_key             TEXT NOT NULL,
    rule                  TEXT NOT NULL,
    title                 TEXT NOT NULL,
    finding_count         INTEGER NOT NULL,
    github_issue_number   INTEGER,
    github_issue_url      TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    orchestrator_status   TEXT NOT NULL DEFAULT 'unprocessed'
);

CREATE TABLE IF NOT EXISTS findings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_fingerprint TEXT NOT NULL REFERENCES batches(fingerprint),
    rule_id           TEXT NOT NULL,
    file_path         TEXT NOT NULL,
    line_start        INTEGER NOT NULL,
    column_start      INTEGER,
    message           TEXT,
    is_autofixable    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS devin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_fingerprint TEXT NOT NULL REFERENCES batches(fingerprint),
    devin_session_id TEXT UNIQUE NOT NULL,
    devin_session_url TEXT,
    status TEXT NOT NULL,
    pr_url TEXT,
    pr_number INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds INTEGER,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devin_session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_devin_sessions_status
    ON devin_sessions(status);
CREATE INDEX IF NOT EXISTS idx_session_events_session
    ON session_events(devin_session_id, timestamp);
"""


@dataclass
class Heartbeat:
    started_at: str
    last_poll_at: str
    poll_count: int


@dataclass
class BatchRow:
    fingerprint: str
    batch_key: str
    rule: str
    title: str
    finding_count: int
    github_issue_number: int | None
    github_issue_url: str | None
    created_at: str
    orchestrator_status: str


@dataclass
class SessionRow:
    id: int
    batch_fingerprint: str
    devin_session_id: str
    devin_session_url: str | None
    status: str
    pr_url: str | None
    pr_number: int | None
    started_at: str
    finished_at: str | None
    duration_seconds: int | None
    error_message: str | None
    merged_at: str | None = None


@contextmanager
def _connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def init_db(db_path: Path) -> None:
    """Apply orchestrator migration idempotently, then create new tables."""
    with _connect(db_path) as conn:
        if _table_exists(conn, "batches") and not _column_exists(conn, "batches", "orchestrator_status"):
            conn.execute(_MIGRATION_ADD_STATUS)
        conn.executescript(_DDL)
        conn.executescript(_HEARTBEAT_DDL)
        if not _column_exists(conn, "devin_sessions", "merged_at"):
            conn.execute(_MIGRATION_ADD_MERGED_AT)


def init_heartbeat(db_path: Path) -> None:
    """Insert the single heartbeat row if it doesn't exist yet."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO orchestrator_heartbeat (id, started_at, last_poll_at, poll_count)
            VALUES (1, datetime('now'), datetime('now'), 0)
            """
        )


def write_heartbeat(db_path: Path) -> None:
    """Update last_poll_at to now and increment poll_count. Idempotent."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO orchestrator_heartbeat (id, started_at, last_poll_at, poll_count)
            VALUES (1, datetime('now'), datetime('now'), 1)
            ON CONFLICT(id) DO UPDATE SET
                last_poll_at = datetime('now'),
                poll_count   = poll_count + 1
            """
        )


def get_heartbeat(db_path: Path) -> Heartbeat | None:
    """Read the heartbeat row. Returns None if the orchestrator has never run."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT started_at, last_poll_at, poll_count FROM orchestrator_heartbeat WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    return Heartbeat(started_at=row[0], last_poll_at=row[1], poll_count=row[2])


# ── Batch queries ─────────────────────────────────────────────────────────────

def get_unprocessed_batches(db_path: Path) -> list[BatchRow]:
    """Return batches eligible for orchestration (unprocessed + have an issue)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM batches
            WHERE orchestrator_status = 'unprocessed'
              AND github_issue_number IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
    return [BatchRow(**dict(r)) for r in rows]


def get_all_batches_with_issues(db_path: Path) -> list[BatchRow]:
    """All batches that have a GitHub issue, regardless of orchestrator_status."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM batches
            WHERE github_issue_number IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
    return [BatchRow(**dict(r)) for r in rows]


def get_batch_by_key(db_path: Path, batch_key: str) -> BatchRow | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE batch_key = ?", (batch_key,)
        ).fetchone()
    return BatchRow(**dict(row)) if row else None


def mark_batch_status(db_path: Path, fingerprint: str, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE batches SET orchestrator_status = ? WHERE fingerprint = ?",
            (status, fingerprint),
        )


# ── Session queries ───────────────────────────────────────────────────────────

def record_session_start(
    db_path: Path,
    batch_fingerprint: str,
    session_id: str,
    session_url: str | None,
    started_at: str,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO devin_sessions
                (batch_fingerprint, devin_session_id, devin_session_url, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (batch_fingerprint, session_id, session_url, started_at),
        )


def update_session(
    db_path: Path,
    session_id: str,
    status: str,
    pr_url: str | None = None,
    pr_number: int | None = None,
    error: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE devin_sessions
            SET status = ?,
                pr_url = COALESCE(?, pr_url),
                pr_number = COALESCE(?, pr_number),
                error_message = COALESCE(?, error_message)
            WHERE devin_session_id = ?
            """,
            (status, pr_url, pr_number, error, session_id),
        )


def finalize_session(
    db_path: Path,
    session_id: str,
    status: str,
    finished_at: str,
    duration_seconds: int,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE devin_sessions
            SET status = ?, finished_at = ?, duration_seconds = ?
            WHERE devin_session_id = ?
            """,
            (status, finished_at, duration_seconds, session_id),
        )


def get_in_progress_sessions(db_path: Path) -> list[SessionRow]:
    """Sessions that are still running (not in a terminal state)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM devin_sessions
            WHERE status NOT IN ('completed', 'failed', 'timeout', 'orphaned')
            ORDER BY started_at
            """
        ).fetchall()
    return [SessionRow(**dict(r)) for r in rows]


def count_in_progress_sessions(db_path: Path) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM devin_sessions
            WHERE status NOT IN ('completed', 'failed', 'timeout', 'orphaned')
            """
        ).fetchone()
    return row[0]


def append_event(
    db_path: Path,
    session_id: str,
    event_type: str,
    payload_dict: dict,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO session_events (devin_session_id, event_type, payload, timestamp)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (session_id, event_type, json.dumps(payload_dict)),
        )
