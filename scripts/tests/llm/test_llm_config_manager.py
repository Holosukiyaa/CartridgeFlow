import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.data_paths import ensure_data_layout
from core.llm import config_manager as manager


class LlmConfigManagerTests(unittest.TestCase):
    def _context(self, root: Path):
        paths = {
            "ROOT": root,
            "LLM_DIR": root / ".data" / "user" / "config" / "llm",
            "PROVIDERS_PATH": root / ".data" / "user" / "config" / "llm" / "providers.json",
            "ASSIGNMENTS_PATH": root / ".data" / "user" / "config" / "llm" / "assignments.json",
        }
        ensure_data_layout(root)
        return patch.multiple(manager, **paths)

    def _write_config(self, root: Path, providers: list[dict], assignments: dict):
        llm_dir = root / ".data" / "user" / "config" / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        (llm_dir / "providers.json").write_text(json.dumps({"version": 1, "providers": providers}), encoding="utf-8")
        (llm_dir / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")

    def test_first_run_provider_and_default_assignments_are_consistent(self):
        env = {
            "id": "env-openai", "name": "Env OpenAI", "api_type": "openai", "wire_api": "chat_completions",
            "base_url": "https://models.test/v1", "api_key": "", "default_model": "env-model",
            "enabled": True, "source": "env", "timeout": 120,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self._context(root), patch.object(manager, "_env_provider", return_value=env):
                manager.ensure_llm_config()
                active = manager.list_providers(False)
                assignments = manager.get_assignments()
                self.assertEqual(["default-deepseek"], [item["id"] for item in active])
                self.assertEqual("default-deepseek", assignments["defaults"]["runtime"]["provider_id"])

    def test_activate_provider_updates_default_assignments(self):
        providers = [
            {"id": "one", "name": "One", "api_type": "openai", "wire_api": "chat_completions", "base_url": "https://one.test/v1", "api_key": "one-key", "default_model": "model-one", "enabled": True},
            {"id": "two", "name": "Two", "api_type": "openai", "wire_api": "responses", "base_url": "https://two.test/v1", "api_key": "two-key", "default_model": "model-two", "enabled": False},
        ]
        assignments = {
            "version": 1,
            "defaults": {"runtime": {"provider_id": "one", "model": "model-one"}},
            "cartridges": {"flow.demo": {"writer": {"provider_id": "one", "model": "model-one"}}},
            "nodes": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, providers, assignments)
            with self._context(root):
                selected = manager.activate_provider("two")
                current = manager.get_assignments()
                self.assertEqual("two", selected["id"])
                self.assertEqual("two", current["defaults"]["runtime"]["provider_id"])
                self.assertEqual("model-two", current["defaults"]["runtime"]["model"])
                self.assertEqual("two", current["defaults"]["steward"]["provider_id"])
                self.assertEqual("two", manager.get_provider("two")["id"])

    def test_connection_change_invalidates_previous_test(self):
        providers = [{
            "id": "local", "name": "Local", "api_type": "openai", "wire_api": "chat_completions",
            "base_url": "https://one.test/v1", "api_key": "key-one", "default_model": "model-one",
            "enabled": True, "tested_ok": True, "tested_at": "2026-01-01T00:00:00+00:00",
        }]
        assignments = {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, providers, assignments)
            with self._context(root):
                changed = manager.upsert_provider({**providers[0], "default_model": "model-two", "api_key": ""})
                self.assertFalse(changed["tested_ok"])
                self.assertEqual("", changed["tested_at"])
                manager.mark_provider_tested("local", True)
                renamed = manager.upsert_provider({**changed, "name": "Renamed", "api_key": ""})
                self.assertTrue(renamed["tested_ok"])

    def test_cartridge_assignment_model_overrides_provider_default(self):
        providers = [{
            "id": "multi-model", "name": "Multi Model", "api_type": "openai", "wire_api": "chat_completions",
            "base_url": "https://models.test/v1", "api_key": "secret", "default_model": "model-one",
            "available_models": ["model-one", "model-two"], "enabled": True,
        }]
        assignments = {
            "version": 1,
            "defaults": {"writer": {"provider_id": "multi-model", "model": "model-one"}},
            "cartridges": {"flow.demo": {"writer": {"provider_id": "multi-model", "model": "model-two"}}},
            "nodes": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, providers, assignments)
            with self._context(root):
                resolved = manager.resolve_model("writer", "flow.demo")
                provider = manager.get_provider("multi-model")

        self.assertEqual("model-two", resolved.model)
        self.assertEqual("model-one", provider["default_model"])

    def test_delete_provider_cleans_bindings_and_repoints_defaults(self):
        providers = [
            {"id": "one", "name": "One", "api_type": "openai", "wire_api": "chat_completions", "base_url": "https://one.test/v1", "api_key": "one-key", "default_model": "model-one", "enabled": True},
            {"id": "two", "name": "Two", "api_type": "openai", "wire_api": "chat_completions", "base_url": "https://two.test/v1", "api_key": "two-key", "default_model": "model-two", "enabled": False},
        ]
        assignments = {
            "version": 1,
            "defaults": {"runtime": {"provider_id": "one", "model": "model-one"}},
            "cartridges": {"flow.demo": {"writer": {"provider_id": "one", "model": "model-one"}}},
            "nodes": {"flow.demo/node": {"runtime": {"provider_id": "one", "model": "model-one"}}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, providers, assignments)
            with self._context(root):
                self.assertTrue(manager.delete_provider("one"))
                self.assertEqual("two", manager.list_providers(False)[0]["id"])
                current = manager.get_assignments()
                self.assertEqual("two", current["defaults"]["runtime"]["provider_id"])
                self.assertNotIn("flow.demo", current["cartridges"])
                self.assertNotIn("flow.demo/node", current["nodes"])

    def test_unsupported_provider_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, [], {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}})
            with self._context(root):
                with self.assertRaises(ValueError):
                    manager.upsert_provider({
                        "id": "anthropic", "name": "Anthropic", "api_type": "anthropic",
                        "wire_api": "messages", "base_url": "https://anthropic.test", "default_model": "claude",
                    })
                self.assertEqual("", manager.provider_route_issue({"api_type": "openai", "wire_api": "responses"}))
                self.assertIn("images", manager.provider_route_issue({"api_type": "openai", "wire_api": "images"}))

    def test_legacy_media_profile_is_migrated_to_standard_text_connection(self):
        standard = manager.normalize_provider({
            "id": "standard", "name": "Standard", "api_type": "openai", "wire_api": "responses",
            "base_url": "https://models.test/v1", "api_key": "standard-key", "default_model": "text-model",
        })
        img2 = manager.normalize_provider({
            "id": "img2", "name": "Img2", "api_type": "openai", "wire_api": "images",
            "base_url": "https://images.test/v1", "api_key": "img2-key", "default_model": "gpt-image-2",
            "adapter_profile": "img2",
        })
        self.assertEqual(["text_reasoning"], standard["capabilities"])
        self.assertEqual("chat_completions", img2["wire_api"])
        self.assertTrue(img2["enabled"])
        self.assertEqual(["text_reasoning"], img2["capabilities"])
        self.assertEqual("standard", img2["adapter_profile"])

    def test_required_recipe_role_needs_explicit_compatible_binding(self):
        providers = [{
            "id": "local", "name": "Local", "api_type": "openai", "wire_api": "responses",
            "base_url": "https://models.test/v1", "api_key": "local-key", "default_model": "model-one",
            "enabled": True,
        }]
        assignments = {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}}
        manifest = {
            "id": "flow.demo",
            "llm_recipe": {"schema": "cartridgeflow.llm_recipe.v1", "roles": [{
                "id": "writer", "label": "Writer", "capability": "text_generation",
                "api_type": "openai_compatible", "wire_api": "responses",
                "model": "configured-locally", "required": True,
            }]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, providers, assignments)
            with self._context(root):
                blocked = manager.build_model_binding_report(manifest)
                self.assertEqual("blocked", blocked["status"])
                current = manager.get_assignments()
                current["cartridges"] = {"flow.demo": {"writer": {"provider_id": "local", "model": "model-one"}}}
                manager.save_assignments(current)
                ready = manager.build_model_binding_report(manifest)
                self.assertEqual("ok", ready["status"])
                self.assertEqual("local", ready["items"][0]["provider_id"])

                missing_node_role = manager.build_model_binding_report(manifest, {
                    "states": {"decide": {
                        "type": "process", "kind": "decision", "executor": "llm", "action": "llm_prompt",
                    }},
                })
                self.assertEqual("blocked", missing_node_role["status"])
                self.assertEqual("AI 决策节点未选择模型角色", missing_node_role["items"][-1]["message"])

                selected_node_role = manager.build_model_binding_report(manifest, {
                    "states": {"decide": {
                        "type": "process", "kind": "decision", "executor": "llm", "action": "llm_prompt",
                        "model_role": "writer",
                    }},
                })
                self.assertEqual("ok", selected_node_role["status"])
                self.assertEqual("writer", selected_node_role["items"][-1]["model_role"])

    def test_public_provider_and_config_paths_do_not_expose_secrets_or_absolute_paths(self):
        provider = {
            "id": "local", "name": "Local", "api_type": "openai", "wire_api": "chat_completions",
            "base_url": "https://models.test/v1", "api_key": "super-secret", "default_model": "model-one",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_config(root, [provider], {"version": 1, "defaults": {}, "cartridges": {}, "nodes": {}})
            with self._context(root):
                public = manager.public_provider(provider)
                paths = manager.config_paths()
                self.assertNotIn("api_key", public)
                self.assertNotIn("super-secret", json.dumps(public))
                self.assertTrue(public["has_key"])
                self.assertTrue(all(not Path(value).is_absolute() for value in paths.values()))


if __name__ == "__main__":
    unittest.main()
