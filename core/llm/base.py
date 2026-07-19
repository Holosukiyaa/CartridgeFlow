import asyncio
import time
from typing import Callable

from .config import ModelConfig
from .openai_provider import openai_chat
from .retry import with_retry


async def chat(
    cfg: ModelConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_token: Callable[[str], None] | None = None,
    on_usage: Callable[[int, int], None] | None = None,
    agent_name: str = "unknown",
    phase: str = "execution",
) -> dict:
    started_at = time.time()

    async def call():
        api_type = "anthropic" if cfg.api_type == "claude" else cfg.api_type
        if api_type == "openai" and cfg.wire_api == "chat_completions":
            try:
                return await openai_chat(cfg, messages, tools, on_token, on_usage)
            except (TimeoutError, asyncio.TimeoutError):
                if on_token:
                    return await openai_chat(cfg, messages, tools, None, on_usage)
                raise
        raise ValueError(f"Unsupported LLM route: api_type={cfg.api_type}, wire_api={cfg.wire_api}")

    result = await with_retry(call)
    usage = result.get("usage") or {}
    result["meta"] = {
        **result.get("meta", {}),
        **result.get("provider_meta", {}),
        "agent_name": agent_name,
        "phase": phase,
        "elapsed_seconds": round(time.time() - started_at, 3),
        "model": cfg.model,
        "provider_id": cfg.provider_id,
        "usage": usage,
    }
    return result
