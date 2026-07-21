import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.extensions.worker_client import cancel_worker_calls_for_run, run_worker_call, shutdown_active_workers


def _worker_fixture(root: Path) -> tuple[Path, dict]:
    package = root / "package"
    backend = package / "dlc" / "backend" / "entry.py"
    backend.parent.mkdir(parents=True)
    backend.write_text(
        "import time\n\ndef invoke(request):\n    time.sleep(float((request.get('params') or {}).get('delay', 0)))\n    return {'ok': True, 'content': 'done'}\n",
        encoding="utf-8",
    )
    descriptor_path = package / "dlc" / "descriptor.json"
    descriptor = {
        "schema": "cartridgeflow.portable_dlc.v1",
        "id": "dlc.worker.fixture",
        "version": "1.0.0",
        "owner_cartridge": "test.worker",
        "tools": [{"server": "fixture", "tool": "sleep", "handler": "backend.entry:invoke"}],
    }
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    descriptor["_descriptor_path"] = str(descriptor_path)
    descriptor["_package_path"] = str(package)
    return package, descriptor


def _request(run_id: str) -> dict:
    return {
        "schema": "cartridgeflow.dlc_worker_request.v1",
        "run_id": run_id,
        "cartridge_id": "test.worker",
        "server": "fixture",
        "tool": "sleep",
        "params": {"delay": 5},
    }


class WorkerLifecycleTests(unittest.TestCase):
    def test_timeout_terminates_worker_and_records_final_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, descriptor = _worker_fixture(root)
            result = run_worker_call(root, package, descriptor, _request("run_timeout"), timeout_ms=100, worker_call_id="timeout_case")
            journal = json.loads((root / ".data" / "runtime" / "workers" / "timeout_case.json").read_text(encoding="utf-8"))

            self.assertEqual("dlc_worker_timeout", result["code"])
            self.assertEqual("timed_out", result["worker_state"])
            self.assertEqual("timed_out", journal["status"])
            self.assertIsNotNone(journal["exit_code"])

    def test_run_cancel_terminates_active_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, descriptor = _worker_fixture(root)
            result = {}

            thread = threading.Thread(target=lambda: result.update(run_worker_call(
                root, package, descriptor, _request("run_cancel"), timeout_ms=10000, worker_call_id="cancel_case",
            )))
            thread.start()
            journal_path = root / ".data" / "runtime" / "workers" / "cancel_case.json"
            for _ in range(100):
                if journal_path.is_file() and json.loads(journal_path.read_text(encoding="utf-8")).get("status") == "running":
                    break
                time.sleep(0.02)
            cancelled = cancel_worker_calls_for_run("run_cancel")
            thread.join(timeout=8)

            self.assertFalse(thread.is_alive())
            self.assertEqual(["cancel_case"], cancelled)
            self.assertEqual("dlc_worker_cancelled", result["code"])
            self.assertEqual("cancelled", json.loads(journal_path.read_text(encoding="utf-8"))["status"])

    def test_host_shutdown_terminates_active_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, descriptor = _worker_fixture(root)
            result = {}

            thread = threading.Thread(target=lambda: result.update(run_worker_call(
                root, package, descriptor, _request("run_shutdown"), timeout_ms=10000, worker_call_id="shutdown_case",
            )))
            thread.start()
            journal_path = root / ".data" / "runtime" / "workers" / "shutdown_case.json"
            for _ in range(100):
                if journal_path.is_file() and json.loads(journal_path.read_text(encoding="utf-8")).get("status") == "running":
                    break
                time.sleep(0.02)
            terminated = shutdown_active_workers("host_exited")
            thread.join(timeout=8)

            self.assertFalse(thread.is_alive())
            self.assertIn("shutdown_case", terminated)
            self.assertEqual("dlc_worker_host_exited", result["code"])
            self.assertEqual("host_exited", json.loads(journal_path.read_text(encoding="utf-8"))["status"])


if __name__ == "__main__":
    unittest.main()
