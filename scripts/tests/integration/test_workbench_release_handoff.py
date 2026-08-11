from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as backend_main
from core.data_paths import PACKAGES_DIR
from core.protocol import inspect_release_archive
from core.protocol.release_signing import generate_signing_identity
from core.studio.release import (
    ProductionReleaseError,
    build_production_release_handoff,
    package_history,
)


ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source(root: Path) -> Path:
    source = root / "source"
    _write_json(
        source / "manifest.json",
        {
            "schema_version": "1.0",
            "id": "dev.release-handoff",
            "name": "Release handoff",
            "version": "0.1.0",
            "publisher": {"id": "test.publisher"},
            "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
            "runtime_contract": {
                "protocol": "CF-FARP",
                "protocol_version": "1.1",
                "target_runtimes": [{"id": "CF-DRP", "version": "1.0"}],
            },
            "inputs": [{"id": "topic", "label": "Topic", "type": "text", "required": True}],
            "outputs": [{"id": "delivery", "label": "Delivery", "type": "text"}],
            "delivery": {"primary_output": "delivery"},
            "asset_registry": "assets/registry.json",
        },
    )
    _write_json(
        source / "root.flow.json",
        {
            "protocol": {"id": "CF-FARP", "version": "1.1"},
            "states": {
                "generate": {
                    "type": "process",
                    "action": "pass_result",
                    "params": {"length": "normal"},
                }
            },
            "execution_plan": {"edges": []},
        },
    )
    _write_json(source / "assets" / "registry.json", {"schema": "cartridgeflow.asset_registry.v1", "assets": []})
    _write_json(
        source / "contracts" / "settings.contract.json",
        {
            "schema": "cartridgeflow.cartridge_settings.v1",
            "storage_scope": "cartridge",
            "fields": [
                {
                    "id": "brief_length",
                    "label": "Brief length",
                    "type": "enum",
                    "default": "normal",
                    "options": [
                        {"value": "short", "label": "Short"},
                        {"value": "normal", "label": "Normal"},
                    ],
                }
            ],
        },
    )
    _write_json(
        source / "settings" / "bindings.json",
        {
            "schema": "cartridgeflow.cartridge_settings_bindings.v1",
            "bindings": [
                {
                    "setting_id": "brief_length",
                    "target": {"kind": "process_param", "node_id": "generate", "param": "length"},
                }
            ],
        },
    )
    _write_json(
        source / "contracts" / "ui.contract.json",
        {"schema": "cartridgeflow.cartridge_ui.v1", "mode": "none", "host_capabilities": []},
    )
    return source


def _identity() -> tuple[object, dict[str, str]]:
    identity = generate_signing_identity("test.publisher.integration")
    return identity, {
        identity.key_id: base64.b64encode(identity.public_key).decode("ascii")
    }


class WorkbenchReleaseHandoffTests(unittest.TestCase):
    def test_builds_verified_v2_and_bound_installation_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            output = temp / PACKAGES_DIR / "release.cf-cre.zip"
            identity, trust = _identity()

            result = build_production_release_handoff(
                source,
                output,
                project_root=ROOT,
                requested_by="integration-test",
                request_id="request-integration",
                plan_id="plan-integration",
                requested_at="2030-01-01T00:00:00Z",
                signing_identity=identity,
                trusted_keys=trust,
            )

            self.assertEqual("CF-CRE@2", result["protocol"])
            self.assertTrue(result["activation_allowed"])
            self.assertEqual(12, len(result["archive_contract_ids"]))
            request = result["installation_request"]
            plan = result["installation_plan"]
            self.assertEqual("cartridgeflow.installation.request", request["contract_id"])
            self.assertEqual("cartridgeflow.installation.plan", plan["contract_id"])
            self.assertEqual("dev.release-handoff", request["payload"]["package_id"])
            self.assertEqual("plan-integration", request["payload"]["plan_id"])
            self.assertEqual(request["payload"]["plan_id"], plan["payload"]["plan_id"])
            self.assertTrue(inspect_release_archive(output, trusted_keys=trust)["activation_allowed"])

            history = package_history(temp)
            self.assertEqual("CF-CRE@2", history[0]["protocol"])

    def test_missing_presentation_contract_fails_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            (source / "contracts" / "ui.contract.json").unlink()
            output = temp / PACKAGES_DIR / "release.cf-cre.zip"

            with self.assertRaisesRegex(ProductionReleaseError, "requires contracts/ui.contract.json") as raised:
                build_production_release_handoff(source, output, project_root=ROOT)

            self.assertEqual("release_presentation_contract_missing", raised.exception.code)
            self.assertFalse(output.exists())

    def test_empty_publisher_fails_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            output = temp / PACKAGES_DIR / "release.cf-cre.zip"

            with self.assertRaises(ProductionReleaseError) as raised:
                build_production_release_handoff(
                    source,
                    output,
                    project_root=ROOT,
                    publisher_id=" ",
                )

            self.assertEqual("release_signing_failed", raised.exception.code)
            self.assertFalse(output.exists())

    def test_invalid_contract_does_not_replace_previous_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            output = temp / PACKAGES_DIR / "release.cf-cre.zip"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"previous-release")
            bindings = json.loads((source / "settings" / "bindings.json").read_text(encoding="utf-8"))
            bindings["bindings"][0]["target"]["node_id"] = "missing-node"
            _write_json(source / "settings" / "bindings.json", bindings)
            identity, trust = _identity()

            with self.assertRaises(ProductionReleaseError) as raised:
                build_production_release_handoff(
                    source,
                    output,
                    project_root=ROOT,
                    signing_identity=identity,
                    trusted_keys=trust,
                )

            self.assertEqual("release_build_failed", raised.exception.code)
            self.assertEqual(b"previous-release", output.read_bytes())
            self.assertEqual([], list(output.parent.glob("*.pending")))

    def test_untrusted_signature_does_not_publish_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            output = temp / PACKAGES_DIR / "release.cf-cre.zip"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"previous-release")
            identity, _trust = _identity()

            with self.assertRaises(ProductionReleaseError) as raised:
                build_production_release_handoff(
                    source,
                    output,
                    project_root=ROOT,
                    signing_identity=identity,
                    trusted_keys={},
                )

            self.assertEqual("release_activation_blocked", raised.exception.code)
            self.assertEqual(b"previous-release", output.read_bytes())


class WorkbenchReleaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(backend_main.app)

    def test_production_package_returns_clean_installation_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            cartridge = {
                "id": "dev.release-handoff",
                "version": "0.1.0",
                "package_path": str(source),
                "manifest": json.loads((source / "manifest.json").read_text(encoding="utf-8")),
                "mcp_tools": [],
            }
            captured: dict = {}

            def build(_source_path, output_file, **kwargs):
                captured.update(kwargs)
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                Path(output_file).write_bytes(b"verified-release")
                return {
                    "protocol": "CF-CRE@2",
                    "release_id": "test.publisher:dev.release-handoff@0.1.0+sha256",
                    "activation_allowed": True,
                    "signature": {"ok": True, "trusted": True},
                    "installation_request": {
                        "contract_id": "cartridgeflow.installation.request",
                        "version": "1.0.0",
                        "payload": {"package_id": "dev.release-handoff", "plan_id": "install-1"},
                    },
                    "installation_plan": {
                        "contract_id": "cartridgeflow.installation.plan",
                        "version": "1.0.0",
                        "payload": {"package_id": "dev.release-handoff", "plan_id": "install-1"},
                    },
                }

            compatibility = {"ok": True, "status": "compatible", "legacy": False, "summary": {}}
            preflight = {"production_ready": True, "portability": {"status": "ok"}}
            with (
                patch.object(backend_main, "ROOT", temp),
                patch.object(backend_main, "PACKAGES_DIR", Path("packages")),
                patch.object(backend_main.registry, "get_packaging_cartridge", return_value=cartridge),
                patch.object(backend_main, "_compatibility_for_cartridge", return_value=compatibility),
                patch.object(backend_main, "_release_preflight_for_cartridge", return_value=preflight),
                patch.object(backend_main, "build_production_release_handoff", side_effect=build),
            ):
                response = self.client.post(
                    "/api/cartridges/dev.release-handoff/package",
                    json={"package_mode": "production", "requested_by": "api-test"},
                )

            self.assertEqual(200, response.status_code, response.text)
            body = response.json()
            self.assertEqual("CF-CRE@2", body["protocol"])
            self.assertEqual("cartridgeflow.installation.request", body["installation_request"]["contract_id"])
            self.assertEqual("cartridgeflow.installation.plan", body["installation_plan"]["contract_id"])
            self.assertEqual("api-test", captured["requested_by"])

    def test_production_package_preserves_release_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = _source(temp)
            cartridge = {
                "id": "dev.release-handoff",
                "version": "0.1.0",
                "package_path": str(source),
                "manifest": json.loads((source / "manifest.json").read_text(encoding="utf-8")),
                "mcp_tools": [],
            }
            compatibility = {"ok": True, "status": "compatible", "legacy": False, "summary": {}}
            preflight = {"production_ready": True, "portability": {"status": "ok"}}
            with (
                patch.object(backend_main, "ROOT", temp),
                patch.object(backend_main, "PACKAGES_DIR", Path("packages")),
                patch.object(backend_main.registry, "get_packaging_cartridge", return_value=cartridge),
                patch.object(backend_main, "_compatibility_for_cartridge", return_value=compatibility),
                patch.object(backend_main, "_release_preflight_for_cartridge", return_value=preflight),
                patch.object(
                    backend_main,
                    "build_production_release_handoff",
                    side_effect=ProductionReleaseError(
                        "release_presentation_contract_missing",
                        "CF-CRE@2 presentation contract is missing.",
                    ),
                ),
            ):
                response = self.client.post(
                    "/api/cartridges/dev.release-handoff/package",
                    json={"package_mode": "production"},
                )

            self.assertEqual(400, response.status_code)
            self.assertEqual("release_presentation_contract_missing", response.json()["detail"]["error"])


if __name__ == "__main__":
    unittest.main()
