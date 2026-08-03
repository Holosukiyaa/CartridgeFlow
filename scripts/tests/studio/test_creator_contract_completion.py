import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore


SHA = "a" * 64
STEPS = [{"id": "research", "intent": "Read declared material.", "inputs": {"brief": {}}, "outputs": {"notes": {}}}]


class CreatorContractCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AuthoringSessionStore(self.temp.name)
        self.store.create("creator.contract", "recipe.contract", "Create a brief", STEPS, [{"id": "source.role", "kind": "source", "digest": SHA, "role": "editorial reference"}], {})

    def tearDown(self):
        self.temp.cleanup()

    def test_reviewed_semantic_changes_are_atomic_and_projected_safely(self):
        proposal = self.store.propose("creator.contract", [
            {"id": "add.source", "target_id": "source.rss", "operation": "add_source", "value": {"id": "source.rss", "kind": "source", "digest": "b" * 64, "rss_url": "https://example.test/feed.xml"}},
            {"id": "binding", "target_id": "research", "operation": "set_creator_binding", "value": {"audience": "readers"}},
        ], author="creator", summary="Add a public feed", expected_revision=1)
        before = self.store.get("creator.contract")
        self.store.preview("creator.contract", proposal["proposal_id"], ["binding"])
        self.assertEqual(before, self.store.get("creator.contract"))
        accepted = self.store.accept("creator.contract", proposal["proposal_id"], ["binding"])
        self.assertEqual(["binding"], accepted["acceptance"]["accepted_change_ids"])
        projection = accepted["creator"]
        self.assertEqual(["brief"], projection["semantic_steps"][0]["plain_inputs"])
        self.assertNotIn("developer", str(projection).lower())
        self.assertNotIn("secret", str(projection).lower())

    def test_unsafe_sources_and_generation_gate_fail_closed(self):
        for url in ("https://user:pass@example.test/feed", "https://example.test/feed?token=secret", "C:\\private\\feed.xml"):
            with self.assertRaises(AuthoringServiceError) as error:
                self.store.propose("creator.contract", [{"id": "bad.source", "target_id": "source.bad", "operation": "add_source", "value": {"id": "source.bad", "kind": "source", "digest": "c" * 64, "remote_url": url}}], author="creator", summary="unsafe", expected_revision=1)
            self.assertEqual("AUTHORING_PROPOSAL_INVALID", error.exception.code)
        state = self.store.get("creator.contract")
        self.assertFalse(self.store.generation_readiness(state)["ready"])
        self.store.freeze("creator.contract", ["research"], author="creator", summary="Reviewed")
        state = self.store.get("creator.contract")
        self.assertTrue(self.store.generation_readiness(state)["ready"])
        self.assertEqual("compile", self.store.compile_candidate(state)["kind"])


if __name__ == "__main__":
    unittest.main()
