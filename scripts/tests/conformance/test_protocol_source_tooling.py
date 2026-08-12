from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import launch_protocol_viewer
import update_protocol_registry


class ProtocolSourceToolingTests(unittest.TestCase):
    def test_protocol_source_is_external_and_pinned_by_the_product_lock(self):
        self.assertFalse((ROOT / ".gitmodules").exists())
        self.assertFalse((ROOT / "protocol-source").exists())
        self.assertFalse(hasattr(update_protocol_registry, "DEFAULT_PROTOCOL_REPOSITORY"))
        lock = json.loads(
            (ROOT / "config" / "protocol" / "protocol-registry.lock.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(update_protocol_registry.REPOSITORY_URL, lock["repository"]["url"])
        self.assertEqual(40, len(lock["repository"]["commit"]))
        self.assertEqual("protocol-source.sqlite", lock["source_database"]["path"])
        self.assertEqual(64, len(lock["source_database"]["database_sha256"]))

    def test_registry_base_and_lock_replace_rolls_back_as_one_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "protocol-registry.sqlite"
            base = root / "BASE_IMPLEMENTATION.json"
            lock = root / "protocol-registry.lock.json"
            database.write_bytes(b"old-database")
            base.write_bytes(b"old-base")
            lock.write_bytes(b"old-lock")
            staged_database = root / "staged.sqlite"
            staged_base = root / "staged-base.json"
            staged_lock = root / "staged-lock.json"
            staged_database.write_bytes(b"new-database")
            staged_base.write_bytes(b"new-base")
            staged_lock.write_bytes(b"new-lock")
            real_replace = os.replace
            calls = 0

            def fail_lock_replace(source, target):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("injected lock replacement failure")
                real_replace(source, target)

            with (
                mock.patch.object(update_protocol_registry, "DATABASE_PATH", database),
                mock.patch.object(update_protocol_registry, "BASE_PATH", base),
                mock.patch.object(update_protocol_registry, "LOCK_PATH", lock),
                mock.patch.object(update_protocol_registry.os, "replace", side_effect=fail_lock_replace),
                self.assertRaisesRegex(RuntimeError, "close processes reading the Registry"),
            ):
                update_protocol_registry._replace_registry_bundle(
                    staged_database, staged_lock, staged_base, root
                )

            self.assertEqual(b"old-database", database.read_bytes())
            self.assertEqual(b"old-base", base.read_bytes())
            self.assertEqual(b"old-lock", lock.read_bytes())

    def test_registry_base_and_lock_replace_succeeds_as_one_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "protocol-registry.sqlite"
            base = root / "BASE_IMPLEMENTATION.json"
            lock = root / "protocol-registry.lock.json"
            for path, content in (
                (database, b"old-database"),
                (base, b"old-base"),
                (lock, b"old-lock"),
            ):
                path.write_bytes(content)
            staged_database = root / "staged.sqlite"
            staged_base = root / "staged-base.json"
            staged_lock = root / "staged-lock.json"
            staged_database.write_bytes(b"new-database")
            staged_base.write_bytes(b"new-base")
            staged_lock.write_bytes(b"new-lock")
            with (
                mock.patch.object(update_protocol_registry, "DATABASE_PATH", database),
                mock.patch.object(update_protocol_registry, "BASE_PATH", base),
                mock.patch.object(update_protocol_registry, "LOCK_PATH", lock),
            ):
                update_protocol_registry._replace_registry_bundle(
                    staged_database, staged_lock, staged_base, root
                )
            self.assertEqual(b"new-database", database.read_bytes())
            self.assertEqual(b"new-base", base.read_bytes())
            self.assertEqual(b"new-lock", lock.read_bytes())

    def test_viewer_is_immutable_and_loopback_only(self):
        databases = launch_protocol_viewer.DEFAULT_DATABASES
        command = launch_protocol_viewer.viewer_command(
            Path("datasette"), databases, 8123
        )
        self.assertEqual(1, command.count("-i"))
        for database in databases:
            self.assertIn(str(database), command)
        self.assertEqual(
            str(launch_protocol_viewer.VIEWER_TEMPLATES),
            command[command.index("--template-dir") + 1],
        )
        self.assertEqual(
            str(launch_protocol_viewer.VIEWER_PLUGINS),
            command[command.index("--plugins-dir") + 1],
        )
        self.assertEqual("127.0.0.1", command[command.index("--host") + 1])
        self.assertEqual("8123", command[command.index("--port") + 1])
        self.assertEqual("1", launch_protocol_viewer.viewer_environment()["PYTHONUTF8"])

        metadata_bytes = launch_protocol_viewer.VIEWER_CONFIG.read_bytes()
        self.assertTrue(metadata_bytes.isascii())
        metadata = json.loads(metadata_bytes)
        self.assertEqual("CartridgeFlow 协议知识库", metadata["title"])
        databases_metadata = metadata["databases"]
        self.assertEqual({"protocol-registry"}, set(databases_metadata))
        self.assertEqual(
            {
                "data_contract_catalog",
                "protocol_catalog",
                "read_protocol",
                "search_protocols",
                "configuration_catalog",
                "read_configuration",
                "search_configuration",
                "implementation_support",
                "implementation_evidence",
            },
            set(databases_metadata["protocol-registry"]["queries"]),
        )
        queries = [
            query
            for database in databases_metadata.values()
            for query in database["queries"].values()
        ]
        self.assertTrue(
            all(
                query["sql"].lstrip().casefold().startswith("select ")
                for query in queries
            )
        )
        templates = launch_protocol_viewer.VIEWER_TEMPLATES
        self.assertIn("协议知识库", (templates / "index.html").read_text(encoding="utf-8"))
        base_template = (templates / "base.html").read_text(encoding="utf-8")
        self.assertIn("https://github.com/Holosukiyaa/cartridgeflow-protocols", base_template)
        self.assertIn("产品锁定协议快照", base_template)
        self.assertIn("运行查询", (templates / "query.html").read_text(encoding="utf-8"))
        self.assertIn(
            "数据合同",
            (templates / "protocol_sidebar.html").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "协议文件树",
            (templates / "protocol_sidebar.html").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "knowledge-shell",
            (templates / "protocol_shell_styles.html").read_text(encoding="utf-8"),
        )
        plugin = launch_protocol_viewer.VIEWER_PLUGINS / "protocol_knowledge.py"
        plugin_text = plugin.read_text(encoding="utf-8")
        self.assertIn("register_routes", plugin_text)
        self.assertIn("FOUR_MAJOR_LAYERS", plugin_text)
        self.assertIn("cartridgeflow-authoritative", plugin_text)
        self.assertIn("IN ('active', 'published')", plugin_text)
        self.assertNotIn("CONTRACT_TOKENS", plugin_text)
        self.assertIn("data_contract_release", plugin_text)

    def test_existing_background_viewer_reopens_in_browser(self):
        with (
            mock.patch.object(sys, "argv", ["launch_protocol_viewer.py"]),
            mock.patch.object(launch_protocol_viewer, "viewer_is_running", return_value=True),
            mock.patch.object(launch_protocol_viewer.webbrowser, "open") as browser_open,
            mock.patch.object(launch_protocol_viewer, "prepare_viewer_environment") as prepare,
        ):
            self.assertEqual(0, launch_protocol_viewer.main())

        browser_open.assert_called_once_with("http://127.0.0.1:8001/")
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
