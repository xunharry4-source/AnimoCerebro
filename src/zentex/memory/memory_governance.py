from __future__ import annotations

"""G38 memory safety and experience-package governance."""

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.memory.management.classification import compute_content_hash
from zentex.memory.management.enhanced import EnhancedMemoryRecord, MemoryAuditEvent
from zentex.memory.security.encryption import AESGCMEncryptionStrategy


UTC = timezone.utc
REQUIRED_CONTAMINATION_STAGES = ("runtime_memory", "goal", "action", "execution", "reflection")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _derive_package_key(secret: str | bytes | None) -> bytes:
    material = secret
    if material is None:
        material = os.environ.get("ZENTEX_MEMORY_GOVERNANCE_PACKAGE_KEY", "zentex-memory-governance-local-development-key")
    if isinstance(material, bytes) and len(material) == 32:
        return material
    if isinstance(material, str) and len(material.encode("utf-8")) == 32:
        return material.encode("utf-8")
    raw = material if isinstance(material, bytes) else str(material).encode("utf-8")
    return hashlib.sha256(raw).digest()


class MemoryTrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    TENTATIVE = "tentative"
    VERIFIED = "verified"
    PROTECTED = "protected"
    REVOKED = "revoked"


class MemoryQuarantineStatus(str, Enum):
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    ADOPTED = "adopted"
    REVOKED = "revoked"


class MemoryImportStatus(str, Enum):
    AUTHORIZED = "authorized"
    IMPORTED = "imported"
    REVOKED = "revoked"
    EXPIRED = "expired"


class MemoryGateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_id: str = Field(min_length=1)
    gate_name: str = Field(min_length=1)
    passed: bool
    reason: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class MemoryGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    gate_results: list[MemoryGateCheck] = Field(default_factory=list)
    failed_gate_ids: list[str] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=_utc_now)


class QuarantinedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory: EnhancedMemoryRecord
    status: MemoryQuarantineStatus = MemoryQuarantineStatus.QUARANTINED
    trust_level: MemoryTrustLevel = MemoryTrustLevel.UNTRUSTED
    source_instance_id: str = Field(min_length=1)
    package_id: str | None = None
    import_id: str | None = None
    gate_decision: MemoryGateDecision
    can_recall: bool = False
    staged_at: datetime = Field(default_factory=_utc_now)
    resolved_at: datetime | None = None


class MemoryExperiencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(default_factory=lambda: str(uuid4()))
    source_instance_id: str = Field(min_length=1)
    target_instance_id: str = Field(min_length=1)
    encrypted_payload: str = Field(min_length=1)
    encryption_context: str = Field(default="g38-experience-package-v1", min_length=1)
    payload_hash: str = Field(min_length=64, max_length=64)
    binding_hash: str = Field(min_length=64, max_length=64)
    expires_at: datetime
    created_at: datetime = Field(default_factory=_utc_now)


class PackageImportGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: str = Field(default_factory=lambda: str(uuid4()))
    package_id: str = Field(min_length=1)
    source_instance_id: str = Field(min_length=1)
    target_instance_id: str = Field(min_length=1)
    authorized_by: str = Field(min_length=1)
    expires_at: datetime
    status: MemoryImportStatus = MemoryImportStatus.AUTHORIZED
    imported_memory_ids: list[str] = Field(default_factory=list)
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class PackageImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    import_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    imported_memory_ids: list[str]
    gate_decisions: list[MemoryGateDecision]


class MemoryContaminationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contamination_id: str = Field(default_factory=lambda: str(uuid4()))
    source_memory_id: str = Field(min_length=1)
    impact_graph: dict[str, list[str]]
    affected_memory_ids: list[str]
    status: str = "active"
    rollback_trace: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=_utc_now)
    resolved_at: datetime | None = None


class MemoryRollbackResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rollback_id: str = Field(default_factory=lambda: str(uuid4()))
    contamination_id: str = Field(min_length=1)
    revoked_memory_ids: list[str]
    rollback_trace: list[str]
    completed_at: datetime = Field(default_factory=_utc_now)


class MemoryRejectedError(ValueError):
    def __init__(self, message: str, decision: MemoryGateDecision) -> None:
        super().__init__(message)
        self.decision = decision


class MemoryGovernance:
    """Authoritative G38 state machine for memory package governance."""

    allowed_layers = frozenset({"semantic", "procedural", "episodic"})
    allowed_sources = frozenset({"operator", "external_import", "consolidation", "reflection", "upgrade", "learning"})
    protected_tags = frozenset({"identity_kernel", "red_line", "protected", "system_constraint"})
    forbidden_content_tokens = ("secret_token", "api_key", "identity_kernel_override", "self_rewrite")

    def __init__(self, *, instance_id: str, package_secret: str | bytes | None = None) -> None:
        self.instance_id = instance_id
        self._crypto = AESGCMEncryptionStrategy(_derive_package_key(package_secret))
        self._quarantine: dict[str, QuarantinedMemory] = {}
        self._main_memory: dict[str, QuarantinedMemory] = {}
        self._imports: dict[str, PackageImportGrant] = {}
        self._contamination: dict[str, MemoryContaminationRecord] = {}
        self._rollbacks: dict[str, MemoryRollbackResult] = {}
        self._audit: list[MemoryAuditEvent] = []
        self._lock = Lock()

    def submit_quarantined_memory(
        self,
        memory: EnhancedMemoryRecord,
        *,
        source_instance_id: str,
        contamination_chain: dict[str, list[str]],
        package_id: str | None = None,
        import_id: str | None = None,
        operator: str = "system",
    ) -> QuarantinedMemory:
        decision = self._run_nine_gates(
            memory,
            source_instance_id=source_instance_id,
            contamination_chain=contamination_chain,
            package_id=package_id,
            import_id=import_id,
        )
        status = MemoryQuarantineStatus.QUARANTINED if decision.outcome == "accepted" else MemoryQuarantineStatus.REJECTED
        entry = QuarantinedMemory(
            memory=memory,
            status=status,
            source_instance_id=source_instance_id,
            package_id=package_id,
            import_id=import_id,
            gate_decision=decision,
        )
        with self._lock:
            self._quarantine[memory.memory_id] = entry
        action = "quarantine_accepted" if status == MemoryQuarantineStatus.QUARANTINED else "quarantine_rejected"
        self._audit_event(memory.memory_id, action, f"Nine-gate outcome: {decision.outcome}.", operator, {
            "trace_id": decision.trace_id,
            "failed_gate_ids": decision.failed_gate_ids,
            "package_id": package_id,
            "import_id": import_id,
        })
        if decision.failed_gate_ids:
            raise MemoryRejectedError(
                f"Memory {memory.memory_id} rejected by G38 gates: {', '.join(decision.failed_gate_ids)}",
                decision,
            )
        return entry

    def promote_memory(
        self,
        memory_id: str,
        *,
        target_trust_level: MemoryTrustLevel,
        reviewer_id: str,
    ) -> QuarantinedMemory:
        if target_trust_level not in {MemoryTrustLevel.TENTATIVE, MemoryTrustLevel.VERIFIED, MemoryTrustLevel.PROTECTED}:
            raise ValueError(f"unsupported promotion trust level: {target_trust_level}")
        with self._lock:
            entry = self._quarantine.get(memory_id)
            if entry is None:
                raise KeyError(memory_id)
            if entry.status != MemoryQuarantineStatus.QUARANTINED:
                raise ValueError(f"memory {memory_id} is not promotable from status {entry.status.value}")
            promoted = entry.model_copy(
                update={
                    "status": MemoryQuarantineStatus.ADOPTED,
                    "trust_level": target_trust_level,
                    "can_recall": True,
                    "resolved_at": _utc_now(),
                }
            )
            self._quarantine[memory_id] = promoted
            self._main_memory[memory_id] = promoted
        self._audit_event(memory_id, "memory_promoted", f"Promoted to {target_trust_level.value}.", reviewer_id, {})
        return promoted

    def recall_memories(self, query: str, *, limit: int = 10) -> list[QuarantinedMemory]:
        needle = query.strip().lower()
        if not needle:
            return []
        with self._lock:
            rows = list(self._main_memory.values())
            revoked_imports = {
                grant.import_id for grant in self._imports.values()
                if grant.status in {MemoryImportStatus.REVOKED, MemoryImportStatus.EXPIRED}
            }
        results: list[QuarantinedMemory] = []
        for row in rows:
            haystack = " ".join([row.memory.title, row.memory.summary, row.memory.content, " ".join(row.memory.tags)]).lower()
            if (
                row.can_recall
                and row.status == MemoryQuarantineStatus.ADOPTED
                and row.trust_level != MemoryTrustLevel.REVOKED
                and row.import_id not in revoked_imports
                and needle in haystack
            ):
                results.append(row)
        return results[:limit]

    def export_package(
        self,
        memory_ids: list[str],
        *,
        target_instance_id: str,
        expires_at: datetime,
    ) -> MemoryExperiencePackage:
        with self._lock:
            records = [self._main_memory[memory_id] for memory_id in memory_ids]
        payload = {
            "records": [row.memory.model_dump(mode="json") for row in records],
            "source_instance_id": self.instance_id,
            "target_instance_id": target_instance_id,
        }
        payload_bytes = _canonical_json(payload).encode("utf-8")
        encrypted = self._crypto.encrypt(payload_bytes)
        package_id = str(uuid4())
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        binding_hash = self._package_binding_hash(
            package_id=package_id,
            source_instance_id=self.instance_id,
            target_instance_id=target_instance_id,
            payload_hash=payload_hash,
            expires_at=expires_at,
        )
        package = MemoryExperiencePackage(
            package_id=package_id,
            source_instance_id=self.instance_id,
            target_instance_id=target_instance_id,
            encrypted_payload=base64.b64encode(encrypted).decode("ascii"),
            payload_hash=payload_hash,
            binding_hash=binding_hash,
            expires_at=expires_at,
        )
        self._audit_event("*", "package_exported", "Encrypted memory package exported.", "system", {
            "package_id": package.package_id,
            "memory_ids": memory_ids,
            "target_instance_id": target_instance_id,
        })
        return package

    def authorize_package_import(
        self,
        *,
        package_id: str,
        source_instance_id: str,
        target_instance_id: str,
        expires_at: datetime,
        authorized_by: str,
    ) -> PackageImportGrant:
        if target_instance_id != self.instance_id:
            raise ValueError("package import target does not match this instance")
        grant = PackageImportGrant(
            package_id=package_id,
            source_instance_id=source_instance_id,
            target_instance_id=target_instance_id,
            authorized_by=authorized_by,
            expires_at=expires_at,
        )
        with self._lock:
            self._imports[grant.import_id] = grant
        self._audit_event("*", "import_authorized", "Package import authorized.", authorized_by, {
            "import_id": grant.import_id,
            "package_id": package_id,
        })
        return grant

    def import_package(
        self,
        package: MemoryExperiencePackage,
        *,
        import_id: str,
        contamination_chain: dict[str, list[str]],
        operator: str = "system",
    ) -> PackageImportResult:
        grant = self._require_active_grant(package, import_id=import_id)
        payload = self._decrypt_package_payload(package)
        decisions: list[MemoryGateDecision] = []
        imported_ids: list[str] = []
        for raw_record in payload["records"]:
            record = EnhancedMemoryRecord.model_validate(raw_record)
            entry = self.submit_quarantined_memory(
                record,
                source_instance_id=package.source_instance_id,
                package_id=package.package_id,
                import_id=grant.import_id,
                contamination_chain=contamination_chain,
                operator=operator,
            )
            decisions.append(entry.gate_decision)
            imported_ids.append(record.memory_id)
        with self._lock:
            updated = grant.model_copy(update={"status": MemoryImportStatus.IMPORTED, "imported_memory_ids": imported_ids})
            self._imports[grant.import_id] = updated
        self._audit_event("*", "package_imported", "Package decrypted, binding-verified, and staged.", operator, {
            "import_id": grant.import_id,
            "package_id": package.package_id,
            "imported_memory_ids": imported_ids,
        })
        return PackageImportResult(
            import_id=grant.import_id,
            package_id=package.package_id,
            imported_memory_ids=imported_ids,
            gate_decisions=decisions,
        )

    def revoke_package_import(self, package_id: str, *, reason: str, operator: str = "system") -> PackageImportGrant:
        with self._lock:
            grants = [grant for grant in self._imports.values() if grant.package_id == package_id]
            if not grants:
                raise KeyError(package_id)
            grant = grants[0]
            revoked = grant.model_copy(update={"status": MemoryImportStatus.REVOKED, "revoked_at": _utc_now()})
            self._imports[grant.import_id] = revoked
            for memory_id in revoked.imported_memory_ids:
                self._revoke_locked(memory_id)
        self._audit_event("*", "import_revoked", reason, operator, {
            "import_id": revoked.import_id,
            "package_id": package_id,
            "revoked_memory_ids": revoked.imported_memory_ids,
        })
        return revoked

    def revoke_memory(self, memory_id: str, *, reason: str, operator: str = "system") -> QuarantinedMemory:
        with self._lock:
            entry = self._revoke_locked(memory_id)
        self._audit_event(memory_id, "memory_revoked", reason, operator, {})
        return entry

    def mark_contamination(
        self,
        *,
        source_memory_id: str,
        impact_graph: dict[str, list[str]],
        operator: str = "system",
    ) -> MemoryContaminationRecord:
        self._validate_contamination_chain(impact_graph)
        affected = sorted({source_memory_id, *[item for refs in impact_graph.values() for item in refs]})
        record = MemoryContaminationRecord(
            source_memory_id=source_memory_id,
            impact_graph=impact_graph,
            affected_memory_ids=affected,
        )
        with self._lock:
            self._contamination[record.contamination_id] = record
            for memory_id in affected:
                if memory_id in self._main_memory or memory_id in self._quarantine:
                    self._revoke_locked(memory_id)
        self._audit_event(source_memory_id, "contamination_marked", "Contamination graph recorded and affected memories revoked.", operator, {
            "contamination_id": record.contamination_id,
            "affected_memory_ids": affected,
        })
        return record

    def rollback_contamination(self, contamination_id: str, *, operator: str = "system") -> MemoryRollbackResult:
        with self._lock:
            contamination = self._contamination.get(contamination_id)
            if contamination is None:
                raise KeyError(contamination_id)
            trace = [f"{stage}:{','.join(contamination.impact_graph[stage])}" for stage in REQUIRED_CONTAMINATION_STAGES]
            for memory_id in contamination.affected_memory_ids:
                if memory_id in self._main_memory or memory_id in self._quarantine:
                    self._revoke_locked(memory_id)
            resolved = contamination.model_copy(update={"status": "rolled_back", "rollback_trace": trace, "resolved_at": _utc_now()})
            self._contamination[contamination_id] = resolved
            rollback = MemoryRollbackResult(
                contamination_id=contamination_id,
                revoked_memory_ids=resolved.affected_memory_ids,
                rollback_trace=trace,
            )
            self._rollbacks[rollback.rollback_id] = rollback
        self._audit_event(contamination.source_memory_id, "contamination_rollback", "Contamination rollback completed.", operator, {
            "contamination_id": contamination_id,
            "revoked_memory_ids": rollback.revoked_memory_ids,
        })
        return rollback

    def list_quarantine(self) -> list[QuarantinedMemory]:
        with self._lock:
            return list(self._quarantine.values())

    def list_main_memory(self) -> list[QuarantinedMemory]:
        with self._lock:
            return list(self._main_memory.values())

    def list_imports(self) -> list[PackageImportGrant]:
        with self._lock:
            return list(self._imports.values())

    def list_contamination(self) -> list[MemoryContaminationRecord]:
        with self._lock:
            return list(self._contamination.values())

    def list_rollbacks(self) -> list[MemoryRollbackResult]:
        with self._lock:
            return list(self._rollbacks.values())

    def list_audit_events(self) -> list[MemoryAuditEvent]:
        with self._lock:
            return list(self._audit)

    def list_memory_governance_audit_events(self) -> list[MemoryAuditEvent]:
        return self.list_audit_events()

    def _run_nine_gates(
        self,
        memory: EnhancedMemoryRecord,
        *,
        source_instance_id: str,
        contamination_chain: dict[str, list[str]],
        package_id: str | None,
        import_id: str | None,
    ) -> MemoryGateDecision:
        results = [
            self._gate_content_integrity(memory),
            self._gate_minimal_content(memory),
            self._gate_memory_layer(memory),
            self._gate_source_authorized(memory),
            self._gate_identity_boundary(memory),
            self._gate_trust_baseline(memory),
            self._gate_import_registry(package_id, import_id),
            self._gate_instance_binding(source_instance_id, package_id, import_id),
            self._gate_contamination_chain(contamination_chain),
        ]
        failed = [result.gate_id for result in results if not result.passed]
        return MemoryGateDecision(
            memory_id=memory.memory_id,
            outcome="accepted" if not failed else "rejected",
            gate_results=results,
            failed_gate_ids=failed,
        )

    def _gate_content_integrity(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        expected = compute_content_hash(memory.memory_layer, memory.source_kind, memory.title, memory.content)
        passed = memory.content_hash == expected
        return MemoryGateCheck(
            gate_id="G1_content_integrity",
            gate_name="Content Integrity",
            passed=passed,
            reason="content_hash verified" if passed else "content_hash mismatch",
            details={"stored": memory.content_hash, "computed": expected},
        )

    def _gate_minimal_content(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        problems = []
        if len(memory.title.strip()) < 2:
            problems.append("title")
        if len(memory.content.strip()) < 8:
            problems.append("content")
        if not memory.trace_id.strip():
            problems.append("trace_id")
        return MemoryGateCheck(
            gate_id="G2_minimal_content",
            gate_name="Minimal Content",
            passed=not problems,
            reason="minimal fields present" if not problems else f"missing or too short: {', '.join(problems)}",
        )

    def _gate_memory_layer(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        passed = memory.memory_layer in self.allowed_layers
        return MemoryGateCheck(
            gate_id="G3_memory_layer",
            gate_name="Memory Layer",
            passed=passed,
            reason="memory layer is allowed" if passed else f"memory layer {memory.memory_layer} is not allowed",
        )

    def _gate_source_authorized(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        passed = memory.source_kind in self.allowed_sources
        return MemoryGateCheck(
            gate_id="G4_source_authorized",
            gate_name="Source Authorized",
            passed=passed,
            reason="source kind is authorized" if passed else f"source kind {memory.source_kind} is not authorized",
        )

    def _gate_identity_boundary(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        text = _canonical_json(memory.model_dump(mode="json")).lower()
        forbidden = [token for token in self.forbidden_content_tokens if token in text]
        protected_hit = set(memory.tags) & self.protected_tags
        passed = not forbidden and (not protected_hit or memory.source_kind == "operator")
        reason = "identity boundary clean"
        if forbidden:
            reason = f"forbidden identity/security token(s): {', '.join(forbidden)}"
        elif protected_hit and memory.source_kind != "operator":
            reason = "non-operator source cannot write protected identity memory"
        return MemoryGateCheck(
            gate_id="G5_identity_boundary",
            gate_name="Identity Boundary",
            passed=passed,
            reason=reason,
            details={"protected_tags": sorted(protected_hit), "forbidden_tokens": forbidden},
        )

    def _gate_trust_baseline(self, memory: EnhancedMemoryRecord) -> MemoryGateCheck:
        passed = memory.confidence_score >= 0.25 and memory.verification_status != "retracted"
        return MemoryGateCheck(
            gate_id="G6_trust_baseline",
            gate_name="Trust Baseline",
            passed=passed,
            reason="trust baseline passed" if passed else "confidence too low or record retracted",
            details={"confidence_score": memory.confidence_score, "verification_status": memory.verification_status},
        )

    def _gate_import_registry(self, package_id: str | None, import_id: str | None) -> MemoryGateCheck:
        if package_id is None and import_id is None:
            return MemoryGateCheck(
                gate_id="G7_import_registry",
                gate_name="Import Registry",
                passed=True,
                reason="local memory does not require package authorization",
            )
        with self._lock:
            grant = self._imports.get(import_id or "")
        now = _utc_now()
        passed = (
            grant is not None
            and grant.package_id == package_id
            and grant.status == MemoryImportStatus.AUTHORIZED
            and grant.expires_at > now
        )
        return MemoryGateCheck(
            gate_id="G7_import_registry",
            gate_name="Import Registry",
            passed=passed,
            reason="package import is authorized and unexpired" if passed else "package import is missing, revoked, expired, or mismatched",
            details={"package_id": package_id, "import_id": import_id, "grant_status": grant.status.value if grant else None},
        )

    def _gate_instance_binding(self, source_instance_id: str, package_id: str | None, import_id: str | None) -> MemoryGateCheck:
        if package_id is None and import_id is None:
            return MemoryGateCheck(
                gate_id="G8_instance_binding",
                gate_name="Instance Binding",
                passed=True,
                reason="local memory is scoped to current instance",
            )
        with self._lock:
            grant = self._imports.get(import_id or "")
        passed = grant is not None and grant.source_instance_id == source_instance_id and grant.target_instance_id == self.instance_id
        return MemoryGateCheck(
            gate_id="G8_instance_binding",
            gate_name="Instance Binding",
            passed=passed,
            reason="source and target instance binding verified" if passed else "package instance binding failed",
            details={"source_instance_id": source_instance_id, "target_instance_id": self.instance_id},
        )

    def _gate_contamination_chain(self, contamination_chain: dict[str, list[str]]) -> MemoryGateCheck:
        missing = [stage for stage in REQUIRED_CONTAMINATION_STAGES if stage not in contamination_chain or not contamination_chain[stage]]
        return MemoryGateCheck(
            gate_id="G9_contamination_chain",
            gate_name="Contamination Chain",
            passed=not missing,
            reason="contamination chain covers runtime_memory -> goal -> action -> execution -> reflection" if not missing else f"missing stages: {', '.join(missing)}",
            details={"required_stages": list(REQUIRED_CONTAMINATION_STAGES)},
        )

    def _require_active_grant(self, package: MemoryExperiencePackage, *, import_id: str) -> PackageImportGrant:
        self._verify_package_binding(package)
        with self._lock:
            grant = self._imports.get(import_id)
        now = _utc_now()
        if grant is None:
            raise PermissionError("package import is not authorized")
        if grant.status != MemoryImportStatus.AUTHORIZED:
            raise PermissionError(f"package import status is {grant.status.value}")
        if grant.expires_at <= now or package.expires_at <= now:
            with self._lock:
                self._imports[grant.import_id] = grant.model_copy(update={"status": MemoryImportStatus.EXPIRED})
            raise PermissionError("package import is expired")
        if grant.package_id != package.package_id or grant.source_instance_id != package.source_instance_id or grant.target_instance_id != package.target_instance_id:
            raise PermissionError("package import grant does not match package binding")
        if package.target_instance_id != self.instance_id:
            raise PermissionError("package target instance does not match receiver")
        return grant

    def _decrypt_package_payload(self, package: MemoryExperiencePackage) -> dict[str, Any]:
        encrypted = base64.b64decode(package.encrypted_payload.encode("ascii"))
        payload_bytes = self._crypto.decrypt(encrypted)
        if hashlib.sha256(payload_bytes).hexdigest() != package.payload_hash:
            raise ValueError("package payload hash mismatch")
        return json.loads(payload_bytes.decode("utf-8"))

    def _verify_package_binding(self, package: MemoryExperiencePackage) -> None:
        expected = self._package_binding_hash(
            package_id=package.package_id,
            source_instance_id=package.source_instance_id,
            target_instance_id=package.target_instance_id,
            payload_hash=package.payload_hash,
            expires_at=package.expires_at,
        )
        if package.binding_hash != expected:
            raise PermissionError("package binding hash mismatch")

    def _package_binding_hash(
        self,
        *,
        package_id: str,
        source_instance_id: str,
        target_instance_id: str,
        payload_hash: str,
        expires_at: datetime,
    ) -> str:
        return hashlib.sha256(
            _canonical_json({
                "package_id": package_id,
                "source_instance_id": source_instance_id,
                "target_instance_id": target_instance_id,
                "payload_hash": payload_hash,
                "expires_at": expires_at.isoformat(),
            }).encode("utf-8")
        ).hexdigest()

    def _validate_contamination_chain(self, impact_graph: dict[str, list[str]]) -> None:
        missing = [stage for stage in REQUIRED_CONTAMINATION_STAGES if stage not in impact_graph or not impact_graph[stage]]
        if missing:
            raise ValueError(f"contamination graph missing required stage(s): {', '.join(missing)}")

    def _revoke_locked(self, memory_id: str) -> QuarantinedMemory:
        entry = self._main_memory.get(memory_id) or self._quarantine.get(memory_id)
        if entry is None:
            raise KeyError(memory_id)
        revoked = entry.model_copy(update={
            "status": MemoryQuarantineStatus.REVOKED,
            "trust_level": MemoryTrustLevel.REVOKED,
            "can_recall": False,
            "resolved_at": _utc_now(),
        })
        self._quarantine[memory_id] = revoked
        self._main_memory.pop(memory_id, None)
        return revoked

    def _audit_event(self, memory_id: str, action: str, reason: str, operator: str, details: dict[str, Any]) -> None:
        event = MemoryAuditEvent(memory_id=memory_id, action=action, reason=reason, operator=operator, details=details)
        with self._lock:
            self._audit.append(event)


def build_default_memory_governance(
    *, instance_id: str, package_secret: str | bytes | None = None
) -> MemoryGovernance:
    return MemoryGovernance(instance_id=instance_id, package_secret=package_secret)
