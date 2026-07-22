import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.main import LLMTestPayload, test_llm_provider as call_llm_provider


PROVIDER = {
    "id": "local-test",
    "api_type": "openai",
    "wire_api": "chat_completions",
    "default_model": "test-model",
    "api_key": "secret-key",
    "base_url": "https://models.invalid/v1",
    "timeout": 5,
}


class LLMConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_marks_provider_as_tested(self):
        with (
            patch("core.llm.config_manager.get_provider", return_value=dict(PROVIDER)),
            patch("core.llm.config_manager.mark_provider_tested") as mark_tested,
            patch("core.llm.chat", new=AsyncMock(return_value={"content": "OK", "meta": {}})),
        ):
            result = await call_llm_provider(LLMTestPayload(provider_id="local-test"))

        self.assertTrue(result["ok"])
        mark_tested.assert_called_once_with("local-test", True)

    async def test_transport_failure_is_not_reported_as_success(self):
        with (
            patch("core.llm.config_manager.get_provider", return_value=dict(PROVIDER)),
            patch("core.llm.config_manager.mark_provider_tested") as mark_tested,
            patch("core.llm.chat", new=AsyncMock(side_effect=ConnectionError("connection refused"))),
        ):
            with self.assertRaises(HTTPException) as raised:
                await call_llm_provider(LLMTestPayload(provider_id="local-test"))

        self.assertEqual(502, raised.exception.status_code)
        self.assertIn("连接测试失败", raised.exception.detail)
        mark_tested.assert_called_once_with("local-test", False)

    async def test_incomplete_connection_is_rejected_before_calling_provider(self):
        incomplete = {**PROVIDER, "base_url": "", "api_key": "", "default_model": ""}
        chat = AsyncMock()
        with (
            patch("core.llm.config_manager.get_provider", return_value=incomplete),
            patch("core.llm.config_manager.mark_provider_tested") as mark_tested,
            patch("core.llm.chat", new=chat),
        ):
            with self.assertRaises(HTTPException) as raised:
                await call_llm_provider(LLMTestPayload(provider_id="local-test"))

        self.assertEqual(400, raised.exception.status_code)
        self.assertIn("URL、Key、默认模型", raised.exception.detail)
        chat.assert_not_awaited()
        mark_tested.assert_called_once_with("local-test", False)


if __name__ == "__main__":
    unittest.main()
