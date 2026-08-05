from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "launch.py"
SPEC = importlib.util.spec_from_file_location("cartridgeflow_launch", SCRIPT)
assert SPEC and SPEC.loader
LAUNCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCH)


class LaunchTests(unittest.TestCase):
    def test_restarts_identified_listener(self) -> None:
        with patch.object(LAUNCH, "listener_pids", side_effect=[[42], []]), patch.object(
            LAUNCH, "process_command_line", return_value="python -m uvicorn backend.main:app"
        ), patch.object(LAUNCH.subprocess, "run") as run:
            LAUNCH.restart_managed_listener(8765, "backend.main:app")

        run.assert_called_once_with(["taskkill", "/PID", "42", "/T", "/F"], check=False, capture_output=True)

    def test_refuses_to_stop_foreign_listener(self) -> None:
        with patch.object(LAUNCH, "listener_pids", return_value=[99]), patch.object(
            LAUNCH, "process_command_line", return_value="python unrelated_service.py"
        ), patch.object(LAUNCH.subprocess, "run") as run:
            with self.assertRaisesRegex(SystemExit, "was not stopped"):
                LAUNCH.restart_managed_listener(8765, "backend.main:app")

        run.assert_not_called()

    def test_build(self) -> None:
        with patch.object(LAUNCH.shutil, "which", return_value="npm.cmd"), patch.object(
            LAUNCH.Path, "exists", return_value=True
        ), patch.object(LAUNCH.subprocess, "run") as run:
            LAUNCH.ensure_frontend_bundle()

        run.assert_called_once_with(["npm.cmd", "run", "build"], cwd=LAUNCH.FRONTEND_DIR, check=True)

    def test_early_exit(self) -> None:
        process = MagicMock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(SystemExit, "stopped before"):
            LAUNCH.wait_until_ready(process)
