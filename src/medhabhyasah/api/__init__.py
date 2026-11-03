"""Local FastAPI routes for student and parent screens."""
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Ensure correct MIME type for woff2 fonts (not always registered on Windows)
mimetypes.add_type("font/woff2", ".woff2")

_WEB_DIR = Path(__file__).parent.parent / "web"
_STATIC_DIR = _WEB_DIR / "static"
_INDEX_PATH = _WEB_DIR / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(title="Medhabhyasah")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return _INDEX_PATH.read_text(encoding="utf-8")

    return app
