from __future__ import annotations

import configparser
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import launch_protocol_viewer
import update_protocol_registry


class ProtocolSourceToolingTests(unittest.TestCase):
    def test_protocol_source_is_embedded_at_the_governed_submodule_path(self):
        config = configparser.ConfigParser()
        self.assertTrue(config.read(ROOT / ".gitmodules", encoding="utf-8"))
        section = 'submodule "protocol-source"'
        self.assertEqual("protocol-source", config.get(section, "path"))
        self.assertEqual(
            "https://github.com/Holosukiyaa/cartridgeflow-protocols.git",
            config.get(section, "url"),
        )
        self.assertEqual(
            ROOT / "protocol-source",
            update_protocol_registry.DEFAULT_PROTOCOL_REPOSITORY,
        )
        self.assertTrue((ROOT / "protocol-source" / ".git").exists())

    def test_embedded_source_checkout_is_clean_and_published(self):
        commit, remote = update_protocol_registry._validate_source_repository(
            update_protocol_registry.DEFAULT_PROTOCOL_REPOSITORY
        )
        lock = json.loads(
            (ROOT / "config" / "protocol" / "protocol-registry.lock.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lock["repository"]["commit"], commit)
        self.assertEqual(lock["repository"]["url"], remote)

    def test_viewer_is_immutable_and_loopback_only(self):
        databases = (
            ROOT / "protocol-source" / "protocol-source.sqlite",
            ROOT / "config" / "protocol" / "protocol-registry.sqlite",
        )
        command = launch_protocol_viewer.viewer_command(
            Path("datasette"), databases, 8123
        )
        self.assertEqual(2, command.count("-i"))
        for database in databases:
            self.assertIn(str(database), command)
        self.assertEqual(
            str(launch_protocol_viewer.VIEWER_TEMPLATES),
            command[command.index("--template-dir") + 1],
        )
        self.assertEqual("127.0.0.1", command[command.index("--host") + 1])
        self.assertEqual("8123", command[command.index("--port") + 1])

        metadata_bytes = launch_protocol_viewer.VIEWER_CONFIG.read_bytes()
        self.assertTrue(metadata_bytes.isascii())
        metadata = json.loads(metadata_bytes)
        self.assertEqual("CartridgeFlow 协议知识库", metadata["title"])
        databases_metadata = metadata["databases"]
        self.assertEqual(
            {"protocol-source", "protocol-registry"},
            set(databases_metadata),
        )
        self.assertEqual(
            {"protocol_catalog", "read_protocol", "search_protocols"},
            set(databases_metadata["protocol-source"]["queries"]),
        )
        self.assertEqual(
            {
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
        self.assertIn("运行查询", (templates / "query.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
