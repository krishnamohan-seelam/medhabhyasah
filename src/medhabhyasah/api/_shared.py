"""Shared models, dependencies, and helpers used across API routers."""
import json
from contextlib import contextmanager
from pathlib import Path

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from medhabhyasah import credentials
from medhabhyasah.db import create_schema, get_connection

# ── Constants ────────────────────────────────────────────────────────────────

SUBJECTS = {"Science", "Maths", "Social Studies", "English"}

MODE_SECONDS_PER_Q: dict[str, int | None] = {
    "practice": None,
    "challenge": 90,
    "exam": 60,
}
MODE_DIFFICULTIES: dict[str, set[str]] = {
    "practice": {"Easy"},
    "challenge": {"Medium", "Hard"},
    "exam": {"Easy", "Medium", "Hard"},
}


# ── DB helpers ───────────────────────────────────────────────────────────────

@contextmanager
def open_db(db_path: Path | None):
    """Open a DB connection, ensure schema exists, and close on exit."""
    conn = get_connection(db_path)
    create_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_db_path(request: Request) -> Path | None:
    return request.app.state.db_path


# ── Auth dependency ──────────────────────────────────────────────────────────

def require_pin(x_parent_pin: str = Header(default="", alias="X-Parent-Pin")) -> None:
    if not x_parent_pin or not credentials.verify_pin(x_parent_pin):
        raise HTTPException(status_code=401, detail="Invalid or missing PIN")


# ── Response helpers ─────────────────────────────────────────────────────────

def parse_options(row: dict) -> dict:
    try:
        row["options"] = json.loads(row["options"])
    except (json.JSONDecodeError, TypeError):
        row["options"] = []
    try:
        row["answer"] = int(row["answer"])
    except (ValueError, TypeError):
        pass
    return row


# ── Request/response models ─────────────────────────────────────────────────

class PinRequest(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_digits(cls, v: str) -> str:
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise ValueError("PIN must be 4–8 digits")
        return v


class ApiKeyRequest(BaseModel):
    api_key: str

    @field_validator("api_key")
    @classmethod
    def key_format(cls, v: str) -> str:
        if not (v.startswith("sk-ant-") or v.startswith("AIza")):
            raise ValueError("API key must start with sk-ant- (Anthropic) or AIza (Google Gemini)")
        return v


class StudentRequest(BaseModel):
    nickname: str
    grade: str
    exam: str

    @field_validator("nickname", "grade", "exam")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v.strip()


class StartAttemptRequest(BaseModel):
    student_id: int
    generation_request_id: int
    mode: str
    question_count: int

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        if v not in MODE_SECONDS_PER_Q:
            raise ValueError("mode must be practice, challenge, or exam")
        return v

    @field_validator("question_count")
    @classmethod
    def valid_count(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("question_count must be 1–50")
        return v


class SubmitAnswerItem(BaseModel):
    question_id: int
    chosen_option: int | None = None


class SubmitAttemptRequest(BaseModel):
    answers: list[SubmitAnswerItem]


class QuestionUpdateRequest(BaseModel):
    question: str | None = None
    options: list[str] | None = None
    answer: int | None = None
    explanation: str | None = None

    @field_validator("options")
    @classmethod
    def valid_options(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) != 4:
            raise ValueError("options must have exactly 4 items")
        return v

    @field_validator("answer")
    @classmethod
    def valid_answer(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3):
            raise ValueError("answer must be 0, 1, 2, or 3")
        return v


class PracticeMistakesRequest(BaseModel):
    student_id: int
    attempt_id: int


class ChangePinRequest(BaseModel):
    current_pin: str
    new_pin: str
    confirm_pin: str

    @field_validator("current_pin", "new_pin", "confirm_pin")
    @classmethod
    def pin_digits(cls, v: str) -> str:
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise ValueError("PIN must be 4–8 digits")
        return v


class GenerationRequest(BaseModel):
    subject: str
    topic: str
    grade: str
    exam: str
    references_text: str = ""
    question_count: int

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, v: str) -> str:
        if v not in SUBJECTS:
            raise ValueError(f"subject must be one of {sorted(SUBJECTS)}")
        return v

    @field_validator("topic", "grade", "exam")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v.strip()

    @field_validator("question_count")
    @classmethod
    def valid_count(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("question_count must be 1–50")
        return v
