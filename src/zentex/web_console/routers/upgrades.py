from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi import Depends

from zentex.upgrade.models import LLMUpgradeIntentRequest, PluginEvolutionIntentRequest
from zentex.upgrade.management import UpgradeLifecycleView, UpgradeTargetKind
from zentex.web_console.contracts.upgrades import (
    ExecuteLLMUpgradeRequest,
    ExecutePluginEvolutionRequest,
    UpgradeAuditEventItem,
    UpgradeActionRequest,
    UpgradeMemoryRecordItem,
    UpgradeOverviewPayload,
    UpgradeRecordCollection,
    UpgradeRecordItem,
    UpgradesByLifecycleViewPayload,
)
from zentex.web_console.dependencies import get_upgrade_audit_store
from zentex.web_console.dependencies import get_upgrade_evidence_service
from zentex.web_console.dependencies import get_upgrade_execution_service
from zentex.web_console.dependencies import get_upgrade_management_store
from zentex.web_console.dependencies import get_upgrade_memory_store
from zentex.web_console.dependencies import get_plugin_evolution_runtime
from zentex.web_console.services.upgrades import (
    build_upgrade_audit_event_item,
    build_upgrade_collection,
    build_upgrade_memory_record_item,
    build_upgrade_overview,
    build_upgrade_record_item,
    build_upgrades_by_lifecycle_view,
)


router = APIRouter()


@router.get("/upgrades/overview", response_model=UpgradeOverviewPayload)
def get_upgrade_overview(
    store=Depends(get_upgrade_management_store),
) -> UpgradeOverviewPayload:
    return build_upgrade_overview(store)


@router.get("/upgrades/by-lifecycle-view", response_model=UpgradesByLifecycleViewPayload)
def get_upgrades_by_lifecycle_view(
    target_kind: str | None = None,
    plugin_action: str | None = None,
    store=Depends(get_upgrade_management_store),
) -> UpgradesByLifecycleViewPayload:
    """Get upgrades grouped by lifecycle view for tabbed display."""
    from zentex.upgrade.management import UpgradeTargetKind
    
    tk = None
    if target_kind:
        try:
            tk = UpgradeTargetKind(target_kind)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid target_kind: {target_kind}")
    
    return build_upgrades_by_lifecycle_view(
        store,
        target_kind=tk,
        plugin_action=plugin_action,
    )


@router.get("/upgrades/llm", response_model=UpgradeRecordCollection)
def list_llm_upgrades(
    lifecycle: UpgradeLifecycleView = UpgradeLifecycleView.ALL,
    store=Depends(get_upgrade_management_store),
) -> UpgradeRecordCollection:
    return build_upgrade_collection(
        store,
        target_kind=UpgradeTargetKind.LLM,
        lifecycle=lifecycle,
    )


@router.get("/upgrades/plugins", response_model=UpgradeRecordCollection)
def list_plugin_evolutions(
    lifecycle: UpgradeLifecycleView = UpgradeLifecycleView.ALL,
    action: str | None = None,
    store=Depends(get_upgrade_management_store),
) -> UpgradeRecordCollection:
    return build_upgrade_collection(
        store,
        target_kind=UpgradeTargetKind.PLUGIN,
        lifecycle=lifecycle,
        action=action,
    )


@router.get("/upgrades/{record_id}", response_model=UpgradeRecordItem)
def get_upgrade_record(
    record_id: str,
    request: Request,
    store=Depends(get_upgrade_management_store),
) -> UpgradeRecordItem:
    try:
        record = store.get(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown upgrade record: {record_id}") from exc
    return build_upgrade_record_item(record)


@router.get("/upgrades/{record_id}/audit-events", response_model=list[UpgradeAuditEventItem])
def list_upgrade_audit_events(
    record_id: str,
    audit_store=Depends(get_upgrade_audit_store),
) -> list[UpgradeAuditEventItem]:
    return [
        build_upgrade_audit_event_item(event)
        for event in audit_store.list_events(record_id=record_id)
    ]


@router.get("/upgrades/{record_id}/memory-records", response_model=list[UpgradeMemoryRecordItem])
def list_upgrade_memory_records(
    record_id: str,
    memory_store=Depends(get_upgrade_memory_store),
) -> list[UpgradeMemoryRecordItem]:
    return [
        build_upgrade_memory_record_item(record)
        for record in memory_store.list_records(record_id=record_id)
    ]


@router.post("/upgrades/llm/execute", response_model=UpgradeRecordItem)
def execute_llm_upgrade(
    payload: ExecuteLLMUpgradeRequest,
    execution_service=Depends(get_upgrade_execution_service),
) -> UpgradeRecordItem:
    try:
        record = execution_service.execute_llm_upgrade(
            LLMUpgradeIntentRequest.model_validate(payload.model_dump())
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(
            status_code=409,
            detail="The request did not require an LLM upgrade.",
        )
    return build_upgrade_record_item(record)


@router.post("/upgrades/plugins/execute", response_model=UpgradeRecordItem)
def execute_plugin_evolution(
    payload: ExecutePluginEvolutionRequest,
    execution_service=Depends(get_upgrade_execution_service),
) -> UpgradeRecordItem:
    try:
        record = execution_service.execute_plugin_evolution(
            PluginEvolutionIntentRequest.model_validate(payload.model_dump())
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(
            status_code=409,
            detail="The request did not require plugin evolution.",
        )
    return build_upgrade_record_item(record)


@router.post("/upgrades/{record_id}/cancel", response_model=UpgradeRecordItem)
def cancel_upgrade_record(
    record_id: str,
    payload: UpgradeActionRequest,
    store=Depends(get_upgrade_management_store),
    evidence_service=Depends(get_upgrade_evidence_service),
) -> UpgradeRecordItem:
    try:
        record = store.cancel(record_id, reason=payload.reason)
        evidence_service.record_event(
            record,
            event_type="upgrade_cancelled",
            summary="Upgrade record was cancelled by an operator action.",
            payload={"cancel_reason": payload.reason},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown upgrade record: {record_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return build_upgrade_record_item(record)


@router.post("/upgrades/{record_id}/cleanup-failed-candidate", response_model=UpgradeRecordItem)
def cleanup_failed_plugin_candidate(
    record_id: str,
    payload: UpgradeActionRequest,
    store=Depends(get_upgrade_management_store),
    plugin_runtime=Depends(get_plugin_evolution_runtime),
    evidence_service=Depends(get_upgrade_evidence_service),
) -> UpgradeRecordItem:
    try:
        record_before = store.get(record_id)
        if record_before.candidate_path:
            plugin_runtime.cleanup_candidate_path(
                candidate_plugin_path=record_before.candidate_path
            )
        record = store.cleanup_failed_candidate(record_id, reason=payload.reason)
        evidence_service.record_event(
            record,
            event_type="failed_candidate_cleaned_up",
            summary="Failed plugin candidate was removed after evidence retention.",
            payload={"cleanup_reason": payload.reason},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown upgrade record: {record_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return build_upgrade_record_item(record)
