from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "launch_authoring.py"
SPEC = importlib.util.spec_from_file_location("cartridgeflow_launch_authoring", SCRIPT)
assert SPEC and SPEC.loader
LAUNCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCH)


class LaunchAuthoringTests(unittest.TestCase):
    def test_vite_environment_targets_the_authoring_api(self) -> None:
        with patch.dict("os.environ", {"PATH": "test"}, clear=True):
            environment = LAUNCH._vite_environment()
        self.assertEqual("http://127.0.0.1:8000", environment["VITE_API_BASE_URL"])

    def test_refuses_any_occupied_authoring_port(self) -> None:
        with patch.object(LAUNCH, "_port_is_available", side_effect=[True, False, True]):
            with self.assertRaisesRegex(SystemExit, "5180"):
                LAUNCH._require_available_ports()
