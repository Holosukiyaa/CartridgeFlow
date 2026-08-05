"""Build and launch the Creator product on one local port."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "src"
FRONTEND_DIR = SOURCE_DIR / "frontend"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    except PermissionError:
        print("Warning: .env is locked; continuing without it.")


def require_port_available(port: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            raise SystemExit(f"Port {port} is already in use.")
    except ConnectionRefusedError:
        pass
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise SystemExit(f"Port {port} is already in use.") from exc


def listener_pids(port: int) -> list[int]:
    """Return local TCP listener PIDs without adding a psutil dependency."""
    if os.name != "nt":
        return []
    output = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    pids: set[int] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        if parts[1].endswith(f":{port}") and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return sorted(pids)


def process_command_line(pid: int) -> str:
    if os.name != "nt":
        return ""
    command = f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def restart_managed_listener(port: int, marker: str) -> None:
    """Replace only a listener positively identified as this application."""
    pids = listener_pids(port)
    if not pids:
        return
    commands = {pid: process_command_line(pid) for pid in pids}
    foreign = {pid: command for pid, command in commands.items() if marker.casefold() not in command.casefold()}
    if foreign:
        details = "; ".join(f"PID {pid}: {command or 'unknown command'}" for pid, command in foreign.items())
        raise SystemExit(f"Port {port} is used by another application ({details}); it was not stopped.")
    for pid in pids:
        print(f"Stopping previous CartridgeFlow listener on port {port} (PID {pid}).")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    for _ in range(30):
        if not listener_pids(port):
            return
        time.sleep(0.1)
    raise SystemExit(f"CartridgeFlow listener on port {port} did not stop in time.")


def ensure_frontend_bundle() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("npm was not found. Install Node.js 20 or newer.")
    if not (FRONTEND_DIR / "node_modules" / ".bin" / "vite.cmd").exists():
        print("Installing Creator dependencies...")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, check=True)
    print("Building Creator...")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)


def wait_until_ready(process: subprocess.Popen[object]) -> None:
    for _ in range(40):
        if process.poll() is not None:
            raise SystemExit("CartridgeFlow stopped before it became ready.")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.25):
                return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("CartridgeFlow did not become ready within 10 seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Do not open Creator automatically.")
    args = parser.parse_args()

    load_env()
    ensure_frontend_bundle()
    restart_managed_listener(PORT, "backend.main:app")
    require_port_available(PORT)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=SOURCE_DIR,
    )
    try:
        wait_until_ready(process)
        print(f"CartridgeFlow Creator: {URL}")
        if not args.no_browser:
            webbrowser.open(URL)
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()


if __name__ == "__main__":
    main()
