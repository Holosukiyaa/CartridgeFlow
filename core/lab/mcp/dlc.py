from __future__ import annotations

from . import media_core


CORE_MODULES = (media_core,)


def resolve_dlc_load_report(protocol_extensions=None, capabilities=None, supported_protocols=None) -> list[dict]:
    """Describe base-owned modules only.

    Cartridge DLCs are discovered from the active cartridge manifest by
    ``core.extensions``. They must never be imported or registered here.
    """
    return [{
        "id": media_core.DLC_ID,
        "protocol": media_core.DLC_PROTOCOL,
        "kind": "core",
        "load_status": "enabled",
        "modules": ["media_core"],
    }]


def register_media_modules(registry, protocol_extensions=None, capabilities=None, supported_protocols=None) -> None:
    registry._dlc_report = resolve_dlc_load_report(
        protocol_extensions,
        capabilities,
        supported_protocols,
    )
    for module in CORE_MODULES:
        module.register(registry)
        for tool_name in module.TOOLS:
            registry._tool_dlc[tool_name] = {
                "id": module.DLC_ID,
                "kind": "core",
                "protocol": module.DLC_PROTOCOL,
            }
