import json
import unittest
from pathlib import Path

from core.cartridge.validator import ManifestValidator
from core.lab.flow_analyzer import analyze_flow_structure
from core.protocol import build_protocol_certification_report, load_base_implementation


ROOT = Path(__file__).resolve().parents[2]
CART = ROOT / "cartridges" / "dev" / "dev.pixel_episode_director"


class PixelEpisodeDirectorProtocolTest(unittest.TestCase):
    def _load(self):
        manifest = json.loads((CART / "manifest.json").read_text(encoding="utf-8"))
        root_flow = json.loads((CART / "root.flow.json").read_text(encoding="utf-8"))
        return manifest, root_flow

    def test_manifest_is_protocol_certified(self):
        manifest, root_flow = self._load()
        ManifestValidator().validate_package(CART, manifest)
        base = load_base_implementation(ROOT)
        report = build_protocol_certification_report(base, manifest, root_flow, ROOT)
        self.assertTrue(report["ok"], report.get("findings"))
        self.assertEqual(report["status"], "certified")
        self.assertEqual(report["label"], "cf-farp-0-4-certified")
        self.assertEqual(manifest["protocol_certification"]["label"], report["label"])

    def test_only_intentional_isolated_nodes_exist(self):
        _, root_flow = self._load()
        structure = analyze_flow_structure(root_flow)
        suspicious = [
            item for item in structure["findings"]
            if item.get("severity") == "warning"
        ]
        self.assertEqual([], suspicious)
        self.assertEqual([], structure["findings"])


if __name__ == "__main__":
    unittest.main()
