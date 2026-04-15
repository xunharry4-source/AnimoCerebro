"""Memory Handler Operations - Write & Management Layer

⚠️  SERVICE LAYER - OPERATIONS & MUTATIONS
════════════════════════════════════════════════════════════════════
This module handles all memory write operations, state changes, and
management actions. Query operations are in memory_commons.py.
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import Request, HTTPException

from zentex.web_console.contracts.memory import (
    EnhancedMemoryRecordItem,
    UpdateEnhancedMemoryRequest,
)
from zentex.web_console.dependencies import (
    get_enhanced_memory_service,
    get_consolidation_engine,
)
from zentex.web_console.services.memory import build_enhanced_memory_record_item

logger = logging.getLogger(__name__)


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
        service = get_enhanced_memory_service(request)
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
        logger.error(f"Error updating memory record {memory_id}: {exc}", exc_info=True)
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
        from zentex.web_console.dependencies import get_consolidation_engine
        consolidation_engine = get_consolidation_engine(request)
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
        logger.error(f"Error triggering consolidation: {exc}")
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
        service = get_enhanced_memory_service(request)
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
        logger.error(f"Error clearing verification for {memory_id}: {exc}", exc_info=True)
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
