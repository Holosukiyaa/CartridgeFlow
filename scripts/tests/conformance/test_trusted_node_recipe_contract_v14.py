import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.llm.creator_flow_skill import build_creator_flow_messages, parse_creator_flow_result
from core.llm.creator_node_skill import build_creator_node_messages, parse_creator_node_result
from core.protocol.trusted_node_recipes import create_dynamic_recipe, creator_recipe_projection, validate_preset
from core.protocol.tuning import TuningProtocolError


def preset(preset_id="rss-source", mapping="source.rss.v1", revision=1):
    return {
        "schema": "cartridgeflow.trusted_node_preset.v1",
        "protocol": {"id": "CF-TUNING", "version": "1.4"},
        "id": preset_id,
        "revision": revision,
        "creator_label": "收集公开信息源",
        "creator_description": "按主题收集可供用户审核的公开信息源。",
        "match_terms": ["RSS", "日报", "信息源"],
        "editable_fields": [{"id": "topics", "label": "关注主题", "value_type": "string_list", "required": True, "default": ["AI"]}],
        "developer_mapping_key": mapping,
    }


class TrustedNodeRecipeContractV14Tests(unittest.TestCase):
    def test_dynamic_recipe_resolves_mapping_only_from_registry(self):
        recipe = create_dynamic_recipe("recipe.daily", "制作 AI 日报", {"nodes": [{"id": "sources", "preset_id": "rss-source", "values": {"topics": ["AI", "模型"]}}], "relations": []}, [preset()])
        self.assertEqual("source.rss.v1", recipe["nodes"][0]["developer_mapping_key"])
        projection = creator_recipe_projection(recipe, [preset()])
        self.assertNotIn("developer_mapping", json.dumps(projection))
        self.assertEqual(["AI", "模型"], projection["nodes"][0]["values"]["topics"])

    def test_unknown_preset_field_and_cycle_fail_closed(self):
        with self.assertRaises(TuningProtocolError):
            create_dynamic_recipe("recipe.bad", "bad", {"nodes": [{"id": "invented", "preset_id": "first-week-output", "values": {}}], "relations": []}, [preset()])
        with self.assertRaises(TuningProtocolError):
            create_dynamic_recipe("recipe.bad", "bad", {"nodes": [{"id": "source", "preset_id": "rss-source", "values": {"executor": "x"}}], "relations": []}, [preset()])
        draft = {"nodes": [{"id": "one", "preset_id": "rss-source", "values": {}}, {"id": "two", "preset_id": "rss-source", "values": {}}], "relations": [{"id": "r1", "from_node_id": "one", "to_node_id": "two", "relation": "informs"}, {"id": "r2", "from_node_id": "two", "to_node_id": "one", "relation": "informs"}]}
        with self.assertRaises(TuningProtocolError):
            create_dynamic_recipe("recipe.cycle", "bad", draft, [preset()])

    def test_whole_flow_and_node_skills_hide_mapping_and_limit_output(self):
        messages = build_creator_flow_messages("制作 AI 日报", [preset()])
        self.assertNotIn("source.rss.v1", messages[1]["content"])
        recipe, _ = parse_creator_flow_result('{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}', "制作 AI 日报", "recipe.daily", [preset()])
        fenced, _ = parse_creator_flow_result('```json\n{"recipe":{"nodes":[{"id":"sources","preset_id":"rss-source","values":{"topics":["AI"]}}],"relations":[]}}\n```', "制作 AI 日报", "recipe.daily", [preset()])
        self.assertEqual(recipe["nodes"][0]["id"], fenced["nodes"][0]["id"])
        node = recipe["nodes"][0]
        node_messages = build_creator_node_messages(node, preset(), "增加模型主题")
        self.assertNotIn("source.rss.v1", node_messages[1]["content"])
        self.assertEqual({"topics": ["AI", "模型"]}, parse_creator_node_result('{"values":{"topics":["AI","模型"]}}', preset()))
        with self.assertRaises(Exception):
            parse_creator_node_result('{"values":{"tools":["hidden"]}}', preset())

    def test_preset_rejects_missing_mapping_and_required_default(self):
        bad = preset(); bad["developer_mapping_key"] = ""
        with self.assertRaises(TuningProtocolError): validate_preset(bad)
        bad = preset(); bad["editable_fields"][0]["default"] = None
        with self.assertRaises(TuningProtocolError): validate_preset(bad)


if __name__ == "__main__":
    unittest.main()
