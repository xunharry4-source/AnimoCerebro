"""
Environment Awareness Router / 环境感知路由

Provides HTTP API endpoints for environment awareness module.
Implements RESTful API for host state sampling, situation interpretation,
signal sanitization, and context snapshot management.

提供环境感知模块的 HTTP API 端点。
实现用于宿主状态采样、态势解释、信号清洗和上下文快照管理的 RESTful API。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from zentex.environment.service import get_environment_service

router = APIRouter(prefix="/api/v1/environment", tags=["environment"])


def _get_service() -> Any:
    """Resolve the environment module through its public service entrypoint."""
    return get_environment_service()


@router.get("/host-state")
def get_host_state():
    """
    Get current physical host state.
    
    获取当前物理宿主状态。
    
    Returns:
        PhysicalHostState with CPU, memory, disk, network metrics
    """
    try:
        service = _get_service()
        state = service.sample_host_state()
        
        return {
            "status": "success",
            "data": {
                "timestamp": state.timestamp.isoformat(),
                "hostname": state.hostname,
                "platform": state.platform,
                "python_version": state.python_version,
                "memory": {
                    "pressure": state.memory_pressure.value,
                    "used_ratio": state.memory_used_ratio,
                    "total_bytes": state.memory_total_bytes,
                    "available_bytes": state.memory_available_bytes,
                },
                "cpu": {
                    "load_percent": state.cpu_load_percent,
                    "count": state.cpu_count,
                },
                "disk": {
                    "usage_percent": state.disk_usage_percent,
                    "free_bytes": state.disk_free_bytes,
                },
                "network": {
                    "health": state.network_health.value,
                    "interfaces_configured": state.network_interfaces_configured,
                    "interfaces_active": state.network_interfaces_active,
                },
                "overall_health": state.overall_health.value,
                "warnings": state.warnings,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sample host state: {str(e)}")


@router.post("/interpret")
def interpret_environment(
    current_role: Optional[str] = Query(None, description="Current agent role"),
    active_goals: Optional[List[str]] = Query(None, description="Active goal IDs"),
):
    """
    Interpret current environment and get situation impact.
    
    解释当前环境并获取态势影响。
    
    Args:
        current_role: Agent's current role (optional)
        active_goals: List of active goal IDs (optional)
    
    Returns:
        SituationImpact with recommendations and risk assessment
    """
    try:
        service = _get_service()
        host_state, impact = service.sample_and_interpret(
            current_role=current_role,
            active_goals=active_goals or [],
        )
        
        return {
            "status": "success",
            "data": {
                "interpretation_id": impact.interpretation_id,
                "timestamp": impact.timestamp.isoformat(),
                "risk_level": impact.risk_level,
                "requires_rational_audit": impact.requires_rational_audit,
                "recommended_cognitive_mode": impact.recommended_cognitive_mode,
                "role_impact": impact.role_impact,
                "goal_impacts": impact.goal_impacts,
                "recommended_actions": impact.recommended_actions,
                "reasoning": impact.reasoning,
                "source_host_state": {
                    "memory_pressure": host_state.memory_pressure.value,
                    "network_health": host_state.network_health.value,
                    "overall_health": host_state.overall_health.value,
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to interpret environment: {str(e)}")


@router.post("/sanitize")
def sanitize_signal(
    payload: Dict[str, Any],
):
    """
    Sanitize a raw sensory signal.
    
    清洗原始感官信号。
    
    Request Body:
        - signal: Raw signal text (required)
        - source_plugin_id: Source plugin identifier (optional)
        - source_kind: Source kind (optional)
    
    Returns:
        SanitizedSignal with injection risk assessment
    """
    try:
        signal = payload.get("signal")
        if not signal or not isinstance(signal, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'signal' field")
        
        service = _get_service()
        result = service.sanitize_signal(
            raw_signal=signal,
            source_plugin_id=payload.get("source_plugin_id"),
            source_kind=payload.get("source_kind"),
        )
        
        return {
            "status": "success",
            "data": {
                "signal_id": result.signal_id,
                "original_fingerprint": result.original_fingerprint,
                "sanitized_content": result.sanitized_content,
                "injection_risk": result.injection_risk,
                "redaction_evidence": result.redaction_evidence,
                "confidence_score": result.confidence_score,
                "source_plugin_id": result.source_plugin_id,
                "source_kind": result.source_kind,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sanitize signal: {str(e)}")


@router.post("/snapshot")
def create_snapshot(payload: Dict[str, Any]):
    """
    Create a new context snapshot.
    
    创建新的上下文快照。
    
    Request Body:
        - session_id: Session identifier (optional)
        - turn_id: Turn identifier (optional)
        - current_role: Current role (optional)
        - working_memory_summary: Memory summary (optional)
        - tags: List of tags (optional)
    
    Returns:
        ContextSnapshot with metadata
    """
    try:
        service = _get_service()
        snapshot = service.create_context_snapshot(
            session_id=payload.get("session_id"),
            turn_id=payload.get("turn_id"),
            current_role=payload.get("current_role"),
            working_memory_summary=payload.get("working_memory_summary"),
            tags=payload.get("tags", []),
        )
        
        return {
            "status": "success",
            "data": {
                "snapshot_id": snapshot.snapshot_id,
                "timestamp": snapshot.timestamp.isoformat(),
                "session_id": snapshot.session_id,
                "turn_id": snapshot.turn_id,
                "current_role": snapshot.current_role,
                "tags": snapshot.tags,
                "host_state_summary": {
                    "memory_pressure": snapshot.host_state.memory_pressure.value if snapshot.host_state else None,
                    "overall_health": snapshot.host_state.overall_health.value if snapshot.host_state else None,
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create snapshot: {str(e)}")


@router.get("/snapshots/recent")
def get_recent_snapshots(
    count: int = Query(10, ge=1, le=100, description="Number of recent snapshots"),
):
    """
    Get recent context snapshots.
    
    获取最近的上下文快照。
    
    Args:
        count: Number of snapshots to retrieve (1-100)
    
    Returns:
        List of recent snapshots
    """
    try:
        service = _get_service()
        snapshots = service.get_recent_snapshots(count=count)
        
        return {
            "status": "success",
            "count": len(snapshots),
            "data": [
                {
                    "snapshot_id": s.snapshot_id,
                    "timestamp": s.timestamp.isoformat(),
                    "session_id": s.session_id,
                    "turn_id": s.turn_id,
                    "current_role": s.current_role,
                    "tags": s.tags,
                }
                for s in snapshots
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent snapshots: {str(e)}")


@router.get("/snapshots/query")
def query_snapshots(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
):
    """
    Query context snapshots with filters.
    
    查询带过滤器的上下文快照。
    
    Args:
        session_id: Filter by session ID (optional)
        tag: Filter by tag (optional)
    
    Returns:
        Filtered list of snapshots
    """
    try:
        service = _get_service()
        snapshots = service.query_snapshots(session_id=session_id, tag=tag)
        
        return {
            "status": "success",
            "count": len(snapshots),
            "filters": {
                "session_id": session_id,
                "tag": tag,
            },
            "data": [
                {
                    "snapshot_id": s.snapshot_id,
                    "timestamp": s.timestamp.isoformat(),
                    "session_id": s.session_id,
                    "turn_id": s.turn_id,
                    "current_role": s.current_role,
                    "tags": s.tags,
                }
                for s in snapshots
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query snapshots: {str(e)}")


@router.post("/compare")
def compare_sources(payload: Dict[str, Any]):
    """
    Compare values from multiple sources to detect conflicts.
    
    比较多个源的值以检测冲突。
    
    Request Body:
        - sources: Dict mapping source_id to value (required)
        - field_name: Field being compared (optional)
    
    Returns:
        List of detected conflicts
    """
    try:
        sources = payload.get("sources")
        if not sources or not isinstance(sources, dict):
            raise HTTPException(status_code=400, detail="Missing or invalid 'sources' field")
        
        if len(sources) < 2:
            raise HTTPException(status_code=400, detail="At least 2 sources required for comparison")
        
        service = _get_service()
        conflicts = service.compare_multiple_sources(
            sources=sources,
            field_name=payload.get("field_name", "value"),
        )
        
        return {
            "status": "success",
            "conflict_count": len(conflicts),
            "data": [
                {
                    "conflict_id": c.conflict_id,
                    "source_a": c.source_a,
                    "source_b": c.source_b,
                    "conflict_type": c.conflict_type,
                    "conflict_field": c.conflict_field,
                    "value_a": c.value_a,
                    "value_b": c.value_b,
                    "conflict_severity": c.conflict_severity,
                    "confidence_in_conflict": c.confidence_in_conflict,
                    "suggested_resolution": c.suggested_resolution,
                    "requires_human_review": c.requires_human_review,
                }
                for c in conflicts
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare sources: {str(e)}")


@router.get("/status")
def get_status():
    """
    Get environment awareness service status.
    
    获取环境感知服务状态。
    
    Returns:
        Service health and configuration info
    """
    try:
        service = _get_service()
        last_state = service.get_last_host_state()
        
        return {
            "status": "healthy",
            "service": "environment_awareness",
            "version": "1.0.0",
            "last_sample": {
                "timestamp": last_state.timestamp.isoformat() if last_state else None,
                "hostname": last_state.hostname if last_state else None,
                "overall_health": last_state.overall_health.value if last_state else None,
            } if last_state else None,
            "features": [
                "host_state_sampling",
                "situation_interpretation",
                "signal_sanitization",
                "context_snapshots",
                "multi_source_comparison",
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service status check failed: {str(e)}")
