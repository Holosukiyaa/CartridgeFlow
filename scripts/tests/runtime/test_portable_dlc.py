import json
import unittest
from pathlib import Path

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.node_executor import LabNodeExecutor
from core.protocol import load_base_implementation
from scripts.tests.fixtures.portable_dlc import PortableDlcFixture


ROOT = Path(__file__).resolve().parents[3]


class PortableDlcTests(unittest.TestCase):
    def test_base_claims_portable_dlc_runtime(self):
        base = load_base_implementation(ROOT)
        self.assertIn("portable_dlc_runtime", base["profiles"])
        required = {"portable_dlc_descriptor", "cartridge_scoped_tool_registry", "isolated_dlc_worker", "frontend_dlc_sandbox", "dlc_uninstall_cleanup"}
        self.assertTrue(required <= set(base["capabilities"]))

    def test_release_tree_contains_no_bundled_business_cartridge(self):
        manifests = list((ROOT / "cartridges" / "dev").glob("*/manifest.json"))
        self.assertEqual([], manifests)

    def test_core_registry_exposes_no_legacy_cartridge_tools(self):
        tools = BuiltinMcpRegistry(ROOT).list_tools()
        media = set(tools["media"])
        self.assertNotIn("generate_pixel_shot_plan", media)
        self.assertNotIn("generate_short_video", media)
        self.assertNotIn("forge_spatial_blockout", media)

    def test_descriptor_activates_only_in_explicit_cartridge_scope(self):
        with PortableDlcFixture() as fixture:
            descriptor = load_portable_dlc_descriptor(fixture.package, fixture.manifest)
            self.assertEqual("dev.fixture", descriptor["owner_cartridge"])
            self.assertNotIn("fixture", BuiltinMcpRegistry(ROOT).list_tools())
            scoped = BuiltinMcpRegistry.for_manifest(ROOT, fixture.manifest, package_path=fixture.package)
            self.assertIn("echo", scoped.list_tools()["fixture"])
            report = scoped.dlc_report()[-1]
            self.assertTrue(report["isolated_worker"])
            self.assertEqual("cartridge", report["scope"])

    def test_worker_transports_nested_unicode_json_as_utf8(self):
        with PortableDlcFixture() as fixture:
            scoped = BuiltinMcpRegistry.for_manifest(
                ROOT,
                fixture.manifest,
                package_path=fixture.package,
                worker_journal_dir=fixture.worker_journal_dir,
            )
            marker = "动作确认：继续。日本語 🎬 " * 500
            result = scoped.call("fixture", "echo", {"value": {"marker": marker}})
            self.assertTrue(result["ok"], result)
            self.assertEqual(marker, json.loads(result["content"])["value"]["marker"])
            self.assertEqual(1, len(list(fixture.worker_journal_dir.glob("*.json"))))

    def test_hash_mismatch_blocks_descriptor(self):
        with PortableDlcFixture() as fixture:
            entry = fixture.package / "dlc" / "backend" / "entry.py"
            entry.write_text(entry.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
            with self.assertRaises(PortableDlcValidationError):
                load_portable_dlc_descriptor(fixture.package, fixture.manifest)

    def test_package_removal_deactivates_existing_proxy(self):
        with PortableDlcFixture() as fixture:
            scoped = BuiltinMcpRegistry.for_manifest(ROOT, fixture.manifest, package_path=fixture.package)
            proxy = scoped._registry["fixture"]["echo"]
            proxy.descriptor["_package_path"] = str(fixture.package / "missing-after-uninstall")
            result = scoped.call("fixture", "echo", {})
            self.assertFalse(result["ok"])
            self.assertEqual("extension_inactive", result["code"])

    def test_human_gate_requires_submit_before_resume(self):
        executor = LabNodeExecutor(ROOT)
        node = {
            "type": "process",
            "kind": "human_gate",
            "executor": "human",
            "effect": "none",
            "action": "confirm_checkpoint",
            "params": {"output": "review", "interaction": {"store_key": "reply", "ui_extension": "portable_dlc", "input_schema": {"type": "object"}}},
        }
        state_doc = {"context": {"store": {}}}
        run = {"run_id": "test", "test_mode": {"decision": "live_collaboration"}}
        paused = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(paused["paused"])
        self.assertEqual("portable_dlc", paused["pending_interaction"]["ui_extension"])
        state_doc["context"]["store"]["reply"] = {"approval": "approve"}
        resumed = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(resumed["approved"])


if __name__ == "__main__":
    unittest.main()
