from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from plugins.nine_questions.q3_what_do_i_have.modules import build_q3_runtime_inventory_context
from plugins.nine_questions.q9_how_should_i_act.modules import (
    derive_posture_baseline,
    normalize_functional_postures,
    normalize_reasoning_budget,
    normalize_self_model,
)
from zentex.common.flow_audit import FlowAudit
from zentex.nine_questions.module_retry import (
    build_q9_question_snapshot,
    retry_q2_identity_input_module,
    retry_q3_runtime_inventory_module,
    retry_q4_capability_input_module,
    retry_q5_policy_module,
    retry_q6_redline_module,
    retry_q7_functional_module,
    retry_q9_posture_input_module,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals
from zentex.nine_questions.plan_verification_data import (
    PlanVerificationDataError,
    generate_plan_verification_data,
)
from zentex.nine_questions.plan_evidence_registry import (
    PlanEvidenceRegistryError,
    register_plan_evidence_manifest,
)
from zentex.nine_questions.plan_execution_evidence import (
    PlanExecutionEvidenceError,
    register_plan_execution_evidence,
)
from zentex.web_console.contracts.nine_questions import NineQuestionsRunRequest, NineQuestionsRunResponse
from zentex.web_console.dependencies import get_learning_service, get_plugin_service, get_task_service

from .q_state import (
    _get_nine_question_service,
    get_nine_question_state,
    get_or_create_session,
    get_question_snapshot_map,
)
from .route_handlers_shared import (
    _nine_question_execution_guard,
    acquire_nine_question_execution_guard,
    inject_app_runtime_context,
    sync_q8_tasks,
)

router = APIRouter()
_build_q9_question_snapshot = build_q9_question_snapshot

_DEFAULT_SINGLE_QUESTION_TIMEOUT_SECONDS = 90.0
_SINGLE_QUESTION_TIMEOUT_SECONDS_BY_ID = {
    # Q3 performs real runtime inventory plus LLM-backed resource sufficiency
    # inference. The clinical acceptance path regularly exceeds 300s on local
    # providers, so the web route must not keep the old generic 90s budget.
    "q3": 480.0,
}


def single_question_timeout_seconds(question_id: str) -> float:
    return _SINGLE_QUESTION_TIMEOUT_SECONDS_BY_ID.get(
        question_id,
        _DEFAULT_SINGLE_QUESTION_TIMEOUT_SECONDS,
    )


def _sync_app_runtime_services_to_kernel(request: Request, service: Any) -> None:
    """Keep web/API registered external capabilities visible to kernel Q runs."""
    app_state = getattr(request.app, "state", None)
    facade = getattr(service, "_facade", None)
    get_kernel = getattr(facade, "_get_kernel_service", None)
    kernel = get_kernel() if callable(get_kernel) else None
    attach = getattr(kernel, "attach_dependencies", None)
    if app_state is None or not callable(attach):
        return
    attach(
        plugins_service=getattr(app_state, "plugin_service", None),
        foundation_service=getattr(app_state, "foundation_service", None),
        agent_service=getattr(app_state, "agent_service", None)
        or getattr(app_state, "agent_coordination_service", None),
        cli_service=getattr(app_state, "cli_service", None),
        mcp_service=getattr(app_state, "mcp_service", None),
        external_connector_service=getattr(app_state, "external_connector_service", None),
        memory_service=getattr(app_state, "memory_service", None),
        audit_service=getattr(app_state, "audit_service", None),
        reflection_service=getattr(app_state, "reflection_service", None),
        learning_service=getattr(app_state, "learning_service", None),
        task_service=getattr(app_state, "task_service", None),
    )


async def _retry_q2_identity_input_module(request: Request, module_id: str) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q2")
    functional_context = inject_app_runtime_context(request, dependency_context)
    return await retry_q2_identity_input_module(
        service=service,
        snapshot_map=snapshot_map,
        module_id=module_id,
        dependency_context=functional_context,
        plugin_service=get_plugin_service(request),
        functional_executor=execute_enabled_cognitive_plugin_functionals,
    )


async def _retry_q3_runtime_inventory_module(request: Request, module_id: str) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q3")
    runtime_context = inject_app_runtime_context(request, dependency_context)
    return await retry_q3_runtime_inventory_module(
        service=service,
        snapshot_map=snapshot_map,
        module_id=module_id,
        dependency_context=runtime_context,
        build_runtime_inventory_context_fn=build_q3_runtime_inventory_context,
    )


async def _retry_q4_capability_input_module(request: Request, module_id: str) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q4")
    functional_context = inject_app_runtime_context(
        request,
        {**dependency_context, "session_id": "nq-baseline"},
    )
    return await retry_q4_capability_input_module(
        service=service,
        snapshot_map=snapshot_map,
        module_id=module_id,
        functional_context=functional_context,
        plugin_service=get_plugin_service(request),
        functional_executor=execute_enabled_cognitive_plugin_functionals,
    )


async def _retry_q5_policy_module(request: Request, *, module_id: str) -> str:
    service = _get_nine_question_service(request)
    snapshot = await service.get_question_snapshot("q5")
    return await retry_q5_policy_module(service=service, snapshot=snapshot, module_id=module_id)


async def _retry_q6_redline_module(request: Request) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q6")
    functional_context = dict(dependency_context)
    return await retry_q6_redline_module(
        service=service,
        snapshot_map=snapshot_map,
        functional_context=functional_context,
        plugin_service=get_plugin_service(request),
        functional_executor=execute_enabled_cognitive_plugin_functionals,
    )


async def _retry_q7_functional_module(request: Request) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q7")
    functional_context = dict(dependency_context)
    return await retry_q7_functional_module(
        service=service,
        snapshot_map=snapshot_map,
        functional_context=functional_context,
        plugin_service=get_plugin_service(request),
        functional_executor=execute_enabled_cognitive_plugin_functionals,
    )


async def _retry_q9_posture_input_module(request: Request, module_id: str) -> str:
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    dependency_context = await service.get_flat_dependency_context(upto_question_id="q9")
    functional_context = inject_app_runtime_context(
        request,
        {**dependency_context, "session_id": "nq-baseline"},
    )
    return await retry_q9_posture_input_module(
        service=service,
        snapshot_map=snapshot_map,
        module_id=module_id,
        dependency_context=dependency_context,
        functional_context=functional_context,
        plugin_service=get_plugin_service(request),
        functional_executor=execute_enabled_cognitive_plugin_functionals,
        normalize_self_model_fn=normalize_self_model,
        normalize_reasoning_budget_fn=normalize_reasoning_budget,
        normalize_functional_postures_fn=normalize_functional_postures,
        derive_posture_baseline_fn=derive_posture_baseline,
    )


async def _retry_single_nine_question_module(
    request: Request,
    session_id: str,
    question_id: str,
    module_id: str,
) -> str:
    state = await get_nine_question_state(request)
    snapshot_map = get_question_snapshot_map(state)

    if question_id == "q2" and module_id in {"q2_q1_dependency_validation", "q2_identity_kernel_validation", "q2_functional_identity_chain"}:
        return await _retry_q2_identity_input_module(request, module_id)
    if question_id == "q3" and module_id in {"q3_runtime_inventory", "workspace_permission_inventory", "cognitive_tools_inventory", "execution_tools_inventory", "connected_agents_inventory", "mcp_inventory", "cli_inventory", "external_connectors_inventory", "memory_strategy_inventory"}:
        return await _retry_q3_runtime_inventory_module(request, module_id)
    if question_id == "q4" and module_id in {"q4_inventory_validation", "q4_permission_validation", "q4_execution_capability_verification"}:
        return await _retry_q4_capability_input_module(request, module_id)
    if question_id == "q5" and module_id in {"q5_contact_policy_validation", "q5_tenant_scope_validation", "q5_agent_trust_validation"}:
        return await _retry_q5_policy_module(request, module_id=module_id)
    if question_id == "q6" and module_id == "q6_redline_hint_chain":
        return await _retry_q6_redline_module(request)
    if question_id == "q7" and module_id == "q7_functional_alternative_chain":
        return await _retry_q7_functional_module(request)
    if question_id == "q8" and module_id == "q8_task_persistence":
        if "q8" not in snapshot_map:
            raise HTTPException(status_code=404, detail="Q8 snapshot missing; cannot retry q8_task_persistence")
        await sync_q8_tasks(request, session_id, snapshot_map)
        return "single_nine_question_module_retried:q8:q8_task_persistence"
    if question_id == "q9" and module_id in {"q9_q1_q8_validation", "q9_self_model_source_validation", "q9_reasoning_budget_source_validation", "q9_functional_posture_chain"}:
        return await _retry_q9_posture_input_module(request, module_id)

    raise HTTPException(
        status_code=400,
        detail=(
            f"Module retry executor not implemented for {question_id}.{module_id}. "
            "This project is not web-driven; unsupported module buttons must not be exposed by the monitoring UI."
        ),
    )


@router.post("/nine-questions/{question_id}/run")
async def run_single_nine_question(
    request: Request,
    question_id: str,
    run_request: NineQuestionsRunRequest,
) -> NineQuestionsRunResponse:
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    acquire_nine_question_execution_guard()
    try:
        session = await get_or_create_session(request)
        service = _get_nine_question_service(request)
        _sync_app_runtime_services_to_kernel(request, service)
        audit_service = getattr(request.app.state, "audit_service", None)
        rerun_audit = FlowAudit.new("nine_questions", source_module=__name__)
        if audit_service:
            audit_service.record_flow_start(rerun_audit)
        try:
            timeout_seconds = single_question_timeout_seconds(question_id)
            await service.run_single(question_id, timeout_seconds=timeout_seconds, audit=rerun_audit)
        except asyncio.TimeoutError:
            if audit_service:
                audit_service.record_flow_end(rerun_audit, status="failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "single_nine_question_timeout",
                    "question_id": question_id,
                    "timeout_seconds": timeout_seconds,
                    "message": f"{question_id.upper()} 重跑超时（{int(timeout_seconds)}s），请稍后重试。",
                },
            )
        except ValueError as exc:
            if audit_service:
                audit_service.record_flow_end(rerun_audit, status="failed")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            if audit_service:
                audit_service.record_flow_end(rerun_audit, status="failed")
            raise
        if audit_service:
            audit_service.record_flow_end(rerun_audit, status="completed")
        state = await get_nine_question_state(request)
        snapshot_map = get_question_snapshot_map(state)
        await sync_q8_tasks(request, session.session_id, snapshot_map)
        return NineQuestionsRunResponse(
            started=question_id in snapshot_map,
            trace_id=str(session.session_id),
            refresh_reason=f"single_nine_question_reexecuted:{question_id}",
            snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
            revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        )
    finally:
        if _nine_question_execution_guard.locked():
            _nine_question_execution_guard.release()


@router.post("/nine-questions/{question_id}/rollback")
async def rollback_single_nine_question(request: Request, question_id: str) -> NineQuestionsRunResponse:
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    session = await get_or_create_session(request)
    service = _get_nine_question_service(request)
    try:
        await service.rollback_question(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state = await get_nine_question_state(request)
    snapshot_map = get_question_snapshot_map(state)
    await sync_q8_tasks(request, session.session_id, snapshot_map)
    return NineQuestionsRunResponse(
        started=question_id in snapshot_map,
        trace_id=str(session.session_id),
        refresh_reason=f"single_nine_question_rolled_back:{question_id}",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )


@router.post("/nine-questions/q8/recover-task-persistence")
async def recover_q8_task_persistence(request: Request) -> NineQuestionsRunResponse:
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request)
    snapshot_map = get_question_snapshot_map(state)
    if "q8" not in snapshot_map:
        raise HTTPException(status_code=404, detail="Q8 snapshot missing; cannot recover task persistence")
    await sync_q8_tasks(request, session.session_id, snapshot_map)
    return NineQuestionsRunResponse(
        started=True,
        trace_id=str(session.session_id),
        refresh_reason="q8_task_persistence_recovered",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )


@router.post("/nine-questions/plan/verification-data")
async def generate_plan_verification_data_endpoint(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    sample_count: int = Query(default=100, ge=1, le=200),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return await generate_plan_verification_data(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            sample_count=sample_count,
        )
    except PlanVerificationDataError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_verification_data_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.post("/nine-questions/plan/evidence-manifests")
async def register_plan_evidence_manifest_endpoint(
    request: Request,
    manifest: dict[str, Any],
):
    await get_or_create_session(request)
    try:
        return register_plan_evidence_manifest(
            learning_service=get_learning_service(request),
            manifest=manifest,
        )
    except PlanEvidenceRegistryError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_evidence_manifest_failed",
                "failures": exc.failures,
            },
        ) from exc


@router.post("/nine-questions/plan/execution-evidence")
async def register_plan_execution_evidence_endpoint(
    request: Request,
    evidence: dict[str, Any],
):
    await get_or_create_session(request)
    try:
        return register_plan_execution_evidence(
            learning_service=get_learning_service(request),
            evidence=evidence,
        )
    except PlanExecutionEvidenceError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_execution_evidence_failed",
                "failures": exc.failures,
            },
        ) from exc


@router.post("/nine-questions/{question_id}/modules/{module_id}/rollback")
async def rollback_single_nine_question_module(
    request: Request,
    question_id: str,
    module_id: str,
) -> NineQuestionsRunResponse:
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    session = await get_or_create_session(request)
    service = _get_nine_question_service(request)
    try:
        await service.rollback_question_module(question_id, module_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RuntimeError as exc:
        if "file-backed side storage is no longer allowed" in str(exc):
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state = await get_nine_question_state(request)
    snapshot_map = get_question_snapshot_map(state)
    if question_id == "q8" and module_id == "q8_task_persistence":
        await sync_q8_tasks(request, session.session_id, snapshot_map)
    return NineQuestionsRunResponse(
        started=True,
        trace_id=str(session.session_id),
        refresh_reason=f"single_nine_question_module_rolled_back:{question_id}:{module_id}",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )


@router.post("/nine-questions/{question_id}/modules/{module_id}/retry")
async def retry_single_nine_question_module(
    request: Request,
    question_id: str,
    module_id: str,
) -> NineQuestionsRunResponse:
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    session = await get_or_create_session(request)
    refresh_reason = await _retry_single_nine_question_module(
        request=request,
        session_id=session.session_id,
        question_id=question_id,
        module_id=module_id,
    )
    state = await get_nine_question_state(request)
    snapshot_map = get_question_snapshot_map(state)
    return NineQuestionsRunResponse(
        started=True,
        trace_id=str(session.session_id),
        refresh_reason=refresh_reason,
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )


@router.post("/nine-questions/run-all")
async def run_all_nine_questions(
    request: Request,
    run_request: NineQuestionsRunRequest,
) -> NineQuestionsRunResponse:
    acquire_nine_question_execution_guard()
    try:
        session = await get_or_create_session(request)
        service = _get_nine_question_service(request)
        audit_service = getattr(request.app.state, "audit_service", None)
        audit = FlowAudit.new("nine_questions", source_module=__name__)
        if audit_service:
            audit_service.record_flow_start(audit)
        try:
            # Use NineQuestionService.execute_all() so that:
            #   - persist_kernel_state() runs in a finally block (P1-Fix-A)
            #   - the merge-write strategy protects existing successful records (P3-Fix-A)
            #   - all state management is centralised in the service layer
            await service.execute_all(
                force=bool(run_request.force_refresh),
                audit=audit,
            )
        except ValueError as exc:
            if audit_service:
                audit_service.record_flow_end(audit, status="failed")
            raise HTTPException(
                status_code=503,
                detail=f"Kernel session unavailable for nine-question bootstrap: {exc}",
            ) from exc
        except asyncio.TimeoutError:
            if audit_service:
                audit_service.record_flow_end(audit, status="failed")
            raise HTTPException(
                status_code=503,
                detail={"error": "nine_question_bootstrap_timeout", "message": "全量9问执行超时，已保存部分进度。"},
            )
        except Exception:
            if audit_service:
                audit_service.record_flow_end(audit, status="failed")
            raise
        if audit_service:
            audit_service.record_flow_end(audit, status="completed")
        state = await get_nine_question_state(request)
        snapshot_map = get_question_snapshot_map(state)
        await sync_q8_tasks(request, session.session_id, snapshot_map)
        return NineQuestionsRunResponse(
            started=bool(snapshot_map),
            trace_id=str(session.session_id),
            refresh_reason="all_nine_questions_executed_forced" if run_request.force_refresh else "all_nine_questions_executed",
            snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
            revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        )
    finally:
        if _nine_question_execution_guard.locked():
            _nine_question_execution_guard.release()
