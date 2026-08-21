"""Honest Studio layer-2 proof: required-present vs required-omitted."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from core.studio.studio_layer2 import normalize_layer2, source_digest


def run_studio_proof(store, session_id: str, node_id: str, mode: str, inputs: dict) -> dict:
    state = store.get(session_id)
    label = store._node_label(state, node_id)
    layer = normalize_layer2(node_id, label, (state.get("studio_layer2") or {}).get(node_id))
    required = [item for item in layer["params"] if item.get("required")]
    missing = []
    for item in required:
        value = inputs.get(item["id"])
        if value in (None, "", [], {}):
            missing.append(item["label"] or item["id"])
    digest = source_digest(layer)
    fingerprint = hashlib.sha256(f"{node_id}:{digest}".encode("utf-8")).hexdigest()[:12]
    if mode == "omit_required" or missing:
        return {
            "success": False,
            "safe_fail": True,
            "success_run_id": "",
            "failure_run_id": f"fail_{digest[:8]}",
            "fingerprint": fingerprint,
            "source_digest": digest,
            "status": "safe_fail",
            "message": "缺少必填 已停住 · 没写半份日报",
            "missing": missing,
        }
    items = []
    sources = inputs.get("sources") or inputs.get("来源列表") or []
    if isinstance(sources, str):
        sources = [line.strip() for line in sources.splitlines() if line.strip()]
    if isinstance(sources, list):
        items = [{"title": str(item), "url": str(item)} if not isinstance(item, dict) else item for item in sources[:12]]
    date = str(inputs.get("date") or inputs.get("运行日期") or "")
    return {
        "success": True,
        "safe_fail": False,
        "success_run_id": f"ok_{digest[:8]}",
        "failure_run_id": "",
        "fingerprint": fingerprint,
        "source_digest": digest,
        "status": "success",
        "message": "成功 已拿到可展示的日报草稿",
        "delivery": {
            "date": date,
            "result_items": items or [{"title": "可展示的日报草稿", "summary": json.dumps(inputs, ensure_ascii=False)[:200]}],
            "source_url": [str(item.get("url") or item.get("title") or "") for item in items if isinstance(item, dict)],
            "approved": False,
        },
        "inputs": deepcopy(inputs),
    }
