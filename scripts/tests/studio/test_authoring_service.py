import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore, compile_instance
from core.protocol.authoring_contract import validate_acceptance
from core.llm.authoring import AuthoringProposalError, build_authoring_messages, parse_authoring_proposal


SOURCE = {"id": "source.brief", "kind": "source", "digest": "a" * 64}
STEPS = [
    {"id": "research", "intent": "Collect declared source material.", "inputs": {}, "outputs": {}},
    {"id": "draft", "intent": "Prepare a plain-language draft.", "inputs": {}, "outputs": {}},
]


class AuthoringServiceTests(unittest.TestCase):

    def test_creates_a_session_from_a_mapped_template(self):
        template = {"schema": "cartridgeflow.developer_recipe_template.v1", "protocol": {"id": "CF-TUNING", "version": "1.3"}, "id": "daily-brief", "revision": 1, "steps": [{"id": "sources", "creator_label": "确认信息来源", "editable_fields": ["topics"], "developer_mapping_key": "daily.sources.v1", "required": True}]}
        projection = self.store.create_from_template("template.session", "template.project", template, {"sources": {"topics": ["AI"]}}, [{"id": "source.role", "kind": "source", "digest": "a" * 64, "role": "reference"}])
        self.assertEqual("确认信息来源", projection["semantic_steps"][0]["intent"])
        self.assertEqual("daily.sources.v1", self.store.get("template.session")["developer_mappings"]["sources"])

    def test_template_session_rejects_free_topology_changes(self):
        template = {"schema": "cartridgeflow.developer_recipe_template.v1", "protocol": {"id": "CF-TUNING", "version": "1.3"}, "id": "daily-brief", "revision": 1, "steps": [{"id": "sources", "creator_label": "确认信息来源", "editable_fields": [], "developer_mapping_key": "daily.sources.v1", "required": True}]}
        self.store.create_from_template("locked.session", "locked.project", template, {}, [{"id": "source.role", "kind": "source", "digest": "a" * 64, "role": "reference"}])
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.propose("locked.session", [{"id": "add", "target_id": "new", "operation": "add_step", "value": {"id": "new", "intent": "new", "inputs": {}, "outputs": {}}}], author="creator", summary="add", expected_revision=1)
        self.assertEqual("AUTHORING_TEMPLATE_CHANGE_FORBIDDEN", error.exception.code)
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
        self.assertEqual(accepted["acceptance"]["id"], reversed_result["reversal"]["reversal_of"])
        validate_acceptance(reversed_result["acceptance"])
        self.assertEqual("Prepare a plain-language draft.", self.store.get("session.demo")["head"]["blueprint"]["steps"][1]["intent"])
        reloaded = AuthoringSessionStore(self.temp.name).get("session.demo")
        self.assertEqual(reversed_result["reversal"], reloaded["reversals"][0])

    def test_freeze_and_source_safety_are_fail_closed(self):
        self.store.freeze("session.demo", ["draft"], author="creator", summary="Freeze reviewed wording.")
        proposal = self.proposal([{"id": "c.draft", "target_id": "draft", "operation": "set_step_intent", "value": "Silently change frozen draft."}])
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.accept("session.demo", proposal["proposal_id"])
        self.assertEqual("AUTHORING_FROZEN_STEP", error.exception.code)
        state = self.store.get("session.demo")
        request = {"source_freeze_ids": [state["freezes"][0]["id"]], "reason": "Correct a reviewed requirement.", "author": "creator", "expected_revision": 1}
        accepted = self.store.accept("session.demo", proposal["proposal_id"], freeze_revision=request)
        self.assertIsNotNone(accepted["freeze_revision"])
        reloaded = AuthoringSessionStore(self.temp.name).get("session.demo")
        self.assertEqual(accepted["freeze_revision"]["source_freeze_ids"], reloaded["freeze_revisions"][0]["source_freeze_ids"])
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

    def test_reversal_rejects_later_change_to_same_target(self):
        first = self.proposal([{"id": "c.first", "target_id": "draft", "operation": "set_step_intent", "value": "First revision."}])
        acceptance = self.store.accept("session.demo", first["proposal_id"])["acceptance"]
        second = self.proposal([{"id": "c.second", "target_id": "draft", "operation": "set_step_intent", "value": "Second revision."}], revision=2)
        self.store.accept("session.demo", second["proposal_id"])
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.reverse("session.demo", acceptance["id"], author="creator", summary="Undo", expected_revision=3)
        self.assertEqual("AUTHORING_REVERSAL_AMBIGUOUS", error.exception.code)

    def test_freeze_revision_preserves_unaffected_steps_and_preview_is_pure(self):
        snapshot = self.store.freeze("session.demo", ["research", "draft"], author="creator", summary="Freeze both steps.")
        proposal = self.proposal([{"id": "c.draft", "target_id": "draft", "operation": "set_step_intent", "value": "Revise only draft."}])
        request = {"source_freeze_ids": [snapshot["id"]], "reason": "Approved draft correction.", "author": "creator", "expected_revision": 1}
        before = self.store.get("session.demo")
        self.store.preview("session.demo", proposal["proposal_id"], freeze_revision=request)
        self.assertEqual(before, self.store.get("session.demo"))
        self.store.accept("session.demo", proposal["proposal_id"], freeze_revision=request)
        reloaded = AuthoringSessionStore(self.temp.name)
        current = reloaded.get("session.demo")
        self.assertIn("research", reloaded.creator_projection(current)["frozen_steps"])
        self.assertNotIn("draft", reloaded.creator_projection(current)["frozen_steps"])
        research = reloaded.propose("session.demo", [{"id": "c.research", "target_id": "research", "operation": "set_step_intent", "value": "Change frozen research."}], author="creator", summary="bad", expected_revision=2)
        with self.assertRaises(AuthoringServiceError) as error:
            reloaded.accept("session.demo", research["proposal_id"])
        self.assertEqual("AUTHORING_FROZEN_STEP", error.exception.code)
        replacement = current["freeze_replacements"][0]
        replacement["digest"] = "0" * 64
        path = Path(self.temp.name) / "session.demo.json"
        path.write_text(__import__("json").dumps(current), encoding="utf-8")
        with self.assertRaises(AuthoringServiceError) as invalid:
            reloaded.get("session.demo") and reloaded.creator_projection(reloaded.get("session.demo"))
        self.assertEqual("AUTHORING_FREEZE_LINEAGE_INVALID", invalid.exception.code)

    def test_overlapping_freezes_require_exact_active_snapshot_set(self):
        first = self.store.freeze("session.demo", ["research", "draft"], author="creator", summary="Freeze both.")
        second = self.store.freeze("session.demo", ["draft"], author="creator", summary="Freeze draft again.")
        proposal = self.proposal([{"id": "c.draft", "target_id": "draft", "operation": "set_step_intent", "value": "Revise draft."}])
        bad = {"source_freeze_ids": [first["id"]], "reason": "incomplete", "author": "creator", "expected_revision": 1}
        with self.assertRaises(AuthoringServiceError) as error:
            self.store.preview("session.demo", proposal["proposal_id"], freeze_revision=bad)
        self.assertEqual("AUTHORING_FREEZE_REVISION_INVALID", error.exception.code)
        good = {**bad, "source_freeze_ids": [first["id"], second["id"]]}
        self.store.accept("session.demo", proposal["proposal_id"], freeze_revision=good)
        self.assertEqual(["research"], self.store.creator_projection(self.store.get("session.demo"))["frozen_steps"])


if __name__ == "__main__":
    unittest.main()
