from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import (
    ProtocolKnowledgeRegistry,
    ProtocolSource,
    build_protocol_knowledge_registry,
    load_protocol_registry_lock,
    resolve_protocol_registry,
)


class ProtocolKnowledgeRegistryTests(unittest.TestCase):
    def test_product_uses_queryable_read_only_registry_from_pinned_source(self):
        target = resolve_protocol_registry(ROOT)
        lock = load_protocol_registry_lock(ROOT)
        self.assertEqual("cartridgeflow.product_protocol_registry_lock.v2", lock["schema"])
        self.assertEqual("current", lock["runtime_source_id"])
        self.assertEqual(40, len(lock["repository"]["commit"]))
        self.assertEqual(
            {"current", "temp-runtime"},
            {item["source_id"] for item in lock["sources"]},
        )

        with ProtocolKnowledgeRegistry(target) as registry:
            summary = registry.summary()
            self.assertEqual(2, summary["source_count"])
            self.assertGreater(summary["release_count"], 40)
            self.assertGreater(summary["artifact_count"], summary["release_count"])
            self.assertGreater(summary["section_count"], 3000)
            self.assertEqual(1, summary["implementation_count"])
            self.assertGreater(summary["evidence_count"], 10)
            self.assertGreater(summary["finding_count"], 0)
            self.assertEqual(
                {"protocol_identity_collision"},
                {item["finding_type"] for item in registry.findings(severity="blocker")},
            )
            release = registry.get_release("current", "CF-FARP", "1.1")
            self.assertIsNotNone(release)
            self.assertEqual("current", release["lifecycle"])
            self.assertIsNotNone(
                registry.get_release("temp-runtime", "CF-FARP", "1.1")
            )
            self.assertTrue(registry.search("CartridgeFlow", source_id="current"))
            self.assertTrue(registry.search("CartridgeFlow", source_id="temp-runtime"))
            evidence_artifact = registry.connection.execute(
                "SELECT media_type, byte_size, length(content), text_content "
                "FROM artifact WHERE source_id = 'current' AND artifact_path = 'config/base/capability_evidence.json'"
            ).fetchone()
            self.assertTrue(evidence_artifact["media_type"].endswith("+zlib"))
            self.assertGreater(evidence_artifact["byte_size"], evidence_artifact["length(content)"])
            self.assertIsNone(evidence_artifact["text_content"])
            evidence_source = registry.artifact_json(
                "current", "config/base/capability_evidence.json"
            )
            self.assertEqual("cartridgeflow.capability_evidence.v1", evidence_source["schema"])
            evidence_row = registry.connection.execute(
                "SELECT failure_tests_json FROM implementation_evidence "
                "WHERE evidence_id = 'delivery_readiness'"
            ).fetchone()
            failure_tests = json.loads(evidence_row["failure_tests_json"])
            self.assertEqual(
                {
                    "owner": "test_protocol_certification.ProtocolCertificationConformanceTest",
                    "case": "legacy_manifest_cannot_be_certified",
                },
                failure_tests[0],
            )
            with self.assertRaises(sqlite3.OperationalError):
                registry.connection.execute(
                    "INSERT INTO registry_metadata(key, value) VALUES ('forbidden', 'write')"
                )

    def test_federated_registry_quarantines_same_identity_with_different_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = base / "first"
            second = base / "second"
            self._write_source(first, "First semantics")
            self._write_source(second, "Second semantics")
            target = base / "registry.sqlite"

            report = build_protocol_knowledge_registry(
                target,
                [ProtocolSource("first", first), ProtocolSource("second", second)],
            )

            self.assertEqual({"blocker": 1}, report.finding_counts)
            with ProtocolKnowledgeRegistry(target) as registry:
                findings = registry.findings(severity="blocker")
                self.assertEqual(1, len(findings))
                self.assertEqual("protocol_identity_collision", findings[0]["finding_type"])
                self.assertEqual("TEST-PROTOCOL", findings[0]["protocol_id"])
                identity = registry.connection.execute(
                    "SELECT source_count, distinct_bundle_count FROM release_identity WHERE protocol_id = 'TEST-PROTOCOL' AND version = '1'"
                ).fetchone()
                self.assertEqual((2, 2), tuple(identity))

    def _write_source(self, root: Path, specification: str) -> None:
        release_dir = root / "protocol" / "test" / "1"
        catalog_dir = root / "protocol" / "catalog"
        release_dir.mkdir(parents=True)
        catalog_dir.mkdir(parents=True)
        manifest = {
            "schema": "cartridgeflow.protocol_release_manifest.v1",
            "releases": [
                {
                    "id": "TEST-PROTOCOL",
                    "version": "1",
                    "lifecycle": "current",
                    "registry": "test/1/release.json",
                }
            ],
        }
        (catalog_dir / "release_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (release_dir / "release.json").write_text(
            json.dumps(
                {
                    "id": "TEST-PROTOCOL",
                    "version": "1",
                    "name": "Test Protocol",
                    "status": "active",
                    "document": "protocol/test/1/specification.md",
                }
            ),
            encoding="utf-8",
        )
        (release_dir / "specification.md").write_text(
            f"# Test Protocol\n\n## Semantics\n\n{specification}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
