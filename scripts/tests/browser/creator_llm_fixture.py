"""Small OpenAI-compatible fixture for Creator browser acceptance."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


DISCOVERY = {
    "possibilities": [
        {
            "id": "action-list",
            "title": "Turn meeting notes into actions",
            "outcome": "A short list of owned and prioritized follow-up actions.",
            "why_it_fits": "It turns an existing meeting record into something the team can execute.",
            "first_week_output": "One reviewed action list from the latest meeting.",
            "needs_confirmation": ["Which meeting record should be processed first?"],
            "recipe": {
                "intent": "Turn meeting notes into clear action items",
                "steps": [
                    {"id": "read-notes", "intent": "Identify decisions and unresolved work", "inputs": [], "outputs": []},
                    {"id": "write-actions", "intent": "Write prioritized actions with owners", "inputs": [], "outputs": []},
                ],
            },
        },
        {
            "id": "decision-summary",
            "title": "Create a decision summary",
            "outcome": "A concise record of decisions, reasons, and open questions.",
            "why_it_fits": "It preserves the parts of a meeting that people need to recall later.",
            "first_week_output": "One decision summary ready for team review.",
            "needs_confirmation": ["How detailed should the decision reasoning be?"],
            "recipe": {
                "intent": "Summarize meeting decisions and open questions",
                "steps": [
                    {"id": "find-decisions", "intent": "Find decisions and supporting reasons", "inputs": [], "outputs": []},
                    {"id": "record-questions", "intent": "Record questions that remain open", "inputs": [], "outputs": []},
                ],
            },
        },
        {
            "id": "weekly-review",
            "title": "Build a weekly review",
            "outcome": "A weekly view of progress, blockers, and the next priorities.",
            "why_it_fits": "It combines repeated meeting notes into a stable review habit.",
            "first_week_output": "A first weekly review based on the notes you provide.",
            "needs_confirmation": ["Which meetings belong in the weekly review?"],
            "recipe": {
                "intent": "Create a weekly progress review from meeting notes",
                "steps": [
                    {"id": "group-progress", "intent": "Group progress and blockers", "inputs": [], "outputs": []},
                    {"id": "set-priorities", "intent": "Set the next weekly priorities", "inputs": [], "outputs": []},
                ],
            },
        },
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        body = json.dumps(value, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("models"):
            self._json(200, {"object": "list", "data": [{"id": "creator-fixture"}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.rstrip("/").endswith("chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = payload.get("messages") if isinstance(payload, dict) else []
        system = str(next((item.get("content") for item in messages or [] if item.get("role") == "system"), ""))
        user = str(next((item.get("content") for item in reversed(messages or []) if item.get("role") == "user"), ""))
        if "exactly three distinct possibilities" in system:
            content = json.dumps(DISCOVERY, ensure_ascii=False)
        elif "supplied trusted preset ids" in system:
            facts = json.loads(user)
            preset_ids = [item["id"] for item in facts.get("trusted_presets") or []]
            starter = "starter-ai-transform" if "starter-ai-transform" in preset_ids else preset_ids[0]
            content = json.dumps({
                "recipe": {
                    "nodes": [{
                        "id": "action-items",
                        "preset_id": starter,
                        "values": {"instruction": "Turn the supplied meeting notes into three prioritized action items with owners and due dates."},
                    }],
                    "relations": [],
                },
            })
        elif 'Return JSON only as {"values": {...}}' in system:
            content = json.dumps({
                "values": {
                    "instruction": "Extract decisions first, then list three prioritized actions with an owner, due date, and completion check.",
                },
            })
        else:
            content = "OK"
        self._json(200, {
            "id": "creator-fixture-response",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8877)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
