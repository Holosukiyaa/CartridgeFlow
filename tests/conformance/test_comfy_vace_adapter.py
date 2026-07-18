import copy
import json
import unittest
from pathlib import Path

from core.lab.mcp.comfy_vace import (
    WORKFLOW_PATH,
    _cached_nodes,
    _prepare_workflow,
    _review_snapshot,
    _snapshot_parameters,
    _validate_workflow,
)


ROOT = Path(__file__).resolve().parents[2]


class ComfyVaceAdapterTests(unittest.TestCase):
    def _workflow(self):
        return json.loads((ROOT / WORKFLOW_PATH).read_text(encoding="utf-8"))

    def test_allowlisted_workflow_binds_preview_mask_and_reference_explicitly(self):
        workflow = self._workflow()
        _validate_workflow(workflow)
        prepared = _prepare_workflow(
            workflow,
            preview_name="CartridgeFlow/crcp/run/preview.mp4",
            mask_name="CartridgeFlow/crcp/run/character_mask.mp4",
            reference_name="CartridgeFlow/crcp/run/reference.png",
            positive_prompt="anime male, stable motion",
            negative_prompt="surrogate leak, reversed motion",
            parameters={"width": 288, "height": 512, "length": 17, "fps": 12, "seed": 42, "steps": 8, "cfg": 6},
            output_prefix="CartridgeFlow/crcp/run/candidate",
        )
        self.assertEqual(["7", 0], prepared["9"]["inputs"]["control_video"])
        self.assertEqual(["18", 0], prepared["9"]["inputs"]["control_masks"])
        self.assertEqual(["8", 0], prepared["9"]["inputs"]["reference_image"])
        self.assertEqual("CartridgeFlow/crcp/run/character_mask.mp4", prepared["16"]["inputs"]["file"])
        self.assertNotIn("Canny", [node["class_type"] for node in prepared.values()])

    def test_workflow_rejects_temporal_length_that_would_change_frame_count(self):
        with self.assertRaisesRegex(ValueError, "4n\\+1"):
            _prepare_workflow(
                copy.deepcopy(self._workflow()),
                preview_name="preview.mp4",
                mask_name="mask.mp4",
                reference_name="reference.png",
                positive_prompt="positive",
                negative_prompt="negative",
                parameters={"width": 288, "height": 512, "length": 24, "fps": 12},
                output_prefix="candidate",
            )

    def test_cache_status_is_recorded_instead_of_counted_as_new_inference(self):
        status = {"messages": [["execution_cached", {"nodes": ["1", "2", "9"]}]]}
        self.assertEqual(["1", "2", "9"], _cached_nodes(status))

    def test_review_snapshot_appends_candidate_without_mutating_locked_input(self):
        locked = {"status": "locked", "outputs": []}
        review = _review_snapshot(locked, "candidate.mp4", "a" * 64, True)
        self.assertEqual("locked", locked["status"])
        self.assertEqual([], locked["outputs"])
        self.assertEqual("review_required", review["status"])
        self.assertEqual("candidate.mp4", review["outputs"][0]["path"])

    def test_snapshot_parameters_must_be_explicit_and_bound_to_artifacts(self):
        spec = {"spec_id": "spec-1", "revision": 2}
        bundle = {"bundle_id": "bundle-1", "revision": 3, "frame_count": 17, "fps": 12}
        snapshot = {
            "status": "locked",
            "seed": 42,
            "creative_spec": {"spec_id": "spec-1", "revision": 2},
            "control_bundle": {"bundle_id": "bundle-1", "revision": 3},
            "parameters": {"width": 288},
        }
        with self.assertRaisesRegex(ValueError, "parameters are missing"):
            _snapshot_parameters(snapshot, spec, bundle)
        snapshot["parameters"].update({
            "height": 512,
            "length": 17,
            "fps": 12,
            "steps": 8,
            "cfg": 6.0,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "strength": 1.0,
            "denoise": 1.0,
        })
        self.assertEqual(42, _snapshot_parameters(snapshot, spec, bundle)["seed"])
        snapshot["control_bundle"]["revision"] = 4
        with self.assertRaisesRegex(ValueError, "control_bundle reference"):
            _snapshot_parameters(snapshot, spec, bundle)


if __name__ == "__main__":
    unittest.main()
