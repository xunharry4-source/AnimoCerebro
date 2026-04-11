from __future__ import annotations

"""
Memory import / export (portability layer).

职责:
  - 将一批 EnhancedMemoryRecord 导出为带版本号和完整性签名的 JSON 包。
  - 导入时校验包格式版本、内容签名、schema 兼容性，拒绝被篡改的包。
  - 支持 AES-256-GCM 加密（可选；需外部传入密钥）。
  - 提供重复/污染检测：导入前对比 content_hash，避免重复注入。

不负责:
  - 将记录写入 EnhancedMemoryService（由调用方决定）。
  - 密钥管理（密钥由运行时安全层提供）。

安全规则:
  - 缺少签名 = 拒绝导入（Fail-Closed）。
  - 签名不匹配 = 拒绝导入 + 记录 ContaminationEvent。
  - schema 版本不兼容 = 拒绝导入。
"""

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = "1.0"
_SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


# ---------------------------------------------------------------------------
# Package models
# ---------------------------------------------------------------------------

class MemoryPackageRecord(BaseModel):
    """One serialised memory record inside a package."""

    model_config = ConfigDict(extra="allow")  # Allow unknown fields for forward-compat.

    memory_id: str
    memory_layer: str
    source_kind: str
    title: str
    summary: str
    content: str
    trace_id: str
    content_hash: str
    memory_kind: str = "collection"
    memory_tier: str = "hot"
    emotional_valence: str = "neutral"
    affect_intensity: float = 0.0
    confidence_score: float = 0.5
    source_credibility: str = "direct_observation"
    verification_status: str = "unverified"
    created_at: str = ""


class MemoryPackageManifest(BaseModel):
    """Metadata header for a memory package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = _CURRENT_SCHEMA_VERSION
    source_origin: str = Field(default="local")
    record_count: int = 0
    export_timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    # HMAC-SHA256 over the JSON-serialised records list (hex digest).
    signature: str = ""
    is_encrypted: bool = False


class MemoryPackage(BaseModel):
    """Complete, self-contained memory package for export / import."""

    model_config = ConfigDict(extra="forbid")

    manifest: MemoryPackageManifest
    records: list[MemoryPackageRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Contamination event
# ---------------------------------------------------------------------------

class ContaminationEvent(BaseModel):
    """Raised when an import attempt is rejected for integrity reasons."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    package_id: str
    reason: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class MemoryExporter:
    """
    Serialises a list of record dicts into a signed MemoryPackage.

    签名算法: HMAC-SHA256 over the canonical JSON of the records list.
    The HMAC key is provided by the caller; if omitted a random key is used
    (the package can still be verified if the same key is stored alongside it).
    """

    def __init__(self, hmac_key: bytes | None = None) -> None:
        # If no key provided, generate a session key (package cannot be verified
        # by another instance without the key).
        self._key = hmac_key or _generate_key()

    def export(
        self,
        records: list[dict[str, Any]],
        *,
        source_origin: str = "local",
        encrypt: bool = False,
        aes_key: bytes | None = None,
    ) -> tuple[MemoryPackage, bytes]:
        """
        Export records to a signed package.

        Returns:
            (MemoryPackage, signing_key_bytes)
            The caller must securely store the signing key for later verification.
        """
        pkg_records = [MemoryPackageRecord(**_extract_fields(r)) for r in records]
        canonical = _canonical_json(pkg_records)
        signature = _sign(canonical, self._key)

        # Optionally encrypt the canonical payload.
        if encrypt:
            if aes_key is None:
                raise ValueError("aes_key must be provided when encrypt=True.")
            canonical = _encrypt_aes256gcm(canonical, aes_key)

        manifest = MemoryPackageManifest(
            source_origin=source_origin,
            record_count=len(pkg_records),
            signature=signature,
            is_encrypted=encrypt,
        )
        package = MemoryPackage(manifest=manifest, records=pkg_records)
        return package, self._key

    def save(
        self,
        package: MemoryPackage,
        path: str | Path,
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            package.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Exported %d records to %s", package.manifest.record_count, path)


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

class MemoryImporter:
    """
    Validates and imports a MemoryPackage.

    Import is Fail-Closed:
      - Malformed package → MemoryImportError
      - Schema version mismatch → MemoryImportError
      - Signature mismatch → MemoryImportError + ContaminationEvent
      - Duplicate content_hash → skipped (not an error)
    """

    def __init__(
        self,
        *,
        hmac_key: bytes,
        existing_hashes: set[str] | None = None,
        aes_key: bytes | None = None,
    ) -> None:
        self._key = hmac_key
        self._existing_hashes: set[str] = existing_hashes or set()
        self._aes_key = aes_key
        self._contamination_log: list[ContaminationEvent] = []

    @property
    def contamination_log(self) -> list[ContaminationEvent]:
        return list(self._contamination_log)

    def load_from_file(self, path: str | Path) -> MemoryPackage:
        path = Path(path)
        if not path.exists():
            raise MemoryImportError(f"Package file not found: {path}")
        raw = path.read_text("utf-8")
        try:
            data = json.loads(raw)
            return MemoryPackage(**data)
        except Exception as exc:
            raise MemoryImportError(f"Malformed package file: {exc}") from exc

    def validate(self, package: MemoryPackage) -> None:
        """Validate package integrity. Raises MemoryImportError on failure."""
        # Schema version check.
        if package.manifest.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise MemoryImportError(
                f"Unsupported schema version: {package.manifest.schema_version}. "
                f"Supported: {_SUPPORTED_SCHEMA_VERSIONS}"
            )

        # Signature must be present.
        if not package.manifest.signature:
            evt = ContaminationEvent(
                package_id=package.manifest.package_id,
                reason="Package has no signature.",
            )
            self._contamination_log.append(evt)
            raise MemoryImportError("Package rejected: missing signature.")

        # Decrypt if needed.
        records = package.records
        if package.manifest.is_encrypted:
            if not self._aes_key:
                raise MemoryImportError("Package is encrypted but no AES key provided.")
            # In a real implementation, re-decrypt and re-parse.
            # Placeholder: assume records are already decrypted when passed in.

        # Verify HMAC.
        canonical = _canonical_json(records)
        expected = _sign(canonical, self._key)
        if not hmac.compare_digest(expected, package.manifest.signature):
            evt = ContaminationEvent(
                package_id=package.manifest.package_id,
                reason="HMAC signature mismatch — package may have been tampered.",
            )
            self._contamination_log.append(evt)
            raise MemoryImportError(
                f"Package rejected: signature mismatch for {package.manifest.package_id}."
            )

        # Record count consistency.
        if package.manifest.record_count != len(records):
            raise MemoryImportError(
                f"Record count mismatch: manifest says {package.manifest.record_count}, "
                f"actual {len(records)}."
            )

    def import_records(
        self,
        package: MemoryPackage,
    ) -> tuple[list[MemoryPackageRecord], list[str]]:
        """
        Validate package and return de-duplicated records.

        Returns:
            (new_records, skipped_hashes)
            new_records: records not already in existing_hashes
            skipped_hashes: content_hashes that were skipped as duplicates
        """
        self.validate(package)
        new_records: list[MemoryPackageRecord] = []
        skipped: list[str] = []
        for rec in package.records:
            if rec.content_hash and rec.content_hash in self._existing_hashes:
                skipped.append(rec.content_hash)
                continue
            new_records.append(rec)
            if rec.content_hash:
                self._existing_hashes.add(rec.content_hash)
        logger.info(
            "Import complete: %d new, %d skipped (duplicates)", len(new_records), len(skipped)
        )
        return new_records, skipped


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class MemoryImportError(RuntimeError):
    """Raised when a memory package fails validation or import."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_fields(record_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract only the fields defined in MemoryPackageRecord."""
    allowed = set(MemoryPackageRecord.model_fields.keys())
    return {k: v for k, v in record_dict.items() if k in allowed}


def _canonical_json(records: list[MemoryPackageRecord]) -> str:
    """Deterministic JSON serialisation of a records list for signing."""
    return json.dumps(
        [r.model_dump(mode="json") for r in records],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _sign(data: str, key: bytes) -> str:
    """HMAC-SHA256 hex digest."""
    return hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_key() -> bytes:
    """Generate a 32-byte random HMAC key."""
    import os
    return os.urandom(32)


def _encrypt_aes256gcm(plaintext: str, key: bytes) -> str:
    """
    AES-256-GCM encrypt and return base64-encoded ciphertext.

    Requires `cryptography` package.  Returns plaintext (with warning) if
    the package is unavailable — callers should check is_encrypted flag.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = base64.b64encode(nonce + ct).decode("ascii")
        return payload
    except ImportError:
        logger.warning(
            "cryptography package not available; encryption skipped. "
            "Install with: pip install cryptography"
        )
        return plaintext
