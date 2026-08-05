import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.extensions import load_portable_dlc_descriptor
from core.protocol.capability_cartridges import build_flow_capability_release, create_semantic_recipe
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore
from core.studio.creator_runtime_bridge import CreatorRuntimeBridge


DEMO = ROOT / "demos" / "capabilities" / "rss-reader"


def rss_release() -> dict:
    manifest = json.loads((DEMO / "manifest.json").read_text(encoding="utf-8"))
    root_flow = json.loads((DEMO / "root.flow.json").read_text(encoding="utf-8"))
    source_files = {
        path.relative_to(DEMO).as_posix(): path.read_text(encoding="utf-8")
        for path in DEMO.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "root.flow.json", "README.md"}
    }
    return build_flow_capability_release(
        capability_id="workspace.rss-reader",
        revision=1,
        trust_scope="workspace",
        label="获取 RSS 信息",
        description="读取用户审核的 RSS 或 Atom 地址并输出标准信息条目。",
        match_terms=["RSS", "信息源", "AI 日报", "最新内容"],
        editable_fields=[
            {
                "id": "feed_urls",
                "label": "RSS 地址",
                "value_type": "string_list",
                "required": True,
                "default": ["https://example.com/feed.xml"],
            },
            {
                "id": "max_items",
                "label": "最多条数",
                "value_type": "number",
                "required": True,
                "default": 20,
            },
        ],
        creator_bindings={
            "feed_urls": "states.fetch.params.tools.0.params.urls",
            "max_items": "states.fetch.params.tools.0.params.max_items",
        },
        public_inputs=[],
        public_outputs=[
            {
                "id": "items",
                "label": "标准信息条目",
                "required": True,
                "schema": {"type": "array"},
                "store_key": "items",
            }
        ],
        dependencies=[],
        source_flow_id=manifest["id"],
        manifest=manifest,
        root_flow=root_flow,
        source_files=source_files,
        evidence={
            "status": "passed",
            "checks": [
                {"id": "flow_contract", "status": "passed"},
                {"id": "portable_dlc", "status": "passed"},
            ],
        },
    )


class RssCapabilityCartridgeIntegrationTests(unittest.TestCase):
    def test_rss_flow_resolves_and_materializes_as_package_owned_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = CapabilityCartridgeStore(temp / "registry")
            release = registry.put(rss_release(), expected_revision=0)
            recipe, publications = create_semantic_recipe(
                "recipe.rss-daily",
                "制作 AI 日报",
                {
                    "nodes": [
                        {
                            "id": "sources",
                            "label": "收集日报信息",
                            "description": "从审核过的 RSS 来源收集最新 AI 内容。",
                            "needed_capability": "RSS 信息源获取",
                            "capability_id": release["id"],
                            "values": {
                                "feed_urls": ["https://example.com/ai.xml"],
                                "max_items": 7,
                            },
                        }
                    ],
                    "relations": [],
                },
                registry.list_active(),
            )
            sessions = AuthoringSessionStore(temp / "sessions")
            sessions.create_from_semantic_recipe("creator.rss-daily", "project.rss-daily", recipe, publications)
            sessions.freeze("creator.rss-daily", ["sources"], author="creator", summary="Reviewed RSS source")

            result = CreatorRuntimeBridge(ROOT, temp / "packages", registry).package(
                sessions,
                "creator.rss-daily",
                expected_revision=1,
            )
            archive = temp / "packages" / result["filename"]
            extracted = temp / "extracted"
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extracted)

            manifest_path = next(extracted.rglob("manifest.json"))
            package_root = manifest_path.parent
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            root_flow = json.loads((package_root / "root.flow.json").read_text(encoding="utf-8"))
            fetch = root_flow["states"]["cap.sources.fetch"]
            tool_params = fetch["params"]["tools"][0]["params"]
            self.assertEqual(["https://example.com/ai.xml"], tool_params["urls"])
            self.assertEqual(7, tool_params["max_items"])
            self.assertEqual(release["digest"], fetch["capability_release"]["digest"])

            descriptor = load_portable_dlc_descriptor(package_root, manifest)
            implementation_entry = descriptor["tools"][0]["implementation"]["entry"]
            self.assertEqual(
                "dlc/mcp_nodes/workspace.rss-reader.1/rss_reader.py",
                implementation_entry,
            )
            self.assertTrue((package_root / implementation_entry).is_file())
            self.assertEqual(
                release["digest"],
                manifest["creator_lineage"]["capability_dependency_closure"][0]["digest"],
            )


if __name__ == "__main__":
    unittest.main()
