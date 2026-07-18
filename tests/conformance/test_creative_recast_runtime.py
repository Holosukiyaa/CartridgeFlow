import hashlib
import unittest
from pathlib import Path

from core.protocol.creative_recast_runtime import (
    transition_crcp_run,
    validate_failure_record,
)


class CreativeRecastRuntimeTest(unittest.TestCase):
    def _candidate_review(self):
        artifact = "tests/conformance/test_creative_recast_runtime.py"
        digest = hashlib.sha256((Path.cwd() / artifact).read_bytes()).hexdigest()
        return {
            "schema": "cartridgeflow.candidate_review.v1",
            "review_id": "review-001",
            "run_id": "run-001",
            "run_revision": 1,
            "candidate": {"path": artifact, "sha256": digest},
            "evidence": {
                "run_report": {"path": artifact, "sha256": digest},
                "run_snapshot": {"path": artifact, "sha256": digest},
            },
            "gates": {
                name: {"status": "passed", "notes": f"{name} passed."}
                for name in ["technical", "motion", "character", "continuity"]
            },
            "user_review": {
                "decision": "accepted",
                "reviewed_by": "user",
                "reviewed_at": "2026-07-18T00:00:00+08:00",
                "feedback": "Accepted after review.",
            },
            "failure_labels": [],
            "status": "accepted",
        }

    def _snapshot(self):
        return {
            "schema": "cartridgeflow.run_snapshot.v1",
            "snapshot_id": "snapshot-001",
            "run_id": "run-001",
            "revision": 1,
            "protocol": {"id": "CF-CRCP", "version": "0.1"},
            "creative_spec": {"spec_id": "spec-001", "revision": 1},
            "control_bundle": {"bundle_id": "bundle-001", "revision": 1},
            "workflow": {"id": "workflow-001", "sha256": "a" * 64},
            "model": {"id": "model-001", "sha256": "b" * 64},
            "seed": 42,
            "parameters": {"steps": 8},
            "outputs": [],
            "status": "locked",
            "approval": {"status": "approved", "approved_by": "user", "approved_revision": 1},
        }

    def _failure(self):
        return {
            "schema": "cartridgeflow.failure_record.v1",
            "failure_id": "failure-001",
            "shot_id": "shot-001",
            "run_revision": 1,
            "label": "temporal_flicker",
            "user_feedback": "The character flickers in the middle frames.",
            "actual_change": "Identity drift after frame 12.",
            "output_location": "runs/run-001/output.mp4",
            "rollback_target": "snapshot-001",
            "retry_index": 0,
            "changed_fields": ["world.lighting"],
            "recommendation": "Retry with the approved style bounds.",
        }

    def test_failure_record_requires_protocol_labels_and_rollback(self):
        record = self._failure()
        self.assertTrue(validate_failure_record(record)["ok"])
        record["label"] = "random_failure"
        result = validate_failure_record(record)
        self.assertFalse(result["ok"])
        self.assertIn("failure_record_label", [item["code"] for item in result["findings"]])

    def test_happy_path_requires_each_crcp_stage(self):
        context = {}
        self.assertTrue(transition_crcp_run("draft", "awaiting_user_approval", context)["ok"])
        context["approval"] = {"status": "approved", "approved_by": "user"}
        self.assertTrue(transition_crcp_run("awaiting_user_approval", "approved", context)["ok"])
        context.update({"creative_spec": {"ok": True}, "shot_control_bundle": {"ok": True}})
        self.assertTrue(transition_crcp_run("approved", "control_ready", context)["ok"])
        context["run_snapshot"] = self._snapshot()
        self.assertTrue(transition_crcp_run("control_ready", "running_blender", context)["ok"])
        context["blender_ok"] = True
        self.assertTrue(transition_crcp_run("running_blender", "running_comfy", context)["ok"])
        context["outputs"] = [{"path": "output.mp4"}]
        self.assertTrue(transition_crcp_run("running_comfy", "review_required", context)["ok"])
        context["candidate_review"] = self._candidate_review()
        context["workspace_root"] = Path.cwd()
        self.assertTrue(transition_crcp_run("review_required", "accepted", context)["ok"])

    def test_acceptance_rejects_legacy_boolean_shortcut(self):
        result = transition_crcp_run(
            "review_required",
            "accepted",
            {"user_review": "accepted", "quality_gate": True},
        )
        self.assertFalse(result["ok"])
        self.assertIn("run_review_required", [item["code"] for item in result["findings"]])

    def test_state_machine_rejects_bypass_and_requires_failure_record(self):
        result = transition_crcp_run("approved", "running_comfy", {})
        self.assertFalse(result["ok"])
        self.assertEqual("approved", result["state"])
        result = transition_crcp_run("review_required", "rejected", {})
        self.assertFalse(result["ok"])
        self.assertIn("failure_record", " ".join(item["code"] for item in result["findings"]))

    def test_rejected_retry_requires_explicit_retry_and_valid_record(self):
        failure = self._failure()
        result = transition_crcp_run("rejected", "awaiting_user_approval", {"failure_record": failure})
        self.assertFalse(result["ok"])
        result = transition_crcp_run("rejected", "awaiting_user_approval", {"failure_record": failure, "retry": True})
        self.assertTrue(result["ok"], result)

    def test_blocked_and_accepted_are_terminal(self):
        self.assertFalse(transition_crcp_run("blocked", "awaiting_user_approval", {})["ok"])
        self.assertFalse(transition_crcp_run("accepted", "rejected", {})["ok"])


if __name__ == "__main__":
    unittest.main()
