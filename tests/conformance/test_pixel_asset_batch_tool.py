import json
import tempfile
import unittest
from pathlib import Path

from core.lab.builtin_mcp import BuiltinMcpRegistry


class PixelAssetBatchToolTest(unittest.TestCase):
    def test_forge_pixel_asset_batch_writes_draft_character(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = root / "assets" / "asset_manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({"approved_assets": {}, "draft_assets": {}}), encoding="utf-8")

            registry = BuiltinMcpRegistry(root)
            specs = {
                "schema": "asset_spec_batch.v1",
                "policy": {"asset_policy": "draft_allowed", "register_mode": "draft"},
                "assets": [
                    {
                        "id": "blue_shirt_actor",
                        "kind": "character",
                        "name": "Blue Shirt Actor",
                        "visual_prompt": "A blue shirt pixel character for a 2.5D stage.",
                        "target_status": "draft",
                        "actions": ["idle", "walk_right"],
                        "palette": {"body": "#2f80d8", "trim": "#7fc7ff"},
                    }
                ],
            }

            result = registry.call("media", "forge_pixel_asset_batch", {
                "asset_specs": json.dumps(specs),
                "asset_policy": "draft_allowed",
                "output_dir": "assets/pixel_stage",
                "asset_manifest_path": "assets/asset_manifest.json",
                "report_path": "out/asset_forge_batch.json",
            })

            self.assertTrue(result["ok"], result)
            self.assertEqual(1, result["asset_count"])
            self.assertEqual(0, result["failed_count"])
            self.assertTrue((root / result["report_path"]).is_file())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            draft_characters = ((manifest.get("draft_assets") or {}).get("characters") or {})
            self.assertIn("blue_shirt_actor", draft_characters)
            profile = draft_characters["blue_shirt_actor"]["profile"]
            spritesheet = draft_characters["blue_shirt_actor"]["spritesheet"]
            self.assertTrue((root / profile).is_file())
            self.assertTrue((root / spritesheet).is_file())


if __name__ == "__main__":
    unittest.main()
