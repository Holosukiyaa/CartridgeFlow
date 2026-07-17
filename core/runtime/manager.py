from core.cartridge.artifacts import ArtifactManager
from .html_generator import HtmlGeneratorRuntime
from .llm_prompt import LlmPromptRuntime
from .agent_squad import AgentSquadRuntime


class RuntimeManager:
    def __init__(self, root):
        self.artifact_manager = ArtifactManager(root)
        self.adapters = {}
        self.register(HtmlGeneratorRuntime(self.artifact_manager))
        self.register(LlmPromptRuntime(self.artifact_manager))
        self.register(AgentSquadRuntime(self.artifact_manager))

    def register(self, adapter):
        self.adapters[adapter.runtime_type] = adapter

    def list_runtime_types(self) -> list[str]:
        return sorted(self.adapters.keys())

    def start(self, run: dict, run_dir):
        runtime = run.get("runtime") or {}
        runtime_type = runtime.get("type", "none")
        adapter = self.adapters.get(runtime_type)
        if adapter:
            return adapter.start(run, run_dir)
        return {
            "runtime_run_id": f"{runtime_type}_{run['run_id']}",
            "runtime_type": runtime_type,
            "status": "ready",
            "artifacts": [],
        }
