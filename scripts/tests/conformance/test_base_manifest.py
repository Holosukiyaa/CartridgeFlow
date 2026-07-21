import unittest
from pathlib import Path

from core.protocol import load_base_implementation


ROOT = Path(__file__).resolve().parents[3]


class BaseManifestConformanceTest(unittest.TestCase):
    def test_base_manifest_loads(self):
        base = load_base_implementation(ROOT)
        self.assertEqual(base["implementation_id"], "cartridgeflow.reference-dev")
        self.assertEqual(base["supported_protocols"][0]["id"], "CF-FARP")
        self.assertEqual(
            ["0.6"],
            [item["version"] for item in base["supported_protocols"] if item["id"] == "CF-FARP"],
        )
        self.assertEqual({"id": "CARTRIDGEFLOW-BASE", "version": "0.2"}, base["base_contract"])
        self.assertIn("runtime_core", base["profiles"])


if __name__ == "__main__":
    unittest.main()
