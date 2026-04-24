from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from plugins.nine_questions.q2_who_am_i.modules import (
    Q2IdentityInputError,
    build_q2_identity_input_context,
)
from plugins.nine_questions.q3_what_do_i_have.modules import build_q3_runtime_inventory_context
from plugins.nine_questions.q4_what_can_i_do.modules import (
    derive_capability_baseline,
    derive_permission_profile,
    normalize_functional_capabilities,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.modules import (
    derive_agent_trust_status,
    derive_authorization_baseline,
)
from plugins.nine_questions.q6_what_should_i_not_do.modules import (
    derive_forbidden_zone_baseline,
    normalize_redline_inputs,
)
from plugins.nine_questions.q7_what_else_can_i_do.modules import (
    build_q7_baseline_modules,
    derive_alternative_strategy_baseline,
    normalize_functional_alternatives,
)
from plugins.nine_questions.q9_how_should_i_act.modules import (
    normalize_q8_profile,
    normalize_snapshot_dict,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q2, NINE_QUESTION_Q4, NINE_QUESTION_Q6


def merge_q_module_recovery_actions(question_id: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for action in actions:
        if isinstance(action, dict) and str(action.get("action_id") or "").strip():
            merged[str(action["action_id"])] = deepcopy(action)

    if question_id == "q2":
        merged["q2-refresh-identity-inputs"] = {
            "action_id": "q2-refresh-identity-inputs",
            "label": "刷新 Q2 身份输入链",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q2_functional_identity_chain",
            "reason": "仅刷新 Q2 的 Q1 依赖、identity kernel、functional identity inputs；不重跑 LLM。",
            "path": "/api/web/nine-questions/q2/modules/q2_functional_identity_chain/retry",
        }
    elif question_id == "q3":
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
        merged["q7-refresh-functional-alternatives"] = {
            "action_id": "q7-refresh-functional-alternatives",
            "label": "刷新备选策略插件输入",
            "kind": "partial_retry",
            "executable": True,
            "scope": "module",
            "target": "q7_functional_alternative_chain",
            "reason": "仅刷新 Q7 functional alternative inputs 与基线，不重跑 LLM。",
            "path": "/api/web/nine-questions/q7/modules/q7_functional_alternative_chain/retry",
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
    return {
        "q1": dependency_context.get("workspace_domain_inference") or {},
        "q2": dependency_context.get("q2_role_profile") or {},
        "q3": dependency_context.get("q3_resource_evaluation") or dependency_context.get("resource_evaluation") or {},
        "q4": dependency_context.get("q4_capability_boundary_profile") or {},
        "q5": dependency_context.get("q5_authorization_boundary_profile") or dependency_context.get("q5_permission_boundary") or {},
        "q6": dependency_context.get("q6_forbidden_zone_profile") or {},
        "q7": dependency_context.get("q7_alternative_strategy_profile") or {},
        "q8": normalize_q8_profile(q8_raw),
        "summaries": dependency_context.get("nine_questions") or {},
    }


async def retry_q2_identity_input_module(
    *,
    service: Any,
    snapshot_map: dict[str, dict[str, Any]],
    module_id: str,
    dependency_context: dict[str, Any],
    plugin_service: Any,
    functional_executor: Any,
) -> str:
    snapshot = snapshot_map.get("q2")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=404, detail="Q2 snapshot missing; cannot retry identity input module")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    functional_context = {
        **dependency_context,
        **context_updates,
        "trace_id": str(snapshot.get("trace_id") or "q2:module-retry"),
        "session_id": "nq-baseline",
    }
    try:
        identity_context = build_q2_identity_input_context(
            functional_context,
            plugin_id=NINE_QUESTION_Q2,
            plugin_service=plugin_service,
            functional_executor=functional_executor,
            trace_id=str(snapshot.get("trace_id") or "q2:module-retry"),
            originator_id="nq-baseline",
            caller_plugin_id=NINE_QUESTION_Q2,
        )
    except Q2IdentityInputError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "q2_functional_identity_chain_failed",
                "message": str(exc),
                "module_runs": exc.module_runs,
            },
        ) from exc

    context_updates.update(identity_context["context_updates"])
    workspace_domain_inference = identity_context["workspace_domain_inference"]
    identity_kernel = identity_context["identity_kernel"]
    plugin_runs = identity_context["plugin_runs"]

    existing_diagnosis = deepcopy(context_updates.get("q2_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q2_q1_dependency_validation",
        status="completed" if workspace_domain_inference else "degraded",
        error_code="" if workspace_domain_inference else "q1_context_missing",
        error_message="" if workspace_domain_inference else "Q1 context missing.",
        data={"workspace_domain_inference": workspace_domain_inference, "q1_scene_model": identity_context["q1_scene_model"]},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q2_identity_kernel_validation",
        status="completed" if identity_kernel else "degraded",
        error_code="" if identity_kernel else "identity_kernel_missing",
        error_message="" if identity_kernel else "Identity kernel missing.",
        data={"identity_kernel_snapshot": identity_kernel},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q2_functional_identity_chain",
        status="completed" if plugin_service is not None else "missing",
        error_code="" if plugin_service is not None else "plugin_service_missing",
        error_message="" if plugin_service is not None else "Functional identity chain not started.",
        data={"functional_identity_inputs": identity_context["functional_inputs"], "plugin_runs": plugin_runs},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q2_role_reasoning_projection",
        status="degraded",
        error_code="role_reasoning_not_rerun",
        error_message="Q2 identity inputs were refreshed without rerunning LLM role reasoning.",
    )
    existing_diagnosis.update(
        {
            "authenticity_status": "degraded",
            "diagnosis_code": "identity_inputs_refreshed",
            "diagnosis_message": "Q2 identity input modules were refreshed. Role reasoning remains the last committed projection until Q2 is rerun.",
            "used_fallback": True,
            "upstream_degraded": not bool(workspace_domain_inference),
            "module_runs": module_runs,
            "plugin_runs": plugin_runs,
            "recovery_plan": {
                **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
                "actions": merge_q_module_recovery_actions("q2", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
            },
        }
    )
    context_updates["q2_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q2",
        {"context_updates": context_updates},
        refresh_reason=f"question_module_retry:q2:{module_id}",
    )
    return f"single_nine_question_module_retried:q2:{module_id}"


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
    for run in inventory_context["module_runs"]:
        if not isinstance(run, dict):
            continue
        module_runs = upsert_module_run(
            module_runs,
            module_id=str(run.get("module_id") or ""),
            status=str(run.get("status") or "missing"),
            error_code=str(run.get("error_code") or ""),
            error_message=str(run.get("error_message") or ""),
            data=run.get("data") if isinstance(run.get("data"), dict) else None,
        )
    existing_diagnosis.update(
        {
            "authenticity_status": "degraded",
            "diagnosis_code": "runtime_inventory_refreshed",
            "diagnosis_message": "Q3 runtime inventory modules were refreshed. Resource inference remains the last committed projection until Q3 is rerun.",
            "used_fallback": True,
            "upstream_degraded": False,
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

    plugin_runs: list[dict[str, Any]] = []
    functional_postures_raw: list[dict[str, Any]] = []
    if plugin_service is not None:
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
                continue
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
            if done:
                functional_postures_raw.append({"plugin_id": item.get("plugin_id"), "result": item.get("result")})

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

    has_q8_basis = bool(question_snapshot.get("q8"))
    has_self_model = bool(self_model)
    has_reasoning_budget = bool(reasoning_budget)
    existing_diagnosis = deepcopy(context_updates.get("q9_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_q1_q8_validation",
        status="completed" if has_q8_basis else "missing",
        error_code="" if has_q8_basis else "q8_basis_missing",
        error_message="" if has_q8_basis else "Q8 objective basis is missing.",
        data={"q1_q8_snapshot": question_snapshot},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_self_model_source_validation",
        status="completed" if has_self_model else "degraded",
        error_code="" if has_self_model else "self_model_missing",
        error_message="" if has_self_model else "Self-model is missing or snapshot-only.",
        data=self_model,
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_reasoning_budget_source_validation",
        status="completed" if has_reasoning_budget else "degraded",
        error_code="" if has_reasoning_budget else "reasoning_budget_missing",
        error_message="" if has_reasoning_budget else "Reasoning budget is missing or default-only.",
        data=reasoning_budget,
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_functional_posture_chain",
        status="completed" if plugin_runs else "missing",
        error_code="" if plugin_runs else "functional_posture_missing",
        error_message="" if plugin_runs else "No posture plugins executed.",
        data={"functional_postures": normalized_functional_postures, "plugin_runs": plugin_runs},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q9_posture_control_projection",
        status="degraded",
        error_code="posture_projection_not_rerun",
        error_message="Q9 posture inputs were refreshed without rerunning LLM posture projection.",
    )
    existing_diagnosis.update(
        {
            "authenticity_status": "degraded",
            "diagnosis_code": "posture_inputs_refreshed",
            "diagnosis_message": "Q9 posture input modules were refreshed. Posture projection remains the last committed result until Q9 is rerun.",
            "used_fallback": True,
            "upstream_degraded": not has_q8_basis,
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
    q3_inventory = functional_context.get("q3_unified_asset_inventory") or {}
    q3_inventory = q3_inventory if isinstance(q3_inventory, dict) else {}
    exec_domains = list(q3_inventory.get("available_execution_tools", []) or [])

    plugin_runs: list[dict[str, Any]] = []
    functional_capabilities: list[dict[str, Any]] = []
    if plugin_service is not None:
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
            if item.get("status") == "done":
                functional_capabilities.append(item)
                plugin_id = str(item.get("plugin_id") or "").strip()
                if plugin_id:
                    exec_domains.append(plugin_id)
    exec_domains = list(dict.fromkeys(exec_domains))
    normalized_functional_capabilities = normalize_functional_capabilities(functional_capabilities)
    permission_profile = derive_permission_profile(functional_context, q3_inventory)
    capability_baseline = derive_capability_baseline(
        functional_context,
        q3_inventory,
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
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_inventory_validation",
        status="completed" if q3_inventory else "missing",
        error_code="" if q3_inventory else "q3_inventory_missing",
        error_message="" if q3_inventory else "Q3 inventory is missing.",
        data={"q3_unified_asset_inventory": q3_inventory},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_permission_validation",
        status="completed" if permission_profile else "missing",
        error_code="" if permission_profile else "permission_profile_missing",
        error_message="" if permission_profile else "Permission profile is not available.",
        data=permission_profile if isinstance(permission_profile, dict) else {},
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q4_execution_capability_verification",
        status="completed" if exec_domains else "degraded",
        error_code="" if exec_domains else "execution_domains_missing",
        error_message="" if exec_domains else "No validated execution domains are available.",
        data={"active_execution_domains": exec_domains, "functional_capabilities": normalized_functional_capabilities},
    )
    existing_diagnosis.update(
        {
            "authenticity_status": "degraded",
            "diagnosis_code": "capability_inputs_refreshed",
            "diagnosis_message": "Q4 capability input modules were refreshed. Actionability projection remains the last committed result until Q4 is rerun.",
            "used_fallback": True,
            "upstream_degraded": not bool(q3_inventory),
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
    context_updates["q5_agent_trust_status"] = authorization_baseline.get("agent_trust_status", {}) or derive_agent_trust_status(merged_snapshot_context)

    tenant_scope = context_updates.get("tenant_scope")
    contact_policy = context_updates.get("contact_policy")
    agent_trust_policy = context_updates.get("agent_trust_policy")
    existing_diagnosis = deepcopy(context_updates.get("q5_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_tenant_scope_validation",
        status="completed" if tenant_scope not in (None, {}, [], "") else "missing",
        error_code="" if tenant_scope not in (None, {}, [], "") else "tenant_scope_missing",
        error_message="" if tenant_scope not in (None, {}, [], "") else "Tenant scope is not available.",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_contact_policy_validation",
        status="completed" if contact_policy not in (None, {}, [], "") else "missing",
        error_code="" if contact_policy not in (None, {}, [], "") else "contact_policy_missing",
        error_message="" if contact_policy not in (None, {}, [], "") else "Contact policy is not available.",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_agent_trust_validation",
        status="completed" if agent_trust_policy not in (None, {}, [], "") else "degraded",
        error_code="" if agent_trust_policy not in (None, {}, [], "") else "agent_trust_snapshot_only",
        error_message="" if agent_trust_policy not in (None, {}, [], "") else "Agent trust is inferred from snapshot only.",
    )

    validated_policy_sources = sum(
        1
        for payload in (tenant_scope, contact_policy, agent_trust_policy)
        if payload not in (None, {}, [], "")
    )
    authenticity_status = "completed" if q4_profile and validated_policy_sources >= 2 else "degraded"
    module_runs = upsert_module_run(
        module_runs,
        module_id="q5_authorization_decision_projection",
        status="completed" if authenticity_status == "completed" else "degraded",
        error_code="" if authenticity_status == "completed" else "authorization_projection_degraded",
        error_message="" if authenticity_status == "completed" else "Authorization actions still lack enough validated policy sources.",
    )
    existing_diagnosis["authenticity_status"] = authenticity_status
    existing_diagnosis["diagnosis_code"] = "completed" if authenticity_status == "completed" else "authorization_boundary_degraded"
    existing_diagnosis["diagnosis_message"] = (
        "Q5 policy sources were refreshed and authorization evidence is now complete."
        if authenticity_status == "completed"
        else "Q5 policy sources were refreshed, but authorization evidence is still incomplete."
    )
    existing_diagnosis["used_fallback"] = authenticity_status != "completed"
    existing_diagnosis["upstream_degraded"] = not bool(q4_profile)
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
            continue
        result = item.get("result")
        if not isinstance(result, (dict, list)):
            continue
        if isinstance(result, dict):
            if result.get("pack_type") == "redline_pack" or "non_bypassable_constraints" in result:
                global_constraints.append(result)
            elif "zone" in result or "forbidden_actions" in result:
                redline_hints.append(result)
        else:
            redline_hints.extend(result)

    normalized_global_constraints = normalize_redline_inputs(global_constraints)
    normalized_redline_hints = normalize_redline_inputs(redline_hints)
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
        status="completed" if normalized_global_constraints else "degraded",
        error_code="" if normalized_global_constraints else "constraint_snapshot_only",
        error_message="" if normalized_global_constraints else "Global constraints were not validated from live plugin sources.",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q6_redline_hint_chain",
        status="completed" if normalized_redline_hints else "missing",
        error_code="" if normalized_redline_hints else "redline_hint_missing",
        error_message="" if normalized_redline_hints else "No live redline hints were produced.",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q6_risk_assessment",
        status="completed" if normalized_global_constraints or normalized_redline_hints else "degraded",
        error_code="" if normalized_global_constraints or normalized_redline_hints else "dynamic_risk_unverified",
        error_message="" if normalized_global_constraints or normalized_redline_hints else "Dynamic risk assessment is inferred from baseline only.",
    )

    existing_diagnosis["authenticity_status"] = "degraded"
    existing_diagnosis["diagnosis_code"] = "forbidden_zone_degraded"
    existing_diagnosis["diagnosis_message"] = (
        "Q6 redline inputs were refreshed. Current forbidden-zone inference remains the last committed projection until Q6 is rerun."
    )
    existing_diagnosis["used_fallback"] = True
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


async def retry_q7_functional_module(
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
    if plugin_service is None:
        raise HTTPException(status_code=503, detail="plugin_service unavailable; cannot retry q7_functional_alternative_chain")

    context_updates = deepcopy(snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {})
    raw_inputs = functional_executor(
        plugin_service,
        "nine_questions.q7",
        default_parameters={"block_context": functional_context},
        trace_id=str(snapshot.get("trace_id") or "q7:module-retry"),
        originator_id="nq-baseline",
        caller_plugin_id="nine_questions.q7",
    )
    plugin_runs: list[dict[str, Any]] = []
    functional_alternatives: list[dict[str, Any]] = []
    for item in raw_inputs:
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or "nine_questions.q7"),
                "expected": True,
                "attempted": True,
                "status": "completed" if item.get("status") == "done" else "failed",
                "error_code": "" if item.get("status") == "done" else "alternative_plugin_failed",
                "error_message": "" if item.get("status") == "done" else str(item.get("error") or "alternative strategy plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if item.get("status") == "done" and isinstance(item.get("result"), dict):
            functional_alternatives.append(item.get("result"))

    normalized_functional_alternatives = normalize_functional_alternatives(functional_alternatives)
    alternative_strategy_baseline = derive_alternative_strategy_baseline(
        functional_context,
        normalized_functional_alternatives,
    )
    q7_module_results = build_q7_baseline_modules(functional_context, normalized_functional_alternatives)
    context_updates["q7_functional_alternatives"] = normalized_functional_alternatives
    context_updates["q7_alternative_strategy_baseline"] = alternative_strategy_baseline
    context_updates["q7_resource_bottlenecks"] = q7_module_results["resource_bottleneck_projection"]["resource_bottlenecks"]
    context_updates["q7_capability_limits"] = q7_module_results["capability_limit_projection"]["capability_limits"]
    context_updates["q7_permission_boundaries"] = q7_module_results["permission_boundary_projection"]["permission_boundaries"]
    context_updates["q7_absolute_red_lines"] = q7_module_results["absolute_redline_projection"]["absolute_red_lines"]

    q4_profile = functional_context.get("q4_capability_boundary_profile") or {}
    q5_profile = functional_context.get("q5_authorization_boundary_profile") or functional_context.get("q5_permission_boundary") or {}
    q6_profile = functional_context.get("q6_forbidden_zone_profile") or {}
    existing_diagnosis = deepcopy(context_updates.get("q7_execution_diagnosis") or {})
    module_runs = existing_diagnosis.get("module_runs")
    module_runs = module_runs if isinstance(module_runs, list) else []
    module_runs = upsert_module_run(
        module_runs,
        module_id="q7_dependency_validation",
        status="completed" if functional_context.get("q3_resource_evaluation") and q4_profile and q5_profile and q6_profile else "degraded",
        error_code="" if functional_context.get("q3_resource_evaluation") and q4_profile and q5_profile and q6_profile else "upstream_dependency_degraded",
        error_message="" if functional_context.get("q3_resource_evaluation") and q4_profile and q5_profile and q6_profile else "One or more upstream profiles are missing or degraded.",
    )
    module_runs = upsert_module_run(
        module_runs,
        module_id="q7_functional_alternative_chain",
        status="completed" if raw_inputs else "missing",
        error_code="" if raw_inputs else "functional_alternative_missing",
        error_message="" if raw_inputs else "No functional alternative plugins executed.",
    )
    existing_diagnosis["authenticity_status"] = "degraded"
    existing_diagnosis["diagnosis_code"] = "alternative_strategy_degraded"
    existing_diagnosis["diagnosis_message"] = (
        "Q7 functional alternative inputs were refreshed. Current alternative projection remains the last committed result until Q7 is rerun."
    )
    existing_diagnosis["used_fallback"] = True
    existing_diagnosis["upstream_degraded"] = not bool(q4_profile and q5_profile and q6_profile)
    existing_diagnosis["module_runs"] = module_runs
    existing_diagnosis["plugin_runs"] = plugin_runs
    existing_diagnosis["recovery_plan"] = {
        **deepcopy(existing_diagnosis.get("recovery_plan") or {}),
        "actions": merge_q_module_recovery_actions("q7", list((existing_diagnosis.get("recovery_plan") or {}).get("actions") or [])),
    }
    context_updates["q7_execution_diagnosis"] = existing_diagnosis

    await service.persist_question_snapshot_patch(
        "q7",
        {"context_updates": context_updates},
        refresh_reason="question_module_retry:q7:q7_functional_alternative_chain",
    )
    return "single_nine_question_module_retried:q7:q7_functional_alternative_chain"
