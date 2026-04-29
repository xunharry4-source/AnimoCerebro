from __future__ import annotations

import base64
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.storage_paths import get_storage_paths

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - real tests require cryptography
    AESGCM = None  # type: ignore[assignment]


UTC = timezone.utc
SENSITIVE_MEMORY_TYPES = {"ExperienceRecord", "StrategyPatch", "IdentityAnchor", "QuarantinedMemory"}


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


class ReflectionRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    risk_level: str = "low"
    outcome_type: str = "unknown"
    summary: str = Field(min_length=1)
    created_at: str | None = None


class ExperienceRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    topic_hash: str = Field(min_length=1)
    risk_level: str = "low"
    outcome_type: str = "unknown"
    trust_level: float = Field(default=0.5, ge=0.0, le=1.0)
    repro_count: int = Field(default=0, ge=0)
    content: str = ""


class AgendaItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expires_at: str
    deferred_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    active: bool = True


class NoiseCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    tier: str = "warm"
    last_hit_at: str | None = None
    repro_count: int = Field(default=0, ge=0)
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SensitiveMemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    sensitivity: Literal["public", "internal", "sensitive", "secret"] = "sensitive"


class MemoryMaintenanceRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_reason: Literal["manual", "low_load", "storage_over_budget"] = "manual"
    load_average: float = Field(default=0.0, ge=0.0)
    low_load_threshold: float = Field(default=0.35, ge=0.0)
    storage_used_bytes: int = Field(default=0, ge=0)
    storage_budget_bytes: int = Field(default=1, ge=1)
    reflection_records: list[ReflectionRecordInput] = Field(default_factory=list)
    experience_records: list[ExperienceRecordInput] = Field(default_factory=list)
    agenda_items: list[AgendaItemInput] = Field(default_factory=list)
    noise_candidates: list[NoiseCandidateInput] = Field(default_factory=list)
    sensitive_records: list[SensitiveMemoryInput] = Field(default_factory=list)
    now: str | None = None


class MemoryCompactionScheduleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    due: bool
    trigger_reason: str
    load_average: float
    low_load_threshold: float
    storage_used_bytes: int
    storage_budget_bytes: int
    reasons: list[str]


class ExperienceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    topic: str
    risk_level: str
    outcome_type: str
    source_record_ids: list[str]
    summary: str
    reference_chain_preserved: bool = True


class ExperienceDedupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dedup_key: str
    kept_record_id: str
    superseded_record_ids: list[str]
    reason: str


class ExpiredAgendaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    action: Literal["expired"]
    reason: str


class NoiseTombstoneDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    action: Literal["tombstone"]
    previous_tier: str
    reason: str


class MemoryCompactionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    status: Literal["completed"]
    trigger_reason: str
    started_at: str
    finished_at: str
    records_merged: int
    records_deduped: int
    records_cleaned: int
    encrypted_records: int
    storage_before_bytes: int
    storage_after_bytes: int
    compression_ratio: float
    experience_candidates: list[ExperienceCandidate]
    dedup_decisions: list[ExperienceDedupDecision]
    expired_items: list[ExpiredAgendaDecision]
    tombstones: list[NoiseTombstoneDecision]
    encrypted_record_ids: list[str]
    errors: list[str] = Field(default_factory=list)


class EncryptedMemoryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    record_type: str
    key_id: str
    encrypted_at: str
    cipher_nonce: str
    ciphertext_size: int


class KeyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key_id: str
    created_at: str
    rotated_at: str | None = None
    revoked_at: str | None = None
    status: str


class KeyRotationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    old_key_id: str
    new_key_id: str
    reencrypted_records: int
    revoked_old_key: bool


class MemoryKeyStore:
    def __init__(self, key_file: str | Path | None = None) -> None:
        runtime_dir = get_storage_paths().runtime_data_dir
        self.key_file = Path(key_file or runtime_dir / "memory_self_maintenance_keystore.json")
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_file.exists():
            self._write(
                {
                    "active_key_id": "",
                    "keys": [],
                }
            )
        if not self._read().get("active_key_id"):
            self.create_initial_key()

    def create_initial_key(self) -> KeyMetadata:
        if self._read().get("active_key_id"):
            return self.active_metadata()
        return self._create_key(status="active")

    def active_key(self) -> tuple[str, bytes]:
        payload = self._read()
        key_id = str(payload.get("active_key_id") or "")
        for row in payload.get("keys", []):
            if row.get("key_id") == key_id and row.get("status") == "active":
                return key_id, base64.b64decode(str(row["key_b64"]).encode("ascii"))
        raise RuntimeError("active memory encryption key is unavailable")

    def key_by_id(self, key_id: str) -> bytes:
        for row in self._read().get("keys", []):
            if row.get("key_id") == key_id and row.get("status") in {"active", "rotating", "revoked"}:
                return base64.b64decode(str(row["key_b64"]).encode("ascii"))
        raise KeyError(key_id)

    def active_metadata(self) -> KeyMetadata:
        active_key_id = str(self._read().get("active_key_id") or "")
        for item in self.list_keys():
            if item.key_id == active_key_id:
                return item
        raise RuntimeError("active key metadata is unavailable")

    def list_keys(self) -> list[KeyMetadata]:
        return [
            KeyMetadata(
                key_id=str(row["key_id"]),
                created_at=str(row["created_at"]),
                rotated_at=row.get("rotated_at"),
                revoked_at=row.get("revoked_at"),
                status=str(row["status"]),
            )
            for row in self._read().get("keys", [])
        ]

    def rotate(self) -> tuple[str, str]:
        payload = self._read()
        old_key_id = str(payload.get("active_key_id") or "")
        rotated_at = _now().isoformat()
        for row in payload["keys"]:
            if row.get("key_id") == old_key_id:
                row["status"] = "rotating"
                row["rotated_at"] = rotated_at
        new_key = self._new_key_row("active")
        payload["keys"].append(new_key)
        payload["active_key_id"] = new_key["key_id"]
        self._write(payload)
        return old_key_id, str(new_key["key_id"])

    def revoke(self, key_id: str) -> None:
        payload = self._read()
        revoked_at = _now().isoformat()
        changed = False
        for row in payload["keys"]:
            if row.get("key_id") == key_id:
                row["status"] = "revoked"
                row["revoked_at"] = revoked_at
                changed = True
        if not changed:
            raise KeyError(key_id)
        self._write(payload)

    def _create_key(self, *, status: str) -> KeyMetadata:
        payload = self._read()
        row = self._new_key_row(status)
        payload["keys"].append(row)
        if status == "active":
            payload["active_key_id"] = row["key_id"]
        self._write(payload)
        return KeyMetadata(
            key_id=str(row["key_id"]),
            created_at=str(row["created_at"]),
            status=str(row["status"]),
        )

    def _new_key_row(self, status: str) -> dict[str, Any]:
        raw_key = os.urandom(32)
        key_id = f"memory-key:{uuid4().hex}"
        return {
            "key_id": key_id,
            "key_b64": base64.b64encode(raw_key).decode("ascii"),
            "created_at": _now().isoformat(),
            "rotated_at": None,
            "revoked_at": None,
            "status": status,
        }

    def _read(self) -> dict[str, Any]:
        return json.loads(self.key_file.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, Any]) -> None:
        self.key_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.key_file.chmod(0o600)
        except OSError:
            pass


class MemoryEncryptionLayer:
    def __init__(self, key_store: MemoryKeyStore) -> None:
        if AESGCM is None:
            raise RuntimeError("cryptography is required for memory self-maintenance encryption")
        self.key_store = key_store

    def encrypt_record(self, record: SensitiveMemoryInput) -> tuple[EncryptedMemoryMetadata, dict[str, Any]]:
        if record.record_type not in SENSITIVE_MEMORY_TYPES:
            raise ValueError(f"unsupported sensitive memory type: {record.record_type}")
        if record.sensitivity not in {"sensitive", "secret"}:
            raise ValueError("only sensitive or secret records may enter static encryption")
        key_id, key = self.key_store.active_key()
        nonce = os.urandom(12)
        plaintext = json.dumps(record.payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, record.record_id.encode("utf-8"))
        encrypted_at = _now().isoformat()
        metadata = EncryptedMemoryMetadata(
            record_id=record.record_id,
            record_type=record.record_type,
            key_id=key_id,
            encrypted_at=encrypted_at,
            cipher_nonce=base64.b64encode(nonce).decode("ascii"),
            ciphertext_size=len(ciphertext),
        )
        stored = {
            **metadata.model_dump(mode="json"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        return metadata, stored

    def decrypt_payload(self, stored: dict[str, Any]) -> dict[str, Any]:
        key = self.key_store.key_by_id(str(stored["key_id"]))
        nonce = base64.b64decode(str(stored["cipher_nonce"]).encode("ascii"))
        ciphertext = base64.b64decode(str(stored["ciphertext"]).encode("ascii"))
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, str(stored["record_id"]).encode("utf-8"))
        return json.loads(plaintext.decode("utf-8"))


class MemorySelfMaintenanceStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        runtime_dir = get_storage_paths().runtime_data_dir
        self.db_path = Path(db_path or runtime_dir / "memory_self_maintenance.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS maintenance_reports (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS encrypted_memory_records (
                    record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    encrypted_at TEXT NOT NULL,
                    encrypted_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_deletion_audit (
                    audit_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    deletion_kind TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def save_report(self, report: MemoryCompactionReport) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO maintenance_reports (task_id, created_at, report_json)
                VALUES (?, ?, ?)
                """,
                (report.task_id, report.finished_at, json.dumps(report.model_dump(mode="json"), ensure_ascii=False)),
            )
            conn.commit()

    def list_reports(self) -> list[MemoryCompactionReport]:
        with self._connect() as conn:
            rows = conn.execute("SELECT report_json FROM maintenance_reports ORDER BY created_at ASC").fetchall()
        return [MemoryCompactionReport.model_validate(json.loads(row["report_json"])) for row in rows]

    def save_encrypted_record(self, stored: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO encrypted_memory_records
                    (record_id, record_type, key_id, encrypted_at, encrypted_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    stored["record_id"],
                    stored["record_type"],
                    stored["key_id"],
                    stored["encrypted_at"],
                    json.dumps(stored, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_encrypted_record(self, record_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT encrypted_json FROM encrypted_memory_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row["encrypted_json"])

    def list_encrypted_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT encrypted_json FROM encrypted_memory_records ORDER BY encrypted_at ASC").fetchall()
        return [json.loads(row["encrypted_json"]) for row in rows]

    def update_encrypted_record(self, stored: dict[str, Any]) -> None:
        self.save_encrypted_record(stored)

    def append_deletion_audit(self, memory_id: str, deletion_kind: str, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_deletion_audit (audit_id, memory_id, deletion_kind, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"deletion-audit:{uuid4().hex}", memory_id, deletion_kind, reason, _now().isoformat()),
            )
            conn.commit()

    def list_deletion_audit(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory_deletion_audit ORDER BY created_at ASC").fetchall()
        return [dict(row) for row in rows]


class ReflectionMergeEngine:
    def merge(self, records: list[ReflectionRecordInput]) -> list[ExperienceCandidate]:
        groups: dict[tuple[str, str, str], list[ReflectionRecordInput]] = defaultdict(list)
        for record in records:
            groups[(record.topic, record.risk_level, record.outcome_type)].append(record)
        candidates: list[ExperienceCandidate] = []
        for (topic, risk_level, outcome_type), items in groups.items():
            if len(items) < 2:
                continue
            candidates.append(
                ExperienceCandidate(
                    candidate_id=f"experience-candidate:{uuid4().hex}",
                    topic=topic,
                    risk_level=risk_level,
                    outcome_type=outcome_type,
                    source_record_ids=[item.record_id for item in items],
                    summary="; ".join(item.summary for item in items),
                )
            )
        return candidates


class ExperienceDedupEngine:
    def dedup(self, records: list[ExperienceRecordInput]) -> list[ExperienceDedupDecision]:
        groups: dict[tuple[str, str, str], list[ExperienceRecordInput]] = defaultdict(list)
        for record in records:
            groups[(record.topic_hash, record.risk_level, record.outcome_type)].append(record)
        decisions: list[ExperienceDedupDecision] = []
        for key, items in groups.items():
            if len(items) < 2:
                continue
            ordered = sorted(items, key=lambda item: (item.trust_level, item.repro_count, item.record_id), reverse=True)
            kept = ordered[0]
            superseded = [item.record_id for item in ordered[1:]]
            decisions.append(
                ExperienceDedupDecision(
                    dedup_key=":".join(key),
                    kept_record_id=kept.record_id,
                    superseded_record_ids=superseded,
                    reason="kept highest trust_level, then highest repro_count",
                )
            )
        return decisions


class ExpiredItemCleaner:
    def clean(
        self,
        *,
        agenda_items: list[AgendaItemInput],
        noise_candidates: list[NoiseCandidateInput],
        now: datetime,
        max_unused_days: int = 90,
        risk_threshold: float = 0.3,
        impact_threshold: float = 0.2,
    ) -> tuple[list[ExpiredAgendaDecision], list[NoiseTombstoneDecision]]:
        expired: list[ExpiredAgendaDecision] = []
        for item in agenda_items:
            expires_at = _parse_dt(item.expires_at)
            if item.active and expires_at and expires_at <= now and item.deferred_risk_score <= risk_threshold:
                expired.append(
                    ExpiredAgendaDecision(
                        item_id=item.item_id,
                        action="expired",
                        reason=f"expired at {expires_at.isoformat()} with deferred_risk_score={item.deferred_risk_score}",
                    )
                )

        tombstones: list[NoiseTombstoneDecision] = []
        cutoff = now - timedelta(days=max_unused_days)
        for item in noise_candidates:
            last_hit_at = _parse_dt(item.last_hit_at)
            unused = last_hit_at is None or last_hit_at <= cutoff
            if unused and item.repro_count == 0 and item.impact_score <= impact_threshold:
                tombstones.append(
                    NoiseTombstoneDecision(
                        memory_id=item.memory_id,
                        action="tombstone",
                        previous_tier=item.tier,
                        reason="low-value noise: stale, no reproductions, low impact",
                    )
                )
        return expired, tombstones


class MemorySelfMaintenanceRuntime:
    def __init__(
        self,
        *,
        store: MemorySelfMaintenanceStore | None = None,
        key_store: MemoryKeyStore | None = None,
    ) -> None:
        self.store = store or MemorySelfMaintenanceStore()
        self.key_store = key_store or MemoryKeyStore()
        self.encryption = MemoryEncryptionLayer(self.key_store)
        self.reflection_merge = ReflectionMergeEngine()
        self.experience_dedup = ExperienceDedupEngine()
        self.expired_cleaner = ExpiredItemCleaner()
        self.scheduler = MemoryCompactionScheduler()

    def run(self, request: MemoryMaintenanceRunRequest) -> MemoryCompactionReport:
        now = _parse_dt(request.now) or _now()
        if request.trigger_reason == "low_load" and request.load_average > request.low_load_threshold:
            raise ValueError("low_load trigger rejected because current load is above threshold")
        if request.trigger_reason == "storage_over_budget" and request.storage_used_bytes <= request.storage_budget_bytes:
            raise ValueError("storage_over_budget trigger rejected because storage is within budget")

        started_at = _now().isoformat()
        candidates = self.reflection_merge.merge(request.reflection_records)
        dedup_decisions = self.experience_dedup.dedup(request.experience_records)
        expired, tombstones = self.expired_cleaner.clean(
            agenda_items=request.agenda_items,
            noise_candidates=request.noise_candidates,
            now=now,
        )

        encrypted_ids: list[str] = []
        for record in request.sensitive_records:
            _metadata, stored = self.encryption.encrypt_record(record)
            self.store.save_encrypted_record(stored)
            encrypted_ids.append(record.record_id)

        for tombstone in tombstones:
            self.store.append_deletion_audit(
                tombstone.memory_id,
                "tombstone",
                tombstone.reason,
            )

        source_bytes = (
            _json_bytes([item.model_dump(mode="json") for item in request.reflection_records])
            + _json_bytes([item.model_dump(mode="json") for item in request.experience_records])
            + _json_bytes([item.model_dump(mode="json") for item in request.agenda_items])
            + _json_bytes([item.model_dump(mode="json") for item in request.noise_candidates])
        )
        result_bytes = (
            _json_bytes([item.model_dump(mode="json") for item in candidates])
            + _json_bytes([item.model_dump(mode="json") for item in dedup_decisions])
            + _json_bytes([item.model_dump(mode="json") for item in expired])
            + _json_bytes([item.model_dump(mode="json") for item in tombstones])
        )
        storage_before = request.storage_used_bytes or source_bytes
        storage_after = max(1, min(storage_before, result_bytes + sum(len(self.store.get_encrypted_record(item)["ciphertext"]) for item in encrypted_ids)))
        records_merged = sum(len(item.source_record_ids) for item in candidates)
        records_deduped = sum(len(item.superseded_record_ids) for item in dedup_decisions)
        report = MemoryCompactionReport(
            task_id=f"memory-maintenance:{uuid4().hex}",
            status="completed",
            trigger_reason=request.trigger_reason,
            started_at=started_at,
            finished_at=_now().isoformat(),
            records_merged=records_merged,
            records_deduped=records_deduped,
            records_cleaned=len(expired) + len(tombstones),
            encrypted_records=len(encrypted_ids),
            storage_before_bytes=storage_before,
            storage_after_bytes=storage_after,
            compression_ratio=round(storage_before / max(storage_after, 1), 6),
            experience_candidates=candidates,
            dedup_decisions=dedup_decisions,
            expired_items=expired,
            tombstones=tombstones,
            encrypted_record_ids=encrypted_ids,
            errors=[],
        )
        self.store.save_report(report)
        return report

    def evaluate_schedule(self, request: MemoryMaintenanceRunRequest) -> MemoryCompactionScheduleDecision:
        return self.scheduler.evaluate(request)

    def run_if_due(self, request: MemoryMaintenanceRunRequest) -> tuple[MemoryCompactionScheduleDecision, MemoryCompactionReport | None]:
        decision = self.evaluate_schedule(request)
        if not decision.due:
            return decision, None
        effective_request = request.model_copy(update={"trigger_reason": decision.trigger_reason})
        return decision, self.run(effective_request)

    def decrypt_record(self, record_id: str) -> dict[str, Any]:
        stored = self.store.get_encrypted_record(record_id)
        return {
            "record_id": stored["record_id"],
            "record_type": stored["record_type"],
            "key_id": stored["key_id"],
            "payload": self.encryption.decrypt_payload(stored),
        }

    def encrypted_metadata(self) -> list[EncryptedMemoryMetadata]:
        rows = self.store.list_encrypted_records()
        return [
            EncryptedMemoryMetadata(
                record_id=str(row["record_id"]),
                record_type=str(row["record_type"]),
                key_id=str(row["key_id"]),
                encrypted_at=str(row["encrypted_at"]),
                cipher_nonce=str(row["cipher_nonce"]),
                ciphertext_size=len(str(row["ciphertext"])),
            )
            for row in rows
        ]

    def rotate_keys(self, *, reencrypt_existing: bool = True) -> KeyRotationResult:
        old_key_id, new_key_id = self.key_store.rotate()
        reencrypted = 0
        if reencrypt_existing:
            for stored in self.store.list_encrypted_records():
                payload = self.encryption.decrypt_payload(stored)
                metadata, encrypted = self.encryption.encrypt_record(
                    SensitiveMemoryInput(
                        record_id=str(stored["record_id"]),
                        record_type=str(stored["record_type"]),
                        payload=payload,
                        sensitivity="sensitive",
                    )
                )
                if metadata.key_id != new_key_id:
                    raise RuntimeError("reencryption did not use the active key")
                self.store.update_encrypted_record(encrypted)
                reencrypted += 1
            self.key_store.revoke(old_key_id)
        return KeyRotationResult(
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            reencrypted_records=reencrypted,
            revoked_old_key=reencrypt_existing,
        )


class MemoryCompactionScheduler:
    def evaluate(self, request: MemoryMaintenanceRunRequest) -> MemoryCompactionScheduleDecision:
        reasons: list[str] = []
        due = False
        trigger_reason = request.trigger_reason

        if request.trigger_reason == "manual":
            due = True
            reasons.append("manual_trigger_requested")
        if request.load_average <= request.low_load_threshold:
            if request.trigger_reason in {"manual", "low_load"}:
                trigger_reason = "low_load" if request.trigger_reason != "manual" else trigger_reason
            due = True if request.trigger_reason == "low_load" else due
            reasons.append("load_average_at_or_below_threshold")
        if request.storage_used_bytes > request.storage_budget_bytes:
            if request.trigger_reason in {"manual", "storage_over_budget"}:
                trigger_reason = "storage_over_budget" if request.trigger_reason != "manual" else trigger_reason
            due = True if request.trigger_reason == "storage_over_budget" else due
            reasons.append("storage_used_bytes_above_budget")
        if not due:
            reasons.append("no_compaction_trigger_due")

        return MemoryCompactionScheduleDecision(
            decision_id=f"memory-compaction-schedule:{uuid4().hex}",
            due=due,
            trigger_reason=trigger_reason,
            load_average=request.load_average,
            low_load_threshold=request.low_load_threshold,
            storage_used_bytes=request.storage_used_bytes,
            storage_budget_bytes=request.storage_budget_bytes,
            reasons=reasons,
        )


def build_default_memory_self_maintenance_runtime() -> MemorySelfMaintenanceRuntime:
    return MemorySelfMaintenanceRuntime()
