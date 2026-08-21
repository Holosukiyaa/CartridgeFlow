import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol.release_builder import inspect_release_archive
from core.protocol.release_signing import trusted_public_keys
from core.studio.release_runtime import (
    CARTRIDGE_ID,
    format_sources,
    install_daily_brief,
    package_daily_brief,
    run_daily_brief_release,
)
from core.studio.run_desk import project_run_progress


class ReleaseRuntimeTests(unittest.TestCase):
    def test_pack_and_independent_unpack_use_the_same_signed_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = package_daily_brief(root, root / "packages")
            archive = root / "packages" / result["filename"]
            self.assertTrue(archive.is_file())
            self.assertTrue(result["signature_verified"])
            self.assertTrue(result["unpack"]["activation_allowed"])
            self.assertEqual("python.extract_release_payload", result["unpack"]["consumer"])
            payload_root = Path(result["unpack"]["payload_path"])
            manifest = json.loads((payload_root / "manifest.json").read_text(encoding="utf-8"))
            flow = json.loads((payload_root / "root.flow.json").read_text(encoding="utf-8"))
            self.assertEqual(CARTRIDGE_ID, manifest["id"])
            self.assertEqual("cartridgeflow.execution_plan.v1", flow["execution_plan"]["schema"])
            inspection = inspect_release_archive(archive, trusted_keys=trusted_public_keys(root))
            self.assertTrue(inspection["activation_allowed"])
            self.assertEqual(inspection["release"]["release"]["cartridge_id"], CARTRIDGE_ID)

    def test_install_copies_the_verified_payload_into_studio_shelves(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = install_daily_brief(root, root / "packages")
            installed = Path(result["installed_path"])
            self.assertTrue((installed / "manifest.json").is_file())
            self.assertTrue((installed / "root.flow.json").is_file())
            self.assertEqual(CARTRIDGE_ID, result["cartridge"]["id"])

    def test_orchestrator_runs_through_studio_cartridge_runner(self):
        items = [{"title": "Model release", "link": "https://example.com/a", "source": "Example", "published": "", "summary": "A note."}]
        runner = Mock()
        runner.create_run.return_value = {
            "run_id": "run_studio",
            "status": "completed",
            "delivery": {"primary_output": "brief", "result": "今日日报正文"},
            "error": None,
        }
        fetched = {
            "schema": "cartridgeflow.creator_trial_fetch.v1",
            "fetched_at": "2026-08-20T00:00:00+00:00",
            "feeds": [{"id": "hn-ai", "name": "Hacker News · AI", "url": "https://hnrss.org/newest?q=AI"}],
            "warnings": [],
            "items": items,
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch("core.studio.release_runtime.fetch_feeds", return_value=fetched):
            payload = run_daily_brief_release(temp_dir, runner)
        self.assertEqual(["pack", "unpack", "install", "fetch", "run"], [step["id"] for step in payload["steps"]])
        self.assertTrue(all(step["status"] == "ok" for step in payload["steps"]))
        self.assertEqual("studio", payload["runtime"]["id"])
        self.assertEqual("今日日报正文", payload["digest"]["body"])
        runner.create_run.assert_called_once()
        self.assertEqual(CARTRIDGE_ID, runner.create_run.call_args.args[0])
        self.assertIn("Model release", runner.create_run.call_args.args[1]["sources"])

    def test_format_sources_keeps_public_item_facts(self):
        text = format_sources([{"title": "Alpha", "source": "HN", "link": "https://example.com/a", "summary": "Note", "published": "today"}])
        self.assertIn("Alpha", text)
        self.assertIn("https://example.com/a", text)

    def test_progress_follows_process_nodes(self):
        flow = {
            "start": "start",
            "states": {
                "start": {"type": "control"},
                "collect": {"type": "process", "display_name": "采集"},
                "write": {"type": "process", "display_name": "写作"},
                "complete": {"type": "terminal"},
            },
            "execution_plan": {
                "entry": "start",
                "edges": [
                    {"kind": "sequence", "from": "start", "to": "collect"},
                    {"kind": "sequence", "from": "collect", "to": "write"},
                    {"kind": "sequence", "from": "write", "to": "complete"},
                ],
            },
        }
        progress = project_run_progress(
            {"status": "running", "current_state": "write"},
            flow,
            [{"type": "state_entered", "state": "collect"}, {"type": "lab_node_completed", "state": "collect"}],
        )
        self.assertEqual(["采集", "写作"], [item["label"] for item in progress["steps"]])
        self.assertEqual("running", progress["steps"][1]["status"])
        self.assertGreater(progress["percent"], 0)
        self.assertLess(progress["percent"], 100)


if __name__ == "__main__":
    unittest.main()
