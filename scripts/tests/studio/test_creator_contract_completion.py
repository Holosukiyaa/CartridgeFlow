import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.protocol.authoring_contract import LEGACY_AUTHORING_PROTOCOL, create_recipe_blueprint, create_recipe_instance, validate_recipe_instance


SHA = "a" * 64
STEPS = [
    {"id": "research", "intent": "Read declared material.", "inputs": {"brief": {}}, "outputs": {"notes": {}}},
    {"id": "draft", "intent": "Draft from notes.", "inputs": {"notes": {}}, "outputs": {"draft": {}}},
]


class CreatorContractCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AuthoringSessionStore(self.temp.name)
        self.store.create("creator.contract", "recipe.contract", "Create a brief", STEPS, [{"id": "source.role", "kind": "source", "digest": SHA, "role": "editorial reference"}], {"draft": {"tone": "plain"}})

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
        self.store.freeze("creator.contract", ["research", "draft"], author="creator", summary="Reviewed")
        state = self.store.get("creator.contract")
        self.assertTrue(self.store.generation_readiness(state)["ready"])
        self.assertEqual("compile", self.store.compile_candidate(state)["kind"])

    def test_new_artifacts_are_v12_and_legacy_artifacts_remain_valid(self):
        state = self.store.get("creator.contract")
        proposal = self.store.propose("creator.contract", [{"id": "change", "target_id": "research", "operation": "set_creator_binding", "value": {"audience": "readers"}}], author="creator", summary="Bind", expected_revision=1)
        accepted = self.store.accept("creator.contract", proposal["proposal_id"])
        freeze = self.store.freeze("creator.contract", ["research", "draft"], author="creator", summary="Freeze")
        candidate = self.store.compile_candidate(self.store.get("creator.contract"))
        for artifact in (state["head"], self.store.get("creator.contract")["head"], proposal, accepted["acceptance"], freeze, candidate):
            self.assertEqual({"id": "CF-TUNING", "version": "1.2"}, artifact.get("protocol", {"id": "CF-TUNING", "version": "1.2"}))
        legacy = create_recipe_blueprint("legacy.recipe", "Legacy", [STEPS[0]], [{"id": "source.legacy", "kind": "source", "digest": SHA}], protocol=LEGACY_AUTHORING_PROTOCOL)
        self.assertEqual(LEGACY_AUTHORING_PROTOCOL, validate_recipe_instance(create_recipe_instance(legacy, {}))["protocol"])
        legacy_without_relations = dict(legacy); legacy_without_relations.pop("relations")
        body = {key: value for key, value in legacy_without_relations.items() if key not in {"id", "digest"}}
        from core.protocol.tuning import canonical_digest
        legacy_without_relations["digest"] = canonical_digest(body); legacy_without_relations["id"] = f"blueprint-{legacy_without_relations['digest'][:16]}"
        self.assertEqual(LEGACY_AUTHORING_PROTOCOL, validate_recipe_instance(create_recipe_instance(legacy_without_relations, {}))["protocol"])

    def test_each_new_operation_accepts_and_reverses(self):
        operations = [
            ("set_creator_binding", "research", {"tone": "clear"}),
            ("add_source", "source.added", {"id": "source.added", "kind": "source", "digest": "b" * 64, "role": "secondary"}),
            ("update_source", "source.role", {"id": "source.role", "kind": "source", "digest": "c" * 64, "role": "changed"}),
            ("remove_source", "source.role", {}),
            ("add_step", "review", {"id": "review", "intent": "Review draft.", "inputs": {}, "outputs": {}}),
            ("update_step", "draft", {"id": "draft", "intent": "Revise draft.", "inputs": {"notes": {}}, "outputs": {"draft": {}}}),
            ("remove_step", "draft", {}),
            ("connect_steps", "rel.research.draft", {"id": "rel.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"}),
        ]
        for index, (operation, target, value) in enumerate(operations):
            with self.subTest(operation=operation):
                temp = tempfile.TemporaryDirectory(); store = AuthoringSessionStore(temp.name)
                store.create(f"reverse.{index}", "recipe.reverse", "Create", STEPS, [{"id": "source.role", "kind": "source", "digest": SHA, "role": "reference"}], {"draft": {"tone": "plain"}})
                proposal = store.propose(f"reverse.{index}", [{"id": "change", "target_id": target, "operation": operation, "value": value}], author="creator", summary="Change", expected_revision=1)
                accepted = store.accept(f"reverse.{index}", proposal["proposal_id"])["acceptance"]
                reversed_result = store.reverse(f"reverse.{index}", accepted["id"], author="creator", summary="Undo", expected_revision=2)
                self.assertEqual(3, reversed_result["acceptance"]["instance"]["revision"])
                self.assertEqual(accepted["id"], reversed_result["reversal"]["reversal_of"])
                temp.cleanup()

    def test_remove_step_reversal_restores_binding_and_relations_and_partial_selection(self):
        initial = self.store.get("creator.contract")
        proposal = self.store.propose("creator.contract", [
            {"id": "connect", "target_id": "rel.research.draft", "operation": "connect_steps", "value": {"id": "rel.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"}},
            {"id": "remove", "target_id": "draft", "operation": "remove_step", "value": {}},
        ], author="creator", summary="Remove", expected_revision=1)
        accepted = self.store.accept("creator.contract", proposal["proposal_id"], ["connect", "remove"])["acceptance"]
        reversed_result = self.store.reverse("creator.contract", accepted["id"], author="creator", summary="Restore", expected_revision=2)
        head = self.store.get("creator.contract")["head"]
        self.assertEqual(initial["head"]["bindings"]["draft"], head["bindings"]["draft"])
        self.assertEqual(initial["head"]["blueprint"]["steps"], head["blueprint"]["steps"])
        self.assertEqual(initial["head"]["blueprint"].get("relations", []), head["blueprint"].get("relations", []))
        self.assertEqual(3, reversed_result["reversal"]["revision"])

    def test_frozen_new_step_change_requires_freeze_revision(self):
        freeze = self.store.freeze("creator.contract", ["draft"], author="creator", summary="Freeze")
        proposal = self.store.propose("creator.contract", [{"id": "change", "target_id": "draft", "operation": "update_step", "value": {"id": "draft", "intent": "Changed", "inputs": {"notes": {}}, "outputs": {"draft": {}}}}], author="creator", summary="Change", expected_revision=1)
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.accept("creator.contract", proposal["proposal_id"])
        self.assertEqual("AUTHORING_FROZEN_STEP", error.exception.code)
        result = self.store.accept("creator.contract", proposal["proposal_id"], freeze_revision={"source_freeze_ids": [freeze["id"]], "reason": "Correct", "author": "creator", "expected_revision": 1})
        self.assertEqual(2, result["acceptance"]["instance"]["revision"])

    def test_disconnect_relation_reverses_and_http_reverse_never_500(self):
        connect = self.store.propose("creator.contract", [{"id": "connect", "target_id": "rel.research.draft", "operation": "connect_steps", "value": {"id": "rel.research.draft", "from_step_id": "research", "to_step_id": "draft", "relation": "informs"}}], author="creator", summary="Connect", expected_revision=1)
        self.store.accept("creator.contract", connect["proposal_id"])
        disconnect = self.store.propose("creator.contract", [{"id": "disconnect", "target_id": "rel.research.draft", "operation": "disconnect_steps", "value": {}}], author="creator", summary="Disconnect", expected_revision=2)
        acceptance = self.store.accept("creator.contract", disconnect["proposal_id"])["acceptance"]
        self.store.reverse("creator.contract", acceptance["id"], author="creator", summary="Restore", expected_revision=3)
        self.assertEqual("rel.research.draft", self.store.get("creator.contract")["head"]["blueprint"]["relations"][0]["id"])


if __name__ == "__main__":
    unittest.main()
