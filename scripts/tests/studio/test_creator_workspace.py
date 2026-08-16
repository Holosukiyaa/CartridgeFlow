import tempfile
import unittest
from pathlib import Path

from core.studio.creator_workspace import CreatorWorkspaceError, CreatorWorkspaceStore


class CreatorWorkspaceStoreTests(unittest.TestCase):
    def test_persists_a_bounded_snapshot_with_optimistic_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CreatorWorkspaceStore(Path(temp_dir))
            snapshot = {
                "version": 1,
                "goal": "Build a useful result",
                "messages": [
                    {"id": f"message-{index}", "role": "user", "text": str(index), "unexpected": "ignored"}
                    for index in range(90)
                ],
                "clarification": None,
                "possibilities": [],
                "selectedId": "draft",
                "middleView": "detail",
                "workspacePane": "outline",
                "packageResult": None,
                "packageRevision": None,
                "api_key": "must-not-persist",
            }
            saved = store.save("project.workspace", snapshot, expected_revision=0)
            self.assertEqual(1, saved["revision"])
            self.assertEqual(80, len(saved["snapshot"]["messages"]))
            self.assertNotIn("unexpected", saved["snapshot"]["messages"][0])
            self.assertNotIn("api_key", saved["snapshot"])
            self.assertEqual(saved, store.get("project.workspace"))

            with self.assertRaises(CreatorWorkspaceError) as conflict:
                store.save("project.workspace", snapshot, expected_revision=0)
            self.assertEqual("CREATOR_WORKSPACE_REVISION_CONFLICT", conflict.exception.code)

            updated = store.save("project.workspace", {**snapshot, "goal": "Updated"}, expected_revision=1)
            self.assertEqual(2, updated["revision"])
            self.assertEqual("Updated", updated["snapshot"]["goal"])

    def test_rejects_invalid_project_identity_and_snapshot_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CreatorWorkspaceStore(Path(temp_dir))
            with self.assertRaises(CreatorWorkspaceError):
                store.get("../outside")
            with self.assertRaises(CreatorWorkspaceError):
                store.save("project.valid", {"version": 2}, expected_revision=0)


if __name__ == "__main__":
    unittest.main()
