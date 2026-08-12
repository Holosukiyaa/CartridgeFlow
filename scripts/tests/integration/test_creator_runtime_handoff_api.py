import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.main import app
from core.protocol import inspect_release_archive, trusted_public_keys
from core.protocol.flow_contract import validate_execution_plan_v1_flow_contract
from core.studio.authoring_service import AuthoringSessionStore


SOURCE_URL = "https://private-source.example.test/creator-brief"
PRIVATE_PROMPT = "creator-private-prompt"
PRIVATE_LOCAL_PATH = "C:/creator/private/workspace"


class CreatorPackageApiAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_public_package_downloads_to_a_trusted_private_free_farp_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthoringSessionStore(root / "creator-sessions")
            with patch.object(backend_main, "authoring_sessions", store), patch.object(backend_main, "ROOT", root):
                created = self.client.post("/api/creator/authoring-sessions", json={
                    "session_id": "creator.private-session",
                    "recipe_id": "recipe.public-handoff",
                    "intent": f"Prepare a handoff without packaging {PRIVATE_PROMPT} or {PRIVATE_LOCAL_PATH}.",
                    "steps": [
                        {"id": "research", "intent": "Research the approved brief.", "inputs": {}, "outputs": {}},
                        {"id": "draft", "intent": "Draft the reviewed handoff.", "inputs": {}, "outputs": {}},
                    ],
                    "source_references": [{
                        "id": "source.private", "kind": "source", "digest": "a" * 64,
                        "role": "approved brief", "remote_url": SOURCE_URL,
                    }],
                    "bindings": {},
                })
                self.assertEqual(200, created.status_code, created.text)
                proposal = self.client.post(
                    "/api/creator/authoring-sessions/creator.private-session/proposals",
                    json={
                        "expected_revision": 1,
                        "summary": "Accept the reviewed relationship.",
                        "changes": [{
                            "id": "relationship.research.draft",
                            "target_id": "relationship.research.draft",
                            "operation": "connect_steps",
                            "value": {
                                "id": "relationship.research.draft",
                                "from_step_id": "research",
                                "to_step_id": "draft",
                                "relation": "informs",
                            },
                        }],
                    },
                )
                self.assertEqual(200, proposal.status_code, proposal.text)
                accepted = self.client.post(
                    f"/api/creator/authoring-sessions/creator.private-session/proposals/{proposal.json()['proposal']['proposal_id']}/accept",
                    json={},
                )
                self.assertEqual(200, accepted.status_code, accepted.text)
                frozen = self.client.post(
                    "/api/creator/authoring-sessions/creator.private-session/freeze",
                    json={"step_ids": ["research", "draft"], "summary": "Freeze accepted semantic steps."},
                )
                self.assertEqual(200, frozen.status_code, frozen.text)
                packaged = self.client.post(
                    "/api/creator/authoring-sessions/creator.private-session/package",
                    json={"expected_revision": 2},
                )
                self.assertEqual(200, packaged.status_code, packaged.text)
                response = packaged.json()
                self.assertEqual("ready", response["status"])
                self.assertTrue(response["signature_verified"])
                self.assertEqual({"schema", "status", "filename", "url", "signature_verified"}, set(response))
                self.assertNotRegex(json.dumps(response).lower(), r"install|execut|running|cartridge run")

                downloaded = self.client.get(response["url"])
                self.assertEqual(200, downloaded.status_code, downloaded.text)
                archive = root / "runtime-download.cf-cre.zip"
                archive.write_bytes(downloaded.content)
                verified = inspect_release_archive(archive, trusted_keys=trusted_public_keys(root))
                self.assertTrue(verified["activation_allowed"], verified["report"])
                self.assertTrue(verified["release"]["release_id"])

                with zipfile.ZipFile(archive) as bundle:
                    files = {name: bundle.read(name) for name in bundle.namelist()}
                root_flow = json.loads(files["payload/root.flow.json"])
                self.assertEqual([], validate_execution_plan_v1_flow_contract(root_flow, protocol_id="CF-FARP", protocol_version="1.1"))
                self.assertEqual(["relationship.research.draft"], [item["id"] for item in root_flow["semantic_relationships"]])
                serialized = b"\n".join(files.values()).decode("utf-8", errors="replace").lower()
                for private_fact in (
                    SOURCE_URL, PRIVATE_PROMPT, PRIVATE_LOCAL_PATH, "creator.private-session", "remote_url",
                    "creator-sessions", "developer_repository", "frontend_state", "credential", "chat", "prompt",
                ):
                    self.assertNotIn(private_fact.lower(), serialized)

                tampered = root / "runtime-download-tampered.cf-cre.zip"
                files["payload/root.flow.json"] = b'{"tampered":true}'
                with zipfile.ZipFile(tampered, "w") as output:
                    for name, content in files.items():
                        output.writestr(name, content)
                rejected = inspect_release_archive(tampered, trusted_keys=trusted_public_keys(root))
                self.assertFalse(rejected["activation_allowed"])
                findings = rejected["report"]["findings"]
                self.assertIn("cre_hashed_file_mismatch", {item["code"] for item in findings})


if __name__ == "__main__":
    unittest.main()
