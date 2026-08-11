"""Fail-closed creator authoring sessions built on immutable authoring facts."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Any, Awaitable, Callable

from core.protocol.authoring_contract import (
    accept_change_set, canonical_digest, create_recipe_blueprint,
    create_recipe_instance, freeze_snapshot, propose_change_set, validate_freeze_snapshot,
    TRUSTED_NODE_AUTHORING_PROTOCOL, CAPABILITY_AUTHORING_PROTOCOL,
)
from core.protocol.base_manifest import load_base_implementation, supports_subprotocol_release
from core.protocol.release_catalog import load_protocol_release_catalog
from core.protocol.capability_registry import ProtocolRegistry
from core.protocol.authoring_contract import _OPERATIONS, _affected_step_ids, _apply_change
from core.protocol.tuning import TuningProtocolError
from core.protocol.creator_templates import create_instance as create_template_instance, creator_blueprint_from_instance
from core.protocol.trusted_node_recipes import (
    creator_recipe_projection,
    validate_dynamic_recipe,
    validate_node_values,
    validate_preset,
)
from core.protocol.capability_cartridges import (
    CapabilityCartridgeError,
    SEMANTIC_RECIPE_SCHEMA,
    resolve_semantic_recipe,
    semantic_recipe_projection,
    validate_capability_release,
    validate_values_for_node,
    capability_compatible_with_recipe_node,
)
from core.protocol.clean_authoring import CleanAuthoringProjector
from core.llm.authoring import AuthoringProposalError, build_authoring_messages, parse_authoring_proposal

SERVICE_AUTHORING_OPERATIONS = frozenset(_OPERATIONS)


class AuthoringServiceError(ValueError):
    """Stable authoring-service error, suitable for creator and developer APIs."""

    def __init__(self, code: str, message: str, *, status: int = 400):
        self.code, self.status = code, status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"schema": "cartridgeflow.authoring_error.v1", "code": self.code, "message": str(self)}


class AuthoringSessionStore:
    """Small atomic JSON store. Chat transcripts deliberately never enter it."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def create(self, session_id: str, recipe_id: str, intent: str, steps: list[dict], sources: list[dict], bindings: dict, project_id: str | None = None, relations: list[dict] | None = None, protocol: dict | None = None) -> dict:
        with self._lock:
            path = self._path(session_id)
            if path.exists():
                raise AuthoringServiceError("AUTHORING_SESSION_EXISTS", "Authoring session already exists.", status=409)
            project_id = project_id or session_id
            self._validate_identifier(project_id, "PROJECT")
            if self._state_for_project_id(project_id) is not None:
                raise AuthoringServiceError("AUTHORING_PROJECT_EXISTS", "A project already owns an authoring session.", status=409)
            try:
                blueprint = create_recipe_blueprint(recipe_id, intent, steps, sources, relations, protocol=protocol)
                instance = create_recipe_instance(blueprint, bindings)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state = {"schema": "cartridgeflow.authoring_session.v1", "id": session_id, "project_id": project_id,
                     "head": instance, "instances": {instance["id"]: instance}, "history": [], "proposals": {}, "rejections": [], "freezes": [], "freeze_replacements": [], "freeze_revisions": [], "reversals": []}
            self._write(path, state)
            return self.creator_projection(state)

    def create_from_recipe(self, session_id: str, project_id: str, recipe: dict, presets: list[dict], sources: list[dict] | None = None, *, mappings: dict[str, dict] | None = None) -> dict:
        """Create one Creator session from a server-resolved dynamic trusted recipe."""
        recipe, normalized_presets, executable_mappings = self._prepare_trusted_recipe(recipe, presets, mappings)
        steps = [{"id": item["id"], "intent": item["creator_label"], "inputs": {}, "outputs": {}} for item in recipe["nodes"]]
        relations = [{"id": item["id"], "from_step_id": item["from_node_id"], "to_step_id": item["to_node_id"], "relation": item["relation"]} for item in recipe["relations"]]
        bindings = {item["id"]: deepcopy(item["values"]) for item in recipe["nodes"]}
        with self._lock:
            path = self._path(session_id)
            if path.exists():
                raise AuthoringServiceError("AUTHORING_SESSION_EXISTS", "Authoring session already exists.", status=409)
            self._validate_identifier(project_id, "PROJECT")
            if self._state_for_project_id(project_id) is not None:
                raise AuthoringServiceError("AUTHORING_PROJECT_EXISTS", "A project already owns an authoring session.", status=409)
            try:
                blueprint = create_recipe_blueprint(recipe["id"], recipe["goal"], steps, list(sources or []), relations, protocol=TRUSTED_NODE_AUTHORING_PROTOCOL)
                instance = create_recipe_instance(blueprint, bindings)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state = {
                "schema": "cartridgeflow.authoring_session.v1", "id": session_id, "project_id": project_id,
                "head": instance, "instances": {instance["id"]: instance}, "history": [], "proposals": {},
                "rejections": [], "freezes": [], "freeze_replacements": [], "freeze_revisions": [], "reversals": [],
                "trusted_recipe": deepcopy(recipe), "trusted_presets": deepcopy(normalized_presets),
                "developer_mappings": deepcopy(executable_mappings),
                "developer_confirmation": None,
            }
            self._write(path, state)
            return self.creator_projection(state)

    def create_from_semantic_recipe(self, session_id: str, project_id: str, recipe: dict, publications: dict[str, dict]) -> dict:
        """Create a Creator session even when some semantic nodes are unresolved."""
        recipe, publications = self._prepare_semantic_recipe(recipe, publications)
        steps = [{"id": item["id"], "intent": item["creator_label"], "inputs": {}, "outputs": {}} for item in recipe["nodes"]]
        relations = [{"id": item["id"], "from_step_id": item["from_node_id"], "to_step_id": item["to_node_id"], "relation": item["relation"]} for item in recipe["relations"]]
        bindings = {item["id"]: deepcopy(item["values"]) for item in recipe["nodes"]}
        with self._lock:
            path = self._path(session_id)
            if path.exists():
                raise AuthoringServiceError("AUTHORING_SESSION_EXISTS", "Authoring session already exists.", status=409)
            self._validate_identifier(project_id, "PROJECT")
            if self._state_for_project_id(project_id) is not None:
                raise AuthoringServiceError("AUTHORING_PROJECT_EXISTS", "A project already owns an authoring session.", status=409)
            try:
                blueprint = create_recipe_blueprint(recipe["id"], recipe["goal"], steps, [], relations, protocol=CAPABILITY_AUTHORING_PROTOCOL)
                instance = create_recipe_instance(blueprint, bindings)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state = {
                "schema": "cartridgeflow.authoring_session.v1", "id": session_id, "project_id": project_id,
                "head": instance, "instances": {instance["id"]: instance}, "history": [], "proposals": {},
                "rejections": [], "freezes": [], "freeze_replacements": [], "freeze_revisions": [], "reversals": [],
                "semantic_recipe": deepcopy(recipe), "capability_publications": deepcopy(publications),
                "capability_reviews": {}, "capability_rejections": {}, "resolution_revision": 1,
            }
            self._write(path, state)
            return self.creator_projection(state)

    def replace_from_semantic_recipe(self, session_id: str, recipe: dict, publications: dict[str, dict], *, expected_revision: int) -> dict:
        recipe, publications = self._prepare_semantic_recipe(recipe, publications)
        steps = [{"id": item["id"], "intent": item["creator_label"], "inputs": {}, "outputs": {}} for item in recipe["nodes"]]
        relations = [{"id": item["id"], "from_step_id": item["from_node_id"], "to_step_id": item["to_node_id"], "relation": item["relation"]} for item in recipe["relations"]]
        bindings = {item["id"]: deepcopy(item["values"]) for item in recipe["nodes"]}
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            try:
                blueprint = create_recipe_blueprint(recipe["id"], recipe["goal"], steps, [], relations, protocol=CAPABILITY_AUTHORING_PROTOCOL)
                instance = create_recipe_instance(blueprint, bindings, revision=state["head"]["revision"] + 1, parent_instance=state["head"])
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state["head"] = instance
            state["instances"][instance["id"]] = instance
            state["semantic_recipe"] = deepcopy(recipe)
            state["capability_publications"] = deepcopy(publications)
            state["capability_reviews"] = {}
            state["capability_rejections"] = {}
            state["resolution_revision"] = int(state.get("resolution_revision") or 0) + 1
            state["proposals"] = {}
            state["freezes"] = []
            state["freeze_replacements"] = []
            state["freeze_revisions"] = []
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    @staticmethod
    def _prepare_semantic_recipe(recipe: dict, publications: dict[str, dict]) -> tuple[dict, dict[str, dict]]:
        if not isinstance(recipe, dict) or recipe.get("schema") != SEMANTIC_RECIPE_SCHEMA:
            raise AuthoringServiceError("AUTHORING_SEMANTIC_RECIPE_INVALID", "Semantic recipe schema is invalid.")
        digest = recipe.get("digest")
        if digest != canonical_digest({key: value for key, value in recipe.items() if key != "digest"}):
            raise AuthoringServiceError("AUTHORING_SEMANTIC_RECIPE_INVALID", "Semantic recipe integrity check failed.")
        normalized: dict[str, dict] = {}
        raw_publications = publications if isinstance(publications, dict) else {}
        try:
            for node in recipe.get("nodes") or []:
                ref = node.get("capability")
                publication = raw_publications.get(node.get("id"))
                if ref is None:
                    if publication is not None:
                        raise AuthoringServiceError("AUTHORING_CAPABILITY_BINDING_INVALID", "Unresolved semantic node cannot carry an implementation publication.")
                    continue
                item = validate_capability_release(publication)
                actual_ref = {key: item[key] for key in ("id", "revision", "digest", "trust_scope")}
                if actual_ref != ref:
                    raise AuthoringServiceError("AUTHORING_CAPABILITY_BINDING_INVALID", "Semantic node capability reference does not match its publication.")
                normalized[node["id"]] = item
        except CapabilityCartridgeError as exc:
            raise AuthoringServiceError("AUTHORING_CAPABILITY_BINDING_INVALID", str(exc)) from exc
        return deepcopy(recipe), normalized

    def resolve_capabilities(self, session_id: str, capabilities: list[dict], *, expected_revision: int) -> tuple[dict, list[str]]:
        """Re-resolve the same semantic nodes against current trusted releases."""
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            recipe = state.get("semantic_recipe")
            if not isinstance(recipe, dict):
                raise AuthoringServiceError("AUTHORING_SEMANTIC_RECIPE_REQUIRED", "This project does not use semantic capability resolution.", status=409)
            try:
                rejected_digests = {
                    node_id: {
                        str(item.get("digest") or "")
                        for item in records
                        if isinstance(item, dict) and item.get("digest")
                    }
                    for node_id, records in (state.get("capability_rejections") or {}).items()
                    if isinstance(records, list)
                }
                next_recipe, publications, resolved = resolve_semantic_recipe(
                    recipe,
                    capabilities,
                    rejected_capability_digests=rejected_digests,
                )
            except CapabilityCartridgeError as exc:
                raise AuthoringServiceError("AUTHORING_CAPABILITY_RESOLUTION_INVALID", str(exc)) from exc
            if not resolved:
                return self.creator_projection(state), []
            nodes = {item["id"]: item for item in next_recipe["nodes"]}
            bindings = deepcopy(state["head"]["bindings"])
            for node_id in resolved:
                try:
                    bindings[node_id] = validate_values_for_node(nodes[node_id], publications[node_id], bindings.get(node_id, {}))
                except CapabilityCartridgeError as exc:
                    raise AuthoringServiceError("AUTHORING_CAPABILITY_RESOLUTION_INVALID", str(exc)) from exc
            try:
                instance = create_recipe_instance(
                    state["head"]["blueprint"], bindings,
                    revision=state["head"]["revision"] + 1, parent_instance=state["head"],
                )
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state["head"] = instance
            state["instances"][instance["id"]] = instance
            state["semantic_recipe"] = next_recipe
            state["capability_publications"] = publications
            state["resolution_revision"] = int(state.get("resolution_revision") or 0) + 1
            state["proposals"] = {}
            self._write(self._path(session_id), state)
            return self.creator_projection(state), resolved

    def bind_capability(self, project_id: str, node_id: str, release: dict) -> dict:
        """Bind a just-published capability to the exact Creator gap that opened Developer."""
        with self._lock:
            state = self.get_by_project_id(project_id)
            recipe = deepcopy(state.get("semantic_recipe"))
            if not isinstance(recipe, dict):
                raise AuthoringServiceError(
                    "AUTHORING_SEMANTIC_RECIPE_REQUIRED",
                    "The target project does not use semantic capability resolution.",
                    status=409,
                )
            node = next((item for item in recipe.get("nodes") or [] if item.get("id") == node_id), None)
            if node is None:
                raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "The target Creator node was not found.", status=404)
            try:
                publication = validate_capability_release(release)
                publications = deepcopy(state.get("capability_publications") or {})
                compatibility = capability_compatible_with_recipe_node(recipe, node_id, publication, publications)
                if not compatibility["compatible"]:
                    raise AuthoringServiceError(
                        "AUTHORING_CAPABILITY_INTERFACE_INCOMPATIBLE",
                        "The published capability does not satisfy the adjacent node data contracts.",
                        status=409,
                    )
                node["capability"] = {
                    key: publication[key] for key in ("id", "revision", "digest", "trust_scope")
                }
                node["values"] = validate_values_for_node(node, publication, state["head"]["bindings"].get(node_id, {}))
            except CapabilityCartridgeError as exc:
                raise AuthoringServiceError("AUTHORING_CAPABILITY_BINDING_INVALID", str(exc), status=409) from exc
            recipe["digest"] = canonical_digest({key: value for key, value in recipe.items() if key != "digest"})
            publications[node_id] = publication
            bindings = deepcopy(state["head"]["bindings"])
            bindings[node_id] = deepcopy(node["values"])
            try:
                instance = create_recipe_instance(
                    state["head"]["blueprint"],
                    bindings,
                    revision=state["head"]["revision"] + 1,
                    parent_instance=state["head"],
                )
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state["head"] = instance
            state["instances"][instance["id"]] = instance
            state["semantic_recipe"] = recipe
            state["capability_publications"] = publications
            state["resolution_revision"] = int(state.get("resolution_revision") or 0) + 1
            state["proposals"] = {}
            state.setdefault("capability_bindings", []).append({
                "node_id": node_id,
                "capability_id": publication["id"],
                "revision": publication["revision"],
                "digest": publication["digest"],
                "binding": "developer_exact_target",
            })
            self._write(self._path(state["id"]), state)
            return self.creator_projection(state)

    def validate_capability_binding(self, project_id: str, node_id: str, release: dict) -> dict:
        """Validate an exact Creator target without changing the project."""
        with self._lock:
            state = self.get_by_project_id(project_id)
            recipe = state.get("semantic_recipe")
            if not isinstance(recipe, dict):
                raise AuthoringServiceError(
                    "AUTHORING_SEMANTIC_RECIPE_REQUIRED",
                    "The target project does not use semantic capability resolution.",
                    status=409,
                )
            node = next((item for item in recipe.get("nodes") or [] if item.get("id") == node_id), None)
            if node is None:
                raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "The target Creator node was not found.", status=404)
            try:
                publication = validate_capability_release(release)
                compatibility = capability_compatible_with_recipe_node(
                    recipe,
                    node_id,
                    publication,
                    state.get("capability_publications") or {},
                )
            except CapabilityCartridgeError as exc:
                raise AuthoringServiceError("AUTHORING_CAPABILITY_BINDING_INVALID", str(exc), status=409) from exc
            if not compatibility["compatible"]:
                raise AuthoringServiceError(
                    "AUTHORING_CAPABILITY_INTERFACE_INCOMPATIBLE",
                    "The published capability does not satisfy the adjacent node data contracts.",
                    status=409,
                )
            return compatibility

    def reject_capability(self, session_id: str, node_id: str, *, expected_revision: int) -> dict:
        """Return one proposed capability binding to an unresolved node in place."""
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            recipe = deepcopy(state.get("semantic_recipe"))
            if not isinstance(recipe, dict):
                raise AuthoringServiceError("AUTHORING_SEMANTIC_RECIPE_REQUIRED", "This project does not use semantic capability resolution.", status=409)
            node = next((item for item in recipe.get("nodes") or [] if item.get("id") == node_id), None)
            if node is None:
                raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "Semantic recipe node was not found.", status=404)
            publications = deepcopy(state.get("capability_publications") or {})
            release = publications.pop(node_id, None)
            if not isinstance(release, dict):
                raise AuthoringServiceError("AUTHORING_CAPABILITY_UNRESOLVED", "This node has no capability binding to reject.", status=409)

            node["capability"] = None
            node["values"] = validate_values_for_node(node, None, {})
            recipe["digest"] = canonical_digest({key: value for key, value in recipe.items() if key != "digest"})
            bindings = deepcopy(state["head"]["bindings"])
            bindings[node_id] = deepcopy(node["values"])
            try:
                instance = create_recipe_instance(
                    state["head"]["blueprint"],
                    bindings,
                    revision=state["head"]["revision"] + 1,
                    parent_instance=state["head"],
                )
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc

            rejected = state.setdefault("capability_rejections", {}).setdefault(node_id, [])
            rejection = {key: release[key] for key in ("id", "revision", "digest")}
            if rejection not in rejected:
                rejected.append(rejection)
            state["head"] = instance
            state["instances"][instance["id"]] = instance
            state["semantic_recipe"] = recipe
            state["capability_publications"] = publications
            state.setdefault("capability_reviews", {}).pop(node_id, None)
            state["resolution_revision"] = int(state.get("resolution_revision") or 0) + 1
            state["proposals"] = {}
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    def replace_from_recipe(self, session_id: str, recipe: dict, presets: list[dict], *, mappings: dict[str, dict] | None, expected_revision: int) -> dict:
        """Atomically replace the current overall draft while preserving project identity."""
        recipe, normalized_presets, executable_mappings = self._prepare_trusted_recipe(recipe, presets, mappings)
        steps = [{"id": item["id"], "intent": item["creator_label"], "inputs": {}, "outputs": {}} for item in recipe["nodes"]]
        relations = [{"id": item["id"], "from_step_id": item["from_node_id"], "to_step_id": item["to_node_id"], "relation": item["relation"]} for item in recipe["relations"]]
        bindings = {item["id"]: deepcopy(item["values"]) for item in recipe["nodes"]}
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            try:
                blueprint = create_recipe_blueprint(recipe["id"], recipe["goal"], steps, [], relations, protocol=TRUSTED_NODE_AUTHORING_PROTOCOL)
                instance = create_recipe_instance(
                    blueprint,
                    bindings,
                    revision=state["head"]["revision"] + 1,
                    parent_instance=state["head"],
                )
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state["head"] = instance
            state["instances"][instance["id"]] = instance
            state["trusted_recipe"] = deepcopy(recipe)
            state["trusted_presets"] = deepcopy(normalized_presets)
            state["developer_mappings"] = deepcopy(executable_mappings)
            state["developer_confirmation"] = None
            state["proposals"] = {}
            state["freezes"] = []
            state["freeze_replacements"] = []
            state["freeze_revisions"] = []
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    @staticmethod
    def _prepare_trusted_recipe(recipe: dict, presets: list[dict], mappings: dict[str, dict] | None) -> tuple[dict, list[dict], dict[str, dict]]:
        try:
            normalized_presets = [validate_preset(item) for item in presets]
            recipe = validate_dynamic_recipe(recipe, normalized_presets)
        except TuningProtocolError as exc:
            raise AuthoringServiceError("AUTHORING_TRUSTED_RECIPE_INVALID", str(exc)) from exc
        from core.studio.trusted_node_presets import validate_trusted_node_mapping
        preset_by_id = {item["id"]: item for item in normalized_presets}
        raw_mappings = mappings if isinstance(mappings, dict) else {}
        if set(raw_mappings) != {item["id"] for item in recipe["nodes"]}:
            raise AuthoringServiceError(
                "AUTHORING_TRUSTED_MAPPING_MISSING",
                "Every trusted recipe node must pin one executable Developer mapping.",
            )
        executable_mappings = {}
        for node in recipe["nodes"]:
            mapping = validate_trusted_node_mapping(raw_mappings[node["id"]], preset_by_id[node["preset"]["id"]])
            if mapping["key"] != node["developer_mapping_key"]:
                raise AuthoringServiceError("AUTHORING_TRUSTED_MAPPING_INVALID", "Recipe and Developer mapping identities differ.")
            executable_mappings[node["id"]] = mapping
        return recipe, normalized_presets, executable_mappings

    def create_from_template(self, session_id: str, project_id: str, template: dict, values: dict, sources: list[dict]) -> dict:
        """Create a session only from a developer-authored CF-TUNING@1.3 template."""
        try:
            template_instance = create_template_instance(template, f"instance.{session_id}", values)
            steps, mappings = creator_blueprint_from_instance(template_instance)
        except TuningProtocolError as exc:
            raise AuthoringServiceError("AUTHORING_TEMPLATE_INVALID", str(exc)) from exc
        projection = self.create(session_id, f"template.{template_instance['template']['id']}", template_instance["template"]["id"], steps, sources, {}, project_id)
        with self._lock:
            state = self.get(session_id)
            state["template_instance"] = template_instance
            state["developer_mappings"] = mappings
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    def get(self, session_id: str) -> dict:
        with self._lock:
            return self._read(self._path(session_id))

    def clean_intent_contracts(
        self,
        session_id: str,
        *,
        registry_path: str | Path | None = None,
        project_root: str | Path | None = None,
    ) -> list[dict]:
        """Expose the current session through the detachable clean-v1 Intent adapter."""
        return CleanAuthoringProjector(
            project_root,
            registry_path=registry_path,
        ).intent_session(self.get(session_id))

    def get_by_project_id(self, project_id: str) -> dict:
        with self._lock:
            self._validate_identifier(project_id, "PROJECT")
            state = self._state_for_project_id(project_id)
            if state is None:
                raise AuthoringServiceError("AUTHORING_PROJECT_UNKNOWN", "Project was not found.", status=404)
            return state

    def list_projects(self) -> list[dict]:
        with self._lock:
            projects = []
            for path in sorted(self.root.glob("*.json")):
                state = self._read(path)
                head = state.get("head") if isinstance(state.get("head"), dict) else {}
                blueprint = head.get("blueprint") if isinstance(head.get("blueprint"), dict) else {}
                projects.append({
                    "project_id": state.get("project_id", state.get("id")),
                    "session_id": state.get("id"),
                    "name": state.get("project_name") or blueprint.get("intent") or state.get("project_id"),
                    "intent": blueprint.get("intent") or "",
                    "revision": head.get("revision") or 0,
                    "updated_at": path.stat().st_mtime,
                })
            return sorted(projects, key=lambda item: (-float(item["updated_at"]), str(item["project_id"])))

    def rename_project(self, project_id: str, name: str) -> dict:
        with self._lock:
            state = self.get_by_project_id(project_id)
            normalized = " ".join(str(name or "").split())
            if not normalized:
                raise AuthoringServiceError("AUTHORING_PROJECT_NAME_INVALID", "Project name is required.")
            state["project_name"] = normalized[:200]
            self._write(self._path(state["id"]), state)
            return self.creator_projection(state)

    def delete_project(self, project_id: str) -> dict:
        with self._lock:
            state = self.get_by_project_id(project_id)
            path = self._path(state["id"])
            path.unlink()
            return {"deleted": True, "project_id": project_id, "session_id": state["id"]}

    def trusted_preset_usage(self, preset_id: str) -> list[dict]:
        """Return Developer-visible references without exposing Creator-safe projections."""
        with self._lock:
            usage = []
            for path in sorted(self.root.glob("*.json")):
                state = self._read(path)
                recipe = state.get("trusted_recipe")
                if not isinstance(recipe, dict):
                    continue
                nodes = [
                    {"node_id": node["id"], "revision": node["preset"]["revision"]}
                    for node in recipe.get("nodes") or []
                    if isinstance(node, dict) and (node.get("preset") or {}).get("id") == preset_id
                ]
                if nodes:
                    usage.append({
                        "project_id": state.get("project_id", state["id"]),
                        "session_id": state["id"],
                        "nodes": nodes,
                    })
            return usage

    def capability_usage(self, capability_id: str) -> list[dict]:
        with self._lock:
            usage = []
            for path in sorted(self.root.glob("*.json")):
                state = self._read(path)
                publications = state.get("capability_publications") or {}
                nodes = []
                for node_id, release in publications.items():
                    if isinstance(release, dict) and release.get("id") == capability_id:
                        nodes.append({"node_id": node_id, "revision": release.get("revision"), "digest": release.get("digest")})
                if nodes:
                    usage.append({
                        "project_id": state.get("project_id", state["id"]),
                        "session_id": state["id"],
                        "nodes": nodes,
                    })
            return usage

    def propose(self, session_id: str, changes: list[dict], *, author: str, summary: str, expected_revision: int) -> dict:
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            if state.get("semantic_recipe"):
                allowed = {"set_creator_binding", "set_source_reference", "add_source", "update_source", "remove_source"}
                if any(item.get("operation") not in allowed for item in changes if isinstance(item, dict)):
                    raise AuthoringServiceError("AUTHORING_SEMANTIC_RECIPE_CHANGE_FORBIDDEN", "Node refinement cannot change overall recipe topology.", status=409)
                nodes = {item["id"]: item for item in state["semantic_recipe"]["nodes"]}
                publications = state.get("capability_publications") or {}
                for change in changes:
                    if not isinstance(change, dict) or change.get("operation") != "set_creator_binding":
                        continue
                    node = nodes.get(change.get("target_id"))
                    if node is None:
                        raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "Semantic recipe node was not found.", status=404)
                    try:
                        change["value"] = validate_values_for_node(node, publications.get(node["id"]), change.get("value"))
                    except CapabilityCartridgeError as exc:
                        raise AuthoringServiceError("AUTHORING_SEMANTIC_NODE_FIELD_INVALID", str(exc), status=409) from exc
            elif state.get("trusted_recipe"):
                allowed = {"set_creator_binding", "set_source_reference", "add_source", "update_source", "remove_source"}
                if any(item.get("operation") not in allowed for item in changes if isinstance(item, dict)):
                    raise AuthoringServiceError("AUTHORING_TRUSTED_RECIPE_CHANGE_FORBIDDEN", "Node refinement cannot change trusted recipe topology or identity.", status=409)
                presets = {item["id"]: item for item in state["trusted_presets"]}
                nodes = {item["id"]: item for item in state["trusted_recipe"]["nodes"]}
                for change in changes:
                    if not isinstance(change, dict) or change.get("operation") != "set_creator_binding":
                        continue
                    node = nodes.get(change.get("target_id"))
                    try:
                        if node is None:
                            raise TuningProtocolError("node refinement target is unknown")
                        change["value"] = validate_node_values(presets[node["preset"]["id"]], change.get("value"))
                    except TuningProtocolError as exc:
                        raise AuthoringServiceError("AUTHORING_TRUSTED_NODE_FIELD_INVALID", str(exc), status=409) from exc
            elif state.get("template_instance"):
                allowed = {"set_creator_binding", "set_binding", "set_step_intent", "set_source_reference", "add_source", "update_source", "remove_source"}
                if any(item.get("operation") not in allowed for item in changes if isinstance(item, dict)):
                    raise AuthoringServiceError("AUTHORING_TEMPLATE_CHANGE_FORBIDDEN", "Template instances cannot change steps or semantic relationships.", status=409)
            try:
                proposal = propose_change_set(state["head"], changes, author, summary)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_PROPOSAL_INVALID", str(exc)) from exc
            state["proposals"][proposal["id"]] = proposal
            self._write(self._path(session_id), state)
            return self.proposal_projection(proposal)

    async def propose_ai(self, session_id: str, *, prompt: str, author: str, summary: str, expected_revision: int,
                         model_call: Callable[[list[dict]], Awaitable[str]]) -> dict:
        """Generate a pending proposal through the configured LLM, never persisting chat text."""
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            head = deepcopy(state["head"])
        try:
            capabilities = resolve_ai_authoring_capabilities(Path(__file__).resolve().parents[3])
            content = await model_call(build_authoring_messages(head, capabilities, prompt))
            changes = parse_authoring_proposal(content, head, capabilities)
        except AuthoringProposalError as exc:
            raise AuthoringServiceError("AI_AUTHORING_PROPOSAL_INVALID", str(exc), status=422) from exc
        # Re-read after the await: the proposal must not be based on a stale head.
        return self.propose(session_id, changes, author=author, summary=summary, expected_revision=expected_revision)

    def preview(self, session_id: str, proposal_id: str, selected_change_ids: list[str] | None = None, *, freeze_revision: dict | None = None) -> dict:
        state = self.get(session_id)
        proposal = self._proposal(state, proposal_id)
        self._require_proposal_current(state, proposal)
        active_freezes, freeze_audit = self._freeze_guard(state, proposal, selected_change_ids, freeze_revision)
        try:
            acceptance = accept_change_set(state["head"], proposal, selected_change_ids, frozen_snapshots=active_freezes)
        except TuningProtocolError as exc:
            raise AuthoringServiceError("AUTHORING_PREVIEW_REJECTED", str(exc), status=409) from exc
        return {"schema": "cartridgeflow.authoring_preview.v1", "would_change": True,
                "base_revision": state["head"]["revision"], "next_revision": acceptance["instance"]["revision"],
                "accepted_change_ids": acceptance["accepted_change_ids"], "impact": self._impact(acceptance), "freeze_revision": freeze_audit,
                "developer": {"acceptance": acceptance, "compiled": compile_instance(acceptance["instance"])}}

    def accept(self, session_id: str, proposal_id: str, selected_change_ids: list[str] | None = None, *, freeze_revision: dict | None = None) -> dict:
        with self._lock:
            state = self.get(session_id)
            proposal = self._proposal(state, proposal_id)
            self._require_proposal_current(state, proposal)
            prior_active_freezes = self._active_freezes(state)
            active_freezes, freeze_audit = self._freeze_guard(state, proposal, selected_change_ids, freeze_revision)
            try:
                acceptance = accept_change_set(state["head"], proposal, selected_change_ids, frozen_snapshots=active_freezes)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_ACCEPT_REJECTED", str(exc), status=409) from exc
            # The sole state transition occurs after every validation has passed.
            replacements = self._next_freeze_replacements(prior_active_freezes, acceptance, freeze_audit)
            state["history"].append(acceptance)
            state["head"] = acceptance["instance"]
            state["instances"][acceptance["instance"]["id"]] = acceptance["instance"]
            if freeze_audit:
                state["freeze_revisions"].append(self._freeze_revision_record(freeze_audit, acceptance, replacements))
            state["freeze_replacements"].extend(replacements)
            state["proposals"].pop(proposal_id, None)
            self._write(self._path(session_id), state)
            return {"acceptance": acceptance, "creator": self.creator_projection(state), "impact": self._impact(acceptance), "freeze_revision": freeze_audit}

    def reject(self, session_id: str, proposal_id: str, *, reason: str = "") -> dict:
        with self._lock:
            state = self.get(session_id)
            proposal = self._proposal(state, proposal_id)
            state["proposals"].pop(proposal_id, None)
            state["rejections"].append({"proposal_id": proposal_id, "proposal_digest": proposal["digest"], "reason": str(reason)[:1000]})
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    def reverse(self, session_id: str, acceptance_id: str, *, author: str, summary: str, expected_revision: int, freeze_revision: dict | None = None) -> dict:
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            original = next((item for item in state["history"] if item["id"] == acceptance_id), None)
            if not original:
                raise AuthoringServiceError("AUTHORING_REVISION_UNKNOWN", "Acceptance revision was not found.", status=404)
            self._ensure_reversal_unambiguous(state, acceptance_id, original)
            inverse = self._inverse_changes(state["instances"], original["source_instance_id"], original["accepted_changes"])
            proposal = propose_change_set(state["head"], inverse, author, summary)
            state["proposals"][proposal["id"]] = proposal
            self._freeze_guard(state, proposal, None, freeze_revision)
            self._write(self._path(session_id), state)
            result = self.accept(session_id, proposal["id"], freeze_revision=freeze_revision)
            reversal = self._reversal_record(acceptance_id, result["acceptance"])
            state = self.get(session_id); state["reversals"].append(reversal); self._write(self._path(session_id), state)
            result["reversal"] = reversal
            return result

    def freeze(self, session_id: str, step_ids: list[str], *, author: str, summary: str) -> dict:
        with self._lock:
            state = self.get(session_id)
            compiled = compile_instance(state["head"])
            steps = [{"step_id": step_id, "semantic_digest": _semantic_digest(state["head"], step_id)} for step_id in step_ids]
            reference = {"id": compiled["id"], "kind": "compile", "digest": compiled["digest"]}
            try:
                snapshot = freeze_snapshot(state["head"], steps, reference, author, summary)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FREEZE_INVALID", str(exc)) from exc
            state["freezes"].append(snapshot)
            if state.get("semantic_recipe"):
                reviews = state.setdefault("capability_reviews", {})
                publications = state.get("capability_publications") or {}
                for step_id in step_ids:
                    publication = publications.get(step_id)
                    if isinstance(publication, dict):
                        reviews[step_id] = publication.get("digest")
            self._write(self._path(session_id), state)
            return snapshot

    def confirm_materialization(self, session_id: str, *, expected_revision: int, author: str, summary: str) -> dict:
        """Record Developer approval of one exact frozen trusted-recipe candidate."""
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            if not state.get("trusted_recipe"):
                raise AuthoringServiceError("DEVELOPER_MATERIALIZATION_NOT_TRUSTED_RECIPE", "This project does not use the trusted-node recipe contract.", status=409)
            readiness = self.generation_readiness(state)
            if not readiness["ready"]:
                raise AuthoringServiceError("DEVELOPER_MATERIALIZATION_BLOCKED", "The Creator recipe is not frozen and design-ready.", status=409)
            if not isinstance(author, str) or not author.strip() or not isinstance(summary, str) or not summary.strip():
                raise AuthoringServiceError("DEVELOPER_MATERIALIZATION_CONFIRMATION_INVALID", "Developer confirmation needs an author and review summary.")
            candidate = self.compile_candidate(state)
            body = {
                "schema": "cartridgeflow.developer_materialization_confirmation.v1",
                "session_id": session_id,
                "revision": expected_revision,
                "candidate": deepcopy(candidate),
                "author": author.strip()[:200],
                "summary": summary.strip()[:1000],
            }
            body["digest"] = canonical_digest(body)
            state["developer_confirmation"] = body
            self._write(self._path(session_id), state)
            return deepcopy(body)

    @staticmethod
    def creator_projection(state: dict) -> dict:
        head = state["head"]
        checks = AuthoringSessionStore.design_checks(state)
        freezes = AuthoringSessionStore._active_freezes(state)
        projection = {"project_id": state.get("project_id", state["id"]), "project_name": state.get("project_name") or head["blueprint"]["intent"], "session_id": state["id"], "revision": head["revision"], "intent": head["blueprint"]["intent"],
                "semantic_steps": [{"id": item["id"], "intent": item["intent"], "plain_inputs": sorted(item["inputs"]), "plain_outputs": sorted(item["outputs"])} for item in head["blueprint"]["steps"]],
                "steps": [{"id": item["id"], "intent": item["intent"]} for item in head["blueprint"]["steps"]],
                "relationships": deepcopy(head["blueprint"].get("relations", [])),
                "sources": [AuthoringSessionStore._safe_source(item) for item in head["blueprint"]["source_references"]],
                "creator_safe_bindings": deepcopy(head["bindings"]), "unresolved_assumptions": [],
                "pending_proposals": [AuthoringSessionStore.proposal_projection(state["proposals"][key]) for key in sorted(state["proposals"])],
                "active_freezes": [{"id": item["id"], "steps": [x["step_id"] for x in item["frozen_steps"]], "freeze_revision": {"source_freeze_ids": [item["id"]], "expected_revision": head["revision"]}} for item in freezes],
                "frozen_steps": sorted({x["step_id"] for f in freezes for x in f["frozen_steps"]}),
                "history": [{"id": item["id"], "revision": item["instance"]["revision"], "summary": item["change_set"]["summary"]} for item in state["history"]],
                "reversals": [{"id": item["id"], "reversal_of": item["reversal_of"], "revision": item["revision"]} for item in state.get("reversals", [])],
                "impact": {"changed_steps": sorted({x["target_id"] for h in state["history"] for x in h["accepted_changes"] if x["operation"] not in {"set_source_reference", "add_source", "update_source", "remove_source"}})},
                "journey_graph": AuthoringSessionStore.journey_graph(state, audience="creator"),
                "blocked_findings": [item for item in checks["findings"] if item["severity"] == "blocked"],
                "design_checks": checks, "generation_readiness": AuthoringSessionStore.generation_readiness(state, checks)}
        if state.get("semantic_recipe"):
            semantic = semantic_recipe_projection(state["semantic_recipe"], state.get("capability_publications") or {}, head["bindings"])
            projection["semantic_recipe"] = semantic
            projection["trusted_recipe"] = semantic
            projection["capability_resolution"] = {
                "resolved": sum(1 for node in semantic["nodes"] if node["resolution"]["status"] == "resolved"),
                "unresolved": sum(1 for node in semantic["nodes"] if node["resolution"]["status"] == "unresolved"),
                "revision": int(state.get("resolution_revision") or 1),
            }
        elif state.get("trusted_recipe"):
            trusted = creator_recipe_projection(state["trusted_recipe"], state["trusted_presets"])
            for node in trusted["nodes"]:
                node["values"] = deepcopy(head["bindings"].get(node["id"], {}))
            projection["trusted_recipe"] = trusted
        return projection

    @staticmethod
    def developer_projection(state: dict) -> dict:
        head = state["head"]
        readiness = AuthoringSessionStore.generation_readiness(state)
        projection = {
            "schema": "cartridgeflow.developer_project_projection.v1",
            "project_id": state.get("project_id", state["id"]),
            "recipe": {
                "revision": head["revision"],
                "steps": [{"id": item["id"], "intent": item["intent"]} for item in head["blueprint"]["steps"]],
                "sources": [AuthoringSessionStore._safe_source(item) for item in head["blueprint"]["source_references"]],
            },
            "journey_graph": AuthoringSessionStore.journey_graph(state, audience="developer"),
            "generation_readiness": readiness,
            "creator_url": f"/projects/{state.get('project_id', state['id'])}/studio",
        }
        if state.get("semantic_recipe"):
            publications = state.get("capability_publications") or {}
            projection["semantic_recipe"] = {
                "id": state["semantic_recipe"]["id"],
                "digest": state["semantic_recipe"]["digest"],
                "nodes": [{
                    "id": node["id"],
                    "label": node["creator_label"],
                    "needed_capability": node["needed_capability"],
                    "capability": ({
                        "id": publications[node["id"]]["id"],
                        "revision": publications[node["id"]]["revision"],
                        "digest": publications[node["id"]]["digest"],
                        "trust_scope": publications[node["id"]]["trust_scope"],
                        "source": deepcopy(publications[node["id"]]["implementation"].get("source")),
                    } if node["id"] in publications else None),
                    "creator_values": deepcopy(head["bindings"].get(node["id"], {})),
                } for node in state["semantic_recipe"]["nodes"]],
                "relations": deepcopy(state["semantic_recipe"]["relations"]),
            }
        elif state.get("trusted_recipe"):
            preset_by_id = {item["id"]: item for item in state["trusted_presets"]}
            projection["trusted_recipe"] = {
                "id": state["trusted_recipe"]["id"],
                "digest": state["trusted_recipe"]["digest"],
                "nodes": [{
                    "id": node["id"],
                    "label": node["creator_label"],
                    "preset_id": node["preset"]["id"],
                    "preset_revision": node["preset"]["revision"],
                    "preset_digest": node["preset"]["digest"],
                    "developer_mapping_key": node["developer_mapping_key"],
                    "developer_mapping_digest": state["developer_mappings"][node["id"]]["digest"],
                    "developer_source": deepcopy(state["developer_mappings"][node["id"]]["source"]),
                    "creator_values": deepcopy(head["bindings"].get(node["id"], {})),
                    "mapping_current": preset_by_id[node["preset"]["id"]]["revision"] == node["preset"]["revision"],
                } for node in state["trusted_recipe"]["nodes"]],
                "relations": deepcopy(state["trusted_recipe"]["relations"]),
                "developer_confirmation": deepcopy(state.get("developer_confirmation")),
            }
        return projection

    @staticmethod
    def journey_graph(state: dict, *, audience: str) -> dict:
        """Project-wide chain projection with only audience-appropriate facts."""
        head = state["head"]
        project_id = state.get("project_id", state["id"])
        frozen = {step["step_id"] for snapshot in AuthoringSessionStore._active_freezes(state) for step in snapshot["frozen_steps"]}
        nodes = [{"id": "project", "kind": "project", "label": "项目", "level": 0, "status": "active"}]
        edges: list[dict] = []
        if audience == "creator":
            nodes.append({"id": "intent", "kind": "intent", "label": head["blueprint"]["intent"], "level": 1, "status": "active"})
            edges.append({"id": "project-intent", "from": "project", "to": "intent", "relation": "starts_with"})
        step_level = 2 if audience == "creator" else 1
        capability_publications = state.get("capability_publications") or {}
        for step in head["blueprint"]["steps"]:
            node_id = f"step:{step['id']}"
            if state.get("semantic_recipe") and step["id"] not in capability_publications:
                status = "unresolved"
            else:
                status = "trusted" if step["id"] in frozen else "untrusted"
            nodes.append({"id": node_id, "kind": "recipe_step", "label": step["intent"], "level": step_level, "status": status})
            if audience == "creator":
                edges.append({"id": f"intent-{step['id']}", "from": "intent", "to": node_id, "relation": "shapes"})
            else:
                edges.append({"id": f"project-{step['id']}", "from": "project", "to": node_id, "relation": "contains"})
        for source in head["blueprint"]["source_references"]:
            source_id = f"source:{source['id']}"
            nodes.append({"id": source_id, "kind": "source", "label": source.get("name") or source.get("role") or "已采用来源", "level": step_level, "status": "adopted"})
            edges.append({"id": f"source-{source['id']}", "from": source_id, "to": "intent" if audience == "creator" else "project", "relation": "informs"})
        for relation in head["blueprint"].get("relations", []):
            edges.append({"id": f"relation:{relation['id']}", "from": f"step:{relation['from_step_id']}", "to": f"step:{relation['to_step_id']}", "relation": relation["relation"]})
        if audience == "developer":
            readiness = AuthoringSessionStore.generation_readiness(state)
            nodes.append({"id": "engineering", "kind": "engineering", "label": "工程验证", "level": step_level + 1, "status": "ready" if readiness["ready"] else "waiting"})
            for step in head["blueprint"]["steps"]:
                edges.append({"id": f"engineering-{step['id']}", "from": f"step:{step['id']}", "to": "engineering", "relation": "hands_off_to"})
        return {"schema": "cartridgeflow.project_journey_graph.v1", "project_id": project_id, "revision": head["revision"], "nodes": nodes, "edges": edges}

    @staticmethod
    def _safe_source(source: dict) -> dict:
        return {key: source[key] for key in ("id", "kind", "digest", "role", "name", "provides", "why_recommended", "risk", "review_focus", "remote_url", "rss_url") if key in source}

    @staticmethod
    def design_checks(state: dict) -> dict:
        head = state["head"]
        active = AuthoringSessionStore._active_freezes(state)
        frozen = {step["step_id"] for snapshot in active for step in snapshot["frozen_steps"]}
        findings = []
        mappings = head.get("developer_mappings") or state.get("developer_mappings") or {}
        mapping_ids = {step["id"] for step in head["blueprint"]["steps"]}
        if (state.get("template_instance") or state.get("trusted_recipe")) and set(mappings) != mapping_ids:
            findings.append({"code": "DESIGN_MAPPING_MISSING", "severity": "blocked", "message": "A template step has no Developer mapping."})
        if state.get("trusted_recipe") and any(not isinstance(mappings.get(step_id), dict) for step_id in mapping_ids):
            findings.append({"code": "DESIGN_EXECUTABLE_MAPPING_MISSING", "severity": "blocked", "message": "A trusted recipe step has no executable Developer snapshot."})
        if state.get("semantic_recipe"):
            publications = state.get("capability_publications") or {}
            reviews = state.get("capability_reviews") or {}
            for step in head["blueprint"]["steps"]:
                publication = publications.get(step["id"])
                if not isinstance(publication, dict):
                    findings.append({"code": "DESIGN_CAPABILITY_UNRESOLVED", "severity": "blocked", "step_id": step["id"], "message": "This semantic node still needs a trusted capability cartridge."})
                elif reviews.get(step["id"]) != publication.get("digest"):
                    findings.append({"code": "DESIGN_CAPABILITY_REVIEW_REQUIRED", "severity": "blocked", "step_id": step["id"], "message": "The resolved capability source has not been reviewed for this node."})
        for step in head["blueprint"]["steps"]:
            if step["id"] not in frozen:
                findings.append({"code": "DESIGN_STEP_UNFROZEN", "severity": "blocked", "step_id": step["id"], "message": "This design step is not frozen."})
        if not head["blueprint"]["source_references"] and not state.get("trusted_recipe") and not state.get("semantic_recipe"):
            findings.append({"code": "DESIGN_SOURCE_MISSING", "severity": "blocked", "message": "At least one declared source or source role is required."})
        return {"schema": "cartridgeflow.creator_design_checks.v1", "revision": head["revision"], "findings": findings}

    @staticmethod
    def generation_readiness(state: dict, checks: dict | None = None) -> dict:
        checks = checks or AuthoringSessionStore.design_checks(state)
        blocked = [item for item in checks["findings"] if item["severity"] == "blocked"]
        return {"schema": "cartridgeflow.creator_generation_readiness.v1", "revision": state["head"]["revision"], "ready": not blocked,
                "blocked_findings": blocked, "compile_candidate": None if blocked else {"reference": AuthoringSessionStore.compile_candidate(state)}}

    @staticmethod
    def compile_candidate(state: dict) -> dict:
        compiled = compile_instance(state["head"])
        candidate = {"id": compiled["id"], "kind": "compile", "digest": compiled["digest"], "revision": state["head"]["revision"]}
        if state.get("trusted_recipe"):
            candidate["trusted_recipe"] = {"id": state["trusted_recipe"]["id"], "digest": state["trusted_recipe"]["digest"]}
            candidate["mapping_digest"] = canonical_digest(state["developer_mappings"])
        if state.get("semantic_recipe"):
            candidate["semantic_recipe"] = {"id": state["semantic_recipe"]["id"], "digest": state["semantic_recipe"]["digest"]}
            candidate["capability_binding_digest"] = canonical_digest({
                node_id: {key: publication[key] for key in ("id", "revision", "digest", "trust_scope")}
                for node_id, publication in sorted((state.get("capability_publications") or {}).items())
            })
        return candidate

    @staticmethod
    def proposal_projection(proposal: dict) -> dict:
        return {"proposal_id": proposal["id"], "revision": proposal["expected_revision"], "summary": proposal["summary"],
                "changes": [{"id": x["id"], "target_id": x["target_id"], "operation": x["operation"],
                             "value": deepcopy(x.get("value"))} for x in proposal["changes"]]}

    def _freeze_guard(self, state: dict, proposal: dict, selected: list[str] | None, freeze_revision: dict | None) -> tuple[list[dict], dict | None]:
        ids = set(selected or [x["id"] for x in proposal["changes"]])
        active = self._active_freezes(state)
        frozen = {x["step_id"] for f in active for x in f["frozen_steps"]}
        touched = set()
        for item in proposal["changes"]:
            if item["id"] not in ids or item["operation"] in {"set_source_reference", "add_source", "update_source", "remove_source"}:
                continue
            if item["operation"] in {"connect_steps", "disconnect_steps"}:
                if isinstance(item["value"], dict): touched.update({item["value"].get("from_step_id"), item["value"].get("to_step_id")})
            else:
                touched.add(item["target_id"])
        touched.discard(None)
        affected = frozen & touched
        if not affected:
            return active, None
        audit = self._validate_freeze_revision(state, affected, freeze_revision)
        return [item for item in active if item["id"] not in set(audit["source_freeze_ids"])], audit

    @staticmethod
    def _active_freezes(state: dict) -> list[dict]:
        head = state["head"]
        replacements = state.get("freeze_replacements", [])
        for item in replacements:
            body = {key: value for key, value in item.items() if key not in {"id", "digest"}}
            digest = canonical_digest(body)
            if item.get("id") != f"freeze-replacement-{digest[:16]}" or item.get("digest") != digest:
                raise AuthoringServiceError("AUTHORING_FREEZE_LINEAGE_INVALID", "Freeze replacement lineage validation failed.", status=409)
        candidates = list(state.get("freezes", [])) + [item["snapshot"] for item in replacements]
        active = []
        for snapshot in candidates:
            try:
                validate_freeze_snapshot(snapshot)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FREEZE_LINEAGE_INVALID", "Freeze snapshot validation failed.", status=409) from exc
            if snapshot["instance_id"] == head["id"] and snapshot["instance_revision"] == head["revision"] and snapshot["instance_digest"] == head["digest"]:
                active.append(snapshot)
        return active

    def _validate_freeze_revision(self, state: dict, affected: set[str], request: dict | None) -> dict:
        if not isinstance(request, dict) or set(request) != {"source_freeze_ids", "reason", "author", "expected_revision"}:
            raise AuthoringServiceError("AUTHORING_FROZEN_STEP", "Frozen steps require a structured freeze revision request.", status=409)
        if request.get("expected_revision") != state["head"]["revision"] or not isinstance(request.get("reason"), str) or not request["reason"].strip() or not isinstance(request.get("author"), str) or not request["author"].strip():
            raise AuthoringServiceError("AUTHORING_FREEZE_REVISION_INVALID", "Freeze revision request is invalid.", status=409)
        ids = request.get("source_freeze_ids")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or any(not isinstance(x, str) for x in ids):
            raise AuthoringServiceError("AUTHORING_FREEZE_REVISION_INVALID", "Freeze revision snapshot ids are invalid.", status=409)
        active = {item["id"]: item for item in self._active_freezes(state)}
        required = {item["id"] for item in active.values() if affected & {x["step_id"] for x in item["frozen_steps"]}}
        if set(ids) != required:
            raise AuthoringServiceError("AUTHORING_FREEZE_REVISION_INVALID", "Freeze revision must name exactly the affected active snapshots.", status=409)
        return {"source_freeze_ids": sorted(ids), "reason": request["reason"].strip(), "author": request["author"].strip(), "expected_revision": request["expected_revision"], "affected_steps": sorted(affected)}

    @staticmethod
    def _freeze_revision_record(audit: dict, acceptance: dict, replacements: list[dict]) -> dict:
        body = {"schema": "cartridgeflow.authoring_freeze_revision.v1", "source_freeze_ids": audit["source_freeze_ids"], "affected_steps": audit["affected_steps"], "reason": audit["reason"], "author": audit["author"], "source_revision": audit["expected_revision"], "acceptance_id": acceptance["id"], "acceptance_digest": acceptance["digest"], "result_revision": acceptance["instance"]["revision"], "replacement_ids": sorted(item["snapshot"]["id"] for item in replacements if item["source_snapshot_id"] in audit["source_freeze_ids"])}
        digest = canonical_digest(body)
        return {"id": f"freeze-revision-{digest[:16]}", **body, "digest": digest}

    def _next_freeze_replacements(self, active_freezes: list[dict], acceptance: dict, audit: dict | None) -> list[dict]:
        """Carry each still-frozen step into the new immutable instance facts."""
        replacements = []
        changed = set((audit or {}).get("affected_steps", []))
        source_ids = set((audit or {}).get("source_freeze_ids", []))
        compiled = compile_instance(acceptance["instance"])
        reference = {"id": compiled["id"], "kind": "compile", "digest": compiled["digest"]}
        for source in active_freezes:
            preserved = [item["step_id"] for item in source["frozen_steps"] if not (source["id"] in source_ids and item["step_id"] in changed)]
            if not preserved:
                continue
            steps = [{"step_id": step_id, "semantic_digest": _semantic_digest(acceptance["instance"], step_id)} for step_id in preserved]
            snapshot = freeze_snapshot(acceptance["instance"], steps, reference, author="freeze-lineage", summary="Carry forward unaffected frozen steps")
            body = {"schema": "cartridgeflow.authoring_freeze_replacement.v1", "source_snapshot_id": source["id"], "source_snapshot_digest": source["digest"], "acceptance_id": acceptance["id"], "preserved_steps": sorted(preserved), "affected_steps": sorted(changed & {item["step_id"] for item in source["frozen_steps"]}), "snapshot": snapshot}
            digest = canonical_digest(body)
            replacements.append({"id": f"freeze-replacement-{digest[:16]}", **body, "digest": digest})
        return replacements

    @staticmethod
    def _reversal_record(reversal_of: str, acceptance: dict) -> dict:
        body = {"schema": "cartridgeflow.authoring_reversal.v1", "reversal_of": reversal_of, "acceptance_id": acceptance["id"], "acceptance_digest": acceptance["digest"], "revision": acceptance["instance"]["revision"]}
        digest = canonical_digest(body)
        return {"id": f"reversal-{digest[:16]}", **body, "digest": digest}

    @staticmethod
    def _ensure_reversal_unambiguous(state: dict, acceptance_id: str, original: dict) -> None:
        if any(item["reversal_of"] == acceptance_id for item in state.get("reversals", [])):
            raise AuthoringServiceError("AUTHORING_REVERSAL_ALREADY_APPLIED", "This acceptance has already been reversed.", status=409)
        index = state["history"].index(original)
        source = state["instances"].get(original["source_instance_id"])
        if source is None:
            raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "The original revision cannot be reconstructed safely.", status=409)
        targets = AuthoringSessionStore._acceptance_targets(state, original)
        later = state["history"][index + 1:]
        if any(targets & AuthoringSessionStore._acceptance_targets(state, acceptance) for acceptance in later):
            raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "A later accepted revision changed the same design target.", status=409)

    @staticmethod
    def _acceptance_targets(state: dict, acceptance: dict) -> set[str]:
        source = state["instances"].get(acceptance.get("source_instance_id"))
        if source is None:
            raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "The accepted revision cannot be reconstructed safely.", status=409)
        blueprint, bindings, targets = deepcopy(source["blueprint"]), deepcopy(source["bindings"]), set()
        try:
            for change in acceptance.get("accepted_changes", []):
                targets.update(AuthoringSessionStore._change_targets(blueprint, change))
                _apply_change(blueprint, bindings, change)
        except (KeyError, StopIteration, TuningProtocolError) as exc:
            raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "The accepted revision cannot be reconstructed safely.", status=409) from exc
        return targets

    @staticmethod
    def _change_targets(blueprint: dict, change: dict) -> set[str]:
        targets = {change["target_id"]}
        targets.update(_affected_step_ids(blueprint, change))
        return targets

    @staticmethod
    def _impact(acceptance: dict) -> dict:
        changes = acceptance["accepted_changes"]
        return {"changed_steps": sorted({x["target_id"] for x in changes if x["operation"] != "set_source_reference"}),
                "changed_sources": sorted({x["target_id"] for x in changes if x["operation"] == "set_source_reference"}),
                "plain_summary": f"{len(changes)} approved design change(s) will create revision {acceptance['instance']['revision']}."}

    @staticmethod
    def _require_revision(state: dict, expected: int) -> None:
        if expected != state["head"]["revision"]:
            raise AuthoringServiceError("AUTHORING_REVISION_CONFLICT", "The design session has changed; refresh before proposing.", status=409)

    def _require_proposal_current(self, state: dict, proposal: dict) -> None:
        if proposal["expected_revision"] != state["head"]["revision"] or proposal["instance_digest"] != state["head"]["digest"]:
            raise AuthoringServiceError("AUTHORING_PROPOSAL_STALE", "The proposal was made from an older design revision.", status=409)

    @staticmethod
    def _proposal(state: dict, proposal_id: str) -> dict:
        proposal = state["proposals"].get(proposal_id)
        if not proposal:
            raise AuthoringServiceError("AUTHORING_PROPOSAL_UNKNOWN", "Proposal was not found or is no longer pending.", status=404)
        return proposal

    def _inverse_changes(self, instances: dict, source_id: str, original_changes: list[dict]) -> list[dict]:
        source = instances.get(source_id)
        if source is None:
            raise AuthoringServiceError("AUTHORING_REVISION_LINEAGE_INVALID", "Cannot reconstruct the requested revision.", status=409)
        changes = []
        working_blueprint = deepcopy(source["blueprint"])
        working_bindings = deepcopy(source["bindings"])
        preimages = []
        for change in original_changes:
            preimages.append((deepcopy(working_blueprint), deepcopy(working_bindings)))
            _apply_change(working_blueprint, working_bindings, change)
        for change, (before_blueprint, before_bindings) in reversed(list(zip(original_changes, preimages))):
            target, op = change["target_id"], change["operation"]
            before_steps = {x["id"]: x for x in before_blueprint["steps"]}
            before_sources = {x["id"]: x for x in before_blueprint["source_references"]}
            before_relations = {x["id"]: x for x in before_blueprint.get("relations", [])}
            def append(operation: str, inverse_target: str, value: object) -> None:
                changes.append({"id": f"reverse.{len(changes)}", "target_id": inverse_target, "operation": operation, "value": deepcopy(value)})
            if op in {"set_binding", "set_creator_binding"}:
                append(op, target, before_bindings.get(target, {}))
            elif op == "set_step_intent":
                append(op, target, before_steps[target]["intent"])
            elif op in {"set_source_reference", "update_source"}:
                append(op, target, before_sources[target])
            elif op == "add_source":
                append("remove_source", target, {})
            elif op == "remove_source":
                append("add_source", target, before_sources[target])
            elif op == "add_step":
                append("remove_step", target, {})
            elif op == "update_step":
                append("update_step", target, before_steps[target])
            elif op == "remove_step":
                append("add_step", target, before_steps[target])
                if target in before_bindings:
                    append("set_creator_binding", target, before_bindings[target])
                for relation in sorted((item for item in before_relations.values() if target in {item["from_step_id"], item["to_step_id"]}), key=lambda item: item["id"]):
                    append("connect_steps", relation["id"], relation)
            elif op == "connect_steps":
                append("disconnect_steps", target, {})
            elif op == "disconnect_steps":
                append("connect_steps", target, before_relations[target])
            else:
                raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "The accepted operation cannot be reversed safely.", status=409)
        return changes

    def _path(self, session_id: str) -> Path:
        self._validate_identifier(session_id, "SESSION")
        return self.root / f"{session_id}.json"

    @staticmethod
    def _validate_identifier(value: str, kind: str) -> None:
        if not isinstance(value, str) or not value or any(item in value for item in ("/", "\\", "..")):
            raise AuthoringServiceError(f"AUTHORING_{kind}_ID_INVALID", f"{kind.title()} id is invalid.")

    def _state_for_project_id(self, project_id: str) -> dict | None:
        for path in sorted(self.root.glob("*.json")):
            state = self._read(path)
            if state.get("project_id", state.get("id")) == project_id:
                return state
        return None

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.is_file(): raise AuthoringServiceError("AUTHORING_SESSION_UNKNOWN", "Authoring session was not found.", status=404)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)


def _semantic_digest(instance: dict, step_id: str) -> str:
    step = next((item for item in instance["blueprint"]["steps"] if item["id"] == step_id), None)
    if not step: raise AuthoringServiceError("AUTHORING_STEP_UNKNOWN", "Step was not found.", status=404)
    return canonical_digest({"step": step, "binding": instance["bindings"].get(step_id)})


def compile_instance(instance: dict) -> dict:
    """Deterministically compile safe semantic facts; no model, secret, path, or runtime access."""
    body = {"schema": "cartridgeflow.authoring_compiled_recipe.v1", "protocol": deepcopy(instance["protocol"]),
            "instance_id": instance["id"], "instance_digest": instance["digest"], "revision": instance["revision"],
            "steps": [{"id": x["id"], "intent": x["intent"], "inputs": x["inputs"], "outputs": x["outputs"], "binding": instance["bindings"].get(x["id"], {})} for x in sorted(instance["blueprint"]["steps"], key=lambda x: x["id"])],
            "sources": sorted(instance["blueprint"]["source_references"], key=lambda x: x["id"])}
    digest = canonical_digest(body)
    return {"id": f"compile-{digest[:16]}", **body, "digest": digest}


def resolve_ai_authoring_capabilities(root: str | Path) -> list[str]:
    """Resolve AI permissions from published catalog + Base trust, never client input."""
    try:
        catalog = load_protocol_release_catalog(root)
        registry = ProtocolRegistry(root)
        base = load_base_implementation(root)
    except Exception as exc:
        raise AuthoringServiceError("AI_AUTHORING_TRUST_UNAVAILABLE", "Published authoring trust facts are unavailable.", status=409) from exc
    host = catalog.get("CF-FARP", "1.3")
    host_adapter = catalog.runtime_adapter("CF-FARP", "1.3")
    if not host or not catalog.published("CF-FARP", "1.3") or not registry.supports_protocol("CF-TUNING", "1.2"):
        raise AuthoringServiceError("AI_AUTHORING_TRUST_UNAVAILABLE", "Required published authoring releases are unavailable.", status=409)
    trusted = [item for item in catalog.trusted_subprotocols("CF-FARP", "1.3") if item.get("id") == "CF-TUNING" and str(item.get("version")) == "1.2" and item.get("binding") == "creator_service_contract"]
    adapters = {item.get("id") for item in base.get("supported_protocol_adapters", []) if item.get("status") == "supported"}
    required_capability = "creator_reviewed_semantic_changes_v1"
    if len(trusted) != 1 or "creator_service_contract" not in catalog.features("CF-FARP", "1.3") or required_capability not in registry.capabilities or required_capability not in set(base.get("capabilities") or []) or not supports_subprotocol_release(base, "CF-TUNING", "1.2", "CF-FARP", "1.3") or host_adapter not in adapters or "cf-tuning.authoring-contract.v1" not in adapters:
        raise AuthoringServiceError("AI_AUTHORING_TRUST_UNAVAILABLE", "Published authoring trust binding is not supported by Base.", status=409)
    capabilities = sorted(SERVICE_AUTHORING_OPERATIONS)
    if not capabilities:
        raise AuthoringServiceError("AI_AUTHORING_CAPABILITIES_EMPTY", "No trusted AI authoring operations are available.", status=409)
    return capabilities
