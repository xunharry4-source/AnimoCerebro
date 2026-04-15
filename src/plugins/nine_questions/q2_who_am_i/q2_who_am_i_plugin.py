from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q2
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q2_who_am_i.models import Q2WhoAmIInference
# Decoupled: Inputs come from identity and weight plugins
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


QUESTION_REF = "我是谁"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
)

logger = logging.getLogger(__name__)

_CONSTRAINT_LABELS = {
    "NO_FAKE_RUNTIME_STATE": "禁止伪造运行态事实或虚构系统状态",
    "NO_SKIP_AUDIT": "禁止跳过审计记录、证据链和可追溯性要求",
    "NO_UNAUTHORIZED_WRITE_ACTION": "禁止未授权写入、修改或执行会产生副作用的动作",
}


def _safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(child)
            for key, child in value.items()
            if isinstance(key, (str, int, float, bool))
        }
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return None


def _serialize_role_payload(role_payload: dict[str, Any]) -> str:
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


def _serialize_constraint_payload(constraint_payload: dict[str, Any]) -> str:
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


class Q2WhoAmIPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q2
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q2"
    display_name: str = "Q2: Who am I?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q2: 我是谁 (dynamic role inference & continuity boundary)

    Enforced red lines:
    - Must use Live LLM (fail-closed; no rule fallback).
    - Must only consume structured summaries from main context snapshot.
    - Must inject provenance via caller_context (source_module + question_driver_refs).
    - Must append-only write prompt/context/response into BrainTranscriptStore.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        workspace_domain_inference = snapshot.get("workspace_domain_inference", {}) or {}
        if not isinstance(workspace_domain_inference, dict):
            workspace_domain_inference = {}
        q1_scene_model = snapshot.get("q1_scene_model", {}) or {}
        if not isinstance(q1_scene_model, dict) or not q1_scene_model:
            q1_scene_model = {
                "primary_domain": workspace_domain_inference.get("primary_domain"),
                "secondary_domains": workspace_domain_inference.get("secondary_domains"),
                "suggested_first_step": workspace_domain_inference.get("suggested_first_step"),
            }
        q1_uncertainty_profile = snapshot.get("q1_uncertainty_profile", {}) or {}
        if not isinstance(q1_uncertainty_profile, dict) or not q1_uncertainty_profile:
            q1_uncertainty_profile = {
                "risk_sources": workspace_domain_inference.get("uncertainties"),
                "risk_summary": workspace_domain_inference.get("reasoning_summary"),
                "uncertainty_intensity": max(
                    0.0,
                    min(1.0, 1.0 - float(workspace_domain_inference.get("confidence", 0.5) or 0.5)),
                ),
            }
        
        snapshot = context.get("context_snapshot", {}) or {}
        identity_kernel = snapshot.get("identity_kernel_snapshot", {}) or {}
        role_payload = identity_kernel
        constraint_payload = {
            "non_bypassable_constraints": identity_kernel.get("non_bypassable_constraints", []) or []
        }
        uncertainty = snapshot.get("q1_uncertainty_profile", {}) or {}
        intensity = uncertainty.get("uncertainty_intensity", 0.5)
        try:
            risk_weight = float(intensity)
        except Exception:
            risk_weight = 0.5
        risk_weight = max(0.0, min(1.0, risk_weight))

        plugin_service = context.get("plugin_service")
        if plugin_service is not None:
            functional_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "q2"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
            for item in functional_inputs:
                if item.get("status") != "done":
                    continue
                result = item.get("result")
                if isinstance(result, (int, float)):
                    risk_weight = max(0.0, min(1.0, float(result)))
                    continue
                if not isinstance(result, dict):
                    continue
                pack_type = str(result.get("pack_type") or "")
                payload = result.get("payload") if isinstance(result.get("payload"), dict) else result
                if pack_type == "role_pack" or "identity_role" in payload or "task_role_mapping" in payload:
                    role_payload = payload
                elif pack_type == "constraint_pack" or "non_bypassable_constraints" in payload:
                    constraint_payload = payload
                elif "risk_weight" in result or "weight" in result:
                    raw_weight = result.get("risk_weight", result.get("weight"))
                    try:
                        risk_weight = max(0.0, min(1.0, float(raw_weight)))
                    except Exception:
                        pass

        system_prompt = (
            "你现在是 Zentex 外部大脑。请根据当前所处的 environment 态势（Q1结果）和你的底层身份内核，"
            "推断出你当前最合适的任务角色、主体定位以及首要职责。"
            f"当前主观风险偏好权重: {risk_weight:.2f} (0=激进, 1=保守)。"
            "记住，你的动态角色绝不能违背底层的不可绕过约束。"
        )

        prompt = (
            f"{system_prompt}\n\n"
            "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
            "- role_profile: { identity_role, active_role, task_role }\n"
            "- mission_boundary: { current_mission, priority_duties, continuity_boundaries }\n\n"
            "输入依据：\n"
            "1) 角色定义包:\n"
            f"{_serialize_role_payload(role_payload)}\n"
            "2) 不可绕过约束（禁令包）:\n"
            f"{_serialize_constraint_payload(constraint_payload)}\n"
            f"3) 当前主观偏好: Risk={risk_weight}\n"
        )

        # Build context for the LLM
        model_context = {
            "workspace_domain_inference": workspace_domain_inference,
            "q1_scene_model": q1_scene_model,
            "q1_uncertainty_profile": q1_uncertainty_profile,
            "identity_kernel_snapshot": snapshot.get("identity_kernel_snapshot"),
            "role_payload": role_payload,
            "constraint_payload": constraint_payload,
            "risk_weight": risk_weight,
            "functional_identity_inputs": (
                functional_inputs if plugin_service is not None else []
            ),
            "manual_role_overrides": snapshot.get("manual_role_overrides", {}),
        }

        trace_id = str(context.get("trace_id") or f"q2-who-am-i:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q2_who_am_i")

        caller_context = build_caller_context(
            source_module="q2_who_am_i_plugin",
            invocation_phase="nine_question_q2_who_am_i",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q2_who_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": _safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        started = perf_counter()
        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q2_who_am_i",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        inference = Q2WhoAmIInference.model_validate(raw)

        # Manual override has highest priority.
        manual_role_overrides = snapshot.get("manual_role_overrides", {}) or {}
        override_active_role = manual_role_overrides.get("active_role_override")
        applied_override = False
        if isinstance(override_active_role, str) and override_active_role.strip():
            role_profile = inference.role_profile.model_copy(
                update={"active_role": override_active_role.strip()}
            )
            inference = inference.model_copy(update={"role_profile": role_profile})
            applied_override = True

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q2_who_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "manual_override_applied": applied_override,
                "raw_response": _json_compatible(getattr(provider, "last_raw_response", None)),
                "token_usage": _json_compatible(getattr(provider, "last_token_usage", {})) or {},
                "model": (
                    str(getattr(provider, "last_model_name", "") or getattr(provider, "default_model", "")).strip()
                    or None
                ),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )

        role_summary = (
            f"identity_role={inference.role_profile.identity_role}; "
            f"active_role={inference.role_profile.active_role}; "
            f"task_role={inference.role_profile.task_role}"
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=role_summary,
            proposals=[
                {
                    "kind": "role_profile",
                    "question_ref": QUESTION_REF,
                    **inference.role_profile.model_dump(mode="json"),
                },
                {
                    "kind": "mission_continuity_boundary",
                    **inference.mission_boundary.model_dump(mode="json"),
                },
            ],
            risks=[
                {
                    "kind": "continuity_boundaries",
                    "items": inference.mission_boundary.continuity_boundaries,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.role_profile.active_role},
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
            },
            confidence=0.75,
        )


def build_q2_who_am_i_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q2,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q2WhoAmIPlugin:
    return Q2WhoAmIPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q2",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
