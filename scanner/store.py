"""SQLite layer for fingerprint deduplication and issue tracking."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from scanner.batches import Batch


_DDL = """\
CREATE TABLE IF NOT EXISTS batches (
    fingerprint       TEXT PRIMARY KEY,
    batch_key         TEXT NOT NULL,
    rule              TEXT NOT NULL,
    title             TEXT NOT NULL,
    finding_count     INTEGER NOT NULL,
    github_issue_number INTEGER,
    github_issue_url  TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
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
"""


@dataclass
class BatchRecord:
    fingerprint: str
    batch_key: str
    rule: str
    title: str
    finding_count: int
    github_issue_number: int | None
    github_issue_url: str | None
    created_at: str


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


def init_db(db_path: Path) -> None:
    """Create tables if they don't exist yet."""
    with _connect(db_path) as conn:
        conn.executescript(_DDL)


def is_known(db_path: Path, fingerprint: str) -> bool:
    """Return True if *fingerprint* already exists in the batches table."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM batches WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
    return row is not None


def record_batch(
    db_path: Path,
    batch: Batch,
    github_issue_number: int | None = None,
    github_issue_url: str | None = None,
) -> None:
    """Insert a batch and its findings into the database."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO batches
                (fingerprint, batch_key, rule, title, finding_count,
                 github_issue_number, github_issue_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch.fingerprint,
                batch.key,
                batch.rule,
                batch.title,
                batch.count,
                github_issue_number,
                github_issue_url,
            ),
        )
        conn.executemany(
            """
            INSERT INTO findings
                (batch_fingerprint, rule_id, file_path, line_start,
                 column_start, message, is_autofixable)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    batch.fingerprint,
                    f.rule_id,
                    f.file_path,
                    f.line_start,
                    f.column_start,
                    f.message,
                    int(f.is_autofixable),
                )
                for f in batch.findings
            ],
        )


def load_batch_record(db_path: Path, fingerprint: str) -> BatchRecord | None:
    """Retrieve a stored batch record by fingerprint."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM batches WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
    if row is None:
        return None
    return BatchRecord(**dict(row))
