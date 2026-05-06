from __future__ import annotations

from typing import Any


def build_q8_external_staged_llm_request(
    *,
    system_prompt: str,
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_llm_output: Any | None = None,
    q7_snapshot: Any,
    normalized_task_state: dict[str, list[dict[str, Any]]],
    request_timeout_seconds: float,
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    q1_q7_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_stage_prompt = (
        "Final stage: synthesize Q8 external ObjectiveProfile only. "
        "Return strict JSON with exactly one top-level key: `ObjectiveProfile`, following the external system prompt's Output Format exactly. "
        "`current_mission` must strictly inherit the current core mission from context.Q3_RoleProfile or upstream Q3 mission data, without rewriting. "
        "Before producing objectives, perform the first-person situational self-questioning over context.Q1_Workspace_Domain_Inference, "
        "context.Q2_AssetInventory, context.Q2_Functional_Capabilities, context.Q4_External_Capabilities, "
        "context.Q5_AuthorizationBoundary, context.Q6_ConsequenceProfile, and context.Q7_Redlines. "
        "`basis_and_traceability.q1_environment_bases`, `basis_and_traceability.q2_asset_support_bases`, "
        "`basis_and_traceability.q4_capability_confidence`, and `basis_and_traceability.q5_q6_q7_boundary_checks` "
        "must all be present as independent arrays and must be written in first person to show the self-questioning chain. "
        "Q2 traceability must name concrete compliant tools/connectors/permissions when they exist, but "
        "`primary_objectives` and `secondary_objectives` must remain pure abstract business intent and must never name concrete plugins, CLI commands, MCP tools, scripts, connector ids, or agent ids. "
        "If Q2 has no external execution function supporting the objective, or the objective touches Q5/Q7 safety prohibitions, "
        "force downgrade to an internal cognitive task intent and explain the downgrade in `pause_conditions` and `escalation_conditions`. "
        "Q8 external_tasks only outputs this abstract ObjectiveProfile; downstream task splitting, executor binding, "
        "state transition, and audited dispatch are owned by 下游任务中心 and Q9. "
        "Do not output `task_name`, `task_description`, `task_goal`, `task_creation_reason_and_basis`, "
        "`functional_plugin_ref`, `execution_parameters`, `expected_receipt_type`, `external_objectives`, "
        "`degraded_to_internal_tasks`, `external_execution_tasks`, `objective_profile`, `task_queue`, `executor_type`, "
        "`target_id`, `required_capabilities`, `generation_basis`, markdown, or explanatory prose."
    )
    q2_functional_plugins = [
        str(item or "").strip()
        for item in (q2_functional_plugins or [])
        if str(item or "").strip()
    ]
    q4_external_capabilities = q4_external_capabilities if isinstance(q4_external_capabilities, dict) else {}
    q7_redlines = q7_redlines if isinstance(q7_redlines, dict) else {}
    snapshot = q1_q7_snapshot if isinstance(q1_q7_snapshot, dict) else {}
    q1_payload = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    if not q1_payload and isinstance(q1_llm_output, dict):
        q1_payload = q1_llm_output
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q4_payload = snapshot.get("q4") if isinstance(snapshot.get("q4"), dict) else {}
    if not q4_payload:
        q4_payload = q4_external_capabilities
    q5_payload = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q6_payload = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    q7_payload = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    if not q7_payload and isinstance(q7_snapshot, dict):
        q7_payload = q7_snapshot
    context = {
        "request_timeout_seconds": request_timeout_seconds,
        "Q1_Workspace_Domain_Inference": q1_payload,
        "Q2_AssetInventory": q2_payload,
        "Q3_RoleProfile": q3_payload,
        "Q4_External_Capabilities": q4_payload,
        "Q5_AuthorizationBoundary": q5_payload,
        "Q6_ConsequenceProfile": q6_payload,
        "Q7_Redlines": q7_payload or q7_redlines,
        "Q2_Functional_Capabilities": q2_functional_plugins,
        "q8_priority_baseline": priority_baseline if isinstance(priority_baseline, dict) else {},
        "allowed_tasks": allowed_tasks,
        "blocked_tasks": blocked_tasks,
        "q7_red_line_assessment": {"q7": q7_snapshot if isinstance(q7_snapshot, dict) else {}},
        "q7_alternatives": {"q7": q7_snapshot if isinstance(q7_snapshot, dict) else {}},
        "task_state": normalized_task_state if isinstance(normalized_task_state, dict) else {},
        "q8_request_scope": "external",
    }
    return {
        "system_prompt": system_prompt,
        "prompt": f"{system_prompt}\n\n{final_stage_prompt}",
        "stage_prompt": final_stage_prompt,
        "context": context,
        "scope": "external",
    }
