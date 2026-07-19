import asyncio
import time
from typing import Callable

from .config import ModelConfig
from .errors import LLMError

STREAM_CHUNK_TIMEOUT = 60
STREAM_TOTAL_TIMEOUT = 180


async def openai_chat(
    cfg: ModelConfig,
    messages: list[dict],
    tools: list[dict] | None,
    on_token: Callable[[str], None] | None,
    on_usage: Callable[[int, int], None] | None = None,
) -> dict:
    from openai import AsyncOpenAI

    async with AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout) as client:
        kwargs = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature, "max_tokens": cfg.max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if on_token:
            kwargs["stream"] = True
            try:
                kwargs["stream_options"] = {"include_usage": True}
            except Exception:
                pass
            return await _stream_chat(client, kwargs, on_token, on_usage)

        response = await client.chat.completions.create(**kwargs)

        # 某些非标准 API 网关可能返回字符串（如 HTML 错误页），需要防御
        if isinstance(response, str):
            snippet = response[:200].replace("\n", " ").strip()
            raise LLMError(
                f"API 返回了非预期格式（字符串而非 JSON 对象）。"
                f"请检查 base_url 是否正确（通常需要以 /v1 结尾）。"
                f"返回内容前 200 字：{snippet}",
                retryable=False,
            )

        if not hasattr(response, "choices") or not response.choices:
            raise LLMError(
                f"API 返回了无效响应：没有 choices 字段。response type={type(response).__name__}",
                retryable=False,
            )

        if on_usage and response.usage:
            on_usage(response.usage.prompt_tokens, response.usage.completion_tokens)
        choice = response.choices[0]
        message = choice.message
        result = {"role": "assistant", "content": message.content or ""}
        reasoning = getattr(message, "reasoning_content", None)
        result["provider_meta"] = {
            "finish_reason": getattr(choice, "finish_reason", None),
            "reasoning_content_length": len(reasoning) if isinstance(reasoning, str) else 0,
        }
        if response.usage:
            result["usage"] = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
            }
        if message.tool_calls:
            result["tool_calls"] = [
                {"id": item.id, "type": "function", "function": {"name": item.function.name, "arguments": item.function.arguments}}
                for item in message.tool_calls
            ]
        return result


async def _stream_chat(client, kwargs: dict, on_token: Callable[[str], None], on_usage: Callable[[int, int], None] | None) -> dict:
    started_at = time.time()
    stream = await client.chat.completions.create(**kwargs)

    # 防御：某些非标准 API 网关在流式模式下也可能返回字符串
    if isinstance(stream, str):
        snippet = stream[:200].replace("\n", " ").strip()
        raise LLMError(
            f"API 流式返回了非预期格式（字符串而非 stream 对象）。"
            f"请检查 base_url 是否正确（通常需要以 /v1 结尾）。"
            f"返回内容前 200 字：{snippet}",
            retryable=False,
        )

    content = ""
    tool_calls: dict[int, dict] = {}
    announced: set[int] = set()
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(stream.__anext__(), timeout=STREAM_CHUNK_TIMEOUT)
            except StopAsyncIteration:
                break
            if time.time() - started_at > STREAM_TOTAL_TIMEOUT:
                raise TimeoutError(f"Stream total timeout: {STREAM_TOTAL_TIMEOUT}s exceeded")
            if hasattr(chunk, "usage") and chunk.usage and on_usage:
                on_usage(chunk.usage.prompt_tokens, chunk.usage.completion_tokens)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content += delta.content
                on_token(delta.content)
            if delta.tool_calls:
                for item in delta.tool_calls:
                    index = item.index
                    if index not in tool_calls:
                        tool_calls[index] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    if item.id:
                        tool_calls[index]["id"] = item.id
                    if item.function and item.function.name:
                        tool_calls[index]["function"]["name"] += item.function.name
                    if item.function and item.function.arguments:
                        tool_calls[index]["function"]["arguments"] += item.function.arguments
                    if index not in announced and tool_calls[index]["function"]["name"]:
                        on_token(f"\n[正在调用工具: {tool_calls[index]['function']['name']}...]")
                        announced.add(index)
    except (TimeoutError, asyncio.TimeoutError):
        if not content and not tool_calls:
            raise
    result = {"role": "assistant", "content": content}
    if tool_calls:
        result["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
    return result
