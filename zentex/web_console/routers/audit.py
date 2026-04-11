from typing import Any, List
from typing_extensions import Annotated
from fastapi import APIRouter, Depends
from zentex.web_console.contracts.audit import AuditPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.dependencies import get_runtime
from zentex.web_console.services.audit import build_audit_page, build_model_provider_traces, build_turn_audit_page
from zentex.runtime.runtime import BrainRuntime


router = APIRouter()


@router.get("/audit/model-provider", response_model=List[ModelProviderTraceItem])
def list_model_provider_audit_traces(
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
) -> List[ModelProviderTraceItem]:
    return build_model_provider_traces(runtime)


@router.get("/audit/turns", response_model=TurnAuditPagePayload)
def list_turn_audit_milestones(
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    page: int = 1,
    page_size: int = 40,
) -> TurnAuditPagePayload:
    entries = runtime.transcript_store.get_entries_snapshot()
    return build_turn_audit_page(entries, page=page, page_size=page_size)


@router.get("/audits", response_model=AuditPagePayload)
def list_audit_entries(
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    page: int = 1,
    page_size: int = 40,
    request_id: str | None = None,
    decision_id: str | None = None,
) -> AuditPagePayload:
    entries = runtime.transcript_store.get_entries_snapshot()
    return build_audit_page(
        entries,
        page=page,
        page_size=page_size,
        request_id=request_id,
        decision_id=decision_id,
    )
