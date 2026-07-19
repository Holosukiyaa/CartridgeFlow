from __future__ import annotations

from collections.abc import Iterable, Mapping

from . import media_core, pixel_episode, short_video, spatial


DLC_DESCRIPTORS = {
    "core.media": {
        "id": "core.media", "protocol": "CF-FARP@0.4", "kind": "core", "enabled_by_default": True, "modules": ["media_core"]
    },
    "dlc.pixel_episode": {
        "id": "dlc.pixel_episode", "protocol": "CF-FARP@0.4", "kind": "dlc", "enabled_by_default": True, "modules": ["pixel_episode"]
    },
    "core.short_video": {
        "id": "core.short_video", "protocol": "CF-FARP@0.4", "kind": "core", "enabled_by_default": True, "modules": ["short_video"]
    },
    "dlc.spatial_blockout": {
        "id": "dlc.spatial_blockout", "protocol": "CF-FARP@0.4", "kind": "dlc", "enabled_by_default": True, "modules": ["spatial"]
    },
}
_MODULES = [media_core, pixel_episode, short_video, spatial]
_EXTENSION_MODULES: dict[str, object] = {}


def _protocol_key(value) -> str:
    if isinstance(value, Mapping):
        protocol_id = str(value.get("id") or value.get("protocol") or "").strip()
        version = str(value.get("version") or value.get("protocol_version") or "").strip()
        if protocol_id and version:
            return f"{protocol_id}@{version}"
        return protocol_id
    return str(value or "").strip()


def normalize_protocol_extensions(value) -> set[str]:
    """Normalize manifest extension declarations to ``protocol@version`` keys."""
    if isinstance(value, Mapping):
        value = value.get("protocol_extensions") or value.get("extensions") or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        return set()
    return {key for item in value if (key := _protocol_key(item))}


def normalize_capabilities(value) -> set[str]:
    if isinstance(value, Mapping):
        value = value.get("capabilities") or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def normalize_protocols(value) -> set[str]:
    if isinstance(value, Mapping):
        value = value.get("supported_protocols") or value.get("protocols") or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        return set()
    return {key for item in value if (key := _protocol_key(item))}


def resolve_dlc_load_report(protocol_extensions=None, capabilities=None, supported_protocols=None) -> list[dict]:
    """Return deterministic DLC/extension loading decisions.

    Base modules are always eligible. Companion protocol modules require both
    an explicit manifest declaration, base protocol support, and every
    capability listed by the DLC descriptor. The report is metadata only; it
    never executes a tool.
    """
    requested = normalize_protocol_extensions(protocol_extensions)
    available_capabilities = normalize_capabilities(capabilities)
    supported = normalize_protocols(supported_protocols)
    report = []
    for descriptor in DLC_DESCRIPTORS.values():
        item = dict(descriptor)
        extension = descriptor.get("optional_extension")
        if not extension:
            item.update({"load_status": "enabled", "extension": None})
            report.append(item)
            continue

        required = [str(cap).strip() for cap in descriptor.get("optional_extension_required_capabilities") or [] if str(cap).strip()]
        missing = [cap for cap in required if cap not in available_capabilities]
        declared = _protocol_key(extension) in requested
        protocol_supported = _protocol_key(extension) in supported
        module_name = descriptor.get("optional_extension_module")
        if not declared:
            status = "not_requested"
        elif not protocol_supported:
            status = "blocked_missing_protocol"
        elif missing:
            status = "blocked_missing_capabilities"
        elif module_name not in _EXTENSION_MODULES:
            status = "unimplemented"
        else:
            status = "enabled"
        item["load_status"] = "enabled"
        item["extension"] = {
            "id": extension,
            "declared": declared,
            "protocol_supported": protocol_supported,
            "module": module_name,
            "required_capabilities": required,
            "missing_capabilities": missing,
            "status": status,
        }
        report.append(item)
    return report


def register_media_modules(registry, protocol_extensions=None, capabilities=None, supported_protocols=None):
    registry._dlc_report = resolve_dlc_load_report(protocol_extensions, capabilities, supported_protocols)
    for module in _MODULES:
        module.register(registry)
        descriptor = DLC_DESCRIPTORS.get(module.DLC_ID, {})
        for tool_name in module.TOOLS:
            registry._tool_dlc[tool_name] = {
                "id": module.DLC_ID,
                "kind": descriptor.get("kind", "core"),
                "protocol": module.DLC_PROTOCOL,
                "optional_extension": descriptor.get("optional_extension"),
            }

    # Companion modules are deliberately opt-in. Keeping this loop separate
    # prevents a future CRCP implementation from changing ordinary FARP cards.
    for descriptor in DLC_DESCRIPTORS.values():
        module_name = descriptor.get("optional_extension_module")
        module = _EXTENSION_MODULES.get(module_name)
        if not module:
            continue
        decision = next((item.get("extension") for item in registry._dlc_report if item.get("id") == descriptor.get("id")), None)
        if not decision or decision.get("status") != "enabled":
            continue
        module.register(registry)
        for tool_name in module.TOOLS:
            registry._tool_dlc[tool_name] = {
                "id": descriptor.get("id"),
                "kind": descriptor.get("kind", "dlc"),
                "protocol": module.DLC_PROTOCOL,
                "extends": descriptor.get("protocol"),
            }
