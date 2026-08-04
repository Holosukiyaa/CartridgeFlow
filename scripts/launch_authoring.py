"""Launch the unified CartridgeFlow workbench and API together."""

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
API_PORT = 8000
FRONTEND_PORT = 5173
RETIRED_CREATOR_PORT = 5180
RETIRED_CONSOLE_PORT = 5181
_PORT_PROCESS_MARKERS = {
    API_PORT: ("uvicorn", "backend.main:app"),
    FRONTEND_PORT: ("vite", "frontend"),
    RETIRED_CREATOR_PORT: ("vite", "creator-studio"),
    RETIRED_CONSOLE_PORT: ("vite", "developer-console"),
}
_ACTIVE_PORTS = (API_PORT, FRONTEND_PORT)


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _require_available_ports() -> None:
    unavailable = [str(port) for port in _ACTIVE_PORTS if not _port_is_available(port)]
    if unavailable:
        raise SystemExit(f"Ports already in use: {', '.join(unavailable)}. Stop those services before launching authoring.")


def _listening_pids(port: int) -> list[int]:
    if os.name != "nt":
        return []
    result = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=False)
    pids: list[int] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP" or fields[-2].upper() != "LISTENING":
            continue
        if fields[1].rsplit(":", 1)[-1] == str(port) and fields[-1].isdigit():
            pids.append(int(fields[-1]))
    return pids


def _process_command_line(pid: int) -> str:
    command = f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _clear_stale_authoring_processes() -> None:
    """Release only ports owned by prior CartridgeFlow authoring launches."""
    if os.name != "nt":
        return
    for port, markers in _PORT_PROCESS_MARKERS.items():
        for pid in _listening_pids(port):
            command = _process_command_line(pid).casefold()
            if not all(marker in command for marker in markers):
                raise SystemExit(f"Port {port} is occupied by an unrelated process (PID {pid}); refusing to stop it.")
            print(f"Stopping stale CartridgeFlow process on port {port} (PID {pid}).")
            result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
            if result.returncode:
                raise SystemExit(f"Could not stop stale CartridgeFlow process on port {port} (PID {pid}).")
    for _ in range(20):
        if all(_port_is_available(port) for port in _PORT_PROCESS_MARKERS):
            return
        time.sleep(0.1)
    _require_available_ports()


def _npm_command() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm:
        return npm
    raise SystemExit("npm was not found. Install Node.js 20 or newer.")


def _wait_for_api(process: subprocess.Popen[object]) -> None:
    for _ in range(40):
        if process.poll() is not None:
            raise SystemExit("The CartridgeFlow API stopped before it became ready.")
        if not _port_is_available(API_PORT):
            return
        time.sleep(0.25)
    raise SystemExit("The CartridgeFlow API did not become ready within 10 seconds.")


def _vite_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("VITE_API_BASE_URL", None)
    environment["AUTHORING_API_TARGET"] = f"http://127.0.0.1:{API_PORT}"
    environment["VITE_API_PROXY_TARGET"] = f"http://127.0.0.1:{API_PORT}"
    return environment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the workbench URL automatically.")
    args = parser.parse_args()

    _clear_stale_authoring_processes()
    _require_available_ports()
    npm = _npm_command()
    environment = _vite_environment()
    processes: list[subprocess.Popen[object]] = []
    try:
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=SOURCE_DIR,
            env=environment,
        )
        processes.append(api)
        _wait_for_api(api)
        processes.append(
            subprocess.Popen(
                [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(FRONTEND_PORT), "--strictPort"],
                cwd=FRONTEND_DIR,
                env=environment,
            )
        )
        workbench_url = f"http://127.0.0.1:{FRONTEND_PORT}/"
        print(f"CartridgeFlow Workbench: {workbench_url}")
        print(f"API documentation: http://127.0.0.1:{API_PORT}/docs")
        if not args.no_browser:
            webbrowser.open(workbench_url)
        while True:
            if any(process.poll() is not None for process in processes):
                raise SystemExit("An authoring service stopped unexpectedly.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    main()
