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


# ── Schema ────────────────────────────────────────────────────────────────────

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
            subject         TEXT    NOT NULL DEFAULT '',
            topic           TEXT    NOT NULL,
            grade           TEXT    NOT NULL,
            exam            TEXT    NOT NULL,
            references_text TEXT    NOT NULL DEFAULT '',
            question_count  INTEGER NOT NULL,
            api_cost_usd    REAL,
            status          TEXT    NOT NULL DEFAULT 'pending',
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
            check_failure         TEXT,
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
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after initial schema, idempotently."""
    gen_cols = {r[1] for r in conn.execute("PRAGMA table_info(generation_requests)")}
    if "subject" not in gen_cols:
        conn.execute("ALTER TABLE generation_requests ADD COLUMN subject TEXT NOT NULL DEFAULT ''")
    if "api_cost_usd" not in gen_cols:
        conn.execute("ALTER TABLE generation_requests ADD COLUMN api_cost_usd REAL")
    if "status" not in gen_cols:
        conn.execute("ALTER TABLE generation_requests ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")

    q_cols = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    if "check_failure" not in q_cols:
        conn.execute("ALTER TABLE questions ADD COLUMN check_failure TEXT")


# ── Students ──────────────────────────────────────────────────────────────────

def count_students(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]


def create_student(
    conn: sqlite3.Connection, nickname: str, grade: str, exam: str
) -> int:
    cur = conn.execute(
        "INSERT INTO students (nickname, grade, exam) VALUES (?, ?, ?)",
        (nickname, grade, exam),
    )
    conn.commit()
    return cur.lastrowid


def list_students(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, nickname, grade, exam, created_at FROM students"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_student(conn: sqlite3.Connection, student_id: int) -> None:
    conn.execute("DELETE FROM attempt_answers WHERE attempt_id IN "
                 "(SELECT id FROM attempts WHERE student_id = ?)", (student_id,))
    conn.execute("DELETE FROM attempts WHERE student_id = ?", (student_id,))
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()


def update_student(
    conn: sqlite3.Connection, student_id: int, nickname: str, grade: str, exam: str
) -> None:
    conn.execute(
        "UPDATE students SET nickname=?, grade=?, exam=? WHERE id=?",
        (nickname, grade, exam, student_id),
    )
    conn.commit()


# ── Generation requests ───────────────────────────────────────────────────────

def create_generation_request(
    conn: sqlite3.Connection,
    subject: str,
    topic: str,
    grade: str,
    exam: str,
    references_text: str,
    question_count: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO generation_requests "
        "(subject, topic, grade, exam, references_text, question_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (subject, topic, grade, exam, references_text, question_count),
    )
    conn.commit()
    return cur.lastrowid


def list_generation_requests(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, subject, topic, grade, exam, references_text, "
        "question_count, api_cost_usd, status, created_at "
        "FROM generation_requests ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_generation_request(conn: sqlite3.Connection, req_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, subject, topic, grade, exam, references_text, "
        "question_count, api_cost_usd, status, created_at "
        "FROM generation_requests WHERE id = ?",
        (req_id,),
    ).fetchone()
    return dict(row) if row else None


def update_generation_request_status(
    conn: sqlite3.Connection, req_id: int, status: str, api_cost_usd: float | None = None
) -> None:
    if api_cost_usd is not None:
        conn.execute(
            "UPDATE generation_requests SET status=?, api_cost_usd=? WHERE id=?",
            (status, api_cost_usd, req_id),
        )
    else:
        conn.execute(
            "UPDATE generation_requests SET status=? WHERE id=?",
            (status, req_id),
        )
    conn.commit()


# ── Questions ─────────────────────────────────────────────────────────────────

def create_question(
    conn: sqlite3.Connection,
    generation_request_id: int,
    difficulty: str,
    type_: str,
    question: str,
    options: str,
    answer: str,
    explanation: str = "",
    source_quote: str = "",
    status: str = "draft",
    check_failure: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO questions "
        "(generation_request_id, difficulty, type, question, options, answer, "
        " explanation, source_quote, status, check_failure) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (generation_request_id, difficulty, type_, question, options, answer,
         explanation, source_quote, status, check_failure),
    )
    conn.commit()
    return cur.lastrowid


def list_questions(
    conn: sqlite3.Connection,
    generation_request_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    sql = (
        "SELECT id, generation_request_id, difficulty, type, question, options, "
        "answer, explanation, source_quote, status, check_failure, created_at "
        "FROM questions WHERE 1=1"
    )
    params: list = []
    if generation_request_id is not None:
        sql += " AND generation_request_id = ?"
        params.append(generation_request_id)
    if status is not None:
        sql += " AND status = ?"
        params.append(status)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def update_question(
    conn: sqlite3.Connection,
    question_id: int,
    *,
    question: str | None = None,
    options: str | None = None,
    answer: str | None = None,
    explanation: str | None = None,
    status: str | None = None,
) -> None:
    sets, params = [], []
    if question  is not None: sets.append("question=?");     params.append(question)
    if options   is not None: sets.append("options=?");      params.append(options)
    if answer    is not None: sets.append("answer=?");       params.append(answer)
    if explanation is not None: sets.append("explanation=?"); params.append(explanation)
    if status    is not None: sets.append("status=?");       params.append(status)
    if not sets:
        return
    params.append(question_id)
    conn.execute(f"UPDATE questions SET {','.join(sets)} WHERE id=?", params)
    conn.commit()


# ── Attempts ──────────────────────────────────────────────────────────────────

def create_attempt(
    conn: sqlite3.Connection,
    student_id: int,
    generation_request_id: int,
    time_limit_seconds: int | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO attempts (student_id, generation_request_id, time_limit_seconds) "
        "VALUES (?, ?, ?)",
        (student_id, generation_request_id, time_limit_seconds),
    )
    conn.commit()
    return cur.lastrowid


def finish_attempt(
    conn: sqlite3.Connection, attempt_id: int, score: int, grade: str
) -> None:
    conn.execute(
        "UPDATE attempts SET score=?, grade=?, finished_at=datetime('now') WHERE id=?",
        (score, grade, attempt_id),
    )
    conn.commit()


def create_attempt_answer(
    conn: sqlite3.Connection,
    attempt_id: int,
    question_id: int,
    chosen_option: str | None,
    is_correct: bool,
) -> int:
    cur = conn.execute(
        "INSERT INTO attempt_answers (attempt_id, question_id, chosen_option, is_correct) "
        "VALUES (?, ?, ?, ?)",
        (attempt_id, question_id, chosen_option, int(is_correct)),
    )
    conn.commit()
    return cur.lastrowid


def list_attempts(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.student_id, a.generation_request_id, a.time_limit_seconds, "
        "a.score, a.grade, a.started_at, a.finished_at, "
        "gr.topic, gr.subject "
        "FROM attempts a JOIN generation_requests gr ON a.generation_request_id = gr.id "
        "WHERE a.student_id = ? ORDER BY a.started_at DESC",
        (student_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_wrong_answers(conn: sqlite3.Connection, attempt_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT aa.question_id, aa.chosen_option, q.question, q.options, "
        "q.answer, q.explanation, q.difficulty "
        "FROM attempt_answers aa JOIN questions q ON aa.question_id = q.id "
        "WHERE aa.attempt_id = ? AND aa.is_correct = 0",
        (attempt_id,),
    ).fetchall()
    return [dict(r) for r in rows]
