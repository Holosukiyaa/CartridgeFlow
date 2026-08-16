import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol.capability_cartridges import CapabilityCartridgeError, _best_match, build_flow_capability_release, create_semantic_recipe, validate_flow_capability_boundary
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge


def capability_root() -> dict:
    return {
        "schema_version": "1.0",
        "id": "dev.rss.root",
        "mode": "lifecycle",
        "protocol": {"id": "CF-FARP", "version": "1.1"},
        "start": "start",
        "states": {
            "start": {"type": "control", "title": "Start", "locked": True},
            "fetch": {
                "type": "process", "kind": "transfer", "executor": "deterministic", "effect": "writes_store",
                "action": "pass_result", "title": "Fetch reviewed sources", "inputs": {},
                "outputs": {"items": {"schema": {"type": "array"}, "target": {"type": "store", "key": "items"}}},
                "params": {"preset_config": {"from": "seed", "to": "items", "topics": ["AI"]}},
            },
            "complete": {"type": "terminal", "title": "Complete", "locked": True},
            "failed": {"type": "terminal", "title": "Failed", "locked": True},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1", "entry": "start",
            "edges": [
                {"id": "start_fetch", "kind": "sequence", "from": "start", "to": "fetch"},
                {"id": "fetch_complete", "kind": "sequence", "from": "fetch", "to": "complete"},
                {"id": "fetch_failed", "kind": "failure", "from": "fetch", "to": "failed", "failure": {"id": "fetch_failure", "causes": ["exception"]}},
            ],
        },
    }


def release(
    revision: int = 1,
    *,
    capability_id: str = "workspace.rss-source",
    trust_scope: str = "workspace",
    public_inputs: list[dict] | None = None,
    public_outputs: list[dict] | None = None,
    dependencies: list[dict] | None = None,
) -> dict:
    root_flow = capability_root()
    return build_flow_capability_release(
        capability_id=capability_id, revision=revision, trust_scope=trust_scope,
        label="获取公开 RSS", description="读取用户审核的 RSS 来源并输出标准条目。",
        match_terms=["RSS", "公开信息", "最新内容"],
        editable_fields=[{"id": "topics", "label": "关注主题", "value_type": "string_list", "required": True, "default": ["AI"]}],
        creator_bindings={"topics": "states.fetch.params.preset_config.topics"},
        public_inputs=public_inputs or [],
        public_outputs=public_outputs if public_outputs is not None else [{"id": "items", "label": "信息条目", "required": True, "schema": {"type": "array"}, "store_key": "items"}],
        dependencies=dependencies or [], source_flow_id="dev.rss", manifest={"id": "dev.rss"}, root_flow=root_flow,
        source_files={}, evidence={"status": "passed", "checks": [{"id": "sample", "status": "passed"}]},
    )


class CapabilityCartridgeTests(unittest.TestCase):
    def test_generic_ai_term_does_not_match_external_information_acquisition(self):
        generic_ai = release(capability_id="workspace.ai-transform")
        generic_ai["creator"].update({
            "label": "AI 内容处理",
            "match_terms": ["AI", "内容整理", "总结", "提炼", "改写", "创作"],
        })
        self.assertIsNone(_best_match(
            "从已审核的公开来源抓取当天的 AI 相关最新内容",
            [generic_ai],
        ))

    def test_empty_success_path_cannot_become_a_trusted_capability(self):
        root = capability_root()
        root["states"].pop("fetch")
        root["states"].pop("failed")
        root["execution_plan"]["edges"] = [{"id": "start_complete", "kind": "sequence", "from": "start", "to": "complete"}]
        with self.assertRaisesRegex(CapabilityCartridgeError, "at least one real state"):
            validate_flow_capability_boundary(root)

    def test_public_output_must_be_produced_by_the_success_path(self):
        with self.assertRaisesRegex(CapabilityCartridgeError, "not produced"):
            release(public_outputs=[{
                "id": "missing", "label": "Missing", "required": True,
                "schema": {"type": "array"}, "store_key": "not_produced",
            }])

    def test_placeholder_remote_node_cannot_become_trusted(self):
        root = capability_root()
        root["states"]["fetch"].update({
            "kind": "remote_call", "executor": "remote", "effect": "external_side_effect",
            "action": "remote_call", "endpoint": "remote://pending", "params": {},
        })
        with self.assertRaisesRegex(CapabilityCartridgeError, "no callable tool binding"):
            validate_flow_capability_boundary(root, {"mcp_tools": []})

    def test_manifest_tool_binding_survives_release_revalidation(self):
        root = capability_root()
        root["states"]["fetch"].update({
            "kind": "mcp_read", "executor": "mcp", "effect": "read_only", "action": "tool_call",
            "allowed_tools": ["rss_fetch"], "mcp_binding": {"mode": "read_only", "allowed_tools": ["rss_fetch"]},
            "params": {"output": "items"},
        })
        candidate = build_flow_capability_release(
            capability_id="workspace.manifest-tool", revision=1, trust_scope="workspace",
            label="Manifest tool", description="Uses a declared package tool.", match_terms=["tool"],
            editable_fields=[], creator_bindings={}, public_inputs=[],
            public_outputs=[{"id": "items", "label": "Items", "required": True, "schema": {"type": "array"}, "store_key": "items"}],
            dependencies=[], source_flow_id="dev.manifest-tool",
            manifest={"id": "dev.manifest-tool", "mcp_tools": [{"id": "rss_fetch"}]}, root_flow=root,
            source_files={}, evidence={"status": "passed", "checks": [{"id": "test", "status": "passed"}]},
        )
        self.assertEqual("workspace.manifest-tool", candidate["id"])

    def test_creator_can_reject_one_binding_without_rejecting_a_future_release(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = AuthoringSessionStore(Path(directory) / "sessions")
            first = release()
            recipe, publications = create_semantic_recipe(
                "recipe.review", "制作 AI 日报",
                {"nodes": [{
                    "id": "sources", "label": "收集公开信息", "description": "通过 RSS 获取可审核的最新内容。",
                    "needed_capability": "RSS 公开信息获取", "capability_id": first["id"], "values": {},
                }], "relations": []},
                [first],
            )
            created = sessions.create_from_semantic_recipe("creator.review", "project.review", recipe, publications)
            self.assertEqual("resolved", created["trusted_recipe"]["nodes"][0]["resolution"]["status"])

            rejected = sessions.reject_capability("creator.review", "sources", expected_revision=1)
            node = rejected["trusted_recipe"]["nodes"][0]
            self.assertEqual(2, rejected["revision"])
            self.assertEqual("unresolved", node["resolution"]["status"])
            self.assertEqual("RSS 公开信息获取", node["values"]["instructions"])

            unchanged, resolved = sessions.resolve_capabilities("creator.review", [first], expected_revision=2)
            self.assertEqual([], resolved)
            self.assertEqual("unresolved", unchanged["trusted_recipe"]["nodes"][0]["resolution"]["status"])

            second = release(revision=2)
            updated, resolved = sessions.resolve_capabilities("creator.review", [second], expected_revision=2)
            self.assertEqual(["sources"], resolved)
            self.assertEqual(3, updated["revision"])
            self.assertEqual(second["digest"], updated["trusted_recipe"]["nodes"][0]["resolution"]["capability"]["digest"])

    def test_developer_exact_target_binding_still_enforces_adjacent_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = AuthoringSessionStore(Path(directory) / "sessions")
            source = release()
            recipe, publications = create_semantic_recipe(
                "recipe.exact", "Build an unusual report",
                {
                    "nodes": [
                        {"id": "source", "label": "Source", "description": "Provide items", "needed_capability": "RSS", "capability_id": source["id"], "values": {}},
                        {"id": "special", "label": "Unique semantic gap", "description": "A capability created for this exact node", "needed_capability": "not keyword matched", "capability_id": None, "values": {}},
                    ],
                    "relations": [{"id": "source_special", "from_node_id": "source", "to_node_id": "special", "relation": "produces"}],
                },
                [source],
            )
            sessions.create_from_semantic_recipe("creator.exact", "project.exact", recipe, publications)
            incompatible = release(
                capability_id="workspace.exact-special",
                public_inputs=[{"id": "items", "label": "Items", "required": True, "schema": {"type": "object"}, "store_key": "items"}],
            )
            with self.assertRaisesRegex(ValueError, "does not satisfy"):
                sessions.validate_capability_binding("project.exact", "special", incompatible)
            compatible = release(
                capability_id="workspace.exact-special",
                public_inputs=[{"id": "items", "label": "Items", "required": True, "schema": {"type": "array"}, "store_key": "items"}],
            )
            revision = sessions.get_by_project_id("project.exact")["head"]["revision"]
            sessions.validate_capability_binding("project.exact", "special", compatible)
            self.assertEqual(revision, sessions.get_by_project_id("project.exact")["head"]["revision"])
            sessions.freeze("creator.exact", ["source"], author="creator", summary="Reviewed the existing source")
            bound = sessions.bind_capability("project.exact", "special", compatible)
            special = next(item for item in bound["trusted_recipe"]["nodes"] if item["id"] == "special")
            self.assertEqual("resolved", special["resolution"]["status"])
            self.assertEqual(compatible["digest"], special["resolution"]["capability"]["digest"])
            self.assertEqual(["source"], bound["frozen_steps"])
            replacement = sessions.get("creator.exact")["freeze_replacements"][0]
            self.assertEqual(["source"], replacement["preserved_steps"])
            self.assertEqual([], replacement["affected_steps"])

    def test_unresolved_node_reresolves_in_place_and_packages_namespaced_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = CapabilityCartridgeStore(temp / "registry")
            sessions = AuthoringSessionStore(temp / "sessions")
            recipe, publications = create_semantic_recipe(
                "recipe.daily", "制作 AI 日报",
                {"nodes": [{
                    "id": "sources", "label": "收集公开信息", "description": "通过 RSS 获取可审核的最新内容。",
                    "needed_capability": "RSS 公开信息获取", "capability_id": None, "values": {},
                }], "relations": []},
                [],
            )
            created = sessions.create_from_semantic_recipe("creator.daily", "project.daily", recipe, publications)
            self.assertEqual("sources", created["trusted_recipe"]["nodes"][0]["id"])
            self.assertEqual("unresolved", created["trusted_recipe"]["nodes"][0]["resolution"]["status"])
            self.assertFalse(created["generation_readiness"]["ready"])

            published = registry.put(release(), expected_revision=0)
            resolved, node_ids = sessions.resolve_capabilities("creator.daily", registry.list_active(), expected_revision=1)
            self.assertEqual(["sources"], node_ids)
            self.assertEqual("sources", resolved["trusted_recipe"]["nodes"][0]["id"])
            self.assertEqual("resolved", resolved["trusted_recipe"]["nodes"][0]["resolution"]["status"])
            self.assertEqual(published["digest"], resolved["trusted_recipe"]["nodes"][0]["resolution"]["capability"]["digest"])
            self.assertFalse(resolved["generation_readiness"]["ready"])

            sessions.freeze("creator.daily", ["sources"], author="creator", summary="Reviewed source and defaults")
            reviewed = sessions.creator_projection(sessions.get("creator.daily"))
            self.assertTrue(reviewed["generation_readiness"]["ready"])
            bridge = CreatorRuntimeBridge(ROOT, temp / "packages", registry)
            packaged = bridge.package(sessions, "creator.daily", expected_revision=2)
            archive = temp / "packages" / packaged["filename"]
            with zipfile.ZipFile(archive) as bundle:
                root_name = next(name for name in bundle.namelist() if name.endswith("root.flow.json"))
                materialized = json.loads(bundle.read(root_name))
            self.assertIn("cap.sources.fetch", materialized["states"])
            self.assertEqual("CF-FARP", materialized["protocol"]["id"])
            self.assertEqual("1.7", materialized["protocol"]["version"])
            self.assertEqual(published["digest"], materialized["states"]["cap.sources.fetch"]["capability_release"]["digest"])
            self.assertEqual("deterministic_namespace_expansion", materialized["capability_materialization"]["strategy"])

    def test_missing_dependency_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CapabilityCartridgeStore(Path(directory) / "registry")
            candidate = release()
            body = {key: value for key, value in candidate.items() if key != "digest"}
            body["dependencies"] = [{"id": "workspace.missing", "revision": 1, "digest": "0" * 64}]
            from core.protocol.tuning import canonical_digest
            body["digest"] = canonical_digest(body)
            with self.assertRaisesRegex(ValueError, "not found"):
                registry.put(body, expected_revision=0)

    def test_creator_binding_rejects_wrong_target_type(self):
        root_flow = capability_root()
        root_flow["states"]["fetch"]["params"]["preset_config"]["topics"] = ["AI"]
        with self.assertRaisesRegex(CapabilityCartridgeError, "does not match"):
            build_flow_capability_release(
                capability_id="workspace.invalid-binding", revision=1, trust_scope="workspace",
                label="Invalid", description="Invalid binding test", match_terms=["invalid"],
                editable_fields=[{"id": "topic", "label": "Topic", "value_type": "string", "required": True, "default": "AI"}],
                creator_bindings={"topic": "states.fetch.params.preset_config.topics"},
                public_inputs=[], public_outputs=[], dependencies=[], source_flow_id="dev.invalid",
                manifest={"id": "dev.invalid"}, root_flow=root_flow, source_files={},
                evidence={"status": "passed", "checks": [{"id": "test", "status": "passed"}]},
            )

    def test_capability_flow_requires_a_reachable_success_boundary(self):
        root_flow = capability_root()
        root_flow["execution_plan"]["edges"] = []
        with self.assertRaisesRegex(CapabilityCartridgeError, "connected execution path"):
            build_flow_capability_release(
                capability_id="workspace.disconnected", revision=1, trust_scope="workspace",
                label="Disconnected", description="Disconnected Flow test", match_terms=["disconnected"],
                editable_fields=[], creator_bindings={}, public_inputs=[], public_outputs=[], dependencies=[],
                source_flow_id="dev.disconnected", manifest={"id": "dev.disconnected"}, root_flow=root_flow,
                source_files={}, evidence={"status": "passed", "checks": [{"id": "test", "status": "passed"}]},
            )

    def test_higher_trust_release_cannot_depend_on_workspace_release(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CapabilityCartridgeStore(Path(directory) / "registry")
            dependency = registry.put(release(), expected_revision=0)
            system_release = release(
                capability_id="system.aggregate",
                trust_scope="system",
                dependencies=[{key: dependency[key] for key in ("id", "revision", "digest")}],
            )
            with self.assertRaisesRegex(ValueError, "System capabilities"):
                registry.put(system_release, expected_revision=0)

    def test_capability_source_file_rejects_windows_absolute_path(self):
        with self.assertRaisesRegex(CapabilityCartridgeError, "package-relative"):
            build_flow_capability_release(
                capability_id="workspace.unsafe-file", revision=1, trust_scope="workspace",
                label="Unsafe", description="Unsafe source path test", match_terms=["unsafe"],
                editable_fields=[], creator_bindings={}, public_inputs=[], public_outputs=[], dependencies=[],
                source_flow_id="dev.unsafe", manifest={"id": "dev.unsafe"}, root_flow=capability_root(),
                source_files={"C:/outside.py": "pass\n"},
                evidence={"status": "passed", "checks": [{"id": "test", "status": "passed"}]},
            )

    def test_in_place_public_store_keeps_the_upstream_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            item_schema = {"type": "array"}
            transform = release(
                capability_id="workspace.transform",
                public_inputs=[{"id": "items", "label": "Items", "required": True, "schema": item_schema, "store_key": "items"}],
                public_outputs=[{"id": "items", "label": "Items", "required": True, "schema": item_schema, "store_key": "items"}],
            )
            bridge = CreatorRuntimeBridge(ROOT, Path(directory) / "packages")
            states, _, _, _, outputs = bridge._inline_flow_release(
                transform,
                "transform",
                {"topics": ["AI"]},
                {"items": {"store_key": "cap.source.items", "schema": item_schema}},
            )
            self.assertEqual("cap.source.items", outputs["items"]["store_key"])
            self.assertEqual("cap.source.items", states["cap.transform.fetch"]["outputs"]["items"]["target"]["key"])

    def test_dependency_closure_rejects_a_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CapabilityCartridgeStore(Path(directory) / "registry")
            releases = {
                "workspace.a": {"id": "workspace.a", "revision": 1, "digest": "a", "dependencies": [{"id": "workspace.b", "revision": 1, "digest": "b"}]},
                "workspace.b": {"id": "workspace.b", "revision": 1, "digest": "b", "dependencies": [{"id": "workspace.a", "revision": 1, "digest": "a"}]},
            }
            with patch.object(registry, "get", side_effect=lambda capability_id, revision: releases[capability_id]):
                with self.assertRaisesRegex(ValueError, "cycle"):
                    registry.dependency_closure([{"id": "workspace.a", "revision": 1, "digest": "a"}])

    def test_recursive_materializer_deduplicates_a_shared_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CapabilityCartridgeStore(Path(directory) / "registry")
            shared = {"id": "workspace.shared", "revision": 1, "digest": "shared", "dependencies": []}
            left = {"id": "workspace.left", "revision": 1, "digest": "left", "dependencies": [{"id": shared["id"], "revision": 1, "digest": shared["digest"]}]}
            right = {"id": "workspace.right", "revision": 1, "digest": "right", "dependencies": [{"id": shared["id"], "revision": 1, "digest": shared["digest"]}]}
            root = {
                "id": "workspace.root", "revision": 1, "digest": "root",
                "dependencies": [
                    {"id": left["id"], "revision": 1, "digest": left["digest"]},
                    {"id": right["id"], "revision": 1, "digest": right["digest"]},
                ],
            }
            releases = {item["id"]: item for item in (shared, left, right)}
            bridge = CreatorRuntimeBridge(ROOT, Path(directory) / "packages", registry)
            with patch.object(registry, "get", side_effect=lambda capability_id, revision: releases[capability_id]):
                expanded = bridge._expand_release(root)
            self.assertEqual(
                ["workspace.shared", "workspace.left", "workspace.right", "workspace.root"],
                [item["id"] for item in expanded],
            )

    def test_public_port_schema_mismatch_blocks_recursive_package(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = CapabilityCartridgeStore(temp / "registry")
            source = registry.put(release(), expected_revision=0)
            sink = registry.put(
                release(
                    capability_id="workspace.object-sink",
                    public_inputs=[{"id": "items", "label": "Items", "required": True, "schema": {"type": "object"}, "store_key": "items"}],
                    public_outputs=[],
                ),
                expected_revision=0,
            )
            recipe, publications = create_semantic_recipe(
                "recipe.schema", "Schema guard",
                {
                    "nodes": [
                        {"id": "source", "label": "Source", "description": "Source", "needed_capability": "source", "capability_id": source["id"], "values": {"topics": ["AI"]}},
                        {"id": "sink", "label": "Sink", "description": "Sink", "needed_capability": "sink", "capability_id": sink["id"], "values": {"topics": ["AI"]}},
                    ],
                    "relations": [{"id": "source_to_sink", "from_node_id": "source", "to_node_id": "sink", "relation": "produces"}],
                },
                registry.list_active(),
            )
            sessions = AuthoringSessionStore(temp / "sessions")
            sessions.create_from_semantic_recipe("creator.schema", "project.schema", recipe, publications)
            sessions.freeze("creator.schema", ["source", "sink"], author="creator", summary="Reviewed")
            with self.assertRaisesRegex(ValueError, "incompatible"):
                CreatorRuntimeBridge(ROOT, temp / "packages", registry).package(sessions, "creator.schema", expected_revision=1)

    def test_uses_relation_runs_provider_before_consumer_and_binds_its_output(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = CapabilityCartridgeStore(temp / "registry")
            item_schema = {"type": "array"}
            source = registry.put(release(), expected_revision=0)
            sink = registry.put(
                release(
                    capability_id="workspace.item-sink",
                    public_inputs=[{
                        "id": "items", "label": "Items", "required": True,
                        "schema": item_schema, "store_key": "items",
                    }],
                    public_outputs=[{
                        "id": "items", "label": "Items", "required": True,
                        "schema": item_schema, "store_key": "items",
                    }],
                ),
                expected_revision=0,
            )
            recipe, publications = create_semantic_recipe(
                "recipe.uses", "Consume source items",
                {
                    "nodes": [
                        {"id": "source", "label": "Source", "description": "Provide items", "needed_capability": "source", "capability_id": source["id"], "values": {"topics": ["AI"]}},
                        {"id": "sink", "label": "Sink", "description": "Use items", "needed_capability": "sink", "capability_id": sink["id"], "values": {"topics": ["AI"]}},
                    ],
                    "relations": [{"id": "sink_uses_source", "from_node_id": "sink", "to_node_id": "source", "relation": "uses"}],
                },
                registry.list_active(),
            )
            sessions = AuthoringSessionStore(temp / "sessions")
            sessions.create_from_semantic_recipe("creator.uses", "project.uses", recipe, publications)
            sessions.freeze("creator.uses", ["source", "sink"], author="creator", summary="Reviewed")

            bridge = CreatorRuntimeBridge(ROOT, temp / "packages", registry)
            packaged = bridge.package(sessions, "creator.uses", expected_revision=1)
            with zipfile.ZipFile(temp / "packages" / packaged["filename"]) as bundle:
                root_name = next(name for name in bundle.namelist() if name.endswith("root.flow.json"))
                materialized = json.loads(bundle.read(root_name))

            self.assertEqual("cap.source.items", materialized["states"]["cap.sink.fetch"]["outputs"]["items"]["target"]["key"])
            self.assertEqual("sink", materialized["capability_materialization"]["application_outputs"][0]["node_id"])
            self.assertEqual(
                {"id": "sink_uses_source", "from_step_id": "sink", "to_step_id": "source", "relation": "uses"},
                materialized["semantic_relationships"][0],
            )


if __name__ == "__main__":
    unittest.main()
