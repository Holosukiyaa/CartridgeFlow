import os
import sys
import threading
import time
import traceback

PORT = 8765

if getattr(sys, "frozen", False):
    ROOT = sys._MEIPASS
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))

LOG = os.path.join(os.path.expanduser("~"), "CartridgeFlow_crash.log")
sys.path.insert(0, ROOT)


def log(message: str):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def run_server():
    try:
        import uvicorn
        from server.main import app
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    except Exception as e:
        log(f"server error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    try:
        import webview

        log("=== CartridgeFlow starting ===")
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(1.5)

        webview.create_window(
            title="CartridgeFlow",
            url=f"http://127.0.0.1:{PORT}",
            width=1280,
            height=860,
            resizable=True,
        )
        webview.start(debug=False, http_server=False)
        log("webview exited normally")
    except Exception as e:
        log(f"FATAL: {e}\n{traceback.format_exc()}")
        raise
