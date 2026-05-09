from __future__ import annotations

"""Web API for G38 memory governance."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from zentex.memory.memory_governance import (
    MemoryExperiencePackage,
    MemoryRejectedError,
    MemoryTrustLevel,
)
from zentex.memory.management.enhanced import EnhancedMemoryRecord
from zentex.memory.service import MemoryService, get_memory_service


router = APIRouter(prefix="/memory-governance/g38", tags=["memory-governance-g38"])


class QuarantineMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory: EnhancedMemoryRecord
    source_instance_id: str
    contamination_chain: dict[str, list[str]]
    package_id: str | None = None
    import_id: str | None = None
    operator: str = "api"


class PromoteMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_trust_level: MemoryTrustLevel
    reviewer_id: str


class ExportPackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_ids: list[str]
    target_instance_id: str
    expires_at: datetime


class AuthorizeImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_id: str
    source_instance_id: str
    target_instance_id: str
    expires_at: datetime
    authorized_by: str


class ImportPackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: MemoryExperiencePackage
    import_id: str
    contamination_chain: dict[str, list[str]]
    operator: str = "api"


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    operator: str = "api"


class MarkContaminationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_memory_id: str
    impact_graph: dict[str, list[str]]
    operator: str = "api"


def _service(request: Request) -> MemoryService:
    service = getattr(request.app.state, "memory_service", None)
    if service is None:
        service = get_memory_service()
        request.app.state.memory_service = service
    return service


@router.post("/quarantine")
def submit_quarantined_memory(payload: QuarantineMemoryRequest, request: Request) -> dict[str, object]:
    try:
        entry = _service(request).submit_quarantined_memory(
            payload.memory,
            source_instance_id=payload.source_instance_id,
            package_id=payload.package_id,
            import_id=payload.import_id,
            contamination_chain=payload.contamination_chain,
            operator=payload.operator,
        )
    except MemoryRejectedError as exc:
        raise HTTPException(status_code=422, detail=exc.decision.model_dump(mode="json")) from exc
    return entry.model_dump(mode="json")


@router.post("/memories/{memory_id}/promote")
def promote_memory(memory_id: str, payload: PromoteMemoryRequest, request: Request) -> dict[str, object]:
    try:
        entry = _service(request).promote_memory(
            memory_id,
            target_trust_level=payload.target_trust_level,
            reviewer_id=payload.reviewer_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    return entry.model_dump(mode="json")


@router.get("/recall")
def recall_memories(request: Request, query: str = Query(min_length=1), limit: int = 10) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).recall_memories(query, limit=limit)]


@router.post("/packages/export")
def export_package(payload: ExportPackageRequest, request: Request) -> dict[str, object]:
    try:
        package = _service(request).export_package(
            payload.memory_ids,
            target_instance_id=payload.target_instance_id,
            expires_at=payload.expires_at,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found", "memory_id": str(exc)}) from exc
    return package.model_dump(mode="json")


@router.post("/imports/authorize")
def authorize_package_import(payload: AuthorizeImportRequest, request: Request) -> dict[str, object]:
    try:
        grant = _service(request).authorize_package_import(
            package_id=payload.package_id,
            source_instance_id=payload.source_instance_id,
            target_instance_id=payload.target_instance_id,
            expires_at=payload.expires_at,
            authorized_by=payload.authorized_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    return grant.model_dump(mode="json")


@router.post("/packages/import")
def import_package(payload: ImportPackageRequest, request: Request) -> dict[str, object]:
    try:
        result = _service(request).import_package(
            payload.package,
            import_id=payload.import_id,
            contamination_chain=payload.contamination_chain,
            operator=payload.operator,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
    except MemoryRejectedError as exc:
        raise HTTPException(status_code=422, detail=exc.decision.model_dump(mode="json")) from exc
    return result.model_dump(mode="json")


@router.post("/packages/{package_id}/revoke")
def revoke_package_import(package_id: str, payload: RevokeRequest, request: Request) -> dict[str, object]:
    try:
        grant = _service(request).revoke_package_import(package_id, reason=payload.reason, operator=payload.operator)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "package_not_found"}) from exc
    return grant.model_dump(mode="json")


@router.post("/memories/{memory_id}/revoke")
def revoke_memory(memory_id: str, payload: RevokeRequest, request: Request) -> dict[str, object]:
    try:
        entry = _service(request).revoke_memory(memory_id, reason=payload.reason, operator=payload.operator)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    return entry.model_dump(mode="json")


@router.post("/contamination")
def mark_contamination(payload: MarkContaminationRequest, request: Request) -> dict[str, object]:
    try:
        record = _service(request).mark_contamination(
            source_memory_id=payload.source_memory_id,
            impact_graph=payload.impact_graph,
            operator=payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    return record.model_dump(mode="json")


@router.post("/contamination/{contamination_id}/rollback")
def rollback_contamination(contamination_id: str, request: Request) -> dict[str, object]:
    try:
        rollback = _service(request).rollback_contamination(contamination_id, operator="api")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "contamination_not_found"}) from exc
    return rollback.model_dump(mode="json")


@router.get("/quarantine")
def list_quarantine(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_quarantine()]


@router.get("/main-memory")
def list_main_memory(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_main_memory()]


@router.get("/imports")
def list_imports(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_imports()]


@router.get("/contamination")
def list_contamination(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_contamination()]


@router.get("/rollbacks")
def list_rollbacks(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_rollbacks()]


@router.get("/audit")
def list_audit_events(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_memory_governance_audit_events()]
