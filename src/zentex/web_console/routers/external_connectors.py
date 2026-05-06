from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.external_connectors.models import (
    ConnectorError,
    ConnectorRegistrationRequest,
    ConnectorTestCallRequest,
    ConnectorUpdateRequest,
)
from zentex.external_connectors.service import resolve_service
from .module_log_writer import record_module_management_log


router = APIRouter(prefix="/external-connectors", tags=["external-connectors"])


def _service(request: Request) -> Any:
    app_state = getattr(request.app, "state", None)
    candidate = getattr(app_state, "external_connector_service", None) if app_state is not None else None
    return resolve_service(candidate)


def _error(exc: ConnectorError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error_code": exc.error_code,
            "error_stage": exc.error_stage,
            "operator_message": exc.operator_message,
            "recovery_hint": exc.recovery_hint,
        },
    )


@router.get("")
def list_external_connectors(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _service(request).list_connectors()]


@router.get("/statistics")
def get_external_connector_statistics(request: Request) -> dict[str, Any]:
    return _service(request).get_external_connector_statistics()


@router.get("/plugin-manifests")
def list_external_connector_plugin_manifests(request: Request) -> list[dict[str, Any]]:
    return _service(request).list_plugin_manifests()


@router.post("")
def register_external_connector(payload: ConnectorRegistrationRequest, request: Request) -> dict[str, Any]:
    try:
        record = _service(request).register_connector(payload)
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="register",
            action_label="已注册",
            object_id=record.connector_id,
            object_label=record.display_name,
            before_status=None,
            after_status=record.status.value,
            reason="通过外部连接器管理页注册新连接器",
            details={"connector_type": record.connector_type.value, "target_app": record.target_app},
        )
        return record.model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.post("/register-from-manifest")
def register_external_connector_from_manifest(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        record = _service(request).register_from_manifest(
            manifest_path=payload.get("manifest_path"),
            connector_id=payload.get("connector_id"),
            connector_id_override=payload.get("connector_id_override"),
            display_name=payload.get("display_name"),
            description=payload.get("description"),
            connection_config=payload.get("connection_config") if isinstance(payload.get("connection_config"), dict) else None,
            permission_scope=payload.get("permission_scope") if isinstance(payload.get("permission_scope"), dict) else None,
        )
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="register",
            action_label="已从 manifest 注册",
            object_id=record.connector_id,
            object_label=record.display_name,
            before_status=None,
            after_status=record.status.value,
            reason="通过插件 manifest 注册外部连接器",
            details={"manifest_path": record.manifest_path, "target_app": record.target_app},
        )
        return record.model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.get("/{connector_id}")
def get_external_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        return _service(request).get_connector(connector_id).model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.put("/{connector_id}")
def update_external_connector(
    connector_id: str,
    payload: ConnectorUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        service = _service(request)
        before = service.get_connector(connector_id)
        updated = service.update_connector(connector_id, payload)
        changed_fields = [
            name
            for name, value in payload.model_dump(mode="json").items()
            if value is not None
        ]
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="update",
            action_label="配置已修改",
            object_id=connector_id,
            object_label=updated.display_name,
            before_status=before.status.value,
            after_status=updated.status.value,
            reason="操作员修改连接器配置",
            details={"changed_fields": changed_fields},
        )
        return updated.model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.post("/{connector_id}/activate")
def activate_external_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        service = _service(request)
        before = service.get_connector(connector_id)
        updated = service.activate_connector(connector_id)
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="status_change",
            action_label="已启用",
            object_id=connector_id,
            object_label=updated.display_name,
            before_status=before.status.value,
            after_status=updated.status.value,
            reason="操作员启用连接器，允许后续能力调用",
        )
        return updated.model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.post("/{connector_id}/disable")
def disable_external_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        service = _service(request)
        before = service.get_connector(connector_id)
        updated = service.disable_connector(connector_id)
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="status_change",
            action_label="已停用",
            object_id=connector_id,
            object_label=updated.display_name,
            before_status=before.status.value,
            after_status=updated.status.value,
            reason="操作员停用连接器，后续任务不会再调用该连接器",
        )
        return updated.model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.delete("/{connector_id}")
def delete_external_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        service = _service(request)
        before = service.get_connector(connector_id)
        result = service.delete_connector(connector_id)
        record_module_management_log(
            request,
            source_module="connector",
            module_label="外部连接器",
            action="delete",
            action_label="已删除",
            object_id=connector_id,
            object_label=before.display_name,
            before_status=before.status.value,
            after_status="deleted",
            reason="操作员删除连接器注册记录",
            details={"target_app": before.target_app, "connector_type": before.connector_type.value},
        )
        return result
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.get("/{connector_id}/health")
def get_external_connector_health(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        return _service(request).health_check(connector_id).model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.post("/{connector_id}/test-call")
def test_external_connector(
    connector_id: str,
    payload: ConnectorTestCallRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return _service(request).test_call(connector_id, payload).model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.get("/{connector_id}/history")
def get_external_connector_history(connector_id: str, request: Request) -> list[dict[str, Any]]:
    try:
        return [item.model_dump(mode="json") for item in _service(request).history(connector_id)]
    except ConnectorError as exc:
        raise _error(exc) from exc
