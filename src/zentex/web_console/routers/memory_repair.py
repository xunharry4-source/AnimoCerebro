from __future__ import annotations

from fastapi import APIRouter, Request

from zentex.web_console.contracts.memory import (
    MemoryRecordDiagnosticsPayload,
    MemoryRepairAllPayload,
    MemoryRepairSchedulerStatusPayload,
    MemoryRepairTicketItem,
)
from .memory_handlers import (
    get_memory_record_diagnostics,
    get_memory_repair_scheduler_status,
    repair_memory_record,
    trigger_memory_repair_all,
    verify_memory_record,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/{memory_id}/diagnostics", response_model=MemoryRecordDiagnosticsPayload)
async def get_record_diagnostics(request: Request, memory_id: str) -> MemoryRecordDiagnosticsPayload:
    return await get_memory_record_diagnostics(request, memory_id)


@router.post("/{memory_id}/verify", response_model=MemoryRepairTicketItem)
async def verify_record(request: Request, memory_id: str) -> MemoryRepairTicketItem:
    return await verify_memory_record(request, memory_id)


@router.post("/{memory_id}/repair", response_model=MemoryRepairTicketItem)
async def repair_record(request: Request, memory_id: str) -> MemoryRepairTicketItem:
    return await repair_memory_record(request, memory_id)


@router.get("/repair/status", response_model=MemoryRepairSchedulerStatusPayload)
async def get_repair_status(request: Request) -> MemoryRepairSchedulerStatusPayload:
    return await get_memory_repair_scheduler_status(request)


@router.post("/repair/trigger", response_model=MemoryRepairAllPayload)
async def trigger_repair_all(request: Request) -> MemoryRepairAllPayload:
    return await trigger_memory_repair_all(request)
