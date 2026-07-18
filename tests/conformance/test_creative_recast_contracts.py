import hashlib
import tempfile
import unittest
from pathlib import Path

from core.lab.mcp import creative_recast
from core.protocol import build_creative_recast_certification_report, validate_candidate_review, validate_failure_record, validate_run_snapshot
from core.protocol.creative_recast import CRCP_REQUIRED_CAPABILITIES, validate_cast_pack, validate_creative_spec, validate_shot_control_bundle


ROOT = Path(__file__).resolve().parents[2]


class CreativeRecastContractTest(unittest.TestCase):
    def _candidate_review(self, decision="accepted"):
        gate_status = "passed" if decision == "accepted" else "failed"
        return {
            "schema": "cartridgeflow.candidate_review.v1",
            "review_id": "review-001",
            "run_id": "run_pilot_01",
            "run_revision": 1,
            "candidate": {"path": "candidate.mp4", "sha256": "6" * 64},
            "evidence": {
                "run_report": {"path": "run_report.json", "sha256": "7" * 64},
                "run_snapshot": {"path": "run_snapshot.json", "sha256": "8" * 64},
            },
            "gates": {
                "technical": {"status": "passed", "notes": "Technical gate passed."},
                "motion": {"status": gate_status, "notes": "Motion reviewed."},
                "character": {"status": gate_status, "notes": "Character reviewed."},
                "continuity": {"status": gate_status, "notes": "Continuity reviewed."},
            },
            "user_review": {
                "decision": decision,
                "reviewed_by": "user",
                "reviewed_at": "2026-07-18T00:00:00+08:00",
                "feedback": "Candidate reviewed explicitly.",
            },
            "failure_labels": [] if decision == "accepted" else ["identity_drift"],
            "status": decision,
        }

    def _cast_pack(self):
        reference = "frontend/src/assets/hero.png"
        digest = hashlib.sha256((ROOT / reference).read_bytes()).hexdigest()
        return {
            "schema": "cartridgeflow.cast_pack.v1",
            "pack_id": "cast.original_anime_male.v1",
            "revision": 1,
            "character_id": "hero_male",
            "display_name": "Approved male hero",
            "references": {"primary": reference, "additional": []},
            "appearance": {
                "wardrobe": ["dark hero outfit"],
                "hair": "short dark hair",
                "fixed_colors": {"hair": "#202020", "outfit": "#303840"},
                "immutable_features": ["adult male", "athletic build"],
            },
            "license": {"name": "test fixture", "source": "repository fixture", "public_delivery_allowed": True},
            "sha256": {reference: digest},
            "status": "approved",
            "approval": {"status": "approved", "approved_by": "user", "approved_revision": 1},
        }

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

    def test_approved_cast_pack_checks_identity_license_and_reference_hash(self):
        pack = self._cast_pack()
        result = validate_cast_pack(pack, ROOT, check_files=True)
        self.assertTrue(result["ok"], result)
        pack["license"]["public_delivery_allowed"] = False
        pack["sha256"][pack["references"]["primary"]] = "0" * 64
        result = validate_cast_pack(pack, ROOT, check_files=True)
        self.assertFalse(result["ok"])
        codes = [item["code"] for item in result["findings"]]
        self.assertIn("cast_pack_license", codes)
        self.assertIn("cast_pack_hash_mismatch", codes)

    def test_candidate_review_requires_four_gates_and_explicit_user_decision(self):
        accepted = self._candidate_review()
        self.assertTrue(validate_candidate_review(accepted)["ok"])
        accepted["gates"]["character"]["status"] = "pending"
        result = validate_candidate_review(accepted)
        self.assertFalse(result["ok"])
        self.assertIn("candidate_review_gates", [item["code"] for item in result["findings"]])

        pending = self._candidate_review()
        pending["status"] = "pending_user"
        pending["user_review"] = {"decision": "pending", "reviewed_by": "", "reviewed_at": "", "feedback": ""}
        pending["gates"]["motion"] = {"status": "pending", "notes": "Awaiting review."}
        self.assertTrue(validate_candidate_review(pending, deliverable=False)["ok"])
        self.assertFalse(validate_candidate_review(pending, deliverable=True)["ok"])

    def test_opt_in_mcp_module_exposes_only_its_declared_tools(self):
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

    def _snapshot(self):
        return {
            "schema": "cartridgeflow.run_snapshot.v1",
            "snapshot_id": "pilot_01_run_0001",
            "run_id": "run_pilot_01",
            "revision": 1,
            "protocol": {"id": "CF-CRCP", "version": "0.1"},
            "creative_spec": {"spec_id": "pilot_01_recast", "revision": 1},
            "control_bundle": {"bundle_id": "pilot_01_walk_01.bundle", "revision": 1},
            "workflow": {"id": "wan21_vace_1_3b_character_replace", "sha256": "4" * 64},
            "model": {"id": "wan2.1-vace-1.3b", "sha256": "5" * 64},
            "seed": 42,
            "parameters": {"steps": 8, "cfg": 5.0, "width": 480, "height": 832},
            "outputs": [],
            "status": "locked",
            "approval": {"status": "approved", "approved_by": "user", "approved_revision": 1},
        }

    def test_locked_run_snapshot_passes_and_completed_snapshot_needs_output(self):
        snapshot = self._snapshot()
        self.assertTrue(validate_run_snapshot(snapshot)["ok"])
        snapshot["status"] = "accepted"
        result = validate_run_snapshot(snapshot)
        self.assertFalse(result["ok"])
        self.assertIn("run_snapshot_outputs", [item["code"] for item in result["findings"]])

    def test_current_base_cannot_receive_crcp_certification(self):
        from core.protocol import load_base_implementation

        report = build_creative_recast_certification_report(
            load_base_implementation(Path(__file__).resolve().parents[2]),
            {"protocol_extensions": [{"id": "CF-CRCP", "version": "0.1"}]},
            {
                "cast_pack": self._cast_pack(),
                "candidate_review": self._candidate_review(),
                "creative_spec": self._spec(),
                "shot_control_bundle": self._bundle(),
                "run_snapshot": self._snapshot(),
            },
        )
        self.assertFalse(report["ok"])
        self.assertIn("crcp_protocol_unsupported", [item["code"] for item in report["findings"]])

    def test_complete_capability_fixture_can_pass_crcp_artifact_report(self):
        base = {
            "supported_protocols": [{"id": "CF-CRCP", "version": "0.1"}],
            "profiles": ["creative_control_runtime"],
            "capabilities": list(CRCP_REQUIRED_CAPABILITIES),
        }
        manifest = {
            "protocol_extensions": [
                {
                    "id": "CF-CRCP",
                    "version": "0.1",
                    "required_profiles": ["creative_control_runtime"],
                    "required_capabilities": list(CRCP_REQUIRED_CAPABILITIES),
                }
            ]
        }
        report = build_creative_recast_certification_report(
            base,
            manifest,
            {
                "cast_pack": self._cast_pack(),
                "candidate_review": self._candidate_review(),
                "creative_spec": self._spec(),
                "shot_control_bundle": self._bundle(),
                "run_snapshot": self._snapshot(),
            },
        )
        self.assertTrue(report["ok"], report)

    def test_runtime_runs_blender_then_forced_comfy_and_stops_for_review(self):
        control_bundle = self._bundle()

        class RegistryStub:
            def __init__(self):
                self._workspace_root = Path.cwd()
                self._registry = {"media": {}}
                self.calls = []

            def call(self, server, tool, params):
                self.calls.append((server, tool, params))
                if tool == "forge_3d_series_episode":
                    return {"ok": True, "path": "preview.mp4", "files": ["preview.mp4"], "control_bundle": control_bundle}
                if tool == "run_vace_character_replace":
                    return {"ok": True, "path": "enhanced.mp4", "files": ["enhanced.mp4"]}
                return {"ok": False, "error": f"unexpected tool: {tool}"}

        registry = RegistryStub()
        creative_recast.register(registry)
        result = registry._registry["media"]["run_creative_recast"]({
            "current_state": "control_ready",
            "creative_spec": self._spec(),
            "cast_pack": self._cast_pack(),
            "shot_control_bundle": self._bundle(),
            "run_snapshot": self._snapshot(),
            "blender_params": {"episode_id": "pilot_01"},
            "comfy_params": {"input_manifest": "control.json"},
        })
        self.assertTrue(result["ok"], result)
        self.assertEqual("review_required", result["state"])
        self.assertTrue(result["requires_user_review"])
        self.assertEqual(["forge_3d_series_episode", "run_vace_character_replace"], [item[1] for item in registry.calls])
        self.assertTrue(registry.calls[0][2]["render_control_passes"])
        self.assertEqual(control_bundle, registry.calls[1][2]["control_bundle"])
        self.assertEqual(self._spec(), registry.calls[1][2]["creative_spec"])
        self.assertEqual(self._cast_pack(), registry.calls[1][2]["cast_pack"])
        self.assertEqual(self._snapshot(), registry.calls[1][2]["run_snapshot"])

    def test_runtime_failure_returns_rejected_failure_record(self):
        class RegistryStub:
            def __init__(self):
                self._workspace_root = Path.cwd()
                self._registry = {"media": {}}

            def call(self, server, tool, params):
                return {"ok": False, "error": "Blender control render failed", "files": []}

        registry = RegistryStub()
        creative_recast.register(registry)
        result = registry._registry["media"]["run_creative_recast"]({
            "current_state": "control_ready",
            "creative_spec": self._spec(),
            "cast_pack": self._cast_pack(),
            "shot_control_bundle": self._bundle(),
            "run_snapshot": self._snapshot(),
        })
        self.assertFalse(result["ok"])
        self.assertEqual("rejected", result["state"])
        self.assertTrue(validate_failure_record(result["failure_record"])["ok"])


if __name__ == "__main__":
    unittest.main()
