import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.main import app
from core.protocol.flow_contract import validate_execution_plan_v1_flow_contract
from core.studio.authoring_service import AuthoringSessionStore


TOOLKIT = Path(__file__).resolve().parents[3] / "demos" / "runtime-developer-toolkit" / "demo" / "run.mjs"
SOURCE_URL = "https://private-source.example.test/creator-brief"
PRIVATE_PROMPT = "creator-private-prompt"
PRIVATE_LOCAL_PATH = "C:/creator/private/workspace"


class CreatorRuntimeHandoffApiAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_public_api_handoff_downloads_to_a_trusted_private_free_farp_archive(self):
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
                    "source_references": [{"id": "source.private", "kind": "source", "digest": "a" * 64, "role": "approved brief", "remote_url": SOURCE_URL}],
                    "bindings": {},
                })
                self.assertEqual(200, created.status_code, created.text)
                proposal = self.client.post("/api/creator/authoring-sessions/creator.private-session/proposals", json={
                    "expected_revision": 1,
                    "summary": "Accept the reviewed relationship.",
                    "changes": [{
                        "id": "relationship.research.draft",
                        "target_id": "relationship.research.draft",
                        "operation": "connect_steps",
                        "value": {"id": "relationship.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"},
                    }],
                })
                self.assertEqual(200, proposal.status_code, proposal.text)
                accepted = self.client.post(
                    f"/api/creator/authoring-sessions/creator.private-session/proposals/{proposal.json()['proposal']['proposal_id']}/accept",
                    json={},
                )
                self.assertEqual(200, accepted.status_code, accepted.text)
                self.assertEqual(2, accepted.json()["creator"]["revision"])
                frozen = self.client.post("/api/creator/authoring-sessions/creator.private-session/freeze", json={
                    "step_ids": ["research", "draft"], "summary": "Freeze accepted semantic steps.",
                })
                self.assertEqual(200, frozen.status_code, frozen.text)
                candidate_response = self.client.post("/api/creator/authoring-sessions/creator.private-session/compile-candidate", json={"expected_revision": 2})
                self.assertEqual(200, candidate_response.status_code, candidate_response.text)
                candidate = candidate_response.json()["compile_candidate"]
                handoff = self.client.post("/api/creator/authoring-sessions/creator.private-session/runtime-handoff", json={
                    "expected_revision": 2, "compile_candidate": candidate,
                })
                self.assertEqual(200, handoff.status_code, handoff.text)
                response = handoff.json()
                self.assertEqual("signed_handoff_ready", response["status"])
                self.assertEqual("CF-CRE@1", response["protocol"])
                self.assertTrue(response["signature"]["verified"])
                self.assertEqual({"schema", "status", "protocol", "release_id", "filename", "lineage", "root_flow", "signature", "url"}, set(response))
                self.assertNotRegex(json.dumps(response).lower(), r"install|execut|running|cartridge run")

                downloaded = self.client.get(response["url"])
                self.assertEqual(200, downloaded.status_code, downloaded.text)
                self.assertEqual("application/zip", downloaded.headers["content-type"])
                archive = root / "runtime-download.cf-cre.zip"
                archive.write_bytes(downloaded.content)
                self.assertNotEqual((Path(__file__).resolve().parents[3] / "demos" / "runtime-developer-toolkit" / "samples").resolve(), archive.parent.resolve())
                trust = root / ".data" / "user" / "config" / "release_keys" / "trusted_publishers.json"
                self.assertTrue(trust.is_file())
                verified = subprocess.run(
                    ["node", str(TOOLKIT), "verify", str(archive), "--trust", str(trust)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(0, verified.returncode, verified.stderr)
                self.assertEqual(response["release_id"], json.loads(verified.stdout)["release_id"])

                with zipfile.ZipFile(archive) as bundle:
                    files = {name: bundle.read(name) for name in bundle.namelist()}
                root_flow = json.loads(files["payload/root.flow.json"])
                self.assertEqual([], validate_execution_plan_v1_flow_contract(root_flow, protocol_id="CF-FARP", protocol_version="1.1"))
                self.assertEqual("1.1", root_flow["protocol"]["version"])
                self.assertEqual(["relationship.research.draft"], [item["id"] for item in root_flow["semantic_relationships"]])
                serialized = b"\n".join(files.values()).decode("utf-8", errors="replace").lower()
                for private_fact in (SOURCE_URL, PRIVATE_PROMPT, PRIVATE_LOCAL_PATH, "creator.private-session", "remote_url", "creator-sessions", "developer_repository", "frontend_state", "credential", "chat", "prompt"):
                    self.assertNotIn(private_fact.lower(), serialized)
                forbidden_paths = ("chat", "conversation", "creator-session", "authoring-session", "developer-repository", "frontend-state", "credential", "local-path")
                self.assertFalse(any(any(part in name.lower() for part in forbidden_paths) for name in files), files)

                tampered = root / "runtime-download-tampered.cf-cre.zip"
                files["payload/root.flow.json"] = b'{"tampered":true}'
                with zipfile.ZipFile(tampered, "w") as output:
                    for name, content in files.items():
                        output.writestr(name, content)
                rejected = subprocess.run(
                    ["node", str(TOOLKIT), "verify", str(tampered), "--trust", str(trust)],
                    capture_output=True, text=True, check=False,
                )
                self.assertNotEqual(0, rejected.returncode)
                self.assertIn("archive digest mismatch", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
