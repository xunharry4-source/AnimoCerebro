from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

from plugins.nine_questions.q4_what_can_i_do.models import Q4WhatCanIDoInference
# Decoupled: Inputs come from execution domain plugins
from zentex.core.plugin_family import ExecutionPluginSpec


QUESTION_REF = "我能做什么"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_plugin_catalog,
    render_q3_asset_inventory,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)


class Q4WhatCanIDoPlugin(LogicalCognitiveToolSpec):
    """
    Q4: 我能做什么 (capability boundary profile)

    Anti-hallucination enforcement:
    - LLM must operate strictly within Q3 asset inventory + permissions.
    - Post-validate actionable_space does not claim write actions when the input states read-only / no execution tools.
    - Violations are fail-closed (raise), never silently corrected.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        q3_inventory = snapshot.get("q3_unified_asset_inventory", {}) or {}
        exec_domains = list(q3_inventory.get("available_execution_tools", []) or [])

        system_prompt = (
            "你现在是 Zentex 外部大脑的能力评估中枢。请严格基于传入的 Q3 真实资产清单、"
            "当前的物理执行域以及环境态势，"
            "评估系统当前真正具备的行动能力。绝对禁止把不存在的能力写成可行动作。"
        )
        execution_domain_catalog = render_plugin_catalog(exec_domains, heading="执行工具目录")
        asset_inventory_summary = render_q3_asset_inventory(snapshot)

        prompt = (
            f"{system_prompt}\n\n"
            "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
            "- capability_boundary_profile: { capability_upper_limits, actionable_space, executable_strategies }\n"
            "- `capability_upper_limits` 必须是字符串数组，列出能力上限，不允许写成长段说明文本。\n"
            "- `actionable_space` 必须是字符串数组，列出当前可做动作。\n"
            "- `executable_strategies` 必须是字符串数组，列出当前可执行策略。\n"
            "- 禁止输出任何额外字段。\n\n"
            f"{execution_domain_catalog}\n\n"
            f"{asset_inventory_summary}\n\n"
            "输出示例:\n"
            "{\n"
            '  "capability_boundary_profile": {\n'
            '    "capability_upper_limits": ["read workspace state", "inspect runtime audit state"],\n'
            '    "actionable_space": ["read logs", "inspect snapshots"],\n'
            '    "executable_strategies": ["static analysis", "request human confirmation before write"]\n'
            "  }\n"
            "}\n"
        )

        model_context = {
            "snapshot_version": snapshot.get("snapshot_version"),
            "q1_scene_model": snapshot.get("q1_scene_model"),
            "q1_uncertainty_profile": snapshot.get("q1_uncertainty_profile"),
            "q2_role_profile": snapshot.get("q2_role_profile"),
            "q2_mission_boundary": snapshot.get("q2_mission_boundary"),
            "q3_unified_asset_inventory": q3_inventory,
            "q3_resource_evaluation": snapshot.get("q3_resource_evaluation"),
            "active_execution_domains": exec_domains,
        }

        trace_id = str(context.get("trace_id") or f"q4-what-can-i-do:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q4_what_can_i_do")

        caller_context = build_caller_context(
            source_module="q4_what_can_i_do_plugin",
            invocation_phase="nine_question_q4_what_can_i_do",
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
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "context": model_context,
            },
        )

        try:
            raw = provider.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q4_what_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "snapshot_version": snapshot.get("snapshot_version"),
                },
            )
            # Fail-Closed: Strictly raise fatal exception.
            raise

        inference = Q4WhatCanIDoInference.model_validate(raw)
        profile = inference.capability_boundary_profile

        # Guardrail validation (anti-hallucination): if there is no execution tool or permissions are read-only,
        # the model must not claim write-like actions.
        execution_tools = q3_inventory.get("available_execution_tools") or []
        permissions = q3_inventory.get("permissions") or {}
        read_only = False
        if isinstance(permissions, dict) and permissions.get("mode") == "read_only":
            read_only = True
        if not execution_tools:
            read_only = True
        if read_only:
            offending = [a for a in profile.actionable_space if isinstance(a, str) and _contains_write_like_action(a)]
            if offending:
                raise RuntimeError(
                    "Anti-hallucination violation: actionable_space contains write-like actions while read-only/no execution tools: "
                    + "; ".join(offending[:5])
                )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                    "result": inference.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                },
            )

        summary = f"actionable={len(profile.actionable_space)}; strategies={len(profile.executable_strategies)}"
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "capability_boundary_profile",
                    **profile.model_dump(mode="json"),
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q4_capability_boundary_profile": profile.model_dump(mode="json"),
                "q4_snapshot_version": snapshot.get("snapshot_version"),
            },
            confidence=0.7,
        )


def _contains_write_like_action(action: str) -> bool:
    lowered = action.lower()
    if re.search(r"\brm\b", lowered):
        return True
    write_markers = (
        "write",
        "delete",
        "remove",
        "modify",
        "edit",
        "overwrite",
        "deploy",
        "apply",
        "chmod",
        "chown",
        "kill",
        "shutdown",
        "format",
        "drop",
    )
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in write_markers)


def build_q4_what_can_i_do_plugin(
    *,
    plugin_id: str = "nine-question-q4-what-can-i-do",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4WhatCanIDoPlugin:
    return Q4WhatCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q4",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["q4_capability_boundary_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="nine_question",
        purpose="LLM-backed nine-question Q4: 我能做什么 (capability boundary profile).",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["capability_boundary_profile"]},
        required_context=["context_snapshot", "transcript_store"],
        trigger_conditions=["inspection"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "unsafe_external_action"],
    )
