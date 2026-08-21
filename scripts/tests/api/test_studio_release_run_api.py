import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.main import app


class StudioReleaseRunApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runner = Mock()
        self.patches = [
            patch.object(backend_main, "ROOT", self.root),
            patch.object(backend_main, "runner", self.runner),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_run_daily_brief_uses_studio_runtime(self):
        payload = {
            "schema": "cartridgeflow.studio_release_run.v1",
            "steps": [
                {"id": "pack", "label": "打包签发 CF-CRE", "status": "ok", "detail": "studio.daily-brief-0.1.0.cf-cre.zip"},
                {"id": "unpack", "label": "按协议拆包验签", "status": "ok", "detail": "python.extract_release_payload"},
                {"id": "install", "label": "装载到 Studio 运行核", "status": "ok", "detail": "studio.daily-brief"},
                {"id": "fetch", "label": "获取已审核来源的最新内容", "status": "ok", "detail": "2 条"},
                {"id": "run", "label": "Studio 运行核执行并交付", "status": "ok", "detail": "completed"},
            ],
            "package": {"filename": "studio.daily-brief-0.1.0.cf-cre.zip", "signature_verified": True},
            "runtime": {"id": "studio"},
            "fetch": {"fetched_at": "", "feeds": [], "warnings": []},
            "items": [],
            "digest": {"headline": "日报", "body": "正文", "used_model": True, "model": "writer", "item_count": 2, "date": "今天"},
            "run": {"run_id": "abc", "status": "completed"},
        }
        with patch("backend.main.run_daily_brief_release", return_value=payload) as orchestrator:
            response = self.client.post("/api/studio/runtime/run-daily-brief", json={})
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("cartridgeflow.studio_release_run.v1", response.json()["schema"])
        self.assertEqual("studio", response.json()["runtime"]["id"])
        orchestrator.assert_called_once()
        self.assertIs(self.runner, orchestrator.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
