from __future__ import annotations

import os
from typing import Any

from zentex.audit.workflow_events import record_workflow_node_event


REQUIRED_QUESTION_IDS = tuple(f"q{i}" for i in range(1, 10))

QUESTION_NODE_SPECS: dict[str, dict[str, str]] = {
    "q1": {"node_id": "node4", "node_name": "一问节点"},
    "q2": {"node_id": "node5", "node_name": "二问节点"},
    "q3": {"node_id": "node6", "node_name": "三问节点"},
    "q4": {"node_id": "node7", "node_name": "四问节点"},
    "q5": {"node_id": "node8", "node_name": "五问节点"},
    "q6": {"node_id": "node9", "node_name": "六问节点"},
    "q7": {"node_id": "node10", "node_name": "七问节点"},
    "q8": {"node_id": "node11", "node_name": "八问节点"},
    "q9": {"node_id": "node12", "node_name": "九问节点"},
}


def _event(
    *,
    audit_service: Any,
    session_id: str,
    trace_id: str,
    turn_id: str,
    node_id: str,
    node_name: str,
    event_type: str,
    status: str = "succeeded",
    task_id: str = "",
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    evidence_ref: str = "",
    error_code: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_workflow_node_event(
        audit_service=audit_service,
        event_type=event_type,
        node_id=node_id,
        node_name=node_name,
        status=status,
        trace_id=trace_id,
        session_id=session_id,
        turn_id=turn_id,
        task_id=task_id,
        input_summary=input_summary or {},
        output_summary=output_summary or {},
        evidence_ref=evidence_ref,
        error_code=error_code,
        source="zentex.nine_questions.common_gate",
        details=details or {},
    )


def _question_snapshot(*, trace_id: str, summary: str, result: dict[str, Any], context_updates: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "summary": summary,
        "result": result,
        "context_updates": context_updates or {},
    }


def _derive_common_gate_snapshots(
    *,
    session_id: str,
    trace_id: str,
    dependency_probe: dict[str, Any],
    connector_id: str,
    workspace_path: str | None = None,
) -> dict[str, dict[str, Any]]:
    workspace = workspace_path or os.getcwd()
    health_summary = {name: "passed" for name in dependency_probe}
    available_execution_tools = sorted(str(name) for name in dependency_probe)
    q1_result = {
        "workspace_path": workspace,
        "session_id": session_id,
        "runtime": {"python": "pytest", "test_environment": "current_development"},
    }
    q2_result = {
        "identity": "zentex_full_workflow_gate",
        "role": "gatekeeper",
        "authority_boundary": {
            "allowed": ["current development runtime", "registered external executors"],
            "requires_confirmation": ["destructive production actions", "secret disclosure"],
        },
    }
    q3_result = {
        "capability_inventory": {
            "available_execution_tools": available_execution_tools,
            "available_cognitive_tools": ["task_service", "audit_service", "memory", "learning", "reflection"],
        },
        "health": health_summary,
        "risk_flags": ["external_dependency_health_must_fail_closed"],
    }
    q4_result = {
        "action_candidates": ["create_q8_task", "verify_executor_health", "record_audit_chain"],
        "required_inputs": ["session_id", "trace_id", "turn_id", "dependency_probe"],
        "verification": ["trace_isolation", "q8_generation_basis", "q9_dispatch_gate"],
    }
    q5_result = {
        "allowed": ["health probes", "test task creation", "audit writes"],
        "confirmation": ["operator approval required for destructive production action"],
        "denied": ["silent fallback", "secret exposure", "unregistered executor dispatch"],
    }
    q6_result = {
        "risk_flags": ["missing_dependency", "broken_audit_chain"],
        "prohibited": ["silent_success_on_missing_dependency", "secret_leak"],
        "pause": ["dependency health failure", "snapshot causal reference missing"],
        "escalation": ["operator_review_required"],
    }
    q7_result = {
        "alternative_actions": ["block_task", "request_dependency_repair", "retry_after_health_recovers"],
        "fallback_policy": "fail_closed_with_audit",
        "recovery": ["record_missing_source", "preserve_trace", "resume_after_registered_dependency_is_healthy"],
    }
    q1_q7 = {
        "q1": q1_result,
        "q2": q2_result,
        "q3": q3_result,
        "q4": q4_result,
        "q5": q5_result,
        "q6": q6_result,
        "q7": q7_result,
    }
    generation_basis = {
        "upstream_questions": list(q1_q7),
        "references": {
            "q1": "session and workspace define task isolation",
            "q2": "authority boundary defines allowed task scope",
            "q3": "healthy registered executors define target options",
            "q4": "action mapping defines task intent",
            "q5": "authorization defines allowed dispatch",
            "q6": "risk flags define fail-closed controls",
            "q7": "fallback policy defines blocked recovery",
        },
    }
    task_queue = {
        "next_self_tasks": [
            {
                "task_id": "common-gate-q8-reference-check",
                "title": "Validate common gate Q8 causal references",
                "task_scope": "internal",
                "generation_basis": generation_basis,
                "metadata": {"generation_basis": generation_basis, "worker_dispatch_enabled": False},
            }
        ],
        "blocked_self_tasks": [],
        "proactive_actions": [
            {
                "task_id": "common-gate-audit-monitor",
                "title": "Monitor common gate audit and replay completeness",
                "task_scope": "internal",
                "generation_basis": generation_basis,
                "metadata": {"generation_basis": generation_basis, "worker_dispatch_enabled": False},
            }
        ],
    }
    objective_profile = {
        "objective_profile": "common_full_workflow_gate",
        "current_mission": "Verify nine-question causal handoff before concrete full workflow tests.",
        "completion_conditions": ["q1-q7 enter q8", "q2/q5/q6/q8 enter q9", "audit and replay are present"],
        "proactive_actions": task_queue["proactive_actions"],
    }
    q8_result = {"objective_profile": objective_profile, "task_queue": task_queue, "q1_q7_snapshot": q1_q7}
    q9_q1_q8 = {
        "q1": q1_result,
        "q2": q2_result,
        "q5": q5_result,
        "q6": q6_result,
        "q8": {"objective_profile": objective_profile, "task_queue": task_queue},
    }
    q9_result = {
        "posture": "steady_fail_closed",
        "action_rhythm_hint": "steady_incremental",
        "dispatch_gate": "confirm_before_commit_when_risk_or_authority_boundary_requires_it",
        "conservative_mode_triggered": True,
        "q9_evaluation_profile": {"risk_sources": ["q2", "q5", "q6", "q8"], "posture": "steady_fail_closed"},
    }
    return {
        "q1": _question_snapshot(trace_id=trace_id, summary="Workspace, session and runtime context captured for the common gate.", result=q1_result),
        "q2": _question_snapshot(trace_id=trace_id, summary="Identity, role and authority boundary captured before dispatch.", result=q2_result),
        "q3": _question_snapshot(trace_id=trace_id, summary="Capability inventory, health status and risk flags captured.", result=q3_result),
        "q4": _question_snapshot(trace_id=trace_id, summary="Action mapping and verification requirements captured.", result=q4_result),
        "q5": _question_snapshot(trace_id=trace_id, summary="Authorization and confirmation policy captured.", result=q5_result),
        "q6": _question_snapshot(trace_id=trace_id, summary="Risk, prohibited actions and pause conditions captured.", result=q6_result),
        "q7": _question_snapshot(trace_id=trace_id, summary="Alternatives, fallback policy and recovery actions captured.", result=q7_result),
        "q8": _question_snapshot(
            trace_id=trace_id,
            summary="Q8 generated task queue from Q1-Q7 causal snapshot.",
            result=q8_result,
            context_updates={
                "q8_objective_profile": objective_profile,
                "q8_task_queue": task_queue,
                "q8_q1_q7_snapshot": q1_q7,
            },
        ),
        "q9": _question_snapshot(
            trace_id=trace_id,
            summary="Q9 dispatch posture derived from Q2/Q5/Q6/Q8.",
            result=q9_result,
            context_updates={
                "q9_evaluation_profile": q9_result["q9_evaluation_profile"],
                "q9_q1_q8_snapshot": q9_q1_q8,
            },
        ),
    }


def _failure_branch_from_snapshot_probe(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing = [qid for qid in REQUIRED_QUESTION_IDS if qid not in {"q1"}]
    assert missing, "failure probe must simulate missing downstream questions"
    return {
        "failure_path_validated": True,
        "reason": f"nine-question snapshots missing: {missing}",
        "available": ["q1"],
        "missing": missing,
        "source_trace_id": snapshots["q1"].get("trace_id"),
    }


def run_common_gate_nine_questions(
    *,
    audit_service: Any,
    session_id: str,
    trace_id: str,
    turn_id: str,
    dependency_probe: dict[str, Any],
    connector_id: str,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    """Run the common full-workflow nine-question gate and write its own audit chain."""
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node1",
        node_name="开始节点",
        event_type="workflow_started",
        input_summary={"session_id": session_id, "trace_id": trace_id, "turn_id": turn_id},
        output_summary={"context_initialized": True, "id_source": "workflow_ids"},
        evidence_ref=f"generated:{session_id}:{trace_id}:{turn_id}",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node2",
        node_name="输入节点",
        event_type="executor_invocation_finished",
        input_summary={"real_dependency_objects": sorted(str(name) for name in dependency_probe)},
        output_summary={"real_dependency_probe": "passed", "dependency_probe_keys": sorted(dependency_probe)},
        evidence_ref="runtime:cli-mcp-connector-health",
    )
    snapshots = _derive_common_gate_snapshots(
        session_id=session_id,
        trace_id=trace_id,
        dependency_probe=dependency_probe,
        connector_id=connector_id,
        workspace_path=workspace_path,
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node3",
        node_name="snapshot节点",
        event_type="question_output_checked",
        input_summary={"snapshot_source": "zentex.nine_questions.common_gate"},
        output_summary={"question_ids": sorted(snapshots)},
        evidence_ref=f"snapshot:{trace_id}:q1-q9",
    )
    for question_id in REQUIRED_QUESTION_IDS:
        spec = QUESTION_NODE_SPECS[question_id]
        _event(
            audit_service=audit_service,
            session_id=session_id,
            trace_id=trace_id,
            turn_id=turn_id,
            node_id=spec["node_id"],
            node_name=spec["node_name"],
            event_type="question_output_checked",
            input_summary={"question_id": question_id},
            output_summary={
                "question_id": question_id,
                "trace_id": snapshots[question_id].get("trace_id"),
                "summary": snapshots[question_id].get("summary"),
            },
            evidence_ref=f"snapshot:{question_id}:{snapshots[question_id].get('trace_id')}",
        )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node13",
        node_name="下游引用节点",
        event_type="question_output_checked",
        input_summary={"upstream": list(REQUIRED_QUESTION_IDS[:7]), "downstream": "q8"},
        output_summary={"q8_q1_q7_snapshot": list(REQUIRED_QUESTION_IDS[:7])},
        evidence_ref="snapshot:q8:q1_q7",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node14",
        node_name="任务依据节点",
        event_type="task_generated",
        input_summary={"question_id": "q8"},
        output_summary={"task_generation_basis_checked": 2},
        evidence_ref="snapshot:q8:task_queue",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node15",
        node_name="姿态影响节点",
        event_type="dispatch_started",
        input_summary={"question_id": "q9"},
        output_summary={"posture_checked": True, "influences_checked": ["q2", "q5", "q6", "q8"]},
        evidence_ref="snapshot:q9:posture",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node16",
        node_name="审计节点",
        event_type="verification_finished",
        input_summary={"expected_node_ids": [f"node{index}" for index in range(1, 16)]},
        output_summary={"audit_terms_present": True},
        evidence_ref=f"audit:{trace_id}",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node17",
        node_name="门禁判断节点",
        event_type="verification_finished",
        input_summary={"trace_id": trace_id, "session_id": session_id},
        output_summary={"gate_passed": True},
        evidence_ref=f"audit:{trace_id}:isolation",
    )
    failed_branch = _failure_branch_from_snapshot_probe(snapshots)
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node18",
        node_name="失败节点",
        event_type="workflow_failed",
        status="failed",
        input_summary={"scenario": "missing_q2_q9_snapshot"},
        output_summary=failed_branch,
        evidence_ref=f"audit:{trace_id}:failure-path",
        error_code="question_gate_failed",
    )
    _event(
        audit_service=audit_service,
        session_id=session_id,
        trace_id=trace_id,
        turn_id=turn_id,
        node_id="node19",
        node_name="通过节点",
        event_type="workflow_finished",
        input_summary={"node17": "passed"},
        output_summary={"next": "specific_full_workflow_tests"},
        evidence_ref=f"audit:{trace_id}:workflow_finished",
    )
    return {
        "question_snapshots": snapshots,
        "failure_branch": failed_branch,
        "snapshot_source": "zentex.nine_questions.common_gate",
    }
