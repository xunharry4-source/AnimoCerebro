from __future__ import annotations
"""Memory Handler Operations - Write & Management Layer

⚠️  SERVICE LAYER - OPERATIONS & MUTATIONS
════════════════════════════════════════════════════════════════════
This module handles all memory write operations, state changes, and
management actions. Query operations are in memory_commons.py.
════════════════════════════════════════════════════════════════════
"""


import logging
from typing import Optional
from fastapi import Request, HTTPException

from zentex.web_console.contracts.memory import (
    EnhancedMemoryRecordItem,
    MemoryRecordDiagnosticsPayload,
    MemoryRepairAllPayload,
    MemoryRepairSchedulerStatusPayload,
    MemoryRepairTicketItem,
    UpdateEnhancedMemoryRequest,
)
from zentex.web_console.services.memory import (
    build_enhanced_memory_record_item,
    build_memory_record_diagnostics_payload,
    build_memory_repair_all_payload,
    build_memory_repair_ticket_item,
)

logger = logging.getLogger(__name__)


def _get_memory_service(request: Request) -> Optional[object]:
    return getattr(request.app.state, "memory_service", None)


def _get_consolidation_engine(request: Request) -> Optional[object]:
    return getattr(request.app.state, "consolidation_engine", None)


def _get_memory_repair_scheduler(request: Request) -> Optional[object]:
    return getattr(request.app.state, "memory_repair_scheduler", None)


async def update_memory_record_management(
    request: Request,
    memory_id: str,
    update_request: UpdateEnhancedMemoryRequest,
) -> EnhancedMemoryRecordItem:
    """Update memory record management state.
    
    Allows operators to:
    - Change lifecycle status (active → deprecated → archived)
    - Modify visibility settings
    - Adjust trust levels
    - Add management and correction notes
    - Mark records as verified
    - Track supersession relationships
    
    Args:
        request: FastAPI Request
        memory_id: Memory record ID
        update_request: UpdateEnhancedMemoryRequest with change details
        
    Returns:
        EnhancedMemoryRecordItem with updated record
        
    Raises:
        HTTPException (404): If record not found
        HTTPException (400): If update is invalid
        HTTPException (500): If update operation fails
    """
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Memory service unavailable",
                    "hint": "增强记忆服务未初始化，请检查系统启动日志",
                }
            )
        
        # Apply management update
        record = service.update_management_state(
            memory_id,
            status=update_request.status,
            visibility=update_request.visibility,
            trust_level=update_request.trust_level,
            management_note=update_request.management_note,
            correction_note=update_request.correction_note,
            operator=update_request.operator,
            reason=update_request.reason,
            supersedes_memory_id=update_request.supersedes_memory_id,
            superseded_by_memory_id=update_request.superseded_by_memory_id,
            mark_verified=update_request.mark_verified,
        )
        
        logger.info(
            f"Updated memory record {memory_id}: "
            f"status={update_request.status}, operator={update_request.operator}"
        )
        
        return build_enhanced_memory_record_item(record)
        
    except KeyError as exc:
        logger.warning(f"Memory record not found: {memory_id}")
        raise HTTPException(
            status_code=404, 
            detail=f"未找到 ID 为 {memory_id} 的记忆记录，请检查输入或刷新列表"
        ) from exc
    except ValueError as exc:
        logger.warning(f"Invalid update request for {memory_id}: {exc}")
        raise HTTPException(
            status_code=400, 
            detail=f"请求参数验证失败：{str(exc)}"
        ) from exc
    except Exception as exc:
        # Do not hide write-path failures behind a plain 500 response. Operators need
        # the traceback here because pretending this was just a generic bad request
        # would mask a real backend mutation failure.
        logger.exception("Error updating memory record %s", memory_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to update memory record",
                "memory_id": memory_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }
        ) from exc


async def trigger_consolidation_cycle(request: Request) -> dict[str, str]:
    """Trigger a manual memory consolidation cycle.
    
    Consolidation process:
    - Analyzes semantic relationships
    - Merges duplicate or redundant records
    - Updates trust scores
    - Optimizes storage layout
    - Generates audit trail
    
    Note: This is an expensive operation that may take time.
    
    Args:
        request: FastAPI Request
        
    Returns:
        Dict with status and message
        
    Raises:
        HTTPException (503): If consolidation engine unavailable
    """
    try:
        consolidation_engine = _get_consolidation_engine(request)
        if consolidation_engine is None:
            raise HTTPException(
                status_code=503,
                detail="Consolidation engine not available"
            )
        
        consolidation_engine.submit_manual_trigger(operator="web_console")
        
        logger.info("Manual memory consolidation cycle initiated")
        
        return {
            "status": "triggered",
            "message": "已成功启动手动记忆固化流程。固化过程将在后台异步完成，您可以稍后查看最新的固化报告。",
        }
        
    except Exception as exc:
        # Do not reduce consolidation trigger failures to a single-line error. This
        # is a backend write/control path; hiding the traceback would fake an
        # operationally normal trigger surface while the engine is already failing.
        logger.exception("Error triggering consolidation")
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail="Failed to trigger consolidation cycle"
        ) from exc


async def clear_memory_verification_flag(
    request: Request,
    memory_id: str,
) -> EnhancedMemoryRecordItem:
    """Clear verification flag from a memory record.
    
    Used when a previously verified record needs re-evaluation
    or when verification status expires.
    
    Args:
        request: FastAPI Request
        memory_id: Memory record ID
        
    Returns:
        EnhancedMemoryRecordItem with updated record
        
    Raises:
        HTTPException (404): If record not found
        HTTPException (500): If operation fails
    """
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Memory service unavailable",
                    "hint": "增强记忆服务未初始化，请检查系统启动日志",
                }
            )
        
        # Clear verification
        record = service.update_management_state(
            memory_id,
            mark_verified=False,
            operator="web_console_user",
            reason="Manual verification flag clearance"
        )
        
        logger.info(f"Cleared verification flag for memory record {memory_id}")
        
        return build_enhanced_memory_record_item(record)
        
    except KeyError as exc:
        raise HTTPException(
            status_code=404, 
            detail=f"无法清除验证标记：记录 {memory_id} 不存在"
        ) from exc
    except Exception as exc:
        # Verification flag updates mutate management state. Swallowing the traceback
        # here would make a real persistence failure look like an ordinary 500 with
        # no backend evidence, which is forbidden.
        logger.exception("Error clearing verification for %s", memory_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to clear verification",
                "memory_id": memory_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }
        ) from exc


async def get_memory_record_diagnostics(
    request: Request,
    memory_id: str,
) -> MemoryRecordDiagnosticsPayload:
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(status_code=503, detail="Memory service unavailable")
        return build_memory_record_diagnostics_payload(service, memory_id=memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到 ID 为 {memory_id} 的记忆记录") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching memory diagnostics for %s", memory_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to fetch memory diagnostics",
                "memory_id": memory_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def verify_memory_record(
    request: Request,
    memory_id: str,
) -> MemoryRepairTicketItem:
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(status_code=503, detail="Memory service unavailable")
        return build_memory_repair_ticket_item(service.verify_record(memory_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到 ID 为 {memory_id} 的记忆记录") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error verifying memory record %s", memory_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to verify memory record",
                "memory_id": memory_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def repair_memory_record(
    request: Request,
    memory_id: str,
) -> MemoryRepairTicketItem:
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(status_code=503, detail="Memory service unavailable")
        return build_memory_repair_ticket_item(service.repair_record(memory_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到 ID 为 {memory_id} 的记忆记录") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error repairing memory record %s", memory_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to repair memory record",
                "memory_id": memory_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def get_memory_repair_scheduler_status(request: Request) -> MemoryRepairSchedulerStatusPayload:
    scheduler = _get_memory_repair_scheduler(request)
    if scheduler is None:
        return MemoryRepairSchedulerStatusPayload(
            enabled=False,
            interval_seconds=0,
            last_cycle_at=None,
            last_summary={"status": "offline"},
        )
    try:
        return MemoryRepairSchedulerStatusPayload.model_validate(scheduler.get_status())
    except Exception as exc:
        logger.exception("Error fetching memory repair scheduler status")
        raise HTTPException(status_code=500, detail=f"Failed to fetch memory repair scheduler status: {exc}") from exc


async def trigger_memory_repair_all(request: Request) -> MemoryRepairAllPayload:
    try:
        service = _get_memory_service(request)
        if service is None:
            raise HTTPException(status_code=503, detail="Memory service unavailable")
        items = list(service.repair_all())
        scheduler = _get_memory_repair_scheduler(request)
        scheduler_status = scheduler.get_status() if scheduler is not None else {
            "enabled": False,
            "interval_seconds": 0,
            "last_cycle_at": None,
            "last_summary": {"status": "offline"},
        }
        return build_memory_repair_all_payload(
            items=items,
            scheduler_status=scheduler_status,
            triggered_by="web_console_manual",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error triggering memory repair_all")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to trigger memory repair_all",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc
