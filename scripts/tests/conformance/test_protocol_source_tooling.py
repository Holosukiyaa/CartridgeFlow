from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
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

if __name__ == "__main__":
    unittest.main()
