import asyncio
import html


class LlmPromptRuntime:
    """LLM Prompt Runtime：调用 LLM 生成文本，并保存为 artifact。"""

    runtime_type = "llm_prompt"

    def __init__(self, artifact_manager):
        self.artifact_manager = artifact_manager

    def start(self, run: dict, run_dir):
        inputs = run.get("inputs") or {}
        prompt = inputs.get("prompt") or inputs.get("task_description") or "你好"
        system_prompt = inputs.get("system_prompt") or "你是一个友好的 AI 助手。"
        model_role = inputs.get("model_role") or "runtime"

        try:
            content, meta = self._call_llm(system_prompt, prompt, model_role, run)
            status = "completed"
        except Exception as e:
            content = f"[LLM 调用失败] {e}"
            meta = {"error": str(e)[:200]}
            status = "error"

        # 保存纯文本 artifact
        text_artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="llm_response",
            name="response.md",
            content=f"# LLM Response\n\n**Prompt:** {prompt}\n\n---\n\n{content}\n",
            artifact_type="text",
            mime_type="text/markdown",
        )

        # 保存 HTML 预览 artifact
        html_artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="llm_response_html",
            name="response.html",
            content=self._render_html(prompt, content, meta),
            artifact_type="html",
            mime_type="text/html",
        )

        return {
            "runtime_run_id": f"llm_prompt_{run['run_id']}",
            "runtime_type": self.runtime_type,
            "status": status,
            "artifacts": [text_artifact, html_artifact],
            "llm_meta": meta,
        }

    def _call_llm(self, system_prompt: str, user_prompt: str, role: str, run: dict) -> tuple[str, dict]:
        from core.llm import chat
        from core.llm.config_manager import resolve_model

        cfg = resolve_model(role=role, cartridge_id=run.get("cartridge_id"))
        if not cfg.api_key:
            return "[未配置 LLM API Key] 请在设置中配置 Provider。", {"configured": False}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = asyncio.run(chat(
                cfg,
                messages,
                agent_name="llm_prompt_runtime",
                phase="run",
            ))
        except RuntimeError:
            # 已在 event loop 中（不应该发生在 runtime start 中，但做容错）
            loop = asyncio.get_event_loop()
            response = loop.run_until_complete(chat(
                cfg,
                messages,
                agent_name="llm_prompt_runtime",
                phase="run",
            ))

        content = response.get("content", "")
        meta = response.get("meta", {})
        meta["configured"] = True
        return content, meta

    def _render_html(self, prompt: str, content: str, meta: dict) -> str:
        safe_prompt = html.escape(prompt)
        safe_content = html.escape(content)
        model = html.escape(str(meta.get("model", "unknown")))
        elapsed = html.escape(str(meta.get("elapsed_seconds", "?")))
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>LLM Response</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #f7f4ee; color: #302a24; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; padding: 32px; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    .card {{ background: #fffdf8; border: 1px solid #e5dbcf; border-radius: 16px; padding: 32px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(75,55,40,.06); }}
    .label {{ font-size: 12px; color: #b09a8a; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
    .prompt {{ background: #f0ebe3; border-radius: 10px; padding: 16px; font-size: 14px; color: #5a4e42; }}
    .response {{ white-space: pre-wrap; word-wrap: break-word; font-size: 15px; line-height: 1.8; color: #302a24; }}
    .meta {{ font-size: 12px; color: #b09a8a; margin-top: 16px; padding-top: 16px; border-top: 1px solid #f0ebe3; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="label">Prompt</div>
      <div class="prompt">{safe_prompt}</div>
    </div>
    <div class="card">
      <div class="label">Response</div>
      <div class="response">{safe_content}</div>
      <div class="meta">model: {model} · elapsed: {elapsed}s</div>
    </div>
  </div>
</body>
</html>"""
