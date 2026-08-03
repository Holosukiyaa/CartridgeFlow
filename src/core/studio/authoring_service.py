"""Fail-closed creator authoring sessions built on immutable authoring facts."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Any

from core.protocol.authoring_contract import (
    accept_change_set, canonical_digest, create_recipe_blueprint,
    create_recipe_instance, freeze_snapshot, propose_change_set,
)
from core.protocol.tuning import TuningProtocolError


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
                     "head": instance, "instances": {instance["id"]: instance}, "history": [], "proposals": {}, "rejections": [], "freezes": []}
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

    def preview(self, session_id: str, proposal_id: str, selected_change_ids: list[str] | None = None, *, revision_path: str = "") -> dict:
        state = self.get(session_id)
        proposal = self._proposal(state, proposal_id)
        self._require_proposal_current(state, proposal)
        self._freeze_guard(state, proposal, selected_change_ids, revision_path)
        try:
            acceptance = accept_change_set(state["head"], proposal, selected_change_ids, frozen_snapshots=state["freezes"])
        except TuningProtocolError as exc:
            raise AuthoringServiceError("AUTHORING_PREVIEW_REJECTED", str(exc), status=409) from exc
        return {"schema": "cartridgeflow.authoring_preview.v1", "would_change": True,
                "base_revision": state["head"]["revision"], "next_revision": acceptance["instance"]["revision"],
                "accepted_change_ids": acceptance["accepted_change_ids"], "impact": self._impact(acceptance),
                "developer": {"acceptance": acceptance, "compiled": compile_instance(acceptance["instance"])}}

    def accept(self, session_id: str, proposal_id: str, selected_change_ids: list[str] | None = None, *, revision_path: str = "") -> dict:
        with self._lock:
            state = self.get(session_id)
            proposal = self._proposal(state, proposal_id)
            self._require_proposal_current(state, proposal)
            self._freeze_guard(state, proposal, selected_change_ids, revision_path)
            try:
                acceptance = accept_change_set(state["head"], proposal, selected_change_ids, frozen_snapshots=state["freezes"])
            except TuningProtocolError as exc:
                raise AuthoringServiceError("AUTHORING_ACCEPT_REJECTED", str(exc), status=409) from exc
            # The sole state transition occurs after every validation has passed.
            state["history"].append(acceptance)
            state["head"] = acceptance["instance"]
            state["instances"][acceptance["instance"]["id"]] = acceptance["instance"]
            state["proposals"].pop(proposal_id, None)
            self._write(self._path(session_id), state)
            return {"acceptance": acceptance, "creator": self.creator_projection(state), "impact": self._impact(acceptance)}

    def reject(self, session_id: str, proposal_id: str, *, reason: str = "") -> dict:
        with self._lock:
            state = self.get(session_id)
            proposal = self._proposal(state, proposal_id)
            state["proposals"].pop(proposal_id, None)
            state["rejections"].append({"proposal_id": proposal_id, "proposal_digest": proposal["digest"], "reason": str(reason)[:1000]})
            self._write(self._path(session_id), state)
            return self.creator_projection(state)

    def reverse(self, session_id: str, acceptance_id: str, *, author: str, summary: str, expected_revision: int, revision_path: str = "") -> dict:
        with self._lock:
            state = self.get(session_id)
            self._require_revision(state, expected_revision)
            original = next((item for item in state["history"] if item["id"] == acceptance_id), None)
            if not original:
                raise AuthoringServiceError("AUTHORING_REVISION_UNKNOWN", "Acceptance revision was not found.", status=404)
            prior = original["change_set"]
            inverse = self._inverse_changes(state["instances"], original["source_instance_id"], prior)
            proposal = propose_change_set(state["head"], inverse, author, summary)
            state["proposals"][proposal["id"]] = proposal
            self._freeze_guard(state, proposal, None, revision_path)
            self._write(self._path(session_id), state)
            result = self.accept(session_id, proposal["id"], revision_path=revision_path)
            result["acceptance"]["reversal_of"] = acceptance_id
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
        return {"session_id": state["id"], "revision": head["revision"], "intent": head["blueprint"]["intent"],
                "steps": [{"id": item["id"], "intent": item["intent"]} for item in head["blueprint"]["steps"]],
                "pending_proposals": sorted(state["proposals"]), "frozen_steps": sorted({x["step_id"] for f in state["freezes"] for x in f["frozen_steps"]}),
                "history": [{"id": item["id"], "revision": item["instance"]["revision"], "summary": item["change_set"]["summary"]} for item in state["history"]]}

    @staticmethod
    def proposal_projection(proposal: dict) -> dict:
        return {"proposal_id": proposal["id"], "revision": proposal["expected_revision"], "summary": proposal["summary"],
                "changes": [{"id": x["id"], "target_id": x["target_id"], "operation": x["operation"]} for x in proposal["changes"]]}

    def _freeze_guard(self, state: dict, proposal: dict, selected: list[str] | None, revision_path: str) -> None:
        ids = set(selected or [x["id"] for x in proposal["changes"]])
        frozen = {x["step_id"] for f in state["freezes"] for x in f["frozen_steps"]}
        touched = {x["target_id"] for x in proposal["changes"] if x["id"] in ids and x["operation"] != "set_source_reference"}
        if frozen & touched and not str(revision_path).strip():
            raise AuthoringServiceError("AUTHORING_FROZEN_STEP", "Frozen steps require an explicit revision path.", status=409)

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

    def _inverse_changes(self, instances: dict, source_id: str, original_changes: dict) -> list[dict]:
        source = instances.get(source_id)
        if source is None:
            raise AuthoringServiceError("AUTHORING_REVISION_LINEAGE_INVALID", "Cannot reconstruct the requested revision.", status=409)
        changes = []
        before_steps = {x["id"]: x for x in source["blueprint"]["steps"]}; before_sources = {x["id"]: x for x in source["blueprint"]["source_references"]}
        for index, change in enumerate(original_changes["changes"]):
            target, op = change["target_id"], change["operation"]
            value = source["bindings"].get(target, {}) if op == "set_binding" else before_steps[target]["intent"] if op == "set_step_intent" else before_sources[target]
            changes.append({"id": f"reverse.{index}", "target_id": target, "operation": op, "value": deepcopy(value)})
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
    body = {"schema": "cartridgeflow.authoring_compiled_recipe.v1", "protocol": {"id": "CF-TUNING", "version": "1.1"},
            "instance_id": instance["id"], "instance_digest": instance["digest"], "revision": instance["revision"],
            "steps": [{"id": x["id"], "intent": x["intent"], "inputs": x["inputs"], "outputs": x["outputs"], "binding": instance["bindings"].get(x["id"], {})} for x in sorted(instance["blueprint"]["steps"], key=lambda x: x["id"])],
            "sources": sorted(instance["blueprint"]["source_references"], key=lambda x: x["id"])}
    digest = canonical_digest(body)
    return {"id": f"compile-{digest[:16]}", **body, "digest": digest}
