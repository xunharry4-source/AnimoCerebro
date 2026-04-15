from __future__ import annotations

import logging
from enum import Enum
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q9
from zentex.plugins.models import PluginLifecycleStatus
from zentex.common.nine_questions_shared import (
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
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
)

logger = logging.getLogger(__name__)


class EvaluationProfile(BaseModel):
    """
    Q9 Result: Evaluation Standards.
    Derived from Q3/Q4/Q7.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    role_context: str = Field(..., description="Current role context.")
    resource_context: str = Field(..., description="Current resource status summary.")
    risk_level: str = Field(..., description="Overall risk level.")
    evaluation_weights: Dict[str, float] = Field(..., description="Weights for accuracy/speed/risk_control/creativity/continuity.")
    conservative_mode_triggered: bool = Field(default=False)
    evaluation_style: str = Field(..., description="logic/evidence threshold.")


class EvolutionProfile(BaseModel):
    """
    Q9 Result: Evolution boundaries.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_directions: List[str] = Field(default_factory=list)
    risk_threshold: float = Field(default=0.1)
    forbidden_directions: List[str] = Field(default_factory=list)
    validation_requirements: List[str] = Field(default_factory=list)


class EscalationProfile(BaseModel):
    """
    Q9 Result: Escalation and Reconfirm rules.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    pause_conditions: List[str] = Field(default_factory=list)
    help_request_conditions: List[str] = Field(default_factory=list)
    confirmation_required_conditions: List[str] = Field(default_factory=list)
    revisit_conditions: List[str] = Field(default_factory=list)
    rollback_conditions: List[str] = Field(default_factory=list)

# Pre-rebuild sub-profiles to resolve type hints for Pydantic v2
EvaluationProfile.model_rebuild()
EvolutionProfile.model_rebuild()
EscalationProfile.model_rebuild()



class HowShouldIActPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    """
    [LLM MANDATORY] Q9 Phase Plugin.
    Determines the Action Posture based on the final decision (Q8) and environmental factors (Q1).
    """
    plugin_id: str = NINE_QUESTION_Q9
    display_name: str = "Q9: How should I act? (Posture & Rhythm)"
    behavior_key: str = "q9_action_posture"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    rollback_conditions: List[str] = Field(default_factory=lambda: ["unhandled_llm_failure"])
    revocation_reasons: List[str] = Field(default_factory=list)
    tool_type: str = "nine_question"
    purpose: str = "Determine action posture, evaluation style, and confirmation strategy (Q9)."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_question_state", "plugin_service", "transcript_store", "llm_service"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_llm_service"]
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
        
        plugin_service = context.get("plugin_service")
        trace_id = str(context.get("trace_id") or f"q9-posture:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        functional_postures: list[dict[str, Any]] = []
        posture_oracles: list[str] = []
        if plugin_service is not None:
            functional_postures = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"decision_trace": dict(context)},
                trace_id=trace_id,
                originator_id=session_id,
                caller_plugin_id=self.plugin_id,
            )
            posture_oracles = [
                str(item.get("plugin_id") or "")
                for item in functional_postures
                if item.get("status") == "done"
            ]

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
只有输出以下 3 个对象：
- `evaluation_profile`:
    - `role_context`: str
    - `resource_context`: str
    - `risk_level`: str
    - `evaluation_weights`: dict (keys: accuracy, speed, risk_control, creativity, continuity)
    - `conservative_mode_triggered`: bool
    - `evaluation_style`: str
- `evolution_profile`:
    - `allowed_directions`: list[str]
    - `risk_threshold`: float
    - `forbidden_directions`: list[str]
    - `validation_requirements`: list[str]
- `escalation_profile`:
    - `pause_conditions`: list[str]
    - `help_request_conditions`: list[str]
    - `confirmation_required_conditions`: list[str]
    - `revisit_conditions`: list[str]
    - `rollback_conditions`: list[str]

输出示例：
{{
  "evaluation_profile": {{
    "role_context": "security auditor",
    "resource_context": "limited time, high compute availability",
    "risk_level": "medium",
    "evaluation_weights": {{"accuracy": 0.4, "speed": 0.1, "risk_control": 0.3, "creativity": 0.1, "continuity": 0.1}},
    "conservative_mode_triggered": true,
    "evaluation_style": "evidence_first"
  }},
  "evolution_profile": {{
    "allowed_directions": ["optimize audit logic", "expand plugin binding"],
    "risk_threshold": 0.05,
    "forbidden_directions": ["bypass auth check"],
    "validation_requirements": ["unit testing required"]
  }},
  "escalation_profile": {{
    "pause_conditions": ["detected unauthorized modification"],
    "confirmation_required_conditions": ["applying system-wide patches"]
  }}
}}
"""

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
            source="plugins.nine_questions.q9_how_should_i_act",
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
                context={
                    "q1_q8": q1_q8,
                    "posture_oracles": posture_oracles,
                    "functional_postures": [
                        {
                            "plugin_id": item.get("plugin_id"),
                            "result": item.get("result"),
                        }
                        for item in functional_postures
                        if item.get("status") == "done"
                    ],
                },
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            eval_prof = EvaluationProfile.model_validate(result_raw.get("evaluation_profile", {}))
            evol_prof = EvolutionProfile.model_validate(result_raw.get("evolution_profile", {}))
            esc_prof = EscalationProfile.model_validate(result_raw.get("escalation_profile", {}))

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_how_should_i_act",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": result_raw,
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )

            return {
                "evaluation_profile": eval_prof.model_dump(mode="json"),
                "evolution_profile": evol_prof.model_dump(mode="json"),
                "escalation_profile": esc_prof.model_dump(mode="json"),
            }

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_how_should_i_act",
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
                "q9_evaluation_profile": result.get("evaluation_profile"),
                "q9_evolution_profile": result.get("evolution_profile"),
                "q9_escalation_profile": result.get("escalation_profile"),
            },
            confidence=0.8,
        )


def build_q9_how_should_i_act_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q9,
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> HowShouldIActPlugin:
    return HowShouldIActPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q9",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )


HowShouldIActPlugin.model_rebuild()
