"""Creator revision to CF-FARP and CF-CRE handoff bridge.

The bridge is deliberately a materializer only.  It validates immutable Creator
facts, writes a minimal portable source package outside the Creator store, and
uses the existing CF-CRE builder/signature path.  It never installs or runs a
cartridge.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

from core.protocol.flow_contract import validate_execution_plan_v1_flow_contract
from core.protocol.release_builder import ReleaseBuildError, build_release_archive, inspect_release_archive
from core.protocol.release_signing import ensure_development_signing_identity, trusted_public_keys
from core.protocol.tuning import canonical_digest
from core.studio.authoring_service import AuthoringServiceError, AuthoringSessionStore
from core.studio.release import release_archive_inputs
from core.studio.trusted_node_presets import materialize_trusted_node_state, validate_trusted_node_mapping


class CreatorRuntimeBridgeError(ValueError):
    """Stable error returned when immutable Creator facts cannot be handed off."""

    def __init__(self, code: str, message: str, *, status: int = 409):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.creator_handoff_error.v1", "code": self.code, "message": str(self)}


class CreatorRuntimeBridge:
    """Build deterministic, signed handoff artifacts from one current revision."""

    PUBLISHER_ID = "creator"
    LEGACY_FLOW_PROTOCOL = {"id": "CF-FARP", "version": "1.1"}
    TRUSTED_FLOW_PROTOCOL = {"id": "CF-FARP", "version": "1.5"}
    CREATOR_PACKAGE_PROTOCOL = {"id": "CF-FARP", "version": "1.6"}
    BASE_CONTRACT = {"id": "CARTRIDGEFLOW-BASE", "version": "0.3"}

    def __init__(self, root: str | Path, packages_dir: str | Path):
        self.root = Path(root).resolve()
        self.packages_dir = Path(packages_dir).resolve()

    def materialize(self, store: AuthoringSessionStore, session_id: str, *, expected_revision: int, candidate: dict) -> dict:
        """Compatibility handoff governed by CF-FARP@1.5 confirmation semantics."""
        with store._lock:
            return self._materialize(
                store,
                session_id,
                expected_revision=expected_revision,
                candidate=candidate,
                package_boundary=False,
            )

    def package(self, store: AuthoringSessionStore, session_id: str, *, expected_revision: int) -> dict:
        """Validate, map, sign, and publish one Creator package atomically."""
        with store._lock:
            state = store.get(session_id)
            store._require_revision(state, expected_revision)
            candidate = store.compile_candidate(state)
            return self._materialize(
                store,
                session_id,
                expected_revision=expected_revision,
                candidate=candidate,
                package_boundary=True,
            )

    def _materialize(self, store: AuthoringSessionStore, session_id: str, *, expected_revision: int, candidate: dict, package_boundary: bool) -> dict:
        try:
            state = store.get(session_id)
            store._require_revision(state, expected_revision)
            mappings = state.get("developer_mappings")
            step_ids = {step["id"] for step in state["head"]["blueprint"]["steps"]}
            if (state.get("template_instance") or state.get("trusted_recipe")) and (not isinstance(mappings, dict) or set(mappings) != step_ids):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have complete Developer mappings.")
            if state.get("trusted_recipe") and any(not isinstance(value, dict) for value in mappings.values()):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have executable Developer mapping snapshots.")
            if state.get("template_instance") and any(not str(value).strip() for value in mappings.values()):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have complete Developer mappings.")
            readiness = store.generation_readiness(state)
            if not readiness.get("ready"):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DESIGN_BLOCKED", "The Creator revision is not design-ready and unblocked.")
            actual_candidate = store.compile_candidate(state)
            if not isinstance(candidate, dict) or candidate != actual_candidate:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CANDIDATE_MISMATCH", "The compile candidate does not identify the current Creator revision.")
            if state.get("trusted_recipe") and not package_boundary:
                confirmation = state.get("developer_confirmation")
                if not isinstance(confirmation, dict) or confirmation.get("candidate") != actual_candidate or confirmation.get("revision") != expected_revision:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DEVELOPER_CONFIRMATION_REQUIRED", "Developer must confirm this exact recipe revision before handoff.")
            freezes = store._active_freezes(state)
        except AuthoringServiceError as exc:
            if exc.code == "AUTHORING_REVISION_CONFLICT":
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_REVISION_STALE", "The Creator revision is no longer current.") from exc
            if exc.code.startswith("AUTHORING_FREEZE_"):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_FREEZE_INVALID", "Applicable freeze facts are invalid.") from exc
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_SESSION_INVALID", "The Creator session facts are unavailable.", status=exc.status) from exc

        instance = state["head"]
        flow_protocol = (
            self.CREATOR_PACKAGE_PROTOCOL
            if state.get("trusted_recipe") and package_boundary
            else self.TRUSTED_FLOW_PROTOCOL
            if state.get("trusted_recipe")
            else self.LEGACY_FLOW_PROTOCOL
        )
        lineage = self._lineage(instance, actual_candidate, freezes)
        if state.get("trusted_recipe"):
            lineage["trusted_recipe"] = {"id": state["trusted_recipe"]["id"], "digest": state["trusted_recipe"]["digest"]}
            lineage["mapping_snapshot_digest"] = actual_candidate["mapping_digest"]
            if not package_boundary:
                lineage["developer_confirmation"] = {"digest": state["developer_confirmation"]["digest"], "author": state["developer_confirmation"]["author"]}
        root_flow = self._root_flow(
            instance,
            lineage,
            flow_protocol,
            mappings or {},
            trusted_recipe=state.get("trusted_recipe"),
            trusted_presets=state.get("trusted_presets") or [],
        )
        findings = validate_execution_plan_v1_flow_contract(
            root_flow,
            protocol_id=flow_protocol["id"],
            protocol_version=flow_protocol["version"],
        )
        if findings:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE", "Accepted semantic relationships cannot be represented as a valid CF-FARP Root Flow.")

        manifest = self._manifest(actual_candidate, lineage, flow_protocol, mappings or {})
        release_inputs = release_archive_inputs(manifest)
        artifact_name = f"creator-{actual_candidate['id']}.cf-cre.zip"
        output = self.packages_dir / artifact_name
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="creator-handoff-", dir=self.packages_dir) as source_dir:
            source = Path(source_dir)
            self._write_json(source / "manifest.json", manifest)
            self._write_json(source / "root.flow.json", root_flow)
            # The release builder writes a complete archive before it is atomically published.
            pending = self.packages_dir / f".{artifact_name}.pending"
            try:
                identity = ensure_development_signing_identity(self.root, self.PUBLISHER_ID)
                built = build_release_archive(
                    source,
                    pending,
                    publisher_id=self.PUBLISHER_ID,
                    experience=release_inputs["experience"],
                    delivery=release_inputs["delivery"],
                    placement=release_inputs["placement"],
                    required_capabilities=release_inputs["required_capabilities"],
                    required_permissions=release_inputs["required_permissions"],
                    signing_identity=identity,
                )
                inspection = inspect_release_archive(pending, trusted_keys=trusted_public_keys(self.root))
                if not inspection.get("activation_allowed"):
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_SIGNATURE_INVALID", "The signed CF-CRE handoff could not be independently verified.")
                pending.replace(output)
            except CreatorRuntimeBridgeError:
                pending.unlink(missing_ok=True)
                raise
            except (ReleaseBuildError, OSError, ValueError) as exc:
                pending.unlink(missing_ok=True)
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_PACKAGE_FAILED", "The signed CF-CRE handoff package could not be created.") from exc

        return {
            "schema": "cartridgeflow.creator_runtime_handoff.v1",
            "status": "signed_handoff_ready",
            "protocol": "CF-CRE@1",
            "release_id": built["release_id"],
            "filename": output.name,
            "lineage": deepcopy(lineage),
            "root_flow": {"entry": "root.flow.json", "protocol": deepcopy(flow_protocol), "digest": self._digest_json(root_flow)},
            "signature": {"verified": True, "key_id": identity.key_id},
        }

    def _manifest(self, candidate: dict, lineage: dict, flow_protocol: dict, mappings: dict) -> dict:
        manifest = {
            "schema_version": "1.0",
            "id": f"creator-{candidate['digest'][:24]}",
            "name": "Creator signed handoff",
            "version": f"0.0.{candidate['revision']}",
            "kind": "creator_handoff",
            "category": "authoring",
            "publisher": {"id": self.PUBLISHER_ID},
            "base_contract": deepcopy(self.BASE_CONTRACT),
            "runtime_contract": {"protocol": flow_protocol["id"], "protocol_version": flow_protocol["version"]},
            "runtime": {"type": "handoff_only"},
            "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
            "inputs": [],
            "outputs": [],
            "delivery": {"primary_output": "handoff"},
            "creator_lineage": deepcopy(lineage),
        }

        trusted_mappings = [item for item in mappings.values() if isinstance(item, dict)]
        for field in ("inputs", "outputs", "permissions", "mcp_tools", "resource_requirements"):
            merged = self._merge_requirement_lists(trusted_mappings, field)
            if merged:
                manifest[field] = merged
        roles = self._merge_requirement_lists(trusted_mappings, "llm_roles")
        if roles:
            manifest["llm_recipe"] = {"schema": "cartridgeflow.llm_recipe.v1", "roles": roles}
        artifacts = [item.get("requirements", {}).get("artifacts") for item in trusted_mappings if item.get("requirements", {}).get("artifacts")]
        if artifacts:
            first = artifacts[0]
            if any(item != first for item in artifacts[1:]):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_REQUIREMENT_CONFLICT", "Trusted nodes declare incompatible artifact policies.")
            manifest["artifacts"] = deepcopy(first)
        return manifest

    def _root_flow(self, instance: dict, lineage: dict, flow_protocol: dict, mappings: dict, *, trusted_recipe: dict | None, trusted_presets: list[dict]) -> dict:
        steps = sorted(instance["blueprint"]["steps"], key=lambda item: item["id"])
        relationships = sorted(instance["blueprint"].get("relations", []), key=lambda item: item["id"])
        order = self._topological_order(steps, relationships)
        states = {
            "start": {"type": "control", "title": "Creator handoff start", "locked": True},
            "complete": {"type": "terminal", "title": "Creator handoff complete", "locked": True},
        }
        trusted_nodes = {item["id"]: item for item in (trusted_recipe or {}).get("nodes", [])}
        presets = {item["id"]: item for item in trusted_presets}
        for step in steps:
            state_id = f"step.{step['id']}"
            if trusted_recipe:
                recipe_node = trusted_nodes.get(step["id"])
                preset = presets.get((recipe_node or {}).get("preset", {}).get("id"))
                if not recipe_node or not preset:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "Trusted recipe facts are incomplete.")
                try:
                    mapping = validate_trusted_node_mapping(mappings[step["id"]], preset)
                    state = materialize_trusted_node_state(mapping, preset, instance["bindings"].get(step["id"], {}))
                except AuthoringServiceError as exc:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_INVALID", str(exc)) from exc
                state["title"] = step["intent"]
                state["display_name"] = step["intent"]
                states[state_id] = state
            else:
                states[state_id] = {
                    "type": "semantic_step",
                    "semantic_step": {
                        "id": step["id"],
                        "semantic_digest": canonical_digest({"step": step, "binding": instance["bindings"].get(step["id"], {})}),
                        "input_ids": sorted(step["inputs"]),
                        "output_ids": sorted(step["outputs"]),
                        **({"developer_mapping_key": mappings[step["id"]]} if step["id"] in mappings else {}),
                    },
                }
        route = ["start", *[f"step.{step_id}" for step_id in order], "complete"]
        edges = [{"id": f"handoff.{index:03d}", "kind": "sequence", "from": route[index], "to": route[index + 1]} for index in range(len(route) - 1)]
        if trusted_recipe:
            states["flow_failed"] = {"type": "terminal", "title": "Trusted flow failed", "locked": True}
            for index, step_id in enumerate(order):
                edges.append({
                    "id": f"handoff.failure.{index:03d}",
                    "kind": "failure",
                    "from": f"step.{step_id}",
                    "to": "flow_failed",
                    "failure": {
                        "id": f"trusted.{step_id}.failure",
                        "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"],
                    },
                })
        return {
            "schema_version": "1.0",
            "id": f"creator-{lineage['compile_candidate']['digest'][:24]}.root",
            "mode": "lifecycle",
            "protocol": deepcopy(flow_protocol),
            "start": "start",
            "states": states,
            "execution_plan": {"schema": "cartridgeflow.execution_plan.v1", "entry": "start", "edges": edges},
            "semantic_relationships": [{key: relation[key] for key in ("id", "from_step_id", "to_step_id", "relation")} for relation in relationships],
            "creator_lineage": deepcopy(lineage),
        }

    @staticmethod
    def _merge_requirement_lists(mappings: list[dict], field: str) -> list[dict]:
        merged: dict[str, dict] = {}
        for mapping in mappings:
            requirements = mapping.get("requirements") if isinstance(mapping.get("requirements"), dict) else {}
            if field == "llm_roles":
                recipe = requirements.get("llm_recipe") if isinstance(requirements.get("llm_recipe"), dict) else {}
                values = recipe.get("roles") or []
            else:
                values = requirements.get(field) or []
            if not isinstance(values, list):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_REQUIREMENT_INVALID", f"Trusted node requirement {field} must be a list.")
            for index, item in enumerate(values):
                if not isinstance(item, dict):
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_REQUIREMENT_INVALID", f"Trusted node requirement {field} contains an invalid item.")
                identity = str(item.get("id") or item.get("role") or f"index:{index}")
                existing = merged.get(identity)
                if existing is not None and existing != item:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_REQUIREMENT_CONFLICT", f"Trusted nodes declare incompatible {field} item {identity}.")
                merged[identity] = deepcopy(item)
        return [merged[key] for key in sorted(merged)]

    @staticmethod
    def _lineage(instance: dict, candidate: dict, freezes: list[dict]) -> dict:
        return {
            "schema": "cartridgeflow.creator_handoff_lineage.v1",
            "accepted_revision": {"id": instance["id"], "revision": instance["revision"], "digest": instance["digest"]},
            "compile_candidate": {key: candidate[key] for key in ("id", "kind", "digest", "revision")},
            "freeze_snapshots": [{"id": item["id"], "digest": item["digest"]} for item in sorted(freezes, key=lambda item: item["id"])],
        }

    @staticmethod
    def _topological_order(steps: list[dict], relationships: list[dict]) -> list[str]:
        ids = {item["id"] for item in steps}
        outgoing = {step_id: [] for step_id in ids}
        indegree = {step_id: 0 for step_id in ids}
        for relation in relationships:
            source, target = relation.get("from_step_id"), relation.get("to_step_id")
            if source not in ids or target not in ids or source == target or target in outgoing[source]:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE", "Accepted semantic relationships cannot be represented as a valid CF-FARP Root Flow.")
            outgoing[source].append(target)
            indegree[target] += 1
        ready = sorted(step_id for step_id, count in indegree.items() if count == 0)
        order = []
        while ready:
            step_id = ready.pop(0)
            order.append(step_id)
            for target in sorted(outgoing[step_id]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
                    ready.sort()
        if len(order) != len(ids):
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE", "Accepted semantic relationships contain a cycle.")
        return order

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    @staticmethod
    def _digest_json(value: dict) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
