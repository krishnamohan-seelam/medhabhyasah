"""Student-facing routes — quiz sessions, progress, mistakes."""
from fastapi import APIRouter, HTTPException, Request

from medhabhyasah.db import (
    create_attempt,
    create_attempt_answer,
    finish_attempt,
    get_attempt_detail,
    get_question,
    list_all_wrong_answers,
    list_approved_questions,
    list_attempts,
    list_students,
    list_topics_with_approved,
)

from ._shared import (
    MODE_DIFFICULTIES,
    MODE_SECONDS_PER_Q,
    PracticeMistakesRequest,
    StartAttemptRequest,
    SubmitAttemptRequest,
    open_db,
    parse_options,
)

router = APIRouter(tags=["student"])


@router.get("/api/students")
async def get_students(request: Request) -> list:
    with open_db(request.app.state.db_path) as conn:
        return list_students(conn)


@router.get("/api/student/questions")
async def get_student_questions(
    request: Request,
    generation_request_id: int | None = None,
    subject: str | None = None,
) -> list:
    with open_db(request.app.state.db_path) as conn:
        rows = list_approved_questions(
            conn,
            generation_request_id=generation_request_id,
            subject=subject,
        )
    for row in rows:
        parse_options(row)
        # Never send answers before the attempt is submitted.
        for secret in ("answer", "explanation", "source_quote"):
            row.pop(secret, None)
    return rows


@router.get("/api/student/topics")
async def get_student_topics(request: Request, subject: str | None = None) -> list:
    with open_db(request.app.state.db_path) as conn:
        return list_topics_with_approved(conn, subject=subject)


@router.post("/api/student/attempts")
async def start_attempt(request: Request, body: StartAttemptRequest) -> dict:
    import random

    with open_db(request.app.state.db_path) as conn:
        pool = list_approved_questions(conn, generation_request_id=body.generation_request_id)

        allowed = MODE_DIFFICULTIES[body.mode]
        filtered = [q for q in pool if q.get("difficulty") in allowed]
        if len(filtered) < body.question_count:
            raise HTTPException(400, f"Only {len(filtered)} questions available for this mode")

        random.shuffle(filtered)
        selected = filtered[: body.question_count]

        secs_per_q = MODE_SECONDS_PER_Q[body.mode]
        time_limit = None if secs_per_q is None else secs_per_q * body.question_count

        attempt_id = create_attempt(
            conn,
            student_id=body.student_id,
            generation_request_id=body.generation_request_id,
            time_limit_seconds=time_limit,
        )

    quiz_questions = []
    for q in selected:
        parse_options(q)
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


@router.post("/api/student/attempts/{attempt_id}/submit")
async def submit_attempt(
    request: Request, attempt_id: int, body: SubmitAttemptRequest
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        detail = get_attempt_detail(conn, attempt_id)
        if detail is None:
            raise HTTPException(404, "Attempt not found")
        if detail["finished_at"] is not None:
            raise HTTPException(400, "Attempt already submitted")

        score = 0
        breakdown = []
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
            parse_options(q)
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

    return {
        "attempt_id": attempt_id,
        "score": score,
        "total": total,
        "grade": grade,
        "pct": round(pct, 1),
        "breakdown": breakdown,
    }


@router.get("/api/student/attempts")
async def get_student_attempts(request: Request, student_id: int) -> list:
    with open_db(request.app.state.db_path) as conn:
        return list_attempts(conn, student_id=student_id)


@router.get("/api/student/mistakes")
async def get_student_mistakes(request: Request, student_id: int) -> list:
    with open_db(request.app.state.db_path) as conn:
        rows = list_all_wrong_answers(conn, student_id)
    for r in rows:
        parse_options(r)
    return rows


@router.post("/api/student/practice-mistakes")
async def create_practice_mistakes(request: Request, body: PracticeMistakesRequest) -> dict:
    with open_db(request.app.state.db_path) as conn:
        detail = get_attempt_detail(conn, body.attempt_id)
        if detail is None:
            raise HTTPException(404, "Attempt not found")
        if detail["student_id"] != body.student_id:
            raise HTTPException(403, "Not your attempt")
        wrong = [a for a in detail["answers"] if not a["is_correct"]]
        if not wrong:
            raise HTTPException(400, "No wrong answers in this attempt")
        attempt_id = create_attempt(
            conn,
            student_id=body.student_id,
            generation_request_id=detail["generation_request_id"],
            time_limit_seconds=None,
        )
    questions = []
    for a in wrong:
        q = dict(a)
        parse_options(q)
        questions.append({
            "id": q["question_id"],
            "question": q["question"],
            "options": q["options"],
            "difficulty": q["difficulty"],
        })
    return {"attempt_id": attempt_id, "time_limit_seconds": None, "questions": questions}
