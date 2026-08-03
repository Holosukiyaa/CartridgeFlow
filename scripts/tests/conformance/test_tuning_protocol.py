import copy
import unittest

from core.protocol.tuning import (
    TuningConflictError,
    TuningProtocolError,
    activate_recipe_release,
    canonical_digest,
    create_node_revision,
    create_tuning_repository,
    flow_source_digest,
    materialize_tuning,
    publish_recipe_release,
    validate_tuning_release,
    validate_tuning_repository,
)


def example_flow():
    return {
        "schema_version": "1.0",
        "id": "dev.example.root",
        "protocol": {"id": "CF-FARP", "version": "1.1"},
        "start": "start",
        "states": {
            "start": {"type": "control", "title": "开始", "layout": {"x": 0, "y": 0}},
            "write": {
                "type": "process",
                "kind": "transform",
                "executor": "llm",
                "effect": "none",
                "title": "写作",
                "params": {"prompt": "draft", "temperature": 0.2},
            },
            "complete": {"type": "terminal", "title": "完成"},
        },
        "execution_plan": {
            "schema": "cartridgeflow.execution_plan.v1",
            "entry": "start",
            "edges": [
                {"id": "start-write", "kind": "sequence", "from": "start", "to": "write"},
                {"id": "write-complete", "kind": "sequence", "from": "write", "to": "complete"},
            ],
        },
    }


def example_experience():
    return {
        "schema": "cartridgeflow.node_experience.v1",
        "visible": True,
        "stage": {
            "label": "生成文章",
            "description": "根据已确认素材生成文章。",
            "waiting": "等待生成文章",
            "running": "正在生成文章",
            "success": "文章已生成",
        },
        "interaction": {
            "mode": "automatic",
            "prompt": "",
            "action_labels": {},
            "fields": [],
            "allow_retry": True,
            "allow_cancel": True,
        },
        "materials": {
            "visibility": "output",
            "label": "文章草稿",
            "live_updates": True,
            "allow_download": False,
            "hidden_fields": ["trace_id"],
        },
        "outcome": {
            "success_title": "文章生成完成",
            "result_label": "文章草稿",
            "empty_text": "暂时没有文章",
            "error_title": "文章生成失败",
            "error_message": "可以重试本步骤。",
            "retry_label": "重新生成",
            "preserve_partial": True,
        },
        "controls": [
            {
                "parameter": "temperature",
                "label": "创意程度",
                "help": "调整表达变化。",
                "control": "slider",
                "required": False,
                "options": [],
                "minimum": 0,
                "maximum": 2,
                "step": 0.1,
            }
        ],
    }


class TuningProtocolTests(unittest.TestCase):
    def test_node_experience_is_versioned_and_materialized_without_execution_fields(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, revision = create_node_revision(
            repository,
            flow,
            "write",
            {"experience": example_experience()},
            expected_head=None,
            author="tester",
            message="配置普通用户体验",
        )
        repository, release = publish_recipe_release(repository, flow, author="tester", message="user experience v1")
        materialized, _ = materialize_tuning(flow, release)
        self.assertEqual("生成文章", materialized["states"]["write"]["experience"]["stage"]["label"])
        self.assertNotIn("executor", revision["patch"])
        self.assertNotIn("next", revision["patch"])

    def test_node_experience_rejects_unsafe_or_ambiguous_controls(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        cases = []
        unknown_field = example_experience()
        unknown_field["route"] = "complete"
        cases.append(unknown_field)
        secret_control = example_experience()
        secret_control["controls"][0]["parameter"] = "provider.api_key"
        cases.append(secret_control)
        invalid_mode = example_experience()
        invalid_mode["interaction"]["mode"] = "execute_code"
        cases.append(invalid_mode)
        unknown_input = example_experience()
        unknown_input["interaction"]["mode"] = "input"
        unknown_input["interaction"]["fields"] = [{
            "field": "invented_field",
            "label": "不存在的字段",
            "help": "",
            "placeholder": "",
            "control": "text",
            "required": False,
            "options": [],
        }]
        cases.append(unknown_input)
        unknown_parameter = example_experience()
        unknown_parameter["controls"][0]["parameter"] = "invented_parameter"
        cases.append(unknown_parameter)
        for experience in cases:
            with self.subTest(experience=experience), self.assertRaises(TuningProtocolError):
                create_node_revision(
                    repository,
                    flow,
                    "write",
                    {"experience": experience},
                    expected_head=None,
                    author="tester",
                    message="invalid experience",
                )

    def test_revision_is_immutable_and_uses_optimistic_head(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        updated, revision = create_node_revision(
            repository,
            flow,
            "write",
            {"params": {"prompt": "final", "temperature": 0.4}},
            expected_head=None,
            author="tester",
            message="调优写作",
            created_at="2026-08-03T00:00:00+00:00",
        )
        self.assertIsNone(repository["node_heads"].get("write"))
        self.assertEqual(revision["id"], updated["node_heads"]["write"])
        with self.assertRaises(TuningConflictError):
            create_node_revision(
                updated,
                flow,
                "write",
                {"title": "过期写入"},
                expected_head=None,
                author="tester",
                message="stale",
            )

    def test_forbidden_topology_secrets_and_local_paths_fail_closed(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        cases = [
            {"next": "complete"},
            {"params": {"api_key": "secret"}},
            {"params": {"output": "C:\\private\\output.txt"}},
            {"params": {"script": "console.log('not allowed')"}},
        ]
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(TuningProtocolError):
                create_node_revision(
                    repository,
                    flow,
                    "write",
                    patch,
                    expected_head=None,
                    author="tester",
                    message="invalid",
                )

        with self.assertRaises(TuningProtocolError):
            create_node_revision(
                repository,
                flow,
                "write",
                {"title": "安全标题"},
                expected_head=None,
                author="".join(("sk-", "sensitive-audit-token")),
                message="invalid audit metadata",
            )

        with self.assertRaises(TuningProtocolError):
            publish_recipe_release(
                repository,
                flow,
                author="tester",
                message=" ".join(("bearer", "sensitive-release-token")),
            )

    def test_release_materialization_and_rollback_are_deterministic(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, revision_one = create_node_revision(
            repository,
            flow,
            "write",
            {"params": {"prompt": "v1", "temperature": 0.3}},
            expected_head=None,
            author="tester",
            message="v1",
            created_at="2026-08-03T00:00:00+00:00",
        )
        repository, release_one = publish_recipe_release(
            repository,
            flow,
            author="tester",
            message="first",
            created_at="2026-08-03T00:01:00+00:00",
        )
        repository, _ = create_node_revision(
            repository,
            flow,
            "write",
            {"params": {"prompt": "v2", "temperature": 0.6}},
            expected_head=revision_one["id"],
            author="tester",
            message="v2",
            created_at="2026-08-03T00:02:00+00:00",
        )
        repository, release_two = publish_recipe_release(
            repository,
            flow,
            author="tester",
            message="second",
            created_at="2026-08-03T00:03:00+00:00",
        )
        materialized, context = materialize_tuning(flow, release_two)
        self.assertEqual("v2", materialized["states"]["write"]["params"]["prompt"])
        self.assertEqual(release_two["id"], context["release_id"])
        repository, rolled_back = activate_recipe_release(repository, release_one["id"])
        restored, restored_context = materialize_tuning(flow, rolled_back)
        self.assertEqual("v1", restored["states"]["write"]["params"]["prompt"])
        self.assertEqual(release_one["id"], repository["active_release_id"])
        self.assertEqual(release_one["id"], restored_context["release_id"])

    def test_release_tampering_and_stale_flow_are_rejected(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, _ = create_node_revision(
            repository,
            flow,
            "write",
            {"title": "精调写作"},
            expected_head=None,
            author="tester",
            message="tune",
        )
        repository, release = publish_recipe_release(repository, flow, author="tester", message="release")
        tampered = copy.deepcopy(release)
        tampered["patches"]["write"]["title"] = "被篡改"
        with self.assertRaises(TuningProtocolError):
            validate_tuning_release(tampered, flow)
        changed_flow = copy.deepcopy(flow)
        changed_flow["states"]["write"]["effect"] = "external_side_effect"
        with self.assertRaises(TuningProtocolError):
            materialize_tuning(changed_flow, release)

    def test_repository_release_must_resolve_immutable_revision(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, revision = create_node_revision(
            repository,
            flow,
            "write",
            {"params": {"temperature": 0.4}},
            expected_head=None,
            author="tester",
            message="tune",
            created_at="2026-08-03T00:00:00+00:00",
        )
        repository, release = publish_recipe_release(
            repository,
            flow,
            author="tester",
            message="publish",
            created_at="2026-08-03T00:01:00+00:00",
        )

        missing_revision = copy.deepcopy(repository)
        missing_revision["revisions"] = []
        with self.assertRaisesRegex(TuningProtocolError, "does not resolve"):
            validate_tuning_repository(missing_revision, flow)

        mismatched_patch = copy.deepcopy(repository)
        changed_release = mismatched_patch["releases"][0]
        changed_release["patches"]["write"] = {"params": {"temperature": 0.8}}
        body = {key: copy.deepcopy(value) for key, value in changed_release.items() if key not in {"id", "digest"}}
        digest = canonical_digest(body)
        changed_release["digest"] = digest
        changed_release["id"] = f"recipe-v0001-{digest[:8]}"
        mismatched_patch["active_release_id"] = changed_release["id"]
        with self.assertRaisesRegex(TuningProtocolError, "differs from its revision"):
            validate_tuning_repository(mismatched_patch, flow)

        self.assertEqual(revision["id"], release["node_revisions"]["write"])

    def test_repository_rejects_cross_flow_release_and_sequence_gaps(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, _ = create_node_revision(
            repository,
            flow,
            "write",
            {"title": "精调写作"},
            expected_head=None,
            author="tester",
            message="tune",
            created_at="2026-08-03T00:00:00+00:00",
        )
        repository, _ = publish_recipe_release(
            repository,
            flow,
            author="tester",
            message="first",
            created_at="2026-08-03T00:01:00+00:00",
        )

        cross_flow = copy.deepcopy(repository)
        changed_release = cross_flow["releases"][0]
        changed_release["flow_id"] = "dev.other"
        body = {key: copy.deepcopy(value) for key, value in changed_release.items() if key not in {"id", "digest"}}
        digest = canonical_digest(body)
        changed_release["digest"] = digest
        changed_release["id"] = f"recipe-v0001-{digest[:8]}"
        cross_flow["active_release_id"] = changed_release["id"]
        with self.assertRaisesRegex(TuningProtocolError, "flow identity"):
            validate_tuning_repository(cross_flow, flow)

        sequence_gap = copy.deepcopy(repository)
        changed_release = sequence_gap["releases"][0]
        changed_release["sequence"] = 2
        body = {key: copy.deepcopy(value) for key, value in changed_release.items() if key not in {"id", "digest"}}
        digest = canonical_digest(body)
        changed_release["digest"] = digest
        changed_release["id"] = f"recipe-v0002-{digest[:8]}"
        sequence_gap["active_release_id"] = changed_release["id"]
        with self.assertRaisesRegex(TuningProtocolError, "sequence"):
            validate_tuning_repository(sequence_gap, flow)

    def test_layout_does_not_change_effect_source_digest(self):
        flow = example_flow()
        moved = copy.deepcopy(flow)
        moved["states"]["start"]["layout"] = {"x": 900, "y": -100}
        moved["annotations"] = [{"id": "note", "text": "layout only"}]
        self.assertEqual(flow_source_digest(flow), flow_source_digest(moved))

    def test_explicit_publish_carries_tuning_across_ai_topology_change(self):
        flow = example_flow()
        repository = create_tuning_repository("dev.example", flow)
        repository, first = create_node_revision(
            repository,
            flow,
            "write",
            {"params": {"prompt": "kept", "temperature": 0.5}},
            expected_head=None,
            author="tester",
            message="tune",
            created_at="2026-08-03T00:00:00+00:00",
        )
        changed = copy.deepcopy(flow)
        changed["states"]["prepare"] = {"type": "process", "kind": "transform", "executor": "deterministic", "effect": "none"}
        repository, release = publish_recipe_release(
            repository,
            changed,
            author="tester",
            message="AI updated outline",
            created_at="2026-08-03T00:05:00+00:00",
        )
        carried = repository["node_heads"]["write"]
        self.assertNotEqual(first["id"], carried)
        self.assertEqual(first["id"], next(item for item in repository["revisions"] if item["id"] == carried)["parent_id"])
        self.assertEqual(carried, release["node_revisions"]["write"])
        materialized, _ = materialize_tuning(changed, release)
        self.assertEqual("kept", materialized["states"]["write"]["params"]["prompt"])


if __name__ == "__main__":
    unittest.main()
