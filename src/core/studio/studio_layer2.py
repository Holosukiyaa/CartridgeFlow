"""Studio second-layer presentation contract persisted on the authoring session."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

DEFAULT_FIELDS = [
    {"id": "date", "label": "日期", "kind": "文本", "source": "运行输入.date"},
    {"id": "result_items", "label": "要点", "kind": "列表", "source": "结果.result_items"},
    {"id": "source_url", "label": "来源链接", "kind": "链接", "source": "结果.source_url"},
    {"id": "approved", "label": "已确认", "kind": "是/否", "source": "结果.approved"},
]

DEFAULT_PARAMS = [
    {"id": "sources", "label": "来源列表", "value_type": "string_list", "required": True, "default": []},
    {"id": "date", "label": "运行日期", "value_type": "string", "required": False, "default": ""},
]


def default_layer2(node_id: str, label: str) -> dict:
    return {
        "schema": "cartridgeflow.studio_layer2.v1",
        "node_id": node_id,
        "step_name": label,
        "params": deepcopy(DEFAULT_PARAMS),
        "fields": deepcopy(DEFAULT_FIELDS),
        "template": "摘要",
        "preview": "正常",
        "panel_name": "日报结果面板",
        "deliver": "",
        "tools": ["rss"],
        "handoff_in": "已审核来源列表",
        "handoff_out": "当天原始材料清单",
        "internal_steps": ["开始", "过程", "完成"],
        "published": False,
        "proof": {
            "success": False,
            "safe_fail": False,
            "success_run_id": "",
            "failure_run_id": "",
            "fingerprint": "",
            "source_digest": "",
        },
        "saved_at": "",
    }


def normalize_layer2(node_id: str, label: str, payload: dict | None) -> dict:
    base = default_layer2(node_id, label)
    if not isinstance(payload, dict):
        return base
    for key in ("step_name", "template", "preview", "panel_name", "deliver", "handoff_in", "handoff_out"):
        if isinstance(payload.get(key), str):
            base[key] = payload[key][:400]
    if isinstance(payload.get("tools"), list):
        base["tools"] = [str(item)[:80] for item in payload["tools"][:12]]
    if isinstance(payload.get("internal_steps"), list):
        steps = [str(item)[:80] for item in payload["internal_steps"][:16]]
        if steps:
            base["internal_steps"] = steps
    params = []
    for item in payload.get("params") or []:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            continue
        params.append({
            "id": str(item["id"])[:80],
            "label": str(item.get("label") or item["id"])[:80],
            "value_type": str(item.get("value_type") or "string")[:40],
            "required": bool(item.get("required")),
            "default": item.get("default"),
        })
    if params:
        base["params"] = params[:12]
    fields = []
    for item in payload.get("fields") or []:
        if not isinstance(item, dict) or not str(item.get("id") or item.get("label") or "").strip():
            continue
        fields.append({
            "id": str(item.get("id") or item.get("label"))[:80],
            "label": str(item.get("label") or item.get("id"))[:80],
            "kind": str(item.get("kind") or "文本")[:40],
            "source": str(item.get("source") or "")[:120],
        })
    if fields:
        base["fields"] = fields[:12]
    proof = payload.get("proof") if isinstance(payload.get("proof"), dict) else {}
    base["proof"].update({
        key: proof[key]
        for key in ("success", "safe_fail", "success_run_id", "failure_run_id", "fingerprint", "source_digest")
        if key in proof
    })
    base["published"] = bool(payload.get("published"))
    if isinstance(payload.get("saved_at"), str):
        base["saved_at"] = payload["saved_at"][:40]
    return base


def source_digest(layer: dict) -> str:
    body = {key: layer[key] for key in ("params", "fields", "template", "tools", "internal_steps", "step_name") if key in layer}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def layers_complete(state: dict) -> bool:
    recipe = state.get("semantic_recipe") or state.get("trusted_recipe") or {}
    nodes = recipe.get("nodes") or []
    if not nodes:
        return False
    stored = state.get("studio_layer2") or {}
    for node in nodes:
        layer = stored.get(node.get("id")) if isinstance(node, dict) else None
        if not isinstance(layer, dict) or not layer.get("published"):
            return False
        proof = layer.get("proof") if isinstance(layer.get("proof"), dict) else {}
        if not (proof.get("success") and proof.get("safe_fail")):
            return False
    return True


def gaps_cleared(state: dict) -> bool:
    recipe = state.get("semantic_recipe") or state.get("trusted_recipe") or {}
    nodes = [node for node in (recipe.get("nodes") or []) if isinstance(node, dict) and node.get("id")]
    if not nodes:
        return False
    stored = state.get("studio_layer2") or {}
    publications = state.get("capability_publications") or {}
    for node in nodes:
        node_id = str(node["id"])
        layer = stored.get(node_id) if isinstance(stored.get(node_id), dict) else {}
        if layer.get("published"):
            continue
        if node_id in publications:
            continue
        return False
    return True


def merge_layer2(node_id: str, label: str, payload: dict | None, existing: dict | None) -> dict:
    previous = normalize_layer2(node_id, label, existing)
    layer = normalize_layer2(node_id, label, payload)
    new_digest = source_digest(layer)
    old_digest = str((previous.get("proof") or {}).get("source_digest") or source_digest(previous))
    incoming = (payload or {}).get("proof") if isinstance((payload or {}).get("proof"), dict) else {}
    if new_digest != old_digest:
        layer["proof"] = {
            "success": False,
            "safe_fail": False,
            "success_run_id": "",
            "failure_run_id": "",
            "fingerprint": "",
            "source_digest": new_digest,
        }
        layer["published"] = False
        return layer
    merged = dict(previous.get("proof") or {})
    if incoming.get("success"):
        merged["success"] = True
        merged["success_run_id"] = str(incoming.get("success_run_id") or merged.get("success_run_id") or "")
    if incoming.get("safe_fail"):
        merged["safe_fail"] = True
        merged["failure_run_id"] = str(incoming.get("failure_run_id") or merged.get("failure_run_id") or "")
    if incoming.get("fingerprint"):
        merged["fingerprint"] = str(incoming["fingerprint"])
    merged["source_digest"] = new_digest
    layer["proof"] = merged
    if "published" in (payload or {}):
        layer["published"] = bool(payload.get("published"))
    else:
        layer["published"] = bool(previous.get("published"))
    return layer


def project_runtime_protocol(layers: dict[str, dict]) -> dict:
    params: list[dict] = []
    fields: list[dict] = []
    seen_params: set[str] = set()
    seen_fields: set[str] = set()
    for layer in layers.values():
        for item in layer.get("params") or []:
            if item["id"] in seen_params:
                continue
            seen_params.add(item["id"])
            params.append(item)
        for item in layer.get("fields") or []:
            key = item["id"]
            if key in seen_fields:
                continue
            seen_fields.add(key)
            fields.append(item)
    if not params:
        params = deepcopy(DEFAULT_PARAMS)
    if not fields:
        fields = deepcopy(DEFAULT_FIELDS)
    template = "摘要"
    for layer in layers.values():
        if layer.get("published") and layer.get("template"):
            template = str(layer["template"])
            break
        if layer.get("template"):
            template = str(layer["template"])
    return {"params": params, "fields": fields, "template": template}
