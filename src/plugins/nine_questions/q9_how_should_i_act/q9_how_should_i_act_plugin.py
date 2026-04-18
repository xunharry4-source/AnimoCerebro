from __future__ import annotations

import logging
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
from plugins.nine_questions.q9_how_should_i_act.llm_prompt import build_q9_llm_request

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _normalize_ratio(value: object) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return 0.0


def _normalize_snapshot_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).strip()}


def _normalize_self_model(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    current_state = raw.get("current_state")
    current_state = current_state if isinstance(current_state, dict) else {}
    weaknesses = raw.get("recent_weaknesses")
    normalized_weaknesses: list[dict[str, Any]] = []
    if isinstance(weaknesses, list):
        for item in weaknesses:
            if not isinstance(item, dict):
                continue
            normalized_weaknesses.append(
                {
                    "pattern_id": _normalize_text(item.get("pattern_id")) or None,
                    "pattern_type": _normalize_text(item.get("pattern_type") or "unknown"),
                    "frequency": item.get("frequency") if isinstance(item.get("frequency"), int) else None,
                    "severity": _normalize_text(item.get("severity")) or None,
                }
            )
    return {
        "cognitive_load": _normalize_text(raw.get("current_cognitive_load") or raw.get("cognitive_load") or "unknown"),
        "stability_level": _normalize_text(current_state.get("stability_level")) or None,
        "recent_weaknesses": normalized_weaknesses,
    }


def _normalize_reasoning_budget(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "compute_remaining_ratio": _normalize_ratio(
            raw.get("compute_remaining_ratio") or raw.get("remaining") or raw.get("compute_remaining")
        ),
        "token_remaining_ratio": _normalize_ratio(
            raw.get("token_remaining_ratio") or raw.get("token_remaining")
        ),
        "time_remaining_ratio": _normalize_ratio(
            raw.get("time_remaining_ratio") or raw.get("time_remaining")
        ),
        "budget_pressure": _normalize_text(raw.get("budget_pressure")) or None,
    }


def _normalize_functional_postures(raw_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        normalized.append(
            {
                "plugin_id": _normalize_text(item.get("plugin_id")),
                "evaluation_style": _normalize_text(result.get("evaluation_style")),
                "risk_level": _normalize_text(result.get("risk_level")),
                "allowed_directions": _coerce_string_list(result.get("allowed_directions")),
                "forbidden_directions": _coerce_string_list(result.get("forbidden_directions")),
                "validation_requirements": _coerce_string_list(result.get("validation_requirements")),
                "pause_conditions": _coerce_string_list(result.get("pause_conditions")),
                "help_request_conditions": _coerce_string_list(result.get("help_request_conditions")),
                "confirmation_required_conditions": _coerce_string_list(result.get("confirmation_required_conditions")),
                "rollback_conditions": _coerce_string_list(result.get("rollback_conditions")),
            }
        )
    return normalized


def _derive_posture_baseline(
    question_snapshot: dict[str, Any],
    self_model: dict[str, Any],
    budget: dict[str, Any],
    functional_postures: list[dict[str, Any]],
) -> dict[str, Any]:
    q2 = question_snapshot.get("q2") if isinstance(question_snapshot.get("q2"), dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}
    q6 = question_snapshot.get("q6") if isinstance(question_snapshot.get("q6"), dict) else {}
    q8 = question_snapshot.get("q8") if isinstance(question_snapshot.get("q8"), dict) else {}

    role_context = _normalize_text(q2.get("active_role") or q2.get("task_role") or q2.get("identity_role") or "unknown role")
    resource_context_parts: list[str] = []
    bottleneck = _normalize_text(q3.get("bottleneck_node"))
    if bottleneck:
        resource_context_parts.append(f"bottleneck={bottleneck}")
    missing_assets = _coerce_string_list(q3.get("missing_critical_assets"))
    if missing_assets:
        resource_context_parts.append(f"missing_assets={len(missing_assets)}")
    budget_pressure = _normalize_text(budget.get("budget_pressure"))
    if budget_pressure:
        resource_context_parts.append(f"budget_pressure={budget_pressure}")
    if not resource_context_parts:
        resource_context_parts.append("resource_context=stable")

    compute_ratio = _normalize_ratio(budget.get("compute_remaining_ratio"))
    token_ratio = _normalize_ratio(budget.get("token_remaining_ratio"))
    time_ratio = _normalize_ratio(budget.get("time_remaining_ratio"))
    stability_level = _normalize_text(self_model.get("stability_level")).lower()
    red_lines = _coerce_string_list(q6.get("absolute_red_lines"))

    conservative = (
        bool(red_lines)
        or stability_level in {"low", "fragile", "unstable"}
        or any(ratio and ratio < 0.3 for ratio in (compute_ratio, token_ratio, time_ratio))
    )
    risk_level = "high" if conservative else "medium"
    evaluation_style = "evidence_first" if conservative else "goal_balanced"
    action_rhythm = "confirm_before_commit" if conservative else "steady_incremental"

    validation_requirements = [f"validate before action: {item}" for item in red_lines[:3]]
    validation_requirements.extend([f"protect objective continuity: {item}" for item in _coerce_string_list(q8.get("priority_order"))[:3]])

    allowed_directions = [f"advance current objective: {item}" for item in _coerce_string_list(q8.get("current_phase_tasks"))[:3]]
    forbidden_directions = [f"avoid red-line direction: {item}" for item in red_lines[:3]]
    pause_conditions = [f"pause on budget exhaustion: {label}" for label, ratio in (("compute", compute_ratio), ("token", token_ratio), ("time", time_ratio)) if ratio and ratio < 0.15]
    help_request_conditions = [f"request help for missing asset: {item}" for item in missing_assets[:3]]
    confirmation_required_conditions = [f"confirmation required for unstable posture: {item}" for item in red_lines[:3]]
    rollback_conditions = [f"rollback on forbidden direction: {item}" for item in forbidden_directions[:3]]

    for item in functional_postures:
        allowed_directions.extend(_coerce_string_list(item.get("allowed_directions")))
        forbidden_directions.extend(_coerce_string_list(item.get("forbidden_directions")))
        validation_requirements.extend(_coerce_string_list(item.get("validation_requirements")))
        pause_conditions.extend(_coerce_string_list(item.get("pause_conditions")))
        help_request_conditions.extend(_coerce_string_list(item.get("help_request_conditions")))
        confirmation_required_conditions.extend(_coerce_string_list(item.get("confirmation_required_conditions")))
        rollback_conditions.extend(_coerce_string_list(item.get("rollback_conditions")))
        if not conservative and _normalize_text(item.get("evaluation_style")):
            evaluation_style = _normalize_text(item.get("evaluation_style"))
        if not conservative and _normalize_text(item.get("risk_level")):
            risk_level = _normalize_text(item.get("risk_level"))

    return {
        "evaluation_profile": {
            "role_context": role_context,
            "resource_context": "; ".join(resource_context_parts),
            "risk_level": risk_level,
            "evaluation_style": evaluation_style,
            "conservative_mode_triggered": conservative,
            "action_rhythm_hint": action_rhythm,
        },
        "evolution_profile": {
            "allowed_directions": list(dict.fromkeys(item for item in allowed_directions if _normalize_text(item))),
            "forbidden_directions": list(dict.fromkeys(item for item in forbidden_directions if _normalize_text(item))),
            "validation_requirements": list(dict.fromkeys(item for item in validation_requirements if _normalize_text(item))),
            "risk_threshold": 0.05 if conservative else 0.15,
        },
        "escalation_profile": {
            "pause_conditions": list(dict.fromkeys(item for item in pause_conditions if _normalize_text(item))),
            "help_request_conditions": list(dict.fromkeys(item for item in help_request_conditions if _normalize_text(item))),
            "confirmation_required_conditions": list(dict.fromkeys(item for item in confirmation_required_conditions if _normalize_text(item))),
            "rollback_conditions": list(dict.fromkeys(item for item in rollback_conditions if _normalize_text(item))),
        },
    }


def _merge_string_lists(primary: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(_coerce_string_list(primary) + _coerce_string_list(baseline)))


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
    action_rhythm_hint: str = Field(
        default="steady_incremental",
        description="Suggested action rhythm such as steady_incremental or confirm_before_commit.",
    )


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
        normalized_functional_postures = _normalize_functional_postures(
            [
                {"plugin_id": item.get("plugin_id"), "result": item.get("result")}
                for item in functional_postures
                if item.get("status") == "done"
            ]
        )

        snapshot = context.get("context_snapshot", {}) or {}
        question_snapshot = _normalize_snapshot_dict(
            snapshot.get("q1_q8_snapshot") or snapshot.get("q1_q8") or context.get("q1_q8_snapshot") or context.get("q1_q8") or {}
        )
        self_model = _normalize_self_model(
            context.get("living_self_model") or context.get("self_model") or snapshot.get("living_self_model") or snapshot.get("self_model")
        )
        reasoning_budget = _normalize_reasoning_budget(
            context.get("reasoning_budget") or context.get("budget") or snapshot.get("reasoning_budget") or snapshot.get("budget")
        )
        # 从 context_snapshot 读取 Q1-Q8 积累的认知摘要
        nine_questions = snapshot.get("nine_questions") or context.get("nine_questions") or {}
        # 构建 Q1-Q8 的 profiles 摘要（用于 LLM 输入）
        q1_q8 = question_snapshot or {
            "q1": snapshot.get("workspace_domain_inference") or {},
            "q2": snapshot.get("q2_role_profile") or {},
            "q3": snapshot.get("q3_resource_evaluation") or {},
            "q4": snapshot.get("q4_capability_boundary_profile") or {},
            "q5": snapshot.get("q5_authorization_boundary_profile") or snapshot.get("q5_permission_boundary") or {},
            "q6": snapshot.get("q6_forbidden_zone_profile") or {},
            "q7": snapshot.get("q7_alternative_strategy_profile") or {},
            "q8": snapshot.get("q8_objective_profile") or {},
            "summaries": nine_questions,
        }
        if "summaries" not in q1_q8:
            q1_q8["summaries"] = nine_questions
        posture_baseline = _derive_posture_baseline(
            q1_q8,
            self_model,
            reasoning_budget,
            normalized_functional_postures,
        )

        # 2. Build synthesis prompt
        system_prompt = (
            "你现在是 Zentex 外部大脑的行动姿态与风格控制中枢。请严格基于当前的主目标（Q8）等认知概览。\n"
            "你的任务不是生成具体的执行动作，而是为接下来的行动定下『基调』。"
        )
        posture_catalog = render_plugin_catalog(posture_oracles, heading="可用姿态策略插件")
        q1_q8_summary = render_nine_questions_snapshot(nine_questions)

        llm_request = build_q9_llm_request(
            system_prompt=system_prompt,
            q1_q8_summary=q1_q8_summary,
            posture_catalog=posture_catalog,
            posture_baseline=posture_baseline,
            q1_q8=q1_q8,
            self_model=self_model,
            reasoning_budget=reasoning_budget,
            posture_oracles=posture_oracles,
            functional_postures=normalized_functional_postures,
        )
        user_prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

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
                "context": model_context,
            },
        )

        try:
            started = perf_counter()
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context=model_context,
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            eval_prof = EvaluationProfile.model_validate(
                {
                    **(result_raw.get("evaluation_profile", {}) if isinstance(result_raw.get("evaluation_profile"), dict) else {}),
                    "role_context": _normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("role_context")
                    ) or posture_baseline["evaluation_profile"]["role_context"],
                    "resource_context": _normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("resource_context")
                    ) or posture_baseline["evaluation_profile"]["resource_context"],
                    "risk_level": _normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("risk_level")
                    ) or posture_baseline["evaluation_profile"]["risk_level"],
                    "evaluation_style": _normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("evaluation_style")
                    ) or posture_baseline["evaluation_profile"]["evaluation_style"],
                    "action_rhythm_hint": _normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("action_rhythm_hint")
                    ) or posture_baseline["evaluation_profile"].get("action_rhythm_hint") or "steady_incremental",
                    "conservative_mode_triggered": bool(
                        (result_raw.get("evaluation_profile", {}) or {}).get("conservative_mode_triggered")
                        or posture_baseline["evaluation_profile"]["conservative_mode_triggered"]
                    ),
                    "evaluation_weights": (
                        (result_raw.get("evaluation_profile", {}) or {}).get("evaluation_weights")
                        if isinstance((result_raw.get("evaluation_profile", {}) or {}).get("evaluation_weights"), dict)
                        else {
                            "accuracy": 0.35,
                            "speed": 0.1 if posture_baseline["evaluation_profile"]["conservative_mode_triggered"] else 0.2,
                            "risk_control": 0.3,
                            "creativity": 0.1,
                            "continuity": 0.15,
                        }
                    ),
                }
            )
            evol_prof = EvolutionProfile.model_validate(
                {
                    **(result_raw.get("evolution_profile", {}) if isinstance(result_raw.get("evolution_profile"), dict) else {}),
                    "allowed_directions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("allowed_directions")),
                        posture_baseline["evolution_profile"]["allowed_directions"],
                    ),
                    "forbidden_directions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("forbidden_directions")),
                        posture_baseline["evolution_profile"]["forbidden_directions"],
                    ),
                    "validation_requirements": _merge_string_lists(
                        _coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("validation_requirements")),
                        posture_baseline["evolution_profile"]["validation_requirements"],
                    ),
                    "risk_threshold": (
                        float((result_raw.get("evolution_profile", {}) or {}).get("risk_threshold"))
                        if isinstance((result_raw.get("evolution_profile", {}) or {}).get("risk_threshold"), (int, float))
                        else posture_baseline["evolution_profile"]["risk_threshold"]
                    ),
                }
            )
            esc_prof = EscalationProfile.model_validate(
                {
                    **(result_raw.get("escalation_profile", {}) if isinstance(result_raw.get("escalation_profile"), dict) else {}),
                    "pause_conditions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("pause_conditions")),
                        posture_baseline["escalation_profile"]["pause_conditions"],
                    ),
                    "help_request_conditions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("help_request_conditions")),
                        posture_baseline["escalation_profile"]["help_request_conditions"],
                    ),
                    "confirmation_required_conditions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("confirmation_required_conditions")),
                        posture_baseline["escalation_profile"]["confirmation_required_conditions"],
                    ),
                    "revisit_conditions": _coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("revisit_conditions")),
                    "rollback_conditions": _merge_string_lists(
                        _coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("rollback_conditions")),
                        posture_baseline["escalation_profile"]["rollback_conditions"],
                    ),
                }
            )

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
                "q1_q8_snapshot": q1_q8,
                "q9_self_model": self_model,
                "q9_reasoning_budget": reasoning_budget,
                "q9_posture_baseline": posture_baseline,
                "q9_functional_postures": normalized_functional_postures,
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
        eval_prof = result.get("evaluation_profile") or {}
        evol_prof = result.get("evolution_profile") or {}
        esc_prof = result.get("escalation_profile") or {}
        summary_q9 = (
            f"style={eval_prof.get('evaluation_style','')}; "
            f"risk={eval_prof.get('risk_level','')}; "
            f"conservative={eval_prof.get('conservative_mode_triggered','')}"
        )
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
                "nine_questions": {"我应该如何行动": summary_q9},
                "q9_evaluation_profile": eval_prof,
                "q9_evolution_profile": evol_prof,
                "q9_escalation_profile": esc_prof,
                "q9_q1_q8_snapshot": result.get("q1_q8_snapshot") or {},
                "q9_self_model": result.get("q9_self_model") or {},
                "q9_reasoning_budget": result.get("q9_reasoning_budget") or {},
                "q9_posture_baseline": result.get("q9_posture_baseline") or {},
                "q9_functional_postures": result.get("q9_functional_postures") or [],
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
