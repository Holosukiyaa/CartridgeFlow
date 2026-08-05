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
from core.protocol.capability_cartridges import validate_capability_release
from core.studio.capability_cartridges import CapabilityCartridgeStore


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
    RECURSIVE_PACKAGE_PROTOCOL = {"id": "CF-FARP", "version": "1.7"}
    BASE_CONTRACT = {"id": "CARTRIDGEFLOW-BASE", "version": "0.3"}

    def __init__(self, root: str | Path, packages_dir: str | Path, capability_store: CapabilityCartridgeStore | None = None):
        self.root = Path(root).resolve()
        self.packages_dir = Path(packages_dir).resolve()
        self.capability_store = capability_store

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
            capability_publications = state.get("capability_publications") or {}
            if (state.get("template_instance") or state.get("trusted_recipe")) and (not isinstance(mappings, dict) or set(mappings) != step_ids):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have complete Developer mappings.")
            if state.get("trusted_recipe") and any(not isinstance(value, dict) for value in mappings.values()):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have executable Developer mapping snapshots.")
            if state.get("template_instance") and any(not str(value).strip() for value in mappings.values()):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_MISSING", "The Creator design does not have complete Developer mappings.")
            if state.get("semantic_recipe") and (set(capability_publications) != step_ids or any(not isinstance(value, dict) for value in capability_publications.values())):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_UNRESOLVED", "Every semantic node must resolve to one trusted capability release.")
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
            self.RECURSIVE_PACKAGE_PROTOCOL
            if state.get("semantic_recipe") and package_boundary
            else self.CREATOR_PACKAGE_PROTOCOL
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
        if state.get("semantic_recipe"):
            expanded_publications = {
                f"{release['id']}@{release['revision']}": release
                for publication in capability_publications.values()
                for release in self._expand_release(publication)
            }
            lineage["semantic_recipe"] = {"id": state["semantic_recipe"]["id"], "digest": state["semantic_recipe"]["digest"]}
            lineage["capability_binding_digest"] = actual_candidate["capability_binding_digest"]
            lineage["capability_releases"] = [
                {key: publication[key] for key in ("id", "revision", "digest", "trust_scope")}
                for _, publication in sorted(capability_publications.items())
            ]
            lineage["capability_dependency_closure"] = [
                {key: publication[key] for key in ("id", "revision", "digest", "trust_scope")}
                for _, publication in sorted(expanded_publications.items())
            ]
        else:
            expanded_publications = {}
        root_flow = self._root_flow(
            instance,
            lineage,
            flow_protocol,
            mappings or {},
            trusted_recipe=state.get("trusted_recipe"),
            trusted_presets=state.get("trusted_presets") or [],
            semantic_recipe=state.get("semantic_recipe"),
            capability_publications=capability_publications,
        )
        findings = validate_execution_plan_v1_flow_contract(
            root_flow,
            protocol_id=flow_protocol["id"],
            protocol_version=flow_protocol["version"],
        )
        if findings:
            codes = ", ".join(sorted({str(item.get("code") or "unknown") for item in findings}))
            raise CreatorRuntimeBridgeError(
                "CREATOR_HANDOFF_TOPOLOGY_INCOMPATIBLE",
                f"Accepted semantic relationships cannot be represented as a valid CF-FARP Root Flow: {codes}.",
            )

        manifest = self._manifest(actual_candidate, lineage, flow_protocol, mappings or {}, expanded_publications)
        combined_dlc = self._combined_dlc_descriptor(expanded_publications, manifest["id"])
        if combined_dlc:
            manifest["portable_dlc"] = {"protocol": "CF-FARP@1.7", "descriptor": "dlc/descriptor.json"}
        release_inputs = release_archive_inputs(manifest)
        artifact_name = f"creator-{actual_candidate['id']}.cf-cre.zip"
        output = self.packages_dir / artifact_name
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="creator-handoff-", dir=self.packages_dir) as source_dir:
            source = Path(source_dir)
            self._write_json(source / "manifest.json", manifest)
            self._write_json(source / "root.flow.json", root_flow)
            self._write_json(
                source / "assets" / "registry.json",
                {"schema": "cartridgeflow.asset_registry.v1", "assets": []},
            )
            if combined_dlc:
                self._write_json(source / "dlc" / "descriptor.json", combined_dlc)
            for publication in expanded_publications.values():
                if (publication.get("implementation") or {}).get("kind") != "flow":
                    continue
                prefix = Path("capabilities") / publication["id"] / str(publication["revision"])
                for relative, content in sorted((publication["implementation"].get("files") or {}).items()):
                    target = source / prefix / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8", newline="")
                for relative, destination in self._dlc_file_destinations(publication).items():
                    content = publication["implementation"]["files"].get(relative)
                    if not isinstance(content, str):
                        raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_FILE_MISSING", f"Capability DLC file is missing: {relative}.")
                    target = source / destination
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8", newline="")
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

    def _manifest(self, candidate: dict, lineage: dict, flow_protocol: dict, mappings: dict, capability_publications: dict[str, dict] | None = None) -> dict:
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
            "tuning_contract": {
                "protocol": "CF-TUNING",
                "protocol_version": "1.5" if capability_publications else "1.0",
                "adapter": "cf-tuning.capability-cartridges.v1" if capability_publications else "cf-tuning.repository.v1",
                "binding": "recursive_capability_materialization" if capability_publications else "authoring_tuning",
            },
            "runtime": {"type": "composed_flow" if capability_publications else "handoff_only"},
            "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
            "asset_registry": "assets/registry.json",
            "inputs": [],
            "outputs": [],
            "delivery": {"primary_output": "handoff"},
            "delivery_readiness": {
                "level": "production",
                "certification_target": f"{flow_protocol['id']}@{flow_protocol['version']}",
                "notes": "Creator package was materialized from reviewed immutable capability releases.",
            },
            "creator_lineage": deepcopy(lineage),
        }

        trusted_mappings = [item for item in mappings.values() if isinstance(item, dict)]
        for publication in (capability_publications or {}).values():
            implementation = publication.get("implementation") or {}
            if implementation.get("kind") == "node_snapshot":
                trusted_mappings.append(implementation["mapping"])
                continue
            if implementation.get("kind") != "flow":
                continue
            requirements = {
                key: deepcopy(implementation["manifest"][key])
                for key in ("inputs", "outputs", "permissions", "mcp_tools", "resource_requirements", "llm_recipe", "artifacts")
                if key in implementation["manifest"]
            }
            prefix = f"capabilities/{publication['id']}/{publication['revision']}/"
            requirements = self._rewrite_package_paths(requirements, prefix, set((implementation.get("files") or {}).keys()))
            trusted_mappings.append({"requirements": requirements})
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

    def _root_flow(
        self, instance: dict, lineage: dict, flow_protocol: dict, mappings: dict, *,
        trusted_recipe: dict | None, trusted_presets: list[dict],
        semantic_recipe: dict | None = None, capability_publications: dict[str, dict] | None = None,
    ) -> dict:
        if semantic_recipe:
            return self._recursive_root_flow(instance, lineage, flow_protocol, semantic_recipe, capability_publications or {})
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

    def _recursive_root_flow(self, instance: dict, lineage: dict, flow_protocol: dict, semantic_recipe: dict, publications: dict[str, dict]) -> dict:
        steps = sorted(instance["blueprint"]["steps"], key=lambda item: item["id"])
        relationships = sorted(instance["blueprint"].get("relations", []), key=lambda item: item["id"])
        order = self._topological_order(steps, relationships)
        recipe_nodes = {item["id"]: item for item in semantic_recipe["nodes"]}
        predecessors: dict[str, list[str]] = {step_id: [] for step_id in order}
        for relation in relationships:
            predecessors[relation["to_step_id"]].append(relation["from_step_id"])

        states: dict[str, dict] = {
            "start": {"type": "control", "title": "Creator application start", "locked": True},
            "complete": {"type": "terminal", "title": "Creator application complete", "locked": True},
        }
        edges: list[dict] = []
        step_outputs: dict[str, dict[str, dict]] = {}
        segment_entries: list[str] = []
        segment_exits: list[str] = []
        nested_releases: list[dict] = []

        for step_id in order:
            publication = publications.get(step_id)
            if not isinstance(publication, dict):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_UNRESOLVED", f"Semantic node {step_id} has no capability release.")
            expanded = self._expand_release(publication)
            upstream: dict[str, dict] = {}
            for predecessor in predecessors[step_id]:
                for port_id, output in step_outputs.get(predecessor, {}).items():
                    existing = upstream.get(port_id)
                    if existing is not None and existing != output:
                        raise CreatorRuntimeBridgeError(
                            "CREATOR_HANDOFF_CAPABILITY_INPUT_AMBIGUOUS",
                            f"More than one predecessor provides capability port {port_id}.",
                        )
                    upstream[port_id] = output
            current_entry = ""
            current_exit = ""
            direct_outputs: dict[str, dict] = {}
            for child_index, release in enumerate(expanded):
                validate_capability_release(release)
                suffix = step_id if child_index == len(expanded) - 1 else f"{step_id}.dependency.{child_index + 1}"
                implementation = release["implementation"]
                values = instance["bindings"].get(step_id, {}) if release["digest"] == publication["digest"] else {
                    field["id"]: deepcopy(field["default"]) for field in release["creator"]["editable_fields"]
                }
                if implementation["kind"] == "node_snapshot":
                    preset = implementation["preset"]
                    try:
                        state = materialize_trusted_node_state(implementation["mapping"], preset, values)
                    except AuthoringServiceError as exc:
                        raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_MAPPING_INVALID", str(exc)) from exc
                    node_id = f"cap.{suffix}.node"
                    state["title"] = recipe_nodes[step_id]["creator_label"]
                    state["display_name"] = recipe_nodes[step_id]["creator_label"]
                    state["capability_release"] = {key: release[key] for key in ("id", "revision", "digest", "trust_scope")}
                    states[node_id] = state
                    entry, exit_id, outputs = node_id, node_id, {}
                else:
                    child_states, child_edges, entry, exit_id, outputs = self._inline_flow_release(
                        release, suffix, values, upstream,
                    )
                    for state_id, state in child_states.items():
                        if state_id in states:
                            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_NAMESPACE_CONFLICT", f"Capability state namespace collided at {state_id}.")
                        states[state_id] = state
                    edges.extend(child_edges)
                nested_releases.append({key: release[key] for key in ("id", "revision", "digest", "trust_scope")})
                if current_exit:
                    edges.append({"id": f"compose.{suffix}.{child_index:03d}", "kind": "sequence", "from": current_exit, "to": entry})
                else:
                    current_entry = entry
                current_exit = exit_id
                upstream = outputs or upstream
                if release["digest"] == publication["digest"]:
                    direct_outputs = outputs
            segment_entries.append(current_entry)
            segment_exits.append(current_exit)
            step_outputs[step_id] = direct_outputs

        edges.append({"id": "compose.application.start", "kind": "sequence", "from": "start", "to": segment_entries[0]})
        for index in range(len(segment_exits) - 1):
            edges.append({"id": f"compose.application.{index:03d}", "kind": "sequence", "from": segment_exits[index], "to": segment_entries[index + 1]})
        outgoing_steps = {relation["from_step_id"] for relation in relationships}
        sink_steps = [step_id for step_id in order if step_id not in outgoing_steps]
        application_outputs = [
            {
                "node_id": step_id,
                "port_id": port_id,
                "store_key": output["store_key"],
                "schema": deepcopy(output["schema"]),
            }
            for step_id in sink_steps
            for port_id, output in sorted(step_outputs.get(step_id, {}).items())
        ]
        if application_outputs:
            output_keys = [item["store_key"] for item in application_outputs]
            delivery_state = {
                "type": "process",
                "kind": "delivery",
                "executor": "deterministic",
                "effect": "writes_store",
                "action": "pass_result",
                "title": "Package application result",
                "input": ",".join(output_keys),
                "output": "handoff",
                "primary_output": "handoff",
                "outputs": {
                    "handoff": {
                        "schema": deepcopy(application_outputs[0]["schema"]) if len(application_outputs) == 1 else {"type": "object"},
                        "target": {"type": "store", "key": "handoff"},
                    }
                },
                "params": {
                    "input": output_keys[0],
                    "output": "handoff",
                    **(
                        {"preset_config": {"items": ",".join(output_keys), "output_name": "handoff"}}
                        if len(output_keys) > 1
                        else {}
                    ),
                },
                "locked": True,
            }
            states["application_delivery"] = delivery_state
            states["application_failed"] = {
                "type": "terminal",
                "title": "Package application failed",
                "locked": True,
            }
            edges.append({"id": "compose.application.delivery", "kind": "sequence", "from": segment_exits[-1], "to": "application_delivery"})
            edges.append({"id": "compose.application.complete", "kind": "sequence", "from": "application_delivery", "to": "complete"})
            edges.append({
                "id": "compose.application.delivery-failed",
                "kind": "failure",
                "from": "application_delivery",
                "to": "application_failed",
                "failure": {
                    "id": "application.delivery.failure",
                    "causes": ["cancelled", "exception", "resource", "retry_exhausted", "timeout", "validation"],
                },
            })
        else:
            edges.append({"id": "compose.application.complete", "kind": "sequence", "from": segment_exits[-1], "to": "complete"})
        return {
            "schema_version": "1.0",
            "id": f"creator-{lineage['compile_candidate']['digest'][:24]}.root",
            "mode": "lifecycle",
            "protocol": deepcopy(flow_protocol),
            "start": "start",
            "states": states,
            "execution_plan": {"schema": "cartridgeflow.execution_plan.v1", "entry": "start", "edges": edges},
            "semantic_relationships": [{key: relation[key] for key in ("id", "from_step_id", "to_step_id", "relation")} for relation in relationships],
            "capability_materialization": {
                "schema": "cartridgeflow.recursive_capability_materialization.v1",
                "strategy": "deterministic_namespace_expansion",
                "releases": nested_releases,
                "application_outputs": application_outputs,
            },
            "creator_lineage": deepcopy(lineage),
        }

    def _expand_release(self, release: dict) -> list[dict]:
        dependencies = release.get("dependencies") or []
        if not dependencies:
            return [release]
        if self.capability_store is None:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DEPENDENCY_STORE_REQUIRED", "Recursive capability dependencies require the shared capability registry.")
        expanded: list[dict] = []
        visiting: set[tuple[str, int]] = set()
        expanded_keys: set[tuple[str, int]] = set()

        def visit(item: dict) -> None:
            key = (item["id"], item["revision"])
            if key in visiting:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DEPENDENCY_CYCLE", "Capability dependency graph contains a cycle.")
            if key in expanded_keys:
                return
            visiting.add(key)
            for ref in item.get("dependencies") or []:
                dependency = self.capability_store.get(ref["id"], ref["revision"])
                if dependency["digest"] != ref["digest"]:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DEPENDENCY_DIGEST_MISMATCH", "Capability dependency digest is invalid.")
                visit(dependency)
            visiting.remove(key)
            expanded.append(item)
            expanded_keys.add(key)

        visit(release)
        return expanded

    def _inline_flow_release(self, release: dict, instance_id: str, values: dict, upstream: dict[str, dict]) -> tuple[dict, list[dict], str, str, dict[str, dict]]:
        implementation = release["implementation"]
        root_flow = deepcopy(implementation["root_flow"])
        for field_id, path in implementation.get("creator_bindings", {}).items():
            if field_id not in values:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_VALUE_MISSING", f"Capability field {field_id} has no Creator value.")
            self._set_path(root_flow, path, deepcopy(values[field_id]))
        plan = root_flow.get("execution_plan")
        states = root_flow.get("states")
        if not isinstance(plan, dict) or plan.get("schema") != "cartridgeflow.execution_plan.v1" or not isinstance(states, dict):
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_FLOW_INVALID", "Capability Flow must declare an execution-plan Root Flow.")
        entry = str(plan.get("entry") or "")
        if entry not in states:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_FLOW_INVALID", "Capability Flow entry is invalid.")
        raw_edges = [item for item in plan.get("edges") or [] if isinstance(item, dict)]
        failure_targets = {str(item.get("to") or "") for item in raw_edges if item.get("kind") == "failure"}
        success_terminals = [state_id for state_id, state in states.items() if isinstance(state, dict) and state.get("type") == "terminal" and state_id not in failure_targets]
        if len(success_terminals) != 1:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_BOUNDARY_INVALID", "Capability Flow must expose exactly one successful exit.")
        success_exit = success_terminals[0]
        id_map = {state_id: f"cap.{instance_id}.{state_id}" for state_id in states}
        prefix = f"cap.{instance_id}."
        input_ports = release["interface"]["inputs"]
        output_ports = release["interface"]["outputs"]
        store_map: dict[str, str] = {}
        for port in input_ports:
            source = upstream.get(port["id"])
            if source is None and len(input_ports) == 1 and len(upstream) == 1:
                source = next(iter(upstream.values()))
            if source is None and port["required"]:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_INPUT_UNBOUND", f"Capability input {port['id']} has no upstream output.")
            if source is not None:
                if source["schema"] != port["schema"]:
                    raise CreatorRuntimeBridgeError(
                        "CREATOR_HANDOFF_CAPABILITY_SCHEMA_MISMATCH",
                        f"Capability input {port['id']} is incompatible with its upstream output.",
                    )
                store_map[port["store_key"]] = source["store_key"]
        outputs = {
            port["id"]: {
                "store_key": store_map.get(port["store_key"], f"{prefix}{port['store_key']}"),
                "schema": deepcopy(port["schema"]),
            }
            for port in output_ports
        }
        store_map.update({port["store_key"]: outputs[port["id"]]["store_key"] for port in output_ports})
        file_prefix = f"capabilities/{release['id']}/{release['revision']}/"
        file_paths = set((implementation.get("files") or {}).keys())
        normalized_states: dict[str, dict] = {}
        ref = {key: release[key] for key in ("id", "revision", "digest", "trust_scope")}
        for state_id, raw_state in states.items():
            state = self._rewrite_flow_value(deepcopy(raw_state), id_map, store_map, prefix, file_prefix, file_paths)
            if state_id == success_exit:
                state = {"type": "control", "title": f"{release['creator']['label']} exit", "locked": True}
            state["capability_release"] = deepcopy(ref)
            normalized_states[id_map[state_id]] = state
        normalized_edges = []
        for index, raw_edge in enumerate(raw_edges):
            edge = self._rewrite_flow_value(deepcopy(raw_edge), id_map, store_map, prefix, file_prefix, file_paths)
            edge["id"] = f"cap.{instance_id}.edge.{index:03d}.{str(raw_edge.get('id') or 'edge')}"
            edge["from"] = id_map[str(raw_edge.get("from"))]
            edge["to"] = id_map[str(raw_edge.get("to"))]
            normalized_edges.append(edge)
        return normalized_states, normalized_edges, id_map[entry], id_map[success_exit], outputs

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

    @classmethod
    def _rewrite_flow_value(
        cls, value: object, id_map: dict[str, str], store_map: dict[str, str], store_prefix: str,
        file_prefix: str, file_paths: set[str], parent_key: str = "",
    ) -> object:
        if isinstance(value, list):
            return [cls._rewrite_flow_value(item, id_map, store_map, store_prefix, file_prefix, file_paths, parent_key) for item in value]
        if isinstance(value, str):
            normalized = value.replace("\\", "/")
            if normalized in file_paths:
                return f"{file_prefix}{normalized}"
            if value.startswith("store:"):
                key = value[6:]
                return "store:" + store_map.setdefault(key, f"{store_prefix}{key}")
            if parent_key in {"node_id", "target_node", "entry", "from", "to"} and value in id_map:
                return id_map[value]
            if parent_key in {"input", "output", "primary_output", "output_name", "from", "to", "source", "items"}:
                keys = [item.strip() for item in value.split(",") if item.strip()]
                if keys and all(key in store_map for key in keys):
                    return ",".join(store_map[key] for key in keys)
                return store_map.get(value, value)
            return value
        if not isinstance(value, dict):
            return value
        result = {
            key: cls._rewrite_flow_value(item, id_map, store_map, store_prefix, file_prefix, file_paths, key)
            for key, item in value.items()
        }
        if result.get("source") == "store" or result.get("type") == "store":
            key = result.get("key")
            if isinstance(key, str):
                result["key"] = store_map.setdefault(key, f"{store_prefix}{key}")
        if parent_key in {"fork", "join", "loop", "batch", "failure"} and isinstance(result.get("id"), str):
            result["id"] = f"{store_prefix}{result['id']}"
        return result

    @classmethod
    def _rewrite_package_paths(cls, value: object, prefix: str, file_paths: set[str]) -> object:
        if isinstance(value, list):
            return [cls._rewrite_package_paths(item, prefix, file_paths) for item in value]
        if isinstance(value, dict):
            return {key: cls._rewrite_package_paths(item, prefix, file_paths) for key, item in value.items()}
        if isinstance(value, str) and value.replace("\\", "/") in file_paths:
            return prefix + value.replace("\\", "/")
        return value

    @classmethod
    def _combined_dlc_descriptor(cls, publications: dict[str, dict], owner_cartridge: str) -> dict | None:
        tools: dict[tuple[str, str], dict] = {}
        protocols: list[dict] = []
        resources: list[dict] = []
        files: dict[str, dict] = {}
        for publication in publications.values():
            implementation = publication.get("implementation") or {}
            if implementation.get("kind") != "flow":
                continue
            manifest = implementation.get("manifest") or {}
            portable = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else None
            if not portable:
                continue
            descriptor_path = str(portable.get("descriptor") or "").replace("\\", "/")
            source_files = implementation.get("files") or {}
            raw_descriptor = source_files.get(descriptor_path)
            if not isinstance(raw_descriptor, str):
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_DESCRIPTOR_MISSING", f"Capability {publication['id']} does not carry its DLC descriptor.")
            try:
                descriptor = json.loads(raw_descriptor)
            except json.JSONDecodeError as exc:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_DESCRIPTOR_INVALID", f"Capability {publication['id']} DLC descriptor is invalid.") from exc
            if descriptor.get("schema") != "cartridgeflow.portable_dlc.v3":
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_DESCRIPTOR_UNSUPPORTED", "Recursive capability packaging requires portable DLC descriptor v3.")
            path_map = cls._dlc_file_destinations(publication)
            for raw_tool in descriptor.get("tools") or []:
                tool = cls._replace_exact_paths(deepcopy(raw_tool), path_map)
                identity = (str(tool.get("server") or ""), str(tool.get("tool") or ""))
                if not all(identity):
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_DESCRIPTOR_INVALID", "Capability DLC tool identity is incomplete.")
                existing = tools.get(identity)
                if existing is not None and existing != tool:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_TOOL_CONFLICT", f"Capability DLC tool conflict: {identity[0]}/{identity[1]}.")
                tools[identity] = tool
            for item in descriptor.get("protocols") or []:
                rewritten = cls._replace_exact_paths(deepcopy(item), path_map)
                if rewritten not in protocols:
                    protocols.append(rewritten)
            for item in descriptor.get("resources") or []:
                if item.get("ownership") != "package":
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_RESOURCE_SCOPE_INVALID", "Capability DLC may carry only package-owned resources into a composed application.")
                rewritten = {"path": "dlc", "ownership": "package"}
                if rewritten not in resources:
                    resources.append(rewritten)
            for item in descriptor.get("files") or []:
                source_path = str(item.get("path") or "").replace("\\", "/")
                if source_path not in path_map:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_FILE_MISSING", f"Capability DLC descriptor references an undeclared file: {source_path}.")
                rewritten = deepcopy(item)
                rewritten["path"] = path_map[source_path]
                existing = files.get(rewritten["path"])
                if existing is not None and existing != rewritten:
                    raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_DLC_FILE_CONFLICT", f"Capability DLC file conflict: {rewritten['path']}.")
                files[rewritten["path"]] = rewritten
        if not tools and not files:
            return None
        return {
            "schema": "cartridgeflow.portable_dlc.v3",
            "id": "dlc.creator.composed",
            "version": "1.0.0",
            "owner_cartridge": owner_cartridge,
            "scope": "cartridge",
            "tools": [tools[key] for key in sorted(tools)],
            "protocols": protocols,
            "resources": resources,
            "files": [files[key] for key in sorted(files)],
        }

    @classmethod
    def _dlc_file_destinations(cls, publication: dict) -> dict[str, str]:
        implementation = publication.get("implementation") or {}
        manifest = implementation.get("manifest") or {}
        portable = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else None
        if not portable:
            return {}
        descriptor_path = str(portable.get("descriptor") or "").replace("\\", "/")
        raw = (implementation.get("files") or {}).get(descriptor_path)
        if not isinstance(raw, str):
            return {}
        try:
            descriptor = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        namespace = f"{publication['id']}.{publication['revision']}"
        result: dict[str, str] = {}
        for item in descriptor.get("files") or []:
            source = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            if source.startswith("dlc/mcp_nodes/"):
                destination = f"dlc/mcp_nodes/{namespace}/{source.removeprefix('dlc/mcp_nodes/')}"
            elif source.startswith("dlc/backend/"):
                destination = f"dlc/backend/{namespace}/{source.removeprefix('dlc/backend/')}"
            elif source.startswith("dlc/protocols/"):
                destination = f"dlc/protocols/{namespace}/{source.removeprefix('dlc/protocols/')}"
            else:
                destination = f"dlc/resources/{namespace}/{source.removeprefix('dlc/')}"
            result[source] = destination
        return result

    @classmethod
    def _replace_exact_paths(cls, value: object, path_map: dict[str, str]) -> object:
        if isinstance(value, list):
            return [cls._replace_exact_paths(item, path_map) for item in value]
        if isinstance(value, dict):
            return {key: cls._replace_exact_paths(item, path_map) for key, item in value.items()}
        if isinstance(value, str):
            return path_map.get(value.replace("\\", "/"), value)
        return value

    @staticmethod
    def _set_path(value: dict, path: str, item: object) -> None:
        current: object = value
        parts = path.split(".")
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                next_value = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                next_value = current[int(part)]
            else:
                raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_BINDING_INVALID", f"Capability binding path is invalid: {path}.")
            current = next_value
        leaf = parts[-1]
        if isinstance(current, dict) and leaf in current:
            current[leaf] = item
            return
        if isinstance(current, list) and leaf.isdigit() and int(leaf) < len(current):
            current[int(leaf)] = item
            return
        else:
            raise CreatorRuntimeBridgeError("CREATOR_HANDOFF_CAPABILITY_BINDING_INVALID", f"Capability binding path is invalid: {path}.")

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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    @staticmethod
    def _digest_json(value: dict) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
