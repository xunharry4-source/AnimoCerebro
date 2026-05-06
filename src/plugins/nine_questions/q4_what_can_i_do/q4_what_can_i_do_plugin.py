from __future__ import annotations

import logging
import json
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q4
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q4_what_can_i_do.internal import (
    contains_write_like_action,
    derive_capability_baseline,
    derive_permission_profile,
    merge_with_capability_baseline,
    normalize_functional_capabilities,
)
from plugins.nine_questions.q4_what_can_i_do.internal import (
    load_internal_q2_asset_inventory,
    render_internal_q2_asset_inventory,
)
from plugins.nine_questions.q4_what_can_i_do.external import (
    load_external_q2_asset_inventory,
    render_external_q2_asset_inventory,
)
from plugins.nine_questions.q4_what_can_i_do.models import (
    CapabilityBoundaryProfile,
    Q4WhatCanIDoInference,
)
from plugins.nine_questions.q4_what_can_i_do.llm_prompt import build_q4_llm_request
from plugins.nine_questions.q4_what_can_i_do.llm_output_table import (
    persist_q4_inferred_capabilities,
    persist_q4_llm_io,
)
from plugins.nine_questions.q1_where_am_i.llm_output_table import (
    load_llm_output_from_table as load_q1_llm_output_from_table,
)
from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_llm_output_from_table as load_q3_llm_output_from_table,
)


QUESTION_REF = "我能做什么"

from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
    run_audit_integration,
    run_learning_integration,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_human_readable_block,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)

MAX_Q4_LLM_ATTEMPTS = 3
Q4_ASSESSMENT_REQUIRED_KEYS = {"inferred_capabilities"}
Q4_CAPABILITY_ROOT_KEY_INTERNAL = "CapabilityAssessment"



def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object, *, limit: int | None = None) -> list[str]:
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    normalized = [_normalize_text(item) for item in value]
    normalized = [item for item in normalized if item]
    if limit is not None and limit > 0:
        return normalized[:limit]
    return normalized


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in values:
        text = _normalize_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _dedupe_dict_items(items: object, *, key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = tuple(_normalize_text(item.get(field)).lower() for field in key_fields)
        if not any(key):
            key = tuple(_normalize_text(value).lower() for value in item.values())
        if not any(key) or key in seen:
            continue
        seen.add(key)
        unique.append(dict(item))
    return unique


def _safe_read_list(value: object, default: list[Any] | None = None) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return list(default or [])


def _coerce_inferred_capabilities(
    value: object,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        return [], ["inferred_capabilities 必须是 array。"]

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in value:
        if not isinstance(raw, dict):
            errors.append("inferred_capabilities 中必须是对象，不允许字符串。")
            continue
        name = _normalize_text(raw.get("capability_name"))
        desc = _normalize_text(raw.get("capability_description"))
        source_bundle = raw.get("used_q1_resources_and_q2_capabilities")
        if not isinstance(source_bundle, dict):
            errors.append("inferred_capabilities 中 used_q1_resources_and_q2_capabilities 必须是对象。")
            continue
        q1_resources = _coerce_string_list(source_bundle.get("q1_resources"), limit=64)
        q2_capabilities = _coerce_string_list(source_bundle.get("q2_capabilities"), limit=64)
        if not q1_resources:
            errors.append("inferred_capabilities 中 used_q1_resources_and_q2_capabilities.q1_resources 不能为空。")
        if not q2_capabilities:
            errors.append("inferred_capabilities 中 used_q1_resources_and_q2_capabilities.q2_capabilities 不能为空。")
        if not q1_resources or not q2_capabilities:
            continue
        if not name:
            errors.append("inferred_capabilities 中 capability_name 不能为空。")
            continue
        if not desc:
            errors.append("inferred_capabilities 中 capability_description 不能为空。")
            continue
        items.append(
            {
                "capability_name": name,
                "capability_description": desc,
                "used_q1_resources_and_q2_capabilities": {
                    "q1_resources": q1_resources,
                    "q2_capabilities": q2_capabilities,
                },
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["capability_name"].lower(), item["capability_description"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, errors


def _coerce_inferred_capability_texts(
    items: list[dict[str, Any]] | list[Any],
) -> list[str]:
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = _normalize_text(item.get("capability_name"))
            if name:
                names.append(name)
    return names



def _summarize_tool_handshake(source_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    source_id = _normalize_text(
        payload.get("agent_id")
        or payload.get("id")
        or payload.get("name")
        or payload.get("connector_id")
        or payload.get("server_id")
        or payload.get("command_name")
    )
    if not source_id:
        return {}

    declared_capabilities = _coerce_string_list(payload.get("capabilities"), limit=24)
    if not declared_capabilities and isinstance(payload.get("tools"), list):
        declared_capabilities = [
            _normalize_text(tool.get("name") if isinstance(tool, dict) else str(tool))
            for tool in payload.get("tools", [])
        ]
    if not declared_capabilities and isinstance(payload.get("tools"), dict):
        declared_capabilities = [k for k in payload.get("tools", {}).keys() if k]
    if not declared_capabilities:
        scope_hint = _normalize_text(payload.get("description") or payload.get("function_description"))
        if scope_hint:
            declared_capabilities = [scope_hint]
    if not declared_capabilities:
        declared_capabilities = [f"{source_type}:{source_id}:declared capability"]

    return {
        "source_type": source_type,
        "source_id": source_id,
        "declared_capabilities": declared_capabilities[:24],
    }


def _internal_asset_inventory_from_context(context: dict[str, Any]) -> dict[str, Any]:
    return load_internal_q2_asset_inventory(context)


def _external_asset_inventory_from_context(context: dict[str, Any]) -> dict[str, Any]:
    return load_external_q2_asset_inventory(context)


def _render_q2_internal_asset_inventory(context: dict[str, Any]) -> str:
    return render_internal_q2_asset_inventory(context)


def _render_q2_external_asset_inventory(context: dict[str, Any]) -> str:
    return render_external_q2_asset_inventory(context)


def _render_q3_role_mission(context: dict[str, Any]) -> str:
    return (
        "Q3 角色与使命边界（来自 Q3 LLM 输出）\n"
        f"{json.dumps(json_safe_payload({
            "q3_role_profile": context.get("q3_role_profile") or {},
            "q3_mission_boundary": context.get("q3_mission_boundary") or {},
        }), ensure_ascii=False, indent=2)}"
    )


def _build_preprocessed_evidence(
    context: dict[str, Any],
    *,
    q2_inventory: dict[str, Any],
    q2_internal_tool_asset_inventory: dict[str, Any],
    q2_external_tool_asset_inventory: dict[str, Any],
    permission_profile: dict[str, Any],
) -> dict[str, Any]:
    capability_handshake: list[dict[str, Any]] = []

    for inventory_key, source_type, inventory in (
        ("q2_internal_tool_asset_inventory", "internal_q2_llm_asset", q2_internal_tool_asset_inventory),
        ("q2_external_tool_asset_inventory", "external_q2_llm_asset", q2_external_tool_asset_inventory),
    ):
        for asset_key in (
            "cognitive_and_functional_tools",
            "connected_agents",
            "long_term_memory",
            "strategy_patches",
        ):
            for item in _safe_read_list(inventory.get(asset_key))[:80]:
                if not isinstance(item, dict):
                    continue
                entry = _summarize_tool_handshake(source_type, item)
                if entry:
                    entry["inventory_key"] = inventory_key
                    entry["asset_bucket"] = asset_key
                    capability_handshake.append(entry)

    capability_handshake = _dedupe_dict_items(
        capability_handshake,
        key_fields=("source_type", "source_id", "inventory_key", "asset_bucket"),
    )

    probe_results: list[dict[str, Any]] = []
    module_results = context.get("q3_module_results") or {}
    if isinstance(module_results, dict):
        for module_id, payload in list(module_results.items()):
            if not isinstance(payload, dict):
                continue
            status = _normalize_text(payload.get("status") or payload.get("state"))
            probe_results.append(
                {
                    "module": module_id,
                    "status": status or "completed",
                    "payload_keys": list(payload.keys()),
                }
            )

    functional_capabilities = _safe_read_list(context.get("q4_functional_capabilities"))
    for item in functional_capabilities:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            continue
        for key in (
            "probe_results",
            "probe_result",
            "health_probe",
            "sandbox_probe",
            "thought_sandbox_probe",
        ):
            probe_entry = result.get(key)
            if probe_entry:
                probe_results.append(
                    {
                        "source": _normalize_text(item.get("plugin_id") or item.get("source") or "functional_plugin"),
                        "key": key,
                        "value": probe_entry if isinstance(probe_entry, str) else str(probe_entry),
                    }
                )

    if not probe_results:
        probe_results.append({
            "status": "missing",
            "reason": "当前快照未发现可重放的 Probe/health 记录。",
        })

    references = _dedupe(
        _coerce_string_list(context.get("question_driver_refs"))
        + [
            "q2_unified_asset_inventory",
            "q2_internal_tool_asset_inventory",
            "q2_external_tool_asset_inventory",
            "q3_role_profile",
            "q3_mission_boundary",
            "q4_functional_capabilities",
        ]
    )

    return {
        "asset_and_permissions": {
            "q2_internal_tool_asset_inventory": q2_internal_tool_asset_inventory,
            "q2_external_tool_asset_inventory": q2_external_tool_asset_inventory,
            "q2_unified_asset_inventory_ref": {
                "inventory_summary": q2_inventory.get("inventory_summary") if isinstance(q2_inventory, dict) else "",
                "available_execution_tools": q2_inventory.get("available_execution_tools") if isinstance(q2_inventory, dict) else [],
            },
            "permission_profile": permission_profile,
        },
        "role_and_mission": {
            "q3_role_profile": context.get("q3_role_profile") or {},
            "q3_mission_boundary": context.get("q3_mission_boundary") or {},
        },
        "capability_handshake": capability_handshake[:120],
        "probe_results": probe_results[:120],
        "question_driver_refs": references,
    }


def _coerce_capability_assessment(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    """Normalize LLM output and validate required fields exist and are in expected types."""
    if not isinstance(payload, dict):
        return {}, None, ["LLM 输出必须是 JSON 对象。"]

    root_keys = set(payload.keys())
    if Q4_CAPABILITY_ROOT_KEY_INTERNAL not in root_keys:
        return {}, None, [
            "根节点必须是 CapabilityAssessment，仅允许该字段作为顶层根。"
        ]
    assessment_key = Q4_CAPABILITY_ROOT_KEY_INTERNAL
    assessment_payload: Any = payload.get(assessment_key)
    extra_root_keys = root_keys - {Q4_CAPABILITY_ROOT_KEY_INTERNAL}
    if extra_root_keys:
        return {}, None, [f"根节点包含未授权字段: {sorted(extra_root_keys)}"]
    if not isinstance(assessment_payload, dict):
        return {}, None, [f"{assessment_key} 必须是 object。"]

    normalized: dict[str, Any] = {}
    issues: list[str] = []
    extra_keys = set(assessment_payload.keys()) - Q4_ASSESSMENT_REQUIRED_KEYS
    if extra_keys:
        return {}, None, [f"{assessment_key} 包含未授权字段: {sorted(extra_keys)}"]

    missing = Q4_ASSESSMENT_REQUIRED_KEYS - set(assessment_payload.keys())
    if missing:
        return {}, None, [f"{assessment_key} 缺少字段: {sorted(missing)}"]

    inferred_items, inferred_issues = _coerce_inferred_capabilities(
        assessment_payload.get("inferred_capabilities")
    )
    issues.extend(inferred_issues)
    normalized["inferred_capabilities"] = inferred_items

    normalized = {**normalized}
    if issues:
        return {}, None, issues
    return normalized, None, []


class Q4WhatCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q4
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q4"
    display_name: str = "Q4: What can I do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q4: 我能做什么 (capability boundary profile)

    Anti-hallucination enforcement:
    - LLM must operate strictly within Q3 role profile and permissions.
    - Post-validate actionable_space does not claim write actions when the input states read-only / no execution tools.
    - Violations are fail-closed (raise), never silently corrected.
    """

    def _build_llm_trace_payload(
        self,
        *,
        attempts: list[dict[str, Any]],
        system_prompt: str,
        model_context: dict[str, Any],
        caller_context: Any,
        profile: Any,
    ) -> dict[str, Any]:
        token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        normalized_attempts: list[dict[str, Any]] = []
        for attempt in attempts:
            usage = attempt.get("token_usage") if isinstance(attempt, dict) else None
            usage = usage if isinstance(usage, dict) else {}
            token_usage["input_tokens"] += int(usage.get("input_tokens") or 0)
            token_usage["output_tokens"] += int(usage.get("output_tokens") or 0)
            token_usage["total_tokens"] += int(usage.get("total_tokens") or 0)
            normalized_attempts.append(attempt)

        latest = attempts[-1] if attempts else {}
        return {
            "provider_name": latest.get("provider_plugin_id"),
            "model": latest.get("provider_model"),
            "system_prompt": system_prompt,
            "prompt": latest.get("prompt") or "",
            "source_module": caller_context.source_module,
            "invocation_phase": caller_context.invocation_phase,
            "question_driver_refs": list(caller_context.question_driver_refs),
            "context_data": model_context,
            "result": profile,
            "raw_response": latest.get("raw_response"),
            "token_usage": token_usage,
            "elapsed_ms": latest.get("elapsed_ms") or 0,
            "invocations": normalized_attempts,
        }

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q4_module_runs = bind_module_runs(context, "q4")
        upstream_context = {
            **load_q1_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q3_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
        }
        q2_internal_tool_asset_inventory = _internal_asset_inventory_from_context(context)
        q2_external_tool_asset_inventory = _external_asset_inventory_from_context(context)
        q2_inventory = {
            "available_cognitive_tools": q2_internal_tool_asset_inventory.get("cognitive_and_functional_tools", []),
            "available_execution_tools": q2_external_tool_asset_inventory.get("cognitive_and_functional_tools", []),
        }
        if not q2_inventory:
            raise RuntimeError("q4_q2_inventory_missing")
        inventory_validation_run = start_module_run(
            q4_module_runs,
            "q4_inventory_validation",
            source="plugins.nine_questions.q4",
        )
        exec_domains = list(q2_inventory.get("available_execution_tools", []) or [])
        plugin_service = context.get("plugin_service")
        if plugin_service is None:
            raise RuntimeError("q4_plugin_service_missing")
        functional_capabilities: list[dict[str, Any]] = []
        execution_capability_run = start_module_run(
            q4_module_runs,
            "q4_execution_capability_verification",
            source="plugins.nine_questions.q4",
        )
        try:
            functional_capabilities = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"context": dict(context)},
                trace_id=str(context.get("trace_id") or "q4"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
        except Exception as exc:
            logger.exception("Q4 functional capability chain failed")
            fail_module_run(
                execution_capability_run,
                error_code="q4_functional_capability_chain_failed",
                error_message=str(exc),
            )
            raise RuntimeError("q4_functional_capability_chain_failed") from exc
        failed_functionals = [
            item
            for item in functional_capabilities
            if isinstance(item, dict) and item.get("status") != "done"
        ]
        if failed_functionals:
            fail_module_run(
                execution_capability_run,
                error_code="q4_functional_capability_chain_failed",
                error_message="Q4 functional capability chain returned failed plugin outputs.",
            )
            raise RuntimeError("q4_functional_capability_chain_failed")
        exec_domains.extend(
            str(item.get("plugin_id") or "")
            for item in functional_capabilities
            if item.get("status") == "done"
        )
        exec_domains = list(dict.fromkeys(item for item in exec_domains if str(item).strip()))
        if not exec_domains:
            fail_module_run(
                execution_capability_run,
                error_code="q4_execution_domains_missing",
                error_message="Q4 requires real execution domains from Q3 or functional capabilities.",
            )
            raise RuntimeError("q4_execution_domains_missing")
        finish_module_run(execution_capability_run)

        normalized_functional_capabilities = normalize_functional_capabilities(functional_capabilities)
        permission_profile = derive_permission_profile(upstream_context, q2_inventory)
        finish_module_run(inventory_validation_run)
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_inventory_validation",
            payload={
                "q1_scene_model": upstream_context.get("q1_scene_model"),
                "q1_uncertainty_profile": upstream_context.get("q1_uncertainty_profile"),
                "q2_unified_asset_inventory": q2_inventory,
                "q2_internal_tool_asset_inventory": q2_internal_tool_asset_inventory,
                "q2_external_tool_asset_inventory": q2_external_tool_asset_inventory,
                "q2_resource_evaluation": upstream_context.get("q2_resource_evaluation"),
                "q3_role_profile": upstream_context.get("q3_role_profile"),
                "q3_mission_boundary": upstream_context.get("q3_mission_boundary"),
            },
            status=str(inventory_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        permission_validation_run = start_module_run(
            q4_module_runs,
            "q4_permission_validation",
            source="plugins.nine_questions.q4",
        )
        finish_module_run(permission_validation_run)
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_permission_validation",
            payload={"q4_permission_profile": permission_profile},
            status=str(permission_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        capability_baseline = derive_capability_baseline(
            upstream_context,
            q2_inventory,
            exec_domains,
            permission_profile,
            normalized_functional_capabilities,
        )
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_execution_capability_verification",
            payload={
                "q4_capability_baseline": capability_baseline,
                "q4_active_execution_domains": exec_domains,
            },
            status=str(execution_capability_run.get("status") or "completed"),
            output_kind="evidence",
        )

        evidence_context = dict(upstream_context)
        evidence_context["q4_functional_capabilities"] = normalized_functional_capabilities
        q3_role_profile = upstream_context.get("q3_role_profile")
        q3_mission_boundary = upstream_context.get("q3_mission_boundary")
        if not q2_internal_tool_asset_inventory:
            raise RuntimeError("q4_q2_internal_tool_asset_inventory_missing")
        if not q2_external_tool_asset_inventory:
            raise RuntimeError("q4_q2_external_tool_asset_inventory_missing")
        if not isinstance(q3_role_profile, dict) or not q3_role_profile:
            raise RuntimeError("q4_q3_role_profile_missing")
        if not isinstance(q3_mission_boundary, dict) or not q3_mission_boundary:
            raise RuntimeError("q4_q3_mission_boundary_missing")
        preprocessed_evidence = _build_preprocessed_evidence(
            evidence_context,
            q2_inventory=q2_inventory,
            q2_internal_tool_asset_inventory=q2_internal_tool_asset_inventory,
            q2_external_tool_asset_inventory=q2_external_tool_asset_inventory,
            permission_profile=permission_profile,
        )
        verification_probe_evidence = render_human_readable_block(
            {
                "verification_probes": preprocessed_evidence.get("probe_results") or [],
                "permission_profile": permission_profile,
                "active_execution_domains": exec_domains,
                "capability_baseline": capability_baseline,
            },
            heading="Verification Probes / Permission Boundary",
        )
        q2_internal_asset_inventory_evidence = _render_q2_internal_asset_inventory(context)
        q2_external_asset_inventory_evidence = _render_q2_external_asset_inventory(context)
        q3_role_mission_evidence = _render_q3_role_mission(upstream_context)
        llm_request = build_q4_llm_request(
            capability_baseline=capability_baseline,
            permission_profile=permission_profile,
            verification_probe_evidence=verification_probe_evidence,
            q2_internal_asset_inventory_evidence=q2_internal_asset_inventory_evidence,
            q2_external_asset_inventory_evidence=q2_external_asset_inventory_evidence,
            q3_role_mission_evidence=q3_role_mission_evidence,
            snapshot_version=upstream_context.get("snapshot_version"),
            q1_scene_model=upstream_context.get("q1_scene_model"),
            q1_uncertainty_profile=upstream_context.get("q1_uncertainty_profile"),
            q3_role_profile=q3_role_profile,
            q3_mission_boundary=q3_mission_boundary,
            q2_internal_tool_asset_inventory=q2_internal_tool_asset_inventory,
            q2_external_tool_asset_inventory=q2_external_tool_asset_inventory,
            q2_unified_asset_inventory=q2_inventory,
            q2_resource_evaluation=upstream_context.get("q2_resource_evaluation"),
            q2_workspaces_and_permissions=upstream_context.get("workspaces_and_permissions"),
            q2_memory_and_strategy=upstream_context.get("memory_and_strategy"),
            active_execution_domains=exec_domains,
            functional_capabilities=normalized_functional_capabilities,
            preprocessed_evidence=preprocessed_evidence,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q4-what-can-i-do:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        decision_id = str(context.get("decision_id") or f"{turn_id}:q4_what_can_i_do")
        q4_run_id = f"{trace_id}:{uuid4().hex}"

        caller_context = build_caller_context(
            source_module="q4_what_can_i_do_plugin",
            invocation_phase="nine_question_q4_what_can_i_do",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        actionability_run = start_module_run(
            q4_module_runs,
            "q4_actionability_projection",
            source="plugins.nine_questions.q4",
        )

        inference: Q4WhatCanIDoInference | None = None
        llm_invocation_attempts: list[dict[str, Any]] = []

        for attempt in range(1, MAX_Q4_LLM_ATTEMPTS + 1):
            attempt_request_id = str(uuid4())
            retry_hint = (
                "\n\n上一次输出不满足 Q4 Contract：仅返回 CapabilityAssessment 根节点，"
                "且其 inferred_capabilities 必须是对象数组（capability_name, capability_description, "
                "used_q1_resources_and_q2_capabilities）。"
                if attempt > 1
                else ""
            )
            current_prompt = f"{system_prompt}\n\n{prompt}{retry_hint}"
            attempt_payload: dict[str, Any] = {
                "attempt": attempt,
                "request_id": attempt_request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "provider_model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "question_driver_refs": list(caller_context.question_driver_refs),
                "caller_context": caller_context.model_dump(mode="json"),
                "system_prompt": system_prompt,
                "prompt": current_prompt,
                "context": model_context,
            }

            try:
                raw = provider.generate_json(
                    prompt=current_prompt,
                    context=model_context,
                    caller_context=caller_context,
                )
                attempt_payload["raw_response"] = json_safe_payload(getattr(provider, "last_raw_response", None))
                attempt_payload["token_usage"] = json_safe_payload(
                    getattr(provider, "last_token_usage", None)
                )
                attempt_payload["result"] = json_safe_payload(raw)
            except Exception as exc:
                logger.exception("Q4 LLM invocation failed")
                attempt_payload.update(
                    {
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                        "snapshot_version": upstream_context.get("snapshot_version"),
                    }
                )
                llm_invocation_attempts.append(attempt_payload)
                record_model_invoked(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                record_model_failed(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                if attempt >= MAX_Q4_LLM_ATTEMPTS:
                    fail_module_run(
                        actionability_run,
                        error_code="q4_llm_invocation_failed",
                        error_message=str(exc),
                    )
                    raise RuntimeError("q4_llm_invocation_failed") from exc
                continue

            normalized_assessment_payload, _, validation_errors = _coerce_capability_assessment(
                raw if isinstance(raw, dict) else {}
            )
            if validation_errors:
                attempt_payload["validation_error"] = ", ".join(validation_errors)
                llm_invocation_attempts.append(attempt_payload)
                record_model_invoked(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                record_model_failed(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                if attempt >= MAX_Q4_LLM_ATTEMPTS:
                    fail_module_run(
                        actionability_run,
                        error_code="q4_output_validation_failed",
                        error_message="; ".join(validation_errors),
                    )
                    raise RuntimeError("q4_output_validation_failed")
                continue

            inference_payload = {
                "capability_assessment": normalized_assessment_payload,
            }

            try:
                inference = Q4WhatCanIDoInference.model_validate(inference_payload)
            except Exception as exc:
                logger.exception("Q4 output validation failed")
                attempt_payload["validation_error"] = str(exc)
                llm_invocation_attempts.append(attempt_payload)
                record_model_invoked(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                record_model_failed(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q4_what_can_i_do",
                    payload=attempt_payload,
                )
                if attempt >= MAX_Q4_LLM_ATTEMPTS:
                    fail_module_run(
                        actionability_run,
                        error_code="q4_output_validation_failed",
                        error_message=str(exc),
                    )
                    raise RuntimeError("q4_output_validation_failed") from exc
                continue

            attempt_payload.update(
                {
                    "result": json_safe_payload(inference_payload),
                    "assessment_payload": json_safe_payload(normalized_assessment_payload),
                }
            )
            llm_invocation_attempts.append(attempt_payload)
            record_model_invoked(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q4_what_can_i_do",
                payload=attempt_payload,
            )
            break

        if inference is None:
            fail_module_run(
                actionability_run,
                error_code="q4_output_validation_failed",
                error_message="Q4 未通过 inferred_capabilities 合约校验",
            )
            raise RuntimeError("q4_output_validation_failed")

        assessment_payload = inference.capability_assessment.model_dump(mode="json")
        profile = inference.capability_boundary_profile
        if profile is None:
            inferred_capability_names = _coerce_inferred_capability_texts(
                inference.capability_assessment.inferred_capabilities
            )
            profile = CapabilityBoundaryProfile(
                capability_upper_limits=_dedupe(list(inferred_capability_names)),
                actionable_space=_dedupe(
                    list(inferred_capability_names)
                ),
                executable_strategies=_dedupe(
                    list(inferred_capability_names)
                ),
            )

        read_only = bool(permission_profile.get("is_read_only"))
        profile.capability_upper_limits = merge_with_capability_baseline(
            profile.capability_upper_limits,
            capability_baseline.get("capability_upper_limits", []),
            read_only=read_only,
        )
        profile.actionable_space = merge_with_capability_baseline(
            profile.actionable_space,
            capability_baseline.get("actionable_space", []),
            read_only=read_only,
        )
        profile.executable_strategies = merge_with_capability_baseline(
            profile.executable_strategies,
            capability_baseline.get("executable_strategies", []),
            read_only=read_only,
        )

        # Guardrail validation (anti-hallucination): if there is no execution tool or permissions are read-only,
        # the model must not claim write-like actions.
        execution_tools = q2_inventory.get("available_execution_tools") or []
        if not execution_tools:
            read_only = True
        if read_only:
            offending = [
                a
                for a in profile.actionable_space
                if isinstance(a, str) and contains_write_like_action(a)
            ]
            anti_hallucination_run = start_module_run(
                q4_module_runs,
                "q4_anti_hallucination_guard",
                source="plugins.nine_questions.q4",
            )
            if offending:
                fail_module_run(
                    anti_hallucination_run,
                    error_code="q4_anti_hallucination_violation",
                    error_message="Actionable space contains write-like actions under read-only/no-execution constraints.",
                )
                raise RuntimeError(
                    "q4_anti_hallucination_violation: " + "; ".join(offending[:5])
                )
            finish_module_run(anti_hallucination_run)
        else:
            anti_hallucination_run = start_module_run(
                q4_module_runs,
                "q4_anti_hallucination_guard",
                source="plugins.nine_questions.q4",
            )
            finish_module_run(anti_hallucination_run)

        q4_profile_payload = profile.model_dump(mode="json")
        q4_profile_payload["provenance"] = {
            "inferred_count": len(assessment_payload.get("inferred_capabilities") or []),
        }

        latest_model_payload = llm_invocation_attempts[-1] if llm_invocation_attempts else {}
        llm_trace_payload = self._build_llm_trace_payload(
            attempts=llm_invocation_attempts,
            system_prompt=system_prompt,
            model_context=model_context,
            caller_context=caller_context,
            profile={"capability_assessment": assessment_payload},
        )
        persist_q4_llm_io(
            db_path=context.get("nine_question_state_db_path"),
            session_id=session_id,
            run_id=q4_run_id,
            trace_id=trace_id,
            request_id=_text(latest_model_payload.get("request_id")),
            decision_id=_text(decision_id),
            provider_name=_text(latest_model_payload.get("provider_plugin_id")),
            model=_text(latest_model_payload.get("provider_model")),
            status="completed",
            attempt_count=len(llm_invocation_attempts),
            internal_llm_input={
                "request_id": latest_model_payload.get("request_id"),
                "decision_id": decision_id,
                "provider_plugin_id": latest_model_payload.get("provider_plugin_id"),
                "provider_model": latest_model_payload.get("provider_model"),
                "system_prompt": latest_model_payload.get("system_prompt"),
                "prompt": latest_model_payload.get("prompt"),
                "context": latest_model_payload.get("context"),
                "caller_context": latest_model_payload.get("caller_context"),
                "question_ref": latest_model_payload.get("question_ref"),
                "question_driver_refs": latest_model_payload.get("question_driver_refs"),
                "attempt": latest_model_payload.get("attempt"),
                "elapsed_ms": latest_model_payload.get("elapsed_ms"),
            },
            internal_llm_output={
                "result": latest_model_payload.get("result"),
                "raw_response": latest_model_payload.get("raw_response"),
                "llm_trace_payload": llm_trace_payload,
            },
            external_llm_input={},
            external_llm_output={},
            token_usage=latest_model_payload.get("token_usage"),
            elapsed_ms=int(latest_model_payload.get("elapsed_ms") or 0),
            error_type=_text(latest_model_payload.get("error_type") or ""),
            error_message=_text(latest_model_payload.get("error_message") or ""),
        )
        persist_q4_inferred_capabilities(
            db_path=context.get("nine_question_state_db_path"),
            session_id=session_id,
            run_id=q4_run_id,
            inferred_capabilities=assessment_payload.get("inferred_capabilities"),
        )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": latest_model_payload.get("request_id", str(uuid4())),
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": latest_model_payload.get("raw_response"),
                "token_usage": latest_model_payload.get("token_usage"),
                "model": latest_model_payload.get("provider_model"),
                "llm_trace_payload": llm_trace_payload,
            },
        )

        summary = (
            f"actionable={len(q4_profile_payload.get('actionable_space', []))}; "
            f"inferred={len(assessment_payload.get('inferred_capabilities', []))}; "
            f"attempts={len(llm_invocation_attempts)}"
        )
        finish_module_run(actionability_run)
        q4_execution_diagnosis = {
            "authenticity_status": "completed",
            "diagnosis_code": "completed",
            "diagnosis_message": "Q4 capability boundary completed with validated evidence.",
            "module_runs": list(q4_module_runs),
            "plugin_runs": [],
            "upstream_dependencies": [
                {
                    "dependency_id": "q3",
                    "required": True,
                    "status": "completed" if upstream_context.get("q3_role_profile") else "missing",
                    "message": "Q3 role profile is required for capability boundary evaluation.",
                }
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q4",
                retriable=True,
                rollback_available=True,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q4-rerun-question",
                        label="重跑 Q4 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q4",
                        reason="重新执行能力边界评估。",
                        path="/api/web/nine-questions/q4/run",
                    ),
                    build_recovery_action(
                        "q4-refresh-capability-inputs",
                        label="刷新 Q4 能力输入模块",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q4_execution_capability_verification",
                        reason="仅刷新 Q4 inventory/permission/execution capability 模块，不重跑 LLM。",
                        path="/api/web/nine-questions/q4/modules/q4_execution_capability_verification/retry",
                    ),
                    build_recovery_action(
                        "q4-rollback-previous-success",
                        label="回滚 Q4 到上一份成功快照",
                        kind="rollback",
                        executable=True,
                        scope="question",
                        target="q4",
                        reason="当前 Q4 部分失败时，恢复上一份成功能力边界。",
                        path="/api/web/nine-questions/q4/rollback",
                    ),
                    build_recovery_action(
                        "q4-rerun-upstream-q3",
                        label="先重跑 Q3 再重跑 Q4",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q2->q3->q4",
                        reason="Q4 的能力边界依赖 Q2 我有什么和 Q3 我是谁。",
                        path="/api/web/nine-questions/q3/run",
                    ),
                ],
            ),
        }
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_capability_reasoning_projection",
            payload={
                "capability_boundary_profile": q4_profile_payload,
                "capability_assessment": assessment_payload,
                "preprocessed_evidence": preprocessed_evidence,
                "llm_trace_payload": llm_trace_payload,
            },
            status=str(actionability_run.get("status") or "completed"),
            output_kind="inference",
        )
        q4_module_runs = q4_execution_diagnosis.get("module_runs")
        q4_module_runs = q4_module_runs if isinstance(q4_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            summary="Q4 能力边界裁剪审计已记录。",
            payload={
                "q4_capability_boundary_profile": q4_profile_payload,
                "q4_capability_assessment": assessment_payload,
                "q4_capability_evidence": {
                    "q1_scene_model": upstream_context.get("q1_scene_model"),
                    "q2_unified_asset_inventory": q2_inventory,
                    "q3_role_profile": upstream_context.get("q3_role_profile"),
                },
                "q4_preprocessed_evidence": preprocessed_evidence,
                "llm_trace_payload": llm_trace_payload,
            },
        )
        run_memory_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            title="Q4 Capability Boundary",
            summary="Q4 能力边界已写入记忆。",
            layer="episodic",
            payload={
                "q4_capability_boundary_profile": q4_profile_payload,
                "q4_capability_assessment": assessment_payload,
            },
            tags=["nine-questions", "q4", "capability-boundary"],
        )
        run_reflection_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            subject="Q4 capability boundary",
            summary="Q4 能力边界反思已记录。",
            reflection_type="strategy_reflection",
            payload={
                "q4_capability_boundary_profile": q4_profile_payload,
                "q4_capability_assessment": assessment_payload,
                "q4_permission_profile": permission_profile,
                "q4_preprocessed_evidence": preprocessed_evidence,
            },
        )
        run_learning_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            learning_kind="capability_boundary",
            summary="Q4 能力边界学习记录已登记。",
            payload={
                "q4_capability_boundary_profile": q4_profile_payload,
                "q4_capability_assessment": assessment_payload,
                "llm_trace_payload": llm_trace_payload,
            },
        )
        q4_execution_diagnosis["module_runs"] = q4_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "capability_boundary_profile",
                    **q4_profile_payload,
                },
                {
                    "kind": "capability_assessment",
                    **assessment_payload,
                },
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q4_capability_boundary_profile": q4_profile_payload,
                "q4_capability_assessment": assessment_payload,
                "q4_snapshot_version": upstream_context.get("snapshot_version"),
                "q4_active_execution_domains": exec_domains,
                "q4_permission_profile": permission_profile,
                "q4_capability_baseline": capability_baseline,
                "q4_functional_capabilities": normalized_functional_capabilities,
                "q4_execution_diagnosis": q4_execution_diagnosis,
                "q4_preprocessed_evidence": preprocessed_evidence,
                "q4_capability_evidence": {
                    "q1_scene_model": upstream_context.get("q1_scene_model"),
                    "q2_unified_asset_inventory": q2_inventory,
                    "q2_resource_evaluation": upstream_context.get("q2_resource_evaluation"),
                    "q3_role_profile": upstream_context.get("q3_role_profile"),
                    "q3_mission_boundary": upstream_context.get("q3_mission_boundary"),
                },
                "llm_trace_payload": llm_trace_payload,
            },
            llm_trace_payload=llm_trace_payload,
            confidence=0.7,
        )


def build_q4_what_can_i_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q4,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4WhatCanIDoPlugin:
    return Q4WhatCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q4",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
