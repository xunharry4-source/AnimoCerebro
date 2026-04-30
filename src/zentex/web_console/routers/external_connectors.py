from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.external_connectors.models import (
    ConnectorError,
    ConnectorRegistrationRequest,
    ConnectorTestCallRequest,
    ConnectorUpdateRequest,
)
from zentex.external_connectors.service import ExternalConnectorService


router = APIRouter(prefix="/external-connectors", tags=["external-connectors"])


def _service(request: Request) -> ExternalConnectorService:
    service = getattr(request.app.state, "external_connector_service", None)
    if service is None:
        service = ExternalConnectorService(transcript_store=getattr(request.app.state, "transcript_store", None))
        request.app.state.external_connector_service = service
    return service


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


@router.get("/plugin-manifests")
def list_external_connector_plugin_manifests(request: Request) -> list[dict[str, Any]]:
    return _service(request).list_plugin_manifests()


@router.post("")
def register_external_connector(payload: ConnectorRegistrationRequest, request: Request) -> dict[str, Any]:
    try:
        return _service(request).register_connector(payload).model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.post("/register-from-manifest")
def register_external_connector_from_manifest(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return _service(request).register_from_manifest(
            manifest_path=payload.get("manifest_path"),
            connector_id=payload.get("connector_id"),
            connector_id_override=payload.get("connector_id_override"),
            display_name=payload.get("display_name"),
            description=payload.get("description"),
            connection_config=payload.get("connection_config") if isinstance(payload.get("connection_config"), dict) else None,
            permission_scope=payload.get("permission_scope") if isinstance(payload.get("permission_scope"), dict) else None,
        ).model_dump(mode="json")
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
        return _service(request).update_connector(connector_id, payload).model_dump(mode="json")
    except ConnectorError as exc:
        raise _error(exc) from exc


@router.delete("/{connector_id}")
def delete_external_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        return _service(request).delete_connector(connector_id)
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
