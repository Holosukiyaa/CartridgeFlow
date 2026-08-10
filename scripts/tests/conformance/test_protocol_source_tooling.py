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
        database = ROOT / "protocol-source" / "protocol-source.sqlite"
        command = launch_protocol_viewer.viewer_command(
            Path("datasette"), database, 8123
        )
        self.assertIn("-i", command)
        self.assertEqual("127.0.0.1", command[command.index("--host") + 1])
        self.assertEqual("8123", command[command.index("--port") + 1])

        metadata = json.loads(launch_protocol_viewer.VIEWER_CONFIG.read_text(encoding="utf-8"))
        queries = metadata["databases"]["protocol-source"]["queries"]
        self.assertEqual(
            {"protocol_catalog", "read_protocol", "search_protocols"},
            set(queries),
        )
        self.assertTrue(
            all(
                query["sql"].lstrip().casefold().startswith("select ")
                for query in queries.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
