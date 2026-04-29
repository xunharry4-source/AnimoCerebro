"""Web API for G34 encrypted soul migration and hot standby takeover."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.continuity.soul_migration import (
    HeartbeatRecord,
    SnapshotExportRequest,
    SnapshotRestoreRequest,
    SoulMigrationManager,
    TakeoverAuthorizationRequest,
    TakeoverCommitRequest,
)

router = APIRouter(prefix="/soul-migration", tags=["soul-migration"])


def _manager(request: Request) -> SoulMigrationManager:
    manager = getattr(request.app.state, "soul_migration_manager", None)
    if manager is None:
        manager = SoulMigrationManager()
        request.app.state.soul_migration_manager = manager
    return manager


@router.post("/export")
def export_snapshot(payload: SnapshotExportRequest, request: Request) -> dict[str, Any]:
    try:
        package = _manager(request).export_snapshot(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "export_failed", "message": str(exc)}) from exc
    return {"package": package.model_dump(mode="json")}


@router.post("/restore")
def restore_snapshot(payload: SnapshotRestoreRequest, request: Request) -> dict[str, Any]:
    try:
        record = _manager(request).restore_snapshot(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "restore_failed", "message": str(exc)}) from exc
    return {"restore": record.model_dump(mode="json")}


@router.get("/backups/{package_id}")
def get_backup(package_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).get_backup(package_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "backup_not_found", "message": str(exc)}) from exc


@router.get("/restores/{restore_id}")
def get_restore(restore_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).get_restore(restore_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "restore_not_found", "message": str(exc)}) from exc


@router.post("/heartbeat")
def record_heartbeat(payload: HeartbeatRecord, request: Request) -> dict[str, Any]:
    heartbeat = _manager(request).record_heartbeat(payload)
    return {"heartbeat": heartbeat.model_dump(mode="json")}


@router.post("/takeover/authorize")
def authorize_takeover(payload: TakeoverAuthorizationRequest, request: Request) -> dict[str, Any]:
    authorization = _manager(request).authorize_takeover(payload)
    return {"authorization": authorization.model_dump(mode="json")}


@router.get("/takeover/status")
def takeover_status(
    primary_instance_id: str,
    standby_instance_id: str,
    request: Request,
    observed_at: datetime | None = None,
    heartbeat_timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    try:
        status = _manager(request).evaluate_takeover(
            primary_instance_id=primary_instance_id,
            standby_instance_id=standby_instance_id,
            observed_at=observed_at,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "takeover_status_failed", "message": str(exc)}) from exc
    return status.model_dump(mode="json")


@router.post("/takeover/commit")
def commit_takeover(payload: TakeoverCommitRequest, request: Request) -> dict[str, Any]:
    try:
        status = _manager(request).commit_takeover(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "takeover_commit_failed", "message": str(exc)}) from exc
    return {"takeover": status.model_dump(mode="json")}


@router.get("/audit")
def audit_events(request: Request) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json") for event in _manager(request).list_audit_events()]

