from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import NINE_QUESTION_Q7
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

from plugins.shared.cognitive_result import CognitiveToolResult
from plugins.nine_questions.q7_what_else_can_i_do.llm_prompt import build_q7_llm_request
from plugins.nine_questions.q7_what_else_can_i_do.models import Q7InferenceResult
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_human_readable_block,
    render_q4_boundary,
    render_q5_boundary,
    render_q6_redlines,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)

QUESTION_REF = "我还可以做什么"


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _normalize_functional_alternatives(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if isinstance(item, dict):
            entry = dict(item)
            for key in (
                "fallback_plans",
                "degradation_strategies",
                "collaboration_switches",
                "exploratory_actions",
                "resource_bottlenecks",
                "capability_limits",
                "permission_boundaries",
                "absolute_red_lines",
                "historical_failure_patches",
            ):
                if key in entry:
                    entry[key] = _coerce_string_list(entry.get(key))
            normalized.append(entry)
        elif isinstance(item, list):
            normalized.append({"items": [str(entry).strip() for entry in item if str(entry).strip()]})
    return normalized


def _derive_alternative_strategy_baseline(
    snapshot: dict[str, Any],
    functional_alternatives: list[dict[str, Any]],
) -> dict[str, list[str]]:
    q3_eval = snapshot.get("q3_resource_evaluation")
    q3_eval = q3_eval if isinstance(q3_eval, dict) else {}
    q4_profile = snapshot.get("q4_capability_boundary_profile")
    q4_profile = q4_profile if isinstance(q4_profile, dict) else {}
    q5_profile = snapshot.get("q5_authorization_boundary_profile")
    q5_profile = q5_profile if isinstance(q5_profile, dict) else {}
    q6_profile = snapshot.get("q6_forbidden_zone_profile")
    q6_profile = q6_profile if isinstance(q6_profile, dict) else {}

    fallback_plans: list[str] = []
    degradation_strategies: list[str] = []
    collaboration_switches: list[str] = []
    exploratory_actions: list[str] = []

    missing_assets = _coerce_string_list(q3_eval.get("missing_critical_assets"))
    bottleneck_node = _normalize_text(q3_eval.get("bottleneck_node"))
    for asset in missing_assets:
        exploratory_actions.append(f"inspect missing asset gap: {asset}")
        collaboration_switches.append(f"request support for missing asset: {asset}")
    if bottleneck_node:
        fallback_plans.append(f"route around bottleneck node: {bottleneck_node}")
        exploratory_actions.append(f"profile bottleneck constraints: {bottleneck_node}")

    capability_limits = _coerce_string_list(q4_profile.get("capability_upper_limits"))
    actionable_space = _coerce_string_list(q4_profile.get("actionable_space"))
    if capability_limits:
        degradation_strategies.extend([f"degrade around capability limit: {item}" for item in capability_limits])
    if not actionable_space:
        fallback_plans.append("switch to information-gathering only until actionable_space is rebuilt")

    escalation_actions = _coerce_string_list(q5_profile.get("requires_escalation_actions"))
    allowed_delegation_targets = _coerce_string_list(q5_profile.get("allowed_delegation_targets"))
    for action in escalation_actions:
        collaboration_switches.append(f"escalate before executing restricted action: {action}")
    if allowed_delegation_targets:
        collaboration_switches.extend([f"delegate through approved target: {item}" for item in allowed_delegation_targets])
    else:
        collaboration_switches.append("fallback to human confirmation when delegation target is unclear")

    absolute_red_lines = _coerce_string_list(q6_profile.get("absolute_red_lines"))
    prohibited_strategies = _coerce_string_list(q6_profile.get("prohibited_strategies"))
    if absolute_red_lines or prohibited_strategies:
        degradation_strategies.append("replace blocked primary path with compliant low-risk read/inspect workflow")
    for item in absolute_red_lines:
        fallback_plans.append(f"avoid red-line path and choose compliant branch: {item}")

    for item in functional_alternatives:
        fallback_plans.extend(_coerce_string_list(item.get("fallback_plans")))
        fallback_plans.extend(_coerce_string_list(item.get("alternative_candidates")))
        degradation_strategies.extend(_coerce_string_list(item.get("degradation_strategies")))
        collaboration_switches.extend(_coerce_string_list(item.get("collaboration_switches")))
        exploratory_actions.extend(_coerce_string_list(item.get("exploratory_actions")))
        fallback_plans.extend([f"fallback from plugin item: {entry}" for entry in _coerce_string_list(item.get("items"))])

    return {
        "fallback_plans": list(dict.fromkeys(item for item in fallback_plans if _normalize_text(item))),
        "degradation_strategies": list(dict.fromkeys(item for item in degradation_strategies if _normalize_text(item))),
        "collaboration_switches": list(dict.fromkeys(item for item in collaboration_switches if _normalize_text(item))),
        "exploratory_actions": list(dict.fromkeys(item for item in exploratory_actions if _normalize_text(item))),
    }


def _merge_with_strategy_baseline(inferred: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(_coerce_string_list(inferred) + _coerce_string_list(baseline)))


class WhatElseCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q7
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q7"
    display_name: str = "Q7: What else can I do?"
    description: str = "Generate fallback strategies and substitute actions."
    behavior_key: str = "q7_alternative_strategy"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["unhandled_q7_failure"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}

        # 1. 从 context_snapshot 提取 Q4/Q5/Q6/Q3 数据
        q4_profile = snapshot.get("q4_capability_boundary_profile") or {}
        q5_profile = snapshot.get("q5_authorization_boundary_profile") or snapshot.get("q5_permission_boundary") or {}
        q6_profile = snapshot.get("q6_forbidden_zone_profile") or {}
        q3_eval = snapshot.get("q3_resource_evaluation") or {}

        # 2. 执行 functional plugins（保留原有逻辑）
        plugin_service = context.get("plugin_service")
        functional_alternatives: list[dict[str, Any]] = []
        if plugin_service is not None:
            try:
                raw_inputs = execute_enabled_cognitive_plugin_functionals(
                    plugin_service,
                    self.plugin_id,
                    default_parameters={"block_context": dict(context)},
                    trace_id=str(context.get("trace_id") or "q7"),
                    originator_id=str(context.get("session_id") or "unknown-session"),
                    caller_plugin_id=self.plugin_id,
                )
                functional_alternatives = [
                    item.get("result")
                    for item in raw_inputs
                    if item.get("status") == "done" and item.get("result")
                ]
            except Exception as exc:
                logger.warning(f"Q7 functional plugins failed: {exc}")
        normalized_functional_alternatives = _normalize_functional_alternatives(functional_alternatives)
        alternative_strategy_baseline = _derive_alternative_strategy_baseline(
            snapshot,
            normalized_functional_alternatives,
        )

        llm_request = build_q7_llm_request(
            rendered_q4_boundary=render_q4_boundary(snapshot),
            rendered_q5_boundary=render_q5_boundary(snapshot),
            rendered_q6_redlines=render_q6_redlines(snapshot),
            rendered_q3_resource_state=render_human_readable_block(q3_eval, heading="Q3 资源状态"),
            rendered_functional_alternatives=render_human_readable_block(normalized_functional_alternatives, heading="插件建议备选策略"),
            rendered_strategy_baseline=render_human_readable_block(alternative_strategy_baseline, heading="备选策略基线"),
            q4_capability_boundary=q4_profile,
            q5_authorization_boundary=q5_profile,
            q6_forbidden_zone=q6_profile,
            q3_resource_evaluation=q3_eval,
            functional_alternatives=normalized_functional_alternatives,
            alternative_strategy_baseline=alternative_strategy_baseline,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]

        # 5. 构建追踪元数据
        trace_id = str(context.get("trace_id") or f"q7-alternatives:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q7_alternatives")

        caller_context = build_caller_context(
            source_module="q7_what_else_can_i_do_plugin",
            invocation_phase="nine_question_q7_alternatives",
            question_ref=QUESTION_REF,
            decision_id=decision_id,
            trace_id=trace_id,
        )

        model_context = llm_request["model_context"]

        # 6. 审计日志：触发
        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q7_what_else_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
            },
        )

        # 7. LLM 调用（Fail-Closed）
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
                source="plugins.nine_questions.q7_what_else_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise RuntimeError(f"[LLM MANDATORY] Q7 alternatives inference failed: {exc}") from exc

        # 8. Pydantic 验证
        inference = Q7InferenceResult.model_validate(raw)
        inferred_profile = inference.alternative_strategy_profile
        profile = inferred_profile.model_copy(
            update={
                "fallback_plans": _merge_with_strategy_baseline(
                    inferred_profile.fallback_plans,
                    alternative_strategy_baseline.get("fallback_plans", []),
                ),
                "degradation_strategies": _merge_with_strategy_baseline(
                    inferred_profile.degradation_strategies,
                    alternative_strategy_baseline.get("degradation_strategies", []),
                ),
                "collaboration_switches": _merge_with_strategy_baseline(
                    inferred_profile.collaboration_switches,
                    alternative_strategy_baseline.get("collaboration_switches", []),
                ),
                "exploratory_actions": _merge_with_strategy_baseline(
                    inferred_profile.exploratory_actions,
                    alternative_strategy_baseline.get("exploratory_actions", []),
                ),
            }
        )

        # 9. 审计日志：完成
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q7_what_else_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "result": inference.model_dump(mode="json"),
            },
        )

        # 10. 返回 CognitiveToolResult
        summary = (
            f"fallbacks={len(profile.fallback_plans)}; "
            f"degradations={len(profile.degradation_strategies)}; "
            f"collaborations={len(profile.collaboration_switches)}"
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[{"kind": "alternative_strategy_profile", **profile.model_dump(mode="json")}],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q7_alternative_strategy_profile": profile.model_dump(mode="json"),
                "q7_functional_alternatives": normalized_functional_alternatives,
                "q7_alternative_strategy_baseline": alternative_strategy_baseline,
                "q7_resource_bottlenecks": _coerce_string_list(q3_eval.get("missing_critical_assets") or q3_eval.get("bottleneck_node")),
                "q7_capability_limits": _coerce_string_list(q4_profile.get("capability_upper_limits")),
                "q7_permission_boundaries": _coerce_string_list(
                    q5_profile.get("allowed_action_space") or q5_profile.get("allowed_actions")
                ),
                "q7_absolute_red_lines": _coerce_string_list(q6_profile.get("absolute_red_lines")),
            },
            confidence=0.7,
        )


def build_q7_what_else_can_i_do_plugin() -> WhatElseCanIDoPlugin:
    return WhatElseCanIDoPlugin()
