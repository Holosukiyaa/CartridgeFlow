import unittest
from pathlib import Path

from core.protocol import load_base_implementation


ROOT = Path(__file__).resolve().parents[2]


class BaseManifestConformanceTest(unittest.TestCase):
    def test_base_manifest_loads(self):
        base = load_base_implementation(ROOT)
        self.assertEqual(base["implementation_id"], "cartridgeflow.reference-dev")
        self.assertEqual(base["supported_protocols"][0]["id"], "CF-FARP")
        self.assertIn("runtime_core", base["profiles"])


if __name__ == "__main__":
    unittest.main()
