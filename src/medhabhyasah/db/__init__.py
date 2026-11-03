"""SQLite schema and data access."""
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    data_dir = Path.home() / ".medhabhyasah"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "medhabhyasah.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname    TEXT    NOT NULL,
            grade       TEXT    NOT NULL,
            exam        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS generation_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic           TEXT    NOT NULL,
            grade           TEXT    NOT NULL,
            exam            TEXT    NOT NULL,
            references_text TEXT    NOT NULL DEFAULT '',
            question_count  INTEGER NOT NULL,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS questions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_request_id INTEGER NOT NULL REFERENCES generation_requests(id),
            difficulty            TEXT    NOT NULL,
            type                  TEXT    NOT NULL,
            question              TEXT    NOT NULL,
            options               TEXT    NOT NULL,
            answer                TEXT    NOT NULL,
            explanation           TEXT    NOT NULL DEFAULT '',
            source_quote          TEXT    NOT NULL DEFAULT '',
            status                TEXT    NOT NULL DEFAULT 'draft',
            created_at            TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id            INTEGER NOT NULL REFERENCES students(id),
            generation_request_id INTEGER NOT NULL REFERENCES generation_requests(id),
            time_limit_seconds    INTEGER,
            score                 INTEGER,
            grade                 TEXT,
            started_at            TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at           TEXT
        );

        CREATE TABLE IF NOT EXISTS attempt_answers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id     INTEGER NOT NULL REFERENCES attempts(id),
            question_id    INTEGER NOT NULL REFERENCES questions(id),
            chosen_option  TEXT,
            is_correct     INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
