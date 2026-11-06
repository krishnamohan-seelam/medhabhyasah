"""Parent-zone routes — auth, settings, approval, generation, oversight, profiles."""
import asyncio
import json
import webbrowser

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from medhabhyasah import credentials, model_config
from medhabhyasah.db import (
    create_generation_request,
    create_question,
    create_student,
    delete_generation_request,
    delete_student,
    get_generation_request,
    get_question,
    has_attempts,
    list_generation_requests,
    list_questions,
    update_generation_request_status,
    update_question,
    update_student,
    weak_area_summary,
)

from ._shared import (
    ApiKeyRequest,
    ModelSettingsRequest,
    OpenLinkRequest,
    ChangePinRequest,
    GenerationRequest,
    PinRequest,
    check_pin,
    QuestionUpdateRequest,
    StudentRequest,
    open_db,
    parse_options,
    require_pin,
)

router = APIRouter(tags=["parent"])


# ── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/api/parent/verify-pin")
async def verify_pin(body: PinRequest) -> dict:
    if not check_pin(body.pin):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    return {"ok": True}


# ── Settings ─────────────────────────────────────────────────────────────────

@router.post("/api/parent/settings/apikey")
async def update_apikey(
    body: ApiKeyRequest, pin: None = Depends(require_pin)
) -> dict:
    provider = credentials.store_key_by_prefix(body.api_key)
    model_config.select_provider(provider)
    return {"ok": True, "provider": provider}


@router.get("/api/parent/settings/model")
async def get_model_settings(pin: None = Depends(require_pin)) -> dict:
    selected = model_config.selected_provider() or credentials.configured_provider()
    providers = {}
    for key, info in model_config.PROVIDERS.items():
        cfg = model_config.settings_for(key)
        providers[key] = {
            "name": info["name"],
            "model": cfg.model,
            "input_cost_per_mtok": cfg.input_cost_per_mtok,
            "output_cost_per_mtok": cfg.output_cost_per_mtok,
            "default_model": info["model"],
            "has_key": credentials.has_key_for(key),
            "links": info["links"],
        }
    return {"selected": selected, "providers": providers}


@router.post("/api/parent/settings/model")
async def update_model_settings(
    body: ModelSettingsRequest, pin: None = Depends(require_pin)
) -> dict:
    try:
        model_config.save(
            body.provider, body.model, body.input_cost_per_mtok, body.output_cost_per_mtok
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.post("/api/parent/open-link")
async def open_link(body: OpenLinkRequest, pin: None = Depends(require_pin)) -> dict:
    """Open a provider help page in the default browser. Known links only."""
    if body.url not in model_config.allowed_link_urls():
        raise HTTPException(400, "Unknown link")
    webbrowser.open(body.url)
    return {"ok": True}


@router.post("/api/parent/settings/pin")
async def change_pin(
    body: ChangePinRequest, pin: None = Depends(require_pin)
) -> dict:
    if not check_pin(body.current_pin):
        raise HTTPException(400, "Current PIN is incorrect")
    if body.new_pin != body.confirm_pin:
        raise HTTPException(400, "PINs do not match")
    credentials.store_pin(body.new_pin)
    return {"ok": True}


# ── Question approval ────────────────────────────────────────────────────────

@router.patch("/api/parent/questions/{question_id}")
async def patch_question(
    request: Request, question_id: int,
    body: QuestionUpdateRequest, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        q = get_question(conn, question_id)
        if q is None:
            raise HTTPException(404, "Question not found")
        update_question(
            conn,
            question_id,
            question=body.question,
            options=json.dumps(body.options) if body.options is not None else None,
            answer=str(body.answer) if body.answer is not None else None,
            explanation=body.explanation,
        )
    return {"ok": True}


@router.post("/api/parent/questions/{question_id}/approve")
async def approve_question(
    request: Request, question_id: int, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        q = get_question(conn, question_id)
        if q is None:
            raise HTTPException(404, "Question not found")
        update_question(conn, question_id, status="approved")
    return {"ok": True, "status": "approved"}


@router.post("/api/parent/questions/{question_id}/reject")
async def reject_question(
    request: Request, question_id: int, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        q = get_question(conn, question_id)
        if q is None:
            raise HTTPException(404, "Question not found")
        update_question(conn, question_id, status="rejected")
    return {"ok": True, "status": "rejected"}


@router.post("/api/parent/questions/{question_id}/undo")
async def undo_question(
    request: Request, question_id: int, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        q = get_question(conn, question_id)
        if q is None:
            raise HTTPException(404, "Question not found")
        revert_status = "auto_checked" if q["check_failure"] is None else "draft"
        update_question(conn, question_id, status=revert_status)
    return {"ok": True, "status": revert_status}


# ── Generation requests ──────────────────────────────────────────────────────

@router.get("/api/parent/generation-requests")
async def get_generation_requests(
    request: Request, pin: None = Depends(require_pin),
) -> list:
    with open_db(request.app.state.db_path) as conn:
        return list_generation_requests(conn)


@router.get("/api/parent/generation-requests/{req_id}")
async def get_generation_request_detail(
    request: Request, req_id: int, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        req = get_generation_request(conn, req_id)
    if req is None:
        raise HTTPException(404, "Not found")
    return req


@router.delete("/api/parent/generation-requests/{req_id}")
async def delete_generation_request_route(
    request: Request, req_id: int, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        req = get_generation_request(conn, req_id)
        if req is None:
            raise HTTPException(404, "Generation request not found")
        if req["status"] not in ("pending", "failed"):
            raise HTTPException(400, f"Cannot delete a request with status '{req['status']}'")
        delete_generation_request(conn, req_id)
    return {"ok": True}


@router.post("/api/parent/generation-requests")
async def post_generation_request(
    request: Request, body: GenerationRequest, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        req_id = create_generation_request(
            conn,
            subject=body.subject,
            topic=body.topic,
            grade=body.grade,
            exam=body.exam,
            references_text=body.references_text,
            question_count=body.question_count,
        )
    return {"ok": True, "id": req_id}


@router.post("/api/parent/generation-requests/{req_id}/generate")
async def trigger_generation(
    request: Request, req_id: int, pin: None = Depends(require_pin),
) -> StreamingResponse:
    from medhabhyasah.generation import (
        GenerationFailure,
        ProviderAccessError,
        failure_from,
        generate_questions,
    )
    from medhabhyasah.safety import check_difficulty_distribution, check_question

    db_path = request.app.state.db_path

    with open_db(db_path) as conn:
        req = get_generation_request(conn, req_id)
    if req is None:
        raise HTTPException(404, "Generation request not found")
    if req["status"] not in ("pending", "failed"):
        raise HTTPException(400, f"Request status is '{req['status']}'; cannot re-generate")

    with open_db(db_path) as conn:
        update_generation_request_status(conn, req_id, "generating")

    async def _stream():
        yield "data: {\"step\": \"sending\"}\n\n"
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
            with open_db(db_path) as conn:
                update_generation_request_status(conn, req_id, "failed")
            # Only fixed, safe messages reach the screen. Anything else is
            # classified and its detail goes to the scrubbed log file.
            if isinstance(exc, ProviderAccessError):
                payload = {"error": str(exc), "provider_issue": exc.to_dict()}
            else:
                failure = exc if isinstance(exc, GenerationFailure) else failure_from(exc, "unknown", "unknown")
                payload = {"error": str(failure), "failure_kind": failure.kind}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        yield "data: {\"step\": \"checking\"}\n\n"

        with open_db(db_path) as conn:
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

            dist_warning = check_difficulty_distribution(result.questions)
            update_generation_request_status(
                conn, req_id, "complete", api_cost_usd=result.api_cost_usd
            )

        done_data = {
            "step": "done",
            "question_count": len(result.questions),
            "auto_checked": auto_checked,
            "draft": draft_count,
            "api_cost_usd": result.api_cost_usd,
        }
        if dist_warning:
            done_data["difficulty_warning"] = dist_warning
        yield f"data: {json.dumps(done_data)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/api/parent/generation-requests/{req_id}/questions")
async def get_request_questions(
    request: Request, req_id: int, pin: None = Depends(require_pin),
) -> list:
    with open_db(request.app.state.db_path) as conn:
        rows = list_questions(conn, generation_request_id=req_id)
    for row in rows:
        parse_options(row)
    return rows


# ── Student oversight ────────────────────────────────────────────────────────

@router.get("/api/parent/weak-areas")
async def get_weak_areas(
    request: Request, student_id: int, pin: None = Depends(require_pin),
) -> list:
    with open_db(request.app.state.db_path) as conn:
        return weak_area_summary(conn, student_id)


# ── Student profile management ───────────────────────────────────────────────

@router.post("/api/parent/students")
async def add_student_parent(
    request: Request, body: StudentRequest, pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        sid = create_student(conn, body.nickname, body.grade, body.exam)
    return {"id": sid, "nickname": body.nickname, "grade": body.grade, "exam": body.exam}


@router.patch("/api/parent/students/{student_id}")
async def edit_student_parent(
    request: Request, student_id: int, body: StudentRequest,
    pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        update_student(conn, student_id, body.nickname, body.grade, body.exam)
    return {"id": student_id, "nickname": body.nickname, "grade": body.grade, "exam": body.exam}


@router.delete("/api/parent/students/{student_id}")
async def delete_student_parent(
    request: Request, student_id: int, force: bool = False,
    pin: None = Depends(require_pin),
) -> dict:
    with open_db(request.app.state.db_path) as conn:
        if has_attempts(conn, student_id) and not force:
            raise HTTPException(
                409, "Student has attempt history. Pass ?force=true to confirm deletion."
            )
        delete_student(conn, student_id)
    return {"deleted": student_id}
