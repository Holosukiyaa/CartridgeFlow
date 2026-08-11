"""Clean-v1 runtime projections shared by Workbench-side conformance tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .clean_protocol import CLEAN_CONTRACT_VERSION, resolve_clean_protocol_adapter
from .data_contracts import DataContractError


RUNTIME_ADAPTER_ID = "cartridgeflow.runtime.v1"
_HOST_KINDS = ("profile", "target", "compatibility")
_EXECUTION_KINDS = ("request", "run", "node-state", "error", "event")
_INTERACTION_KINDS = ("pending", "response")
_RECOVERY_KINDS = ("checkpoint", "request", "result")
_ARTIFACT_KINDS = ("record", "content-reference")


class CleanRuntimeProjectionError(DataContractError):
    """Raised when a runtime fact lacks information required by clean-v1."""


class CleanRuntimeProjector:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.registry_path = Path(registry_path).resolve() if registry_path is not None else None
        self.adapter = resolve_clean_protocol_adapter(RUNTIME_ADAPTER_ID)

    def host(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "host fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "host_id": _text(fact.get("host_id"), "host id"),
            "target": _text(fact.get("target"), "host target"),
            "protocols": _texts(fact.get("protocols"), "host protocols"),
            "capabilities": _texts(fact.get("capabilities"), "host capabilities"),
        }
        return [
            self._envelope(f"cartridgeflow.host.{kind}", {**common, "kind": kind})
            for kind in _HOST_KINDS
        ]

    def execution(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "execution fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "run_id": _text(fact.get("run_id"), "run id"),
            "state": str(fact.get("state") or ""),
            "node_id": _text(fact.get("node_id"), "execution node id"),
            "sequence": _sequence(fact.get("sequence", 0)),
        }
        result = []
        for kind in _EXECUTION_KINDS:
            payload = {**common, "kind": kind}
            if kind == "request":
                payload.update(
                    {
                        "request_id": _text(fact.get("request_id"), "execution request id"),
                        "requested_at": _text(fact.get("requested_at"), "execution request time"),
                        "requested_by": _text(fact.get("requested_by"), "execution requester"),
                    }
                )
            elif kind == "error":
                payload.update(
                    {
                        "error_code": _text(fact.get("error_code"), "execution error code"),
                        "message": _text(fact.get("error_message"), "execution error message"),
                        "retryable": bool(fact.get("retryable")),
                    }
                )
            elif kind == "event":
                payload.update(
                    {
                        "event_id": _text(fact.get("event_id"), "execution event id"),
                        "event_type": _text(fact.get("event_type"), "execution event type"),
                    }
                )
            result.append(self._envelope(f"cartridgeflow.execution.{kind}", payload))
        return result

    def interaction(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "interaction fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "interaction_id": _text(fact.get("interaction_id"), "interaction id"),
            "run_id": _text(fact.get("run_id"), "interaction run id"),
            "prompt": _text(fact.get("prompt"), "interaction prompt"),
            "expires_at": _text(fact.get("expires_at"), "interaction expiry"),
        }
        return [
            self._envelope(f"cartridgeflow.interaction.{kind}", {**common, "kind": kind})
            for kind in _INTERACTION_KINDS
        ]

    def recovery(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "recovery fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "run_id": _text(fact.get("run_id"), "recovery run id"),
            "checkpoint_id": _text(fact.get("checkpoint_id"), "checkpoint id"),
            "action": str(fact.get("action") or ""),
        }
        result = []
        for kind in _RECOVERY_KINDS:
            payload = {**common, "kind": kind}
            if kind == "request":
                payload.update(
                    {
                        "request_id": _text(fact.get("request_id"), "recovery request id"),
                        "requested_at": _text(fact.get("requested_at"), "recovery request time"),
                        "requested_by": _text(fact.get("requested_by"), "recovery requester"),
                    }
                )
            elif kind == "result":
                payload.update(
                    {
                        "status": str(fact.get("status") or ""),
                        "message": _text(fact.get("message"), "recovery result message"),
                    }
                )
            result.append(self._envelope(f"cartridgeflow.recovery.{kind}", payload))
        return result

    def artifact(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "artifact fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "artifact_id": _text(fact.get("artifact_id"), "artifact id"),
            "run_id": _text(fact.get("run_id"), "artifact run id"),
            "media_type": _text(fact.get("media_type"), "artifact media type"),
            "digest": _digest(fact.get("digest"), "artifact digest"),
            "path": _text(fact.get("path"), "artifact path"),
        }
        return [
            self._envelope(f"cartridgeflow.artifact.{kind}", {**common, "kind": kind})
            for kind in _ARTIFACT_KINDS
        ]

    def delivery(self, fact: dict) -> list[dict]:
        fact = _mapping(fact, "delivery fact")
        common = {
            "revision": _revision(fact.get("revision", 1)),
            "run_id": _text(fact.get("run_id"), "delivery run id"),
            "artifact_ids": _texts(fact.get("artifact_ids"), "delivery artifact ids"),
            "receipt_id": _text(fact.get("receipt_id"), "delivery receipt id"),
        }
        return [
            self._envelope(
                "cartridgeflow.delivery.result",
                {
                    **common,
                    "kind": "result",
                    "status": str(fact.get("result_status") or ""),
                    "message": _text(fact.get("message"), "delivery result message"),
                },
            ),
            self._envelope(
                "cartridgeflow.delivery.receipt",
                {
                    **common,
                    "kind": "receipt",
                    "status": str(fact.get("receipt_status") or ""),
                    "delivered_at": _text(fact.get("delivered_at"), "delivery time"),
                },
            ),
        ]

    def _envelope(self, contract_id: str, payload: dict) -> dict:
        envelope = {"contract_id": contract_id, "version": CLEAN_CONTRACT_VERSION, "payload": payload}
        self.adapter.validate(
            contract_id,
            envelope,
            root=self.root,
            registry_path=self.registry_path,
        )
        return envelope


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        _projection_error("clean_runtime_source_invalid", f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _projection_error("clean_runtime_source_invalid", f"{label} must not be empty")
    return text


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        _projection_error("clean_runtime_source_invalid", f"{label} must be an array")
    result = [_text(item, label) for item in value]
    if not result:
        _projection_error("clean_runtime_source_invalid", f"{label} must not be empty")
    return result


def _revision(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _projection_error("clean_runtime_revision_invalid", "revision must be a positive integer")
    return value


def _sequence(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _projection_error("clean_runtime_sequence_invalid", "sequence must be a non-negative integer")
    return value


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        _projection_error("clean_runtime_digest_invalid", f"{label} must be a SHA-256 digest")
    return text


def _projection_error(code: str, message: str) -> None:
    raise CleanRuntimeProjectionError(code, message)
