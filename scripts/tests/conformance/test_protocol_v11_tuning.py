import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cartridge.registry import CartridgeRegistry
from core.lab.dev_flow import DevFlowManager
from core.lab.flow_analyzer import analyze_flow
from core.protocol import (
    build_compatibility_report,
    load_base_implementation,
    load_protocol_release_catalog,
    supports_subprotocol_release,
)
from core.protocol.tuning import TuningProtocolError


ROOT = Path(__file__).resolve().parents[3]


class ProtocolV11TuningTests(unittest.TestCase):
    def test_current_release_trusts_exact_supported_tuning_protocol(self):
        catalog = load_protocol_release_catalog(ROOT)
        release = catalog.get("CF-FARP", "1.1")
        self.assertEqual("current", release["lifecycle"])
        self.assertIn("trusted_tuning_subprotocol", release["features"])
        self.assertTrue(catalog.trusts_subprotocol("CF-FARP", "1.1", "CF-TUNING", "1.0"))
        base = load_base_implementation(ROOT)
        self.assertTrue(supports_subprotocol_release(base, "CF-TUNING", "1.0", "CF-FARP", "1.1"))

    def test_new_flow_is_v11_and_requires_release_for_package_target(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = DevFlowManager(directory)
            created = manager.create_flow("dev.v11-test", "V11 Test")
            manifest = created["manifest"]
            root_flow = created["root_flow"]
            self.assertEqual({"id": "CARTRIDGEFLOW-BASE", "version": "0.3"}, manifest["base_contract"])
            self.assertEqual("1.1", manifest["runtime_contract"]["protocol_version"])
            self.assertEqual("CF-TUNING", manifest["tuning_contract"]["protocol"])
            self.assertEqual({"id": "CF-FARP", "version": "1.1"}, root_flow["protocol"])

            preview = manager.preview_graph("dev.v11-test")
            base = load_base_implementation(ROOT)
            compatibility = build_compatibility_report(base, manifest, preview["root_flow"], ROOT)
            self.assertTrue(compatibility["ok"], compatibility["findings"])
            package_analysis = analyze_flow(
                preview["root_flow"],
                preview,
                target="package",
                base=base,
                runtime_adapter="cf-farp.execution-plan.v1",
            )
            self.assertIn("RECIPE_RELEASE_REQUIRED", [item["code"] for item in package_analysis["findings"]])

            repository, release = manager.tuning.publish("dev.v11-test", author="tester", message="first")
            self.assertEqual(release["id"], repository["active_release_id"])
            published = CartridgeRegistry(directory).get_runtime_cartridge("dev.v11-test")
            published_analysis = analyze_flow(
                published["root_flow"],
                {**published["manifest"], "tuning_context": published["tuning_context"]},
                target="package",
                base=base,
                runtime_adapter="cf-farp.execution-plan.v1",
            )
            self.assertNotIn("RECIPE_RELEASE_REQUIRED", [item["code"] for item in published_analysis["findings"]])

    def test_registry_separates_draft_preview_from_active_runtime_release(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = DevFlowManager(directory)
            manager.create_flow("dev.runtime-recipe", "Runtime Recipe")
            registry = CartridgeRegistry(directory)

            with self.assertRaises(TuningProtocolError):
                registry.get_runtime_cartridge("dev.runtime-recipe")

            repository, revision, _, _ = manager.tuning.create_revision(
                "dev.runtime-recipe",
                "start",
                {"title": "发布版开始"},
                expected_head=None,
                author="tester",
                message="published",
            )
            repository, release = manager.tuning.publish(
                "dev.runtime-recipe",
                author="tester",
                message="v1",
            )
            manager.tuning.create_revision(
                "dev.runtime-recipe",
                "start",
                {"title": "草稿版开始"},
                expected_head=revision["id"],
                author="tester",
                message="draft",
            )

            draft = registry.get_cartridge("dev.runtime-recipe")
            runtime = registry.get_runtime_cartridge("dev.runtime-recipe")
            self.assertEqual("草稿版开始", draft["root_flow"]["states"]["start"]["title"])
            self.assertEqual("发布版开始", runtime["root_flow"]["states"]["start"]["title"])
            self.assertEqual("draft", draft["tuning_context"]["mode"])
            self.assertEqual(release["id"], runtime["tuning_context"]["release_id"])
            self.assertEqual(release["id"], repository["active_release_id"])

    def test_packaging_requires_the_active_release_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = DevFlowManager(directory)
            manager.create_flow("dev.package-recipe", "Package Recipe")
            repository, first = manager.tuning.publish("dev.package-recipe", author="tester", message="v1")
            repository, second = manager.tuning.publish("dev.package-recipe", author="tester", message="v2")
            registry = CartridgeRegistry(directory)

            packaged = registry.get_packaging_cartridge("dev.package-recipe")
            self.assertEqual(second["id"], packaged["tuning_context"]["release_id"])

            release_path = manager.tuning._release_path("dev.package-recipe")
            release_path.write_text(json.dumps(first), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "active recipe release"):
                registry.get_packaging_cartridge("dev.package-recipe")

    def test_failed_release_snapshot_write_does_not_advance_active_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = DevFlowManager(directory)
            manager.create_flow("dev.atomic-recipe", "Atomic Recipe")
            with patch.object(manager.tuning, "_write_release", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    manager.tuning.publish("dev.atomic-recipe", author="tester", message="v1")
            repository = manager.tuning.load("dev.atomic-recipe")
            self.assertIsNone(repository["active_release_id"])
            self.assertEqual([], repository["releases"])


if __name__ == "__main__":
    unittest.main()
