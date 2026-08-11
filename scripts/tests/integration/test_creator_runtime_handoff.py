import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.protocol import inspect_release_archive
from core.protocol.flow_contract import validate_execution_plan_v1_flow_contract
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge, CreatorRuntimeBridgeError


SOURCE = {"id": "source.brief", "kind": "source", "digest": "a" * 64, "role": "approved", "remote_url": "https://source.example.test/brief"}
STEPS = [
    {"id": "research", "intent": "Research the approved brief.", "inputs": {}, "outputs": {}},
    {"id": "draft", "intent": "Draft the reviewed handoff.", "inputs": {}, "outputs": {}},
]


class CreatorRuntimeHandoffTests(unittest.TestCase):
    def _ready_store(self, root: Path, intent: str = "Create a handoff") -> AuthoringSessionStore:
        store = AuthoringSessionStore(root / "sessions")
        store.create("creator.session", "recipe.handoff", intent, STEPS, [SOURCE], {})
        proposal = store.propose("creator.session", [{
            "id": "connect", "target_id": "rel.research.draft", "operation": "connect_steps",
            "value": {"id": "rel.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"},
        }], author="creator", summary="Accept relationship", expected_revision=1)
        store.accept("creator.session", proposal["proposal_id"])
        store.freeze("creator.session", ["research", "draft"], author="creator", summary="Approved")
        return store

    def test_materializes_deterministic_signed_handoff_without_private_state(self):
        secret = "private-prompt-and-token-value"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._ready_store(root, intent=f"Do not package {secret}")
            bridge = CreatorRuntimeBridge(root, root / "packages")
            candidate = store.compile_candidate(store.get("creator.session"))
            before = store.get("creator.session")
            first = bridge.materialize(store, "creator.session", expected_revision=2, candidate=candidate)
            archive = root / "packages" / first["filename"]
            first_bytes = archive.read_bytes()
            second = bridge.materialize(store, "creator.session", expected_revision=2, candidate=candidate)

            self.assertEqual(first["release_id"], second["release_id"])
            self.assertEqual(first_bytes, archive.read_bytes())
            self.assertEqual(before, store.get("creator.session"))
            self.assertEqual("signed_handoff_ready", first["status"])
            self.assertEqual("CF-CRE@1", first["protocol"])
            self.assertEqual(
                {
                    "mode": "compatibility",
                    "production_eligible": False,
                    "reason": "explicit_presentation_contracts_absent",
                },
                first["distribution"],
            )
            self.assertTrue(first["signature"]["verified"])
            inspection = inspect_release_archive(archive)
            self.assertTrue(inspection["report"]["ok"], inspection["report"]["findings"])
            with zipfile.ZipFile(archive) as bundle:
                members = {name: bundle.read(name) for name in bundle.namelist()}
            self.assertNotIn("payload/contracts/settings.contract.json", members)
            self.assertNotIn("payload/settings/bindings.json", members)
            self.assertNotIn("payload/contracts/ui.contract.json", members)
            root_flow = json.loads(members["payload/root.flow.json"])
            self.assertFalse(validate_execution_plan_v1_flow_contract(root_flow, protocol_id="CF-FARP", protocol_version="1.1"))
            self.assertEqual(["rel.research.draft"], [item["id"] for item in root_flow["semantic_relationships"]])
            serialized = b"\n".join(members.values()).decode("utf-8", errors="replace")
            for forbidden in (secret, "creator.session", "https://", "remote_url", "authorization", "cookie", "local paths"):
                self.assertNotIn(forbidden, serialized.lower())

    def test_rejects_stale_candidate_missing_or_invalid_freezes_without_package_or_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthoringSessionStore(root / "sessions")
            store.create("creator.session", "recipe.handoff", "Create a handoff", STEPS, [SOURCE], {})
            bridge = CreatorRuntimeBridge(root, root / "packages")
            candidate = store.compile_candidate(store.get("creator.session"))
            before = store.get("creator.session")
            with self.assertRaises(CreatorRuntimeBridgeError) as blocked:
                bridge.materialize(store, "creator.session", expected_revision=1, candidate=candidate)
            self.assertEqual("CREATOR_HANDOFF_DESIGN_BLOCKED", blocked.exception.code)
            self.assertEqual(before, store.get("creator.session"))
            self.assertFalse((root / "packages").exists())

            ready_root = root / "ready"
            ready = self._ready_store(ready_root)
            bridge = CreatorRuntimeBridge(ready_root, ready_root / "packages")
            valid = ready.compile_candidate(ready.get("creator.session"))
            before = ready.get("creator.session")
            with self.assertRaises(CreatorRuntimeBridgeError) as stale_revision:
                bridge.materialize(ready, "creator.session", expected_revision=1, candidate=valid)
            self.assertEqual("CREATOR_HANDOFF_REVISION_STALE", stale_revision.exception.code)
            stale = {**valid, "digest": "0" * 64}
            with self.assertRaises(CreatorRuntimeBridgeError) as mismatch:
                bridge.materialize(ready, "creator.session", expected_revision=2, candidate=stale)
            self.assertEqual("CREATOR_HANDOFF_CANDIDATE_MISMATCH", mismatch.exception.code)
            self.assertEqual(before, ready.get("creator.session"))
            self.assertFalse((ready_root / "packages").exists())

            state = ready.get("creator.session")
            state["freezes"][0]["digest"] = "0" * 64
            (ready_root / "sessions" / "creator.session.json").write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(CreatorRuntimeBridgeError) as invalid:
                bridge.materialize(ready, "creator.session", expected_revision=2, candidate=valid)
            self.assertEqual("CREATOR_HANDOFF_FREEZE_INVALID", invalid.exception.code)
            self.assertFalse((ready_root / "packages").exists())

    def test_rejects_cyclic_relationship_topology_and_tampered_archive_signature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthoringSessionStore(root / "sessions")
            store.create("creator.session", "recipe.handoff", "Create a handoff", STEPS, [SOURCE], {})
            changes = [
                {"id": "forward", "target_id": "rel.research.draft", "operation": "connect_steps", "value": {"id": "rel.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"}},
                {"id": "backward", "target_id": "rel.draft.research", "operation": "connect_steps", "value": {"id": "rel.draft.research", "from_step_id": "draft", "to_step_id": "research", "relation": "uses"}},
            ]
            proposal = store.propose("creator.session", changes, author="creator", summary="Accept cycle", expected_revision=1)
            store.accept("creator.session", proposal["proposal_id"])
            store.freeze("creator.session", ["research", "draft"], author="creator", summary="Approved")
            bridge = CreatorRuntimeBridge(root, root / "packages")
            with self.assertRaises(CreatorRuntimeBridgeError) as topology:
                bridge.materialize(store, "creator.session", expected_revision=2, candidate=store.compile_candidate(store.get("creator.session")))
            self.assertEqual("CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE", topology.exception.code)
            self.assertFalse((root / "packages").exists())

            valid_root = root / "valid"
            store = self._ready_store(valid_root)
            bridge = CreatorRuntimeBridge(valid_root, valid_root / "packages")
            result = bridge.materialize(store, "creator.session", expected_revision=2, candidate=store.compile_candidate(store.get("creator.session")))
            archive = valid_root / "packages" / result["filename"]
            with zipfile.ZipFile(archive) as source:
                files = {name: source.read(name) for name in source.namelist()}
            signature = json.loads(files["signatures/publisher.ed25519.json"])
            signature["signature"] = "A" * len(signature["signature"])
            files["signatures/publisher.ed25519.json"] = json.dumps(signature).encode("utf-8")
            tampered = root / "tampered.zip"
            with zipfile.ZipFile(tampered, "w") as output:
                for name, content in files.items():
                    output.writestr(name, content)
            inspection = inspect_release_archive(tampered)
            self.assertFalse(inspection["report"]["ok"])
            self.assertIn("cre_signature_verification_failed", {item["code"] for item in inspection["report"]["findings"]})


if __name__ == "__main__":
    unittest.main()
