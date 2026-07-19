import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / "dlc"))

from core.cartridge.runner import CartridgeRunner
from core.extensions.worker_sdk import DlcWorkerRegistry
from backend.mcp import series_3d

LIBRARY_PATH = "cartridges/dev/dev.series_3d_episode_factory/assets/series_asset_library.json"


class Series3dEpisodeFactoryTest(unittest.TestCase):
    def setUp(self):
        self.registry = DlcWorkerRegistry(ROOT, PACKAGE)
        self.registry._registry["media"] = {}
        series_3d.register(self.registry)
        self.script = {
            "schema": "episode_script.v1",
            "title": "Pilot",
            "episode_id": "pilot_test",
            "logline": "A man walks along a suburban street.",
        }
        self.shots = {
            "schema": "shot_list.v1",
            "shots": [
                {
                    "id": "shot_01",
                    "title": "Walk",
                    "description": "The male hero walks along the daytime suburban street.",
                    "scene": "daytime suburban street",
                    "characters": ["hero"],
                    "props": [],
                    "action_tags": ["walk_slow"],
                    "camera": "slow_push_in",
                    "duration": 3,
                }
            ],
        }

    def _match(self):
        params = {
            "episode_script": self.script,
            "shot_list": self.shots,
            "asset_library_path": LIBRARY_PATH,
        }
        assets = self.registry.call("media", "match_series_assets", params)
        actions = self.registry.call("media", "match_series_actions", params)
        self.assertTrue(assets["ok"], assets)
        self.assertTrue(actions["ok"], actions)
        return assets["asset_plan"], actions["action_plan"]

    def test_library_selects_real_pilot_assets(self):
        assets, actions = self._match()
        self.assertEqual([], assets["missing"])
        self.assertEqual("pilot_male_hero", assets["characters"][0]["id"])
        self.assertTrue(assets["characters"][0]["asset_path"])
        self.assertEqual("-Y", assets["characters"][0]["world_transform"]["forward_axis"])
        self.assertEqual(180.0, assets["characters"][0]["world_transform"]["rotation_z_degrees"])
        self.assertEqual("pilot_suburban_street_day", assets["scenes"][0]["id"])
        self.assertTrue(assets["scenes"][0]["components"])
        primary_action = actions["shots"][0]["primary_action"]
        self.assertEqual("walk_slow", primary_action["id"])
        self.assertEqual("Walk_Loop", primary_action["clip_name"])
        self.assertTrue(primary_action["motion_path"])

    def test_script_only_mode_generates_real_asset_blender_script(self):
        assets, actions = self._match()
        output_root = ROOT / "test_output"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as tmpdir:
            relative_output = Path(tmpdir).resolve().relative_to(ROOT).as_posix()
            result = self.registry.call(
                "media",
                "forge_3d_series_episode",
                {
                    "episode_script": self.script,
                    "shot_list": self.shots,
                    "asset_plan": assets,
                    "action_plan": actions,
                    "output_dir": relative_output,
                    "episode_id": "pilot_test",
                    "execute_blender": False,
                },
            )
            self.assertTrue(result["ok"], result)
            self.assertFalse(result["series_episode_ok"])
            self.assertEqual("blender_script_only", result["provider"])
            blender_script = Path(tmpdir) / "pilot_test.blender_scene.py"
            content = blender_script.read_text(encoding="utf-8")
            self.assertIn("Superhero_Male_FullBody.gltf", content)
            self.assertIn("Walk_Loop", content)
            self.assertIn("bpy.ops.import_scene.gltf", content)
            self.assertIn("for index, shot in enumerate(shots, start=1)", content)
            self.assertIn("scene.timeline_markers.new", content)
            self.assertIn("distance * forward_y_sign", content)
            self.assertIn('.final.mp4', content)
            self.assertNotIn("primitive_cube_add", content)
            manifest = json.loads((Path(tmpdir) / "pilot_test.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("blender_script_created", manifest["status"])
            self.assertEqual("full_episode", manifest["render_scope"])
            self.assertEqual("script_only_not_rendered", manifest["quality_gate"])

    def test_control_pass_generation_is_explicitly_opt_in(self):
        assets, actions = self._match()
        output_root = ROOT / "test_output"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as tmpdir:
            relative_output = Path(tmpdir).resolve().relative_to(ROOT).as_posix()
            result = self.registry.call(
                "media",
                "forge_3d_series_episode",
                {
                    "episode_script": self.script,
                    "shot_list": self.shots,
                    "asset_plan": assets,
                    "action_plan": actions,
                    "output_dir": relative_output,
                    "episode_id": "pilot_control",
                    "execute_blender": False,
                    "render_control_passes": True,
                },
            )
            self.assertTrue(result["ok"], result)
            script = (Path(tmpdir) / "pilot_control.blender_scene.py").read_text(encoding="utf-8")
            compile(script, "pilot_control.blender_scene.py", "exec")
            self.assertIn("_render_control_bundle", script)
            self.assertIn("character_mask.mp4", script)
            self.assertIn("pose.json", script)
            self.assertIn("scene.render.film_transparent = True", script)
            self.assertIn("view_layer.use_pass_z = True", script)
            plan = json.loads((Path(tmpdir) / "pilot_control.episode_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["render_settings"]["render_control_passes"])

    def test_exact_action_id_beats_generic_idle_tag(self):
        shots = json.loads(json.dumps(self.shots))
        shots["shots"][0]["action_tags"] = ["idle_talk"]
        shots["shots"][0]["camera"] = "close_up_reveal"
        result = self.registry.call(
            "media",
            "match_series_actions",
            {
                "episode_script": self.script,
                "shot_list": shots,
                "asset_library_path": LIBRARY_PATH,
            },
        )
        self.assertTrue(result["ok"], result)
        plan = result["action_plan"]["shots"][0]
        self.assertEqual("idle_talk", plan["primary_action"]["id"])
        self.assertEqual("Idle_Talking_Loop", plan["primary_action"]["clip_name"])
        self.assertEqual("close_up_reveal", plan["camera_template"]["id"])

    def test_unsupported_action_blocks_render_instead_of_falling_back(self):
        unsupported_shots = json.loads(json.dumps(self.shots))
        unsupported_shots["shots"][0]["action_tags"] = ["fly_loop"]
        params = {
            "episode_script": self.script,
            "shot_list": unsupported_shots,
            "asset_library_path": LIBRARY_PATH,
        }
        assets = self.registry.call("media", "match_series_assets", params)
        actions = self.registry.call("media", "match_series_actions", params)
        self.assertTrue(assets["ok"], assets)
        self.assertTrue(actions["ok"], actions)
        self.assertEqual("action", actions["action_plan"]["missing"][0]["type"])
        result = self.registry.call(
            "media",
            "forge_3d_series_episode",
            {
                "episode_script": self.script,
                "shot_list": unsupported_shots,
                "asset_plan": assets["asset_plan"],
                "action_plan": actions["action_plan"],
                "output_dir": "test_output/series_3d_episode/unsupported_action",
                "execute_blender": False,
            },
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["missing_actions"])

    def test_blend_artifact_is_classified_as_model(self):
        runner = object.__new__(CartridgeRunner)
        self.assertEqual("model", runner._artifact_type_for_path(Path("episode.blend")))
        self.assertEqual("application/x-blender", runner._mime_type_for_path(Path("episode.blend")))


if __name__ == "__main__":
    unittest.main()
