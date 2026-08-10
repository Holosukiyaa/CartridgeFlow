"""Prepare and launch a local read-only browser for the protocol source database."""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "protocol-source" / "protocol-source.sqlite"
VIEWER_CONFIG = ROOT / "config" / "protocol-viewer" / "datasette.json"
VIEWER_REQUIREMENTS = ROOT / "config" / "protocol-viewer" / "requirements.txt"
VIEWER_ENV = ROOT / ".tools" / "protocol-viewer"
REQUIREMENTS_MARKER = VIEWER_ENV / ".requirements.sha256"
DEFAULT_PORT = 8001


def environment_python() -> Path:
    if os.name == "nt":
        return VIEWER_ENV / "Scripts" / "python.exe"
    return VIEWER_ENV / "bin" / "python"


def environment_datasette() -> Path:
    if os.name == "nt":
        return VIEWER_ENV / "Scripts" / "datasette.exe"
    return VIEWER_ENV / "bin" / "datasette"


def requirements_digest() -> str:
    return hashlib.sha256(VIEWER_REQUIREMENTS.read_bytes()).hexdigest()


def prepare_viewer_environment(*, install: bool = True) -> Path:
    expected = requirements_digest()
    executable = environment_datasette()
    marker = REQUIREMENTS_MARKER.read_text(encoding="ascii").strip() if REQUIREMENTS_MARKER.is_file() else ""
    if executable.is_file() and marker == expected:
        return executable
    if not install:
        raise RuntimeError(
            "protocol viewer is not prepared; run 'python scripts/launch_protocol_viewer.py --prepare-only'"
        )

    python = environment_python()
    if not python.is_file():
        print(f"Creating isolated protocol viewer environment: {VIEWER_ENV}")
        venv.EnvBuilder(with_pip=True).create(VIEWER_ENV)
    print("Installing pinned protocol viewer dependencies...")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--retries",
            "3",
            "--timeout",
            "60",
            "-r",
            str(VIEWER_REQUIREMENTS),
        ],
        check=True,
    )
    REQUIREMENTS_MARKER.write_text(expected + "\n", encoding="ascii")
    if not executable.is_file():
        raise RuntimeError(f"Datasette executable was not installed: {executable}")
    return executable


def viewer_command(executable: Path, database: Path, port: int) -> list[str]:
    return [
        str(executable),
        "serve",
        "-i",
        str(database),
        "--metadata",
        str(VIEWER_CONFIG),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def require_port_available(port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(f"local port {port} is already in use") from exc


def wait_until_ready(process: subprocess.Popen[object], port: int) -> None:
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("protocol viewer stopped before it became ready")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("protocol viewer did not become ready within 20 seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    database = args.database.resolve()
    try:
        if not database.is_file():
            raise RuntimeError(
                f"protocol database not found: {database}. "
                "Run 'git submodule update --init protocol-source' first."
            )
        executable = prepare_viewer_environment(install=not args.no_install)
        if args.prepare_only:
            print(f"Protocol viewer is ready: {executable}")
            return 0
        require_port_available(args.port)
        process = subprocess.Popen(viewer_command(executable, database, args.port))
        try:
            wait_until_ready(process, args.port)
            database_name = quote(database.stem, safe="")
            url = f"http://127.0.0.1:{args.port}/{database_name}"
            print(f"Protocol library: {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Protocol viewer failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
