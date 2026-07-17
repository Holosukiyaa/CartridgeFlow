import unittest

from core.protocol import validate_tool_plan


def manifest():
    return {
        "mcp_tools": [
            {
                "id": "render_episode",
                "type": "builtin",
                "server": "media",
                "tool": "render",
                "contract": {"side_effect": "writes_run_artifacts"},
                "params_schema": {
                    "type": "object",
                    "required": ["episode_id", "shot_count"],
                    "properties": {
                        "episode_id": {"type": "string"},
                        "shot_count": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
            }
        ]
    }


def node():
    return {
        "type": "process",
        "kind": "mcp_execute",
        "executor": "mcp",
        "effect": "writes_artifacts",
        "allowed_tools": ["render_episode"],
    }


def plan(**overrides):
    data = {
        "schema": "tool_plan.v1",
        "tool_id": "render_episode",
        "params": {"episode_id": "ep_001", "shot_count": 3},
        "expected_output": "render_bundle",
        "failure_policy": "fail_closed",
    }
    data.update(overrides)
    return data


class ToolPlanV1Test(unittest.TestCase):
    def test_valid_tool_plan_passes(self):
        findings = validate_tool_plan(plan(), manifest(), node())
        self.assertEqual([], findings)

    def test_unallowed_tool_blocks(self):
        findings = validate_tool_plan(plan(tool_id="other_tool"), manifest(), node())
        self.assertIn("tool_plan_tool_not_declared", [item["code"] for item in findings])
        self.assertIn("tool_plan_tool_not_allowed", [item["code"] for item in findings])

    def test_params_schema_mismatch_blocks(self):
        findings = validate_tool_plan(plan(params={"episode_id": "ep_001", "shot_count": "three"}), manifest(), node())
        self.assertIn("tool_plan_param_type_invalid", [item["code"] for item in findings])

    def test_side_effect_tool_requires_side_effect_node(self):
        safe_node = dict(node())
        safe_node["effect"] = "read_only"
        findings = validate_tool_plan(plan(), manifest(), safe_node)
        self.assertIn("tool_plan_effect_conflict", [item["code"] for item in findings])


if __name__ == "__main__":
    unittest.main()
