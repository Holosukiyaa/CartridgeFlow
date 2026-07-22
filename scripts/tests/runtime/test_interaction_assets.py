import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.cartridge.assets import (
    ASSET_SCHEMA,
    COMPONENT_SCHEMA,
    CartridgeAssetError,
    load_asset_bundle,
    validate_interaction_nodes,
    validate_passive_html,
)
from core.cartridge.runner import CartridgeRunner
from core.lab.node_executor import LabNodeExecutor
from core.lab.dev_flow import DevFlowManager
from core.protocol import build_compatibility_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[3]


class InteractionAssetRuntimeTests(unittest.TestCase):
    def test_new_dev_flow_is_v07_compatible_and_asset_backed(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = DevFlowManager(temp)
            created = manager.create_flow("dev.interaction", "Interaction", "Asset-backed flow")
            package = Path(created["path"])
            bundle = load_asset_bundle(package, created["manifest"], include_content=True)
            self.assertIn("welcome.panel", bundle["component_by_id"])
            report = build_compatibility_report(
                load_base_implementation(ROOT),
                created["manifest"],
                created["root_flow"],
                ROOT,
            )
            self.assertTrue(report["ok"], report["findings"])

    def test_passive_html_rejects_script_events_and_external_navigation(self):
        for content in [
            "<script>alert(1)</script>",
            '<section onclick="submit()">x</section>',
            '<a href="https://example.com">leave</a>',
            '<link rel="stylesheet" href="styles.css">',
        ]:
            with self.subTest(content=content):
                with self.assertRaises(CartridgeAssetError) as caught:
                    validate_passive_html(content)
                self.assertEqual("PASSIVE_HTML_ACTIVE_CONTENT", caught.exception.code)

    def test_asset_bundle_validates_integrity_and_interaction_nodes(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp)
            manifest, flow = self._write_package(package)
            bundle = load_asset_bundle(package, manifest, include_content=True)
            self.assertEqual("<main>Review</main>", bundle["asset_by_id"]["ui.review"]["content"])
            self.assertEqual([], validate_interaction_nodes(flow, bundle))

            (package / "assets/review.html").write_text("changed", encoding="utf-8")
            with self.assertRaises(CartridgeAssetError) as caught:
                load_asset_bundle(package, manifest)
            self.assertEqual("ASSET_INTEGRITY_MISMATCH", caught.exception.code)

    def test_interaction_executor_displays_or_pauses_without_running_html(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp)
            manifest, _ = self._write_package(package)
            run = {
                "run_id": "run_assets",
                "package_path": str(package),
                "asset_registry": manifest["asset_registry"],
                "interaction_components": manifest["interaction_components"],
                "artifacts": [],
            }
            state_doc = {"context": {"store": {"draft": {"title": "Example"}}}}
            executor = LabNodeExecutor(package)

            display = executor.execute("preview", {
                "type": "process",
                "kind": "interaction",
                "executor": "deterministic",
                "effect": "none",
                "component_ref": "review.panel",
                "interaction_mode": "display",
                "input_binding": {"draft": "store:draft"},
            }, state_doc, run, package / "run")
            self.assertEqual("render_interaction", display["action"])
            self.assertEqual("Example", display["presentation"]["bindings"]["draft"]["title"])
            self.assertNotIn("review_result", state_doc["context"]["store"])

            review = executor.execute("review", {
                "type": "process",
                "kind": "interaction",
                "executor": "user",
                "effect": "writes_store",
                "component_ref": "review.panel",
                "interaction_mode": "review",
                "input_binding": {"draft": "store:draft"},
                "output": "review_result",
                "action_routes": {"approve": "complete", "revise": "draft"},
            }, state_doc, run, package / "run")
            pending = review["pending_interaction"]
            self.assertTrue(review["paused"])
            self.assertEqual("cartridgeflow.pending_interaction.v2", pending["schema"])
            self.assertEqual({"approve", "revise"}, set(pending["allowed_actions"]))
            self.assertEqual("resume_by_action_route", pending["resume"]["policy"])

    def test_named_action_resume_is_static_and_fail_closed(self):
        runner = object.__new__(CartridgeRunner)
        resume = {
            "policy": "resume_by_action_route",
            "action_routes": {"approve": "complete", "revise": "draft"},
        }
        resolved = runner._resolve_answer_resume(resume, {"action_id": "approve", "payload": {}})
        self.assertEqual({"policy": "resume_target_node", "target_node": "complete", "action_id": "approve"}, resolved)
        with self.assertRaises(ValueError):
            runner._resolve_answer_resume(resume, {"action_id": "undeclared", "payload": {}})

    def test_pending_interaction_rejects_component_identity_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp)
            manifest, _ = self._write_package(package)
            run = {
                "run_id": "run_identity",
                "cartridge_id": "test.assets",
                "package_path": str(package),
                "asset_registry": manifest["asset_registry"],
                "interaction_components": manifest["interaction_components"],
                "artifacts": [],
            }
            state_doc = {"context": {"store": {}}}
            pending = LabNodeExecutor(package).execute("review", {
                "type": "process",
                "kind": "interaction",
                "executor": "user",
                "effect": "writes_store",
                "component_ref": "review.panel",
                "interaction_mode": "review",
                "input_binding": {},
                "output": "review_result",
                "action_routes": {"approve": "complete"},
            }, state_doc, run, package / "run")["pending_interaction"]

            class Registry:
                def get_cartridge(self, _cartridge_id):
                    return {"package_path": str(package), "manifest": manifest}

            runner = object.__new__(CartridgeRunner)
            runner.registry = Registry()
            runner._validate_pending_interaction_identity(run, pending)
            components_path = package / "assets/components.json"
            components = json.loads(components_path.read_text(encoding="utf-8"))
            components["components"][0]["version"] = "2.0.0"
            components_path.write_text(json.dumps(components), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "component identity changed"):
                runner._validate_pending_interaction_identity(run, pending)

    def _write_package(self, package: Path):
        assets = package / "assets"
        assets.mkdir()
        html = b"<main>Review</main>"
        (assets / "review.html").write_bytes(html)
        registry = {
            "schema": ASSET_SCHEMA,
            "assets": [{
                "id": "ui.review",
                "kind": "interaction_template",
                "path": "assets/review.html",
                "media_type": "text/html",
                "sha256": hashlib.sha256(html).hexdigest(),
                "size": len(html),
                "executable": False,
            }],
        }
        components = {
            "schema": COMPONENT_SCHEMA,
            "components": [{
                "id": "review.panel",
                "version": "1.0.0",
                "runtime": "passive",
                "entry": {"type": "asset", "ref": "asset:ui.review"},
                "supported_modes": ["display", "review"],
                "input_schema": {"type": "object"},
                "actions": [
                    {"id": "approve", "label": "Approve", "payload_schema": {"type": "object", "additionalProperties": False}},
                    {"id": "revise", "label": "Revise", "payload_schema": {"type": "object", "properties": {"feedback": {"type": "string"}}, "required": ["feedback"]}},
                ],
                "host_capabilities": [],
            }],
        }
        (assets / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
        (assets / "components.json").write_text(json.dumps(components), encoding="utf-8")
        manifest = {"asset_registry": "assets/registry.json", "interaction_components": "assets/components.json"}
        flow = {
            "states": {
                "review": {
                    "type": "process",
                    "kind": "interaction",
                    "executor": "user",
                    "effect": "writes_store",
                    "display_name": "Review",
                    "component_ref": "review.panel",
                    "interaction_mode": "review",
                    "input_binding": {"draft": "store:draft"},
                    "output": "review_result",
                    "action_routes": {"approve": "complete", "revise": "draft"},
                },
                "draft": {"type": "system"},
                "complete": {"type": "terminal"},
            },
        }
        return manifest, flow


if __name__ == "__main__":
    unittest.main()
