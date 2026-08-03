import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore, compile_instance
from core.llm.authoring import AuthoringProposalError, build_authoring_messages, parse_authoring_proposal


SOURCE = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
STEPS = [
    {"id": "research", "intent": "Collect declared source material.", "inputs": {}, "outputs": {}},
    {"id": "draft", "intent": "Prepare a plain-language draft.", "inputs": {}, "outputs": {}},
]


class AuthoringServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AuthoringSessionStore(self.temp.name)
        self.store.create("session.demo", "recipe.demo", "Create a source-grounded brief.", STEPS, [SOURCE], {})

    def tearDown(self):
        self.temp.cleanup()

    def proposal(self, changes, revision=1):
        return self.store.propose("session.demo", changes, author="creator", summary="Refine the draft.", expected_revision=revision)

    def test_preview_and_conflict_do_not_modify_head(self):
        proposal = self.proposal([{"id": "c.intent", "target_id": "draft", "operation": "set_step_intent", "value": "Prepare a reviewed draft."}])
        preview = self.store.preview("session.demo", proposal["proposal_id"])
        self.assertTrue(preview["would_change"])
        self.assertEqual(1, self.store.get("session.demo")["head"]["revision"])
        self.store.accept("session.demo", proposal["proposal_id"])
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.propose("session.demo", [], author="creator", summary="late", expected_revision=1)
        self.assertEqual("AUTHORING_REVISION_CONFLICT", error.exception.code)

    def test_partial_accept_and_reversal_history(self):
        proposal = self.proposal([
            {"id": "c.research", "target_id": "research", "operation": "set_step_intent", "value": "Collect cited material."},
            {"id": "c.draft", "target_id": "draft", "operation": "set_step_intent", "value": "Prepare a reviewed draft."},
        ])
        accepted = self.store.accept("session.demo", proposal["proposal_id"], ["c.draft"])
        self.assertEqual(["c.draft"], accepted["acceptance"]["accepted_change_ids"])
        self.assertEqual("Collect declared source material.", self.store.get("session.demo")["head"]["blueprint"]["steps"][0]["intent"])
        reversed_result = self.store.reverse("session.demo", accepted["acceptance"]["id"], author="creator", summary="Undo draft revision.", expected_revision=2)
        self.assertEqual(accepted["acceptance"]["id"], reversed_result["acceptance"]["reversal_of"])
        self.assertEqual("Prepare a plain-language draft.", self.store.get("session.demo")["head"]["blueprint"]["steps"][1]["intent"])

    def test_freeze_and_source_safety_are_fail_closed(self):
        self.store.freeze("session.demo", ["draft"], author="creator", summary="Freeze reviewed wording.")
        proposal = self.proposal([{"id": "c.draft", "target_id": "draft", "operation": "set_step_intent", "value": "Silently change frozen draft."}])
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.accept("session.demo", proposal["proposal_id"])
        self.assertEqual("AUTHORING_FROZEN_STEP", error.exception.code)
        with self.assertRaises(AuthoringServiceError) as unsafe:
            self.store.create("session.unsafe", "recipe.unsafe", "x", STEPS, [SOURCE], {"draft": {"api_key": "nope"}})
        self.assertEqual("AUTHORING_FACT_INVALID", unsafe.exception.code)

    def test_compilation_is_deterministic(self):
        head = self.store.get("session.demo")["head"]
        first, second = compile_instance(head), compile_instance(head)
        self.assertEqual(first, second)
        self.assertNotIn("credentials", str(first).lower())

    def test_ai_adapter_allows_only_declared_semantic_capabilities(self):
        head = self.store.get("session.demo")["head"]
        messages = build_authoring_messages(head, ["set_step_intent"], "Make the draft clearer.")
        self.assertNotIn("chat_history", messages[1]["content"])
        changes = parse_authoring_proposal('{"changes":[{"id":"ai.draft","target_id":"draft","operation":"set_step_intent","value":"Write a clearer draft."}]}', head, ["set_step_intent"])
        self.assertEqual("set_step_intent", changes[0]["operation"])
        with self.assertRaises(AuthoringProposalError):
            parse_authoring_proposal('{"changes":[{"id":"ai.bad","target_id":"draft","operation":"set_binding","value":{}}]}', head, ["set_step_intent"])


if __name__ == "__main__":
    unittest.main()
