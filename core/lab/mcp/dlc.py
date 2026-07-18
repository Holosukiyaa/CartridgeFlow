from __future__ import annotations

from . import media_core, pixel_episode, short_video, spatial, series_3d


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
    "dlc.series_3d_episode_factory": {
        "id": "dlc.series_3d_episode_factory", "protocol": "CF-FARP@0.4", "optional_extension": "CF-CRCP@0.1", "kind": "dlc", "enabled_by_default": True, "modules": ["series_3d"]
    },
}
_MODULES = [media_core, pixel_episode, short_video, spatial, series_3d]


def register_media_modules(registry):
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
