import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.llm.base import chat
from core.llm.config import ModelConfig
from core.llm.openai_responses_provider import (
    _stream_responses,
    openai_responses,
    response_result,
    responses_input,
    responses_tools,
)


class FakeStream:
    def __init__(self, events):
        self.events = iter(events)

    async def __anext__(self):
        try:
            return next(self.events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class LlmResponsesApiTest(unittest.TestCase):
    def config(self):
        return ModelConfig(
            provider_id="test-responses",
            api_type="openai",
            wire_api="responses",
            model="test-vision-model",
            api_key="test-key",
            base_url="https://example.test/v1",
            max_tokens=512,
        )

    def test_multimodal_messages_convert_to_responses_content(self):
        image = "data:image/png;base64,AAAA"
        converted = responses_input([
            {"role": "system", "content": "Review the image."},
            {"role": "user", "content": [
                {"type": "text", "text": "What is visible?"},
                {"type": "image_url", "image_url": {"url": image, "detail": "high"}},
            ]},
        ])
        self.assertEqual("Review the image.", converted[0]["content"])
        self.assertEqual("input_text", converted[1]["content"][0]["type"])
        self.assertEqual({"type": "input_image", "image_url": image, "detail": "high"}, converted[1]["content"][1])

    def test_chat_tool_history_converts_to_responses_items(self):
        converted = responses_input([
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "finish_task", "arguments": '{"summary":"done"}'},
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": "accepted"},
        ])
        self.assertEqual("function_call", converted[0]["type"])
        self.assertEqual("call_1", converted[0]["call_id"])
        self.assertEqual("function_call_output", converted[1]["type"])
        self.assertEqual("accepted", converted[1]["output"])
        tools = responses_tools([{
            "type": "function",
            "function": {"name": "finish_task", "description": "Finish", "parameters": {"type": "object"}},
        }])
        self.assertEqual("finish_task", tools[0]["name"])
        self.assertNotIn("function", tools[0])

    def test_response_result_preserves_text_usage_and_tool_calls(self):
        response = SimpleNamespace(
            id="resp_1",
            status="completed",
            output_text="done",
            usage=SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16),
            output=[SimpleNamespace(type="function_call", call_id="call_2", id="fc_2", name="finish_task", arguments="{}")],
        )
        usage = []
        result = response_result(response, lambda prompt, completion: usage.append((prompt, completion)))
        self.assertEqual("done", result["content"])
        self.assertEqual("call_2", result["tool_calls"][0]["id"])
        self.assertEqual({"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}, result["usage"])
        self.assertEqual([(12, 4)], usage)

    def test_stream_preserves_text_and_function_arguments(self):
        function_item = SimpleNamespace(type="function_call", id="fc_1", call_id="call_1", name="finish_task", arguments="")
        final = SimpleNamespace(
            id="resp_stream",
            status="completed",
            usage=SimpleNamespace(input_tokens=8, output_tokens=3, total_tokens=11),
        )
        stream = FakeStream([
            SimpleNamespace(type="response.output_text.delta", delta="OK"),
            SimpleNamespace(type="response.output_item.added", item=function_item, output_index=1),
            SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc_1", output_index=1, delta='{"summary":'),
            SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc_1", output_index=1, delta='"done"}'),
            SimpleNamespace(type="response.completed", response=final),
        ])
        tokens = []
        usage = []
        result = asyncio.run(_stream_responses(stream, tokens.append, lambda prompt, completion: usage.append((prompt, completion))))
        self.assertEqual("OK", result["content"])
        self.assertEqual('{"summary":"done"}', result["tool_calls"][0]["function"]["arguments"])
        self.assertEqual([(8, 3)], usage)

    def test_openai_responses_uses_responses_endpoint_and_converted_image(self):
        captured = {}
        response = SimpleNamespace(
            id="resp_live_shape",
            status="completed",
            output_text="OK",
            usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
            output=[],
        )

        class FakeResponses:
            async def create(self, **kwargs):
                captured.update(kwargs)
                return response

        class FakeClient:
            def __init__(self, **_kwargs):
                self.responses = FakeResponses()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        with patch("openai.AsyncOpenAI", FakeClient):
            result = asyncio.run(openai_responses(self.config(), [{
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
            }], None, None))
        self.assertEqual("OK", result["content"])
        self.assertEqual("input_image", captured["input"][0]["content"][0]["type"])
        self.assertEqual(512, captured["max_output_tokens"])

    def test_unified_chat_routes_responses_provider(self):
        expected = {"role": "assistant", "content": "routed"}
        with patch("core.llm.base.openai_responses", new=AsyncMock(return_value=expected)) as adapter:
            result = asyncio.run(chat(self.config(), [{"role": "user", "content": "hello"}]))
        self.assertEqual("routed", result["content"])
        adapter.assert_awaited_once()
        self.assertEqual("test-vision-model", result["meta"]["model"])


if __name__ == "__main__":
    unittest.main()
