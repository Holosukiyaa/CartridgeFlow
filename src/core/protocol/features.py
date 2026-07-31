"""Resolve protocol capabilities from the release catalog.

Business code asks for a semantic capability instead of enumerating release
numbers.  A new release can therefore retain an adapter or capability without
forcing unrelated runtime modules to change.
"""

from __future__ import annotations

from pathlib import Path

from .release_catalog import ProtocolReleaseCatalogError, load_protocol_release_catalog


_SOURCE_ROOT = Path(__file__).resolve().parents[3]


def protocol_features(protocol_id: str, version: str, root: str | Path | None = None) -> frozenset[str]:
    """Return catalog-declared capabilities, or no capabilities if unknown."""
    candidate = Path(root) if root is not None else _SOURCE_ROOT
    catalog_root = candidate if (candidate / "protocol" / "catalog" / "release_manifest.json").is_file() else _SOURCE_ROOT
    try:
        return load_protocol_release_catalog(catalog_root).features(str(protocol_id), str(version))
    except ProtocolReleaseCatalogError:
        return frozenset()


def has_protocol_feature(protocol_id: str, version: str, feature: str, root: str | Path | None = None) -> bool:
    return str(feature) in protocol_features(protocol_id, version, root)
