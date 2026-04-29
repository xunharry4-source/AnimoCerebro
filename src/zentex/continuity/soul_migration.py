"""G34 encrypted soul migration, continuity restore, and standby takeover."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel, ConfigDict, Field


UTC = timezone.utc
KDF_ITERATIONS = 200_000


class SnapshotExportRequest(BaseModel):
    """Request to export a complete encrypted soul snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_instance_id: str
    target_instance_id: str
    operator_id: str
    passphrase: str = Field(min_length=12)
    identity_kernel: dict[str, Any]
    memory_snapshot: list[dict[str, Any]]
    goal_tree: dict[str, Any]
    audit_chain_refs: list[str] = Field(min_length=1)


class EncryptedSoulBackupPackage(BaseModel):
    """Encrypted G34 backup package that must not expose plaintext identity data."""

    model_config = ConfigDict(extra="forbid")

    feature_code: str = "G34"
    package_id: str = Field(default_factory=lambda: f"g34-backup-{uuid4().hex[:12]}")
    source_instance_id: str
    target_instance_id: str
    encryption: str = "AESGCM-256"
    kdf: str = f"PBKDF2HMAC-SHA256-{KDF_ITERATIONS}"
    salt_b64: str
    nonce_b64: str
    aad: str
    ciphertext_b64: str
    plaintext_sha256: str
    manifest: dict[str, Any]
    signature: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContinuityCheck(BaseModel):
    """Continuity verification result for a restored backup."""

    model_config = ConfigDict(extra="forbid")

    signature_verified: bool
    integrity_verified: bool
    target_binding_verified: bool
    identity_fields_verified: bool
    memory_hash_verified: bool
    audit_chain_refs_present: bool
    allowed: bool
    violations: list[str] = Field(default_factory=list)


class SnapshotRestoreRequest(BaseModel):
    """Request to restore an encrypted soul backup on the target instance."""

    model_config = ConfigDict(extra="forbid")

    package: EncryptedSoulBackupPackage
    target_instance_id: str
    operator_id: str
    passphrase: str = Field(min_length=12)


class SnapshotRestoreRecord(BaseModel):
    """Persisted restore result."""

    model_config = ConfigDict(extra="forbid")

    restore_id: str = Field(default_factory=lambda: f"g34-restore-{uuid4().hex[:12]}")
    package_id: str
    target_instance_id: str
    operator_id: str
    status: str = Field(pattern="^(restored|blocked)$")
    continuity_check: ContinuityCheck
    restored_snapshot: dict[str, Any] | None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HeartbeatRecord(BaseModel):
    """Observed heartbeat for primary or standby instances."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    role: str = Field(pattern="^(primary|standby)$")
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field(default="online", pattern="^(online|degraded|offline)$")


class TakeoverAuthorizationRequest(BaseModel):
    """Manual authorization required before standby takeover can commit."""

    model_config = ConfigDict(extra="forbid")

    primary_instance_id: str
    standby_instance_id: str
    operator_id: str
    reason: str = Field(min_length=1)


class TakeoverAuthorization(BaseModel):
    """Authorization receipt for a standby takeover."""

    model_config = ConfigDict(extra="forbid")

    authorization_id: str = Field(default_factory=lambda: f"g34-takeover-auth-{uuid4().hex[:12]}")
    primary_instance_id: str
    standby_instance_id: str
    operator_id: str
    reason: str
    takeover_token: str = Field(default_factory=lambda: f"takeover-token-{uuid4().hex[:16]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TakeoverStatus(BaseModel):
    """Standby takeover readiness decision."""

    model_config = ConfigDict(extra="forbid")

    primary_instance_id: str
    standby_instance_id: str
    status: str = Field(pattern="^(blocked|ready|committed)$")
    heartbeat_age_seconds: float | None
    heartbeat_timeout_seconds: float
    authorization_id: str | None
    takeover_token: str | None
    reasons: list[str]
    manual_commit_required: bool


class TakeoverCommitRequest(BaseModel):
    """Request to commit an already authorized standby takeover."""

    model_config = ConfigDict(extra="forbid")

    primary_instance_id: str
    standby_instance_id: str
    takeover_token: str
    operator_id: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    heartbeat_timeout_seconds: float = Field(default=30.0, gt=0)


class MigrationAuditEvent(BaseModel):
    """Audit event emitted by the G34 migration manager."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"g34-audit-{uuid4().hex[:12]}")
    action: str
    detail: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SoulMigrationManager:
    """Encrypted continuity manager for G34 soul migration and hot standby takeover."""

    def __init__(self) -> None:
        self._backups: dict[str, EncryptedSoulBackupPackage] = {}
        self._restores: dict[str, SnapshotRestoreRecord] = {}
        self._heartbeats: dict[str, HeartbeatRecord] = {}
        self._authorizations: dict[tuple[str, str], TakeoverAuthorization] = {}
        self._takeover_commits: dict[tuple[str, str], TakeoverStatus] = {}
        self._audit_events: list[MigrationAuditEvent] = []

    def export_snapshot(self, request: SnapshotExportRequest) -> EncryptedSoulBackupPackage:
        """Export identity, memory, goals, and audit refs as an encrypted package."""

        self._validate_snapshot_components(request)
        plaintext = {
            "feature_code": "G34",
            "source_instance_id": request.source_instance_id,
            "target_instance_id": request.target_instance_id,
            "identity_kernel": request.identity_kernel,
            "memory_snapshot": request.memory_snapshot,
            "goal_tree": request.goal_tree,
            "audit_chain_refs": request.audit_chain_refs,
            "exported_by": request.operator_id,
            "exported_at": datetime.now(UTC).isoformat(),
        }
        plaintext_bytes = _canonical_json(plaintext).encode("utf-8")
        plaintext_hash = hashlib.sha256(plaintext_bytes).hexdigest()
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = _derive_key(request.passphrase, salt)
        aad = self._aad(request.source_instance_id, request.target_instance_id)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext_bytes, aad.encode("utf-8"))
        manifest = self._manifest_for(request, plaintext_hash)
        unsigned = {
            "feature_code": "G34",
            "source_instance_id": request.source_instance_id,
            "target_instance_id": request.target_instance_id,
            "encryption": "AESGCM-256",
            "kdf": f"PBKDF2HMAC-SHA256-{KDF_ITERATIONS}",
            "salt_b64": _b64(salt),
            "nonce_b64": _b64(nonce),
            "aad": aad,
            "ciphertext_b64": _b64(ciphertext),
            "plaintext_sha256": plaintext_hash,
            "manifest": manifest,
        }
        package = EncryptedSoulBackupPackage(
            **unsigned,
            signature=_signature(key, unsigned),
        )
        self._backups[package.package_id] = package
        self._audit(
            "export",
            {
                "package_id": package.package_id,
                "source_instance_id": request.source_instance_id,
                "target_instance_id": request.target_instance_id,
                "operator_id": request.operator_id,
                "plaintext_exposed": False,
            },
        )
        return package

    def restore_snapshot(self, request: SnapshotRestoreRequest) -> SnapshotRestoreRecord:
        """Restore an encrypted backup only after signature, integrity, and binding checks pass."""

        package = request.package
        snapshot = self._decrypt_package(
            package,
            passphrase=request.passphrase,
            target_instance_id=request.target_instance_id,
        )
        continuity_check = self._continuity_check(package, snapshot, request.target_instance_id)
        if not continuity_check.allowed:
            record = SnapshotRestoreRecord(
                package_id=package.package_id,
                target_instance_id=request.target_instance_id,
                operator_id=request.operator_id,
                status="blocked",
                continuity_check=continuity_check,
                restored_snapshot=None,
            )
            self._restores[record.restore_id] = record
            self._audit("restore_blocked", {"restore_id": record.restore_id, "violations": continuity_check.violations})
            return record
        record = SnapshotRestoreRecord(
            package_id=package.package_id,
            target_instance_id=request.target_instance_id,
            operator_id=request.operator_id,
            status="restored",
            continuity_check=continuity_check,
            restored_snapshot=snapshot,
        )
        self._restores[record.restore_id] = record
        self._audit(
            "restore",
            {
                "restore_id": record.restore_id,
                "package_id": package.package_id,
                "target_instance_id": request.target_instance_id,
                "operator_id": request.operator_id,
            },
        )
        return record

    def record_heartbeat(self, heartbeat: HeartbeatRecord) -> HeartbeatRecord:
        """Record a real heartbeat observation for takeover evaluation."""

        normalized = heartbeat.model_copy(update={"observed_at": _as_utc(heartbeat.observed_at)})
        self._heartbeats[normalized.instance_id] = normalized
        self._audit(
            "heartbeat",
            {
                "instance_id": normalized.instance_id,
                "role": normalized.role,
                "status": normalized.status,
                "observed_at": normalized.observed_at.isoformat(),
            },
        )
        return normalized

    def authorize_takeover(self, request: TakeoverAuthorizationRequest) -> TakeoverAuthorization:
        """Create the explicit authorization required for standby takeover."""

        authorization = TakeoverAuthorization(**request.model_dump())
        self._authorizations[(request.primary_instance_id, request.standby_instance_id)] = authorization
        self._audit(
            "takeover_authorized",
            {
                "authorization_id": authorization.authorization_id,
                "primary_instance_id": request.primary_instance_id,
                "standby_instance_id": request.standby_instance_id,
                "operator_id": request.operator_id,
                "reason": request.reason,
            },
        )
        return authorization

    def evaluate_takeover(
        self,
        *,
        primary_instance_id: str,
        standby_instance_id: str,
        observed_at: datetime | None = None,
        heartbeat_timeout_seconds: float = 30.0,
    ) -> TakeoverStatus:
        """Evaluate standby takeover readiness without committing automatically."""

        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be > 0")
        committed = self._takeover_commits.get((primary_instance_id, standby_instance_id))
        if committed is not None:
            return committed
        now = _as_utc(observed_at or datetime.now(UTC))
        primary = self._heartbeats.get(primary_instance_id)
        authorization = self._authorizations.get((primary_instance_id, standby_instance_id))
        reasons: list[str] = []
        age: float | None = None
        if primary is None:
            reasons.append("primary_heartbeat_missing")
        else:
            age = max(0.0, (now - _as_utc(primary.observed_at)).total_seconds())
            if age <= heartbeat_timeout_seconds and primary.status != "offline":
                reasons.append("primary_heartbeat_still_fresh")
        if standby_instance_id not in self._heartbeats:
            reasons.append("standby_heartbeat_missing")
        if authorization is None:
            reasons.append("takeover_authorization_missing")

        ready = not reasons or reasons == ["primary_heartbeat_still_fresh"] and False
        if primary is not None and age is not None and (age > heartbeat_timeout_seconds or primary.status == "offline"):
            timeout_ready = True
        else:
            timeout_ready = False
        ready = timeout_ready and standby_instance_id in self._heartbeats and authorization is not None
        if ready:
            reasons = ["primary_heartbeat_expired", "manual_authorization_present", "standby_heartbeat_present"]
        return TakeoverStatus(
            primary_instance_id=primary_instance_id,
            standby_instance_id=standby_instance_id,
            status="ready" if ready else "blocked",
            heartbeat_age_seconds=age,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            authorization_id=authorization.authorization_id if authorization else None,
            takeover_token=authorization.takeover_token if authorization and ready else None,
            reasons=reasons,
            manual_commit_required=ready,
        )

    def commit_takeover(self, request: TakeoverCommitRequest) -> TakeoverStatus:
        """Commit standby takeover only with a valid token and expired primary heartbeat."""

        status = self.evaluate_takeover(
            primary_instance_id=request.primary_instance_id,
            standby_instance_id=request.standby_instance_id,
            observed_at=request.observed_at,
            heartbeat_timeout_seconds=request.heartbeat_timeout_seconds,
        )
        authorization = self._authorizations.get((request.primary_instance_id, request.standby_instance_id))
        if status.status != "ready" or authorization is None:
            raise ValueError("takeover is not ready")
        if not hmac.compare_digest(request.takeover_token, authorization.takeover_token):
            raise ValueError("takeover token verification failed")
        committed = status.model_copy(update={"status": "committed", "manual_commit_required": False})
        self._takeover_commits[(request.primary_instance_id, request.standby_instance_id)] = committed
        self._audit(
            "takeover_committed",
            {
                "primary_instance_id": request.primary_instance_id,
                "standby_instance_id": request.standby_instance_id,
                "operator_id": request.operator_id,
                "authorization_id": authorization.authorization_id,
            },
        )
        return committed

    def get_backup(self, package_id: str) -> EncryptedSoulBackupPackage:
        package = self._backups.get(package_id)
        if package is None:
            raise KeyError(f"Unknown package_id: {package_id}")
        return package

    def get_restore(self, restore_id: str) -> SnapshotRestoreRecord:
        record = self._restores.get(restore_id)
        if record is None:
            raise KeyError(f"Unknown restore_id: {restore_id}")
        return record

    def list_audit_events(self) -> list[MigrationAuditEvent]:
        return list(self._audit_events)

    def _decrypt_package(
        self,
        package: EncryptedSoulBackupPackage,
        *,
        passphrase: str,
        target_instance_id: str,
    ) -> dict[str, Any]:
        salt = _unb64(package.salt_b64)
        key = _derive_key(passphrase, salt)
        unsigned = package.model_dump(mode="json", exclude={"package_id", "signature", "created_at"})
        expected_signature = _signature(key, unsigned)
        if not hmac.compare_digest(expected_signature, package.signature):
            raise ValueError("backup package signature verification failed")
        if target_instance_id != package.target_instance_id:
            raise ValueError("backup package target binding does not match restore target")
        try:
            plaintext = AESGCM(key).decrypt(
                _unb64(package.nonce_b64),
                _unb64(package.ciphertext_b64),
                package.aad.encode("utf-8"),
            )
        except InvalidTag as exc:
            raise ValueError("backup package decryption failed: invalid authentication tag") from exc
        digest = hashlib.sha256(plaintext).hexdigest()
        if not hmac.compare_digest(digest, package.plaintext_sha256):
            raise ValueError("backup package plaintext hash mismatch")
        snapshot = json.loads(plaintext.decode("utf-8"))
        if snapshot.get("target_instance_id") != target_instance_id:
            raise ValueError("decrypted snapshot target binding mismatch")
        return snapshot

    def _continuity_check(
        self,
        package: EncryptedSoulBackupPackage,
        snapshot: dict[str, Any],
        target_instance_id: str,
    ) -> ContinuityCheck:
        violations: list[str] = []
        identity = snapshot.get("identity_kernel") or {}
        identity_fields_verified = all(identity.get(key) for key in ("role", "mission", "core_values"))
        if not identity_fields_verified:
            violations.append("identity_required_fields_missing")
        memory_hash_verified = _hash(snapshot.get("memory_snapshot")) == package.manifest.get("memory_hash")
        if not memory_hash_verified:
            violations.append("memory_hash_mismatch")
        target_binding_verified = (
            package.target_instance_id == target_instance_id
            and snapshot.get("target_instance_id") == target_instance_id
            and package.aad == self._aad(str(snapshot.get("source_instance_id")), target_instance_id)
        )
        if not target_binding_verified:
            violations.append("target_binding_mismatch")
        audit_chain_refs_present = bool(snapshot.get("audit_chain_refs"))
        if not audit_chain_refs_present:
            violations.append("audit_chain_refs_missing")
        allowed = not violations
        return ContinuityCheck(
            signature_verified=True,
            integrity_verified=True,
            target_binding_verified=target_binding_verified,
            identity_fields_verified=identity_fields_verified,
            memory_hash_verified=memory_hash_verified,
            audit_chain_refs_present=audit_chain_refs_present,
            allowed=allowed,
            violations=violations,
        )

    @staticmethod
    def _aad(source_instance_id: str, target_instance_id: str) -> str:
        return f"g34:{source_instance_id}->{target_instance_id}"

    @staticmethod
    def _validate_snapshot_components(request: SnapshotExportRequest) -> None:
        identity = request.identity_kernel
        if not all(identity.get(key) for key in ("role", "mission", "core_values")):
            raise ValueError("identity_kernel requires role, mission, and core_values")
        if "continuity_lock" not in identity:
            raise ValueError("identity_kernel requires continuity_lock")
        if not isinstance(request.memory_snapshot, list):
            raise ValueError("memory_snapshot must be a list")
        if not request.goal_tree:
            raise ValueError("goal_tree must be a non-empty object")
        if request.source_instance_id == request.target_instance_id:
            raise ValueError("source_instance_id and target_instance_id must be different")

    @staticmethod
    def _manifest_for(request: SnapshotExportRequest, plaintext_hash: str) -> dict[str, Any]:
        return {
            "plaintext_sha256": plaintext_hash,
            "identity_hash": _hash(request.identity_kernel),
            "memory_hash": _hash(request.memory_snapshot),
            "goal_tree_hash": _hash(request.goal_tree),
            "audit_chain_hash": _hash(request.audit_chain_refs),
            "memory_record_count": len(request.memory_snapshot),
            "goal_root_id": str(request.goal_tree.get("goal_id") or request.goal_tree.get("id") or ""),
            "audit_ref_count": len(request.audit_chain_refs),
            "target_binding": request.target_instance_id,
            "continuity_requirements": [
                "signature_verified",
                "integrity_verified",
                "target_binding_verified",
                "identity_fields_verified",
                "memory_hash_verified",
                "audit_chain_refs_present",
            ],
        }

    def _audit(self, action: str, detail: dict[str, Any]) -> None:
        self._audit_events.append(MigrationAuditEvent(action=action, detail=detail))


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise ValueError("passphrase must be at least 12 characters")
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    ).derive(passphrase.encode("utf-8"))


def _signature(key: bytes, unsigned_package: dict[str, Any]) -> str:
    body = _canonical_json(unsigned_package).encode("utf-8")
    return "hmac-sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

