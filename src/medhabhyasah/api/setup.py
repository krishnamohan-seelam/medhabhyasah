"""Setup wizard routes — first-run PIN, API key, and first student."""
from fastapi import APIRouter, HTTPException, Request

from medhabhyasah import credentials, model_config
from medhabhyasah.db import create_student, is_setup_complete, mark_setup_complete

from ._shared import ApiKeyRequest, PinRequest, StudentRequest, open_db

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status")
async def setup_status(request: Request) -> dict:
    with open_db(request.app.state.db_path) as conn:
        needs = not is_setup_complete(conn)
    return {
        "needs_setup": needs,
        "configured_provider": model_config.selected_provider() or credentials.configured_provider(),
    }


def _require_first_run(request: Request) -> None:
    """Setup routes carry no PIN, so they work only until first-run setup is done."""
    with open_db(request.app.state.db_path) as conn:
        if is_setup_complete(conn):
            raise HTTPException(
                403, "Setup is already complete. Change settings from the parent dashboard."
            )


@router.post("/pin")
async def setup_pin(request: Request, body: PinRequest) -> dict:
    _require_first_run(request)
    credentials.store_pin(body.pin)
    return {"ok": True}


@router.post("/apikey")
async def setup_apikey(request: Request, body: ApiKeyRequest) -> dict:
    _require_first_run(request)
    provider = credentials.store_key_by_prefix(body.api_key)
    return {"ok": True, "provider": provider}


@router.post("/student")
async def setup_student(request: Request, body: StudentRequest) -> dict:
    _require_first_run(request)
    with open_db(request.app.state.db_path) as conn:
        student_id = create_student(conn, body.nickname, body.grade, body.exam)
        mark_setup_complete(conn)
    return {"ok": True, "id": student_id}
