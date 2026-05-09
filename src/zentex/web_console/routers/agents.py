from __future__ import annotations
"""
Agents Router — HTTP route handlers for agent management and task coordination.

RESPONSIBILITY:
  Exposes REST endpoints for registering, monitoring, and coordinating
  AgentAsset objects.  Does NOT implement agent logic; all coordination
  delegates to AgentCoordinationService and TaskManagementService obtained
  via FastAPI Depends().

CAPABILITIES:
  - GET    /agents                          — list agents with task inbox/receipts
  - POST   /agents/register                 — register a new agent
  - GET    /agents/{id}/handshake           — optional capability discovery
  - POST   /agents/{id}/safety-audit        — legacy alias for local invocation policy evaluation
  - POST   /agents/{id}/invocation-policy   — evaluate Zentex-local invocation policy
  - POST   /agents/{id}/dispatch            — dispatch a task with optional local verification
  - POST   /agents/{id}/credentials         — store encrypted local credentials
  - GET    /agents/{id}/credentials         — list credential metadata only
  - DELETE /agents/{id}/credentials/{cid}   — delete local credential
  - POST   /agents/{id}/auth/test           — test local auth resolution/login
  - DELETE /agents/{id}                     — unregister an agent
  - GET    /agents-health/status            — health check across all agents
  - PATCH  /agents/{id}/policy             — update trust level / scope
  - GET    /agents/{id}/tasks              — list tasks for an agent
  - GET    /agents/{id}/audit              — audit events from transcript store
  - GET    /agents/{id}/detail             — credit score + statistics
  - GET    /agents/{id}/tasks/by-status    — paginated status-filtered task view
  - POST   /agents/{id}/tasks/{tid}/cancel — cancel a task
  - POST   /agents/{id}/tasks/{tid}/retry  — retry a failed task

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - get_agent_coordination_service() and get_task_service() raise HTTPException(503)
    when the underlying service is None.  Route handlers always receive valid
    service objects, never None.

DOES NOT:
  - Own AgentCoordinationService, TaskManagementService, or TranscriptStore.
  - Implement capability discovery, local invocation policy, or dispatch logic directly.
  - Silently return empty results when a required service is absent.
"""

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, Header, HTTPException, Query, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.agents.service import AgentAsset, AgentCoordinationService, AgentRegistrationRequest
from zentex.agents.bridge import AgentBridgeError

logger = logging.getLogger(__name__)
from zentex.tasks.models import TaskStatus
from zentex.tasks import TaskManagementService, ZentexTask
from zentex.web_console.contracts.agents import (
    AgentConsoleRecord,
    AgentPolicyUpdateRequest,
    AgentDispatchTaskRequest,
    AgentCallbackResultRequest,
    AgentAuthTestRequest,
    AgentCredentialUpsertRequest,
    AgentAuditRecord,
)
from zentex.web_console.dependencies import (
    get_agent_coordination_service,
    get_cli_service,
    get_mcp_service,
    get_task_service,
    get_kernel_service_facade,
)
from zentex.web_console.contracts.kernel_service import KernelServiceFacade
from zentex.web_console.services.agents import get_tasks_by_status as handle_get_tasks_by_status
from .agents_handlers import (
    handle_list_agents,
    handle_get_agent_audit_events,
    handle_get_agent_detail,
    handle_cancel_agent_task,
    handle_retry_agent_task,
)
from .module_log_writer import record_module_management_log


router = APIRouter()


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix):].strip()
    return authorization.strip()


def _task_context(task_service: Any, task_id: str) -> dict[str, str]:
    task = task_service.get_task(task_id) if task_id and callable(getattr(task_service, "get_task", None)) else None
    metadata = getattr(task, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "trace_id": str(metadata.get("trace_id") or ""),
        "session_id": str(metadata.get("session_id") or getattr(task, "originator_id", "") or ""),
        "turn_id": str(metadata.get("turn_id") or metadata.get("session_id") or getattr(task, "originator_id", "") or ""),
        "task_title": str(getattr(task, "title", "") or ""),
    }


def _record_agent_workflow_event(
    *,
    event_type: str,
    status: str,
    task_service: Any,
    task_id: str,
    fallback_trace_id: str = "",
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    evidence_ref: str = "",
    error_code: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    from zentex.audit.workflow_events import record_workflow_node_event

    context = _task_context(task_service, task_id)
    record_workflow_node_event(
        event_type=event_type,
        node_id="agent-callback",
        node_name="Agent Callback",
        status=status,
        trace_id=context["trace_id"] or fallback_trace_id,
        session_id=context["session_id"] or "unknown",
        turn_id=context["turn_id"] or context["session_id"] or "unknown",
        task_id=task_id,
        input_summary=input_summary or {},
        output_summary=output_summary or {},
        evidence_ref=evidence_ref,
        error_code=error_code,
        source="zentex.web_console.routers.agents",
        details={
            "task_title": context["task_title"],
            **dict(details or {}),
        },
    )


@router.get("/agents", response_model=List[AgentConsoleRecord])
def list_agents(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[AgentConsoleRecord]:
    """获取所有智能体及其收件箱/回执列表"""
    return handle_list_agents(service, task_service)


@router.get("/agents/statistics")
def get_agent_asset_statistics(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    return service.get_agent_asset_statistics()


@router.post("/agents/register", response_model=AgentAsset)
async def register_agent(
    payload: AgentRegistrationRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    request: Request,
) -> AgentAsset:
    try:
        asset = await service.register_agent(
            payload,
            operator_id=request.client.host if request.client else "unknown",
        )
        record_module_management_log(
            request,
            source_module="agent",
            module_label="Agent",
            action="register",
            action_label="已注册",
            object_id=asset.agent_id,
            object_label=asset.agent_name or asset.name,
            before_status=None,
            after_status=asset.status.value,
            reason="通过 Agent 管理页注册新 Agent",
            details={"endpoint": asset.endpoint, "role_tag": asset.role_tag},
            operator_id=request.client.host if request.client else "unknown",
        )
        return asset
    except AgentBridgeError as exc:
        # Unreachable endpoint or protocol error — reject registration with 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Agent registration failed unexpectedly")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/handshake", response_model=AgentAsset)
async def trigger_handshake(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    await service.perform_handshake(agent_id)
    asset = service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Agent not found")
    return asset


@router.post("/agents/{agent_id}/safety-audit", response_model=AgentAsset)
async def evaluate_invocation_policy_legacy(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        await service.evaluate_local_invocation_policy(agent_id)
        asset = service.manager.get_asset(agent_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Agent not found")
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/invocation-policy", response_model=AgentAsset)
async def evaluate_agent_invocation_policy(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        await service.evaluate_local_invocation_policy(agent_id)
        asset = service.manager.get_asset(agent_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Agent not found")
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/activate", response_model=AgentAsset)
async def activate_agent(
    agent_id: str,
    request: Request,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    cli_service: Annotated[Any, Depends(get_cli_service)] = None,
    mcp_service: Annotated[Any, Depends(get_mcp_service)] = None,
) -> AgentAsset:
    try:
        before = service.manager.get_asset(agent_id)
        asset = await service.activate_agent(agent_id, cli_service=cli_service, mcp_service=mcp_service)
        record_module_management_log(
            request,
            source_module="agent",
            module_label="Agent",
            action="status_change",
            action_label="已启用",
            object_id=agent_id,
            object_label=asset.agent_name or asset.name,
            before_status=before.status.value if before else None,
            after_status=asset.status.value,
            reason="操作员启用 Agent，允许任务调度使用",
        )
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/disable", response_model=AgentAsset)
async def disable_agent(
    agent_id: str,
    request: Request,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        before = service.manager.get_asset(agent_id)
        asset = await service.disable_agent(agent_id)
        record_module_management_log(
            request,
            source_module="agent",
            module_label="Agent",
            action="status_change",
            action_label="已停用",
            object_id=agent_id,
            object_label=asset.agent_name or asset.name,
            before_status=before.status.value if before else None,
            after_status=asset.status.value,
            reason="操作员停用 Agent，后续任务不会再调度该 Agent",
        )
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/dispatch")
async def dispatch_agent_task(
    agent_id: str,
    payload: AgentDispatchTaskRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[Any, Depends(get_task_service)],
    cli_service: Annotated[Any, Depends(get_cli_service)] = None,
    mcp_service: Annotated[Any, Depends(get_mcp_service)] = None,
) -> Dict[str, Any]:
    try:
        response = await service.dispatch_task(
            agent_id,
            payload.task_payload,
            payload.verification_plan,
            zentex_task_id=payload.zentex_task_id,
            idempotency_key=payload.idempotency_key,
            cli_service=cli_service,
            mcp_service=mcp_service,
        )
        task_exists = (
            bool(payload.zentex_task_id)
            and callable(getattr(task_service, "get_task", None))
            and task_service.get_task(payload.zentex_task_id) is not None
        )
        if not response.is_error and payload.zentex_task_id and task_exists:
            from zentex.tasks.execution.external_result_bridge import mark_external_execution_started

            data = response.data if isinstance(response.data, dict) else {}
            await mark_external_execution_started(
                task_service=task_service,
                task_id=payload.zentex_task_id,
                trace_id=str(response.trace_id or data.get("trace_id") or ""),
                executor_type="agent",
                executor_metadata={
                    "agent_id": agent_id,
                    "external_task_ref": data.get("external_task_ref"),
                    "callback_url": data.get("callback_url"),
                    "callback_status": data.get("status"),
                },
            )
            _record_agent_workflow_event(
                event_type="external_invoked",
                status="running",
                task_service=task_service,
                task_id=payload.zentex_task_id,
                fallback_trace_id=str(response.trace_id or data.get("trace_id") or ""),
                input_summary={"agent_id": agent_id, "idempotency_key": payload.idempotency_key},
                output_summary={
                    "external_task_ref": data.get("external_task_ref"),
                    "callback_url": data.get("callback_url"),
                    "callback_status": data.get("status"),
                },
                evidence_ref=f"agent_invocation:{data.get('external_task_ref') or ''}",
                details={"agent_id": agent_id},
            )
            _record_agent_workflow_event(
                event_type="dispatch_started",
                status="running",
                task_service=task_service,
                task_id=payload.zentex_task_id,
                fallback_trace_id=str(response.trace_id or data.get("trace_id") or ""),
                input_summary={"agent_id": agent_id, "idempotency_key": payload.idempotency_key},
                output_summary={
                    "external_task_ref": data.get("external_task_ref"),
                    "callback_url": data.get("callback_url"),
                    "ledger_status": data.get("status"),
                },
                evidence_ref=f"agent_invocation:{data.get('external_task_ref') or ''}",
                details={"agent_id": agent_id},
            )
        return asdict(response)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/credentials")
def upsert_agent_credential(
    agent_id: str,
    payload: AgentCredentialUpsertRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    try:
        record = service.store_integration_credential(
            "agent",
            agent_id,
            credential_type=payload.credential_type,
            secret_payload=payload.secret_payload,
            credential_id=payload.credential_id,
            metadata=payload.metadata,
        )
        return record.model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        code = getattr(exc, "code", "")
        if str(code) == "DEPENDENCY_UNAVAILABLE" or getattr(code, "value", "") == "DEPENDENCY_UNAVAILABLE":
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if str(code) == "INVALID_ARGUMENT" or getattr(code, "value", "") == "INVALID_ARGUMENT":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/credentials")
def list_agent_credentials(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> List[Dict[str, Any]]:
    try:
        return [item.model_dump(mode="json") for item in service.list_integration_credentials("agent", agent_id)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}/credentials/{credential_id}")
def delete_agent_credential(
    agent_id: str,
    credential_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, bool]:
    try:
        deleted = service.delete_integration_credential("agent", agent_id, credential_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"success": True}


@router.post("/agents/{agent_id}/auth/test")
async def test_agent_auth(
    agent_id: str,
    payload: AgentAuthTestRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    response = await service.test_agent_auth(agent_id, force_refresh=payload.force_refresh)
    if response.is_error:
        if response.code == "PERMISSION_DENIED":
            raise HTTPException(status_code=403, detail=response.message)
        if response.code == "DEPENDENCY_UNAVAILABLE":
            raise HTTPException(status_code=503, detail=response.message)
        raise HTTPException(status_code=400, detail=response.message)
    return asdict(response)


@router.post("/integrations/{owner_type}/{owner_id}/credentials")
def upsert_integration_credential(
    owner_type: str,
    owner_id: str,
    payload: AgentCredentialUpsertRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    try:
        record = service.store_integration_credential(
            owner_type,
            owner_id,
            credential_type=payload.credential_type,
            secret_payload=payload.secret_payload,
            credential_id=payload.credential_id,
            metadata=payload.metadata,
        )
        return record.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        code = getattr(exc, "code", "")
        if str(code) == "DEPENDENCY_UNAVAILABLE" or getattr(code, "value", "") == "DEPENDENCY_UNAVAILABLE":
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if str(code) == "INVALID_ARGUMENT" or getattr(code, "value", "") == "INVALID_ARGUMENT":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/integrations/{owner_type}/{owner_id}/credentials")
def list_integration_credentials(
    owner_type: str,
    owner_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> List[Dict[str, Any]]:
    try:
        return [item.model_dump(mode="json") for item in service.list_integration_credentials(owner_type, owner_id)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/integrations/{owner_type}/{owner_id}/credentials/{credential_id}")
def delete_integration_credential(
    owner_type: str,
    owner_id: str,
    credential_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, bool]:
    try:
        deleted = service.delete_integration_credential(owner_type, owner_id, credential_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"success": True}


@router.post("/integrations/{owner_type}/{owner_id}/auth/test")
async def test_integration_auth(
    owner_type: str,
    owner_id: str,
    payload: AgentAuthTestRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    response = await service.test_integration_auth(
        owner_type,
        owner_id,
        auth_config=payload.auth_config,
        endpoint=payload.endpoint or "",
        force_refresh=payload.force_refresh,
    )
    if response.is_error:
        if response.code == "PERMISSION_DENIED":
            raise HTTPException(status_code=403, detail=response.message)
        if response.code == "DEPENDENCY_UNAVAILABLE":
            raise HTTPException(status_code=503, detail=response.message)
        raise HTTPException(status_code=400, detail=response.message)
    return asdict(response)


@router.post("/agents/callbacks/{external_task_ref}")
async def receive_agent_callback(
    external_task_ref: str,
    payload: AgentCallbackResultRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = payload.callback_token or _bearer_token(authorization)
    if payload.external_task_ref and payload.external_task_ref != external_task_ref:
        raise HTTPException(status_code=400, detail="Callback payload external_task_ref does not match URL")
    prior_record = service.get_invocation_by_external_task_ref(external_task_ref)
    prior_task_id = str(getattr(prior_record, "zentex_task_id", "") or "")
    if not token:
        _record_agent_workflow_event(
            event_type="executor_invocation_finished",
            status="failed",
            task_service=task_service,
            task_id=prior_task_id,
            fallback_trace_id=str(payload.trace_id or getattr(prior_record, "trace_id", "") or ""),
            input_summary={"external_task_ref": external_task_ref, "callback_status": payload.status},
            output_summary={"error": "Missing callback token"},
            evidence_ref=f"agent_callback:{external_task_ref}",
            error_code="MISSING_CALLBACK_TOKEN",
        )
        raise HTTPException(status_code=401, detail="Missing callback token")
    prior_status = str(getattr(prior_record, "status", "") or "")
    response = await service.receive_callback_result(
        external_task_ref,
        callback_token=token,
        status=payload.status,
        trace_id=payload.trace_id,
        normalized_result=payload.normalized_result,
        raw_response=payload.raw_response,
    )
    if response.is_error:
        _record_agent_workflow_event(
            event_type="executor_invocation_finished",
            status="failed",
            task_service=task_service,
            task_id=prior_task_id,
            fallback_trace_id=str(payload.trace_id or getattr(prior_record, "trace_id", "") or ""),
            input_summary={"external_task_ref": external_task_ref, "callback_status": payload.status},
            output_summary={"error": response.message},
            evidence_ref=f"agent_callback:{external_task_ref}",
            error_code=str(response.code or "AGENT_CALLBACK_REJECTED"),
        )
        status_code = 403 if response.code == "PERMISSION_DENIED" else 400
        raise HTTPException(status_code=status_code, detail=response.message)
    record = response.data if isinstance(response.data, dict) else {}
    task_id = str(record.get("zentex_task_id") or "").strip()
    callback_status = str(record.get("status") or payload.status or "").strip()
    task_exists = bool(task_id) and callable(getattr(task_service, "get_task", None)) and task_service.get_task(task_id) is not None
    if task_id and task_exists:
        task = task_service.get_task(task_id)
        task_status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "")
        if (
            prior_status == "completed"
            and callback_status == "completed"
            and task_status == TaskStatus.DONE.value
            and callable(getattr(task_service, "get_task_outcome", None))
            and task_service.get_task_outcome(task_id) is not None
        ):
            return asdict(response)
        if callback_status == "completed":
            from zentex.tasks.execution.external_result_bridge import write_external_execution_result

            await write_external_execution_result(
                task_service=task_service,
                task_id=task_id,
                trace_id=str(response.trace_id or record.get("trace_id") or ""),
                executor_type="agent",
                executor_metadata={
                    "agent_id": record.get("agent_id"),
                    "external_task_ref": external_task_ref,
                    "callback_url": record.get("callback_url"),
                    "callback_status": callback_status,
                },
                result_payload={
                    "status": "completed",
                    "callback_status": callback_status,
                    "external_task_ref": external_task_ref,
                    "trace_id": record.get("trace_id"),
                    "normalized_result": payload.normalized_result,
                    "raw_response": payload.raw_response,
                },
                succeeded=True,
            )
            _record_agent_workflow_event(
                event_type="node_succeeded",
                status="succeeded",
                task_service=task_service,
                task_id=task_id,
                fallback_trace_id=str(response.trace_id or record.get("trace_id") or ""),
                input_summary={"external_task_ref": external_task_ref, "callback_status": callback_status},
                output_summary={
                    "normalized_result": payload.normalized_result,
                    "raw_response": payload.raw_response,
                    "task_outcome_recorded": True,
                },
                evidence_ref=f"agent_callback:{external_task_ref}",
                details={"agent_id": record.get("agent_id"), "callback_url": record.get("callback_url")},
            )
            for event_type in ("executor_invocation_finished", "task_outcome_recorded", "verification_finished"):
                _record_agent_workflow_event(
                    event_type=event_type,
                    status="succeeded",
                    task_service=task_service,
                    task_id=task_id,
                    fallback_trace_id=str(response.trace_id or record.get("trace_id") or ""),
                    input_summary={"external_task_ref": external_task_ref, "callback_status": callback_status},
                    output_summary={
                        "normalized_result": payload.normalized_result,
                        "raw_response": payload.raw_response,
                        "task_outcome_recorded": True,
                    },
                    evidence_ref=f"agent_callback:{external_task_ref}",
                    details={"agent_id": record.get("agent_id"), "callback_url": record.get("callback_url")},
                )
        elif callback_status in {"failed", "uncertain"}:
            await task_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                remarks=f"agent callback returned {callback_status}",
            )
            _record_agent_workflow_event(
                event_type="node_failed",
                status="failed",
                task_service=task_service,
                task_id=task_id,
                fallback_trace_id=str(response.trace_id or record.get("trace_id") or ""),
                input_summary={"external_task_ref": external_task_ref, "callback_status": callback_status},
                output_summary={"normalized_result": payload.normalized_result, "raw_response": payload.raw_response},
                evidence_ref=f"agent_callback:{external_task_ref}",
                error_code="AGENT_CALLBACK_NOT_COMPLETED",
                details={"agent_id": record.get("agent_id"), "callback_url": record.get("callback_url")},
            )
            _record_agent_workflow_event(
                event_type="executor_invocation_finished",
                status="failed",
                task_service=task_service,
                task_id=task_id,
                fallback_trace_id=str(response.trace_id or record.get("trace_id") or ""),
                input_summary={"external_task_ref": external_task_ref, "callback_status": callback_status},
                output_summary={"normalized_result": payload.normalized_result, "raw_response": payload.raw_response},
                evidence_ref=f"agent_callback:{external_task_ref}",
                error_code="AGENT_CALLBACK_NOT_COMPLETED",
                details={"agent_id": record.get("agent_id"), "callback_url": record.get("callback_url")},
            )
    return asdict(response)


@router.get("/agents/invocations/{external_task_ref}")
def get_agent_invocation(
    external_task_ref: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    record = service.get_invocation_by_external_task_ref(external_task_ref)
    if record is None:
        raise HTTPException(status_code=404, detail="Invocation not found")
    return record.model_dump(mode="json")


@router.get("/agents/{agent_id}/invocations")
def list_agent_invocations(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    limit: int = Query(100, ge=1, le=500),
) -> List[Dict[str, Any]]:
    return [item.model_dump(mode="json") for item in service.list_invocations_for_agent(agent_id, limit=limit)]


@router.get("/agents/tasks/{zentex_task_id}/invocations")
def list_task_agent_invocations(
    zentex_task_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    limit: int = Query(100, ge=1, le=500),
) -> List[Dict[str, Any]]:
    return [item.model_dump(mode="json") for item in service.list_invocations_for_task(zentex_task_id, limit=limit)]


@router.delete("/agents/{agent_id}")
async def unregister_agent(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    request: Request,
) -> Dict[str, bool]:
    before = service.manager.get_asset(agent_id)
    success = await service.unregister_agent(
        agent_id,
        operator_id=request.client.host if request.client else "unknown",
    )
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    record_module_management_log(
        request,
        source_module="agent",
        module_label="Agent",
        action="delete",
        action_label="已删除",
        object_id=agent_id,
        object_label=(before.agent_name or before.name) if before else agent_id,
        before_status=before.status.value if before else None,
        after_status="deleted",
        reason="操作员删除 Agent 注册记录",
        operator_id=request.client.host if request.client else "unknown",
    )
    return {"success": True}


@router.get("/agents-health/status")
async def monitor_agents_health(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> List[AgentAsset]:
    return await service.monitor_health()


@router.patch("/agents/{agent_id}/policy", response_model=AgentAsset)
async def update_agent_policy(
    agent_id: str,
    payload: AgentPolicyUpdateRequest,
    request: Request,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        before = service.manager.get_asset(agent_id)
        asset = await service.update_policy(
            agent_id,
            trust_level=payload.trust_level,
            scope=payload.scope,
        )
        record_module_management_log(
            request,
            source_module="agent",
            module_label="Agent",
            action="update",
            action_label="策略已修改",
            object_id=agent_id,
            object_label=asset.agent_name or asset.name,
            before_status=before.trust_level.value if before else None,
            after_status=asset.trust_level.value,
            reason="操作员修改 Agent 信任等级或权限范围",
            details={"scope": payload.scope, "trust_level": payload.trust_level},
        )
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/tasks", response_model=List[ZentexTask])
def list_agent_tasks(
    agent_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[ZentexTask]:
    return service.list_tasks(target_id=agent_id)


@router.get("/agents/{agent_id}/audit", response_model=List[AgentAuditRecord])
def list_agent_audit_events(
    agent_id: str,
    request: Request,
) -> List[AgentAuditRecord]:
    """获取所有智能体的审计日志"""
    audit_service = getattr(request.app.state, "audit_service", None)
    return handle_get_agent_audit_events(agent_id, audit_service)


@router.get("/agents/{agent_id}/detail")
def get_agent_detail(
    agent_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """获取智能体详细详情（含信用分、统计信息、收发件箱）"""
    return handle_get_agent_detail(agent_id, agent_service, task_service)


@router.get("/agents/{agent_id}/tasks/by-status")
def get_agent_tasks_view(
    agent_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
    status: str = Query(..., description="状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("started_at"),
    order: str = Query("desc"),
    search: str = Query(""),
    task_type: str = Query(""),
    originator: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
) -> Dict[str, Any]:
    """带分页和过滤的智能体任务视图"""
    return handle_get_tasks_by_status(
        agent_id=agent_id,
        status_filter=status,
        agent_service=agent_service,
        task_service=task_service,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
        search=search,
        task_type=task_type,
        originator=originator,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/agents/{agent_id}/tasks/{task_id}/cancel")
def cancel_agent_task(
    agent_id: str,
    task_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    return handle_cancel_agent_task(agent_id, task_id, agent_service, task_service)


@router.post("/agents/{agent_id}/tasks/{task_id}/retry")
def retry_agent_task(
    agent_id: str,
    task_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    return handle_retry_agent_task(agent_id, task_id, agent_service, task_service)
