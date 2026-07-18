import hashlib
import tempfile
import unittest
from pathlib import Path

from core.lab.mcp import creative_recast
from core.protocol.creative_recast import validate_creative_spec, validate_shot_control_bundle


class CreativeRecastContractTest(unittest.TestCase):
    def _bundle(self):
        return {
            "schema": "cartridgeflow.shot_control_bundle.v1",
            "bundle_id": "pilot_01_walk_01.bundle",
            "revision": 1,
            "shot_id": "pilot_01_walk_01",
            "fps": 12,
            "frame_count": 33,
            "width": 480,
            "height": 832,
            "source": {"engine": "blender", "preview": "preview.mp4"},
            "controls": {
                "character_mask": "character_mask.mp4",
                "depth": "depth.mp4",
                "pose": "pose.mp4",
            },
            "mask_convention": {"white": "generate_or_replace", "black": "preserve_control_input"},
            "sha256": {
                "preview.mp4": "0" * 64,
                "character_mask.mp4": "1" * 64,
                "depth.mp4": "2" * 64,
                "pose.mp4": "3" * 64,
            },
            "status": "validated",
        }

    def _spec(self):
        return {
            "schema": "cartridgeflow.creative_spec.v1",
            "spec_id": "pilot_01_recast",
            "revision": 1,
            "mode": "character_replace",
            "cast_pack": "cast.original_anime_male.v1",
            "world_pack": "world.suburban_daylight.v1",
            "style_pack": "style.polished_3d.v1",
            "locked": ["shot.motion", "shot.camera", "shot.timing", "world.landmarks"],
            "free": ["character.identity", "world.materials"],
            "bounds": {
                "character.identity": "CastPack reference images only",
                "world.materials": "StylePack bounded variation",
            },
            "anchors": ["cast.main_reference", "world.house_facade", "shot.camera_path"],
            "allowed_workflows": ["wan21_vace_1_3b_character_replace"],
            "approval": {"status": "approved", "approved_by": "user", "approved_revision": 1},
        }

    def test_valid_control_bundle_manifest_passes_without_io(self):
        result = validate_shot_control_bundle(self._bundle())
        self.assertTrue(result["ok"], result)

    def test_control_bundle_requires_hashes_and_rejects_path_escape(self):
        bundle = self._bundle()
        bundle["sha256"].pop("depth.mp4")
        bundle["controls"]["pose"] = "../pose.mp4"
        result = validate_shot_control_bundle(bundle, Path.cwd(), check_files=True)
        self.assertFalse(result["ok"])
        codes = [item["code"] for item in result["findings"]]
        self.assertIn("control_bundle_hashes", codes)
        self.assertIn("control_bundle_path_escape", codes)

    def test_file_hashes_are_checked_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            content = b"preview"
            (root / "preview.mp4").write_bytes(content)
            bundle = self._bundle()
            bundle["sha256"]["preview.mp4"] = hashlib.sha256(content).hexdigest()
            result = validate_shot_control_bundle(bundle, root, check_files=True)
            self.assertFalse(result["ok"])
            self.assertIn("control_bundle_file_missing", [item["code"] for item in result["findings"]])

    def test_creative_spec_rejects_locked_free_overlap_and_missing_bounds(self):
        spec = self._spec()
        spec["free"].append("shot.camera")
        spec["bounds"].pop("world.materials")
        result = validate_creative_spec(spec)
        self.assertFalse(result["ok"])
        codes = [item["code"] for item in result["findings"]]
        self.assertIn("creative_spec_overlap", codes)
        self.assertIn("creative_spec_bounds", codes)

    def test_approved_creative_spec_passes(self):
        result = validate_creative_spec(self._spec())
        self.assertTrue(result["ok"], result)

    def test_opt_in_mcp_module_exposes_only_read_only_validators(self):
        class RegistryStub:
            def __init__(self, root):
                self._workspace_root = root
                self._registry = {"media": {}}

        registry = RegistryStub(Path.cwd())
        creative_recast.register(registry)
        self.assertEqual(set(creative_recast.TOOLS), set(registry._registry["media"]))
        result = registry._registry["media"]["validate_change_proposal"]({"proposal": {}})
        self.assertFalse(result["ok"])
        self.assertFalse(any(path for path in Path.cwd().glob("change_proposal*")))

    def test_change_proposal_requires_explicit_user_approval_metadata(self):
        proposal = {
            "schema": "cartridgeflow.change_proposal.v1",
            "proposal_id": "crcp-proposal-0001",
            "protocol": "CF-CRCP@0.1",
            "reason": "Test proposal",
            "current": {"workflow": "wan21_vace_1_3b_v2v"},
            "proposed": {"workflow": "wan21_vace_1_3b_character_replace"},
            "affected_locks": ["character.silhouette"],
            "expected_benefit": "Test benefit",
            "cost_and_risk": "Test risk",
            "rollback": "Return to current workflow",
            "question": "Approve this change?",
            "status": "approved",
            "approved_by": "user",
            "approved_revision": 1,
            "approved_at": "2026-07-18T00:00:00Z",
        }
        class RegistryStub:
            def __init__(self):
                self._workspace_root = Path.cwd()
                self._registry = {"media": {}}

        registry = RegistryStub()
        creative_recast.register(registry)
        result = registry._registry["media"]["validate_change_proposal"]({"proposal": proposal})
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
