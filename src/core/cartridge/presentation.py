"""Defaults for cartridge-owned CF-CRE@2 presentation contracts."""

from __future__ import annotations

from copy import deepcopy


SETTINGS_SCHEMA = "cartridgeflow.cartridge_settings.v1"
SETTINGS_BINDINGS_SCHEMA = "cartridgeflow.cartridge_settings_bindings.v1"
UI_SCHEMA = "cartridgeflow.cartridge_ui.v1"


def default_settings_contract() -> dict:
    return {"schema": SETTINGS_SCHEMA, "storage_scope": "cartridge", "fields": []}


def default_settings_bindings() -> dict:
    return {"schema": SETTINGS_BINDINGS_SCHEMA, "bindings": []}


def default_ui_contract() -> dict:
    return {"schema": UI_SCHEMA, "mode": "none", "host_capabilities": []}


def without_node_settings(settings: dict, bindings: dict, node_id: str) -> tuple[dict, dict]:
    """Remove settings owned only by one deleted process node."""
    next_settings = deepcopy(settings)
    next_bindings = deepcopy(bindings)
    binding_items = next_bindings.get("bindings") if isinstance(next_bindings.get("bindings"), list) else []
    removed_ids = {
        str(item.get("setting_id"))
        for item in binding_items
        if isinstance(item, dict)
        and isinstance(item.get("target"), dict)
        and str(item["target"].get("node_id")) == str(node_id)
    }
    remaining = [
        item for item in binding_items
        if not (
            isinstance(item, dict)
            and isinstance(item.get("target"), dict)
            and str(item["target"].get("node_id")) == str(node_id)
        )
    ]
    retained_ids = {
        str(item.get("setting_id"))
        for item in remaining
        if isinstance(item, dict) and item.get("setting_id")
    }
    orphaned_ids = removed_ids - retained_ids
    fields = next_settings.get("fields") if isinstance(next_settings.get("fields"), list) else []
    next_settings["fields"] = [
        item for item in fields
        if not (isinstance(item, dict) and str(item.get("id")) in orphaned_ids)
    ]
    next_bindings["bindings"] = remaining
    return next_settings, next_bindings
