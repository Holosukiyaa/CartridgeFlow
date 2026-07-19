import json
import unittest
from pathlib import Path

from core.cartridge.registry import CartridgeRegistry
from core.extensions import load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry


ROOT = Path(__file__).resolve().parents[5]
PACKAGE = Path(__file__).resolve().parents[2]


class PortableDlcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cartridge = CartridgeRegistry(ROOT).get_cartridge("dev.series_3d_episode_factory")

    def scoped_registry(self, package=PACKAGE):
        return BuiltinMcpRegistry.for_manifest(
            ROOT,
            self.cartridge["manifest"],
            package_path=package,
            capabilities=["portable_dlc_descriptor", "portable_dlc_validate"],
            supported_protocols=[{"id": "CF-FARP", "version": "0.5"}],
        )

    def test_core_does_not_expose_cartridge_tools(self):
        tools = BuiltinMcpRegistry(ROOT).list_tools()["media"]
        self.assertNotIn("match_series_assets", tools)
        self.assertNotIn("build_storyboard_project", tools)

    def test_descriptor_activates_only_in_cartridge_scope(self):
        descriptor = load_portable_dlc_descriptor(PACKAGE, self.cartridge["manifest"])
        self.assertEqual("cartridgeflow.portable_dlc.v1", descriptor["schema"])
        self.assertEqual("isolated_iframe", descriptor["frontend"]["sandbox"])
        registry = self.scoped_registry()
        self.assertIn("build_storyboard_project", registry.list_tools()["media"])
        report = registry.dlc_report()[-1]
        self.assertTrue(report["isolated_worker"])
        self.assertEqual("cartridge", report["scope"])

    def test_storyboard_worker_returns_editable_project(self):
        result = self.scoped_registry().call("media", "build_storyboard_project", {
            "episode_script": {"episode_id": "test"},
            "shot_list": {"shots": [{"id": "s1", "description": "Hero walks", "action_tags": ["walk_slow"]}]},
            "asset_plan": {},
            "action_plan": {},
        })
        self.assertTrue(result["ok"], result)
        self.assertEqual("cartridgeflow.storyboard_project.v1", result["project"]["schema"])
        self.assertEqual("blocking", result["project"]["approval"]["status"])

    def test_storyboard_preserves_distinct_ai_scene_camera_and_pose_plans(self):
        result = self.scoped_registry().call("media", "build_storyboard_project", {
            "episode_script": {"episode_id": "scene-plan-test"},
            "shot_list": {"shots": [
                {
                    "id": "street",
                    "title": "Street arrival",
                    "description": "Hero enters a city street.",
                    "scene_design": {"location": "city street", "landmarks": ["bus stop"]},
                    "camera": {"template": "slow_push_in", "position": [-2, -9, 2.5], "target": [0, 1, 1.2], "focal_length_mm": 35},
                    "actor_blocking": {"position": [-1, 2, 0], "pose_time": 0.2},
                    "action_tags": ["walk_slow"],
                },
                {
                    "id": "bedroom",
                    "title": "Bedroom reaction",
                    "description": "Hero turns inside a bedroom.",
                    "scene_design": {"location": "bedroom", "landmarks": ["window"]},
                    "camera": {"template": "close_up_reveal", "position": [2, -3, 1.7], "target": [0, 0.5, 1.5], "focal_length_mm": 72},
                    "characters": ["hero", "partner"],
                    "actor_blocking": [
                        {"actor_id": "hero", "position": [0.7, 0.5, 0], "pose_time": 0.75},
                        {"actor_id": "partner", "position": [-0.8, 1.2, 0], "action": "idle_talk", "pose_time": 0.35},
                    ],
                },
            ]},
            "asset_plan": {},
            "action_plan": {"shots": [
                {"shot_id": "street", "primary_action": {"id": "walk_slow"}, "camera_template": {"id": "slow_push_in"}},
                {"shot_id": "bedroom", "primary_action": {"id": "look_back"}, "camera_template": {"id": "close_up_reveal"}},
            ]},
        })
        self.assertTrue(result["ok"], result)
        street, bedroom = result["project"]["shots"]
        self.assertEqual("street", street["scene"]["archetype"])
        self.assertEqual("bedroom", bedroom["scene"]["archetype"])
        self.assertNotEqual(street["scene"]["environment"], bedroom["scene"]["environment"])
        self.assertEqual([-2.0, -9.0, 2.5], street["camera"]["position"])
        self.assertEqual(72.0, bedroom["camera"]["focal_length_mm"])
        self.assertEqual("walk_slow", street["actors"][0]["action"])
        self.assertEqual("look_back", bedroom["actors"][0]["action"])
        self.assertEqual(2, len(bedroom["actors"]))
        self.assertEqual("idle_talk", bedroom["actors"][1]["action"])
        self.assertNotEqual(street["actors"][0]["pose_time"], bedroom["actors"][0]["pose_time"])

    def test_package_removal_deactivates_existing_proxy(self):
        registry = self.scoped_registry()
        proxy = registry._registry["media"]["build_storyboard_project"]
        proxy.descriptor["_package_path"] = str(PACKAGE / "missing-after-uninstall")
        result = registry.call("media", "build_storyboard_project", {})
        self.assertFalse(result["ok"])
        self.assertEqual("extension_inactive", result["code"])


if __name__ == "__main__":
    unittest.main()
