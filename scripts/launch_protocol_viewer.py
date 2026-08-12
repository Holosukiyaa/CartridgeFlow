"""Prepare and launch the local read-only protocol knowledge browser."""

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
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DATABASE = ROOT / "config" / "protocol" / "protocol-registry.sqlite"
DEFAULT_DATABASES = (PRODUCT_DATABASE,)
VIEWER_CONFIG = ROOT / "config" / "protocol-viewer" / "datasette.json"
VIEWER_TEMPLATES = ROOT / "config" / "protocol-viewer" / "templates"
VIEWER_PLUGINS = ROOT / "config" / "protocol-viewer" / "plugins"
VIEWER_REQUIREMENTS = ROOT / "config" / "protocol-viewer" / "requirements.txt"
VIEWER_ENV = ROOT / ".tools" / "protocol-viewer"
REQUIREMENTS_MARKER = VIEWER_ENV / ".requirements.sha256"
DEFAULT_PORT = 8001
VIEWER_HEADER = "X-CartridgeFlow-Protocol-Viewer"


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


def viewer_command(executable: Path, databases: tuple[Path, ...], port: int) -> list[str]:
    command = [
        str(executable),
        "serve",
    ]
    for database in databases:
        command.extend(("-i", str(database)))
    command.extend(
        [
            "--metadata",
            str(VIEWER_CONFIG),
            "--template-dir",
            str(VIEWER_TEMPLATES),
            "--plugins-dir",
            str(VIEWER_PLUGINS),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
    )
    return command


def viewer_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return environment


def require_port_available(port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(f"local port {port} is already in use") from exc


def viewer_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def viewer_is_running(port: int) -> bool:
    try:
        with urlopen(viewer_url(port), timeout=0.75) as response:
            return response.status == 200 and response.headers.get(VIEWER_HEADER) == "1"
    except (OSError, URLError):
        return False


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
    parser.add_argument(
        "--database",
        action="append",
        type=Path,
        help="SQLite database to serve. Repeat to override the default product snapshot.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    databases = tuple(
        database.resolve() for database in (args.database or DEFAULT_DATABASES)
    )
    try:
        missing = [str(database) for database in databases if not database.is_file()]
        if missing:
            raise RuntimeError(
                f"knowledge database not found: {', '.join(missing)}. "
                "Publish the product protocol registry first."
            )
        url = viewer_url(args.port)
        if not args.prepare_only and viewer_is_running(args.port):
            print(f"Protocol knowledge base is already running: {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        executable = prepare_viewer_environment(install=not args.no_install)
        if args.prepare_only:
            print(f"Protocol viewer is ready: {executable}")
            return 0
        require_port_available(args.port)
        process = subprocess.Popen(
            viewer_command(executable, databases, args.port),
            env=viewer_environment(),
        )
        try:
            wait_until_ready(process, args.port)
            print(f"Protocol knowledge base: {url}")
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
