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
        with patch.dict("os.environ", {"PATH": "test", "VITE_API_BASE_URL": "http://wrong.test"}, clear=True):
            environment = LAUNCH._vite_environment()
        self.assertEqual("http://127.0.0.1:8000", environment["AUTHORING_API_TARGET"])
        self.assertEqual("http://127.0.0.1:8000", environment["VITE_API_PROXY_TARGET"])
        self.assertNotIn("VITE_API_BASE_URL", environment)

    def test_refuses_any_occupied_authoring_port(self) -> None:
        with patch.object(LAUNCH, "_port_is_available", side_effect=[True, False]):
            with self.assertRaisesRegex(SystemExit, "5173"):
                LAUNCH._require_available_ports()

    def test_clears_only_recognized_creator_processes(self) -> None:
        with patch.object(LAUNCH.os, "name", "nt"), \
             patch.object(LAUNCH, "_listening_pids", side_effect=[[101], [], [], []]), \
             patch.object(LAUNCH, "_process_command_line", return_value="uvicorn backend.main:app"), \
             patch.object(LAUNCH, "_port_is_available", return_value=True), \
             patch.object(LAUNCH.subprocess, "run") as run:
            run.return_value.returncode = 0
            LAUNCH._clear_stale_authoring_processes()
        self.assertTrue(any(call.args[0][:3] == ["taskkill", "/PID", "101"] for call in run.call_args_list))

    def test_refuses_to_clear_an_unrecognized_process(self) -> None:
        with patch.object(LAUNCH.os, "name", "nt"), \
             patch.object(LAUNCH, "_listening_pids", side_effect=[[101], [], [], []]), \
             patch.object(LAUNCH, "_process_command_line", return_value="python another_service.py"):
            with self.assertRaisesRegex(SystemExit, "refusing to stop"):
                LAUNCH._clear_stale_authoring_processes()
