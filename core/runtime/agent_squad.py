"""
core/runtime/agent_squad.py — Agent Squad Runtime

一个 Runtime = 一个 Mentor + 一个 Worker，通过 CorrectionBus 协作。
Worker 负责执行任务，每轮发布快照给 Mentor 审查；
Mentor 负责监督，输出 OK / CORRECT / ROLLBACK 指令。

设计原则：
- 不依赖 display / debug 探针 / 旧 server / SessionController
- 最多 10 轮，防止无限循环
- 无 API key 时返回提示信息而非抛异常
- 工具仅 finish_task 和 ask_mentor，不做文件读写（安全边界）
"""
import asyncio
import html
import json
from dataclasses import dataclass, field

from core.llm import chat
from core.llm.config_manager import resolve_model


# ── 工具 schema ──────────────────────────────────────────────

# finish_task：Worker 完成任务时调用
_FINISH_TASK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "finish_task",
        "description": "任务完成时调用此工具，并给出完成摘要",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "任务完成摘要"},
            },
            "required": ["summary"],
        },
    },
}

# ask_mentor：Worker 向 Mentor 提问，获取设计信息
_ASK_MENTOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_mentor",
        "description": "向管家询问你不知道的设计信息或需求细节",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
}

# Worker 可用的全部工具
_TOOL_SCHEMAS = [_FINISH_TASK_SCHEMA, _ASK_MENTOR_SCHEMA]


# ── 默认 system prompt ──────────────────────────────────────

# Mentor 拥有蓝图时的 system prompt
_MENTOR_SYSTEM_WITH_BLUEPRINT = (
    "你是 Mentor（管家），是本 Squad 的唯一知识持有者。\n"
    "以下蓝图和设计信息只有你能看到，Worker 对此一无所知：\n\n{blueprint}\n\n"
    "你的职责：\n"
    "1. 当 Worker 通过 ask_mentor 工具提问时，根据蓝图详细、准确地回答\n"
    "2. 每轮审查 Worker 的工作，偏离规范时用 CORRECT: 纠正，严重错误用 ROLLBACK: 回滚\n"
    "3. 不需要主动发起对话，等待 Worker 提问或审查快照\n"
    "回答提问时要具体直接，不要说'请参考文档'，直接告诉 Worker 答案。"
)

# Mentor 无蓝图时的默认 system prompt
_MENTOR_SYSTEM_DEFAULT = (
    "你是 Mentor，负责监督 Worker 执行任务，是设计信息的唯一来源。"
    "Worker 会通过 ask_mentor 向你提问，请据实回答。发现错误时用 CORRECT: 纠正。"
)

# Worker 默认 system prompt
_WORKER_SYSTEM_DEFAULT = (
    "你是 Worker，负责完成任务。\n"
    "重要：你对当前项目的设计一无所知。你必须通过 ask_mentor 工具向管家（Mentor）提问来获取所有设计信息。\n"
    "工作流程：\n"
    "1. 先用 ask_mentor 询问任务的整体设计、需求和技术细节\n"
    "2. 收到回答后继续追问，直到掌握足够信息\n"
    "3. 了解清楚后开始执行任务\n"
    "4. 完成后调用 finish_task\n"
    "收到 [MENTOR CORRECTION] 消息时，这是高优先级指令，必须立即按照纠正内容修改。"
)

# Mentor 评估 Worker 快照时使用的 prompt
_MENTOR_EVAL_PROMPT = """You are observing Worker's full conversation history on a task.
Task: {task}
Round: {round}

=== Worker's complete context ===
{worker_context}
=== End of Worker context ===

Evaluate Worker's progress and respond with ONE of:
- "ROLLBACK: <reason>" — Worker has gone severely off-track
- "CORRECT: <fix needed>" — Worker is slightly off-track
- "OK" — Worker is on track

Be concise. Only intervene when necessary."""


# ── 数据结构 ────────────────────────────────────────────────

@dataclass
class WorkerSnapshot:
    """Worker 状态快照，发布给 Mentor 审查。"""
    round: int
    messages: list[dict]
    last_response: str = ""


class CorrectionBus:
    """Worker 与 Mentor 之间的通信总线，基于 asyncio.Queue 实现。"""

    def __init__(self):
        # 纠正消息队列（Mentor → Worker）
        self._corrections: asyncio.Queue[str] = asyncio.Queue()
        # 回滚指令队列（Mentor → Worker）
        self._rollback: asyncio.Queue[tuple] = asyncio.Queue()
        # 快照订阅回调列表
        self._snapshot_handlers: list = []
        # 评估完成事件，Worker 用它等待 Mentor 评估结束
        self._eval_done = asyncio.Event()
        self._eval_done.set()

    def on_snapshot(self, handler):
        """注册快照回调函数。"""
        self._snapshot_handlers.append(handler)

    async def publish_snapshot(self, snapshot: WorkerSnapshot):
        """Worker 发布快照，触发 Mentor 评估（会阻塞直到评估完成）。"""
        self._eval_done.clear()
        for handler in self._snapshot_handlers:
            await handler(snapshot)

    def mark_eval_done(self):
        """Mentor 评估完成后调用，解除 Worker 的阻塞。"""
        self._eval_done.set()

    async def wait_eval_done(self):
        """Worker 等待 Mentor 评估完成。"""
        await self._eval_done.wait()

    async def inject_correction(self, correction: str):
        """Mentor 注入纠正消息。"""
        await self._corrections.put(correction)

    async def inject_rollback(self, snapshot: WorkerSnapshot, reason: str):
        """Mentor 注入回滚指令。"""
        await self._rollback.put((snapshot, reason))

    def drain_corrections(self) -> list[str]:
        """Worker 取出所有待处理的纠正消息。"""
        items = []
        while not self._corrections.empty():
            items.append(self._corrections.get_nowait())
        return items

    def drain_rollback(self):
        """Worker 取出回滚指令（如果有）。返回 (snapshot, reason) 或 None。"""
        if self._rollback.empty():
            return None
        return self._rollback.get_nowait()


# ── Agent 实现 ──────────────────────────────────────────────

class _MentorAgent:
    """Mentor Agent：被动驱动，监听 Worker 快照并评估。"""

    def __init__(self, cfg, bus: CorrectionBus, task: str, system_prompt: str):
        self.cfg = cfg  # ModelConfig
        self.bus = bus
        self.task = task
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        # 注册快照回调
        bus.on_snapshot(self._on_worker_snapshot)

    async def _on_worker_snapshot(self, snapshot: WorkerSnapshot):
        """收到 Worker 快照后进行评估。"""
        # 构造 Worker 上下文摘要（带字符预算）
        visible = [m for m in snapshot.messages if m["role"] != "system"]
        context_lines = []
        char_budget = 6000
        for m in reversed(visible):
            line = f"[{m['role'].upper()}]: {m.get('content') or json.dumps(m.get('tool_calls', ''), ensure_ascii=False)}"
            if char_budget - len(line) < 0:
                context_lines.append("[... 更早的历史已截断 ...]")
                break
            context_lines.append(line)
            char_budget -= len(line)
        worker_context = "\n".join(reversed(context_lines))

        eval_prompt = _MENTOR_EVAL_PROMPT.format(
            task=self.task[:1000],
            round=snapshot.round,
            worker_context=worker_context,
        )
        self.messages.append({"role": "user", "content": eval_prompt})

        try:
            response = await chat(
                self.cfg, self.messages,
                agent_name="mentor", phase="evaluation",
            )
        except Exception as e:
            # Mentor 评估失败时不阻塞 Worker，直接标记完成
            self.messages.append({"role": "assistant", "content": f"[Mentor 评估失败] {e}"})
            self.bus.mark_eval_done()
            return

        self.messages.append(response)
        content = response.get("content", "")
        stripped = content.strip()
        upper = stripped.upper()

        # 解析评估结果
        if upper.startswith("ROLLBACK:"):
            reason = stripped[len("ROLLBACK:"):].strip()
            await self.bus.inject_rollback(snapshot, reason)
        elif upper.startswith("CORRECT:"):
            correction = stripped[len("CORRECT:"):].strip()
            await self.bus.inject_correction(correction)
        # OK 时不做任何干预

        # 标记评估完成，解除 Worker 阻塞
        self.bus.mark_eval_done()

    async def answer_question(self, question: str) -> str:
        """回答 Worker 通过 ask_mentor 提出的问题。"""
        prompt = f"[WORKER QUESTION] {question}\n请根据你的私有知识回答，要具体、有帮助。"
        self.messages.append({"role": "user", "content": prompt})
        try:
            response = await chat(
                self.cfg, self.messages,
                agent_name="mentor", phase="answer_question",
            )
        except Exception as e:
            return f"[Mentor 错误] {e}"
        self.messages.append(response)
        return response.get("content", "")


class _WorkerAgent:
    """Worker Agent：执行任务，每轮发布快照给 Mentor 审查。"""

    def __init__(self, cfg, bus: CorrectionBus, mentor: _MentorAgent, max_rounds: int = 10):
        self.cfg = cfg  # ModelConfig
        self.bus = bus
        self.mentor = mentor
        self.max_rounds = max_rounds
        self.messages: list[dict] = []
        self.finished = False
        self.round = 0
        self.final_content = ""  # Worker 最终输出内容

    async def run(self, system_prompt: str, task: str):
        """Worker 主循环。"""
        self.messages = [{"role": "system", "content": system_prompt}]
        self.messages.append({"role": "user", "content": task})

        # 待处理的纠正消息（上一轮 Mentor 产生的，本轮注入）
        pending_corrections: list[str] = []
        last_response: dict = {}

        for _ in range(self.max_rounds):
            # 等待 Mentor 评估完成（首轮无需等待，但调用是幂等的）
            await self.bus.wait_eval_done()

            # 处理回滚指令
            rollback = self.bus.drain_rollback()
            if rollback:
                snapshot, reason = rollback
                # 回滚到快照时的消息状态
                self.messages = [m for m in snapshot.messages]
                self.messages.append({"role": "user", "content": f"[MENTOR ROLLBACK] {reason}"})
                continue

            # 注入上一轮遗留的纠正消息
            if pending_corrections:
                combined = "\n".join(f"[MENTOR CORRECTION] {c}" for c in pending_corrections)
                self.messages.append({"role": "user", "content": combined})
                pending_corrections.clear()

            # 也取出本轮可能已经产生的纠正消息
            corrections = self.bus.drain_corrections()
            if corrections:
                combined = "\n".join(f"[MENTOR CORRECTION] {c}" for c in corrections)
                self.messages.append({"role": "user", "content": combined})

            self.round += 1

            # 调用 LLM
            try:
                last_response = await chat(
                    self.cfg, self.messages, tools=_TOOL_SCHEMAS,
                    agent_name="worker", phase="execution",
                )
            except Exception as e:
                # LLM 错误时注入提示，让 Worker 下一轮继续
                self.messages.append({"role": "user", "content": f"[LLM 错误] {e}，请继续。"})
                continue

            self.messages.append(last_response)

            finish_requested = False
            # 容错解析 tool_calls
            tool_calls = last_response.get("tool_calls") or []
            for idx, tc in enumerate(tool_calls):
                name = (tc.get("function") or {}).get("name", "unknown")
                raw_args = (tc.get("function") or {}).get("arguments", "")
                tc_id = tc.get("id") or f"missing_id_{idx}"

                # 容错解析参数 JSON
                try:
                    if isinstance(raw_args, str):
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    else:
                        args = raw_args or {}
                except json.JSONDecodeError:
                    self.messages.append({
                        "role": "tool", "tool_call_id": tc_id, "name": name,
                        "content": f"[ERROR] 工具参数 JSON 解析失败: {raw_args}",
                    })
                    continue

                if name == "finish_task":
                    finish_requested = True
                    summary = args.get("summary", "") if isinstance(args, dict) else ""
                    self.messages.append({
                        "role": "tool", "tool_call_id": tc_id, "name": name,
                        "content": "任务已完成",
                    })
                    self.final_content = summary or last_response.get("content", "")
                    continue

                if name == "ask_mentor":
                    question = args.get("question", "") if isinstance(args, dict) else str(args)
                    result = await self.mentor.answer_question(question)
                else:
                    result = f"[ERROR] 未知工具: {name}"

                self.messages.append({
                    "role": "tool", "tool_call_id": tc_id, "name": name,
                    "content": result,
                })

            if finish_requested:
                # 发布最终快照给 Mentor（Mentor 可能会纠正过早完成）
                await self.bus.publish_snapshot(WorkerSnapshot(
                    round=self.round,
                    messages=list(self.messages),
                    last_response=self.final_content,
                ))
                # 如果 Mentor 在最终快照后注入了纠正，则不标记完成
                final_corrections = self.bus.drain_corrections()
                final_rollback = self.bus.drain_rollback()
                if final_corrections:
                    pending_corrections = final_corrections
                    continue
                if final_rollback:
                    snapshot, reason = final_rollback
                    self.messages = [m for m in snapshot.messages]
                    self.messages.append({"role": "user", "content": f"[MENTOR ROLLBACK] {reason}"})
                    continue
                self.finished = True
                return

            # 发布快照给 Mentor 审查
            await self.bus.publish_snapshot(WorkerSnapshot(
                round=self.round,
                messages=list(self.messages),
                last_response=last_response.get("content", ""),
            ))

            # 取出 Mentor 本轮产生的纠正消息，留到下一轮注入
            pending_corrections = self.bus.drain_corrections()

            # 如果没有工具调用且有内容，提示 Worker 继续
            if not tool_calls and last_response.get("content"):
                self.messages.append({"role": "user", "content": "请继续，或确认任务完成时调用 finish_task。"})

        # 达到最大轮数仍未完成
        if not self.finished:
            self.final_content = last_response.get("content", "") if last_response else ""


# ── Runtime ─────────────────────────────────────────────────

class AgentSquadRuntime:
    """Agent Squad Runtime：编排 Mentor + Worker 协作完成任务。"""

    runtime_type = "agent_squad"

    # 最大执行轮数，防止无限循环
    MAX_ROUNDS = 10

    def __init__(self, artifact_manager):
        self.artifact_manager = artifact_manager

    def start(self, run: dict, run_dir) -> dict:
        """同步入口，内部用 asyncio.run 调用异步执行。"""
        return asyncio.run(self._start_async(run, run_dir))

    async def _start_async(self, run: dict, run_dir) -> dict:
        """异步执行 Agent Squad。"""
        inputs = run.get("inputs") or {}
        task = inputs.get("task") or inputs.get("task_description") or "请完成以下任务。"
        blueprint = inputs.get("blueprint") or ""
        system_prompt = inputs.get("system_prompt") or ""

        # 解析 model config，分别用于 worker 和 mentor
        cartridge_id = run.get("cartridge_id")
        worker_cfg = resolve_model(role="worker", cartridge_id=cartridge_id)
        mentor_cfg = resolve_model(role="mentor", cartridge_id=cartridge_id)

        # 无 API key 时返回提示信息而非报错
        if not worker_cfg.api_key or not mentor_cfg.api_key:
            return self._no_key_result(run, run_dir, task)

        # 构造 system prompt
        worker_system = system_prompt or _WORKER_SYSTEM_DEFAULT
        if blueprint:
            mentor_system = _MENTOR_SYSTEM_WITH_BLUEPRINT.format(blueprint=blueprint)
        else:
            mentor_system = _MENTOR_SYSTEM_DEFAULT

        # 创建通信总线
        bus = CorrectionBus()

        # 创建 Mentor（被动监听，注册到 bus）
        mentor = _MentorAgent(mentor_cfg, bus, task, mentor_system)

        # 创建 Worker
        worker = _WorkerAgent(worker_cfg, bus, mentor, max_rounds=self.MAX_ROUNDS)

        # 运行 Worker 主循环
        await worker.run(worker_system, task)

        # 生成 artifact
        content = worker.final_content or "（Worker 未产出内容）"
        status = "completed" if worker.finished else "incomplete"

        text_artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="agent_squad_response",
            name="response.md",
            content=self._render_markdown(task, content, worker, status),
            artifact_type="text",
            mime_type="text/markdown",
        )

        html_artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="agent_squad_response_html",
            name="response.html",
            content=self._render_html(task, content, worker, status),
            artifact_type="html",
            mime_type="text/html",
        )

        return {
            "runtime_run_id": f"agent_squad_{run['run_id']}",
            "runtime_type": self.runtime_type,
            "status": status,
            "artifacts": [text_artifact, html_artifact],
            "rounds": worker.round,
            "finished": worker.finished,
        }

    def _no_key_result(self, run: dict, run_dir, task: str) -> dict:
        """无 API key 时返回的提示结果。"""
        tip = "[未配置 LLM API Key] 请在设置中配置 Provider 后再运行 Agent Squad 任务。"
        text_artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="agent_squad_response",
            name="response.md",
            content=f"# Agent Squad\n\n**Task:** {task}\n\n---\n\n{tip}\n",
            artifact_type="text",
            mime_type="text/markdown",
        )
        return {
            "runtime_run_id": f"agent_squad_{run['run_id']}",
            "runtime_type": self.runtime_type,
            "status": "no_api_key",
            "artifacts": [text_artifact],
            "message": tip,
        }

    def _render_markdown(self, task: str, content: str, worker: _WorkerAgent, status: str) -> str:
        """生成 Markdown 格式的 artifact 内容。"""
        status_text = "已完成" if worker.finished else f"未完成（已达最大轮数 {self.MAX_ROUNDS}）"
        return (
            f"# Agent Squad Response\n\n"
            f"**Task:** {task}\n\n"
            f"**Status:** {status_text}\n\n"
            f"**Rounds:** {worker.round}\n\n"
            f"---\n\n"
            f"{content}\n"
        )

    def _render_html(self, task: str, content: str, worker: _WorkerAgent, status: str) -> str:
        """生成 HTML 格式的 artifact 内容。"""
        safe_task = html.escape(task)
        safe_content = html.escape(content)
        status_text = "已完成" if worker.finished else f"未完成（已达最大轮数 {self.MAX_ROUNDS}）"
        safe_status = html.escape(status_text)
        rounds = worker.round
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agent Squad Response</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #f7f4ee; color: #302a24; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; padding: 32px; }}
    .container {{ max-width: 860px; margin: 0 auto; }}
    .card {{ background: #fffdf8; border: 1px solid #e5dbcf; border-radius: 16px; padding: 32px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(75,55,40,.06); }}
    .label {{ font-size: 12px; color: #b09a8a; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
    .task {{ background: #f0ebe3; border-radius: 10px; padding: 16px; font-size: 14px; color: #5a4e42; }}
    .response {{ white-space: pre-wrap; word-wrap: break-word; font-size: 15px; line-height: 1.8; color: #302a24; }}
    .meta {{ font-size: 12px; color: #b09a8a; margin-top: 16px; padding-top: 16px; border-top: 1px solid #f0ebe3; }}
    .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
    .badge-ok {{ background: #e6f4ea; color: #1e7e34; }}
    .badge-warn {{ background: #fff4e5; color: #b35900; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="label">Task</div>
      <div class="task">{safe_task}</div>
    </div>
    <div class="card">
      <div class="label">Response</div>
      <div class="response">{safe_content}</div>
      <div class="meta">
        <span class="badge {'badge-ok' if worker.finished else 'badge-warn'}">{safe_status}</span>
        &middot; 共 {rounds} 轮
      </div>
    </div>
  </div>
</body>
</html>"""
