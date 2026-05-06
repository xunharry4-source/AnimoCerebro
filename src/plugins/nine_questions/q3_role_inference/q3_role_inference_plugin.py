from __future__ import annotations

import logging
from copy import deepcopy
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_llm_output_from_table as load_q2_external_llm_output_from_table,
)
from plugins.nine_questions.q1_where_am_i.llm_output_table import (
    load_llm_output_from_table as load_q1_llm_output_from_table,
)
from plugins.nine_questions.q3_role_inference.llm_prompt import build_q3_role_llm_request
from plugins.nine_questions.q3_role_inference.models import (
    Q3WhoAmIInference,
)
from plugins.nine_questions.q3_role_inference.modules import (
    json_safe_payload,
    safe_provider_plugin_id,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    build_caller_context,
    fail_module_run,
    finish_module_run,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
    run_audit_integration,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q3
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)

QUESTION_REF = "我是谁"
MAX_Q3_LLM_ATTEMPTS = 3
Q3_ROLE_REQUIRED_TOP_LEVEL_KEYS = {"Q3InferenceResult"}
Q3_INFERENCE_RESULT_KEYS = {"RoleProfile", "MissionContinuityBoundary"}
Q3_ROLE_PROFILE_KEYS = {
    "identity_role",
    "active_role",
    "inferred_reference_role",
    "role_alignment_gap",
    "task_role",
}
Q3_MISSION_BOUNDARY_KEYS = {
    "current_mission",
    "priority_duties",
    "continuity_boundaries",
}
Q3_Q2_ROLE_FORBIDDEN_ASSET_KEYS = {
    "available_cognitive_tools",
    "available_execution_tools",
    "cognitive_tool_registry",
    "execution_domain_registry",
    "execution_tool_rows",
    "execution_tools",
    "functional_assets",
    "functional_plugins",
    "internal_plugin_registry",
    "plugin_runs",
}
Q3_Q2_ROLE_FORBIDDEN_TEXT_TOKENS = {
    "available_execution_tools",
    "functional_assets",
    "functional_plugin_outputs",
    "internal_functional_plugins",
}
Q3_Q2_TOOL_ASSET_FIELDS = {
    "asset_name",
    "description",
    "source",
    "plugin_category",
    "trust_level",
    "validity",
}

def _validate_non_empty_string_list(payload: dict[str, Any], key: str, issues: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        issues.append(f"{key} 必须是非空 string[]。")
        return
    if any(not isinstance(item, str) or not item.strip() for item in value):
        issues.append(f"{key} 中必须只包含非空字符串。")


def _coerce_string_items(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates: list[object] = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = [value]
    items: list[str] = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _get_identity_kernel_role(identity_kernel: dict[str, Any]) -> str:
    if not isinstance(identity_kernel, dict):
        return ""
    for key in ("identity_role", "role_name", "role"):
        value = str(identity_kernel.get(key) or "").strip()
        if value:
            return value
    return ""


def _sanitize_identity_kernel_for_role_prompt(identity_kernel: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(identity_kernel, dict):
        return {}
    # Q3 锁定契约要求 identity_role 必须来源于 Identity_Kernel，
    # 但最终输出应抽象为 AI 系统本体级身份标记；禁止隐藏身份内核字段导致 LLM 无源可追。
    return {
        str(key): deepcopy(value)
        for key, value in identity_kernel.items()
        if value not in (None, "", [], {})
    }


def _normalize_role_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def _same_role_text(left: object, right: object) -> bool:
    left_text = _normalize_role_text(left)
    right_text = _normalize_role_text(right)
    return bool(left_text and right_text and left_text == right_text)


def _role_is_identity_anchor(role: object, identity_kernel_role: str) -> bool:
    role_text = _normalize_role_text(role)
    if not role_text:
        return False
    if _same_role_text(role_text, identity_kernel_role):
        return True
    return role_text in {"zentex agent", "zentex core cognitive agent", "animocerebro", "zentex"}


def _flatten_role_signal_text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_role_signal_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_role_signal_text(item) for item in value)
    return str(value or "")


def _derive_reference_role_fallback(q1_llm_output: dict[str, Any], q2_llm_output: dict[str, Any]) -> str:
    text = f"{_flatten_role_signal_text(q1_llm_output)} {_flatten_role_signal_text(q2_llm_output)}".casefold()
    if any(token in text for token in ("linux", "server", "服务器", "运维", "ops", "devops", "nginx")):
        return "系统运维协作角色"
    if any(token in text for token in ("code", "repo", "repository", "software", "python", "typescript", "frontend", "backend", "代码", "工程", "开发")):
        return "软件工程协作角色"
    if any(token in text for token in ("data", "dataset", "analysis", "analytics", "数据", "分析")):
        return "数据分析协作角色"
    return "环境态势与任务协作角色"


def _normalize_manual_role_overrides(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        text_key = str(key)
        if item not in (None, "", [], {}):
            normalized[text_key] = item
    return normalized


def _get_user_configured_active_role(identity_kernel: dict[str, Any], manual_role_overrides: dict[str, Any]) -> str:
    if isinstance(manual_role_overrides, dict):
        override = str(manual_role_overrides.get("active_role_override") or "").strip()
        if override:
            return override
    if not isinstance(identity_kernel, dict):
        return ""
    if identity_kernel.get("active_role_user_locked") is not True:
        return ""
    for key in ("active_role", "active_role_override", "locked_active_role", "user_active_role"):
        role = str(identity_kernel.get(key) or "").strip()
        if role:
            return role
    return ""


def _user_locked_role_label(role: str) -> str:
    role = str(role or "").strip()
    if not role:
        return ""
    if "[User Locked]" in role:
        return role
    return f"{role} [User Locked]"


def _identity_continuity_boundaries(identity_kernel: dict[str, Any], constraint_payload: dict[str, Any]) -> list[str]:
    boundaries: list[str] = []
    if isinstance(constraint_payload, dict):
        boundaries.extend(_coerce_string_items(constraint_payload.get("non_bypassable_constraints")))
    if isinstance(identity_kernel, dict):
        boundaries.extend(_coerce_string_items(identity_kernel.get("non_bypassable_constraints")))
        boundaries.extend(_coerce_string_items(identity_kernel.get("self_binding_constraints")))
        boundaries.extend(_coerce_string_items(identity_kernel.get("core_values")))
        continuity_lock = identity_kernel.get("continuity_lock")
        if isinstance(continuity_lock, dict):
            lock_reason = str(continuity_lock.get("lock_reason") or "").strip()
            locked_fields = _coerce_string_items(continuity_lock.get("locked_fields"))
            if lock_reason:
                boundaries.append(f"continuity_lock: {lock_reason}")
            if locked_fields:
                boundaries.append(f"continuity_locked_fields: {', '.join(locked_fields)}")
    unique: list[str] = []
    for item in boundaries:
        if item and item not in unique:
            unique.append(item)
    return unique


def _merge_continuity_boundaries(
    inference: Q3WhoAmIInference,
    *,
    identity_kernel: dict[str, Any],
    constraint_payload: dict[str, Any],
) -> Q3WhoAmIInference:
    required_boundaries = _identity_continuity_boundaries(identity_kernel, constraint_payload)
    if not required_boundaries:
        return inference
    merged = _coerce_string_items(inference.mission_continuity_boundary.continuity_boundaries)
    for boundary in required_boundaries:
        if boundary not in merged:
            merged.append(boundary)
    if merged == list(inference.mission_continuity_boundary.continuity_boundaries):
        return inference
    mission_continuity_boundary = inference.mission_continuity_boundary.model_copy(update={"continuity_boundaries": merged})
    return _replace_q3_inference_parts(inference, mission_continuity_boundary=mission_continuity_boundary)


def _replace_q3_inference_parts(
    inference: Q3WhoAmIInference,
    *,
    role_profile: Any | None = None,
    mission_continuity_boundary: Any | None = None,
) -> Q3WhoAmIInference:
    updates: dict[str, Any] = {}
    if role_profile is not None:
        updates["RoleProfile"] = role_profile
    if mission_continuity_boundary is not None:
        updates["MissionContinuityBoundary"] = mission_continuity_boundary
    if not updates:
        return inference
    q3_result = inference.Q3InferenceResult.model_copy(update=updates)
    return inference.model_copy(update={"Q3InferenceResult": q3_result})


def _q2_external_asset_items(external_inventory: Any) -> list[Any]:
    if isinstance(external_inventory, list):
        return external_inventory
    if not isinstance(external_inventory, dict):
        return []
    items: list[Any] = []
    available_tools = external_inventory.get("available_external_tools")
    external_agents = external_inventory.get("external_agents")
    if isinstance(available_tools, list):
        items.extend(available_tools)
    if isinstance(external_agents, list):
        items.extend(external_agents)
    return items


def _normalize_q2_external_asset_for_q3(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    asset_name = item.get("asset_name") or item.get("name")
    description = item.get("description") or item.get("capability_summary") or item.get("expertise")
    source = item.get("source") or item.get("asset_type") or item.get("operation_object") or item.get("name")
    plugin_category = item.get("plugin_category") or item.get("asset_type") or "external_tool"
    trust_level = item.get("trust_level") or item.get("credibility_level") or item.get("verification_status")
    validity = item.get("validity") or item.get("verification_status") or item.get("status")
    normalized = {
        "asset_name": asset_name,
        "description": description,
        "source": source,
        "plugin_category": plugin_category,
        "trust_level": trust_level,
        "validity": validity,
    }
    return {
        key: _sanitize_q2_role_asset_input(value)
        for key, value in normalized.items()
        if value not in (None, "", [], {})
    }


def _compact_q2_external_tool_role_input(q2_external_llm_output: dict[str, Any]) -> dict[str, Any]:
    external_inventory: Any = None
    if isinstance(q2_external_llm_output, dict):
        external_inventory = q2_external_llm_output.get("q2_external_tool_asset_inventory")
    sanitized = [
        item
        for item in (
            _normalize_q2_external_asset_for_q3(asset)
            for asset in _q2_external_asset_items(external_inventory)
        )
        if item not in (None, "", [], {})
    ]
    if not sanitized:
        return {}
    return {"q2_external_tool_asset_inventory": sanitized}


def _normalize_q3_role_llm_output(raw: object) -> object:
    # Q3 输出契约禁止兼容旧字段、别名字段、嵌套自动提取或降级修复。
    return raw


def _find_nested_q3_object(value: object, required_keys: set[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if required_keys.issubset(set(value.keys())):
        return value
    for child in value.values():
        if isinstance(child, dict):
            found = _find_nested_q3_object(child, required_keys)
            if found is not None:
                return found
    return None


def _compact_q1_role_input(q1_context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(q1_context, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in ("workspace_domain_inference", "q1_scene_model", "q1_uncertainty_profile"):
        value = q1_context.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    return compact


def _sanitize_q2_role_asset_input(value: Any) -> Any:
    if isinstance(value, list):
        sanitized_items = [_sanitize_q2_role_asset_input(item) for item in value]
        return [item for item in sanitized_items if item not in (None, "", [], {})]
    if isinstance(value, str):
        return _sanitize_q2_role_text(value)
    if not isinstance(value, dict):
        return value
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key)
        if normalized_key in Q3_Q2_ROLE_FORBIDDEN_ASSET_KEYS:
            continue
        if Q3_Q2_TOOL_ASSET_FIELDS.issubset(set(value.keys())) and normalized_key not in Q3_Q2_TOOL_ASSET_FIELDS:
            continue
        sanitized_item = _sanitize_q2_role_asset_input(item)
        if sanitized_item not in (None, "", [], {}):
            sanitized[normalized_key] = sanitized_item
    return sanitized


def _sanitize_q2_role_text(value: str) -> str:
    text = value
    for token in Q3_Q2_ROLE_FORBIDDEN_TEXT_TOKENS:
        text = text.replace(token, "")
    return " ".join(text.split()).strip()


def _validate_q3_role_llm_output(raw: object) -> tuple[Q3WhoAmIInference | None, list[str]]:
    raw = _normalize_q3_role_llm_output(raw)
    if not isinstance(raw, dict):
        return None, ["Q3 LLM 输出必须是 JSON 对象。"]
    issues: list[str] = []
    raw_keys = set(raw.keys())
    missing = sorted(Q3_ROLE_REQUIRED_TOP_LEVEL_KEYS - raw_keys)
    extra = sorted(raw_keys - Q3_ROLE_REQUIRED_TOP_LEVEL_KEYS)
    if missing:
        issues.append(f"缺少 required 顶层字段: {missing}")
    if extra:
        issues.append(f"输出包含未授权顶层字段: {extra}")
    q3_inference_result = raw.get("Q3InferenceResult")
    if not isinstance(q3_inference_result, dict):
        issues.append("Q3InferenceResult 必须是 object。")
        q3_inference_result = {}
    else:
        result_keys = set(q3_inference_result.keys())
        result_missing = sorted(Q3_INFERENCE_RESULT_KEYS - result_keys)
        result_extra = sorted(result_keys - Q3_INFERENCE_RESULT_KEYS)
        if result_missing:
            issues.append(f"Q3InferenceResult 缺少字段: {result_missing}")
        if result_extra:
            issues.append(f"Q3InferenceResult 包含未授权字段: {result_extra}")
    role_profile = q3_inference_result.get("RoleProfile")
    mission_continuity_boundary = q3_inference_result.get("MissionContinuityBoundary")
    if not isinstance(role_profile, dict):
        issues.append("Q3InferenceResult.RoleProfile 必须是 object。")
    else:
        role_keys = set(role_profile.keys())
        role_missing = sorted(Q3_ROLE_PROFILE_KEYS - role_keys)
        role_extra = sorted(role_keys - Q3_ROLE_PROFILE_KEYS)
        if role_missing:
            issues.append(f"Q3InferenceResult.RoleProfile 缺少字段: {role_missing}")
        if role_extra:
            issues.append(f"Q3InferenceResult.RoleProfile 包含未授权字段: {role_extra}")
        for key in Q3_ROLE_PROFILE_KEYS:
            if not isinstance(role_profile.get(key), str) or not role_profile.get(key, "").strip():
                issues.append(f"Q3InferenceResult.RoleProfile.{key} 必须是非空字符串。")
    if not isinstance(mission_continuity_boundary, dict):
        issues.append("Q3InferenceResult.MissionContinuityBoundary 必须是 object。")
    else:
        mission_keys = set(mission_continuity_boundary.keys())
        mission_missing = sorted(Q3_MISSION_BOUNDARY_KEYS - mission_keys)
        mission_extra = sorted(mission_keys - Q3_MISSION_BOUNDARY_KEYS)
        if mission_missing:
            issues.append(f"Q3InferenceResult.MissionContinuityBoundary 缺少字段: {mission_missing}")
        if mission_extra:
            issues.append(f"Q3InferenceResult.MissionContinuityBoundary 包含未授权字段: {mission_extra}")
        if not isinstance(mission_continuity_boundary.get("current_mission"), str) or not mission_continuity_boundary.get("current_mission", "").strip():
            issues.append("Q3InferenceResult.MissionContinuityBoundary.current_mission 必须是非空字符串。")
        _validate_non_empty_string_list(mission_continuity_boundary, "priority_duties", issues)
        _validate_non_empty_string_list(mission_continuity_boundary, "continuity_boundaries", issues)
    if issues:
        return None, issues
    try:
        return Q3WhoAmIInference.model_validate(raw), []
    except Exception as exc:
        return None, [str(exc)]


def _run_q3_role_inference(plugin: "Q3WhatDoIHavePlugin", context: dict[str, Any]) -> CognitiveToolResult:
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    trace_id = str(context.get("trace_id") or f"q3-role-inference:{uuid4().hex}")
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or "unknown-turn")
    decision_id = str(context.get("decision_id") or f"{turn_id}:q3_role_inference")
    module_runs = bind_module_runs(context, "q3")

    upstream_run = start_module_run(
        module_runs,
        "q3_upstream_llm_output_validation",
        source="plugins.nine_questions.q3_role_inference",
    )
    try:
        q1_llm_output = load_q1_llm_output_from_table(db_path=context.get("nine_question_state_db_path"))
        q2_external_llm_output = {
            "q2_external_tool_asset_inventory": load_q2_external_llm_output_from_table(
                db_path=context.get("nine_question_state_db_path"),
            )
        }
        q1_role_input = _compact_q1_role_input(q1_llm_output)
        q2_external_role_input = _compact_q2_external_tool_role_input(q2_external_llm_output)
        workspace_domain_inference = q1_role_input.get("workspace_domain_inference", {})
        q2_external_tool_asset_inventory = q2_external_role_input.get("q2_external_tool_asset_inventory") or {}
        if not isinstance(workspace_domain_inference, dict) or not workspace_domain_inference:
            raise RuntimeError("q3_q1_llm_output_missing_workspace_domain_inference")
        if not isinstance(q2_external_tool_asset_inventory, list) or not q2_external_tool_asset_inventory:
            raise RuntimeError("q3_q2_external_tool_asset_inventory_missing")
        upstream_run["data"] = {
            "q1_source": "plugins.nine_questions.q1_where_am_i.llm_output_table.load_llm_output_from_table",
            "q2_source": "plugins.nine_questions.q2_asset_inventory.llm_output_table.load_external_llm_output_from_table",
            "q1_keys": sorted(q1_role_input.keys()),
            "q2_external_asset_count": len(q2_external_tool_asset_inventory),
        }
        finish_module_run(upstream_run)
        persist_question_module_output(
            context,
            question_id="q3",
            module_id="q3_upstream_llm_output_validation",
            payload=upstream_run.get("data") or {},
            status=str(upstream_run.get("status") or "completed"),
            output_kind="evidence",
        )
    except Exception as exc:
        fail_module_run(
            upstream_run,
            error_code="q3_upstream_llm_output_invalid",
            error_message=str(exc),
        )
        logger.exception("[Q3] upstream LLM output validation failed session=%s trace=%s", session_id, trace_id)
        raise

    identity_kernel = context.get("identity_kernel_snapshot", {}) or {}
    if not isinstance(identity_kernel, dict):
        identity_kernel = {}
    identity_kernel_for_prompt = _sanitize_identity_kernel_for_role_prompt(identity_kernel)
    role_payload = dict(identity_kernel_for_prompt)
    if "mission" not in role_payload and "mission" in context:
        role_payload["mission"] = context.get("mission")
    constraint_payload = {"non_bypassable_constraints": identity_kernel.get("non_bypassable_constraints", []) or []}
    manual_role_overrides = _normalize_manual_role_overrides(
        context.get("manual_role_overrides") or {}
    )
    confidence = workspace_domain_inference.get("confidence", 0.5) or 0.5
    try:
        risk_weight = max(0.0, min(1.0, 1.0 - float(confidence)))
    except (TypeError, ValueError):
        risk_weight = 0.5
    q2_role_input = q2_external_role_input

    llm_request = build_q3_role_llm_request(
        risk_weight=risk_weight,
        q1_llm_output=q1_role_input,
        q2_llm_output=q2_role_input,
        identity_kernel_snapshot=identity_kernel_for_prompt,
        role_payload=role_payload,
        constraint_payload=constraint_payload,
        manual_role_overrides=manual_role_overrides,
    )
    system_prompt = llm_request["system_prompt"]
    prompt = llm_request["prompt"]
    combined_prompt = llm_request["combined_prompt"]
    model_context = llm_request["model_context"]
    caller_context = build_caller_context(
        source_module="q3_role_inference_plugin",
        invocation_phase="nine_question_q3_role_inference",
        question_ref=QUESTION_REF,
        question_driver_refs=["q1_authoritative_llm_output", "q2_authoritative_llm_output"],
        decision_id=decision_id,
        trace_id=trace_id,
    )
    started = perf_counter()
    llm_invocation_attempts: list[dict[str, Any]] = []
    inference: Q3WhoAmIInference | None = None
    q3_computed_role_profile: dict[str, Any] = {}
    role_projection_run = start_module_run(
        module_runs,
        "q3_role_projection",
        source="plugins.nine_questions.q3_role_inference",
    )
    for attempt in range(1, MAX_Q3_LLM_ATTEMPTS + 1):
        request_id = str(uuid4())
        retry_hint = "\n\n上一次 Q3 输出未通过字段级审计。请严格返回 Q3InferenceResult，并包含 RoleProfile 与 MissionContinuityBoundary。" if attempt > 1 else ""
        current_prompt = str(combined_prompt)
        if retry_hint:
            current_prompt = current_prompt.replace(
                "<Q3_RETRY_HINT>\n\n</Q3_RETRY_HINT>",
                f"<Q3_RETRY_HINT>\n{retry_hint.strip()}\n</Q3_RETRY_HINT>",
            )
        attempt_started = perf_counter()
        attempt_payload: dict[str, Any] = {
            "attempt": attempt,
            "request_id": request_id,
            "decision_id": decision_id,
            "question_ref": QUESTION_REF,
            "provider_plugin_id": safe_provider_plugin_id(provider),
            "caller_context": caller_context.model_dump(mode="json"),
            "prompt": current_prompt,
            "system_prompt": system_prompt,
            "context": model_context,
        }
        try:
            raw = provider.generate_json(prompt=current_prompt, context=model_context, caller_context=caller_context)
            attempt_payload["raw_response"] = json_safe_payload(getattr(provider, "last_raw_response", None))
            attempt_payload["token_usage"] = json_safe_payload(getattr(provider, "last_token_usage", None))
            attempt_payload["model"] = json_safe_payload(getattr(provider, "last_model_name", None))
            attempt_payload["result"] = json_safe_payload(raw)
            attempt_payload["elapsed_ms"] = int((perf_counter() - attempt_started) * 1000)
        except Exception as exc:
            attempt_payload.update({"error_type": exc.__class__.__name__, "error_message": str(exc), "elapsed_ms": int((perf_counter() - attempt_started) * 1000)})
            llm_invocation_attempts.append(attempt_payload)
            record_model_invoked(transcript_store, session_id=session_id, turn_id=turn_id, trace_id=trace_id, source="plugins.nine_questions.q3_role_inference", payload=attempt_payload)
            record_model_failed(transcript_store, session_id=session_id, turn_id=turn_id, trace_id=trace_id, source="plugins.nine_questions.q3_role_inference", payload=attempt_payload)
            if attempt >= MAX_Q3_LLM_ATTEMPTS:
                fail_module_run(
                    role_projection_run,
                    error_code="q3_llm_invocation_failed",
                    error_message=str(exc),
                )
                raise RuntimeError("q3_llm_invocation_failed") from exc
            continue
        validated_inference, validation_errors = _validate_q3_role_llm_output(raw)
        if validation_errors or validated_inference is None:
            attempt_payload["validation_error"] = "; ".join(validation_errors)
            llm_invocation_attempts.append(attempt_payload)
            record_model_invoked(transcript_store, session_id=session_id, turn_id=turn_id, trace_id=trace_id, source="plugins.nine_questions.q3_role_inference", payload=attempt_payload)
            record_model_failed(transcript_store, session_id=session_id, turn_id=turn_id, trace_id=trace_id, source="plugins.nine_questions.q3_role_inference", payload=attempt_payload)
            if attempt >= MAX_Q3_LLM_ATTEMPTS:
                fail_module_run(
                    role_projection_run,
                    error_code="q3_output_validation_failed",
                    error_message="; ".join(validation_errors),
                )
                raise RuntimeError("q3_output_validation_failed")
            continue
        inference = validated_inference
        q3_computed_role_profile = inference.role_profile.model_dump(mode="json")
        identity_kernel_role = _get_identity_kernel_role(identity_kernel)
        user_configured_role = _get_user_configured_active_role(identity_kernel, manual_role_overrides)
        inferred_reference_role = str(inference.role_profile.inferred_reference_role or inference.role_profile.task_role).strip()
        if not user_configured_role and _role_is_identity_anchor(inferred_reference_role, identity_kernel_role):
            task_candidate = str(inference.role_profile.task_role or "").strip()
            if task_candidate and not _role_is_identity_anchor(task_candidate, identity_kernel_role):
                inferred_reference_role = task_candidate
            else:
                inferred_reference_role = _derive_reference_role_fallback(q1_role_input, q2_role_input)
        active_role = _user_locked_role_label(user_configured_role) if user_configured_role else inferred_reference_role or str(inference.role_profile.active_role).strip()
        identity_role = str(inference.role_profile.identity_role).strip()
        role_alignment_gap = str(inference.role_profile.role_alignment_gap or "").strip()
        if inferred_reference_role and active_role and inferred_reference_role != active_role:
            if not role_alignment_gap or role_alignment_gap in {"aligned", "无明显偏差"}:
                role_alignment_gap = f"当前 active_role“{active_role}”与系统参考角色“{inferred_reference_role}”不一致；后续必须保留用户角色优先级并在执行中显式处理能力缺口。"
        elif not role_alignment_gap:
            role_alignment_gap = "aligned"
        if not user_configured_role:
            role_alignment_gap = "aligned" if role_alignment_gap in {"", "aligned", "无明显偏差"} else role_alignment_gap
        role_profile_updates = {
            "identity_role": identity_role,
            "active_role": active_role,
            "inferred_reference_role": inferred_reference_role or active_role,
            "role_alignment_gap": role_alignment_gap,
        }
        role_profile = inference.role_profile.model_copy(update=role_profile_updates)
        inference = _replace_q3_inference_parts(inference, role_profile=role_profile)
        if not user_configured_role and identity_kernel_role and active_role and active_role != identity_kernel_role:
            current_mission = str(inference.mission_continuity_boundary.current_mission or "")
            if identity_kernel_role in current_mission:
                mission_continuity_boundary = inference.mission_continuity_boundary.model_copy(
                    update={"current_mission": current_mission.replace(identity_kernel_role, active_role)}
                )
                inference = _replace_q3_inference_parts(inference, mission_continuity_boundary=mission_continuity_boundary)
        inference = _merge_continuity_boundaries(
            inference,
            identity_kernel=identity_kernel,
            constraint_payload=constraint_payload,
        )
        attempt_payload["result"] = json_safe_payload(inference.model_dump(mode="json"))
        llm_invocation_attempts.append(attempt_payload)
        record_model_invoked(transcript_store, session_id=session_id, turn_id=turn_id, trace_id=trace_id, source="plugins.nine_questions.q3_role_inference", payload=attempt_payload)
        break
    if inference is None:
        fail_module_run(
            role_projection_run,
            error_code="q3_output_validation_failed",
            error_message="Q3 LLM did not produce a valid Q3InferenceResult.",
        )
        raise RuntimeError("q3_output_validation_failed")
    role_projection_run["data"] = inference.model_dump(mode="json")
    finish_module_run(role_projection_run)
    persist_question_module_output(
        context,
        question_id="q3",
        module_id="q3_role_projection",
        payload=role_projection_run.get("data") or {},
        status=str(role_projection_run.get("status") or "completed"),
        output_kind="inference",
    )
    latest_model_payload = llm_invocation_attempts[-1] if llm_invocation_attempts else {}
    record_model_completed(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source="plugins.nine_questions.q3_role_inference",
        payload={
            "request_id": latest_model_payload.get("request_id", str(uuid4())),
            "decision_id": decision_id,
            "question_ref": QUESTION_REF,
            "caller_context": caller_context.model_dump(mode="json"),
            "result": inference.model_dump(mode="json"),
            "raw_response": latest_model_payload.get("raw_response"),
            "token_usage": latest_model_payload.get("token_usage"),
            "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            "elapsed_ms": int((perf_counter() - started) * 1000),
            "invocations": llm_invocation_attempts,
        },
    )
    role_profile_payload = inference.role_profile.model_dump(mode="json")
    mission_boundary_payload = inference.mission_continuity_boundary.model_dump(mode="json")
    user_configured_role = _get_user_configured_active_role(identity_kernel, manual_role_overrides)
    q3_role_alignment_judgement = {}
    if user_configured_role:
        aligned = role_profile_payload.get("active_role") == role_profile_payload.get("inferred_reference_role")
        q3_role_alignment_judgement = {
            "user_configured_role": user_configured_role,
            "q3_computed_role_profile": q3_computed_role_profile,
            "final_role_profile": role_profile_payload,
            "aligned": bool(aligned),
            "replacement_allowed": False,
            "analysis": str(role_profile_payload.get("role_alignment_gap") or ""),
        }
    role_summary = f"identity_role={role_profile_payload['identity_role']}; active_role={role_profile_payload['active_role']}; task_role={role_profile_payload['task_role']}"
    llm_trace_payload = _build_q3_llm_trace_payload(
        trace_id=trace_id,
        decision_id=decision_id,
        caller_context=caller_context.model_dump(mode="json"),
        system_prompt=system_prompt,
        prompt=prompt,
        model_context=model_context,
        latest_model_payload=latest_model_payload,
        invocations=llm_invocation_attempts,
        elapsed_ms=int((perf_counter() - started) * 1000),
    )
    result_payload = {
        "q3_role_profile": role_profile_payload,
        "q3_mission_boundary": mission_boundary_payload,
        "q3_role_alignment_judgement": q3_role_alignment_judgement,
    }
    q3_audit_provenance = _build_q3_audit_provenance(
        trace_id=trace_id,
        result_payload=result_payload,
        llm_trace_payload=llm_trace_payload,
    )
    run_audit_integration(
        context,
        question_id="q3",
        module_runs=module_runs,
        summary="Q3 角色推断 LLM 输入、输出、模型调用与结果保存链路已记录。",
        payload=q3_audit_provenance,
    )
    q3_execution_diagnosis = {
        "authenticity_status": "completed",
        "diagnosis_code": "completed",
        "diagnosis_message": "Q3 role inference completed with audit provenance.",
        "module_runs": list(module_runs),
        "upstream_dependencies": [
            {"dependency_id": "q1", "required": True, "status": "completed", "message": "Q1 LLM output loaded through Q1 public method."},
            {"dependency_id": "q2", "required": True, "status": "completed", "message": "Q2 external LLM output loaded through Q2 public method."},
        ],
    }
    return CognitiveToolResult(
        tool_id=plugin.plugin_id,
        summary=role_summary,
        llm_output={
            "Q3InferenceResult": {
                "RoleProfile": role_profile_payload,
                "MissionContinuityBoundary": mission_boundary_payload,
            },
        },
        proposals=[
            {"kind": "role_profile", "question_ref": QUESTION_REF, **role_profile_payload},
            {"kind": "mission_continuity_boundary", **mission_boundary_payload},
        ],
        risks=[{"kind": "continuity_boundaries", "items": mission_boundary_payload.get("continuity_boundaries", [])}],
        context_updates={
            "nine_questions": {QUESTION_REF: role_profile_payload["active_role"]},
            "identity_kernel_snapshot": identity_kernel,
            "manual_role_overrides": manual_role_overrides,
            "q3_risk_weight": risk_weight,
            "q3_role_profile": role_profile_payload,
            "q3_mission_boundary": mission_boundary_payload,
            "q3_role_alignment_judgement": q3_role_alignment_judgement,
            "q3_audit_provenance": q3_audit_provenance,
            "q3_execution_diagnosis": q3_execution_diagnosis,
            "llm_trace_payload": llm_trace_payload,
        },
        llm_trace_payload=llm_trace_payload,
        confidence=0.75,
    )


def _build_q3_llm_trace_payload(
    *,
    trace_id: str,
    decision_id: str,
    caller_context: dict[str, Any],
    system_prompt: str,
    prompt: str,
    model_context: dict[str, Any],
    latest_model_payload: dict[str, Any],
    invocations: list[dict[str, Any]],
    elapsed_ms: int,
) -> dict[str, Any]:
    token_usage = latest_model_payload.get("token_usage")
    token_usage = token_usage if isinstance(token_usage, dict) else {}
    return {
        "request_id": latest_model_payload.get("request_id", str(uuid4())),
        "decision_id": decision_id,
        "question_id": "q3",
        "trace_id": trace_id,
        "provider_name": latest_model_payload.get("provider_plugin_id"),
        "model": latest_model_payload.get("model"),
        "system_prompt": system_prompt,
        "prompt": prompt,
        "source_module": "plugins.nine_questions.q3_role_inference",
        "invocation_phase": "nine_question_q3_role_inference",
        "question_driver_refs": caller_context.get("question_driver_refs") or [],
        "caller_context": caller_context,
        "context_data": model_context,
        "raw_response": latest_model_payload.get("raw_response"),
        "token_usage": token_usage,
        "elapsed_ms": elapsed_ms,
        "invocations": invocations,
        "error_type": latest_model_payload.get("error_type"),
        "error_message": latest_model_payload.get("error_message") or latest_model_payload.get("validation_error"),
    }


def _build_q3_audit_provenance(
    *,
    trace_id: str,
    result_payload: dict[str, Any],
    llm_trace_payload: dict[str, Any],
) -> dict[str, Any]:
    invocations = llm_trace_payload.get("invocations")
    invocations = invocations if isinstance(invocations, list) else []
    return {
        "question_id": "q3",
        "trace_id": trace_id,
        "source_module": "plugins.nine_questions.q3_role_inference",
        "source_of_truth": "nine_question_q3_snapshots.llm_output_json",
        "upstream_sources": {
            "q1": "plugins.nine_questions.q1_where_am_i.llm_output_table.load_llm_output_from_table",
            "q2": "plugins.nine_questions.q2_asset_inventory.llm_output_table.load_external_llm_output_from_table",
        },
        "save_flow": [
            "Q3 LLM output",
            "audit provenance payload",
            "q3 llm_output table payload",
            "service reads q3 table",
            "frontend displays q3 table output",
        ],
        "llm_invocation_count": len(invocations),
        "llm_invocations": invocations,
        "q3_role_profile": result_payload.get("q3_role_profile") or {},
        "q3_mission_boundary": result_payload.get("q3_mission_boundary") or {},
        "q3_role_alignment_judgement": result_payload.get("q3_role_alignment_judgement") or {},
        "token_usage": llm_trace_payload.get("token_usage") if isinstance(llm_trace_payload.get("token_usage"), dict) else {},
    }


class Q3WhatDoIHavePlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q3
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q3"
    display_name: str = "Q3: 我是谁"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q3: 我是谁 (role profile and mission continuity inference)

    Red lines:
    - Must use Live LLM (fail-closed).
    - Must not scan full repo or read raw bodies; only lightweight metadata.
    - Must write prompt/context/response into the trace store with trace_id.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        return _run_q3_role_inference(self, context)

def build_q3_role_inference_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q3,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3WhatDoIHavePlugin:
    return Q3WhatDoIHavePlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q3",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
