from __future__ import annotations
from typing import List


from fastapi import APIRouter, HTTPException, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    ForceEnablePluginResponse,
    PluginActionRequest,
    PluginRelationActionRequest,
    PluginFeatureGroupItem,
    FunctionalPluginDetailResponse,
    PluginVersionHistoryItem,
    PluginTestRequest,
    PluginTestResponse,
)
from zentex.web_console.dependencies import (
    get_cognitive_tool_registry,
    get_managed_plugin_records,
    get_plugin_feature_catalog,
    get_plugin_registry,
    get_plugin_service,
)
from zentex.web_console.services.plugins import (
    build_cognitive_plugin_detail,
    build_cognitive_plugin_list,
    build_force_enable_response,
    build_plugin_feature_groups,
    build_plugin_payloads,
    build_functional_plugin_detail,
    build_functional_plugin_list,
    force_disable_managed_plugin,
    force_enable_managed_plugin,
    run_managed_plugin_test,
)


router = APIRouter()


@router.get("/plugins/cognitive", response_model=List[CognitivePluginStatusItem])
def list_cognitive_plugins(
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> List[CognitivePluginStatusItem]:
    return build_cognitive_plugin_list(
        cognitive_registry,
        get_plugin_registry(request),
        get_managed_plugin_records(request),
    )


@router.get("/plugins/functional", response_model=List[CognitivePluginStatusItem])
def list_functional_plugins(
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> List[CognitivePluginStatusItem]:
    return build_functional_plugin_list(
        cognitive_registry,
        get_plugin_registry(request),
        get_managed_plugin_records(request),
    )


@router.get("/plugins", response_model=List[PluginFeatureGroupItem])
def list_plugins_by_feature(
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> List[PluginFeatureGroupItem]:
    return build_plugin_feature_groups(
        cognitive_registry,
        get_plugin_registry(request),
        get_managed_plugin_records(request),
        get_plugin_feature_catalog(request),
    )


@router.get("/plugins/cognitive/{plugin_id}", response_model=CognitivePluginDetailResponse)
def get_cognitive_plugin_detail(
    plugin_id: str,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> CognitivePluginDetailResponse:
    plugin_service = get_plugin_service(request)
    try:
        return build_cognitive_plugin_detail(
            cognitive_registry,
            get_plugin_registry(request),
            get_managed_plugin_records(request),
            plugin_service,
            plugin_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/plugins/functional/{plugin_id}", response_model=FunctionalPluginDetailResponse)
def get_functional_plugin_detail(
    plugin_id: str,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> FunctionalPluginDetailResponse:
    plugin_service = get_plugin_service(request)
    try:
        return build_functional_plugin_detail(
            cognitive_registry,
            get_plugin_registry(request),
            get_managed_plugin_records(request),
            plugin_service,
            plugin_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/plugins/{plugin_id}/history", response_model=List[PluginVersionHistoryItem])
def get_plugin_history(
    plugin_id: str,
    request: Request,
) -> List[PluginVersionHistoryItem]:
    plugin_service = get_plugin_service(request)
    if plugin_service is None or not hasattr(plugin_service, "get_upgrade_history"):
        return []
    history = []
    for item in list(plugin_service.get_upgrade_history(plugin_id) or []):
        history.append(
            PluginVersionHistoryItem(
                plugin_id=getattr(item, "plugin_id", plugin_id),
                version=str(getattr(item, "version", "")),
                status=str(getattr(item, "status", "")),
                started_at=getattr(item, "started_at", None),
                completed_at=getattr(item, "completed_at", None),
                error_message=getattr(item, "error_message", None),
                previous_version=getattr(item, "previous_version", None),
            )
        )
    return history


@router.post("/plugins/cognitive/{plugin_id}/functional/{functional_id}/bind", response_model=CognitivePluginDetailResponse)
def bind_functional_plugin_to_cognitive(
    plugin_id: str,
    functional_id: str,
    payload: PluginRelationActionRequest,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> CognitivePluginDetailResponse:
    plugin_service = get_plugin_service(request)
    if plugin_service is None:
        raise HTTPException(status_code=503, detail="plugin_service is not attached")
    try:
        plugin_service.bind_cognitive_functional(
            cognitive_plugin_id=plugin_id,
            functional_plugin_id=functional_id,
            role=payload.role,
            priority=payload.priority,
            fallback_id=payload.fallback_id,
        )
        return build_cognitive_plugin_detail(
            cognitive_registry,
            get_plugin_registry(request),
            get_managed_plugin_records(request),
            plugin_service,
            plugin_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/plugins/cognitive/{plugin_id}/functional/{functional_id}/bind", response_model=CognitivePluginDetailResponse)
def unbind_functional_plugin_from_cognitive(
    plugin_id: str,
    functional_id: str,
    payload: PluginRelationActionRequest,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> CognitivePluginDetailResponse:
    plugin_service = get_plugin_service(request)
    if plugin_service is None:
        raise HTTPException(status_code=503, detail="plugin_service is not attached")
    try:
        plugin_service.unbind_cognitive_functional(plugin_id, functional_id)
        return build_cognitive_plugin_detail(
            cognitive_registry,
            get_plugin_registry(request),
            get_managed_plugin_records(request),
            plugin_service,
            plugin_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/plugins/cognitive/{plugin_id}/functional/{functional_id}/test", response_model=PluginTestResponse)
def test_functional_plugin_from_cognitive(
    plugin_id: str,
    functional_id: str,
    payload: PluginTestRequest,
    request: Request,
) -> PluginTestResponse:
    return run_managed_plugin_test(
        request,
        plugin_id=functional_id,
        audit_reason=payload.audit_reason,
        idempotency_key=payload.idempotency_key,
    )


@router.post("/plugins/{plugin_id}/force-enable", response_model=ForceEnablePluginResponse)
def force_enable_plugin(
    plugin_id: str,
    payload: PluginActionRequest,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> ForceEnablePluginResponse:
    try:
        if plugin_id in {registration.plugin_id for registration in cognitive_registry.list_registrations()}:
            result = cognitive_registry.force_enable_plugin(
                plugin_id,
                audit_reason=payload.audit_reason,
                allow_overwrite_active=payload.allow_overwrite_active,
            )
            auto_disabled = list(result.auto_disabled_plugin_ids)
            enabled_plugin_id = result.registration.spec.plugin_id
            requires_override_warning = result.requires_override_warning
            message = result.message
        else:
            result2 = force_enable_managed_plugin(
                request,
                plugin_id,
                payload.audit_reason,
                allow_overwrite_active=payload.allow_overwrite_active,
            )
            auto_disabled = list(result2.auto_disabled_plugin_ids)
            enabled_plugin_id = result2.plugin_id
            requires_override_warning = False
            message = "ok"
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return build_force_enable_response(
        cognitive_registry,
        get_plugin_registry(request),
        get_managed_plugin_records(request),
        enabled_plugin_id=enabled_plugin_id,
        auto_disabled_plugin_ids=auto_disabled,
        requires_override_warning=requires_override_warning,
        message=message,
    )


@router.post("/plugins/{plugin_id}/force-disable", response_model=CognitivePluginStatusItem)
def force_disable_plugin(
    plugin_id: str,
    payload: PluginActionRequest,
    cognitive_registry: Annotated[CognitiveToolRegistry, Depends(get_cognitive_tool_registry)],
    request: Request,
) -> CognitivePluginStatusItem:
    try:
        if plugin_id in {registration.plugin_id for registration in cognitive_registry.list_registrations()}:
            target_plugin_id = cognitive_registry.force_disable_plugin(
                plugin_id,
                audit_reason=payload.audit_reason,
            ).spec.plugin_id
        else:
            target_plugin_id = force_disable_managed_plugin(
                request,
                plugin_id,
                payload.audit_reason,
            ).plugin.plugin_id
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    item = next(
        item
        for item in build_plugin_payloads(
            cognitive_registry,
            get_plugin_registry(request),
            get_managed_plugin_records(request),
        )
        if item.tool_id == target_plugin_id
    )
    return item


@router.post("/plugins/{plugin_id}/test", response_model=PluginTestResponse)
def test_plugin(
    plugin_id: str,
    payload: PluginTestRequest,
    request: Request,
) -> PluginTestResponse:
    return run_managed_plugin_test(
        request,
        plugin_id=plugin_id,
        audit_reason=payload.audit_reason,
        idempotency_key=payload.idempotency_key,
    )

