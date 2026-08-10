from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import (
    load_base_implementation,
    load_protocol_artifact_json,
    load_protocol_artifact_text,
    load_protocol_release_catalog,
)


class CreatorPackageProtocolV16Tests(unittest.TestCase):
    def test_release_is_published_and_supported_without_runtime_tuning_authority(self):
        catalog = load_protocol_release_catalog(ROOT)
        release = catalog.get("CF-FARP", "1.6")
        self.assertEqual("supported_previous", release["lifecycle"])
        self.assertEqual("cf-farp.execution-plan.v1", release["runtime_adapter"])
        self.assertEqual([], release.get("trusted_subprotocols", []))
        supported = {(item["id"], item["version"]) for item in load_base_implementation(ROOT)["supported_protocols"]}
        self.assertIn(("CF-FARP", "1.6"), supported)

    def test_release_snapshots_define_one_atomic_package_boundary(self):
        release_dir = "flow-authoring/1.6"
        registry = load_protocol_artifact_json(f"{release_dir}/release.json")
        capabilities = load_protocol_artifact_json(f"{release_dir}/capabilities.json")
        document = load_protocol_artifact_text(f"{release_dir}/README.md")
        self.assertEqual("1.6", registry["version"])
        self.assertIn("creator_atomic_package_boundary_v1", {item["id"] for item in capabilities["capabilities"]})
        self.assertIn("does not require a second", document)
        self.assertIn("never installs or executes", document)


if __name__ == "__main__":
    unittest.main()
