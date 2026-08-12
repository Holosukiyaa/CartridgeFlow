from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.cartridge.presentation import without_node_settings
from core.lab.dev_flow import DevFlowManager


class DevFlowPresentationTests(unittest.TestCase):
    def test_new_flow_owns_empty_v1_presentation_contracts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = DevFlowManager(temp_dir).create_flow("dev.settings", "Settings")
            package = Path(created["path"])
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            settings = json.loads((package / "contracts" / "settings.contract.json").read_text(encoding="utf-8"))
            bindings = json.loads((package / "settings" / "bindings.json").read_text(encoding="utf-8"))

            self.assertEqual("cartridgeflow.cartridge_settings.v1", settings["schema"])
            self.assertEqual([], settings["fields"])
            self.assertEqual("cartridgeflow.cartridge_settings_bindings.v1", bindings["schema"])
            self.assertEqual("contracts/settings.contract.json", manifest["presentation"]["settings"]["contract"])
            self.assertIn({"id": "CF-DRP", "version": "1.0"}, manifest["runtime_contract"]["target_runtimes"])

    def test_related_flow_and_setting_files_commit_as_one_valid_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DevFlowManager(temp_dir)
            created = manager.create_flow("dev.settings", "Settings")
            flow = created["root_flow"]
            flow["states"]["generate"] = {
                "type": "process", "kind": "transfer", "executor": "deterministic",
                "effect": "none", "action": "pass_result", "params": {"length": "normal"},
            }
            flow["states"]["generate_failed"] = {"type": "terminal", "title": "生成失败", "locked": True}
            flow["execution_plan"]["edges"] = [
                {"id": "start-generate", "kind": "sequence", "from": "start", "to": "generate"},
                {"id": "generate-complete", "kind": "sequence", "from": "generate", "to": "complete"},
                {
                    "id": "generate-failed", "kind": "failure", "from": "generate", "to": "generate_failed",
                    "failure": {"id": "generate_exception", "causes": ["exception"]},
                },
            ]
            settings = {
                "schema": "cartridgeflow.cartridge_settings.v1", "storage_scope": "cartridge",
                "fields": [{"id": "brief.length", "label": "简报长度", "type": "string", "default": "normal"}],
            }
            bindings = {
                "schema": "cartridgeflow.cartridge_settings_bindings.v1",
                "bindings": [{"setting_id": "brief.length", "target": {"kind": "process_param", "node_id": "generate", "param": "length"}}],
            }

            result = manager.save_files("dev.settings", {
                "root_flow": json.dumps(flow, ensure_ascii=False),
                "settings_contract": json.dumps(settings, ensure_ascii=False),
                "settings_bindings": json.dumps(bindings, ensure_ascii=False),
            })

            self.assertEqual(["root_flow", "settings_bindings", "settings_contract"], result["file_types"])
            self.assertEqual("brief.length", json.loads(manager.read_files("dev.settings")["settings_contract"])["fields"][0]["id"])

    def test_invalid_binding_rolls_back_every_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DevFlowManager(temp_dir)
            manager.create_flow("dev.settings", "Settings")
            before = manager.read_files("dev.settings")
            settings = {
                "schema": "cartridgeflow.cartridge_settings.v1", "storage_scope": "cartridge",
                "fields": [{"id": "orphan", "label": "Orphan", "type": "boolean", "default": True}],
            }
            with self.assertRaisesRegex(ValueError, "settings_binding_missing"):
                manager.save_files("dev.settings", {"settings_contract": json.dumps(settings)})
            after = manager.read_files("dev.settings")
            self.assertEqual(before, after)

    def test_deleted_node_removes_its_orphaned_public_fields(self):
        settings = {
            "schema": "cartridgeflow.cartridge_settings.v1", "storage_scope": "cartridge",
            "fields": [{"id": "a", "label": "A", "type": "string"}, {"id": "b", "label": "B", "type": "boolean"}],
        }
        bindings = {
            "schema": "cartridgeflow.cartridge_settings_bindings.v1",
            "bindings": [
                {"setting_id": "a", "target": {"kind": "process_param", "node_id": "removed", "param": "value"}},
                {"setting_id": "b", "target": {"kind": "process_param", "node_id": "kept", "param": "enabled"}},
            ],
        }
        next_settings, next_bindings = without_node_settings(settings, bindings, "removed")
        self.assertEqual(["b"], [item["id"] for item in next_settings["fields"]])
        self.assertEqual(["b"], [item["setting_id"] for item in next_bindings["bindings"]])
        self.assertEqual(2, len(settings["fields"]), "input documents must not be mutated")


if __name__ == "__main__":
    unittest.main()
