from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    get_authoritative_question_snapshot,
    merge_authoritative_question_payload,
    persist_question_module_output,
    start_module_run,
)

logger = logging.getLogger(__name__)


_CONSTRAINT_LABELS = {
    "NO_FAKE_RUNTIME_STATE": "禁止伪造运行态事实或虚构系统状态",
    "NO_SKIP_AUDIT": "禁止跳过审计记录、证据链和可追溯性要求",
    "NO_UNAUTHORIZED_WRITE_ACTION": "禁止未授权写入、修改或执行会产生副作用的动作",
}


class Q2IdentityInputError(RuntimeError):
    def __init__(self, message: str, *, context_updates: dict[str, Any], module_runs: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.context_updates = context_updates
        self.module_runs = module_runs


def coerce_string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def normalize_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def coerce_risk_weight(
    raw_value: object,
    *,
    fallback: float,
    log_message: str,
    extra: dict[str, Any] | None = None,
) -> float:
    try:
        return max(0.0, min(1.0, float(raw_value)))
    except Exception:
        # 严禁吞掉 Q2 身份输入模块中的脏风险权重并假装模块正常。
        # 风险权重可回退，但必须打印异常堆栈，否则输入污染会被伪装为成功。
        logger.exception(log_message, extra=extra or {})
        return max(0.0, min(1.0, fallback))


def _build_plugin_run(item: dict[str, Any], *, default_feature_code: str) -> dict[str, Any]:
    done = item.get("status") == "done"
    return {
        "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
        "feature_code": str(item.get("feature_code") or default_feature_code),
        "expected": True,
        "attempted": True,
        "status": "completed" if done else "failed",
        "error_code": "" if done else "identity_plugin_failed",
        "error_message": "" if done else str(item.get("error") or "identity plugin failed"),
        "duration_ms": 0,
        "input_summary": {},
        "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
    }


def _load_q1_context_from_storage(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = get_authoritative_question_snapshot(context, "q1")
    return merge_authoritative_question_payload(snapshot)


def build_q2_identity_input_context(
    context: dict[str, Any],
    *,
    plugin_id: str,
    plugin_service: Any,
    functional_executor: Any | None,
    trace_id: str,
    originator_id: str,
    caller_plugin_id: str,
) -> dict[str, Any]:
    module_runs = bind_module_runs(context, "q2")
    q1_dependency_run = start_module_run(
        module_runs,
        "q2_q1_dependency_validation",
        source="plugins.nine_questions.q2",
    )

    q1_storage_context = _load_q1_context_from_storage(context)
    workspace_domain_inference = q1_storage_context.get("workspace_domain_inference", {}) or {}
    if not isinstance(workspace_domain_inference, dict):
        workspace_domain_inference = {}
    q1_scene_model = q1_storage_context.get("q1_scene_model", {}) or {}
    if not isinstance(q1_scene_model, dict) or not q1_scene_model:
        q1_scene_model = {
            "primary_domain": workspace_domain_inference.get("primary_domain"),
            "secondary_domains": workspace_domain_inference.get("secondary_domains"),
            "suggested_first_step": workspace_domain_inference.get("suggested_first_step"),
        }
    q1_uncertainty_profile = q1_storage_context.get("q1_uncertainty_profile", {}) or {}
    if not isinstance(q1_uncertainty_profile, dict) or not q1_uncertainty_profile:
        confidence = workspace_domain_inference.get("confidence", 0.5) or 0.5
        q1_uncertainty_profile = {
            "risk_sources": workspace_domain_inference.get("uncertainties"),
            "risk_summary": workspace_domain_inference.get("reasoning_summary"),
            "uncertainty_intensity": max(0.0, min(1.0, 1.0 - float(confidence))),
        }

    finish_module_run(
        q1_dependency_run,
        status="completed" if workspace_domain_inference else "degraded",
        error_code="" if workspace_domain_inference else "q1_context_missing",
        error_message="" if workspace_domain_inference else "Q1 context missing.",
    )
    persist_question_module_output(
        context,
        question_id="q2",
        module_id="q2_q1_dependency_validation",
        payload={
            "workspace_domain_inference": workspace_domain_inference,
            "q1_scene_model": q1_scene_model,
            "q1_uncertainty_profile": q1_uncertainty_profile,
        },
        status=str(q1_dependency_run.get("status") or "completed"),
        output_kind="evidence",
    )

    identity_kernel = context.get("identity_kernel_snapshot", {}) or {}
    if not isinstance(identity_kernel, dict):
        identity_kernel = {}
    identity_kernel_run = start_module_run(
        module_runs,
        "q2_identity_kernel_validation",
        source="plugins.nine_questions.q2",
    )
    role_payload = dict(identity_kernel)
    if "identity_role" not in role_payload and "role_name" in context:
        role_payload["identity_role"] = context.get("role_name")
    if "mission" not in role_payload and "mission" in context:
        role_payload["mission"] = context.get("mission")
    if "core_values" not in role_payload and "core_values" in context:
        role_payload["core_values"] = context.get("core_values")

    constraint_payload: dict[str, Any] = {
        "non_bypassable_constraints": identity_kernel.get("non_bypassable_constraints", []) or []
    }
    finish_module_run(
        identity_kernel_run,
        status="completed" if identity_kernel else "degraded",
        error_code="" if identity_kernel else "identity_kernel_missing",
        error_message="" if identity_kernel else "Identity kernel missing.",
    )
    persist_question_module_output(
        context,
        question_id="q2",
        module_id="q2_identity_kernel_validation",
        payload={"identity_kernel": identity_kernel},
        status=str(identity_kernel_run.get("status") or "completed"),
        output_kind="evidence",
    )
    intensity = q1_uncertainty_profile.get("uncertainty_intensity", 0.5)
    risk_weight = coerce_risk_weight(
        intensity,
        fallback=0.5,
        log_message="Q2 fell back to default risk weight because uncertainty_intensity is invalid",
        extra={
            "source_module": "plugins.nine_questions.q2_who_am_i.modules.identity",
            "uncertainty_intensity": intensity,
        },
    )
    functional_inputs: list[dict[str, Any]] = []
    plugin_runs: list[dict[str, Any]] = []
    functional_chain_run = start_module_run(
        module_runs,
        "q2_functional_identity_chain",
        source="plugins.nine_questions.q2",
    )

    if plugin_service is not None and functional_executor is not None:
        try:
            functional_inputs = functional_executor(
                plugin_service,
                plugin_id,
                default_parameters=dict(context),
                trace_id=trace_id,
                originator_id=originator_id,
                caller_plugin_id=caller_plugin_id,
            )
        except Exception as exc:
            # 严禁吞掉 Q2 functional identity chain 异常然后继续伪装“只是缺少身份输入”。
            # 这里抛带上下文的模块异常，由调用方生成 partial_failed 或 HTTP 失败，不能静默成功。
            logger.exception("Q2 functional identity chain failed")
            fail_module_run(
                functional_chain_run,
                error_code="q2_functional_identity_chain_failed",
                error_message=str(exc),
            )
            partial_updates = {
                "workspace_domain_inference": workspace_domain_inference,
                "q1_scene_model": q1_scene_model,
                "q1_uncertainty_profile": q1_uncertainty_profile,
                "identity_kernel_snapshot": identity_kernel,
            }
            failed_module_runs = bind_module_runs(context, "q2")
            raise Q2IdentityInputError(
                str(exc),
                context_updates=partial_updates,
                module_runs=list(failed_module_runs),
            ) from exc
        for item in functional_inputs:
            if not isinstance(item, dict):
                continue
            plugin_runs.append(_build_plugin_run(item, default_feature_code=plugin_id))
            if item.get("status") != "done":
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                if isinstance(result, (int, float)):
                    risk_weight = max(0.0, min(1.0, float(result)))
                continue
            if "risk_weight" in result:
                risk_weight = coerce_risk_weight(
                    result["risk_weight"],
                    fallback=risk_weight,
                    log_message="Q2 ignored invalid functional risk weight",
                    extra={
                        "source_module": "plugins.nine_questions.q2_who_am_i.modules.identity",
                        "raw_weight": result["risk_weight"],
                    },
                )
            pack_type = str(result.get("pack_type") or "")
            payload = result.get("role_pack") if isinstance(result.get("role_pack"), dict) else result
            if not isinstance(payload, dict):
                continue
            if pack_type in ("role_pack", "posture_pack") or "identity_role" in payload:
                role_payload.update(payload)
            elif pack_type == "constraint_pack" or "non_bypassable_constraints" in payload:
                constraint_payload = payload
            elif "risk_weight" in result or "weight" in result:
                raw_weight = result.get("risk_weight", result.get("weight"))
                risk_weight = coerce_risk_weight(
                    raw_weight,
                    fallback=risk_weight,
                    log_message="Q2 ignored invalid functional risk weight",
                    extra={
                        "source_module": "plugins.nine_questions.q2_who_am_i.modules.identity",
                        "raw_weight": raw_weight,
                    },
                )
        finish_module_run(functional_chain_run)
    else:
        finish_module_run(
            functional_chain_run,
            status="missing",
            error_code="plugin_service_missing",
            error_message="Functional identity chain not started.",
        )
    persist_question_module_output(
        context,
        question_id="q2",
        module_id="q2_functional_identity_chain",
        payload={"functional_inputs": functional_inputs},
        status=str(functional_chain_run.get("status") or "completed"),
        output_kind="evidence",
    )

    # Reconcile identity kernel after functional chain execution.
    # Real runtime may not pre-seed identity_kernel_snapshot, but functionals can
    # still provide enough role/constraint evidence to build a usable kernel.
    if not isinstance(identity_kernel, dict):
        identity_kernel = {}
    if not identity_kernel:
        normalized_role_for_kernel = normalize_dict(role_payload)
        normalized_constraint_for_kernel = normalize_dict(constraint_payload)
        synthesized_constraints = coerce_string_items(
            normalized_constraint_for_kernel.get("non_bypassable_constraints")
        )
        synthesized_identity_role = str(
            normalized_role_for_kernel.get("identity_role")
            or normalized_role_for_kernel.get("active_role_default")
            or workspace_domain_inference.get("primary_domain")
            or ""
        ).strip()
        synthesized_mission = str(
            normalized_role_for_kernel.get("mission")
            or workspace_domain_inference.get("reasoning_summary")
            or ""
        ).strip()
        synthesized_core_values = coerce_string_items(normalized_role_for_kernel.get("core_values"))

        synthesized_kernel: dict[str, Any] = {}
        if synthesized_identity_role:
            synthesized_kernel["identity_role"] = synthesized_identity_role
        if synthesized_mission:
            synthesized_kernel["mission"] = synthesized_mission
        if synthesized_core_values:
            synthesized_kernel["core_values"] = synthesized_core_values
        if synthesized_constraints:
            synthesized_kernel["non_bypassable_constraints"] = synthesized_constraints

        if synthesized_kernel:
            identity_kernel = synthesized_kernel
            finish_module_run(
                identity_kernel_run,
                status="completed",
                used_fallback=True,
            )
            persist_question_module_output(
                context,
                question_id="q2",
                module_id="q2_identity_kernel_validation",
                payload={
                    "identity_kernel": identity_kernel,
                    "source": "functional_chain_derivation",
                },
                status=str(identity_kernel_run.get("status") or "completed"),
                output_kind="evidence",
            )

    normalized_role_payload = normalize_dict(role_payload)
    normalized_constraint_payload = normalize_dict(constraint_payload)
    normalized_manual_overrides = normalize_dict(context.get("manual_role_overrides", {}))
    q2_identity_audit = {
        "risk_weight": risk_weight,
        "role_payload_keys": sorted(normalized_role_payload.keys()),
        "constraint_count": len(coerce_string_items(normalized_constraint_payload.get("non_bypassable_constraints"))),
        "manual_override_keys": sorted(normalized_manual_overrides.keys()),
        "functional_input_count": len(functional_inputs),
    }
    context_updates = {
        "workspace_domain_inference": workspace_domain_inference,
        "q1_scene_model": q1_scene_model,
        "q1_uncertainty_profile": q1_uncertainty_profile,
        "identity_kernel_snapshot": identity_kernel,
        "manual_role_overrides": normalized_manual_overrides,
        "q2_role_payload": normalized_role_payload,
        "q2_constraint_payload": normalized_constraint_payload,
        "q2_risk_weight": risk_weight,
        "q2_risk_preference": {
            "base_weight": risk_weight,
            "posture_label": "conservative" if risk_weight > 0.6 else "aggressive" if risk_weight < 0.4 else "balanced",
            "reasoning": f"Derived from Q1 uncertainty intensity ({risk_weight:.2f}).",
            "impact_on_decision": "Preference applied to role inference boundaries.",
        },
        "q2_identity_audit": q2_identity_audit,
        "q2_functional_identity_inputs": functional_inputs,
    }
    return {
        "workspace_domain_inference": workspace_domain_inference,
        "q1_scene_model": q1_scene_model,
        "q1_uncertainty_profile": q1_uncertainty_profile,
        "identity_kernel": identity_kernel,
        "role_payload": role_payload,
        "constraint_payload": constraint_payload,
        "risk_weight": risk_weight,
        "functional_inputs": functional_inputs,
        "plugin_runs": plugin_runs,
        "normalized_role_payload": normalized_role_payload,
        "normalized_constraint_payload": normalized_constraint_payload,
        "normalized_manual_overrides": normalized_manual_overrides,
        "q2_identity_audit": q2_identity_audit,
        "context_updates": context_updates,
        "module_runs": list(module_runs),
    }


def normalize_q2_inference_payload(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw

    normalized = dict(raw)
    mission_boundary = normalized.get("mission_boundary")
    if not isinstance(mission_boundary, dict):
        return normalized

    mission_boundary_normalized = dict(mission_boundary)
    for key in ("priority_duties", "continuity_boundaries"):
        if key in mission_boundary_normalized:
            mission_boundary_normalized[key] = coerce_string_items(mission_boundary_normalized.get(key))
    normalized["mission_boundary"] = mission_boundary_normalized
    return normalized


def safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): json_compatible(child)
            for key, child in value.items()
            if isinstance(key, (str, int, float, bool))
        }
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return None


def serialize_role_payload(role_payload: dict[str, Any]) -> str:
    if not isinstance(role_payload, dict) or not role_payload:
        return "(empty)"
    lines: list[str] = []
    identity_role = str(role_payload.get("identity_role") or "").strip()
    if identity_role:
        lines.append(f"- 主体身份角色: {identity_role}")
    active_role_default = str(role_payload.get("active_role_default") or "").strip()
    if active_role_default:
        lines.append(f"- 默认活跃角色: {active_role_default}")
    mapping = role_payload.get("task_role_mapping")
    if isinstance(mapping, dict) and mapping:
        lines.append("- 任务到角色映射:")
        for key, value in mapping.items():
            lines.append(f"  - 任务 {key} -> 角色 {value}")
    return "\n".join(lines) or "(empty)"


def serialize_constraint_payload(constraint_payload: dict[str, Any]) -> str:
    if not isinstance(constraint_payload, dict) or not constraint_payload:
        return "(empty)"
    constraints = constraint_payload.get("non_bypassable_constraints")
    if isinstance(constraints, list) and constraints:
        lines: list[str] = []
        for item in constraints:
            text = str(item).strip()
            if not text:
                continue
            lines.append(f"- 严格约束: {_CONSTRAINT_LABELS.get(text, text)}")
        return "\n".join(lines) or "(empty)"
    return "(empty)"
