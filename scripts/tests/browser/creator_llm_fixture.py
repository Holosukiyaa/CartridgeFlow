"""Small OpenAI-compatible fixture for Creator browser acceptance."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


DISCOVERY = {
    "mode": "propose",
    "clarification": None,
    "possibilities": [
        {
            "id": "action-list",
            "title": "把信息整理成行动清单",
            "outcome": "每天得到一份有负责人和优先级的后续行动清单。",
            "why_it_fits": "它把零散信息变成可以立即执行的结果。",
            "first_week_output": "一份经过确认的行动清单。",
            "needs_confirmation": ["最先处理哪一类信息？"],
            "recipe": {
                "intent": "把每天收到的信息整理成明确行动",
                "steps": [
                    {"id": "read-notes", "intent": "识别决定和仍未解决的事项", "inputs": [], "outputs": []},
                    {"id": "write-actions", "intent": "整理带负责人和优先级的行动", "inputs": [], "outputs": []},
                ],
            },
        },
        {
            "id": "decision-summary",
            "title": "生成可审核的中文简报",
            "outcome": "得到一份包含结论、依据和待确认问题的简报。",
            "why_it_fits": "它适合快速阅读，也保留了继续核查的入口。",
            "first_week_output": "一份可供团队审核的中文简报。",
            "needs_confirmation": ["简报主要给谁阅读？"],
            "recipe": {
                "intent": "把每天收到的信息生成可审核的中文简报",
                "steps": [
                    {"id": "find-decisions", "intent": "找出主要结论和支持依据", "inputs": [], "outputs": []},
                    {"id": "record-questions", "intent": "记录仍需要确认的问题", "inputs": [], "outputs": []},
                ],
            },
        },
        {
            "id": "weekly-review",
            "title": "形成每周变化回顾",
            "outcome": "每周汇总重要变化、阻碍和下一步优先事项。",
            "why_it_fits": "它更适合观察长期趋势，而不是处理单条信息。",
            "first_week_output": "第一份本周变化回顾。",
            "needs_confirmation": ["哪些主题需要持续跟踪？"],
            "recipe": {
                "intent": "从每天的信息中形成每周变化回顾",
                "steps": [
                    {"id": "group-progress", "intent": "归纳本周变化和阻碍", "inputs": [], "outputs": []},
                    {"id": "set-priorities", "intent": "确定下周优先关注的事项", "inputs": [], "outputs": []},
                ],
            },
        },
    ],
}

CLARIFICATION = {
    "mode": "clarify",
    "clarification": {
        "question": "你希望这些信息最后变成什么结果？",
        "why_it_matters": "结果形态会决定后续是强调行动、审核还是长期观察。",
        "suggested_answers": ["每天生成一份可审核的中文简报", "整理成带优先级的行动清单", "每周形成一次变化回顾"],
    },
    "possibilities": [],
}

SEMANTIC_RECIPE = {
    "nodes": [
        {
            "id": "read-notes",
            "label": "读懂会议记录",
            "description": "找出会议中的决定、待办事项和仍未解决的问题。",
            "needed_capability": "能够理解会议记录并识别决定与待办事项",
            "capability_id": None,
            "values": {},
        },
        {
            "id": "assign-actions",
            "label": "整理负责人和截止时间",
            "description": "把待办事项整理成有负责人、截止时间和优先级的行动清单。",
            "needed_capability": "能够把待办事项整理成明确的行动清单",
            "capability_id": None,
            "values": {},
        },
        {
            "id": "review-output",
            "label": "生成可确认的结果",
            "description": "输出一份便于团队逐项确认和继续跟进的结果。",
            "needed_capability": "能够生成便于团队确认的行动结果",
            "capability_id": None,
            "values": {},
        },
    ],
    "relations": [
        {"id": "notes-to-actions", "from_node_id": "read-notes", "to_node_id": "assign-actions", "relation": "informs"},
        {"id": "actions-to-review", "from_node_id": "assign-actions", "to_node_id": "review-output", "relation": "produces"},
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
        if "mode=clarify" in system:
            content = json.dumps(DISCOVERY if "补充：" in user else CLARIFICATION, ensure_ascii=False)
        elif "one-to-eight step semantic recipe" in system:
            content = json.dumps(SEMANTIC_RECIPE, ensure_ascii=False)
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
