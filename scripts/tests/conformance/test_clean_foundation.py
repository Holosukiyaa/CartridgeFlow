from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_SOURCE_ID,
    CleanFoundationProjectionError,
    CleanFoundationProjector,
)


class CleanFoundationProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ROOT / "config" / "protocol" / "protocol-registry.sqlite"
        cls.projector = CleanFoundationProjector(ROOT, registry_path=cls.registry)

    def test_verified_implementation_and_v4_lock_cover_all_8_foundation_contracts(self):
        envelopes = self.projector.implementation(
            implementation_id="cartridgeflow.reference-dev",
            supported_targets=["python", "go"],
            validator_ref="scripts/validate_clean_protocol.py",
        )
        envelopes += self.projector.conformance(
            result="pass",
            finding_codes=["CF-FOUNDATION.CONFORMANCE.PASS"],
            evidence_refs=["test:clean-protocol", "test:desktop-runner"],
        )
        envelopes += self.projector.publication_lock(self._v4_lock())
        envelopes.append(
            self.projector.change(
                target_version="1.0.0",
                compatibility="major",
                impact="Replaces the unified-v1 product boundary with clean-v1.",
            )
        )
        expected = {
            "cartridgeflow.foundation.implementation", "cartridgeflow.foundation.support",
            "cartridgeflow.foundation.conformance-report", "cartridgeflow.foundation.finding",
            "cartridgeflow.foundation.evidence", "cartridgeflow.governance.protocol-release",
            "cartridgeflow.governance.registry-lock", "cartridgeflow.governance.change",
        }
        self.assertEqual(expected, {item["contract_id"] for item in envelopes})

    def test_checked_in_v3_lock_cannot_prove_clean_v1_publication(self):
        lock = self._v4_lock()
        lock["schema"] = "cartridgeflow.product_protocol_registry_lock.v3"
        with self.assertRaises(CleanFoundationProjectionError) as error:
            self.projector.publication_lock(lock)
        self.assertEqual("clean_foundation_lock_generation_invalid", error.exception.code)

    def test_lock_rejects_multiple_or_wrong_authoritative_sources(self):
        lock = self._v4_lock()
        lock["sources"].append(dict(lock["sources"][0]))
        with self.assertRaises(CleanFoundationProjectionError) as multiple:
            self.projector.publication_lock(lock)
        self.assertEqual("clean_foundation_lock_source_invalid", multiple.exception.code)
        lock = self._v4_lock()
        lock["runtime_source_id"] = "unified"
        with self.assertRaises(CleanFoundationProjectionError) as wrong:
            self.projector.publication_lock(lock)
        self.assertEqual("clean_foundation_lock_source_invalid", wrong.exception.code)

    @staticmethod
    def _v4_lock() -> dict:
        return {
            "schema": "cartridgeflow.product_protocol_registry_lock.v4",
            "repository": {"url": "https://example.test/protocols.git", "commit": "a" * 40},
            "source_database": {"path": "protocol-source.sqlite", "database_sha256": "b" * 64, "logical_digest": "c" * 64},
            "runtime_source_id": CLEAN_SOURCE_ID,
            "sources": [
                {"source_id": CLEAN_SOURCE_ID, "manifest_digest": "d" * 64, "source_digest": "e" * 64}
            ],
            "registry": {"schema_version": "4", "logical_digest": "f" * 64, "database_sha256": "1" * 64, "path": "config/protocol/protocol-registry.sqlite"},
        }


if __name__ == "__main__":
    unittest.main()
