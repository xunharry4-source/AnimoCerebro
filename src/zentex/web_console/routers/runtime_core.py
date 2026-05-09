from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from zentex.web_console.dependencies import get_kernel_service_facade


router = APIRouter()


class BrainDaemonControlRequest(BaseModel):
    action: str = Field(pattern="^(start|tick|pause|resume|stop)$")
    session_id: str | None = None
    interval_seconds: float | None = Field(default=None, gt=0)
    max_consecutive_failures: int | None = Field(default=None, gt=0)
    run_background: bool = False


class EnvironmentAwarenessRequest(BaseModel):
    session_id: str
    turn_id: str | None = None
    raw_signals: list[str] = Field(default_factory=list)
    source_conflict_field: str = "memory_used_ratio"
    source_conflict_samples: dict[str, Any] = Field(default_factory=dict)


class ResourceNegotiationCreateRequest(BaseModel):
    session_id: str
    task_id: str
    gap_type: str = Field(pattern="^(permission|compute_resource|human_verification|resource_unavailable)$")
    required_asset: str
    observed_error: str
    recovery_conditions: list[str] = Field(min_length=1)
    task_context: dict[str, Any] = Field(default_factory=dict)
    proposed_tradeoff: str | None = None
    priority: int = Field(default=3, ge=1, le=5)


class ResourceNegotiationResolveRequest(BaseModel):
    session_id: str
    negotiation_id: str
    approved: bool
    resolution_note: str
    granted_asset: str | None = None


class IdentityKernelMountRequest(BaseModel):
    session_id: str
    topics: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    identity_package: dict[str, Any] | None = None


class IdentityChangeEvaluationRequest(BaseModel):
    session_id: str
    proposed_changes: dict[str, Any] = Field(min_length=1)
    human_confirmed: bool = False
    reviewer: str | None = None
    drift_threshold: float = Field(default=0.34, gt=0, le=1)


class InterAgentConflictCreateRequest(BaseModel):
    session_id: str
    task_id: str
    task_payload: dict[str, Any] = Field(min_length=1)
    required_capabilities: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(default=5.0, gt=0)


class InterAgentConflictReassignRequest(BaseModel):
    session_id: str
    task_id: str
    failed_agent_id: str
    failure_reason: str


class SafetyGateActionRequest(BaseModel):
    session_id: str
    action_type: str
    action_payload: dict[str, Any] = Field(min_length=1)
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    context: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = Field(default="real", pattern="^(real|dry_run|simulate)$")
    cloud_audit_config: dict[str, Any] | None = None


class SafetyGateConfirmRequest(BaseModel):
    session_id: str
    confirmed_by: str
    confirmation_context: dict[str, Any] = Field(default_factory=dict)


class ThoughtSandboxSimulationRequest(BaseModel):
    session_id: str
    action_type: str
    action_payload: dict[str, Any] = Field(min_length=1)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    task_type: str = "general"
    domain: str = "general"
    branches: list[dict[str, Any]] = Field(default_factory=list)
    catastrophe_threshold: float = Field(default=0.7, gt=0, le=1)
    context: dict[str, Any] = Field(default_factory=dict)


class SensorySignalRequest(BaseModel):
    session_id: str
    source: str
    payload: str
    domain: str = "environment"
    source_observations: list[dict[str, Any]] = Field(default_factory=list)


class WorkingMemoryUpdateRequest(BaseModel):
    session_id: str
    tick_id: str
    new_candidates: list[dict[str, Any]] = Field(min_length=1)
    attention_budget: dict[str, Any] | None = None
    trace_id: str | None = None


class WorkingMemoryInterruptRequest(BaseModel):
    session_id: str
    tick_id: str
    high_risk_item: dict[str, Any] = Field(min_length=1)
    trace_id: str | None = None


class WorkingMemoryResumeRequest(BaseModel):
    session_id: str
    tick_id: str
    focus_id: str
    trace_id: str | None = None


class WorkingMemoryConsideredRequest(BaseModel):
    session_id: str
    tick_id: str | None = None
    ref_id: str
    trace_id: str | None = None


class LivingSelfModelUpdateRequest(BaseModel):
    session_id: str
    turn_result: dict[str, Any] = Field(min_length=1)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    working_memory_frame: dict[str, Any] | None = None
    trace_id: str | None = None


class LivingSelfWeaknessRequest(BaseModel):
    session_id: str
    recent_events: list[dict[str, Any]] = Field(min_length=1)
    trace_id: str | None = None


class LivingSelfConfidenceDriftRequest(BaseModel):
    session_id: str
    statements: list[dict[str, Any]] = Field(min_length=1)
    evidence: Any | None = None
    threshold: float = Field(default=0.25, gt=0, le=1)
    trace_id: str | None = None


class LivingSelfLoadAdjustmentRequest(BaseModel):
    session_id: str
    working_memory_frame: dict[str, Any] = Field(min_length=1)
    trace_id: str | None = None


class MetaCognitionDecisionRequest(BaseModel):
    session_id: str
    wm_frame: dict[str, Any] = Field(min_length=1)
    self_model: dict[str, Any] = Field(min_length=1)
    budget: dict[str, Any] = Field(min_length=1)
    nine_q_state: dict[str, Any] = Field(min_length=1)
    agenda: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    tool_registry: list[dict[str, Any]] | dict[str, Any] = Field(min_length=1)
    trace_id: str | None = None


class TemporalAgendaTickRequest(BaseModel):
    session_id: str
    current_time: str
    agenda_items: list[dict[str, Any]] = Field(min_length=1)
    brain_scope: str | None = None
    trace_id: str | None = None


class CognitiveConflictDetectRequest(BaseModel):
    session_id: str
    working_memory: dict[str, Any] = Field(min_length=1)
    goals: list[dict[str, Any]] = Field(default_factory=list)
    nine_q_state: dict[str, Any] = Field(default_factory=dict)
    memory_recalls: list[dict[str, Any]] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    self_model: dict[str, Any] = Field(default_factory=dict)
    agenda: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None


class ExperienceExpectationRequest(BaseModel):
    session_id: str
    task_id: str
    expected_outcome: dict[str, Any] = Field(min_length=1)
    success_criteria: list[str] = Field(min_length=1)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    source: str = "runtime"


class ExperienceOutcomeBindingRequest(BaseModel):
    session_id: str
    expectation_id: str
    actual_outcome: dict[str, Any]
    benefits: list[str] = Field(default_factory=list)
    losses: list[str] = Field(default_factory=list)
    source_reliability: float = Field(default=0.8, ge=0, le=1)
    strategy_patch: dict[str, Any] = Field(default_factory=dict)


class ExperienceGoalRankingRequest(BaseModel):
    session_id: str
    candidate_goals: list[dict[str, Any]] = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class DynamicToolLearningRequest(BaseModel):
    session_id: str
    documentation_url: str
    source_kind: str = Field(pattern="^(real_document|static_catalog_sample)$")
    capability_name: str | None = None
    verification_endpoint: str | None = None
    verification_cases: list[dict[str, Any]] = Field(default_factory=list)
    timeout_seconds: float = Field(default=3.0, gt=0)


class ValueEngineEvaluationRequest(BaseModel):
    session_id: str
    candidate_goals: list[dict[str, Any]] = Field(min_length=1)
    candidate_plans: list[dict[str, Any]] = Field(default_factory=list)
    resource_state: dict[str, Any] = Field(default_factory=dict)
    risk_state: dict[str, Any] = Field(default_factory=dict)
    role_state: dict[str, Any] = Field(default_factory=dict)
    self_state: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    requested_capabilities: list[str] = Field(default_factory=list)
    weight_profile: dict[str, Any] | None = None


class SelfRefactorProposalRequest(BaseModel):
    session_id: str
    workspace_root: str
    target_path: str
    bottleneck_evidence: dict[str, Any] = Field(min_length=1)
    change_summary: str
    replacement: dict[str, str]
    sandbox_commands: list[list[str]] = Field(min_length=1)
    capability_id: str
    resource_state: dict[str, Any] = Field(default_factory=dict)
    risk_state: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    self_mod_gate_inputs: dict[str, Any] = Field(default_factory=dict)


class SelfCodingCycleRequest(BaseModel):
    session_id: str
    workspace_root: str
    candidate_root: str
    capability_gap: dict[str, Any] = Field(min_length=1)
    patch_plan: dict[str, Any] = Field(min_length=1)
    verification_commands: list[list[str]] = Field(min_length=1)


class PreferenceJudgmentRequest(BaseModel):
    session_id: str
    detected_state: dict[str, Any] = Field(min_length=1)
    detection_source: str
    context: dict[str, Any] = Field(default_factory=dict)


class PreferenceConfirmRequest(BaseModel):
    session_id: str
    user_decision: str = Field(pattern="^(confirm_as_preference|mark_as_anomaly|needs_investigation)$")
    user_id: str
    confirmation_context: dict[str, Any] = Field(default_factory=dict)


class PreferenceRevokeRequest(BaseModel):
    session_id: str
    reason: str
    user_id: str


class ExtremeSignalRequest(BaseModel):
    session_id: str
    signal_content: str
    signal_source: str
    context: dict[str, Any] = Field(default_factory=dict)


class AttackSampleMarkRequest(BaseModel):
    session_id: str
    attack_type: str
    confidence: float = Field(ge=0, le=1)
    analyst_id: str | None = None


@router.get("/runtime/architecture")
def get_runtime_architecture(
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    return facade.get_core_architecture_snapshot()


@router.get("/runtime/daemon/status")
def get_brain_daemon_status(
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    return facade.get_brain_daemon_status()


@router.post("/runtime/daemon/control")
def control_brain_daemon(
    payload: BrainDaemonControlRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.control_brain_daemon(
            action=payload.action,
            session_id=payload.session_id,
            interval_seconds=payload.interval_seconds,
            max_consecutive_failures=payload.max_consecutive_failures,
            run_background=payload.run_background,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/resource-negotiations")
async def create_resource_negotiation_request(
    payload: ResourceNegotiationCreateRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.create_resource_negotiation_request(
            session_id=payload.session_id,
            task_id=payload.task_id,
            gap_type=payload.gap_type,
            required_asset=payload.required_asset,
            observed_error=payload.observed_error,
            recovery_conditions=payload.recovery_conditions,
            task_context=payload.task_context,
            proposed_tradeoff=payload.proposed_tradeoff,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/resource-negotiations")
def query_resource_negotiation_requests(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
    task_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    try:
        return facade.query_resource_negotiation_requests(
            session_id=session_id,
            task_id=task_id,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/resource-negotiations/resolve")
async def resolve_resource_negotiation_request(
    payload: ResourceNegotiationResolveRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.resolve_resource_negotiation_request(
            session_id=payload.session_id,
            negotiation_id=payload.negotiation_id,
            approved=payload.approved,
            resolution_note=payload.resolution_note,
            granted_asset=payload.granted_asset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/identity-kernel/mount")
def mount_identity_kernel(
    payload: IdentityKernelMountRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.mount_identity_kernel(
            session_id=payload.session_id,
            topics=payload.topics,
            risk_level=payload.risk_level,
            identity_package=payload.identity_package,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/identity-kernel/anchors")
def query_identity_anchors(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
    role: str | None = None,
    risk_level: str | None = None,
    topics: list[str] | None = Query(default=None),
    limit: int = Query(default=20, gt=0),
) -> dict[str, Any]:
    try:
        return facade.query_identity_anchors(
            session_id=session_id,
            role=role,
            risk_level=risk_level,
            topics=topics,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/identity-kernel/evaluate-change")
def evaluate_identity_change(
    payload: IdentityChangeEvaluationRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.evaluate_identity_change(
            session_id=payload.session_id,
            proposed_changes=payload.proposed_changes,
            human_confirmed=payload.human_confirmed,
            reviewer=payload.reviewer,
            drift_threshold=payload.drift_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/inter-agent/conflicts")
async def create_inter_agent_conflict(
    payload: InterAgentConflictCreateRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.create_inter_agent_conflict(
            session_id=payload.session_id,
            task_id=payload.task_id,
            task_payload=payload.task_payload,
            required_capabilities=payload.required_capabilities,
            timeout_seconds=payload.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/inter-agent/conflicts/{conflict_id}")
def query_inter_agent_conflict(
    conflict_id: str,
    session_id: str,
    task_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_inter_agent_conflict(
            session_id=session_id,
            conflict_id=conflict_id,
            task_id=task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/inter-agent/conflicts/{conflict_id}/reassign")
async def reassign_inter_agent_conflict(
    conflict_id: str,
    payload: InterAgentConflictReassignRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.reassign_inter_agent_conflict(
            session_id=payload.session_id,
            conflict_id=conflict_id,
            task_id=payload.task_id,
            failed_agent_id=payload.failed_agent_id,
            failure_reason=payload.failure_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/safety-gate/actions")
def validate_safety_gate_action(
    payload: SafetyGateActionRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.validate_safety_gate_action(
            session_id=payload.session_id,
            action_type=payload.action_type,
            action_payload=payload.action_payload,
            risk_level=payload.risk_level,
            context=payload.context,
            execution_mode=payload.execution_mode,
            cloud_audit_config=payload.cloud_audit_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/safety-gate/decisions/{decision_id}")
def query_safety_gate_decision(
    decision_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_safety_gate_decision(session_id=session_id, decision_id=decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/safety-gate/decisions/{decision_id}/confirm")
def confirm_safety_gate_decision(
    decision_id: str,
    payload: SafetyGateConfirmRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.confirm_safety_gate_decision(
            session_id=payload.session_id,
            decision_id=decision_id,
            confirmed_by=payload.confirmed_by,
            confirmation_context=payload.confirmation_context,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/thought-sandbox/simulations")
def run_thought_sandbox_simulation(
    payload: ThoughtSandboxSimulationRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.run_thought_sandbox_simulation(
            session_id=payload.session_id,
            action_type=payload.action_type,
            action_payload=payload.action_payload,
            risk_level=payload.risk_level,
            task_type=payload.task_type,
            domain=payload.domain,
            branches=payload.branches,
            catastrophe_threshold=payload.catastrophe_threshold,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/thought-sandbox/outcomes/{outcome_id}")
def query_thought_sandbox_outcome(
    outcome_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_thought_sandbox_outcome(session_id=session_id, outcome_id=outcome_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/sensory/signals")
def ingest_sensory_signal(
    payload: SensorySignalRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.ingest_sensory_signal(
            session_id=payload.session_id,
            source=payload.source,
            payload=payload.payload,
            domain=payload.domain,
            source_observations=payload.source_observations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/sensory/events/{event_id}")
def query_sensory_event(
    event_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_sensory_event(session_id=session_id, event_id=event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/working-memory/frame")
def update_working_memory_frame(
    payload: WorkingMemoryUpdateRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.update_working_memory_frame(
            session_id=payload.session_id,
            tick_id=payload.tick_id,
            new_candidates=payload.new_candidates,
            attention_budget=payload.attention_budget,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/working-memory/frame")
def query_working_memory_frame(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_working_memory_frame(session_id=session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/working-memory/interrupt")
def interrupt_working_memory_focus(
    payload: WorkingMemoryInterruptRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.interrupt_working_memory_focus(
            session_id=payload.session_id,
            tick_id=payload.tick_id,
            high_risk_item=payload.high_risk_item,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/working-memory/resume")
def resume_working_memory_focus(
    payload: WorkingMemoryResumeRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.resume_working_memory_focus(
            session_id=payload.session_id,
            tick_id=payload.tick_id,
            focus_id=payload.focus_id,
            trace_id=payload.trace_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/working-memory/considered")
def mark_working_memory_considered(
    payload: WorkingMemoryConsideredRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.mark_working_memory_considered(
            session_id=payload.session_id,
            ref_id=payload.ref_id,
            tick_id=payload.tick_id,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/living-self-model/update")
def update_living_self_model(
    payload: LivingSelfModelUpdateRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.update_living_self_model(
            session_id=payload.session_id,
            turn_result=payload.turn_result,
            recent_events=payload.recent_events,
            working_memory_frame=payload.working_memory_frame,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/living-self-model")
def query_living_self_model(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_living_self_model(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/living-self-model/weakness-patterns")
def detect_living_self_weakness_patterns(
    payload: LivingSelfWeaknessRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.detect_living_self_weakness_patterns(
            session_id=payload.session_id,
            recent_events=payload.recent_events,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/living-self-model/confidence-drift")
def check_living_self_confidence_drift(
    payload: LivingSelfConfidenceDriftRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.check_living_self_confidence_drift(
            session_id=payload.session_id,
            statements=payload.statements,
            evidence=payload.evidence,
            threshold=payload.threshold,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/living-self-model/load-adjustment")
def apply_living_self_load_adjustment(
    payload: LivingSelfLoadAdjustmentRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.apply_living_self_load_adjustment(
            session_id=payload.session_id,
            working_memory_frame=payload.working_memory_frame,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/meta-cognition/decide")
def decide_meta_cognition(
    payload: MetaCognitionDecisionRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.decide_meta_cognition(
            session_id=payload.session_id,
            wm_frame=payload.wm_frame,
            self_model=payload.self_model,
            budget=payload.budget,
            nine_q_state=payload.nine_q_state,
            agenda=payload.agenda,
            tool_registry=payload.tool_registry,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/meta-cognition/decision")
def query_meta_cognition_decision(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_meta_cognition_decision(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/temporal-agenda/tick")
def tick_temporal_agenda(
    payload: TemporalAgendaTickRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.tick_temporal_agenda(
            session_id=payload.session_id,
            current_time=payload.current_time,
            agenda_items=payload.agenda_items,
            brain_scope=payload.brain_scope,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/temporal-agenda/state")
def query_temporal_agenda_state(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_temporal_agenda_state(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/cognitive-conflicts/detect")
def detect_cognitive_conflicts(
    payload: CognitiveConflictDetectRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.detect_cognitive_conflicts(
            session_id=payload.session_id,
            working_memory=payload.working_memory,
            goals=payload.goals,
            nine_q_state=payload.nine_q_state,
            memory_recalls=payload.memory_recalls,
            budget=payload.budget,
            self_model=payload.self_model,
            agenda=payload.agenda,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/cognitive-conflicts")
def query_cognitive_conflicts(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_cognitive_conflicts(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/experience-engine/expectations")
def register_experience_expectation(
    payload: ExperienceExpectationRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.register_experience_expectation(
            session_id=payload.session_id,
            task_id=payload.task_id,
            expected_outcome=payload.expected_outcome,
            success_criteria=payload.success_criteria,
            risk_assessment=payload.risk_assessment,
            source=payload.source,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/experience-engine/bindings")
def bind_experience_outcome(
    payload: ExperienceOutcomeBindingRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.bind_experience_outcome(
            session_id=payload.session_id,
            expectation_id=payload.expectation_id,
            actual_outcome=payload.actual_outcome,
            benefits=payload.benefits,
            losses=payload.losses,
            source_reliability=payload.source_reliability,
            strategy_patch=payload.strategy_patch,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/experience-engine/bindings/{binding_id}")
def query_experience_binding(
    binding_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_experience_binding(session_id=session_id, binding_id=binding_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/experience-engine/goal-ranking")
def rank_goals_with_experience(
    payload: ExperienceGoalRankingRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.rank_goals_with_experience(
            session_id=payload.session_id,
            candidate_goals=payload.candidate_goals,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/dynamic-tools/learn")
def learn_dynamic_tool_capability(
    payload: DynamicToolLearningRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.learn_dynamic_tool_capability(
            session_id=payload.session_id,
            documentation_url=payload.documentation_url,
            source_kind=payload.source_kind,
            capability_name=payload.capability_name,
            verification_endpoint=payload.verification_endpoint,
            verification_cases=payload.verification_cases,
            timeout_seconds=payload.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/dynamic-tools/knowledge/{knowledge_id}")
def query_tool_knowledge_record(
    knowledge_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_tool_knowledge_record(session_id=session_id, knowledge_id=knowledge_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/dynamic-tools/capabilities/{capability_id}")
def query_capability_registration(
    capability_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_capability_registration(session_id=session_id, capability_id=capability_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/value-engine/evaluate")
def evaluate_value_engine(
    payload: ValueEngineEvaluationRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.evaluate_value_engine(
            session_id=payload.session_id,
            candidate_goals=payload.candidate_goals,
            candidate_plans=payload.candidate_plans,
            resource_state=payload.resource_state,
            risk_state=payload.risk_state,
            role_state=payload.role_state,
            self_state=payload.self_state,
            context=payload.context,
            requested_capabilities=payload.requested_capabilities,
            weight_profile=payload.weight_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/value-engine/decisions/{decision_id}")
def query_value_engine_decision(
    decision_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_value_engine_decision(session_id=session_id, decision_id=decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/self-refactor/proposals")
def submit_self_refactor_proposal(
    payload: SelfRefactorProposalRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.submit_self_refactor_proposal(
            session_id=payload.session_id,
            workspace_root=payload.workspace_root,
            target_path=payload.target_path,
            bottleneck_evidence=payload.bottleneck_evidence,
            change_summary=payload.change_summary,
            replacement=payload.replacement,
            sandbox_commands=payload.sandbox_commands,
            capability_id=payload.capability_id,
            resource_state=payload.resource_state,
            risk_state=payload.risk_state,
            context=payload.context,
            self_mod_gate_inputs=payload.self_mod_gate_inputs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/self-refactor/proposals/{proposal_id}")
def query_self_refactor_proposal(
    proposal_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_self_refactor_proposal(session_id=session_id, proposal_id=proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/self-coding/cycles")
def run_self_coding_cycle(
    payload: SelfCodingCycleRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.run_self_coding_cycle(
            session_id=payload.session_id,
            workspace_root=payload.workspace_root,
            candidate_root=payload.candidate_root,
            capability_gap=payload.capability_gap,
            patch_plan=payload.patch_plan,
            verification_commands=payload.verification_commands,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/self-coding/patches/{patch_id}")
def query_self_coding_patch(
    patch_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.query_self_coding_patch(session_id=session_id, patch_id=patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/preference-alignment/judgments")
async def run_preference_judgment(
    payload: PreferenceJudgmentRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.run_preference_judgment(
            session_id=payload.session_id,
            detected_state=payload.detected_state,
            detection_source=payload.detection_source,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/preference-alignment/cases/{case_id}/confirm")
async def confirm_preference_case(
    case_id: str,
    payload: PreferenceConfirmRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.confirm_preference_case(
            session_id=payload.session_id,
            ambiguity_case_id=case_id,
            user_decision=payload.user_decision,
            user_id=payload.user_id,
            confirmation_context=payload.confirmation_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/preference-alignment/preferences/{preference_id}")
async def query_preference_record(
    preference_id: str,
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.query_preference_record(session_id=session_id, preference_id=preference_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/preference-alignment/preferences/{preference_id}/revoke")
async def revoke_preference_record(
    preference_id: str,
    payload: PreferenceRevokeRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.revoke_preference_record(
            session_id=payload.session_id,
            preference_id=preference_id,
            reason=payload.reason,
            user_id=payload.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/preference-alignment/signals/intercept")
async def intercept_extreme_signal(
    payload: ExtremeSignalRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.intercept_extreme_signal(
            session_id=payload.session_id,
            signal_content=payload.signal_content,
            signal_source=payload.signal_source,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/preference-alignment/signals/{signal_record_id}/attack-sample")
async def mark_attack_sample(
    signal_record_id: str,
    payload: AttackSampleMarkRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return await facade.mark_attack_sample(
            session_id=payload.session_id,
            signal_record_id=signal_record_id,
            attack_type=payload.attack_type,
            confidence=payload.confidence,
            analyst_id=payload.analyst_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/preference-alignment/attacks/detect")
async def detect_similar_attack(
    session_id: str,
    signal_content: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
    similarity_threshold: float = Query(default=0.85, ge=0, le=1),
) -> dict[str, Any]:
    try:
        return await facade.detect_similar_attack(
            session_id=session_id,
            signal_content=signal_content,
            similarity_threshold=similarity_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/runtime/environment/observe")
def observe_environment_awareness(
    payload: EnvironmentAwarenessRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.observe_environment_awareness(
            session_id=payload.session_id,
            turn_id=payload.turn_id,
            raw_signals=payload.raw_signals,
            source_conflict_field=payload.source_conflict_field,
            source_conflict_samples=payload.source_conflict_samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/runtime/environment/snapshots")
def query_environment_awareness_snapshots(
    session_id: str,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
    limit: int = 10,
) -> dict[str, Any]:
    try:
        return facade.query_environment_awareness_snapshots(session_id=session_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
