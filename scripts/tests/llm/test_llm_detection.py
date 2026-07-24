import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.llm.detection import LLMDetectionError, detect_model_connection


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, endpoint, *, headers):
        self.requests.append({"endpoint": endpoint, "headers": headers})
        status, payload = self.responses[endpoint]
        return httpx.Response(status, json=payload, request=httpx.Request("GET", endpoint))


class LlmDetectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_named_models_still_use_standard_text_profile(self):
        responses = {
            "https://models.test/models": (200, {"data": [{"id": "gpt-image-2"}]}),
            "https://models.test/v1/models": (200, {"data": [{"id": "gpt-image-2"}]}),
        }
        client = FakeClient(responses)
        with patch("core.llm.detection.httpx.AsyncClient", return_value=client):
            result = await detect_model_connection(base_url="https://models.test", api_key="secret")

        self.assertEqual("standard", result["provider"]["adapter_profile"])
        self.assertEqual("chat_completions", result["provider"]["wire_api"])
        self.assertEqual("gpt-image-2", result["provider"]["default_model"])
        self.assertEqual("https://models.test/v1", result["provider"]["base_url"])
        self.assertEqual(["text_reasoning"], result["provider"]["capabilities"])
        self.assertEqual(120, result["provider"]["timeout"])
        self.assertNotIn("secret", str(result))

    async def test_gpt_5_5_is_not_misidentified_as_an_image_extension(self):
        responses = {
            "https://models.test/models": (200, {"data": [{"id": "gpt-5.5"}]}),
            "https://models.test/v1/models": (404, {"error": {"message": "not found"}}),
        }
        with patch("core.llm.detection.httpx.AsyncClient", return_value=FakeClient(responses)):
            result = await detect_model_connection(base_url="https://models.test", api_key="secret")

        self.assertEqual("standard", result["provider"]["adapter_profile"])
        self.assertEqual("chat_completions", result["provider"]["wire_api"])
        self.assertEqual("https://models.test", result["provider"]["base_url"])
        self.assertEqual("medium", result["detection"]["confidence"])

    async def test_text_model_uses_standard_profile(self):
        responses = {
            "https://models.test/v1/models": (200, {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}),
            "https://models.test/models": (404, {"detail": "not found"}),
        }
        with patch("core.llm.detection.httpx.AsyncClient", return_value=FakeClient(responses)):
            result = await detect_model_connection(
                base_url="https://models.test/v1",
                api_key="secret",
                preferred_model="deepseek-reasoner",
            )

        self.assertEqual("standard", result["provider"]["adapter_profile"])
        self.assertEqual("chat_completions", result["provider"]["wire_api"])
        self.assertEqual("deepseek-reasoner", result["provider"]["default_model"])
        self.assertEqual("https://models.test/v1", result["provider"]["base_url"])

    async def test_authentication_failure_is_specific(self):
        responses = {
            "https://models.test/models": (401, {"error": {"message": "invalid token"}}),
            "https://models.test/v1/models": (401, {"error": {"message": "invalid token"}}),
        }
        with patch("core.llm.detection.httpx.AsyncClient", return_value=FakeClient(responses)):
            with self.assertRaises(LLMDetectionError) as raised:
                await detect_model_connection(base_url="https://models.test", api_key="bad-secret")

        self.assertEqual(401, raised.exception.status_code)
        self.assertIn("鉴权", str(raised.exception))
        self.assertNotIn("bad-secret", str(raised.exception))

    async def test_empty_model_list_is_rejected(self):
        responses = {
            "https://models.test/models": (200, {"data": []}),
            "https://models.test/v1/models": (200, {"data": []}),
        }
        with patch("core.llm.detection.httpx.AsyncClient", return_value=FakeClient(responses)):
            with self.assertRaises(LLMDetectionError) as raised:
                await detect_model_connection(base_url="https://models.test", api_key="secret")

        self.assertEqual(422, raised.exception.status_code)
        self.assertIn("没有返回可用模型", str(raised.exception))

    async def test_endpoint_reuses_stored_key_without_returning_it(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        detected = {
            "ok": True,
            "status": "detected",
            "provider": {"base_url": "https://models.test/v1", "default_model": "gpt-image-2"},
            "detection": {"models": ["gpt-image-2"]},
            "attempts": [],
        }
        with (
            patch("core.llm.config_manager.get_provider", return_value={
                "id": "saved", "base_url": "https://models.test", "api_key": "stored-secret", "default_model": "",
            }),
            patch("core.llm.detection.detect_model_connection", new=AsyncMock(return_value=detected)) as detect,
        ):
            response = TestClient(app).post("/api/llm/detect", json={"provider_id": "saved", "base_url": "https://models.test"})

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["used_stored_key"])
        self.assertNotIn("stored-secret", response.text)
        self.assertEqual("stored-secret", detect.await_args.kwargs["api_key"])

    async def test_opencode_import_is_text_first_and_keeps_model_candidates(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        content = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "openai": {
                    "options": {"baseURL": "https://models.test", "apiKey": "import-secret"},
                    "models": {"gpt-5.2": {"name": "GPT-5.2"}, "gpt-image-2": {"name": "Image"}},
                },
            },
        }
        detected = {
            "provider": {
                "name": "models · 文本模型", "api_type": "openai",
                "base_url": "https://models.test/v1", "default_model": "gpt-5.2",
                "wire_api": "chat_completions", "capabilities": ["text_reasoning"],
                "adapter_profile": "standard", "timeout": 120,
            },
            "detection": {
                "capability": "text_reasoning", "adapter_label": "文本模型", "confidence": "medium",
                "model_count": 1, "models": ["gpt-5.2"], "models_endpoint": "https://models.test/v1/models",
                "summary": "detected",
            },
        }
        saved = []

        def save(item):
            saved.append(item)
            return item

        with (
            patch("core.llm.detection.detect_model_connection", new=AsyncMock(return_value=detected)) as detect,
            patch("core.llm.config_manager.upsert_provider", side_effect=save),
        ):
            response = TestClient(app).post("/api/llm/import/opencode", json={"content": __import__("json").dumps(content)})

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(saved))
        self.assertEqual("standard", saved[0]["adapter_profile"])
        self.assertEqual("standard", saved[0]["adapter_profile"])
        self.assertEqual(["gpt-5.2", "gpt-image-2"], saved[0]["available_models"])
        self.assertTrue(saved[0]["enabled"])
        self.assertEqual("import-secret", detect.await_args.kwargs["api_key"])
        self.assertNotIn("import-secret", response.text)

    async def test_opencode_import_failure_does_not_save_partial_config(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        content = {"provider": {"openai": {"options": {"baseURL": "https://models.test", "apiKey": "secret"}, "models": {"model": {}}}}}
        failure = LLMDetectionError("upstream unavailable", status_code=503)
        with (
            patch("core.llm.detection.detect_model_connection", new=AsyncMock(side_effect=failure)),
            patch("core.llm.config_manager.upsert_provider") as save,
        ):
            response = TestClient(app).post("/api/llm/import/opencode", json={"content": __import__("json").dumps(content)})

        self.assertEqual(503, response.status_code)
        save.assert_not_called()
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()
