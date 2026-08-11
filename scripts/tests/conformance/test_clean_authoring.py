from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import (
    CLEAN_SOURCE_ID,
    CleanAuthoringProjectionError,
    CleanAuthoringProjector,
    ImplementationSource,
    publish_protocol_knowledge_registry,
)
from core.studio.authoring_service import AuthoringSessionStore
from core.studio.capability_cartridges import CapabilityCartridgeStore


class CleanAuthoringProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.registry = Path(cls._temporary.name) / "protocol-registry.sqlite"
        publish_protocol_knowledge_registry(
            cls.registry,
            ROOT / "protocol-source" / "protocol-source.sqlite",
            implementation_sources=[ImplementationSource(CLEAN_SOURCE_ID, ROOT)],
        )
        cls.projector = CleanAuthoringProjector(ROOT, registry_path=cls.registry)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_current_product_facts_project_to_all_35_authoring_contracts(self):
        envelopes = []
        envelopes += self.projector.intent_session(self._session())
        envelopes += self.projector.capability_release(self._capability(), permissions=["network.read"])
        envelopes += self.projector.flow(self._root_flow())
        envelopes += self.projector.data(
            {
                "revision": 1,
                "source": "fetch.items",
                "target": "review.items",
                "value_type": "array",
                "nullable": False,
                "lineage": ["fetch"],
            }
        )
        envelopes += self.projector.presentation(
            settings_id="workspace.rss-source",
            fields=["topics"],
            visibility="public",
        )
        envelopes += [
            self.projector.integration(
                {
                    "kind": kind,
                    "binding_id": f"binding-{kind}",
                    "provider": "local",
                    "resource": "rss-reader",
                    "permissions": ["network.read"],
                }
            )
            for kind in ("model-binding", "tool", "tool-binding", "resource", "extension")
        ]
        envelopes += self.projector.composition(
            {
                "composition_id": "composition-rss-review",
                "dependencies": ["workspace.rss-source@1"],
                "lock_digest": "d" * 64,
                "namespace": "flow.rss-review",
                "request_id": "request-001",
                "requested_at": "2030-01-01T00:00:00Z",
                "requested_by": "operator",
            }
        )
        actual = {item["contract_id"] for item in envelopes}
        expected = {
            "cartridgeflow.intent.project", "cartridgeflow.intent.node", "cartridgeflow.intent.field",
            "cartridgeflow.intent.review", "cartridgeflow.intent.capability-gap",
            "cartridgeflow.intent.capability-proposal", "cartridgeflow.capability.definition",
            "cartridgeflow.capability.port", "cartridgeflow.capability.field",
            "cartridgeflow.capability.dependency", "cartridgeflow.capability.verification",
            "cartridgeflow.capability.release", "cartridgeflow.flow.definition", "cartridgeflow.flow.node",
            "cartridgeflow.flow.edge", "cartridgeflow.flow.plan", "cartridgeflow.flow.decision",
            "cartridgeflow.flow.interaction", "cartridgeflow.data.value-type", "cartridgeflow.data.binding",
            "cartridgeflow.data.store-access", "cartridgeflow.data.output-write", "cartridgeflow.data.lineage",
            "cartridgeflow.presentation.settings", "cartridgeflow.presentation.settings-binding",
            "cartridgeflow.presentation.ui", "cartridgeflow.integration.model-binding",
            "cartridgeflow.integration.tool", "cartridgeflow.integration.tool-binding",
            "cartridgeflow.integration.resource", "cartridgeflow.integration.extension",
            "cartridgeflow.composition.request", "cartridgeflow.composition.resolution",
            "cartridgeflow.composition.materialization", "cartridgeflow.composition.provenance",
        }
        self.assertEqual(expected, actual)

    def test_projection_fails_instead_of_inventing_missing_public_ports(self):
        capability = self._capability()
        capability["interface"] = {"inputs": [], "outputs": []}
        with self.assertRaises(CleanAuthoringProjectionError) as error:
            self.projector.capability_release(capability)
        self.assertEqual("clean_authoring_capability_ports_missing", error.exception.code)

    def test_projection_rejects_invalid_flow_and_incomplete_composition(self):
        flow = self._root_flow()
        flow["execution_plan"]["edges"][0]["to"] = "missing"
        with self.assertRaises(CleanAuthoringProjectionError) as flow_error:
            self.projector.flow(flow)
        self.assertEqual("clean_authoring_flow_edge_invalid", flow_error.exception.code)
        with self.assertRaises(CleanAuthoringProjectionError) as composition_error:
            self.projector.composition(
                {
                    "composition_id": "empty",
                    "dependencies": [],
                    "lock_digest": "d" * 64,
                    "namespace": "flow.empty",
                    "request_id": "request-empty",
                    "requested_at": "2030-01-01T00:00:00Z",
                    "requested_by": "operator",
                }
            )
        self.assertEqual("clean_authoring_composition_dependencies_missing", composition_error.exception.code)

    def test_product_stores_expose_clean_contracts_without_changing_saved_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = AuthoringSessionStore(Path(directory) / "sessions")
            sessions.create(
                "session.clean",
                "recipe.clean",
                "Review public entries",
                [{"id": "review", "intent": "Review", "inputs": {}, "outputs": {}}],
                [],
                {"review": {"tone": "plain"}},
            )
            before = sessions.get("session.clean")
            intent = sessions.clean_intent_contracts(
                "session.clean", project_root=ROOT, registry_path=self.registry
            )
            self.assertIn("cartridgeflow.intent.project", {item["contract_id"] for item in intent})
            self.assertEqual(before, sessions.get("session.clean"))

            capabilities = CapabilityCartridgeStore(Path(directory) / "capabilities")
            capability = self._capability()
            with patch.object(capabilities, "get", return_value=capability):
                projected = capabilities.clean_authoring_contracts(
                    capability["id"], project_root=ROOT, registry_path=self.registry
                )
            contract_ids = {item["contract_id"] for item in projected}
            self.assertIn("cartridgeflow.capability.definition", contract_ids)
            self.assertIn("cartridgeflow.presentation.settings", contract_ids)

    @staticmethod
    def _session() -> dict:
        return {
            "schema": "cartridgeflow.authoring_session.v1",
            "project_id": "project.rss-review",
            "head": {
                "revision": 2,
                "blueprint": {
                    "id": "recipe.rss-review",
                    "intent": "Review public RSS entries",
                    "steps": [
                        {"id": "fetch", "intent": "Fetch entries", "inputs": {}, "outputs": {"items": {}}},
                        {"id": "review", "intent": "Review entries", "inputs": {"items": {}}, "outputs": {}},
                    ],
                },
                "bindings": {"fetch": {"topics": ["AI"]}, "review": {}},
            },
            "semantic_recipe": {
                "nodes": [
                    {"id": "fetch", "capability": {"id": "workspace.rss-source"}},
                    {"id": "review", "capability": None},
                ]
            },
        }

    @staticmethod
    def _capability() -> dict:
        return {
            "schema": "cartridgeflow.capability_cartridge_release.v1",
            "id": "workspace.rss-source",
            "revision": 1,
            "creator": {
                "editable_fields": [
                    {"id": "topics", "value_type": "string_list", "required": True}
                ]
            },
            "interface": {
                "inputs": [],
                "outputs": [
                    {"id": "items", "schema": {"type": "array"}, "required": True}
                ],
            },
            "dependencies": [],
        }

    @staticmethod
    def _root_flow() -> dict:
        return {
            "id": "flow.rss-review",
            "start": "fetch",
            "states": {"fetch": {"type": "process"}, "review": {"type": "process"}},
            "execution_plan": {
                "entry": "fetch",
                "edges": [{"id": "fetch-review", "from": "fetch", "to": "review"}],
            },
        }


if __name__ == "__main__":
    unittest.main()
