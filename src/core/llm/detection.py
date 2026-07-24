from __future__ import annotations

from urllib.parse import urlparse

import httpx


class LLMDetectionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


async def detect_model_connection(
    *,
    base_url: str,
    api_key: str,
    preferred_model: str = "",
    timeout: int = 20,
) -> dict:
    clean_base = _validate_base_url(base_url)
    clean_key = str(api_key or "").strip()
    if not clean_key:
        raise LLMDetectionError("请填写 API Key 后再自动检测", status_code=400)

    attempts = []
    successes = []
    headers = {"Authorization": f"Bearer {clean_key}"}
    try:
        async with httpx.AsyncClient(timeout=max(5, min(int(timeout or 20), 60)), follow_redirects=True) as client:
            for endpoint in _model_endpoints(clean_base):
                try:
                    response = await client.get(endpoint, headers=headers)
                except httpx.TimeoutException:
                    attempts.append({"endpoint": endpoint, "status": 504, "error": "连接超时"})
                    continue
                except httpx.HTTPError as exc:
                    attempts.append({"endpoint": endpoint, "status": 502, "error": f"连接失败：{exc}"})
                    continue

                body = _response_body(response)
                models = _model_ids(body)
                error = _response_error(body)
                attempts.append({
                    "endpoint": endpoint,
                    "status": response.status_code,
                    "model_count": len(models),
                    "error": error,
                })
                if response.status_code < 400 and models:
                    successes.append({"endpoint": endpoint, "models": models})
    except (TypeError, ValueError) as exc:
        raise LLMDetectionError(f"自动检测参数无效：{exc}", status_code=400) from exc

    if not successes:
        raise _detection_failure(attempts)

    models = list(dict.fromkeys(model for success in successes for model in success["models"]))
    profile = _detect_profile(models, preferred_model)

    prefer_versioned = True
    detected_base = _recommended_base(successes, prefer_versioned=prefer_versioned)
    host = urlparse(detected_base).hostname or "model-api"
    short_host = host.removeprefix("api.").split(".")[0] or host
    adapter_label = "普通文本模型"
    return {
        "ok": True,
        "status": "detected",
        "provider": {
            "name": f"{short_host} · {adapter_label}",
            "api_type": "openai",
            "base_url": detected_base,
            "default_model": profile["model"],
            "wire_api": profile["wire_api"],
            "capabilities": profile["capabilities"],
            "adapter_profile": "standard",
            "timeout": profile["timeout"],
        },
        "detection": {
            "capability": profile["capability"],
            "adapter_label": adapter_label,
            "confidence": profile["confidence"],
            "model_count": len(models),
            "models": models,
            "models_endpoint": _recommended_endpoint(successes, prefer_versioned=prefer_versioned),
            "summary": f"已识别为{adapter_label}，默认使用 {profile['model']}",
        },
        "attempts": attempts,
    }


def _validate_base_url(value: str) -> str:
    clean = str(value or "").strip().rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMDetectionError("请填写有效的 http(s) 模型服务 URL", status_code=400)
    return clean


def _model_endpoints(base_url: str) -> list[str]:
    if base_url.lower().endswith("/v1"):
        parent = base_url[:-3].rstrip("/")
        values = [f"{base_url}/models", f"{parent}/models"]
    else:
        values = [f"{base_url}/models", f"{base_url}/v1/models"]
    return list(dict.fromkeys(values))


def _response_body(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return response.text[:300].strip()


def _model_ids(body) -> list[str]:
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        return []
    values = []
    for item in body["data"]:
        model_id = item.get("id") if isinstance(item, dict) else item if isinstance(item, str) else ""
        clean = str(model_id or "").strip()
        if clean:
            values.append(clean)
    return list(dict.fromkeys(values))


def _response_error(body) -> str:
    if isinstance(body, str):
        return body[:300]
    if not isinstance(body, dict):
        return ""
    error = body.get("error") or body.get("message") or body.get("detail") or ""
    if isinstance(error, dict):
        error = error.get("message") or error.get("detail") or error.get("code") or ""
    return str(error or "")[:300]


def _detection_failure(attempts: list[dict]) -> LLMDetectionError:
    if not attempts:
        return LLMDetectionError("模型服务没有响应自动检测请求", status_code=502)
    if all(int(item.get("status") or 0) < 400 for item in attempts):
        return LLMDetectionError("自动检测失败：模型服务没有返回可用模型", status_code=422)
    preferred = next((item for item in attempts if item.get("status") in {401, 403}), None)
    preferred = preferred or next((item for item in attempts if item.get("error")), None) or attempts[0]
    status = int(preferred.get("status") or 502)
    if status in {401, 403}:
        message = "API Key 未通过模型服务鉴权"
    elif status == 404:
        message = "模型服务没有提供可识别的 Models API"
    elif preferred.get("error"):
        message = str(preferred["error"])
    else:
        message = "模型服务没有返回可用模型"
    return LLMDetectionError(f"自动检测失败：{message}", status_code=status if 400 <= status <= 599 else 502)


def _detect_profile(models: list[str], preferred_model: str = "") -> dict:
    preferred = str(preferred_model or "").strip()
    return {
        "model": _select_model(models, preferred),
        "capability": "text_reasoning",
        "wire_api": "chat_completions",
        "adapter_profile": "standard",
        "capabilities": ["text_reasoning"],
        "timeout": 120,
        "confidence": "medium",
    }


def _select_model(models: list[str], preferred: str = "", priorities: tuple[str, ...] = ()) -> str:
    lookup = {model.lower(): model for model in models}
    if preferred.lower() in lookup:
        return lookup[preferred.lower()]
    for value in priorities:
        if value.lower() in lookup:
            return lookup[value.lower()]
    return models[0]


def _recommended_base(successes: list[dict], *, prefer_versioned: bool) -> str:
    return _recommended_endpoint(successes, prefer_versioned=prefer_versioned).rsplit("/models", 1)[0]


def _recommended_endpoint(successes: list[dict], *, prefer_versioned: bool) -> str:
    if prefer_versioned:
        selected = next((item for item in successes if item["endpoint"].lower().endswith("/v1/models")), None)
    else:
        selected = next((item for item in successes if not item["endpoint"].lower().endswith("/v1/models")), None)
    return str((selected or successes[0])["endpoint"])
