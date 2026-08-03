import copy
import unittest

from core.protocol.authoring_contract import (
    accept_change_set,
    create_recipe_blueprint,
    create_recipe_instance,
    freeze_snapshot,
    propose_change_set,
    validate_change_set,
    validate_freeze_snapshot,
)
from core.protocol.tuning import TuningProtocolError


SHA = "a" * 64


class AuthoringContractV12Tests(unittest.TestCase):
    def setUp(self):
        self.blueprint = create_recipe_blueprint(
            "recipe.article", "Draft an article", [{"id": "draft", "intent": "Write", "inputs": {}, "outputs": {}}],
            [{"id": "source.brief", "kind": "source", "digest": SHA}],
        )
        self.instance = create_recipe_instance(self.blueprint, {"draft": {"tone": "clear"}})

    def test_accepted_revision_and_freeze_are_deterministic(self):
        proposed = propose_change_set(self.instance, [{"step_id": "draft", "operation": "set_binding", "value": {"tone": "concise"}}], "author", "Refine tone")
        revised = accept_change_set(self.instance, proposed)
        self.assertEqual(2, revised["revision"])
        frozen = freeze_snapshot(revised, [{"step_id": "draft", "semantic_digest": SHA}], {"id": "topology.article", "kind": "compile", "digest": SHA}, "author", "Freeze draft semantics")
        self.assertEqual(frozen, validate_freeze_snapshot(frozen))
        self.assertEqual(["draft"], [item["step_id"] for item in frozen["frozen_steps"]])
        self.assertEqual(frozen["digest"], freeze_snapshot(revised, [{"step_id": "draft", "semantic_digest": SHA}], {"id": "topology.article", "kind": "compile", "digest": SHA}, "author", "Freeze draft semantics")["digest"])

    def test_stale_changes_and_unsafe_or_silent_freezes_fail_closed(self):
        proposed = propose_change_set(self.instance, [{"step_id": "draft", "operation": "set_binding", "value": {"tone": "clear"}}], "author", "Change")
        revised = accept_change_set(self.instance, proposed)
        with self.assertRaises(TuningProtocolError):
            accept_change_set(revised, proposed)
        with self.assertRaises(TuningProtocolError):
            propose_change_set(self.instance, [{"step_id": "draft", "operation": "set_binding", "value": {"api_key": "secret"}}], "author", "Unsafe")
        with self.assertRaises(TuningProtocolError):
            freeze_snapshot(revised, [], {"id": "topology.article", "kind": "compile", "digest": SHA}, "author", "Silent")
        tampered = copy.deepcopy(proposed)
        tampered["summary"] = "Changed"
        with self.assertRaises(TuningProtocolError):
            validate_change_set(tampered)


if __name__ == "__main__":
    unittest.main()
