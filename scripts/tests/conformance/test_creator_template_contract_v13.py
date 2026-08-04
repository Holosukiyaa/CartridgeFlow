import unittest

from core.protocol.creator_templates import create_instance, validate_template
from core.protocol.tuning import TuningProtocolError


TEMPLATE = {"schema": "cartridgeflow.developer_recipe_template.v1", "protocol": {"id": "CF-TUNING", "version": "1.3"}, "id": "daily-brief", "revision": 1, "steps": [{"id": "sources", "creator_label": "确认信息来源", "editable_fields": ["topics"], "developer_mapping_key": "daily.sources.v1", "required": True}]}


class CreatorTemplateContractV13Tests(unittest.TestCase):
    def test_instance_is_pinned_to_developer_mapping(self):
        instance = create_instance(TEMPLATE, "instance.daily", {"sources": {"topics": ["AI"]}})
        self.assertEqual("daily.sources.v1", instance["steps"][0]["developer_mapping_key"])

    def test_rejects_unmapped_or_out_of_contract_fields(self):
        bad = dict(TEMPLATE); bad["steps"] = [dict(TEMPLATE["steps"][0], developer_mapping_key="")]
        with self.assertRaises(TuningProtocolError): validate_template(bad)
        with self.assertRaises(TuningProtocolError): create_instance(TEMPLATE, "instance.daily", {"sources": {"tools": "hidden"}})
