import unittest
from pathlib import Path

from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.lab.mcp.dlc import DLC_DESCRIPTORS


ROOT = Path(__file__).resolve().parents[2]


class BuiltinMcpDlcModuleTest(unittest.TestCase):
    def test_facade_is_small_and_module_registry_is_explicit(self):
        facade_lines = len((ROOT / "core" / "lab" / "builtin_mcp.py").read_text(encoding="utf-8").splitlines())
        self.assertLess(facade_lines, 1000)
        self.assertIn("dlc.series_3d_episode_factory", DLC_DESCRIPTORS)
        self.assertEqual("CF-FARP@0.4", DLC_DESCRIPTORS["dlc.series_3d_episode_factory"]["protocol"])
        self.assertEqual("CF-CRCP@0.1", DLC_DESCRIPTORS["dlc.series_3d_episode_factory"]["optional_extension"])

    def test_existing_tools_keep_their_server_and_receive_dlc_metadata(self):
        registry = BuiltinMcpRegistry(ROOT)
        tools = registry.list_tools()
        self.assertIn("forge_3d_series_episode", tools["media"])
        self.assertIn("forge_pixel_asset_batch", tools["media"])
        description = {item["tool"]: item for item in registry.describe()}
        series = description["forge_3d_series_episode"]
        self.assertEqual("dlc.series_3d_episode_factory", series["dlc"]["id"])
        self.assertEqual("CF-FARP@0.4", series["dlc"]["protocol"])
        self.assertEqual("CF-CRCP@0.1", series["dlc"]["optional_extension"])
        self.assertEqual("dlc.pixel_episode", description["forge_pixel_asset_batch"]["dlc"]["id"])

    def test_crcp_is_metadata_only_until_an_extension_module_is_enabled(self):
        registry = BuiltinMcpRegistry(ROOT)
        self.assertNotIn("creative_recast", registry.list_tools().get("media", []))
        self.assertNotIn("CF-CRCP@0.1", [item.get("protocol") for item in registry.describe() if item.get("tool") == "forge_3d_series_episode"])
        self.assertEqual("CF-CRCP@0.1", next(item for item in registry.describe() if item.get("tool") == "forge_3d_series_episode")["dlc"]["optional_extension"])

    def test_extension_load_gate_requires_explicit_declaration_and_capabilities(self):
        default = BuiltinMcpRegistry(ROOT)
        series = next(item for item in default.dlc_report() if item["id"] == "dlc.series_3d_episode_factory")
        self.assertEqual("not_requested", series["extension"]["status"])

        blocked = BuiltinMcpRegistry(
            ROOT,
            protocol_extensions=[{"id": "CF-CRCP", "version": "0.1"}],
            capabilities=[],
        )
        series = next(item for item in blocked.dlc_report() if item["id"] == "dlc.series_3d_episode_factory")
        self.assertEqual("blocked_missing_capabilities", series["extension"]["status"])
        self.assertEqual(
            ["control_bundle_validate", "creative_approval_gate"],
            series["extension"]["missing_capabilities"],
        )
        self.assertNotIn("creative_recast", blocked.list_tools().get("media", []))

    def test_manifest_factory_keeps_extension_scope_explicit(self):
        manifest = {"protocol_extensions": [{"id": "CF-CRCP", "version": "0.1"}]}
        registry = BuiltinMcpRegistry.for_manifest(ROOT, manifest, capabilities=[])
        series = next(item for item in registry.dlc_report() if item["id"] == "dlc.series_3d_episode_factory")
        self.assertTrue(series["extension"]["declared"])
        self.assertEqual("blocked_missing_capabilities", series["extension"]["status"])


if __name__ == "__main__":
    unittest.main()
