import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol.capability_cartridges import build_flow_capability_release, create_semantic_recipe
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge
from fastapi.testclient import TestClient
from backend import main as backend_main
from backend.main import app


def _asset(asset_id: str, path: str, content: str) -> dict:
    raw = content.encode("utf-8")
    return {
        "id": asset_id,
        "kind": "interaction_template",
        "path": path,
        "media_type": "text/html",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
        "executable": False,
    }


def experience_release() -> dict:
    list_html = '<main><h1>信息列表</h1><div data-cf-bind="items"></div></main>'
    summary_html = '<main><h1>今日摘要</h1><p data-cf-bind="summary"></p></main>'
    files = {
        "assets/list.html": list_html,
        "assets/summary.html": summary_html,
        "assets/registry.json": json.dumps({
            "schema": "cartridgeflow.asset_registry.v1",
            "assets": [
                _asset("ui.items", "assets/list.html", list_html),
                _asset("ui.summary", "assets/summary.html", summary_html),
            ],
        }, ensure_ascii=False),
        "assets/components.json": json.dumps({
            "schema": "cartridgeflow.interaction_components.v1",
            "components": [
                {
                    "id": "items.list",
                    "label": "信息列表",
                    "description": "逐条查看已收集的信息",
                    "version": "1.0.0",
                    "runtime": "passive",
                    "entry": {"type": "asset", "ref": "asset:ui.items"},
                    "supported_modes": ["display"],
                    "input_schema": {
                        "type": "object",
                        "properties": {"items": {"type": "array", "title": "信息内容"}},
                        "required": ["items"],
                    },
                    "actions": [],
                    "host_capabilities": [],
                },
                {
                    "id": "items.summary",
                    "label": "摘要卡片",
                    "description": "用紧凑卡片显示本轮结果",
                    "version": "1.0.0",
                    "runtime": "passive",
                    "entry": {"type": "asset", "ref": "asset:ui.summary"},
                    "supported_modes": ["display"],
                    "input_schema": {
                        "type": "object",
                        "properties": {"summary": {"type": "array", "title": "摘要内容"}},
                        "required": ["summary"],
                    },
                    "actions": [],
                    "host_capabilities": [],
                },
            ],
        }, ensure_ascii=False),
    }
    flow = {
        "schema_version": "1.0",
        "id": "dev.experience.root",
        "mode": "lifecycle",
        "protocol": {"id": "CF-FARP", "version": "1.7"},
        "start": "start",
        "states": {
            "start": {"type": "control", "title": "Start", "locked": True},
            "produce": {
                "type": "process",
                "kind": "transfer",
                "executor": "deterministic",
                "effect": "writes_store",
                "action": "pass_result",
                "inputs": {"items": {"required": False, "binding": {"source": "constant", "value": ["A", "B"]}}},
                "outputs": {"items": {"schema": {"type": "array"}, "target": {"type": "store", "key": "items"}}},
                "params": {},
            },
            "show": {
                "type": "process",
                "kind": "interaction",
                "executor": "deterministic",
                "effect": "none",
                "action": "render_interaction",
                "display_name": "查看本轮结果",
                "component_ref": "items.list",
                "interaction_mode": "display",
                "input_binding": {"items": "store:items"},
            },
            "complete": {"type": "terminal", "title": "Complete", "locked": True},
            "failed": {"type": "terminal", "title": "Failed", "locked": True},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": "start",
            "edges": [
                {"id": "start_produce", "kind": "sequence", "from": "start", "to": "produce"},
                {"id": "produce_show", "kind": "sequence", "from": "produce", "to": "show"},
                {"id": "show_complete", "kind": "sequence", "from": "show", "to": "complete"},
                {"id": "produce_failed", "kind": "failure", "from": "produce", "to": "failed", "failure": {"id": "produce.failure", "causes": ["exception"]}},
                {"id": "show_failed", "kind": "failure", "from": "show", "to": "failed", "failure": {"id": "show.failure", "causes": ["exception"]}},
            ],
        },
    }
    manifest = {
        "id": "dev.experience",
        "asset_registry": "assets/registry.json",
        "interaction_components": "assets/components.json",
    }
    return build_flow_capability_release(
        capability_id="workspace.experience",
        revision=1,
        trust_scope="workspace",
        label="结果呈现",
        description="产出信息并让用户选择结果呈现方式",
        match_terms=["呈现", "结果"],
        editable_fields=[],
        creator_bindings={},
        public_inputs=[],
        public_outputs=[{"id": "items", "label": "信息条目", "required": True, "schema": {"type": "array"}, "store_key": "items"}],
        dependencies=[],
        source_flow_id="dev.experience",
        manifest=manifest,
        root_flow=flow,
        source_files=files,
        evidence={"status": "passed", "checks": [{"id": "experience-fixture", "status": "passed"}]},
    )


class CreatorComponentMappingTests(unittest.TestCase):
    def _store(self, root: Path) -> tuple[AuthoringSessionStore, CapabilityCartridgeStore]:
        registry = CapabilityCartridgeStore(root / "capabilities")
        release = registry.put(experience_release(), expected_revision=0)
        recipe, publications = create_semantic_recipe(
            "recipe.experience",
            "制作一份可以切换呈现方式的结果",
            {
                "nodes": [{
                    "id": "result",
                    "label": "呈现结果",
                    "description": "把本轮信息显示给用户",
                    "needed_capability": "结果呈现",
                    "capability_id": release["id"],
                    "values": {},
                }],
                "relations": [],
            },
            registry.list_active(),
        )
        sessions = AuthoringSessionStore(root / "sessions")
        sessions.create_from_semantic_recipe("creator.experience", "project.experience", recipe, publications)
        return sessions, registry

    def test_projects_business_safe_choices_and_rejects_stale_or_unknown_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions, _ = self._store(Path(directory))
            creator = sessions.creator_projection(sessions.get("creator.experience"))
            experience = creator["trusted_recipe"]["nodes"][0]["experience"]
            self.assertEqual("available", experience["status"])
            self.assertEqual(["信息列表", "摘要卡片"], [item["label"] for item in experience["slots"][0]["components"]])
            self.assertEqual("信息条目", experience["slots"][0]["sources"][0]["label"])
            self.assertEqual("摘要内容", experience["slots"][0]["components"][1]["fields"][0]["label"])
            self.assertNotIn("store:items", json.dumps(experience, ensure_ascii=False))

            with self.assertRaises(AuthoringServiceError) as stale:
                sessions.set_experience_mapping(
                    "creator.experience", "result", "show", "items.summary", {"summary": "items"},
                    expected_revision=1, expected_experience_revision=2,
                )
            self.assertEqual("AUTHORING_EXPERIENCE_REVISION_CONFLICT", stale.exception.code)
            with self.assertRaises(AuthoringServiceError) as unknown:
                sessions.set_experience_mapping(
                    "creator.experience", "result", "show", "items.summary", {"summary": "missing"},
                    expected_revision=1, expected_experience_revision=0,
                )
            self.assertEqual("AUTHORING_EXPERIENCE_MAPPING_INVALID", unknown.exception.code)

    def test_packages_selected_component_field_mapping_as_verified_cf_cre_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions, registry = self._store(root)
            updated = sessions.set_experience_mapping(
                "creator.experience", "result", "show", "items.summary", {"summary": "items"},
                expected_revision=1, expected_experience_revision=0,
            )
            self.assertEqual("items.summary", updated["trusted_recipe"]["nodes"][0]["experience"]["slots"][0]["selected_component_id"])
            sessions.freeze("creator.experience", ["result"], author="creator", summary="确认能力与呈现")

            packaged = CreatorRuntimeBridge(ROOT, root / "packages", registry).package(
                sessions, "creator.experience", expected_revision=1,
            )
            self.assertEqual("CF-CRE@2", packaged["protocol"])
            self.assertTrue(packaged["distribution"]["production_eligible"])
            with zipfile.ZipFile(root / "packages" / packaged["filename"]) as bundle:
                members = {name: bundle.read(name) for name in bundle.namelist()}
            release_manifest = json.loads(members["release.manifest.json"])
            self.assertEqual("cartridgeflow.release_envelope.v2", release_manifest["schema"])
            manifest = json.loads(members["payload/manifest.json"])
            flow = json.loads(members["payload/root.flow.json"])
            node = flow["states"]["cap.result.show"]
            self.assertEqual("display", node["interaction_mode"])
            self.assertEqual({"summary": "store:cap.result.items"}, node["input_binding"])
            self.assertNotEqual("items.summary", node["component_ref"])
            components = json.loads(members[f"payload/{manifest['interaction_components']}"])
            self.assertIn(node["component_ref"], {item["id"] for item in components["components"]})
            self.assertIn(b'data-cf-bind="summary"', b"\n".join(members.values()))

    def test_experience_api_saves_once_and_rejects_a_stale_page(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions, registry = self._store(Path(directory))
            with (
                patch.object(backend_main, "authoring_sessions", sessions),
                patch.object(backend_main, "capability_cartridges", registry),
                TestClient(app) as client,
            ):
                payload = {
                    "expected_revision": 1,
                    "expected_experience_revision": 0,
                    "slot_id": "show",
                    "component_id": "items.summary",
                    "field_sources": {"summary": "items"},
                }
                saved = client.put(
                    "/api/creator/authoring-sessions/creator.experience/nodes/result/experience",
                    json=payload,
                )
                self.assertEqual(200, saved.status_code, saved.text)
                self.assertEqual(1, saved.json()["creator"]["experience_revision"])

                stale = client.put(
                    "/api/creator/authoring-sessions/creator.experience/nodes/result/experience",
                    json=payload,
                )
                self.assertEqual(409, stale.status_code, stale.text)
                self.assertEqual("AUTHORING_EXPERIENCE_REVISION_CONFLICT", stale.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
