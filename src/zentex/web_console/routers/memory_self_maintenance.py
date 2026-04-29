from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from zentex.memory.self_maintenance import (
    KeyMetadata,
    KeyRotationResult,
    MemoryCompactionScheduleDecision,
    MemoryMaintenanceRunRequest,
    MemorySelfMaintenanceRuntime,
    build_default_memory_self_maintenance_runtime,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType


router = APIRouter(prefix="/memory-self-maintenance", tags=["memory-self-maintenance"])


class KeyRotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reencrypt_existing: bool = True


class SchedulerRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: dict[str, Any]
    report: dict[str, Any] | None = None


def _runtime(request: Request) -> MemorySelfMaintenanceRuntime:
    runtime = getattr(request.app.state, "memory_self_maintenance_runtime", None)
    if runtime is None:
        runtime = build_default_memory_self_maintenance_runtime()
        request.app.state.memory_self_maintenance_runtime = runtime
    if not isinstance(runtime, MemorySelfMaintenanceRuntime):
        raise HTTPException(status_code=503, detail="MemorySelfMaintenanceRuntime is unavailable")
    return runtime


def _write_report_audit(request: Request, report: dict[str, Any]) -> None:
    store = getattr(request.app.state, "transcript_store", None)
    if store is None or not callable(getattr(store, "write_entry", None)):
        raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
    store.write_entry(
        session_id="memory-self-maintenance",
        turn_id=str(report["task_id"]),
        entry_type=BrainTranscriptEntryType.FLOW_AUDIT,
        source="memory.self_maintenance",
        trace_id=str(report["task_id"]),
        payload={
            "event_type": "memory_self_maintenance_completed",
            "task_id": report["task_id"],
            "trigger_reason": report["trigger_reason"],
            "records_merged": report["records_merged"],
            "records_deduped": report["records_deduped"],
            "records_cleaned": report["records_cleaned"],
            "encrypted_records": report["encrypted_records"],
            "compression_ratio": report["compression_ratio"],
            "encrypted_record_ids": report["encrypted_record_ids"],
            "errors": report["errors"],
        },
    )


@router.post("/runs")
def run_memory_self_maintenance(payload: MemoryMaintenanceRunRequest, request: Request) -> dict[str, Any]:
    try:
        report = _runtime(request).run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    report_payload = report.model_dump(mode="json")
    _write_report_audit(request, report_payload)
    return report_payload


@router.post("/scheduler/evaluate", response_model=MemoryCompactionScheduleDecision)
def evaluate_memory_compaction_schedule(payload: MemoryMaintenanceRunRequest, request: Request) -> MemoryCompactionScheduleDecision:
    return _runtime(request).evaluate_schedule(payload)


@router.post("/scheduler/run-due", response_model=SchedulerRunResult)
def run_due_memory_compaction(payload: MemoryMaintenanceRunRequest, request: Request) -> SchedulerRunResult:
    try:
        decision, report = _runtime(request).run_if_due(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    report_payload = report.model_dump(mode="json") if report else None
    if report_payload is not None:
        _write_report_audit(request, report_payload)
    return SchedulerRunResult(
        decision=decision.model_dump(mode="json"),
        report=report_payload,
    )


@router.get("/reports")
def list_memory_self_maintenance_reports(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).store.list_reports()]


@router.get("/encrypted-records")
def list_encrypted_memory_records(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).encrypted_metadata()]


@router.get("/encrypted-records/{record_id}")
def get_decrypted_memory_record(record_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).decrypt_record(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"encrypted record not found: {record_id}") from exc


@router.get("/raw-encrypted-records/{record_id}")
def get_raw_encrypted_memory_record(record_id: str, request: Request) -> dict[str, Any]:
    try:
        stored = _runtime(request).store.get_encrypted_record(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"encrypted record not found: {record_id}") from exc
    return {
        "record_id": stored["record_id"],
        "record_type": stored["record_type"],
        "key_id": stored["key_id"],
        "encrypted_at": stored["encrypted_at"],
        "cipher_nonce": stored["cipher_nonce"],
        "ciphertext": stored["ciphertext"],
    }


@router.get("/deletion-audit")
def list_memory_deletion_audit(request: Request) -> list[dict[str, Any]]:
    return _runtime(request).store.list_deletion_audit()


@router.get("/keys", response_model=list[KeyMetadata])
def list_memory_keys(request: Request) -> list[KeyMetadata]:
    return _runtime(request).key_store.list_keys()


@router.post("/keys/rotate", response_model=KeyRotationResult)
def rotate_memory_key(payload: KeyRotationRequest, request: Request) -> KeyRotationResult:
    return _runtime(request).rotate_keys(reencrypt_existing=payload.reencrypt_existing)
