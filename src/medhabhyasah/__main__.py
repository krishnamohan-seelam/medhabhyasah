"""Application entry point."""
import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from medhabhyasah.api import create_app
from medhabhyasah.db import create_schema, get_connection


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"Server did not start within {timeout}s")


def main() -> None:
    conn = get_connection()
    create_schema(conn)
    conn.close()

    port = _find_free_port()
    server_thread = threading.Thread(
        target=_run_server, args=(port,), daemon=True
    )
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    _wait_for_server(url)

    webview.create_window(
        "Medhabhyasah",
        url,
        width=1200,
        height=820,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
