import html


class HtmlGeneratorRuntime:
    runtime_type = "html_generator"

    def __init__(self, artifact_manager):
        self.artifact_manager = artifact_manager

    def start(self, run: dict, run_dir):
        inputs = run.get("inputs") or {}
        title = inputs.get("title") or inputs.get("task_description") or "欢迎使用 CartridgeFlow"
        description = inputs.get("description") or "这是由 HTML Welcome Generator 卡带生成的欢迎页面。"
        button_text = inputs.get("button_text") or "开始使用"
        content = self._render_welcome_html(title, description, button_text)
        artifact = self.artifact_manager.create_text_artifact(
            run=run,
            run_dir=run_dir,
            artifact_id="welcome_html",
            name="welcome.html",
            content=content,
            artifact_type="html",
            mime_type="text/html",
        )
        return {
            "runtime_run_id": f"html_generator_{run['run_id']}",
            "runtime_type": self.runtime_type,
            "status": "completed",
            "artifacts": [artifact],
        }

    def _render_welcome_html(self, title: str, description: str, button_text: str) -> str:
        safe_title = html.escape(title)
        safe_description = html.escape(description)
        safe_button = html.escape(button_text)
        return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{safe_title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f7f4ee; color: #302a24; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; }}
    .card {{ width: min(720px, calc(100vw - 32px)); border: 1px solid #e5dbcf; border-radius: 24px; background: radial-gradient(circle at center 10%, rgba(201,85,53,.1), transparent 35%), #fffdf8; padding: 46px; text-align: center; box-shadow: 0 18px 42px rgba(75,55,40,.08); }}
    .mark {{ width: 72px; height: 72px; margin: 0 auto 22px; border: 1px solid #e8c6b5; border-radius: 22px; background: #fff0e8; color: #c95535; display: grid; place-items: center; font-family: Georgia, serif; font-size: 34px; font-weight: 900; }}
    h1 {{ margin: 0 0 14px; font-size: 34px; letter-spacing: -.03em; }}
    p {{ margin: 0 auto 26px; max-width: 560px; color: #81776c; line-height: 1.8; font-size: 15px; }}
    button {{ border: 1px solid #b9492d; background: #c95535; color: white; border-radius: 10px; height: 40px; padding: 0 18px; font-weight: 850; }}
  </style>
</head>
<body>
  <main class=\"card\">
    <div class=\"mark\">C</div>
    <h1>{safe_title}</h1>
    <p>{safe_description}</p>
    <button>{safe_button}</button>
  </main>
</body>
</html>
"""
