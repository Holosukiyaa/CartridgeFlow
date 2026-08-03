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
)
from core.protocol.base_manifest import load_base_implementation, supports_subprotocol_release
from core.protocol.release_catalog import load_protocol_release_catalog
from core.protocol.capability_registry import ProtocolRegistry
from core.protocol.authoring_contract import _OPERATIONS, _affected_step_ids, _apply_change
from core.protocol.tuning import TuningProtocolError
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

    def create(self, session_id: str, recipe_id: str, intent: str, steps: list[dict], sources: list[dict], bindings: dict) -> dict:
        with self._lock:
            path = self._path(session_id)
            if path.exists():
                raise AuthoringServiceError("AUTHORING_SESSION_EXISTS", "Authoring session already exists.", status=409)
            try:
                blueprint = create_recipe_blueprint(recipe_id, intent, steps, sources)
                instance = create_recipe_instance(blueprint, bindings)
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_FACT_INVALID", str(exc)) from exc
            state = {"schema": "cartridgeflow.authoring_session.v1", "id": session_id,
                     "head": instance, "instances": {instance["id"]: instance}, "history": [], "proposals": {}, "rejections": [], "freezes": [], "freeze_replacements": [], "freeze_revisions": [], "reversals": []}
            self._write(path, state)
            return self.creator_projection(state)

    def get(self, session_id: str) -> dict:
        with self._lock:
            return self._read(self._path(session_id))

    def propose(self, session_id: str, changes: list[dict], *, author: str, summary: str, expected_revision: int) -> dict:
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
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
            state["freezes"].append(snapshot); self._write(self._path(session_id), state)
            return snapshot

    @staticmethod
    def creator_projection(state: dict) -> dict:
        head = state["head"]
        checks = AuthoringSessionStore.design_checks(state)
        freezes = AuthoringSessionStore._active_freezes(state)
        return {"session_id": state["id"], "revision": head["revision"], "intent": head["blueprint"]["intent"],
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
                "blocked_findings": [item for item in checks["findings"] if item["severity"] == "blocked"],
                "design_checks": checks, "generation_readiness": AuthoringSessionStore.generation_readiness(state, checks)}

    @staticmethod
    def _safe_source(source: dict) -> dict:
        return {key: source[key] for key in ("id", "kind", "digest", "role", "remote_url", "rss_url") if key in source}

    @staticmethod
    def design_checks(state: dict) -> dict:
        head = state["head"]
        active = AuthoringSessionStore._active_freezes(state)
        frozen = {step["step_id"] for snapshot in active for step in snapshot["frozen_steps"]}
        findings = []
        for step in head["blueprint"]["steps"]:
            if step["id"] not in frozen:
                findings.append({"code": "DESIGN_STEP_UNFROZEN", "severity": "blocked", "step_id": step["id"], "message": "This design step is not frozen."})
        if not head["blueprint"]["source_references"]:
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
        return {"id": compiled["id"], "kind": "compile", "digest": compiled["digest"], "revision": state["head"]["revision"]}

    @staticmethod
    def proposal_projection(proposal: dict) -> dict:
        return {"proposal_id": proposal["id"], "revision": proposal["expected_revision"], "summary": proposal["summary"],
                "changes": [{"id": x["id"], "target_id": x["target_id"], "operation": x["operation"]} for x in proposal["changes"]]}

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
        targets = set().union(*(AuthoringSessionStore._change_targets(source["blueprint"], item) for item in original["accepted_changes"]))
        later = state["history"][index + 1:]
        if any(targets & {item["target_id"] for item in acceptance["accepted_changes"]} for acceptance in later):
            raise AuthoringServiceError("AUTHORING_REVERSAL_AMBIGUOUS", "A later accepted revision changed the same design target.", status=409)

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
        if not isinstance(session_id, str) or not session_id or any(x in session_id for x in ("/", "\\", "..")):
            raise AuthoringServiceError("AUTHORING_SESSION_ID_INVALID", "Session id is invalid.")
        return self.root / f"{session_id}.json"

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
        registry = ProtocolRegistry(root, overlay_dirs=[Path(root) / "protocol" / "tuning" / "1.2"])
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
