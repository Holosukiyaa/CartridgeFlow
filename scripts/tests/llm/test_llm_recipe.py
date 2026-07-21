import json
import tempfile
import unittest
from pathlib import Path

from core.cartridge.validator import ManifestValidationError, ManifestValidator
from core.lab.dev_flow import DevFlowManager


def manifest_with(recipe: dict) -> dict:
    return {
        "schema_version": "1.0",
        "id": "test.llm_recipe",
        "name": "LLM Recipe Test",
        "version": "0.0.1",
        "kind": "runtime_cartridge",
        "category": "test",
        "runtime": {"type": "lab"},
        "root_flow": {"entry": "root.flow.json"},
        "llm_recipe": recipe,
    }


class LlmRecipeManifestTests(unittest.TestCase):
    def validate(self, manifest: dict):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "root.flow.json").write_text(json.dumps({"start": "done", "states": {"done": {"type": "terminal"}}}), encoding="utf-8")
            return ManifestValidator().validate_package(package, manifest)

    def test_accepts_portable_model_role(self):
        recipe = {
            "schema": "cartridgeflow.llm_recipe.v1",
            "roles": [{
                "id": "copywriter",
                "label": "Copywriter",
                "capability": "text_generation",
                "api_type": "openai",
                "wire_api": "chat_completions",
                "model": "example-model",
                "required": True,
            }],
        }
        result = self.validate(manifest_with(recipe))
        self.assertEqual(result["llm_recipe"], recipe)

    def test_rejects_local_credentials_and_urls(self):
        recipe = {
            "schema": "cartridgeflow.llm_recipe.v1",
            "roles": [{
                "id": "copywriter",
                "label": "Copywriter",
                "capability": "text_generation",
                "api_type": "openai",
                "wire_api": "chat_completions",
                "model": "example-model",
                "required": True,
                "connection": {"base_url": "https://example.invalid", "api_key": "secret"},
            }],
        }
        with self.assertRaises(ManifestValidationError) as context:
            self.validate(manifest_with(recipe))
        message = str(context.exception)
        self.assertIn("base_url is local-only", message)
        self.assertIn("api_key is local-only", message)

    def test_rejected_recipe_is_not_written_to_dev_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DevFlowManager(temp_dir)
            created = manager.create_flow("credential-boundary", "Credential Boundary")
            manifest_path = Path(created["path"]) / "manifest.json"
            original = manifest_path.read_text(encoding="utf-8")
            invalid = json.loads(original)
            invalid["llm_recipe"] = {
                "schema": "cartridgeflow.llm_recipe.v1",
                "roles": [{
                    "id": "writer",
                    "label": "Writer",
                    "capability": "text_generation",
                    "api_type": "openai",
                    "wire_api": "chat_completions",
                    "model": "example-model",
                    "required": True,
                    "api_key": "must-not-persist",
                }],
            }
            with self.assertRaises(ManifestValidationError):
                manager.save_file("dev.credential-boundary", "manifest", json.dumps(invalid))

            persisted = manifest_path.read_text(encoding="utf-8")
            self.assertEqual(persisted, original)
            self.assertNotIn("must-not-persist", persisted)


if __name__ == "__main__":
    unittest.main()
