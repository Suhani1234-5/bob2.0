"""
SQLite schema and connection helpers for ProofPR.

Usage:
    from database import get_connection, init_db

    init_db()                       # create tables if they don't exist
    conn = get_connection()         # get a thread-local connection
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.investigator_agent import CandidateFinding

DB_PATH = Path(__file__).parent / "proofpr.db"

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------------------
-- pull_requests
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pull_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    repository  TEXT    NOT NULL,
    pr_number   INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    description TEXT,
    branch      TEXT    NOT NULL,
    base_branch TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- -------------------------------------------------------------------------
-- findings
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS findings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id             INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    title             TEXT    NOT NULL,
    description       TEXT,
    severity          TEXT    NOT NULL,
    file              TEXT,
    line              INTEGER,
    claim             TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'candidate',
    created_by_agent  TEXT    NOT NULL
);

-- -------------------------------------------------------------------------
-- evidence
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id  INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    type        TEXT    NOT NULL,
    description TEXT,
    file        TEXT,
    line        INTEGER,
    content     TEXT
);

-- -------------------------------------------------------------------------
-- test_executions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_executions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id      INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    test_name       TEXT    NOT NULL,
    test_type       TEXT    NOT NULL,
    command         TEXT,
    expected_result TEXT,
    actual_result   TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    execution_time  REAL
);

-- -------------------------------------------------------------------------
-- patches
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id          INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    diff                TEXT    NOT NULL,
    generated_by        TEXT    NOT NULL,
    verification_status TEXT    NOT NULL DEFAULT 'pending'
);

-- -------------------------------------------------------------------------
-- agent_executions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_executions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT    NOT NULL,
    finding_id    INTEGER REFERENCES findings(id) ON DELETE SET NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    started_at    TEXT,
    completed_at  TEXT,
    summary       TEXT
);
"""

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set to Row."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create all tables if they do not already exist."""
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)


def insert_findings(
    pr_id: int,
    findings: list["CandidateFinding"],
    db_path: Path = DB_PATH,
) -> list[int]:
    """
    Persist a list of CandidateFinding rows linked to pr_id.

    Each finding is inserted with status = 'candidate' and
    created_by_agent = 'investigator'.

    Returns the list of newly inserted row IDs in insertion order.
    """
    row_ids: list[int] = []
    with get_connection(db_path) as conn:
        for f in findings:
            cur = conn.execute(
                """
                INSERT INTO findings
                    (pr_id, title, description, severity, file, line,
                     claim, status, created_by_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', 'investigator')
                """,
                (
                    pr_id,
                    f.title,
                    f.description,   # reasoning summary → description column
                    f.severity,
                    f.file,
                    f.line,
                    f.claim,
                ),
            )
            row_ids.append(cur.lastrowid)
    return row_ids


def get_findings_for_pr(pr_id: int, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    """Return all finding rows for a given pr_id, ordered by id."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM findings WHERE pr_id = ? ORDER BY id",
            (pr_id,),
        ).fetchall()


def get_pr_by_id(pr_id: int, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    """Return the pull_requests row for the given id, or None."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM pull_requests WHERE id = ?",
            (pr_id,),
        ).fetchone()


def get_finding_by_id(finding_id: int, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    """Return the findings row for the given id, or None."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM findings WHERE id = ?",
            (finding_id,),
        ).fetchone()


def update_finding_status(
    finding_id: int,
    status: str,
    db_path: Path = DB_PATH,
) -> None:
    """Update the status column of a single finding row."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE findings SET status = ? WHERE id = ?",
            (status, finding_id),
        )


def insert_test_execution(
    finding_id:      int,
    test_name:       str,
    test_type:       str,          # "reproduction" | "adversarial" | ...
    command:         str,
    expected_result: str,
    actual_result:   str,
    status:          str,          # "pass" | "fail" | "error"
    execution_time:  float | None,
    db_path: Path = DB_PATH,
) -> int:
    """
    Insert a test_executions row and return its new id.
    """
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO test_executions
                (finding_id, test_name, test_type, command,
                 expected_result, actual_result, status, execution_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                test_name,
                test_type,
                command,
                expected_result,
                actual_result,
                status,
                execution_time,
            ),
        )
        return cur.lastrowid
