from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from core.protocol import (
    ProtocolRegistry,
    build_release_envelope_report,
    load_base_implementation,
    load_protocol_artifact_text,
    load_protocol_release_catalog,
)


ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = "protocol/release-envelope/1/specification.md"


def digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def canonical_bytes(value: dict | list) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def payload_digest(entries: list[dict]) -> str:
    payload = [
        {"path": entry["path"], "sha256": entry["sha256"], "size": entry["size"]}
        for entry in sorted(entries, key=lambda entry: entry["path"])
        if entry["path"].startswith("payload/")
    ]
    return digest(canonical_bytes(payload))


def valid_release_bundle():
    experience = {
        "schema": "cartridgeflow.cartridge_experience.v1",
        "product": {"name": "Daily brief", "category": "content.video"},
        "inputs": [{"id": "topic", "label": "Topic", "type": "string", "required": True, "sensitive": False}],
        "stages": [{"id": "prepare", "label": "Prepare"}, {"id": "deliver", "label": "Deliver"}],
    }
    delivery = {
        "schema": "cartridgeflow.delivery_contract.v1",
        "primary_artifacts": [{"id": "main_video", "label": "Video", "mime_types": ["video/mp4"]}],
        "attachments": [],
        "revision": {"mode": "new_run"},
        "delivery_states": ["produced", "delivered", "failed"],
    }
    files = {
        "public/experience.json": canonical_bytes(experience),
        "public/delivery.contract.json": canonical_bytes(delivery),
        "payload/manifest.json": b'{"id":"daily.brief"}',
        "payload/root.flow.json": b'{"states":{"start":{}}}',
        "proof/portability.json": b'{"status":"ok"}',
    }
    entries = [
        {"path": path, "sha256": digest(content), "size": len(content)}
        for path, content in sorted(files.items())
    ]
    hashes_bytes = canonical_bytes({"schema": "cartridgeflow.release_hashes.v1", "files": entries})
    content_digest = digest(hashes_bytes)
    release = {
        "schema": "cartridgeflow.release_envelope.v1",
        "release": {"publisher_id": "publisher.example", "cartridge_id": "daily.brief", "version": "1.2.0"},
        "release_id": f"publisher.example:daily.brief@1.2.0+{content_digest}",
        "runtime": {
            "base_contract": {"id": "CARTRIDGEFLOW-BASE", "version": "0.2"},
            "flow_contract": {"id": "CF-FARP", "version": "0.9"},
            "min_runner_version": "1.0.0",
        },
        "execution": {"placement": "either", "required_capabilities": ["media.ffmpeg"], "required_permissions": ["filesystem.output"]},
        "public_contracts": {
            "experience": {"path": "public/experience.json", "digest": digest(files["public/experience.json"])},
            "delivery": {"path": "public/delivery.contract.json", "digest": digest(files["public/delivery.contract.json"])},
        },
        "payload": {"path": "payload", "digest": payload_digest(entries)},
        "integrity": {"hashes_path": "hashes.json", "content_digest": content_digest},
        "signatures": [{"role": "publisher", "key_id": "publisher-key-2026", "algorithm": "ed25519", "path": "signatures/publisher.ed25519"}],
    }
    bundle = {**files, "hashes.json": hashes_bytes, "signatures/publisher.ed25519": b"signature-bytes"}
    return release, experience, delivery, bundle


def refresh_bundle_integrity(release, bundle):
    entries = json.loads(bundle["hashes.json"])["files"]
    hashes_bytes = canonical_bytes({"schema": "cartridgeflow.release_hashes.v1", "files": entries})
    content_digest = digest(hashes_bytes)
    bundle["hashes.json"] = hashes_bytes
    release["release_id"] = f"{release['release']['publisher_id']}:{release['release']['cartridge_id']}@{release['release']['version']}+{content_digest}"
    release["integrity"] = {"hashes_path": "hashes.json", "content_digest": content_digest}
    release["payload"] = {"path": "payload", "digest": payload_digest(entries)}


def replace_hashed_file(release, bundle, path, content):
    bundle[path] = content
    entries = json.loads(bundle["hashes.json"])["files"]
    for entry in entries:
        if entry["path"] == path:
            entry["sha256"] = digest(content)
            entry["size"] = len(content)
            break
    release["public_contracts"]["experience" if path == "public/experience.json" else "delivery"] = {
        "path": path,
        "digest": digest(content),
    }
    bundle["hashes.json"] = canonical_bytes({"schema": "cartridgeflow.release_hashes.v1", "files": entries})
    refresh_bundle_integrity(release, bundle)


class ReleaseEnvelopeProtocolTests(unittest.TestCase):
    def test_catalog_registers_a_supported_release_builder_without_changing_flow_default(self):
        catalog = load_protocol_release_catalog(ROOT)
        release = catalog.default_release_envelope()
        self.assertEqual(("CF-CRE", "1"), (release["id"], release["version"]))
        self.assertEqual("supported", release["implementation_status"])
        self.assertEqual({"id": "CF-FARP", "version": "1.1"}, catalog.data["default_for_new_flows"])
        self.assertEqual("CF-CRE", catalog.public_payload()["release_envelopes"]["default_for_new_releases"]["id"])
        base = load_base_implementation(ROOT)
        self.assertIn(("CF-CRE", "1"), {(item["id"], item["version"]) for item in base["supported_protocols"]})
        registry = ProtocolRegistry(ROOT)
        self.assertTrue(registry.supports_protocol("CF-CRE", "1"))
        self.assertIn("release_envelope_builder_v1", registry.capabilities)

    def test_valid_release_bundle_passes_static_validation(self):
        release, experience, delivery, bundle = valid_release_bundle()
        report = build_release_envelope_report(release, experience, delivery, bundle_files=bundle)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual("compatible", report["status"])
        self.assertEqual("supported", report["implementation_status"])

    def test_public_contract_cannot_leak_internal_connection_fields(self):
        release, experience, delivery, bundle = valid_release_bundle()
        experience = deepcopy(experience)
        experience["endpoint"] = "https://private.example"
        replace_hashed_file(release, bundle, "public/experience.json", canonical_bytes(experience))
        report = build_release_envelope_report(release, experience, delivery, bundle_files=bundle)
        self.assertIn("cre_public_contract_leaks_internal", {item["code"] for item in report["findings"]})

    def test_bundle_public_contract_is_the_validated_source_not_a_caller_shadow(self):
        release, experience, delivery, bundle = valid_release_bundle()
        leaked = deepcopy(experience)
        leaked["endpoint"] = "https://private.example/secret"
        replace_hashed_file(release, bundle, "public/experience.json", canonical_bytes(leaked))

        report = build_release_envelope_report(release, experience, delivery, bundle_files=bundle)
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("cre_public_contract_leaks_internal", codes)
        self.assertIn("cre_public_contract_object_mismatch", codes)
        self.assertFalse(report["ok"])

    def test_altered_or_unlisted_bundle_content_is_rejected(self):
        release, experience, delivery, bundle = valid_release_bundle()
        altered = dict(bundle)
        altered["payload/root.flow.json"] = b"tampered"
        altered_report = build_release_envelope_report(release, experience, delivery, bundle_files=altered)
        self.assertIn("cre_hashed_file_mismatch", {item["code"] for item in altered_report["findings"]})

        unlisted = dict(bundle)
        unlisted["payload/unlisted.json"] = b"{}"
        unlisted_report = build_release_envelope_report(release, experience, delivery, bundle_files=unlisted)
        self.assertIn("cre_bundle_file_unlisted", {item["code"] for item in unlisted_report["findings"]})

    @unittest.skipIf(
        load_base_implementation(ROOT)["protocol_generation"]["id"] == "clean-v1",
        "CF-CRE@1 source snapshots are historical after the clean-v1 cutover",
    )
    def test_protocol_document_declares_active_support_boundary(self):
        text = load_protocol_artifact_text(DOCUMENT)
        self.assertIn("CF-CRE@1", text)
        self.assertIn("active/supported", text)
        self.assertIn("晋级条件", text)


if __name__ == "__main__":
    unittest.main()
