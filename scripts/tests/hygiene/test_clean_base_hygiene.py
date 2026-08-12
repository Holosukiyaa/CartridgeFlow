import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cartridge.registry import CartridgeRegistry
from core.data_paths import (
    CONFORMANCE_DIR,
    DataLayoutMigrationError,
    DEV_CARTRIDGES_DIR,
    ERROR_REPORTS_DIR,
    LLM_ASSIGNMENTS_FILE,
    LLM_PROVIDERS_FILE,
    LOGS_DIR,
    RUNS_DIR,
    STUDIO_CREDENTIALS_FILE,
    STUDIO_RESOURCES_FILE,
    WORKERS_DIR,
    configured_data_root,
    ensure_data_layout,
)
from core.lab.dev_flow import DevFlowManager
from core.studio.hygiene import release_tree_manifests, scan_package_hygiene, scan_source_ownership


ROOT = Path(__file__).resolve().parents[3]


class CleanBaseHygieneTests(unittest.TestCase):
    def test_data_root_can_be_relocated_as_one_unified_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"CARTRIDGEFLOW_DATA_ROOT": temp_dir}, clear=False,
        ):
            self.assertEqual(Path(temp_dir), configured_data_root())

        with patch.dict(os.environ, {"CARTRIDGEFLOW_DATA_ROOT": ""}, clear=False):
            self.assertEqual(Path(".data"), configured_data_root())

    def test_config_templates_are_safe_and_local_state_is_ignored(self):
        template_paths = [
            ROOT / "config" / "templates" / "llm" / "providers.json",
            ROOT / "config" / "templates" / "llm" / "assignments.json",
            ROOT / "config" / "templates" / "studio" / "credentials.json",
            ROOT / "config" / "templates" / "studio" / "resources.json",
        ]
        for path in template_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict)
        provider_template = json.loads(template_paths[0].read_text(encoding="utf-8"))
        self.assertTrue(all(not item.get("api_key") for item in provider_template["providers"]))

        for legacy_local_path in (
            ROOT / "config" / "llm" / "providers.json",
            ROOT / "config" / "llm" / "assignments.json",
            ROOT / "config" / "studio" / "credentials.json",
            ROOT / "config" / "studio" / "resources.json",
        ):
            self.assertFalse(legacy_local_path.exists(), legacy_local_path)

        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            ".env.*",
            "/.data/",
            "/.tools/",
            "/.venv/",
            "/config/llm/providers.json*",
            "/config/llm/assignments.json*",
            "/config/studio/credentials.json*",
            "/config/studio/resources.json*",
            "/src/intent-studio/dist/",
            "/src/capability-workshop/dist/",
            "/temp/",
            "Thumbs.db",
        ):
            self.assertIn(pattern, gitignore)

    def test_documentation_has_canonical_entry_points(self):
        expected = (
            ROOT / "README.md",
            ROOT / "config" / "protocol" / "README.md",
            ROOT / "config" / "protocol" / "protocol-registry.lock.json",
            ROOT / "config" / "protocol" / "protocol-registry.sqlite",
        )

        self.assertTrue(all(path.is_file() for path in expected))
        self.assertFalse((ROOT / "protocol").exists())
        self.assertFalse((ROOT / "GOAL.md").exists())
        self.assertNotIn("TODO.md", {path.name for path in ROOT.iterdir()})
        self.assertFalse((ROOT / "TODO_TEMPLATE.md").exists())
        self.assertFalse((ROOT / "CHANGELOG.md").exists())
        self.assertFalse((ROOT / ".env.example").exists())
        self.assertFalse((ROOT / "BASE_IMPLEMENTATION.json").exists())
        self.assertTrue((ROOT / "config" / "base" / "BASE_IMPLEMENTATION.json").is_file())
        self.assertFalse((ROOT / "cartridges").exists())
        for governance_only in (
            "AGENT.md",
            "AGENTS.md",
            "MENTOR_WORKERS.md",
            "PLAN.md",
            "PRODUCT_EXPERIENCE_ARCHITECTURE.md",
            "todo.md",
        ):
            self.assertFalse((ROOT / governance_only).exists(), governance_only)
        self.assertFalse((ROOT / "demos").exists())
        self.assertFalse(any(path.is_file() for path in (ROOT / "docs" / "development").rglob("*")))
        self.assertFalse(any(path.is_file() for path in (ROOT / "docs" / "protocol-rebuild").rglob("*")))

    def test_maintenance_assets_and_generated_output_have_single_owners(self):
        expected_maintenance_assets = (
            ROOT / "scripts" / "bootstrap.ps1",
            ROOT / "scripts" / "launch.py",
            ROOT / "scripts" / "run_conformance.py",
        )
        self.assertTrue(all(path.is_file() for path in expected_maintenance_assets))
        for legacy_dir in ("development", "devtools", "skills", "web_static", "logs", "tests", "tooling"):
            self.assertFalse((ROOT / legacy_dir).exists(), legacy_dir)

        vite_config = (ROOT / "src" / "intent-studio" / "vite.config.ts").read_text(encoding="utf-8")
        server_main = (ROOT / "src" / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("outDir: 'dist'", vite_config)
        self.assertIn('ROOT / "src" / "intent-studio" / "dist"', server_main)
        self.assertIn("ROOT / LOGS_DIR", server_main)
        self.assertNotIn('ROOT / "logs"', server_main)
        self.assertIn("/src/intent-studio/dist/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_scripts_tree_contains_only_executable_maintenance_code(self):
        scripts_root = ROOT / "scripts"
        unexpected = [
            path.relative_to(ROOT).as_posix()
            for path in scripts_root.rglob("*")
            if path.is_file() and path.suffix.lower() not in {".py", ".ps1", ".mjs"}
            and "__pycache__" not in path.parts
        ]
        self.assertEqual([], unexpected)
        self.assertFalse((scripts_root / "skills").exists())
        self.assertFalse(any(path.is_file() for path in (ROOT / "docs" / "development").rglob("*")))

    def test_lite_uses_host_runtimes(self):
        launcher = (ROOT / "run.bat").read_text(encoding="utf-8")
        bootstrap = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")

        self.assertIn("where python", launcher)
        self.assertIn("where node", launcher)
        self.assertIn('Resolve-RequiredCommand "python"', bootstrap)
        self.assertIn('Resolve-RequiredCommand "node"', bootstrap)
        self.assertNotIn(".tools", launcher)
        self.assertNotIn(".tools", bootstrap)
        environment = (ROOT / "src" / "core" / "studio" / "environment.py").read_text(encoding="utf-8")
        self.assertIn('shutil.which("node")', environment)
        self.assertNotIn('ROOT / ".tools" / "runtimes"', environment)

    def test_legacy_release_shelves_are_not_runtime_cartridges(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "cartridges" / "dev").mkdir(parents=True)
            (root / "cartridges" / "builtin").mkdir(parents=True)

            self.assertEqual([], CartridgeRegistry(root).list_cartridges())

    def test_dev_flows_are_local_data_not_release_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = DevFlowManager(root)
            created = manager.create_flow("local-only", "Local only")

            self.assertEqual(root / DEV_CARTRIDGES_DIR, manager.dev_dir)
            self.assertTrue(Path(created["path"]).is_dir())
            self.assertEqual([], release_tree_manifests(root))

    def test_release_tree_has_no_business_cartridges(self):
        self.assertEqual([], release_tree_manifests(ROOT))

    def test_legacy_data_layout_migrates_without_losing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixtures = {
                root / ".data" / "dev_cartridges" / "dev.example" / "manifest.json": "{}",
                root / ".data" / "cartridge_runs" / "run_example" / "run.json": "{}",
                root / ".data" / "conformance" / "latest.json": "{}",
                root / ".data" / "diagnostics" / "logs" / "legacy.log": "old log",
                root / "config" / "llm" / "providers.json": '{"providers":[{"api_key":"preserved"}]}',
                root / "config" / "llm" / "assignments.json": '{"defaults":{"runtime":{"provider_id":"local"}}}',
                root / "config" / "studio" / "credentials.json": '{"items":[{"value":"preserved"}]}',
                root / "config" / "studio" / "resources.json": '{"tools":[{"id":"local"}]}',
            }
            for path, content in fixtures.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            migrations = ensure_data_layout(root)

            self.assertEqual(8, len(migrations))
            self.assertTrue((root / DEV_CARTRIDGES_DIR / "dev.example" / "manifest.json").is_file())
            self.assertTrue((root / RUNS_DIR / "run_example" / "run.json").is_file())
            self.assertTrue((root / CONFORMANCE_DIR / "latest.json").is_file())
            self.assertTrue((root / LOGS_DIR / "legacy.log").is_file())
            self.assertIn("preserved", (root / LLM_PROVIDERS_FILE).read_text(encoding="utf-8"))
            self.assertTrue((root / LLM_ASSIGNMENTS_FILE).is_file())
            self.assertIn("preserved", (root / STUDIO_CREDENTIALS_FILE).read_text(encoding="utf-8"))
            self.assertTrue((root / STUDIO_RESOURCES_FILE).is_file())
            self.assertTrue((root / ERROR_REPORTS_DIR).is_dir())
            self.assertTrue((root / WORKERS_DIR).is_dir())
            self.assertTrue((root / LOGS_DIR).is_dir())
            self.assertFalse((root / ".data" / "dev_cartridges").exists())
            self.assertFalse((root / ".data" / "cartridge_runs").exists())
            self.assertFalse((root / ".data" / "conformance").exists())
            self.assertFalse((root / ".data" / "diagnostics").exists())
            self.assertFalse((root / "config" / "llm" / "providers.json").exists())
            self.assertFalse((root / "config" / "studio" / "credentials.json").exists())

    def test_local_config_migration_refuses_conflicting_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "config" / "llm" / "providers.json"
            current = root / LLM_PROVIDERS_FILE
            legacy.parent.mkdir(parents=True)
            current.parent.mkdir(parents=True)
            legacy.write_text('{"version":"legacy"}', encoding="utf-8")
            current.write_text('{"version":"current"}', encoding="utf-8")

            with self.assertRaises(DataLayoutMigrationError):
                ensure_data_layout(root)

            self.assertTrue(legacy.is_file())
            self.assertTrue(current.is_file())

    def test_source_ownership_scan_catches_package_id_tool_and_ui_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / DEV_CARTRIDGES_DIR / "dev.acme_video"
            package.mkdir(parents=True)
            (package / "manifest.json").write_text(json.dumps({
                "id": "dev.acme_video",
                "mcp_tools": [{"id": "render_acme_video", "server": "acme_video", "tool": "render_clip"}],
            }), encoding="utf-8")
            (root / "src" / "core").mkdir(parents=True)
            (root / "src" / "backend").mkdir(parents=True)
            (root / "src" / "intent-studio" / "src").mkdir(parents=True)
            (root / "src" / "core" / "leak.py").write_text("TOOL = 'render_acme_video'\n", encoding="utf-8")
            (root / "src" / "intent-studio" / "src" / "branch.tsx").write_text(
                "if (cartridgeId === 'dev.acme_video') return <AcmeVideo />\n",
                encoding="utf-8",
            )

            findings = scan_source_ownership(root)
            markers = {item["marker"] for item in findings}
            self.assertIn("render_acme_video", markers)
            self.assertIn("dev.acme_video", markers)

    def test_base_source_contains_no_cartridge_owned_branches(self):
        self.assertEqual([], scan_source_ownership(ROOT))

    def test_base_runtime_contains_no_vendor_specific_adapter(self):
        vendor_markers = ("comfyui", "comfy_ui", "krea", "runway", "pika", "godot")
        findings = []
        for relative in ("src/core", "src/backend", "src/intent-studio/src", "src/capability-workshop/src"):
            source_root = ROOT / relative
            for path in source_root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html"}:
                    continue
                content = path.read_text(encoding="utf-8", errors="replace").lower()
                for marker in vendor_markers:
                    if marker in content:
                        findings.append(f"{path.relative_to(ROOT).as_posix()}: {marker}")
        self.assertEqual([], findings)

    def test_package_hygiene_rejects_local_and_sensitive_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "manifest.json").write_text("{}", encoding="utf-8")
            (package / ".data").mkdir()
            (package / ".data" / "run.json").write_text("{}", encoding="utf-8")
            (package / "credentials.json").write_text("{}", encoding="utf-8")
            (package / "weights.gguf").write_bytes(b"model")
            (package / "debug.log").write_text("trace", encoding="utf-8")

            report = scan_package_hygiene(package)
            self.assertEqual("blocked", report["status"])
            self.assertEqual({"local_data", "secret", "model", "logs"}, {item["category"] for item in report["items"]})

    def test_package_hygiene_accepts_portable_source_and_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "assets").mkdir()
            (package / "manifest.json").write_text("{}", encoding="utf-8")
            (package / "root.flow.json").write_text("{}", encoding="utf-8")
            (package / "assets" / "cover.png").write_bytes(b"png")

            report = scan_package_hygiene(package)
            self.assertEqual("ok", report["status"])
            self.assertEqual([], report["items"])


if __name__ == "__main__":
    unittest.main()
