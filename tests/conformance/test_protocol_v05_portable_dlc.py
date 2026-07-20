import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.node_executor import LabNodeExecutor
from core.protocol import ProtocolRegistry, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PortableDlcFixture:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cartridgeflow-dlc-")
        self.package = Path(self.temp.name) / "dev.fixture"
        backend = self.package / "dlc" / "backend" / "entry.py"
        frontend = self.package / "dlc" / "frontend" / "index.html"
        backend.parent.mkdir(parents=True)
        frontend.parent.mkdir(parents=True)
        backend.write_text(
            """from __future__ import annotations
import json
from core.extensions.worker_sdk import DlcWorkerRegistry

def invoke(request: dict) -> dict:
    registry = DlcWorkerRegistry(request[\"workspace_root\"], request[\"package_path\"])
    registry._registry.setdefault(\"fixture\", {})[\"echo\"] = lambda params: {
        \"ok\": True,
        \"content\": json.dumps({\"value\": params.get(\"value\")}, ensure_ascii=False),
    }
    return registry.call(request.get(\"server\", \"\"), request.get(\"tool\", \"\"), request.get(\"params\") or {})
""",
            encoding="utf-8",
        )
        frontend.write_text("<!doctype html><title>Fixture DLC</title>", encoding="utf-8")
        self.manifest = {
            "schema_version": "1.0",
            "id": "dev.fixture",
            "name": "Fixture",
            "version": "1.0.0",
            "kind": "runtime_cartridge",
            "category": "test",
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.5"},
            "mcp_tools": [{
                "id": "fixture_echo",
                "name": "Fixture echo",
                "type": "builtin",
                "server": "fixture",
                "tool": "echo",
                "enabled": True,
                "required": True,
                "contract": {"side_effect": "read_only", "timeout_ms": 30000},
            }],
            "portable_dlc": {"protocol": "CF-FARP@0.5", "descriptor": "dlc/descriptor.json"},
        }
        descriptor = {
            "schema": "cartridgeflow.portable_dlc.v1",
            "id": "dlc.fixture",
            "version": "1.0.0",
            "owner_cartridge": "dev.fixture",
            "scope": "cartridge",
            "backend": {"transport": "json_stdio_worker", "entry": "dlc/backend/entry.py"},
            "frontend": {"sandbox": "isolated_iframe", "entry": "dlc/frontend/index.html", "context_keys": ["fixture_project"]},
            "tools": [{
                "server": "fixture",
                "tool": "echo",
                "handler": "backend.entry:invoke",
                "effect": "read_only",
                "timeout_ms": 30000,
                "description": "Return a UTF-8 test value.",
                "params": {},
            }],
            "protocols": [],
            "resources": [
                {"path": "dlc", "ownership": "package"},
                {"path": ".data/cartridge_dlc/dev.fixture", "ownership": "private_data"},
                {"path": "test_output", "ownership": "user_artifact"},
            ],
            "files": [
                {"path": "dlc/backend/entry.py", "sha256": _sha256(backend)},
                {"path": "dlc/frontend/index.html", "sha256": _sha256(frontend)},
            ],
        }
        descriptor_path = self.package / "dlc" / "descriptor.json"
        descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.temp.cleanup()


class ProtocolV05PortableDlcTest(unittest.TestCase):
    def test_v05_is_standalone_and_registered(self):
        protocol = json.loads((ROOT / "protocol" / "CF-FARP-0.5.json").read_text(encoding="utf-8"))
        self.assertTrue(protocol["standalone"])
        self.assertTrue(ProtocolRegistry(ROOT).supports_protocol("CF-FARP", "0.5"))
        text = (ROOT / protocol["document"]).read_text(encoding="utf-8")
        self.assertNotIn("CF-FARP@0.4", text)
        self.assertIn("Portable DLC", text)

    def test_base_claims_portable_dlc_runtime(self):
        base = load_base_implementation(ROOT)
        self.assertEqual("0.1.0", base["implementation_version"])
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
            scoped = BuiltinMcpRegistry.for_manifest(ROOT, fixture.manifest, package_path=fixture.package)
            marker = "动作确认：继续。日本語 🎬 " * 500
            result = scoped.call("fixture", "echo", {"value": {"marker": marker}})
            self.assertTrue(result["ok"], result)
            self.assertEqual(marker, json.loads(result["content"])["value"]["marker"])

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
