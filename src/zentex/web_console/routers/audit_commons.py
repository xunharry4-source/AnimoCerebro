"""Audit query layer — reads only from the canonical AuditService store."""

from typing import Any, Dict, List, Optional
import logging

from fastapi import HTTPException, Request

from zentex.web_console.contracts.audit import AuditPagePayload, AuditTraceStartsPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.audit import AuditGraphPayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.services.audit import build_audit_graph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_audit_service(request: Request) -> Any:
    return getattr(request.app.state, "audit_service", None)


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

async def query_flow_health(
    request: Request,
    *,
    limit: int = 100,
    flow_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent audit flows for the health-monitor panel.

    Each entry: audit_id, flow_type, source_module, status, started_at, ended_at.
    This data is written directly by route handlers — no sync required.
    """
    audit_service = _get_audit_service(request)
    if audit_service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_service_unavailable",
                "message": "Audit service is unavailable",
            },
        )
    try:
        return audit_service.query_flows(limit=limit, flow_type=flow_type, status=status)
    except Exception as exc:
        # Do not fake "no recent flows" when the flow-health backend failed.
        logger.exception("Failed to query audit flows")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_flow_query_failed",
                "message": "Failed to query audit flows",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def query_trace_starts(
    request: Request,
    *,
    page: int = 1,
    page_size: int = 40,
) -> AuditTraceStartsPagePayload:
    audit_service = _get_audit_service(request)
    if audit_service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_service_unavailable",
                "message": "Audit service is unavailable",
            },
        )
    try:
        return audit_service.query_trace_starts_page(page=page, page_size=page_size)
    except Exception as exc:
        logger.exception("Failed to query audit trace starts")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_trace_start_query_failed",
                "message": "Failed to query audit trace starts",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def query_model_provider_traces(request: Request, facade: object) -> List[ModelProviderTraceItem]:
    """Query persisted model-provider traces from the canonical audit store."""
    try:
        audit_service = _get_audit_service(request)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        traces = audit_service.query_model_provider_traces()
        logger.info("Retrieved %d persisted model provider traces", len(traces))
        return traces
    except Exception as exc:
        # Do not fake an empty trace list when the audit trace plane failed.
        logger.exception("Failed to query model provider traces")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "model_provider_trace_query_failed",
                "message": "Failed to query model provider traces",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def query_turn_audit_milestones(
    request: Request,
    facade: object,
    page: int = 1,
    page_size: int = 40,
) -> TurnAuditPagePayload:
    """Query turn-level audit milestones from the canonical audit store."""
    try:
        audit_service = _get_audit_service(request)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        return audit_service.query_turn_audit_items(page=page, page_size=page_size)
    except Exception as exc:
        # Do not fake an empty turn-audit page when the audit backend failed.
        logger.exception("Failed to query turn audit milestones")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "turn_audit_query_failed",
                "message": "Failed to query turn audit milestones",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def query_audit_entries(
    request: Request,
    facade: object,
    page: int = 1,
    page_size: int = 40,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None,
) -> AuditPagePayload:
    """Query audit entries from the canonical audit store."""
    try:
        audit_service = _get_audit_service(request)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        return audit_service.query_audit_entries(
            page=page,
            page_size=page_size,
            request_id=request_id,
            decision_id=decision_id,
        )
    except Exception as exc:
        # Do not fake an empty audit page when the audit backend failed.
        logger.exception("Failed to query audit entries")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_entry_query_failed",
                "message": "Failed to query audit entries",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


async def query_audit_graph(
    request: Request,
    facade: object,
    *,
    mode: str,
) -> AuditGraphPayload:
    try:
        audit_service = _get_audit_service(request)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        audit_page = audit_service.query_audit_entries(page=1, page_size=500)
        model_traces = audit_service.query_model_provider_traces()
        return build_audit_graph(mode=mode, audit_items=audit_page.items, model_provider_traces=model_traces)
    except Exception as exc:
        # Do not fabricate a graph from stale fallback data after audit assembly has
        # already failed. Return an explicitly degraded graph so operators can see
        # the audit plane is unhealthy instead of trusting mismatched data.
        logger.exception("Failed to query audit graph")
        return AuditGraphPayload(
            mode=mode,
            title="Audit Trace Graph",
            subtitle="Audit graph degraded due to backend failure",
            database_backed=False,
            generated_at="",
            summary={
                "health_status": "degraded",
                "degradation_reason": type(exc).__name__,
                "error_message": str(exc),
            },
            lanes=[],
            edges=[],
        )
