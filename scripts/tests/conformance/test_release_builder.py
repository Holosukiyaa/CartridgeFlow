import json
import os
import stat
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import build_release_archive, extract_release_payload, inspect_release_archive
from core.protocol.release_signing import ensure_development_signing_identity, generate_signing_identity, verify_signature_metadata


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
    @unittest.skipIf(os.name == "nt", "POSIX file modes are not enforced on Windows")
    def test_development_signing_material_is_owner_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ensure_development_signing_identity(root, "demo.publisher")
            private_files = list(root.rglob("*.pem")) + list(root.rglob("trusted_publishers.json"))

            self.assertEqual(2, len(private_files))
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in private_files))

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

    def test_trusted_signer_allows_payload_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            write_source(source)
            identity = generate_signing_identity("demo.publisher.development")
            experience, delivery = public_contracts()
            result = build_release_archive(
                source,
                root / "daily.cf-release.zip",
                publisher_id="demo.publisher",
                experience=experience,
                delivery=delivery,
                signing_identity=identity,
            )
            import base64

            trusted = {identity.key_id: base64.b64encode(identity.public_key).decode("ascii")}
            inspection = inspect_release_archive(result["archive"], trusted_keys=trusted)
            self.assertTrue(inspection["activation_allowed"], inspection["report"])
            staged = extract_release_payload(result["archive"], root / "staged", trusted_keys=trusted)
            self.assertEqual("dev.release-demo", json.loads((Path(staged["payload_path"]) / "manifest.json").read_text(encoding="utf-8"))["id"])

    def test_untrusted_or_tampered_signature_blocks_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            write_source(source)
            identity = generate_signing_identity("demo.publisher.development")
            experience, delivery = public_contracts()
            result = build_release_archive(
                source,
                root / "daily.cf-release.zip",
                publisher_id="demo.publisher",
                experience=experience,
                delivery=delivery,
                signing_identity=identity,
            )
            self.assertFalse(inspect_release_archive(result["archive"])["activation_allowed"])
            with zipfile.ZipFile(result["archive"]) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            release = json.loads(files["release.manifest.json"].decode("utf-8"))
            metadata = json.loads(files["signatures/publisher.ed25519.json"].decode("utf-8"))
            metadata["signature"] = "A" * len(metadata["signature"])
            files["signatures/publisher.ed25519.json"] = json.dumps(metadata).encode("utf-8")
            report = verify_signature_metadata(release, files)
            self.assertFalse(report["ok"])
            self.assertIn("cre_signature_verification_failed", {finding["code"] for finding in report["findings"]})


if __name__ == "__main__":
    unittest.main()
