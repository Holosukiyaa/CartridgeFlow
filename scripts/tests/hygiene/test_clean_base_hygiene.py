import json
import tempfile
import unittest
from pathlib import Path

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
    ensure_data_layout,
)
from core.lab.dev_flow import DevFlowManager
from core.studio.hygiene import release_tree_manifests, scan_package_hygiene, scan_source_ownership


ROOT = Path(__file__).resolve().parents[3]


class CleanBaseHygieneTests(unittest.TestCase):
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
            "/src/frontend/dist/",
            "/temp/",
            "Thumbs.db",
        ):
            self.assertIn(pattern, gitignore)

    def test_documentation_has_canonical_entry_points(self):
        expected = (
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "overview" / "PROJECT_STRUCTURE.md",
            ROOT / "docs" / "development" / "FILE_INVENTORY.md",
            ROOT / "docs" / "architecture" / "PORTABLE_DLC_ARCHITECTURE.md",
            ROOT / "docs" / "planning" / "ROADMAP.md",
            ROOT / "docs" / "planning" / "TODO.md",
            ROOT / "docs" / "planning" / "TODO_TEMPLATE.md",
            ROOT / "docs" / "protocol" / "GOVERNANCE.md",
            ROOT / "protocol" / "README.md",
        )

        self.assertTrue(all(path.is_file() for path in expected))
        self.assertFalse((ROOT / "GOAL.md").exists())
        self.assertFalse((ROOT / "TODO.md").exists())
        self.assertFalse((ROOT / "TODO_TEMPLATE.md").exists())
        self.assertFalse((ROOT / "CHANGELOG.md").exists())
        self.assertFalse((ROOT / ".env.example").exists())
        self.assertFalse((ROOT / "BASE_IMPLEMENTATION.json").exists())
        self.assertTrue((ROOT / "config" / "base" / "BASE_IMPLEMENTATION.json").is_file())
        self.assertFalse((ROOT / "cartridges").exists())

    def test_maintenance_assets_and_generated_output_have_single_owners(self):
        expected_maintenance_assets = (
            ROOT / "docs" / "development" / "README.md",
            ROOT / "docs" / "development" / "AI_DEVELOPER_GUIDE.md",
            ROOT / "scripts" / "bootstrap.ps1",
            ROOT / "scripts" / "launch.py",
            ROOT / "scripts" / "run_conformance.py",
            ROOT / "docs" / "development" / "skills" / "cartridgeflow-protocol-upgrader" / "SKILL.md",
        )
        self.assertTrue(all(path.is_file() for path in expected_maintenance_assets))
        for legacy_dir in ("development", "devtools", "skills", "web_static", "logs", "tests", "tooling"):
            self.assertFalse((ROOT / legacy_dir).exists(), legacy_dir)

        vite_config = (ROOT / "src" / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
        server_main = (ROOT / "src" / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("outDir: 'dist'", vite_config)
        self.assertIn('ROOT / "src" / "frontend" / "dist"', server_main)
        self.assertIn("ROOT / LOGS_DIR", server_main)
        self.assertNotIn('ROOT / "logs"', server_main)
        self.assertIn("/src/frontend/dist/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_scripts_tree_contains_only_executable_maintenance_code(self):
        scripts_root = ROOT / "scripts"
        unexpected = [
            path.relative_to(ROOT).as_posix()
            for path in scripts_root.rglob("*")
            if path.is_file() and path.suffix.lower() not in {".py", ".ps1"}
        ]
        self.assertEqual([], unexpected)
        self.assertEqual([], [path for path in scripts_root.rglob("__pycache__") if path.is_dir()])
        self.assertFalse((scripts_root / "skills").exists())
        self.assertTrue((ROOT / "docs" / "development" / "skills").is_dir())

    def test_project_local_runtimes_are_grouped_under_tools_runtimes(self):
        launcher = (ROOT / "run.bat").read_text(encoding="utf-8")
        bootstrap = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")

        self.assertIn(r".tools\runtimes\python", launcher)
        self.assertIn(r".tools\runtimes\node", launcher)
        self.assertIn('$RuntimesDir = Join-Path $ToolsDir "runtimes"', bootstrap)
        self.assertIn('$LegacyPythonDir = Join-Path $ToolsDir "python"', bootstrap)
        self.assertIn('$LegacyNodeDir = Join-Path $ToolsDir "node"', bootstrap)
        environment = (ROOT / "src" / "core" / "studio" / "environment.py").read_text(encoding="utf-8")
        self.assertIn('ROOT / ".tools" / "runtimes" / "node"', environment)

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
            (root / "src" / "frontend" / "src").mkdir(parents=True)
            (root / "src" / "core" / "leak.py").write_text("TOOL = 'render_acme_video'\n", encoding="utf-8")
            (root / "src" / "frontend" / "src" / "branch.tsx").write_text(
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
        for relative in ("src/core", "src/backend", "src/frontend/src"):
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
