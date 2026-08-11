"""Reversible projections from current product facts into CF-AUTHORING@1.0.0."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable

from .clean_protocol import CLEAN_CONTRACT_VERSION, resolve_clean_protocol_adapter
from .data_contracts import DataContractError


AUTHORING_ADAPTER_ID = "cartridgeflow.authoring.v1"
_INTENT_KINDS = (
    "project",
    "node",
    "review",
    "capability-gap",
    "capability-proposal",
)
_CAPABILITY_KINDS = ("definition", "dependency", "verification", "release")
_FLOW_KINDS = ("definition", "node", "plan", "decision", "interaction")
_DATA_KINDS = ("value-type", "binding", "store-access", "output-write", "lineage")
_PRESENTATION_KINDS = ("settings", "settings-binding", "ui")
_INTEGRATION_KINDS = ("model-binding", "tool", "tool-binding", "resource", "extension")
_COMPOSITION_KINDS = ("request", "resolution", "materialization", "provenance")


class CleanAuthoringProjectionError(DataContractError):
    """Raised when an existing product fact cannot be projected without guessing."""


class CleanAuthoringProjector:
    """Build clean-v1 envelopes while leaving the current domain objects untouched."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.registry_path = Path(registry_path).resolve() if registry_path is not None else None
        self.adapter = resolve_clean_protocol_adapter(AUTHORING_ADAPTER_ID)

    def intent_session(self, state: dict) -> list[dict]:
        """Project one persisted AuthoringSessionStore state into current Intent facts."""
        state = _mapping(state, "authoring state")
        head = _mapping(state.get("head"), "authoring head")
        blueprint = _mapping(head.get("blueprint"), "authoring blueprint")
        steps = _mapping_list(blueprint.get("steps"), "authoring steps")
        node_ids = [_text(item.get("id"), "authoring node id") for item in steps]
        if not node_ids:
            _projection_error("clean_authoring_intent_nodes_missing", "authoring session has no intent nodes")
        intent_id = _text(
            state.get("project_id") or blueprint.get("id") or blueprint.get("recipe_id"),
            "intent id",
        )
        goal = _text(blueprint.get("intent") or blueprint.get("goal"), "intent goal")
        revision = _revision(head.get("revision"))
        semantic_recipe = state.get("semantic_recipe")
        recipe_nodes = (
            _mapping_list(semantic_recipe.get("nodes"), "semantic recipe nodes")
            if isinstance(semantic_recipe, dict)
            else []
        )
        gaps = sorted(
            _text(item.get("id"), "capability gap id")
            for item in recipe_nodes
            if not isinstance(item.get("capability"), dict)
        )
        common = {
            "revision": revision,
            "intent_id": intent_id,
            "goal": goal,
            "node_ids": node_ids,
            "capability_gaps": gaps,
        }
        result = [self._envelope(f"cartridgeflow.intent.{kind}", {**common, "kind": kind}) for kind in _INTENT_KINDS[:3]]
        if gaps:
            result.extend(
                self._envelope(f"cartridgeflow.intent.{kind}", {**common, "kind": kind})
                for kind in _INTENT_KINDS[3:]
            )
        bindings = _mapping(head.get("bindings") or {}, "authoring bindings")
        for node_id in sorted(bindings):
            values = _mapping(bindings[node_id], f"binding values for {node_id}")
            for field_id in sorted(values):
                result.append(
                    self._envelope(
                        "cartridgeflow.intent.field",
                        {
                            **common,
                            "kind": "field",
                            "field_id": f"{node_id}.{field_id}",
                            "value_type": _value_type(values[field_id]),
                            "required": True,
                        },
                    )
                )
        return result

    def capability_release(
        self,
        release: dict,
        *,
        version: str | None = None,
        permissions: Iterable[str] | None = None,
    ) -> list[dict]:
        """Project one immutable capability-cartridge release into capability contracts."""
        release = _mapping(release, "capability release")
        capability_id = _text(release.get("id"), "capability id")
        revision = _revision(release.get("revision"))
        capability_version = _semver(version or release.get("version") or CLEAN_CONTRACT_VERSION)
        interface = _mapping(release.get("interface"), "capability interface")
        inputs = _mapping_list(interface.get("inputs") or [], "capability inputs")
        outputs = _mapping_list(interface.get("outputs") or [], "capability outputs")
        port_records = [(item, "input") for item in inputs] + [(item, "output") for item in outputs]
        port_ids = [_text(item.get("id"), "capability port id") for item, _direction in port_records]
        if not port_ids:
            _projection_error(
                "clean_authoring_capability_ports_missing",
                f"capability {capability_id} has no public port and cannot satisfy clean-v1",
            )
        dependency_ids = [
            f"{_text(item.get('id'), 'capability dependency id')}@{_revision(item.get('revision'))}"
            for item in _mapping_list(release.get("dependencies") or [], "capability dependencies")
        ]
        declared_permissions = sorted({_text(item, "capability permission") for item in permissions or []})
        common = {
            "revision": revision,
            "capability_id": capability_id,
            "version": capability_version,
            "ports": port_ids,
            "permissions": declared_permissions,
            "dependencies": dependency_ids,
        }
        result = [
            self._envelope(f"cartridgeflow.capability.{kind}", {**common, "kind": kind})
            for kind in _CAPABILITY_KINDS
        ]
        for port, direction in port_records:
            result.append(
                self._envelope(
                    "cartridgeflow.capability.port",
                    {
                        **common,
                        "kind": "port",
                        "port_id": _text(port.get("id"), "capability port id"),
                        "direction": direction,
                        "value_type": _schema_value_type(port.get("schema")),
                    },
                )
            )
        creator = _mapping(release.get("creator"), "capability creator contract")
        for field in _mapping_list(creator.get("editable_fields") or [], "capability fields"):
            result.append(
                self._envelope(
                    "cartridgeflow.capability.field",
                    {
                        **common,
                        "kind": "field",
                        "field_id": _text(field.get("id"), "capability field id"),
                        "value_type": _text(field.get("value_type"), "capability field value type"),
                        "required": bool(field.get("required")),
                    },
                )
            )
        return result

    def flow(self, root_flow: dict, *, flow_id: str | None = None, revision: int = 1) -> list[dict]:
        """Project an executable Root Flow without copying runtime-only node details."""
        root_flow = _mapping(root_flow, "root flow")
        states = _mapping(root_flow.get("states"), "root flow states")
        node_ids = sorted(_text(item, "flow node id") for item in states)
        if not node_ids:
            _projection_error("clean_authoring_flow_nodes_missing", "root flow has no nodes")
        plan = _mapping(root_flow.get("execution_plan"), "root flow execution plan")
        entry_node = _text(plan.get("entry") or root_flow.get("start") or node_ids[0], "flow entry node")
        if entry_node not in states:
            _projection_error("clean_authoring_flow_entry_invalid", f"flow entry is not a declared node: {entry_node}")
        edges = []
        source_edges = _mapping_list(plan.get("edges") or [], "root flow edges")
        for edge in source_edges:
            source = _text(edge.get("from"), "flow edge source")
            target = _text(edge.get("to"), "flow edge target")
            if source not in states or target not in states:
                _projection_error(
                    "clean_authoring_flow_edge_invalid",
                    f"flow edge references an unknown node: {source} -> {target}",
                )
            edges.append({"from": source, "to": target})
        common = {
            "revision": _revision(revision),
            "flow_id": _text(flow_id or root_flow.get("id"), "flow id"),
            "entry_node": entry_node,
            "node_ids": node_ids,
            "edges": edges,
        }
        result = [
            self._envelope(f"cartridgeflow.flow.{kind}", {**common, "kind": kind})
            for kind in _FLOW_KINDS
        ]
        for edge, projected in zip(source_edges, edges):
            condition = edge.get("condition")
            if isinstance(condition, (dict, list)):
                condition = json.dumps(condition, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            result.append(
                self._envelope(
                    "cartridgeflow.flow.edge",
                    {
                        **common,
                        "kind": "edge",
                        "from": projected["from"],
                        "to": projected["to"],
                        "condition": str(condition or ""),
                    },
                )
            )
        return result

    def data(self, fact: dict) -> list[dict]:
        """Project one explicit data movement fact into the five clean data views."""
        fact = _mapping(fact, "data fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "source": _text(fact.get("source"), "data source"),
            "target": _text(fact.get("target"), "data target"),
            "value_type": _text(fact.get("value_type"), "data value type"),
            "nullable": bool(fact.get("nullable")),
            "lineage": [_text(item, "data lineage id") for item in _list(fact.get("lineage"), "data lineage")],
        }
        if not common["lineage"]:
            _projection_error("clean_authoring_data_lineage_missing", "data fact has no lineage")
        return [
            self._envelope(f"cartridgeflow.data.{kind}", {**common, "kind": kind})
            for kind in _DATA_KINDS
        ]

    def presentation(
        self,
        *,
        settings_id: str,
        fields: Iterable[str],
        visibility: str,
        revision: int = 1,
    ) -> list[dict]:
        field_ids = [_text(item, "presentation field id") for item in fields]
        if not field_ids:
            _projection_error("clean_authoring_presentation_fields_missing", "presentation has no fields")
        common = {
            "revision": _revision(revision),
            "settings_id": _text(settings_id, "settings id"),
            "fields": field_ids,
            "visibility": visibility,
        }
        return [
            self._envelope(f"cartridgeflow.presentation.{kind}", {**common, "kind": kind})
            for kind in _PRESENTATION_KINDS
        ]

    def integration(self, fact: dict) -> dict:
        """Project one declared model/tool/resource/extension binding."""
        fact = _mapping(fact, "integration fact")
        kind = str(fact.get("kind") or "")
        if kind not in _INTEGRATION_KINDS:
            _projection_error("clean_authoring_integration_kind_invalid", f"unknown integration kind: {kind}")
        return self._envelope(
            f"cartridgeflow.integration.{kind}",
            {
                "kind": kind,
                "revision": _revision(fact.get("revision", 1)),
                "binding_id": _text(fact.get("binding_id"), "integration binding id"),
                "provider": _text(fact.get("provider"), "integration provider"),
                "resource": _text(fact.get("resource"), "integration resource"),
                "permissions": [
                    _text(item, "integration permission")
                    for item in _list(fact.get("permissions") or [], "integration permissions")
                ],
            },
        )

    def composition(self, fact: dict) -> list[dict]:
        """Project one resolved dependency closure and its optional request metadata."""
        fact = _mapping(fact, "composition fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "composition_id": _text(fact.get("composition_id"), "composition id"),
            "dependencies": [
                _text(item, "composition dependency")
                for item in _list(fact.get("dependencies"), "composition dependencies")
            ],
            "lock_digest": _digest(fact.get("lock_digest"), "composition lock digest"),
            "namespace": _text(fact.get("namespace"), "composition namespace"),
        }
        if not common["dependencies"]:
            _projection_error("clean_authoring_composition_dependencies_missing", "composition has no dependencies")
        result = []
        for kind in _COMPOSITION_KINDS:
            payload = {**common, "kind": kind}
            if kind == "request":
                payload.update(
                    {
                        "request_id": _text(fact.get("request_id"), "composition request id"),
                        "requested_at": _text(fact.get("requested_at"), "composition request time"),
                        "requested_by": _text(fact.get("requested_by"), "composition requester"),
                    }
                )
            result.append(self._envelope(f"cartridgeflow.composition.{kind}", payload))
        return result

    def _envelope(self, contract_id: str, payload: dict) -> dict:
        envelope = {
            "contract_id": contract_id,
            "version": CLEAN_CONTRACT_VERSION,
            "payload": deepcopy(payload),
        }
        self.adapter.validate(
            contract_id,
            envelope,
            root=self.root,
            registry_path=self.registry_path,
        )
        return envelope


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        _projection_error("clean_authoring_source_invalid", f"{label} must be an object")
    return value


def _mapping_list(value: Any, label: str) -> list[dict]:
    items = _list(value, label)
    if any(not isinstance(item, dict) for item in items):
        _projection_error("clean_authoring_source_invalid", f"{label} must contain only objects")
    return items


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        _projection_error("clean_authoring_source_invalid", f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _projection_error("clean_authoring_source_invalid", f"{label} must not be empty")
    return text


def _revision(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _projection_error("clean_authoring_revision_invalid", "revision must be a positive integer")
    return value


def _semver(value: Any) -> str:
    text = _text(value, "capability version")
    parts = text.split(".")
    if len(parts) != 3 or any(not item.isdigit() for item in parts):
        _projection_error("clean_authoring_version_invalid", "capability version must use x.y.z")
    return text


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _projection_error("clean_authoring_digest_invalid", f"{label} must be a lowercase SHA-256 digest")
    return text


def _schema_value_type(value: Any) -> str:
    if not isinstance(value, dict):
        return "json"
    if isinstance(value.get("$ref"), str) and value["$ref"].strip():
        return value["$ref"].strip()
    kind = value.get("type")
    if isinstance(kind, str) and kind:
        return kind
    if isinstance(kind, list) and kind:
        return "|".join(sorted(str(item) for item in kind))
    return "json"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "json"


def _projection_error(code: str, message: str) -> None:
    raise CleanAuthoringProjectionError(code, message)
