from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    server_version = "CartridgeFlowNoCache/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> None:
    root = Path(__file__).resolve().parent
    handler = partial(NoCacheHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 5174), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
