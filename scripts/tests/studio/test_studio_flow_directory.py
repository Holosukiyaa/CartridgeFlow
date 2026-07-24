import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend import main


class _Registry:
    def __init__(self, cartridge):
        self.cartridge = cartridge

    def get_cartridge(self, cartridge_id):
        if cartridge_id != self.cartridge.get("id"):
            raise FileNotFoundError(cartridge_id)
        return self.cartridge


class StudioFlowDirectoryTests(unittest.TestCase):
    def test_opens_registered_directory_inside_workspace(self):
        path = main.ROOT / "src"
        registry = _Registry({"id": "dev.demo", "package_path": str(path)})

        with patch.object(main, "registry", registry), patch.object(main, "_open_directory") as opener:
            result = main.open_lab_flow_directory("dev.demo")

        self.assertTrue(result["ok"])
        self.assertEqual("dev.demo", result["id"])
        opener.assert_called_once_with(path.resolve())

    def test_rejects_registered_directory_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            registry = _Registry({"id": "external.demo", "package_path": temporary_directory})
            with patch.object(main, "registry", registry), self.assertRaises(HTTPException) as raised:
                main.open_lab_flow_directory("external.demo")

        self.assertEqual(403, raised.exception.status_code)

    def test_rejects_missing_registered_directory(self):
        registry = _Registry({"id": "missing.demo", "package_path": ""})
        with patch.object(main, "registry", registry), self.assertRaises(HTTPException) as raised:
            main.open_lab_flow_directory("missing.demo")

        self.assertEqual(404, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
