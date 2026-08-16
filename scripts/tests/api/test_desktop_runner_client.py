import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.desktop_runner import DesktopRunnerClient


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class DesktopRunnerClientTests(unittest.TestCase):
    def test_status_projects_only_safe_runner_facts(self):
        payload = {
            "ok": True, "runtime": "runtime-shell", "version": "0.6.0-SP", "busy": False,
            "cartridge": {"active": True, "cartridge_id": "demo", "name": "Demo", "version": "1.0.0", "package_path": "C:/private"},
            "settings": {"llm": {"api_key": "secret"}},
        }
        client = DesktopRunnerClient()
        with patch("backend.desktop_runner.urlopen", return_value=_Response(json.dumps(payload).encode("utf-8"))):
            result = client.status()
        self.assertTrue(result["available"])
        self.assertEqual({"id": "demo", "name": "Demo", "version": "1.0.0"}, result["cartridge"])
        self.assertNotIn("settings", result)
        self.assertNotIn("package_path", json.dumps(result))

    def test_status_does_not_invent_a_cartridge_for_an_empty_runner(self):
        payload = {
            "ok": True, "runtime": "runtime-shell", "version": "0.6.0-SP", "busy": False,
            "cartridge": {"active": False, "cartridge_id": "", "name": "", "version": ""},
        }
        with patch("backend.desktop_runner.urlopen", return_value=_Response(json.dumps(payload).encode("utf-8"))):
            result = DesktopRunnerClient().status()
        self.assertIsNone(result["cartridge"])

    def test_install_posts_the_signed_archive_as_multipart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "trial.cf-cre.zip"
            archive.write_bytes(b"signed-package")
            captured = {}

            def respond(request, **_kwargs):
                captured["content_type"] = request.headers["Content-type"]
                captured["body"] = request.data
                return _Response(json.dumps({"ok": True, "cartridge": {"id": "trial", "name": "Trial", "version": "1"}}).encode("utf-8"))

            with patch("backend.desktop_runner.urlopen", side_effect=respond):
                result = DesktopRunnerClient().install(archive)
            self.assertEqual("installed", result["status"])
            self.assertIn(b"signed-package", captured["body"])
            self.assertIn("multipart/form-data", captured["content_type"])

    def test_rejects_non_loopback_runner_urls(self):
        with self.assertRaises(ValueError):
            DesktopRunnerClient("https://runner.example.test")

    def test_install_projects_explicit_runner_trust_approval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "trial.cf-cre.zip"
            archive.write_bytes(b"signed-package")
            payload = {
                "ok": True, "status": "trust_required", "id": "a" * 32,
                "approval_url": "/?pending=" + "a" * 32,
                "publisher": {"id": "creator", "key_id": "creator.development", "fingerprint": "0123456789abcdef", "public_key": "private"},
                "cartridge": {"id": "trial", "name": "Trial", "version": "1.0.0"},
            }
            with patch("backend.desktop_runner.urlopen", return_value=_Response(json.dumps(payload).encode("utf-8"))):
                result = DesktopRunnerClient("http://127.0.0.1:18991").install(archive)
        self.assertEqual("trust_required", result["status"])
        self.assertEqual("http://127.0.0.1:18991/?pending=" + "a" * 32, result["runner_url"])
        self.assertNotIn("public_key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
