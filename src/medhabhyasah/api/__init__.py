"""Local FastAPI routes for student and parent screens."""
import asyncio
import json
import mimetypes
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from medhabhyasah import credentials
from medhabhyasah.db import (
    count_students,
    create_attempt,
    create_attempt_answer,
    create_generation_request,
    create_question,
    create_schema,
    create_student,
    delete_generation_request,
    delete_student,
    finish_attempt,
    get_attempt_detail,
    get_connection,
    get_generation_request,
    get_question,
    has_attempts,
    list_all_wrong_answers,
    list_approved_questions,
    list_attempts,
    list_generation_requests,
    list_questions,
    list_students,
    list_topics_with_approved,
    update_generation_request_status,
    update_question,
    update_student,
    weak_area_summary,
)

# Ensure correct MIME type for woff2 fonts (not always registered on Windows)
mimetypes.add_type("font/woff2", ".woff2")

_WEB_DIR = Path(__file__).parent.parent / "web"
_STATIC_DIR = _WEB_DIR / "static"
_INDEX_PATH = _WEB_DIR / "index.html"

_SUBJECTS = {"Science", "Maths", "Social Studies", "English"}


# ── Request/response models ───────────────────────────────────────────────────

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


_MODE_SECONDS_PER_Q: dict[str, int | None] = {
    "practice": None,
    "challenge": 90,
    "exam": 60,
}
_MODE_DIFFICULTIES: dict[str, set[str]] = {
    "practice": {"Easy"},
    "challenge": {"Medium", "Hard"},
    "exam": {"Easy", "Medium", "Hard"},
}


class StartAttemptRequest(BaseModel):
    student_id: int
    generation_request_id: int
    mode: str
    question_count: int

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        if v not in _MODE_SECONDS_PER_Q:
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
    new_pin: str
    confirm_pin: str

    @field_validator("new_pin", "confirm_pin")
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
        if v not in _SUBJECTS:
            raise ValueError(f"subject must be one of {sorted(_SUBJECTS)}")
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


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Medhabhyasah")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    def _conn():
        conn = get_connection(db_path)
        create_schema(conn)
        return conn

    def _require_pin(x_parent_pin: str = Header(default="", alias="X-Parent-Pin")) -> str:
        if not x_parent_pin or not credentials.verify_pin(x_parent_pin):
            raise HTTPException(status_code=401, detail="Invalid or missing PIN")
        return x_parent_pin

    # ── Static page ───────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return _INDEX_PATH.read_text(encoding="utf-8")

    # ── Setup API ─────────────────────────────────────────────────────────────

    @app.get("/api/setup/status")
    async def setup_status() -> dict:
        conn = _conn()
        needs = count_students(conn) == 0
        conn.close()
        return {
            "needs_setup": needs,
            "configured_provider": credentials.configured_provider(),
        }

    @app.post("/api/setup/pin")
    async def setup_pin(body: PinRequest) -> dict:
        credentials.store_pin(body.pin)
        return {"ok": True}

    @app.post("/api/setup/apikey")
    async def setup_apikey(body: ApiKeyRequest) -> dict:
        key = body.api_key
        if key.startswith("sk-ant-"):
            credentials.store_api_key(key)
        else:
            credentials.store_gemini_key(key)
        return {"ok": True, "provider": "anthropic" if key.startswith("sk-ant-") else "gemini"}

    @app.post("/api/setup/student")
    async def setup_student(body: StudentRequest) -> dict:
        conn = _conn()
        student_id = create_student(conn, body.nickname, body.grade, body.exam)
        conn.close()
        return {"ok": True, "id": student_id}

    # ── Student API ───────────────────────────────────────────────────────────

    @app.get("/api/students")
    async def get_students() -> list:
        conn = _conn()
        students = list_students(conn)
        conn.close()
        return students

    # ── Parent auth ───────────────────────────────────────────────────────────

    @app.post("/api/parent/verify-pin")
    async def verify_pin(body: PinRequest) -> dict:
        if not credentials.verify_pin(body.pin):
            raise HTTPException(status_code=401, detail="Incorrect PIN")
        return {"ok": True}

    # ── Parent: settings ─────────────────────────────────────────────────────

    @app.post("/api/parent/settings/apikey")
    async def update_apikey(
        body: ApiKeyRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        key = body.api_key
        if key.startswith("sk-ant-"):
            credentials.store_api_key(key)
        else:
            credentials.store_gemini_key(key)
        return {"ok": True, "provider": "anthropic" if key.startswith("sk-ant-") else "gemini"}

    # ── Parent: question approval ─────────────────────────────────────────────

    def _parse_options(row: dict) -> dict:
        try:
            row["options"] = json.loads(row["options"])
        except (json.JSONDecodeError, TypeError):
            row["options"] = []
        try:
            row["answer"] = int(row["answer"])
        except (ValueError, TypeError):
            pass
        return row

    @app.patch("/api/parent/questions/{question_id}")
    async def patch_question(
        question_id: int, body: QuestionUpdateRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        q = get_question(conn, question_id)
        conn.close()
        if q is None:
            raise HTTPException(404, "Question not found")
        conn = _conn()
        update_question(
            conn,
            question_id,
            question=body.question,
            options=json.dumps(body.options) if body.options is not None else None,
            answer=str(body.answer) if body.answer is not None else None,
            explanation=body.explanation,
        )
        conn.close()
        return {"ok": True}

    @app.post("/api/parent/questions/{question_id}/approve")
    async def approve_question(
        question_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        q = get_question(conn, question_id)
        conn.close()
        if q is None:
            raise HTTPException(404, "Question not found")
        conn = _conn()
        update_question(conn, question_id, status="approved")
        conn.close()
        return {"ok": True, "status": "approved"}

    @app.post("/api/parent/questions/{question_id}/reject")
    async def reject_question(
        question_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        q = get_question(conn, question_id)
        conn.close()
        if q is None:
            raise HTTPException(404, "Question not found")
        conn = _conn()
        update_question(conn, question_id, status="rejected")
        conn.close()
        return {"ok": True, "status": "rejected"}

    @app.post("/api/parent/questions/{question_id}/undo")
    async def undo_question(
        question_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        q = get_question(conn, question_id)
        conn.close()
        if q is None:
            raise HTTPException(404, "Question not found")
        # Revert to auto_checked if it passed safety, otherwise draft
        conn = _conn()
        q2 = get_question(conn, question_id)
        conn.close()
        revert_status = "auto_checked" if q2["check_failure"] is None else "draft"
        conn = _conn()
        update_question(conn, question_id, status=revert_status)
        conn.close()
        return {"ok": True, "status": revert_status}

    # ── Student: questions (approved only) ────────────────────────────────────

    @app.get("/api/student/questions")
    async def get_student_questions(
        generation_request_id: int | None = None,
        subject: str | None = None,
    ) -> list:
        conn = _conn()
        rows = list_approved_questions(
            conn,
            generation_request_id=generation_request_id,
            subject=subject,
        )
        conn.close()
        for row in rows:
            _parse_options(row)
        return rows

    @app.get("/api/student/topics")
    async def get_student_topics(subject: str | None = None) -> list:
        conn = _conn()
        rows = list_topics_with_approved(conn, subject=subject)
        conn.close()
        return rows

    @app.post("/api/student/attempts")
    async def start_attempt(body: StartAttemptRequest) -> dict:
        import random
        conn = _conn()
        pool = list_approved_questions(conn, generation_request_id=body.generation_request_id)
        conn.close()

        allowed = _MODE_DIFFICULTIES[body.mode]
        filtered = [q for q in pool if q.get("difficulty") in allowed]
        if len(filtered) < body.question_count:
            raise HTTPException(400, f"Only {len(filtered)} questions available for this mode")

        random.shuffle(filtered)
        selected = filtered[: body.question_count]

        secs_per_q = _MODE_SECONDS_PER_Q[body.mode]
        time_limit = None if secs_per_q is None else secs_per_q * body.question_count

        conn = _conn()
        attempt_id = create_attempt(
            conn,
            student_id=body.student_id,
            generation_request_id=body.generation_request_id,
            time_limit_seconds=time_limit,
        )
        conn.close()

        quiz_questions = []
        for q in selected:
            _parse_options(q)
            quiz_questions.append({
                "id": q["id"],
                "question": q["question"],
                "options": q["options"],
                "difficulty": q["difficulty"],
            })

        return {
            "attempt_id": attempt_id,
            "time_limit_seconds": time_limit,
            "questions": quiz_questions,
        }

    @app.post("/api/student/attempts/{attempt_id}/submit")
    async def submit_attempt(
        attempt_id: int, body: SubmitAttemptRequest
    ) -> dict:
        conn = _conn()
        detail = get_attempt_detail(conn, attempt_id)
        conn.close()
        if detail is None:
            raise HTTPException(404, "Attempt not found")
        if detail["finished_at"] is not None:
            raise HTTPException(400, "Attempt already submitted")

        score = 0
        breakdown = []
        conn = _conn()
        for item in body.answers:
            q = get_question(conn, item.question_id)
            if q is None:
                continue
            correct_answer = str(q["answer"])
            is_correct = (
                item.chosen_option is not None
                and str(item.chosen_option) == correct_answer
            )
            if is_correct:
                score += 1
            create_attempt_answer(
                conn,
                attempt_id=attempt_id,
                question_id=item.question_id,
                chosen_option=item.chosen_option,
                is_correct=is_correct,
            )
            _parse_options(q)
            breakdown.append({
                "question_id": item.question_id,
                "question": q["question"],
                "options": q["options"],
                "chosen_option": item.chosen_option,
                "correct_answer": int(correct_answer) if correct_answer.isdigit() else correct_answer,
                "explanation": q["explanation"],
                "is_correct": is_correct,
                "difficulty": q["difficulty"],
            })

        total = len(body.answers)
        pct = (score / total * 100) if total > 0 else 0
        grade = "A" if pct >= 80 else "B" if pct >= 60 else "C" if pct >= 40 else "D"
        finish_attempt(conn, attempt_id, score=score, grade=grade)
        conn.close()

        return {
            "attempt_id": attempt_id,
            "score": score,
            "total": total,
            "grade": grade,
            "pct": round(pct, 1),
            "breakdown": breakdown,
        }

    @app.get("/api/student/attempts")
    async def get_student_attempts(student_id: int) -> list:
        conn = _conn()
        rows = list_attempts(conn, student_id=student_id)
        conn.close()
        return rows

    @app.get("/api/student/mistakes")
    async def get_student_mistakes(student_id: int) -> list:
        conn = _conn()
        rows = list_all_wrong_answers(conn, student_id)
        conn.close()
        for r in rows:
            _parse_options(r)
        return rows

    @app.post("/api/student/practice-mistakes")
    async def create_practice_mistakes(body: PracticeMistakesRequest) -> dict:
        conn = _conn()
        detail = get_attempt_detail(conn, body.attempt_id)
        if detail is None:
            conn.close()
            raise HTTPException(404, "Attempt not found")
        if detail["student_id"] != body.student_id:
            conn.close()
            raise HTTPException(403, "Not your attempt")
        wrong = [a for a in detail["answers"] if not a["is_correct"]]
        if not wrong:
            conn.close()
            raise HTTPException(400, "No wrong answers in this attempt")
        attempt_id = create_attempt(
            conn,
            student_id=body.student_id,
            generation_request_id=detail["generation_request_id"],
            time_limit_seconds=None,
        )
        conn.close()
        questions = []
        for a in wrong:
            q = dict(a)
            _parse_options(q)
            questions.append({
                "id": q["question_id"],
                "question": q["question"],
                "options": q["options"],
                "difficulty": q["difficulty"],
            })
        return {"attempt_id": attempt_id, "time_limit_seconds": None, "questions": questions}

    # ── Parent: student oversight (issue 07) ──────────────────────────────────

    @app.get("/api/parent/weak-areas")
    async def get_weak_areas(student_id: int, pin: str = Depends(_require_pin)) -> list:
        conn = _conn()
        rows = weak_area_summary(conn, student_id)
        conn.close()
        return rows

    # ── Parent: student profile management (issue 08) ─────────────────────────

    @app.post("/api/parent/students")
    async def add_student_parent(
        body: StudentRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        sid = create_student(conn, body.nickname, body.grade, body.exam)
        conn.close()
        return {"id": sid, "nickname": body.nickname, "grade": body.grade, "exam": body.exam}

    @app.patch("/api/parent/students/{student_id}")
    async def edit_student_parent(
        student_id: int, body: StudentRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        update_student(conn, student_id, body.nickname, body.grade, body.exam)
        conn.close()
        return {"id": student_id, "nickname": body.nickname, "grade": body.grade, "exam": body.exam}

    @app.delete("/api/parent/students/{student_id}")
    async def delete_student_parent(
        student_id: int, force: bool = False, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        if has_attempts(conn, student_id) and not force:
            conn.close()
            raise HTTPException(
                409, "Student has attempt history. Pass ?force=true to confirm deletion."
            )
        delete_student(conn, student_id)
        conn.close()
        return {"deleted": student_id}

    @app.post("/api/parent/settings/pin")
    async def change_pin(
        body: ChangePinRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        if body.new_pin != body.confirm_pin:
            raise HTTPException(400, "PINs do not match")
        credentials.store_pin(body.new_pin)
        return {"ok": True}

    # ── Parent: generation requests ───────────────────────────────────────────

    @app.get("/api/parent/generation-requests")
    async def get_generation_requests(pin: str = Depends(_require_pin)) -> list:
        conn = _conn()
        reqs = list_generation_requests(conn)
        conn.close()
        return reqs

    @app.get("/api/parent/generation-requests/{req_id}")
    async def get_generation_request_detail(
        req_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        req = get_generation_request(conn, req_id)
        conn.close()
        if req is None:
            raise HTTPException(404, "Not found")
        return req

    @app.delete("/api/parent/generation-requests/{req_id}")
    async def delete_generation_request_route(
        req_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        req = get_generation_request(conn, req_id)
        conn.close()
        if req is None:
            raise HTTPException(404, "Generation request not found")
        if req["status"] not in ("pending", "failed"):
            raise HTTPException(400, f"Cannot delete a request with status '{req['status']}'")
        conn = _conn()
        delete_generation_request(conn, req_id)
        conn.close()
        return {"ok": True}

    @app.post("/api/parent/generation-requests")
    async def post_generation_request(
        body: GenerationRequest, pin: str = Depends(_require_pin)
    ) -> dict:
        conn = _conn()
        req_id = create_generation_request(
            conn,
            subject=body.subject,
            topic=body.topic,
            grade=body.grade,
            exam=body.exam,
            references_text=body.references_text,
            question_count=body.question_count,
        )
        conn.close()
        return {"ok": True, "id": req_id}

    @app.post("/api/parent/generation-requests/{req_id}/generate")
    async def trigger_generation(
        req_id: int, pin: str = Depends(_require_pin)
    ) -> dict:
        # Import here — generation is parent-zone only; never at module level
        from medhabhyasah.generation import generate_questions
        from medhabhyasah.safety import check_question

        conn = _conn()
        req = get_generation_request(conn, req_id)
        conn.close()
        if req is None:
            raise HTTPException(404, "Generation request not found")
        if req["status"] not in ("pending", "failed"):
            raise HTTPException(400, f"Request status is '{req['status']}'; cannot re-generate")

        conn = _conn()
        update_generation_request_status(conn, req_id, "generating")
        conn.close()

        try:
            result = await asyncio.to_thread(
                generate_questions,
                subject=req["subject"],
                topic=req["topic"],
                grade=req["grade"],
                exam=req["exam"],
                references_text=req["references_text"] or "",
                question_count=req["question_count"],
            )
        except Exception as exc:
            conn = _conn()
            update_generation_request_status(conn, req_id, "failed")
            conn.close()
            raise HTTPException(502, f"Generation failed: {exc}") from exc

        conn = _conn()
        auto_checked = 0
        draft_count = 0
        for q in result.questions:
            check = check_question(q, req["subject"])
            status = "auto_checked" if check.passed else "draft"
            create_question(
                conn,
                generation_request_id=req_id,
                difficulty=q.get("difficulty", ""),
                type_=q.get("type", "mcq"),
                question=q.get("question", ""),
                options=json.dumps(q.get("options", [])),
                answer=str(q.get("answer", "")),
                explanation=q.get("explanation", ""),
                source_quote=q.get("source_quote", ""),
                status=status,
                check_failure=check.failure,
            )
            if check.passed:
                auto_checked += 1
            else:
                draft_count += 1

        update_generation_request_status(
            conn, req_id, "complete", api_cost_usd=result.api_cost_usd
        )
        conn.close()

        return {
            "ok": True,
            "question_count": len(result.questions),
            "auto_checked": auto_checked,
            "draft": draft_count,
            "api_cost_usd": result.api_cost_usd,
        }

    @app.get("/api/parent/generation-requests/{req_id}/questions")
    async def get_request_questions(
        req_id: int, pin: str = Depends(_require_pin)
    ) -> list:
        conn = _conn()
        rows = list_questions(conn, generation_request_id=req_id)
        conn.close()
        for row in rows:
            _parse_options(row)
        return rows

    return app
