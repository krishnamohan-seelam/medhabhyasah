"""App factory — creates the FastAPI app and includes all routers."""
import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

mimetypes.add_type("font/woff2", ".woff2")

_WEB_DIR = Path(__file__).parent.parent / "web"
_STATIC_DIR = _WEB_DIR / "static"
_INDEX_PATH = _WEB_DIR / "index.html"


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Medhabhyasah")
    app.state.db_path = db_path

    # Refuse any Host other than this machine. Blocks DNS rebinding, where a
    # web page makes the browser talk to this local server under its own name.
    hosts = ["127.0.0.1", "localhost"]
    hosts += [h for h in os.environ.get("MEDHABHYASAH_EXTRA_ALLOWED_HOSTS", "").split(",") if h]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    from .parent import router as parent_router
    from .setup import router as setup_router
    from .student import router as student_router

    app.include_router(setup_router)
    app.include_router(student_router)
    app.include_router(parent_router)

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return _INDEX_PATH.read_text(encoding="utf-8")

    return app
