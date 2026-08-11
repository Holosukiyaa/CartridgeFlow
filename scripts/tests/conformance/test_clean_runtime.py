from __future__ import annotations

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
    CleanRuntimeProjector,
    DataContractError,
    ImplementationSource,
    publish_protocol_knowledge_registry,
)


class CleanRuntimeProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.registry = Path(cls._temporary.name) / "protocol-registry.sqlite"
        publish_protocol_knowledge_registry(
            cls.registry,
            ROOT / "protocol-source" / "protocol-source.sqlite",
            implementation_sources=[ImplementationSource(CLEAN_SOURCE_ID, ROOT)],
        )
        cls.projector = CleanRuntimeProjector(ROOT, registry_path=cls.registry)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_runtime_facts_cover_all_17_contracts(self):
        envelopes = self.projector.host(
            {
                "host_id": "desktop-runner-local",
                "target": "desktop",
                "protocols": ["CF-RUNTIME@1.0.0"],
                "capabilities": ["store", "interaction"],
            }
        )
        envelopes += self.projector.execution(
            {
                "run_id": "run-001", "state": "running", "node_id": "review", "sequence": 1,
                "request_id": "request-001", "requested_at": "2030-01-01T00:00:00Z",
                "requested_by": "operator", "error_code": "NODE_FAILED",
                "error_message": "Node failed", "retryable": False,
                "event_id": "event-001", "event_type": "node.completed",
            }
        )
        envelopes += self.projector.interaction(
            {
                "interaction_id": "interaction-001", "run_id": "run-001",
                "prompt": "Approve result", "expires_at": "2030-01-01T00:00:00Z",
            }
        )
        envelopes += self.projector.recovery(
            {
                "run_id": "run-001", "checkpoint_id": "checkpoint-001", "action": "resume",
                "request_id": "request-recovery", "requested_at": "2030-01-01T00:00:00Z",
                "requested_by": "operator", "status": "succeeded", "message": "Resumed",
            }
        )
        envelopes += self.projector.artifact(
            {
                "artifact_id": "artifact-001", "run_id": "run-001", "media_type": "text/plain",
                "digest": "a" * 64, "path": "outputs/result.txt",
            }
        )
        envelopes += self.projector.delivery(
            {
                "run_id": "run-001", "artifact_ids": ["artifact-001"], "receipt_id": "receipt-001",
                "result_status": "succeeded", "receipt_status": "delivered",
                "message": "Delivered", "delivered_at": "2030-01-01T00:00:00Z",
            }
        )
        expected = {
            "cartridgeflow.host.profile", "cartridgeflow.host.target", "cartridgeflow.host.compatibility",
            "cartridgeflow.execution.request", "cartridgeflow.execution.run",
            "cartridgeflow.execution.node-state", "cartridgeflow.execution.error",
            "cartridgeflow.execution.event", "cartridgeflow.interaction.pending",
            "cartridgeflow.interaction.response", "cartridgeflow.recovery.checkpoint",
            "cartridgeflow.recovery.request", "cartridgeflow.recovery.result",
            "cartridgeflow.artifact.record", "cartridgeflow.artifact.content-reference",
            "cartridgeflow.delivery.result", "cartridgeflow.delivery.receipt",
        }
        self.assertEqual(expected, {item["contract_id"] for item in envelopes})

    def test_runtime_projection_rejects_unknown_state_and_empty_artifact_set(self):
        with self.assertRaises(DataContractError):
            self.projector.execution(
                {
                    "run_id": "run-001", "state": "paused", "node_id": "review", "sequence": 1,
                    "request_id": "request-001", "requested_at": "now", "requested_by": "operator",
                    "error_code": "FAILED", "error_message": "Failed", "retryable": False,
                    "event_id": "event-001", "event_type": "node.failed",
                }
            )
        with self.assertRaises(DataContractError):
            self.projector.delivery(
                {
                    "run_id": "run-001", "artifact_ids": [], "receipt_id": "receipt-001",
                    "result_status": "failed", "receipt_status": "rejected",
                    "message": "No artifact", "delivered_at": "now",
                }
            )


if __name__ == "__main__":
    unittest.main()
