import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import build_release_archive


SPEC = importlib.util.spec_from_file_location("personal_runtime_demo", ROOT / "scripts" / "demo_personal_runtime.py")
runtime_demo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_demo)


class FakeRegistry:
    def __init__(self, root):
        self.root = Path(root)

    def get_cartridge(self, cartridge_id):
        return {"id": cartridge_id, "source": "installed"}


class FakeRunner:
    def __init__(self, root, registry):
        self.root = Path(root)

    def create_run(self, cartridge_id, inputs):
        return {
            "run_id": "run_personal_demo",
            "status": "completed",
            "artifacts": [{"name": "welcome.html", "type": "html"}],
        }


def _contracts():
    return (
        {
            "schema": "cartridgeflow.cartridge_experience.v1",
            "product": {"name": "Personal Runtime Demo", "category": "content"},
            "inputs": [],
            "stages": [{"id": "deliver", "label": "Deliver"}],
        },
        {
            "schema": "cartridgeflow.delivery_contract.v1",
            "primary_artifacts": [{"id": "brief", "label": "Brief", "mime_types": ["text/html"]}],
            "attachments": [],
            "revision": {"mode": "new_run"},
            "delivery_states": ["produced", "delivered", "failed"],
        },
    )


class PersonalRuntimeDemoTests(unittest.TestCase):
    def test_validated_release_is_installed_and_run_in_a_separate_host(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "manifest.json").write_text(json.dumps({"id": "demo.runtime", "version": "0.1.0"}), encoding="utf-8")
            (source / "root.flow.json").write_text(json.dumps({"protocol": {"id": "CF-FARP", "version": "0.9"}}), encoding="utf-8")
            experience, delivery = _contracts()
            archive = root / "demo.cf-release.zip"
            build_release_archive(source, archive, publisher_id="demo.publisher", experience=experience, delivery=delivery)

            with patch.object(runtime_demo, "CartridgeRegistry", FakeRegistry), patch.object(runtime_demo, "CartridgeRunner", FakeRunner):
                result = runtime_demo.run_personal_runtime_demo(archive, root / "personal-host", inputs={"title": "Demo"})

            host = root / "personal-host"
            self.assertTrue(result["ok"])
            self.assertEqual("completed", result["status"])
            self.assertTrue((host / result["installed_version"] / "manifest.json").is_file())
            self.assertTrue((host / result["active_release"]).is_file())
            self.assertFalse((host / ".data" / "user" / "dev_cartridges").exists())


if __name__ == "__main__":
    unittest.main()
