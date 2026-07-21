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


def free_port(port: int):
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess | Sort -Unique | ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}",
            ],
            capture_output=True,
        )
        print(f"  [清理] 已释放端口 {port}")
        time.sleep(0.5)
    except Exception as e:
        print(f"  [警告] 释放端口 {port} 失败: {e}")


load_env()

free_port(8765)
free_port(5173)

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
        "0.0.0.0",
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
