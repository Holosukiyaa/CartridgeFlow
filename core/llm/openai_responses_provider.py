from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

from .config import ModelConfig
from .errors import LLMError


STREAM_CHUNK_TIMEOUT = 60
STREAM_TOTAL_TIMEOUT = 180


async def openai_responses(
    cfg: ModelConfig,
    messages: list[dict],
    tools: list[dict] | None,
    on_token: Callable[[str], None] | None,
    on_usage: Callable[[int, int], None] | None = None,
) -> dict:
    from openai import AsyncOpenAI

    async with AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout) as client:
        kwargs = {
            "model": cfg.model,
            "input": responses_input(messages),
            "temperature": cfg.temperature,
            "max_output_tokens": cfg.max_tokens,
        }
        converted_tools = responses_tools(tools or [])
        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = "auto"

        if on_token:
            kwargs["stream"] = True
            stream = await client.responses.create(**kwargs)
            return await _stream_responses(stream, on_token, on_usage)

        response = await client.responses.create(**kwargs)
        return response_result(response, on_usage)


def responses_input(messages: list[dict]) -> list[dict]:
    items: list[dict] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        if role == "tool":
            call_id = str(message.get("tool_call_id") or message.get("call_id") or "").strip()
            if not call_id:
                raise ValueError("Responses tool output requires tool_call_id")
            items.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": _string_value(message.get("content")),
            })
            continue

        if role not in {"user", "assistant", "system", "developer"}:
            role = "user"
        content = response_content(message.get("content"))
        if content not in ("", []):
            items.append({"role": role, "content": content})

        if role == "assistant":
            for tool_call in message.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                call_id = str(tool_call.get("id") or tool_call.get("call_id") or "").strip()
                name = str(function.get("name") or tool_call.get("name") or "").strip()
                if not call_id or not name:
                    continue
                items.append({
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": _string_value(function.get("arguments") or tool_call.get("arguments") or "{}"),
                })
    return items


def response_content(content) -> str | list[dict]:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _string_value(content)

    converted = []
    for block in content:
        if isinstance(block, str):
            converted.append({"type": "input_text", "text": block})
            continue
        if not isinstance(block, dict):
            converted.append({"type": "input_text", "text": _string_value(block)})
            continue
        block_type = str(block.get("type") or "text")
        if block_type in {"text", "input_text", "output_text"}:
            converted.append({"type": "input_text", "text": str(block.get("text") or "")})
            continue
        if block_type in {"image_url", "input_image"}:
            image = block.get("image_url")
            if isinstance(image, dict):
                url = str(image.get("url") or image.get("image_url") or "")
                detail = str(image.get("detail") or block.get("detail") or "auto")
            else:
                url = str(image or block.get("url") or "")
                detail = str(block.get("detail") or "auto")
            if not url:
                raise ValueError("Responses image input requires image_url")
            item = {"type": "input_image", "image_url": url}
            if detail in {"auto", "low", "high"}:
                item["detail"] = detail
            converted.append(item)
            continue
        if block_type == "input_file":
            item = {"type": "input_file"}
            for field in ("file_id", "file_data", "file_url", "filename"):
                if block.get(field):
                    item[field] = block[field]
            converted.append(item)
            continue
        raise ValueError(f"Unsupported Responses content block: {block_type}")
    return converted


def responses_tools(tools: list[dict]) -> list[dict]:
    converted = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        item = {
            "type": "function",
            "name": name,
            "parameters": function.get("parameters") if isinstance(function.get("parameters"), dict) else {"type": "object", "properties": {}},
        }
        if function.get("description"):
            item["description"] = str(function["description"])
        if "strict" in function:
            item["strict"] = bool(function["strict"])
        converted.append(item)
    return converted


def response_result(response, on_usage: Callable[[int, int], None] | None = None) -> dict:
    if isinstance(response, str):
        snippet = response[:200].replace("\n", " ").strip()
        raise LLMError(f"Responses API returned text instead of a response object: {snippet}", retryable=False)

    content = str(getattr(response, "output_text", None) or "")
    tool_calls = []
    if not content:
        content = _output_text(getattr(response, "output", None) or [])
    for item in getattr(response, "output", None) or []:
        if _field(item, "type") != "function_call":
            continue
        call_id = str(_field(item, "call_id") or _field(item, "id") or "")
        tool_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": str(_field(item, "name") or ""),
                "arguments": str(_field(item, "arguments") or "{}"),
            },
        })

    usage = _usage(getattr(response, "usage", None))
    if on_usage and usage:
        on_usage(usage["prompt_tokens"], usage["completion_tokens"])
    status = str(getattr(response, "status", None) or "completed")
    result = {
        "role": "assistant",
        "content": content,
        "provider_meta": {
            "finish_reason": status,
            "response_id": str(getattr(response, "id", None) or ""),
            "reasoning_content_length": 0,
        },
    }
    if usage:
        result["usage"] = usage
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


async def _stream_responses(stream, on_token: Callable[[str], None], on_usage: Callable[[int, int], None] | None) -> dict:
    started_at = time.time()
    content = ""
    tool_calls: dict[str, dict] = {}
    output_index_keys: dict[int, str] = {}
    announced: set[str] = set()
    final_response = None
    try:
        while True:
            try:
                event = await asyncio.wait_for(stream.__anext__(), timeout=STREAM_CHUNK_TIMEOUT)
            except StopAsyncIteration:
                break
            if time.time() - started_at > STREAM_TOTAL_TIMEOUT:
                raise TimeoutError(f"Stream total timeout: {STREAM_TOTAL_TIMEOUT}s exceeded")
            event_type = str(_field(event, "type") or "")
            if event_type == "response.output_text.delta":
                delta = str(_field(event, "delta") or "")
                content += delta
                on_token(delta)
            elif event_type in {"response.output_item.added", "response.output_item.done"}:
                item = _field(event, "item")
                if _field(item, "type") == "function_call":
                    key = str(_field(item, "id") or _field(item, "call_id") or _field(event, "output_index") or len(tool_calls))
                    output_index = _field(event, "output_index")
                    if isinstance(output_index, int):
                        output_index_keys[output_index] = key
                    call = tool_calls.setdefault(key, {
                        "id": str(_field(item, "call_id") or _field(item, "id") or key),
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    call["function"]["name"] = str(_field(item, "name") or call["function"]["name"])
                    arguments = str(_field(item, "arguments") or "")
                    if event_type.endswith(".done") or not call["function"]["arguments"]:
                        call["function"]["arguments"] = arguments
                    if call["function"]["name"] and key not in announced:
                        on_token(f"\n[正在调用工具: {call['function']['name']}...]")
                        announced.add(key)
            elif event_type == "response.function_call_arguments.delta":
                item_id = str(_field(event, "item_id") or "")
                output_index = _field(event, "output_index")
                key = item_id or (output_index_keys.get(output_index) if isinstance(output_index, int) else None)
                key = key or str(output_index if output_index is not None else len(tool_calls))
                call = tool_calls.setdefault(key, {
                    "id": item_id or key,
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                })
                call["function"]["arguments"] += str(_field(event, "delta") or "")
            elif event_type in {"response.completed", "response.incomplete", "response.failed"}:
                final_response = _field(event, "response")
    except (TimeoutError, asyncio.TimeoutError):
        if not content and not tool_calls:
            raise

    usage = _usage(_field(final_response, "usage")) if final_response is not None else None
    if on_usage and usage:
        on_usage(usage["prompt_tokens"], usage["completion_tokens"])
    result = {
        "role": "assistant",
        "content": content,
        "provider_meta": {
            "finish_reason": str(_field(final_response, "status") or "completed"),
            "response_id": str(_field(final_response, "id") or ""),
            "reasoning_content_length": 0,
        },
    }
    if usage:
        result["usage"] = usage
    if tool_calls:
        result["tool_calls"] = list(tool_calls.values())
    return result


def _output_text(output) -> str:
    parts = []
    for item in output or []:
        if _field(item, "type") != "message":
            continue
        for block in _field(item, "content") or []:
            if _field(block, "type") in {"output_text", "text"} and _field(block, "text"):
                parts.append(str(_field(block, "text")))
            elif _field(block, "type") == "refusal" and _field(block, "refusal"):
                parts.append(str(_field(block, "refusal")))
    return "".join(parts)


def _usage(value) -> dict | None:
    if value is None:
        return None
    prompt = int(_field(value, "input_tokens") or _field(value, "prompt_tokens") or 0)
    completion = int(_field(value, "output_tokens") or _field(value, "completion_tokens") or 0)
    total = int(_field(value, "total_tokens") or prompt + completion)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def _field(value, name: str):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _string_value(value) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
