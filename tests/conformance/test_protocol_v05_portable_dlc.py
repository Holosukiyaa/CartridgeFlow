import json
import unittest
from pathlib import Path

from core.cartridge.registry import CartridgeRegistry
from core.cartridge.runner import CartridgeRunner
from core.extensions import load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.node_executor import LabNodeExecutor
from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]
CARTRIDGE_ID = "dev.series_3d_episode_factory"


class ProtocolV05PortableDlcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = CartridgeRegistry(ROOT)
        cls.cartridge = cls.registry.get_cartridge(CARTRIDGE_ID)

    def test_v05_is_standalone_and_registered(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.5.json").read_text(encoding="utf-8"))
        self.assertTrue(protocol["standalone"])
        self.assertTrue(ProtocolRegistry(ROOT).supports_protocol("CF-FARP", "0.5"))
        text = (ROOT / protocol["document"]).read_text(encoding="utf-8")
        self.assertNotIn("CF-FARP@0.4", text)
        self.assertNotIn("CF-CRCP", text)
        self.assertIn("Portable DLC", text)

    def test_base_claims_portable_dlc_runtime(self):
        base = load_base_implementation(ROOT)
        self.assertIn("portable_dlc_runtime", base["profiles"])
        required = {
            "portable_dlc_descriptor",
            "cartridge_scoped_tool_registry",
            "isolated_dlc_worker",
            "frontend_dlc_sandbox",
            "dlc_uninstall_cleanup",
        }
        self.assertTrue(required <= set(base["capabilities"]))

    def test_cartridge_descriptor_is_valid_and_core_stays_clean(self):
        descriptor = load_portable_dlc_descriptor(self.cartridge["package_path"], self.cartridge["manifest"])
        self.assertEqual(CARTRIDGE_ID, descriptor["owner_cartridge"])
        self.assertNotIn("build_storyboard_project", BuiltinMcpRegistry(ROOT).list_tools()["media"])
        scoped = BuiltinMcpRegistry.for_manifest(
            ROOT,
            self.cartridge["manifest"],
            package_path=self.cartridge["package_path"],
        )
        self.assertIn("build_storyboard_project", scoped.list_tools()["media"])

    def test_storyboard_flow_closes_in_mock_mode(self):
        runner = CartridgeRunner(ROOT, self.registry)
        report = runner.build_cartridge_compatibility_report(CARTRIDGE_ID)
        self.assertTrue(report["ok"], report["findings"])
        run = runner.create_run(
            CARTRIDGE_ID,
            {"episode_brief": "A boy hears a second footstep on an empty street."},
            test_mode={"decision": "mock_resolved", "tool": "dry_run"},
        )
        self.assertEqual("completed", run["status"])
        self.assertEqual("complete", run["current_state"])
        self.assertTrue(run["data_chain"]["passed"])
        names = {item["name"] for item in run["artifacts"]}
        self.assertIn("video_shot_package.json", names)
        self.assertIn("shot_01.png", names)

    def test_human_gate_requires_submit_before_resume(self):
        executor = LabNodeExecutor(ROOT)
        node = {"type": "process", "kind": "human_gate", "executor": "human", "effect": "none", "action": "confirm_checkpoint", "params": {"output": "review", "interaction": {"store_key": "reply", "ui_extension": "portable_dlc", "input_schema": {"type": "object"}}}}
        state_doc = {"context": {"store": {}}}
        run = {"run_id": "test", "test_mode": {"decision": "live_collaboration"}}
        paused = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(paused["paused"])
        self.assertEqual("portable_dlc", paused["pending_interaction"]["ui_extension"])
        state_doc["context"]["store"]["reply"] = {"approval": "approve_all"}
        resumed = executor.execute("director", node, state_doc, run, ROOT)
        self.assertTrue(resumed["approved"])


if __name__ == "__main__":
    unittest.main()
