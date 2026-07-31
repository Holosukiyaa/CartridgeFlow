"""Ed25519 signing and local trust records for CF-CRE@1 archives."""

from __future__ import annotations

import base64
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.data_paths import DATA_ROOT, USER_CONFIG_DIR


SIGNATURE_SCHEMA = "cartridgeflow.release_signature.v1"
TRUST_STORE_SCHEMA = "cartridgeflow.release_trust_store.v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ReleaseSigningError(ValueError):
    """Raised when a CRE signing key or signature is invalid."""


@dataclass(frozen=True)
class ReleaseSigningIdentity:
    key_id: str
    private_key: Ed25519PrivateKey
    public_key: bytes


def generate_signing_identity(key_id: str = "ephemeral.release") -> ReleaseSigningIdentity:
    if not _ID.fullmatch(key_id):
        raise ReleaseSigningError("release signing key_id must be a stable identifier")
    private_key = Ed25519PrivateKey.generate()
    return ReleaseSigningIdentity(
        key_id=key_id,
        private_key=private_key,
        public_key=private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ),
    )


def ensure_development_signing_identity(root: str | Path, publisher_id: str) -> ReleaseSigningIdentity:
    """Provision one local development signer and explicitly trust its public key."""
    if not _ID.fullmatch(publisher_id):
        raise ReleaseSigningError("publisher_id must be a stable identifier")
    base = Path(root).resolve()
    key_id = f"{publisher_id}.development"
    key_dir = _release_keys_dir(base)
    key_path = key_dir / f"{publisher_id}.ed25519.pem"
    if key_path.is_file():
        try:
            private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        except (ValueError, TypeError) as exc:
            raise ReleaseSigningError("development release signing key is unreadable") from exc
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ReleaseSigningError("development release signing key must be Ed25519")
    else:
        private_key = Ed25519PrivateKey.generate()
        key_path.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    identity = ReleaseSigningIdentity(key_id=key_id, private_key=private_key, public_key=public_key)
    trust_store = _load_trust_store(base)
    keys = trust_store["keys"]
    entry = {
        "key_id": key_id,
        "publisher_id": publisher_id,
        "algorithm": "ed25519",
        "public_key": _encode(public_key),
    }
    trust_store["keys"] = [item for item in keys if item.get("key_id") != key_id] + [entry]
    _trust_store_path(base).write_text(json.dumps(trust_store, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return identity


def trusted_public_keys(root: str | Path) -> dict[str, str]:
    """Return key_id -> raw-public-key base64 from the local, user-owned trust store."""
    return {
        str(item["key_id"]): str(item["public_key"])
        for item in _load_trust_store(Path(root).resolve())["keys"]
        if _ID.fullmatch(str(item.get("key_id") or "")) and isinstance(item.get("public_key"), str)
    }


def build_signature_metadata(identity: ReleaseSigningIdentity, release_bytes: bytes, hashes_bytes: bytes) -> dict:
    signature = identity.private_key.sign(signing_payload(release_bytes, hashes_bytes))
    return {
        "schema": SIGNATURE_SCHEMA,
        "algorithm": "ed25519",
        "key_id": identity.key_id,
        "public_key": _encode(identity.public_key),
        "signature": _encode(signature),
        "signed_files": ["release.manifest.json", "hashes.json"],
    }


def verify_signature_metadata(
    release: dict,
    bundle_files: Mapping[str, bytes],
    *,
    trusted_keys: Mapping[str, str] | None = None,
) -> dict:
    """Verify the publisher signature and report trust separately from cryptographic validity."""
    descriptor = next((item for item in release.get("signatures") or [] if isinstance(item, dict) and item.get("role") == "publisher"), None)
    if not isinstance(descriptor, dict):
        return _failure("cre_publisher_signature_missing", "release has no publisher signature descriptor")
    path = str(descriptor.get("path") or "")
    key_id = str(descriptor.get("key_id") or "")
    if not _ID.fullmatch(key_id) or path not in bundle_files:
        return _failure("cre_signature_file_missing", "publisher signature descriptor does not name a bundled signature file", key_id=key_id)
    try:
        metadata = json.loads(bundle_files[path].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failure("cre_signature_metadata_invalid", "publisher signature metadata must be UTF-8 JSON", key_id=key_id)
    if not isinstance(metadata, dict) or metadata.get("schema") != SIGNATURE_SCHEMA:
        return _failure("cre_signature_metadata_invalid", "publisher signature metadata has an unknown schema", key_id=key_id)
    if metadata.get("algorithm") != "ed25519" or metadata.get("key_id") != key_id:
        return _failure("cre_signature_metadata_invalid", "publisher signature metadata does not match its descriptor", key_id=key_id)
    if metadata.get("signed_files") != ["release.manifest.json", "hashes.json"]:
        return _failure("cre_signature_coverage_invalid", "publisher signature must cover release.manifest.json and hashes.json", key_id=key_id)
    try:
        public_key = _decode(metadata.get("public_key"), 32)
        signature = _decode(metadata.get("signature"), 64)
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            signing_payload(bundle_files["release.manifest.json"], bundle_files["hashes.json"]),
        )
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return _failure("cre_signature_verification_failed", "publisher Ed25519 signature verification failed", key_id=key_id)
    expected = (trusted_keys or {}).get(key_id)
    trusted = bool(expected and _decode(expected, 32) == public_key)
    return {
        "ok": True,
        "findings": [],
        "key_id": key_id,
        "trusted": trusted,
        "trust_status": "trusted" if trusted else "untrusted",
        "public_key": _encode(public_key),
    }


def signing_payload(release_bytes: bytes, hashes_bytes: bytes) -> bytes:
    return release_bytes + b"\n" + hashes_bytes


def _trust_store_path(root: Path) -> Path:
    return _release_keys_dir(root) / "trusted_publishers.json"


def _release_keys_dir(root: Path) -> Path:
    """Use the canonical user config root and repair the short-lived doubled-data path."""
    canonical = root / USER_CONFIG_DIR / "release_keys"
    legacy = root / DATA_ROOT / USER_CONFIG_DIR / "release_keys"
    if not canonical.exists() and legacy.is_dir():
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(canonical))
    canonical.mkdir(parents=True, exist_ok=True)
    return canonical


def _load_trust_store(root: Path) -> dict:
    path = _trust_store_path(root)
    if not path.is_file():
        return {"schema": TRUST_STORE_SCHEMA, "keys": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseSigningError("release trust store is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != TRUST_STORE_SCHEMA or not isinstance(value.get("keys"), list):
        raise ReleaseSigningError("release trust store has an unknown schema")
    return value


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, size: int) -> bytes:
    if not isinstance(value, str):
        raise ValueError("signature value must be base64 text")
    decoded = base64.b64decode(value, validate=True)
    if len(decoded) != size:
        raise ValueError("signature value has an invalid length")
    return decoded


def _failure(code: str, message: str, *, key_id: str = "") -> dict:
    return {
        "ok": False,
        "findings": [{"severity": "blocker", "code": code, "message": message, "path": "signatures/publisher.ed25519.json"}],
        "key_id": key_id,
        "trusted": False,
        "trust_status": "invalid",
        "public_key": "",
    }
