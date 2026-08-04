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
    BASE_CONTRACT = {"id": "CARTRIDGEFLOW-BASE", "version": "0.3"}

    def __init__(self, root: str | Path, packages_dir: str | Path):
        self.root = Path(root).resolve()
        self.packages_dir = Path(packages_dir).resolve()

    def materialize(self, store: AuthoringSessionStore, session_id: str, *, expected_revision: int, candidate: dict) -> dict:
        # Acceptance and handoff share the Creator store's atomic revision boundary.
        with store._lock:
            return self._materialize(store, session_id, expected_revision=expected_revision, candidate=candidate)

    def _materialize(self, store: AuthoringSessionStore, session_id: str, *, expected_revision: int, candidate: dict) -> dict:
        try:
            state = store.get(session_id)
            store._require_revision(state, expected_revision)
            mappings = state.get("developer_mappings")
            step_ids = {step["id"] for step in state["head"]["blueprint"]["steps"]}
            if (state.get("template_instance") or state.get("trusted_recipe")) and (not isinstance(mappings, dict) or set(mappings) != step_ids or any(not str(value).strip() for value in mappings.values())):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have complete Developer mappings.")
            readiness = store.generation_readiness(state)
            if not readiness.get("ready"):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DESIGN_BLOCKED", "The Creator revision is not design-ready and unblocked.")
            actual_candidate = store.compile_candidate(state)
            if not isinstance(candidate, dict) or candidate != actual_candidate:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CANDIDATE_MISMATCH", "The compile candidate does not identify the current Creator revision.")
            if state.get("trusted_recipe"):
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
        flow_protocol = self.TRUSTED_FLOW_PROTOCOL if state.get("trusted_recipe") else self.LEGACY_FLOW_PROTOCOL
        lineage = self._lineage(instance, actual_candidate, freezes)
        if state.get("trusted_recipe"):
            lineage["trusted_recipe"] = {"id": state["trusted_recipe"]["id"], "digest": state["trusted_recipe"]["digest"]}
            lineage["developer_confirmation"] = {"digest": state["developer_confirmation"]["digest"], "author": state["developer_confirmation"]["author"]}
        root_flow = self._root_flow(instance, lineage, flow_protocol, mappings or {})
        findings = validate_execution_plan_v1_flow_contract(
            root_flow,
            protocol_id=flow_protocol["id"],
            protocol_version=flow_protocol["version"],
        )
        if findings:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE", "Accepted semantic relationships cannot be represented as a valid CF-FARP Root Flow.")

        manifest = self._manifest(actual_candidate, lineage, flow_protocol)
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

    def _manifest(self, candidate: dict, lineage: dict, flow_protocol: dict) -> dict:
        return {
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

    def _root_flow(self, instance: dict, lineage: dict, flow_protocol: dict, mappings: dict) -> dict:
        steps = sorted(instance["blueprint"]["steps"], key=lambda item: item["id"])
        relationships = sorted(instance["blueprint"].get("relations", []), key=lambda item: item["id"])
        order = self._topological_order(steps, relationships)
        states = {
            "start": {"type": "control", "title": "Creator handoff start", "locked": True},
            "complete": {"type": "terminal", "title": "Creator handoff complete", "locked": True},
        }
        for step in steps:
            states[f"step.{step['id']}"] = {
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
