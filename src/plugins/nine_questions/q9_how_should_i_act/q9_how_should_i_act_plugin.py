from __future__ import annotations

import logging
from enum import Enum
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import (
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.core.models import LogicalCognitiveToolSpec
from zentex.runtime.cognitive_tools import CognitiveToolResult
from plugins.nine_questions._shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
# Decoupled: Inputs come from posture control plugins
from zentex.core.plugin_family import PostureSpec

logger = logging.getLogger(__name__)


class EvaluationStyle(str, Enum):
    EVIDENCE_FIRST = "evidence_first"
    BALANCED = "balanced"
    FAST_FAIL = "fast_fail"


class RiskTolerance(str, Enum):
    ZERO_TOLERANCE = "zero_tolerance"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionPostureProfile(BaseModel):
    """
    Q9 Result: Action Posture and Execution Style.
    Sets the tone for the G31A Execution Controller.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_style: EvaluationStyle = Field(..., description="The logic/evidence threshold for actions.")
    risk_tolerance: RiskTolerance = Field(..., description="The current risk envelope.")
    action_rhythm: str = Field(..., description="Instructions on execution pacing and feedback.")
    confirmation_strategy: str = Field(..., description="The human-in-the-loop requirement strategy.")
    evolution_direction: str = Field(..., description="What to focus on learning during this action.")


class HowShouldIActPlugin(LogicalCognitiveToolSpec):
    """
    [LLM MANDATORY] Q9 Phase Plugin.
    Determines the Action Posture based on the final decision (Q8) and environmental factors (Q1).
    """
    plugin_id: str = "nine_question_q9_posture"
    display_name: str = "Q9: How should I act? (Posture & Rhythm)"
    behavior_key: str = "q9_action_posture"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = Field(default_factory=lambda: ["unhandled_llm_failure"])
    revocation_reasons: List[str] = Field(default_factory=list)
    tool_type: str = "nine_question"
    purpose: str = "Determine action posture, evaluation style, and confirmation strategy (Q9)."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_question_state", "plugin_registry", "transcript_store", "model_provider"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_model_provider"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize action posture via LLM.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        
        # 1. G-series Posture Control Oracle Discovery
        try:
             registry = context.get("plugin_registry")
             if not registry:
                 raise RuntimeError("Plugin Registry missing from context.")
             
             # Locate active posture oracles
             active_plugins = registry.get_active_plugins()
             posture_oracles = [p.plugin_id for p in active_plugins if isinstance(p, PostureSpec)]
             
        except Exception as exc:
             logger.error(f"Posture Discovery Failure: {exc}")
             raise RuntimeError(f"Q9 Control Path Break: {exc}") from exc

        nine_question_state = context.get("nine_question_state") or {}
        q1_q8 = {f"q{i}": nine_question_state.get(f"q{i}", {}) for i in range(1, 9)}

        # 2. Build synthesis prompt
        system_prompt = (
            "你现在是 Zentex 外部大脑的行动姿态与风格控制中枢。请严格基于当前的主目标（Q8）等认知概览。\n"
            "你的任务不是生成具体的执行动作，而是为接下来的行动定下『基调』。"
        )
        posture_catalog = render_plugin_catalog(posture_oracles, heading="可用姿态策略插件")
        q1_q8_summary = render_nine_questions_snapshot(q1_q8)

        user_prompt = f"""
### 聚合状态快照 (Cognitive Snapshot Q1-Q8)
{q1_q8_summary}

### 可用姿态策略插件
{posture_catalog}

### 任务
生成严格 JSON，且顶层不要再包裹任何额外对象。
只能输出以下 5 个键：
- `evaluation_style`: one of `evidence_first`, `balanced`, `fast_fail`
- `risk_tolerance`: one of `zero_tolerance`, `low`, `medium`, `high`
- `action_rhythm`: string
- `confirmation_strategy`: string
- `evolution_direction`: string

禁止输出以下风格化说明字段：
- `posture_id`
- `active_postures`
- `core_tone`
- `linguistic_style`
- `operational_intensity`
- `risk_appetite`
- `interaction_protocol`
- `posture_justification`
- `style_constraints`

输出示例：
{{
  "evaluation_style": "evidence_first",
  "risk_tolerance": "low",
  "action_rhythm": "bounded incremental verification",
  "confirmation_strategy": "require human confirmation before write actions",
  "evolution_direction": "improve runtime binding and contract consistency"
}}
"""

        trace_id = str(context.get("trace_id") or f"q9-posture:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        # 3. Invoke LLM with strict traceability
        caller_context = build_caller_context(
            invocation_phase="nine_question_q9_posture",
            source_module="q9_how_should_i_act_plugin",
            question_ref="我应该如何行动",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q9_need_reconfirm",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我应该如何行动",
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "context": {"q1_q8": q1_q8, "posture_oracles": posture_oracles},
            },
        )

        try:
            started = perf_counter()
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={"q1_q8": q1_q8, "posture_oracles": posture_oracles},
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            profile = ActionPostureProfile.model_validate(result_raw)

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_need_reconfirm",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": profile.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )

            return profile.model_dump(mode="json")

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_need_reconfirm",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error(f"Q9 LLM Failure: {exc}")
            raise RuntimeError(f"[LLM MANDATORY] Q9 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        result = self.execute(dict(context))
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Synthesized action posture profile (Q9)",
            proposals=[
                {
                    "kind": "nine_question_q9_posture",
                    "result": result,
                }
            ],
            context_updates={
                "q9_action_posture_profile": result,
            },
            confidence=0.8,
        )


def build_q9_how_should_i_act_plugin(
    *,
    plugin_id: str = "nine_question_q9_posture",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> HowShouldIActPlugin:
    return HowShouldIActPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q9",
        status=status,
    )
