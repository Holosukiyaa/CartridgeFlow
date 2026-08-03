import copy
import unittest

from core.protocol.authoring_contract import (
    accept_change_set, create_recipe_blueprint, create_recipe_instance,
    freeze_snapshot, propose_change_set, validate_acceptance,
    validate_change_set, validate_freeze_snapshot, _step_semantic_digest,
)
from core.protocol.tuning import TuningProtocolError, canonical_digest


SHA_A = "a" * 64
SHA_B = "b" * 64


class AuthoringContractV12Tests(unittest.TestCase):
    def setUp(self):
        self.blueprint = create_recipe_blueprint(
            "recipe.article", "Draft an article",
            [{"id": "draft", "intent": "Write", "inputs": {}, "outputs": {}}],
            [{"id": "source.brief", "kind": "source", "digest": SHA_A}],
        )
        self.instance = create_recipe_instance(self.blueprint, {"draft": {"tone": "clear"}})
        self.changes = [
            {"id": "change.binding", "target_id": "draft", "operation": "set_binding", "value": {"tone": "concise"}},
            {"id": "change.intent", "target_id": "draft", "operation": "set_step_intent", "value": "Write a concise article"},
            {"id": "change.source", "target_id": "source.brief", "operation": "set_source_reference", "value": {"id": "source.brief", "kind": "source", "digest": SHA_B}},
        ]

    def propose(self):
        return propose_change_set(self.instance, self.changes, "author", "Refine recipe")

    def test_full_acceptance_applies_every_supported_operation_immutably(self):
        proposal = self.propose()
        acceptance = accept_change_set(self.instance, proposal)
        self.assertEqual(acceptance, validate_acceptance(acceptance))
        self.assertEqual([item["id"] for item in self.changes], acceptance["accepted_change_ids"])
        self.assertEqual("concise", acceptance["instance"]["bindings"]["draft"]["tone"])
        self.assertEqual("Write a concise article", acceptance["blueprint"]["steps"][0]["intent"])
        self.assertEqual(SHA_B, acceptance["blueprint"]["source_references"][0]["digest"])
        self.assertEqual(self.blueprint["digest"], self.instance["blueprint_digest"])
        self.assertNotEqual(self.blueprint["digest"], acceptance["blueprint"]["digest"])
        self.assertEqual(2, acceptance["instance"]["revision"])
        self.assertEqual(self.instance["id"], acceptance["instance"]["parent_instance"]["id"])
        self.assertEqual(proposal, acceptance["change_set"])

    def test_partial_acceptance_is_atomic_and_retains_unselected_provenance(self):
        proposal = self.propose()
        acceptance = accept_change_set(self.instance, proposal, ["change.binding", "change.source"])
        self.assertEqual(["change.binding", "change.source"], acceptance["accepted_change_ids"])
        self.assertEqual("concise", acceptance["instance"]["bindings"]["draft"]["tone"])
        self.assertEqual("Write", acceptance["blueprint"]["steps"][0]["intent"])
        self.assertEqual(SHA_B, acceptance["blueprint"]["source_references"][0]["digest"])
        self.assertIn("change.intent", [item["id"] for item in acceptance["change_set"]["changes"]])
        self.assertNotIn("change.intent", acceptance["accepted_change_ids"])

    def test_selection_and_operation_validation_fail_closed_without_result(self):
        proposal = self.propose()
        for selection in ([], ["change.binding", "change.binding"], ["missing"]):
            with self.subTest(selection=selection), self.assertRaises(TuningProtocolError):
                accept_change_set(self.instance, proposal, selection)
        for change in (
            {"id": "bad.op", "target_id": "draft", "operation": "ignored", "value": {}},
            {"id": "bad.target", "target_id": "missing", "operation": "set_binding", "value": {}},
            {"id": "bad.secret", "target_id": "draft", "operation": "set_binding", "value": {"api_key": "x"}},
            {"id": "bad.path", "target_id": "source.brief", "operation": "set_source_reference", "value": {"id": "source.brief", "kind": "source", "digest": "C:\\private"}},
        ):
            with self.subTest(change=change), self.assertRaises(TuningProtocolError):
                propose_change_set(self.instance, [change], "author", "Invalid")

    def test_tampering_staleness_and_invalid_item_abort_entire_acceptance(self):
        proposal = self.propose()
        revised = accept_change_set(self.instance, proposal)["instance"]
        with self.assertRaises(TuningProtocolError):
            accept_change_set(revised, proposal)
        tampered = copy.deepcopy(proposal)
        tampered["changes"][0]["operation"] = "unsupported"
        body = {key: copy.deepcopy(value) for key, value in tampered.items() if key not in {"id", "digest"}}
        tampered["digest"] = canonical_digest(body)
        tampered["id"] = f"change-{tampered['digest'][:16]}"
        with self.assertRaises(TuningProtocolError):
            accept_change_set(self.instance, tampered, ["change.binding"])
        for artifact, validator in ((proposal, validate_change_set), (accept_change_set(self.instance, proposal), validate_acceptance), (self.blueprint, lambda item: create_recipe_instance(item, {}))):
            altered = copy.deepcopy(artifact)
            altered["digest"] = SHA_A
            with self.subTest(artifact=artifact.get("schema")), self.assertRaises(TuningProtocolError):
                validator(altered)

    def test_freeze_binds_exact_semantics_and_blocks_silent_step_change(self):
        semantic = _step_semantic_digest(self.instance, "draft")
        frozen = freeze_snapshot(self.instance, [{"step_id": "draft", "semantic_digest": semantic}], {"id": "topology.article", "kind": "compile", "digest": SHA_A}, "author", "Freeze draft")
        self.assertEqual(frozen, validate_freeze_snapshot(frozen))
        proposal = self.propose()
        with self.assertRaises(TuningProtocolError):
            accept_change_set(self.instance, proposal, ["change.intent"], frozen_snapshots=[frozen])
        altered = copy.deepcopy(frozen)
        altered["frozen_steps"][0]["semantic_digest"] = SHA_B
        with self.assertRaises(TuningProtocolError):
            validate_freeze_snapshot(altered)

    def test_digests_are_deterministic(self):
        first = self.propose()
        second = self.propose()
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(accept_change_set(self.instance, first)["digest"], accept_change_set(self.instance, second)["digest"])


if __name__ == "__main__":
    unittest.main()
