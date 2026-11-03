"""Build a PyInstaller one-dir bundle for Medhabhyasah."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "medhabhyasah"


def main() -> None:
    web_dir = SRC / "web"
    generation_dir = SRC / "generation"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", "Medhabhyasah",
        "--onedir",
        "--windowed",
        "--add-data", f"{web_dir}{os.pathsep}medhabhyasah/web",
        "--add-data", f"{generation_dir / 'quiz_generator_prompt.md'}{os.pathsep}medhabhyasah/generation",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.lifespan.off",
        "--collect-submodules", "webview",
        "--collect-submodules", "keyring.backends",
        str(SRC / "__main__.py"),
    ]

    print("Running PyInstaller …")
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"\nBundle ready at: {ROOT / 'dist' / 'Medhabhyasah'}")


if __name__ == "__main__":
    main()
