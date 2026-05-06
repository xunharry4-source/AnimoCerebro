from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_llm_output_from_table as load_q2_external_llm_output_from_table,
    load_internal_llm_output_from_table as load_q2_internal_llm_output_from_table,
)
from plugins.nine_questions.q3_role_inference.modules import build_q3_runtime_inventory_context
from plugins.nine_questions.q4_what_can_i_do.modules import (
    derive_capability_baseline,
    derive_permission_profile,
    normalize_functional_capabilities,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.modules import (
    derive_authorization_baseline,
)
from plugins.nine_questions.q6_what_should_i_not_do.modules import (
    derive_forbidden_zone_baseline,
    normalize_redline_inputs,
)
from plugins.nine_questions.q7_what_else_can_i_do.modules import (
    derive_red_line_assessment_baseline,
)
from plugins.nine_questions.q9_how_should_i_act.modules import (
    normalize_q8_profile,
    normalize_snapshot_dict,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q4, NINE_QUESTION_Q6


def merge_q_module_recovery_actions(question_id: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for action in actions:
        if isinstance(action, dict) and str(action.get("action_id") or "").strip():
            merged[str(action["action_id"])] = deepcopy(action)

    if question_id == "q3":
        merged["q3-refresh-runtime-inventory"] = {
            "action_id": "q3-refresh-runtime-inventory",
            "label": "刷新 Q3 运行态盘点模块",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q3_runtime_inventory",
            "reason": "仅刷新 Q3 runtime inventory 相关模块，不重跑 LLM。",
            "path": "/api/web/nine-questions/q3/modules/q3_runtime_inventory/retry",
        }
    elif question_id == "q4":
        merged["q4-refresh-capability-inputs"] = {
            "action_id": "q4-refresh-capability-inputs",
            "label": "刷新 Q4 能力输入模块",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q4_execution_capability_verification",
            "reason": "仅刷新 Q4 inventory/permission/execution capability 模块，不重跑 LLM。",
            "path": "/api/web/nine-questions/q4/modules/q4_execution_capability_verification/retry",
        }
    elif question_id == "q5":
        merged["q5-refresh-contact-policy"] = {
            "action_id": "q5-refresh-contact-policy",
            "label": "刷新 contact policy",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q5_contact_policy_validation",
            "reason": "仅刷新 Q5 的 contact_policy 基线与模块状态，不重跑 LLM。",
            "path": "/api/web/nine-questions/q5/modules/q5_contact_policy_validation/retry",
        }
    elif question_id == "q6":
        merged["q6-refresh-redline-plugins"] = {
            "action_id": "q6-refresh-redline-plugins",
            "label": "刷新红线插件输入",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q6_redline_hint_chain",
            "reason": "仅刷新 Q6 redline functional inputs 和基线，不重跑 LLM。",
            "path": "/api/web/nine-questions/q6/modules/q6_redline_hint_chain/retry",
        }
    elif question_id == "q7":
        merged["q7-refresh-redline-baseline"] = {
            "action_id": "q7-refresh-redline-baseline",
            "label": "刷新 Q7 红线证据",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q7_red_line_baseline_projection",
            "reason": "仅刷新 IdentityKernel、Q5、安全拒绝历史和程序记忆证据，不重跑 LLM。",
            "path": "/api/web/nine-questions/q7/modules/q7_red_line_baseline_projection/retry",
        }
    elif question_id == "q9":
        merged["q9-refresh-posture-inputs"] = {
            "action_id": "q9-refresh-posture-inputs",
            "label": "刷新 Q9 姿态输入模块",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q9_functional_posture_chain",
            "reason": "仅刷新 Q9 self-model/budget/posture plugin baseline；不重跑 LLM 姿态投影。",
            "path": "/api/web/nine-questions/q9/modules/q9_functional_posture_chain/retry",
        }
    return list(merged.values())


def upsert_module_run(
    module_runs: list[dict[str, Any]],
    *,
    module_id: str,
    status: str,
    error_code: str = "",
    error_message: str = "",
    data: dict[str, Optional[Any]] = None,
) -> list[dict[str, Any]]:
    next_runs: list[dict[str, Any]] = []
    replaced = False
    for run in module_runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("module_id") or "") == module_id:
            next_runs.append(
                {
                    **deepcopy(run),
                    "module_id": module_id,
                    "status": status,
                    "error_code": error_code,
                    "error_message": error_message,
                    **({"data": deepcopy(data)} if data is not None else {}),
                }
            )
            replaced = True
        else:
            next_runs.append(deepcopy(run))
    if not replaced:
        next_runs.append(
            {
                "module_id": module_id,
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
                **({"data": deepcopy(data)} if data is not None else {}),
            }
        )
    return next_runs


def build_q9_question_snapshot(dependency_context: dict[str, Any]) -> dict[str, Any]:
    raw = dependency_context.get("q1_q8_snapshot") or dependency_context.get("q1_q8") or {}
    question_snapshot = normalize_snapshot_dict(raw)
    if question_snapshot:
        question_snapshot["q8"] = normalize_q8_profile(question_snapshot.get("q8"))
        return question_snapshot
    q8_raw = (
        dependency_context.get("q8")
        or dependency_context.get("q8_objective_profile")
        or dependency_context.get("q8_objective_and_queue")
        or {}
    )
    q2_internal_output = load_q2_internal_llm_output_from_table(
        db_path=dependency_context.get("nine_question_state_db_path")
    )
    q2_external_output = load_q2_external_llm_output_from_table(
        db_path=dependency_context.get("nine_question_state_db_path")
    )
    return {
        "q1": dependency_context.get("workspace_domain_inference") or {},
        "q2": {
            "q2_internal_tool_asset_inventory": q2_internal_output,
            "q2_external_tool_asset_inventory": q2_external_output,
        },
        "q3": dependency_context.get("q3_role_profile") or {},
        "q4": dependency_context.get("q4_capability_boundary_profile") or {},
        "q5": dependency_context.get("q5_authorization_boundary_profile") or dependency_context.get("q5_permission_boundary") or {},
        "q6": dependency_context.get("q6_forbidden_zone_profile") or {},
        "q7": dependency_context.get("q7_red_line_assessment") or dependency_context.get("red_line_assessment") or {},
        "q8": normalize_q8_profile(q8_raw),
        "summaries": dependency_context.get("nine_questions") or {},
    }

async def retry_q3_runtime_inventory_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    module_id: str,
    dependency_context: dict[str, Any],
    build_runtime_inventory_context_fn: Any = build_q3_runtime_inventory_context,
) -> str:
    snapshot = snapshot_map.get("q3")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q3 snapshot missing; cannot retry runtime inventory module")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    runtime_context = {
        **dependency_context,
        **context_updates,
        "trace_id": str(snapshot.get("trace_id") or "q3:module-retry"),
        "session_id": "nq-baseline",
    }
    inventory_context = build_runtime_inventory_context_fn(
        runtime_context,
        include_resource_inference_gate=True,
    )
    context_updates.update(inventory_context["context_updates"])

    existing_diagnosis = deepcopy(context_updates.get("q3_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    refreshed_runs: list[dict[str, Any]] = []
    for run in inventory_context["module_runs"]:
        if not isinstance(run, dict):
            continue
        refreshed_runs.append(run)
        module_runs = upsert_module_run(
            module_runs,
            module_id=str(run.get("module_id") or ""),
            status=str(run.get("status") or "missing"),
            error_code=str(run.get("error_code") or ""),
            error_message=str(run.get("error_message") or ""),
            data=run.get("data") if isinstance(run.get("data"), dict) else None,
        )
    incomplete_runs = [
        run
        for run in refreshed_runs
        if str(run.get("status") or "").lower() not in {"completed", "ready"}
    ]
    if incomplete_runs:
        raise HTTPException(status_code=409, detail="Q3 runtime inventory module retry cannot save incomplete module outputs")
    existing_diagnosis.update(
        {
            "authenticity_status": "completed",
            "diagnosis_code": "runtime_inventory_refreshed",
            "diagnosis_message": "Q3 runtime inventory modules were refreshed from real module outputs. Resource inference remains the last committed LLM output until Q3 is rerun.",
            "module_runs": module_runs,
            "recovery_plan": {
                **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
                "actions": merge_q_module_recovery_actions("q3", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
            },
        }
    )
    context_updates["q3_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q3",
        {"context_updates": context_updates},
        refresh_reason=f"question_module_retry:q3:{module_id}",
    )
    return f"single_nine_question_module_retried:q3:{module_id}"


async def retry_q9_posture_input_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    module_id: str,
    dependency_context: dict[str, Any],
    functional_context: dict[str, Any],
    plugin_service: Any,
    functional_executor: Any,
    normalize_self_model_fn: Any,
    normalize_reasoning_budget_fn: Any,
    normalize_functional_postures_fn: Any,
    derive_posture_baseline_fn: Any,
) -> str:
    snapshot = snapshot_map.get("q9")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q9 snapshot missing; cannot retry posture input module")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    question_snapshot = build_q9_question_snapshot(functional_context)
    self_model = normalize_self_model_fn(
        functional_context.get("living_self_model")
        or functional_context.get("self_model")
        or dependency_context.get("living_self_model")
        or dependency_context.get("self_model")
    )
    reasoning_budget = normalize_reasoning_budget_fn(
        functional_context.get("reasoning_budget")
        or functional_context.get("budget")
        or dependency_context.get("reasoning_budget")
        or dependency_context.get("budget")
    )

    if not question_snapshot.get("q8"):
        raise HTTPException(status_code=409, detail="Q9 posture input module retry requires completed Q8 SQLite LLM output")
    if not self_model:
        raise HTTPException(status_code=409, detail="Q9 posture input module retry requires real self-model input")
    if not reasoning_budget:
        raise HTTPException(status_code=409, detail="Q9 posture input module retry requires real reasoning budget input")
    if plugin_service is None:
        raise HTTPException(status_code=409, detail="Q9 posture input module retry requires plugin_service")

    plugin_runs: list[dict[str, Any]] = []
    functional_postures_raw: list[dict[str, Any]] = []
    raw_inputs = functional_executor(
        plugin_service,
        "nine_questions.q9",
        default_parameters={"decision_trace": dict(functional_context)},
        trace_id=str(snapshot.get("trace_id") or "q9:module-retry"),
        originator_id="nq-baseline",
        caller_plugin_id="nine_questions.q9",
    )
    for item in raw_inputs:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="Q9 posture input module retry received invalid plugin output")
        done = item.get("status") == "done"
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or "nine_questions.q9"),
                "expected": True,
                "attempted": True,
                "status": "completed" if done else "failed",
                "error_code": "" if done else "posture_plugin_failed",
                "error_message": "" if done else str(item.get("error") or "posture plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if not done:
            raise HTTPException(
                status_code=409,
                detail=f"Q9 posture input module retry cannot save failed functional posture outputs: {item}",
            )
        functional_postures_raw.append({"plugin_id": item.get("plugin_id"), "result": item.get("result")})
    if not plugin_runs:
        raise HTTPException(status_code=409, detail="Q9 posture input module retry requires successful posture plugin outputs")

    normalized_functional_postures = normalize_functional_postures_fn(functional_postures_raw)
    posture_baseline = derive_posture_baseline_fn(
        question_snapshot,
        self_model,
        reasoning_budget,
        normalized_functional_postures,
    )
    context_updates["q9_q1_q8_snapshot"] = question_snapshot
    context_updates["q9_self_model"] = self_model
    context_updates["q9_reasoning_budget"] = reasoning_budget
    context_updates["q9_posture_baseline"] = posture_baseline
    context_updates["q9_functional_postures"] = normalized_functional_postures

    existing_diagnosis = deepcopy(context_updates.get("q9_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_q1_q8_validation",
        status="completed",
        error_code="",
        error_message="",
        data={"q1_q8_snapshot": question_snapshot},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_self_model_source_validation",
        status="completed",
        error_code="",
        error_message="",
        data=self_model,
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_reasoning_budget_source_validation",
        status="completed",
        error_code="",
        error_message="",
        data=reasoning_budget,
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_functional_posture_chain",
        status="completed",
        error_code="",
        error_message="",
        data={"functional_postures": normalized_functional_postures, "plugin_runs": plugin_runs},
    )
    existing_diagnosis.update(
        {
            "authenticity_status": "completed",
            "diagnosis_code": "posture_inputs_refreshed",
            "diagnosis_message": "Q9 posture input modules were refreshed from real module outputs; LLM posture projection was not rewritten.",
            "module_runs": module_runs,
            "plugin_runs": plugin_runs,
            "recovery_plan": {
                **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
                "actions": merge_q_module_recovery_actions("q9", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
            },
        }
    )
    context_updates["q9_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q9",
        {"context_updates": context_updates},
        refresh_reason=f"question_module_retry:q9:{module_id}",
    )
    return f"single_nine_question_module_retried:q9:{module_id}"


async def retry_q4_capability_input_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    module_id: str,
    functional_context: dict[str, Any],
    plugin_service: Any,
    functional_executor: Any,
) -> str:
    snapshot = snapshot_map.get("q4")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q4 snapshot missing; cannot retry capability input module")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    q2_inventory = functional_context.get("q2_unified_asset_inventory") or {}
    q2_inventory = q2_inventory if isinstance(q2_inventory, dict) else {}
    exec_domains = list(q2_inventory.get("available_execution_tools", []) or [])

    plugin_runs: list[dict[str, Any]] = []
    functional_capabilities: list[dict[str, Any]] = []
    if plugin_service is None:
        raise HTTPException(status_code=409, detail="Q4 capability input module retry requires plugin_service")
    raw_inputs = functional_executor(
        plugin_service,
        NINE_QUESTION_Q4,
        default_parameters={"context": dict(functional_context)},
        trace_id=str(snapshot.get("trace_id") or "q4:module-retry"),
        originator_id="nq-baseline",
        caller_plugin_id=NINE_QUESTION_Q4,
    )
    for item in raw_inputs:
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or NINE_QUESTION_Q4),
                "expected": True,
                "attempted": True,
                "status": "completed" if item.get("status") == "done" else "failed",
                "error_code": "" if item.get("status") == "done" else "capability_plugin_failed",
                "error_message": "" if item.get("status") == "done" else str(item.get("error") or "capability plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if item.get("status") != "done":
            raise HTTPException(status_code=409, detail="Q4 capability input module retry cannot save failed functional capability outputs")
        functional_capabilities.append(item)
        plugin_id = str(item.get("plugin_id") or "").strip()
        if plugin_id:
            exec_domains.append(plugin_id)
    exec_domains = list(dict.fromkeys(exec_domains))
    normalized_functional_capabilities = normalize_functional_capabilities(functional_capabilities)
    permission_profile = derive_permission_profile(functional_context, q2_inventory)
    capability_baseline = derive_capability_baseline(
        functional_context,
        q2_inventory,
        exec_domains,
        permission_profile,
        normalized_functional_capabilities,
    )
    context_updates["q4_active_execution_domains"] = exec_domains
    context_updates["q4_permission_profile"] = permission_profile
    context_updates["q4_capability_baseline"] = capability_baseline
    context_updates["q4_functional_capabilities"] = normalized_functional_capabilities

    existing_diagnosis = deepcopy(context_updates.get("q4_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    if not q2_inventory or not permission_profile or not exec_domains:
        raise HTTPException(status_code=409, detail="Q4 capability input module retry cannot save incomplete capability evidence")
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_inventory_validation",
        status="completed",
        error_code="",
        error_message="",
        data={"q2_unified_asset_inventory": q2_inventory},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_permission_validation",
        status="completed",
        error_code="",
        error_message="",
        data=permission_profile if isinstance(permission_profile, dict) else {},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_execution_capability_verification",
        status="completed",
        error_code="",
        error_message="",
        data={"active_execution_domains": exec_domains, "functional_capabilities": normalized_functional_capabilities},
    )
    existing_diagnosis.update(
        {
            "authenticity_status": "completed",
            "diagnosis_code": "capability_inputs_refreshed",
            "diagnosis_message": "Q4 capability input modules were refreshed from real inputs. Actionability projection remains the last committed LLM output until Q4 is rerun.",
            "module_runs": module_runs,
            "plugin_runs": plugin_runs,
            "recovery_plan": {
                **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
                "actions": merge_q_module_recovery_actions("q4", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
            },
        }
    )
    context_updates["q4_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q4",
        {"context_updates": context_updates},
        refresh_reason=f"question_module_retry:q4:{module_id}",
    )
    return f"single_nine_question_module_retried:q4:{module_id}"


async def retry_q5_policy_module(
    *,
    service: Any,
    snapshot: dict[str, Any],
    module_id: str,
) -> str:
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q5 snapshot missing; cannot retry module")

    result_payload = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    q4_profile = context_updates.get("q4_capability_boundary_profile") or result_payload.get("q4_capability_boundary_profile") or {}
    q4_profile = q4_profile if isinstance(q4_profile, dict) else {}
    actionable_space = list(q4_profile.get("actionable_space", []) or q4_profile.get("available_actions", []) or [])
    normalized_functional_inputs = context_updates.get("q5_functional_authorization_inputs")
    normalized_functional_inputs = normalized_functional_inputs if isinstance(normalized_functional_inputs, list) else []

    merged_snapshot_context = {
        **context_updates,
        **{
            "q4_capability_boundary_profile": q4_profile,
            "contact_policy": context_updates.get("contact_policy"),
            "tenant_scope": context_updates.get("tenant_scope"),
            "agent_trust_policy": context_updates.get("agent_trust_policy"),
            "q3_connected_agents": context_updates.get("q3_connected_agents"),
        },
    }
    authorization_baseline = derive_authorization_baseline(
        merged_snapshot_context,
        actionable_space,
        normalized_functional_inputs,
    )
    context_updates["q5_authorization_baseline"] = authorization_baseline
    context_updates["q5_agent_trust_status"] = authorization_baseline.get("agent_trust_status", {})

    tenant_scope = context_updates.get("tenant_scope")
    contact_policy = context_updates.get("contact_policy")
    agent_trust_policy = context_updates.get("agent_trust_policy")
    validated_policy_sources = sum(
        1
        for payload in (tenant_scope, contact_policy, agent_trust_policy)
        if payload not in (None, {}, [], "")
    )
    if not (q4_profile and validated_policy_sources >= 3):
        raise HTTPException(status_code=409, detail="Q5 policy module retry cannot save incomplete authorization evidence")

    existing_diagnosis = deepcopy(context_updates.get("q5_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_tenant_scope_validation",
        status="completed",
        error_code="",
        error_message="",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_contact_policy_validation",
        status="completed",
        error_code="",
        error_message="",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_agent_trust_validation",
        status="completed",
        error_code="",
        error_message="",
    )

    authenticity_status = "completed"
    existing_diagnosis["authenticity_status"] = authenticity_status
    existing_diagnosis["diagnosis_code"] = "completed"
    existing_diagnosis["diagnosis_message"] = "Q5 policy sources were refreshed and authorization evidence is complete."
    existing_diagnosis["module_runs"] = module_runs
    existing_diagnosis["recovery_plan"] = {
        **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
        "actions": merge_q_module_recovery_actions("q5", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
    }
    context_updates["q5_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q5",
        {"context_updates": context_updates},
        refresh_reason=f"question_module_retry:q5:{module_id}",
    )
    return f"single_nine_question_module_retried:q5:{module_id}"


async def retry_q6_redline_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    functional_context: dict[str, Any],
    plugin_service: Any,
    functional_executor: Any,
) -> str:
    snapshot = snapshot_map.get("q6")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q6 snapshot missing; cannot retry module")
    if plugin_service is None:
        raise HTTPException(status_code=503, detail="plugin_service unavailable; cannot retry q6_redline_hint_chain")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    functional_inputs = functional_executor(
        plugin_service,
        NINE_QUESTION_Q6,
        default_parameters=functional_context,
        trace_id=str(snapshot.get("trace_id") or "q6:module-retry"),
        originator_id="nq-baseline",
        caller_plugin_id=NINE_QUESTION_Q6,
    )
    plugin_runs: list[dict[str, Any]] = []
    global_constraints: list[dict[str, Any]] = []
    redline_hints: list[Any] = []
    for item in functional_inputs:
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or NINE_QUESTION_Q6),
                "expected": True,
                "attempted": True,
                "status": "completed" if item.get("status") == "done" else "failed",
                "error_code": "" if item.get("status") == "done" else "redline_plugin_failed",
                "error_message": "" if item.get("status") == "done" else str(item.get("error") or "redline plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if item.get("status") != "done":
            raise HTTPException(status_code=409, detail="Q6 redline module retry cannot save failed functional redline outputs")
        result = item.get("result")
        if not isinstance(result, (dict, list)):
            raise HTTPException(status_code=409, detail="Q6 redline module retry cannot save invalid functional redline outputs")
        if isinstance(result, dict):
            is_redline_pack = result.get("pack_type") == "redline_pack"
            has_constraints = "non_bypassable_constraints" in result
            has_redline_hints = is_redline_pack or any(
                key in result
                for key in (
                    "zone",
                    "forbidden_actions",
                    "absolute_red_lines",
                    "performance_tradeoff_bans",
                    "prohibited_strategies",
                    "contamination_risks",
                )
            )
            if is_redline_pack or has_constraints:
                global_constraints.append(result)
            if has_redline_hints:
                redline_hints.append(result)
            if not (is_redline_pack or has_constraints or has_redline_hints):
                raise HTTPException(status_code=409, detail="Q6 redline module retry cannot save invalid functional redline outputs")
        else:
            redline_hints.extend(result)

    normalized_global_constraints = normalize_redline_inputs(global_constraints)
    normalized_redline_hints = normalize_redline_inputs(redline_hints)
    if not normalized_global_constraints or not normalized_redline_hints:
        raise HTTPException(status_code=409, detail="Q6 redline module retry cannot save incomplete redline evidence")
    forbidden_zone_baseline = derive_forbidden_zone_baseline(
        functional_context,
        normalized_global_constraints,
        normalized_redline_hints,
    )
    context_updates["q6_global_constraints"] = normalized_global_constraints
    context_updates["q6_redline_hints"] = normalized_redline_hints
    context_updates["q6_forbidden_zone_baseline"] = forbidden_zone_baseline

    existing_diagnosis = deepcopy(context_updates.get("q6_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q6_constraint_source_validation",
        status="completed",
        error_code="",
        error_message="",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q6_redline_hint_chain",
        status="completed",
        error_code="",
        error_message="",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q6_risk_assessment",
        status="completed",
        error_code="",
        error_message="",
    )

    existing_diagnosis["authenticity_status"] = "completed"
    existing_diagnosis["diagnosis_code"] = "redline_inputs_refreshed"
    existing_diagnosis["diagnosis_message"] = (
        "Q6 redline inputs were refreshed from real module outputs. Current forbidden-zone inference remains the last committed LLM output until Q6 is rerun."
    )
    existing_diagnosis["module_runs"] = module_runs
    existing_diagnosis["plugin_runs"] = plugin_runs
    existing_diagnosis["recovery_plan"] = {
        **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
        "actions": merge_q_module_recovery_actions("q6", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
    }
    context_updates["q6_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q6",
        {"context_updates": context_updates},
        refresh_reason="question_module_retry:q6:q6_redline_hint_chain",
    )
    return "single_nine_question_module_retried:q6:q6_redline_hint_chain"


async def retry_q7_redline_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    functional_context: dict[str, Any],
    plugin_service: Any,
    functional_executor: Any,
) -> str:
    snapshot = snapshot_map.get("q7")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q7 snapshot missing; cannot retry module")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    identity_kernel = functional_context.get("identity_kernel_snapshot") or functional_context.get("identity_kernel") or {}
    q5_profile = functional_context.get("q5_authorization_boundary_profile") or {}
    q5_permission_boundary = functional_context.get("q5_permission_boundary") or {}
    q6_profile = functional_context.get("q6_forbidden_zone_profile") or {}
    safety_rejection_history = context_updates.get("q7_rejected_operation_records") or functional_context.get("safety_rejection_history") or []
    procedural_memory_constraints = functional_context.get("procedural_memory_constraints") or context_updates.get("procedural_memory_constraints") or []
    if not identity_kernel:
        raise HTTPException(status_code=409, detail="Q7 red-line module retry cannot save missing identity kernel")
    if not q5_profile and not q5_permission_boundary:
        raise HTTPException(status_code=409, detail="Q7 red-line module retry cannot save missing Q5 boundary")
    red_line_baseline = derive_red_line_assessment_baseline(
        identity_kernel=identity_kernel if isinstance(identity_kernel, dict) else {},
        q5_profile=q5_profile if isinstance(q5_profile, dict) else {},
        q5_permission_boundary=q5_permission_boundary if isinstance(q5_permission_boundary, dict) else {},
        q6_profile=q6_profile if isinstance(q6_profile, dict) else {},
        safety_rejection_history=[str(item) for item in safety_rejection_history if str(item).strip()] if isinstance(safety_rejection_history, list) else [],
        procedural_memory_constraints=[str(item) for item in procedural_memory_constraints if str(item).strip()] if isinstance(procedural_memory_constraints, list) else [],
    )
    context_updates["q7_red_line_baseline"] = red_line_baseline
    context_updates["q7_non_bypassable_constraints"] = red_line_baseline.get("non_bypassable_constraints", [])
    context_updates["q7_absolute_red_lines"] = red_line_baseline.get("non_bypassable_constraints", [])
    existing_diagnosis = deepcopy(context_updates.get("q7_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q7_dependency_validation",
        status="completed",
        error_code="",
        error_message="",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q7_red_line_baseline_projection",
        status="completed",
        error_code="",
        error_message="",
    )
    existing_diagnosis["authenticity_status"] = "completed"
    existing_diagnosis["diagnosis_code"] = "red_line_baseline_refreshed"
    existing_diagnosis["diagnosis_message"] = (
        "Q7 red-line baseline evidence was refreshed. Current RedLineAssessment remains the last committed LLM output until Q7 is rerun."
    )
    existing_diagnosis["module_runs"] = module_runs
    existing_diagnosis["plugin_runs"] = existing_diagnosis.get("plugin_runs") or []
    existing_diagnosis["recovery_plan"] = {
        **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
        "actions": merge_q_module_recovery_actions("q7", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
    }
    context_updates["q7_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q7",
        {"context_updates": context_updates},
        refresh_reason="question_module_retry:q7:q7_red_line_baseline_projection",
    )
    return "single_nine_question_module_retried:q7:q7_red_line_baseline_projection"
