from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "launch.py"
SPEC = importlib.util.spec_from_file_location("cartridgeflow_launch_port_safety", SCRIPT)
assert SPEC and SPEC.loader
LAUNCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCH)


class LaunchPortSafetyTests(unittest.TestCase):
    def test_refuses_any_occupied_authoring_port(self) -> None:
        connection = MagicMock()
        with patch.object(LAUNCH.socket, "create_connection", return_value=connection):
            with self.assertRaisesRegex(SystemExit, "8765"):
                LAUNCH.require_port_available(LAUNCH.PORT)
