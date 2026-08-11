import copy
import unittest
from pathlib import Path

from core.protocol import BaseManifestError, build_clean_base_candidate, load_base_implementation
from core.protocol.base_manifest import validate_base_implementation


ROOT = Path(__file__).resolve().parents[3]


class BaseManifestConformanceTest(unittest.TestCase):
    def test_base_manifest_loads(self):
        base = load_base_implementation(ROOT)
        self.assertEqual(base["implementation_id"], "cartridgeflow.reference-dev")
        self.assertEqual(base["supported_protocols"][0]["id"], "CF-FARP")
        self.assertEqual(
            ["0.6", "0.7", "0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7"],
            [item["version"] for item in base["supported_protocols"] if item["id"] == "CF-FARP"],
        )
        self.assertEqual({"id": "CARTRIDGEFLOW-BASE", "version": "0.3"}, base["base_contract"])
        self.assertEqual("CF-TUNING", base["supported_subprotocols"][0]["id"])
        self.assertIn("runtime_core", base["profiles"])
        self.assertIn("tool_transparency", base["profiles"])

    def test_clean_candidate_is_valid_but_mixed_layers_fail_closed(self):
        candidate = build_clean_base_candidate(ROOT)
        self.assertEqual("clean-v1", candidate["protocol_generation"]["id"])
        validate_base_implementation(candidate)

        mixed = copy.deepcopy(candidate)
        mixed["protocol_generation"]["layers"][0]["runtime_adapter"] = "cf.foundation.v1"
        with self.assertRaisesRegex(BaseManifestError, "does not match clean-v1"):
            validate_base_implementation(mixed)


if __name__ == "__main__":
    unittest.main()
