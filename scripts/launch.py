import os
import sys
import subprocess
import webbrowser
import time
import shutil
import socket

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
SOURCE_DIR = os.path.join(ROOT, "src")
sys.path.insert(0, SOURCE_DIR)
FRONTEND_DIR = os.path.join(SOURCE_DIR, "frontend")
npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def load_env():
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except PermissionError:
            print("  [警告] .env 文件被占用，跳过加载。")


def require_port_available(port: int):
    try:
        active = socket.create_connection(("127.0.0.1", port), timeout=0.2)
    except OSError:
        active = None
    if active is not None:
        active.close()
        raise SystemExit(f"Port {port} is already in use. Stop that service or choose another port.")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise SystemExit(f"Port {port} is already in use. Stop that service or choose another port.") from exc


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
        local_address = parts[1]
        if local_address.endswith(f":{port}") and parts[-1].isdigit():
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
    """Stop an existing CartridgeFlow listener, never an unidentified process."""
    pids = listener_pids(port)
    if not pids:
        return
    commands = {pid: process_command_line(pid) for pid in pids}
    foreign = {pid: command for pid, command in commands.items() if marker.lower() not in command.lower()}
    if foreign:
        details = "; ".join(f"PID {pid}: {command or 'unknown command'}" for pid, command in foreign.items())
        raise SystemExit(f"Port {port} is in use by another application ({details}). It was not stopped.")
    for pid in pids:
        print(f"[restart] Stopping previous CartridgeFlow listener on port {port} (PID {pid})...")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    for _ in range(30):
        if not listener_pids(port):
            return
        time.sleep(0.1)
    raise SystemExit(f"CartridgeFlow listener on port {port} did not stop in time.")


def main() -> None:
    load_env()

    # A repeat launch replaces only a process we can positively identify as
    # this workbench. A foreign listener remains an actionable error.
    restart_managed_listener(8765, "backend.main:app")
    restart_managed_listener(5173, "vite")
    require_port_available(8765)
    require_port_available(5173)

    if not os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")):
        print("[0/2] 安装前端依赖...")
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)

    print("[1/2] 启动后端 (port 8765)...")
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "warning",
        ],
        cwd=SOURCE_DIR,
    )

    print("[2/2] 启动前端开发服务器 (port 5173)...")
    frontend = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
        cwd=FRONTEND_DIR,
    )

    for _ in range(20):
        time.sleep(0.5)
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=1):
                break
        except OSError:
            continue

    webbrowser.open("http://127.0.0.1:5173")
    print("已打开 http://127.0.0.1:5173  (Ctrl+C 停止)")

    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        backend.terminate()
        frontend.terminate()


if __name__ == "__main__":
    main()
