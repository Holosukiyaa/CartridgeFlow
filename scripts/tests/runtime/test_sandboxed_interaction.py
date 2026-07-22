import hashlib
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.cartridge.assets import load_asset_bundle
from core.extensions.descriptor import PortableDlcValidationError, load_portable_dlc_descriptor
from core.extensions.sandbox_service import SandboxRendererManager


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class SandboxedInteractionTests(unittest.TestCase):
    def _package(self, root: Path, *, inline_script: bool = False):
        (root / "assets").mkdir(parents=True)
        (root / "dlc" / "frontend" / "editor").mkdir(parents=True)
        schema = b'{"type":"object"}'
        (root / "assets" / "answer.json").write_bytes(schema)
        assets = {
            "schema": "cartridgeflow.asset_registry.v1",
            "assets": [{
                "id": "schema.answer", "kind": "schema", "path": "assets/answer.json",
                "media_type": "application/schema+json", "sha256": _hash(schema), "size": len(schema), "executable": False,
            }],
        }
        (root / "assets" / "registry.json").write_text(json.dumps(assets), encoding="utf-8")
        components = {
            "schema": "cartridgeflow.interaction_components.v1",
            "components": [{
                "id": "editor.panel", "version": "1.0.0", "runtime": "sandboxed",
                "entry": {"type": "dlc_frontend", "ref": "editor"},
                "supported_modes": ["review"], "input_schema": "asset:schema.answer",
                "actions": [{"id": "approve", "label": "Approve", "payload_schema": "asset:schema.answer"}],
                "host_capabilities": ["draft.write", "interaction.propose"],
            }],
        }
        (root / "assets" / "components.json").write_text(json.dumps(components), encoding="utf-8")
        script = b"window.addEventListener('message',e=>{const p=e.ports[0];const m=e.data;p.postMessage({schema:'cartridgeflow.interaction_component_message.v1',type:'channel.ready',channel_id:m.channel_id,run_id:m.run_id,cartridge_id:m.cartridge_id,node_id:m.node_id,component_id:m.component_id,interaction_id:m.interaction_id,payload:{nonce:m.nonce}})},{once:true});"
        html = (b"<!doctype html><script>bad()</script>" if inline_script else b"<!doctype html><script src=\"app.js\"></script>")
        entry = root / "dlc" / "frontend" / "editor" / "index.html"
        js = root / "dlc" / "frontend" / "editor" / "app.js"
        entry.write_bytes(html)
        js.write_bytes(script)
        descriptor = {
            "schema": "cartridgeflow.portable_dlc.v2", "id": "dlc.demo", "version": "1.0.0",
            "owner_cartridge": "demo.sandbox", "scope": "cartridge", "tools": [], "protocols": [],
            "frontend": {"sandbox": "isolated_iframe", "components": [{
                "id": "editor", "entry": "dlc/frontend/editor/index.html",
                "host_capabilities": ["draft.write", "interaction.propose"], "script_policy": "external_hashed_only",
            }]},
            "resources": [{"path": "dlc", "ownership": "package"}],
            "files": [
                {"path": "dlc/frontend/editor/index.html", "sha256": _hash(html), "media_type": "text/html", "role": "frontend_entry"},
                {"path": "dlc/frontend/editor/app.js", "sha256": _hash(script), "media_type": "text/javascript", "role": "frontend_script"},
            ],
        }
        (root / "dlc" / "descriptor.json").write_text(json.dumps(descriptor), encoding="utf-8")
        manifest = {
            "id": "demo.sandbox", "version": "1.0.0", "mcp_tools": [],
            "runtime_contract": {"protocol": "CF-FARP", "protocol_version": "0.7"},
            "asset_registry": "assets/registry.json", "interaction_components": "assets/components.json",
            "portable_dlc": {"protocol": "CF-FARP@0.7", "descriptor": "dlc/descriptor.json"},
        }
        return manifest

    def test_descriptor_bundle_and_dedicated_renderer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = self._package(root)
            descriptor = load_portable_dlc_descriptor(root, manifest)
            bundle = load_asset_bundle(root, manifest)
            component = bundle["component_by_id"]["editor.panel"]
            self.assertEqual("cartridgeflow.portable_dlc.v2", descriptor["schema"])
            self.assertEqual("sandboxed", component["runtime"])
            self.assertEqual(_hash((root / "dlc/frontend/editor/index.html").read_bytes()), component["entry_sha256"])

            manager = SandboxRendererManager()
            session = manager.launch(root, manifest, "editor", "run:interaction", "http://127.0.0.1:5173")
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(session["url"], timeout=2) as response:
                    csp = response.headers["Content-Security-Policy"]
                    self.assertIn("connect-src 'none'", csp)
                    self.assertIn("script-src 'self'", csp)
                    self.assertNotIn("unsafe-inline", csp.split("style-src")[0])
                    self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
            finally:
                manager.revoke("run:interaction")

    def test_inline_script_is_rejected_before_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = self._package(root, inline_script=True)
            with self.assertRaisesRegex(PortableDlcValidationError, "inline script"):
                load_portable_dlc_descriptor(root, manifest)


if __name__ == "__main__":
    unittest.main()
