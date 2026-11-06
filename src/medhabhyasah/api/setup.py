"""Setup wizard routes — first-run PIN, API key, and first student."""
from fastapi import APIRouter, Request

from medhabhyasah import credentials, model_config
from medhabhyasah.db import count_students, create_student

from ._shared import ApiKeyRequest, PinRequest, StudentRequest, open_db

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status")
async def setup_status(request: Request) -> dict:
    with open_db(request.app.state.db_path) as conn:
        needs = count_students(conn) == 0
    return {
        "needs_setup": needs,
        "configured_provider": model_config.selected_provider() or credentials.configured_provider(),
    }


@router.post("/pin")
async def setup_pin(body: PinRequest) -> dict:
    credentials.store_pin(body.pin)
    return {"ok": True}


@router.post("/apikey")
async def setup_apikey(body: ApiKeyRequest) -> dict:
    provider = credentials.store_key_by_prefix(body.api_key)
    return {"ok": True, "provider": provider}


@router.post("/student")
async def setup_student(request: Request, body: StudentRequest) -> dict:
    with open_db(request.app.state.db_path) as conn:
        student_id = create_student(conn, body.nickname, body.grade, body.exam)
    return {"ok": True, "id": student_id}
