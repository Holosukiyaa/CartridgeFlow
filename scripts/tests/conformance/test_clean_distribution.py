from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_SOURCE_ID,
    CleanDistributionProjectionError,
    CleanDistributionProjector,
    DataContractError,
    ImplementationSource,
    build_release_archive,
    publish_protocol_knowledge_registry,
)
from core.protocol.release_signing import generate_signing_identity
from core.studio.release import clean_release_contracts


class CleanDistributionProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.registry = cls.root / "protocol-registry.sqlite"
        publish_protocol_knowledge_registry(
            cls.registry,
            ROOT / "protocol-source" / "protocol-source.sqlite",
            implementation_sources=[ImplementationSource(CLEAN_SOURCE_ID, ROOT)],
        )
        source = cls.root / "source"
        (source / "assets").mkdir(parents=True)
        (source / "manifest.json").write_text(
            json.dumps({"id": "dev.clean-release", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (source / "root.flow.json").write_text(
            json.dumps({"protocol": {"id": "CF-FARP", "version": "1.0"}}),
            encoding="utf-8",
        )
        (source / "assets" / "readme.txt").write_text("clean release", encoding="utf-8")
        cls.identity = generate_signing_identity("dev.clean-publisher")
        cls.archive = cls.root / "clean.cf-cre.zip"
        build_release_archive(
            source,
            cls.archive,
            publisher_id="dev.clean-publisher",
            experience={
                "schema": "cartridgeflow.cartridge_experience.v1",
                "product": {"name": "Clean release", "category": "test"},
                "inputs": [{"id": "topic", "label": "Topic", "type": "string", "required": True}],
                "stages": [{"id": "prepare", "label": "Prepare"}],
            },
            delivery={
                "schema": "cartridgeflow.delivery_contract.v1",
                "primary_artifacts": [{"id": "result", "label": "Result", "mime_types": ["text/plain"]}],
                "attachments": [],
                "revision": {"mode": "new_run"},
                "delivery_states": ["produced", "delivered", "failed"],
            },
            signing_identity=cls.identity,
        )
        cls.trusted_keys = {
            cls.identity.key_id: base64.b64encode(cls.identity.public_key).decode("ascii")
        }
        cls.projector = CleanDistributionProjector(ROOT, registry_path=cls.registry)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_verified_release_and_installation_cover_all_15_distribution_contracts(self):
        envelopes = self.projector.archive(self.archive, trusted_keys=self.trusted_keys)
        envelopes += self.projector.installation(
            {
                "package_id": "dev.clean-release",
                "target": "desktop-runner",
                "plan_id": "install-001",
                "rollback": "enabled",
                "request_id": "request-001",
                "requested_at": "2030-01-01T00:00:00Z",
                "requested_by": "operator",
                "status": "succeeded",
                "message": "Installed and activated",
            }
        )
        expected = {
            "cartridgeflow.package.manifest", "cartridgeflow.package.content-entry",
            "cartridgeflow.package.dependency-lock", "cartridgeflow.package.entrypoint",
            "cartridgeflow.integrity.manifest", "cartridgeflow.integrity.signature-payload",
            "cartridgeflow.integrity.verification", "cartridgeflow.trust.publisher",
            "cartridgeflow.trust.signature", "cartridgeflow.trust.decision",
            "cartridgeflow.installation.request", "cartridgeflow.installation.plan",
            "cartridgeflow.installation.result", "cartridgeflow.exposure.experience",
            "cartridgeflow.exposure.delivery",
        }
        self.assertEqual(expected, {item["contract_id"] for item in envelopes})
        decision = next(item for item in envelopes if item["contract_id"] == "cartridgeflow.trust.decision")
        self.assertEqual("allow", decision["payload"]["decision"])

    def test_untrusted_signature_is_preserved_as_deny_not_static_failure(self):
        contracts = self.projector.archive(self.archive)
        decision = next(item for item in contracts if item["contract_id"] == "cartridgeflow.trust.decision")
        self.assertEqual("deny", decision["payload"]["decision"])

    def test_studio_release_entrypoint_projects_without_mutating_archive(self):
        before = self.archive.read_bytes()
        contracts = clean_release_contracts(
            self.archive,
            trusted_keys=self.trusted_keys,
            project_root=ROOT,
            registry_path=self.registry,
        )
        self.assertIn("cartridgeflow.package.manifest", {item["contract_id"] for item in contracts})
        self.assertEqual(before, self.archive.read_bytes())

    def test_invalid_archive_and_incomplete_installation_fail_closed(self):
        invalid = self.root / "invalid.zip"
        invalid.write_text("not a zip", encoding="utf-8")
        with self.assertRaises(CleanDistributionProjectionError) as archive_error:
            self.projector.archive(invalid)
        self.assertEqual("clean_distribution_archive_invalid", archive_error.exception.code)
        with self.assertRaises(DataContractError):
            self.projector.installation(
                {
                    "package_id": "dev.clean-release",
                    "target": "desktop-runner",
                    "plan_id": "install-001",
                    "rollback": "enabled",
                    "request_id": "request-001",
                    "requested_at": "2030-01-01T00:00:00Z",
                    "requested_by": "operator",
                    "status": "unknown",
                    "message": "No result",
                }
            )

    def test_install_intent_does_not_require_an_invented_result(self):
        envelopes = self.projector.installation_request(
            {
                "package_id": "dev.clean-release",
                "target": "desktop-runner",
                "plan_id": "install-001",
                "rollback": "enabled",
                "request_id": "request-001",
                "requested_at": "2030-01-01T00:00:00Z",
                "requested_by": "operator",
            }
        )
        self.assertEqual(
            ["cartridgeflow.installation.request", "cartridgeflow.installation.plan"],
            [item["contract_id"] for item in envelopes],
        )


if __name__ == "__main__":
    unittest.main()
