import json
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import build_release_archive, inspect_release_archive


def public_contracts():
    return (
        {
            "schema": "cartridgeflow.cartridge_experience.v1",
            "product": {"name": "每日摘要", "category": "content"},
            "inputs": [{"id": "topic", "label": "主题", "type": "string", "required": True}],
            "stages": [{"id": "prepare", "label": "准备"}, {"id": "deliver", "label": "交付"}],
        },
        {
            "schema": "cartridgeflow.delivery_contract.v1",
            "primary_artifacts": [{"id": "brief", "label": "日报", "mime_types": ["text/markdown"]}],
            "attachments": [],
            "revision": {"mode": "new_run"},
            "delivery_states": ["produced", "delivered", "failed"],
        },
    )


def write_source(path: Path):
    (path / "assets").mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({
        "id": "dev.release-demo", "version": "0.1.0", "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
    }), encoding="utf-8")
    (path / "root.flow.json").write_text(json.dumps({"protocol": {"id": "CF-FARP", "version": "0.9"}}), encoding="utf-8")
    (path / "assets" / "readme.txt").write_text("release fixture", encoding="utf-8")


class ReleaseBuilderTests(unittest.TestCase):
    def test_builds_real_archive_that_runtime_can_stage_without_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            write_source(source)
            experience, delivery = public_contracts()
            result = build_release_archive(source, root / "daily.cf-release.zip", publisher_id="demo.publisher", experience=experience, delivery=delivery)

            self.assertTrue(Path(result["archive"]).is_file())
            self.assertEqual("validated_pending_install", result["status"])
            self.assertFalse(result["activation_allowed"])
            inspection = inspect_release_archive(result["archive"])
            self.assertTrue(inspection["report"]["ok"], inspection["report"]["findings"])
            self.assertEqual("每日摘要", inspection["public_contracts"]["experience"]["product"]["name"])

    def test_archive_reader_rejects_duplicate_members_before_contract_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            write_source(source)
            experience, delivery = public_contracts()
            result = build_release_archive(source, root / "daily.cf-release.zip", publisher_id="demo.publisher", experience=experience, delivery=delivery)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(result["archive"], "a") as archive:
                    archive.writestr("payload/manifest.json", b"tampered")

            inspection = inspect_release_archive(result["archive"])
            self.assertFalse(inspection["report"]["ok"])
            self.assertIn("cre_archive_duplicate_path", {item["code"] for item in inspection["report"]["findings"]})

    def test_builder_rejects_local_runtime_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            write_source(source)
            (source / "run.log").write_text("not portable", encoding="utf-8")
            experience, delivery = public_contracts()
            with self.assertRaisesRegex(ValueError, "non-portable"):
                build_release_archive(source, root / "daily.cf-release.zip", publisher_id="demo.publisher", experience=experience, delivery=delivery)


if __name__ == "__main__":
    unittest.main()
