from dataclasses import dataclass


@dataclass
class ModelConfig:
    provider_id: str = "env-openai"
    api_type: str = "openai"
    wire_api: str = "chat_completions"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 8192
    timeout: int = 120

    @property
    def provider(self) -> str:
        return "anthropic" if self.api_type == "claude" else self.api_type
