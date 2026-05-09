from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from zentex.reflection.service import ReflectionService
from zentex.reflection.nine_question_prompt_upgrade import get_prompt_upgrade_contract
from zentex.upgrade.models import LLMUpgradeIntentRequest
from zentex.upgrade.llm.models import LLMUpgradeRequest
from zentex.common.startup_markers import log_once


QUESTION_DEPENDENCIES: dict[str, list[str]] = {
    "q1": ["q1"],
    "q2": ["q1", "q2"],
    "q3": ["q1", "q2", "q3"],
    "q4": ["q1", "q2", "q3", "q4"],
    "q5": ["q1", "q2", "q3", "q4", "q5"],
    "q6": ["q1", "q2", "q3", "q4", "q5", "q6"],
    "q7": ["q1", "q2", "q3", "q4", "q5", "q6", "q7"],
    "q8": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
    "q9": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"],
}


def dependent_questions(question_id: str) -> list[str]:
    return list(QUESTION_DEPENDENCIES.get(question_id, [question_id]))


def _build_missing_data(snapshot: dict[str, Any], required_fields: list[str]) -> list[str]:
    missing: list[str] = []
    context_updates = snapshot.get("context_updates") if isinstance(snapshot, dict) else {}
    if not isinstance(context_updates, dict):
        context_updates = {}
    for field in required_fields:
        if field not in context_updates:
            missing.append(f"关键字段缺失: {field}")
    if snapshot.get("summary") in (None, "", "-"):
        missing.append("摘要缺失或为空")
    if snapshot.get("confidence") is None:
        missing.append("置信度缺失")
    return missing


def _build_useless_data(snapshot: dict[str, Any]) -> list[str]:
    useless: list[str] = []
    context_updates = snapshot.get("context_updates") if isinstance(snapshot, dict) else {}
    if not isinstance(context_updates, dict):
        context_updates = {}

    # Heuristic: large raw blobs are often not directly useful for decision-making.
    for key, value in context_updates.items():
        if key in {"raw_response", "debug_payload", "trace_dump"}:
            useless.append(f"可能无用调试数据: {key}")
        elif isinstance(value, str) and len(value) > 5000:
            useless.append(f"超长文本可能需要压缩: {key}")

    return useless


def analyze_question_effectiveness(question_id: str, snapshot: dict[str, Any], state_payload: dict[str, Any]) -> dict[str, Any]:
    confidence = snapshot.get("confidence") if isinstance(snapshot, dict) else None
    confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.0

    required_by_question = {
        "q1": ["workspace_domain_inference"],
        "q2": ["q2_asset_inventory"],
        "q3": ["q3_role_profile"],
        "q4": ["q4_capability_boundary"],
        "q5": ["q5_permission_boundary"],
        "q6": ["q6_forbidden_zone"],
        "q7": ["q7_alternative_strategies"],
        "q8": ["q8_objective_profile"],
        "q9": ["q9_action_plan"],
    }

    missing_data = _build_missing_data(snapshot, required_by_question.get(question_id, []))
    useless_data = _build_useless_data(snapshot)

    effectiveness_score = max(0.0, min(1.0, confidence_value - 0.1 * len(missing_data)))
    effective = effectiveness_score >= 0.6
    need_upgrade = effectiveness_score < 0.55 or len(missing_data) >= 2

    missing_for_goal = (
        "当前结果对本问目标支撑不足，建议补齐关键字段并增加证据来源。"
        if missing_data
        else "当前结果基本满足本问目标。"
    )

    return {
        "question_id": question_id,
        "effective": effective,
        "effectiveness_score": round(effectiveness_score, 3),
        "need_upgrade": need_upgrade,
        "upgrade_reason": "有效性偏低或关键字段缺失" if need_upgrade else "当前有效性达标",
        "useless_data": useless_data,
        "missing_data": missing_data,
        "missing_for_goal": missing_for_goal,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_version": state_payload.get("snapshot_version"),
        "revision": state_payload.get("revision"),
    }


def run_question_reflection(
    *,
    reflection_service: ReflectionService,
    question_id: str,
    state_payload: dict[str, Any],
    scope: str,
    trigger: str,
    upgrade_execution_service: Optional[Any] = None,
) -> dict[str, Any]:
    log_once(
        "reflection.invoked",
        question_id=question_id,
        scope=scope,
        trigger=trigger,
    )
    snapshots = state_payload.get("question_snapshots") if isinstance(state_payload, dict) else {}
    if not isinstance(snapshots, dict):
        snapshots = {}

    snapshot = snapshots.get(question_id) if isinstance(snapshots.get(question_id), dict) else {}
    analysis = analyze_question_effectiveness(question_id, snapshot, state_payload)

    context = {
        "question_id": question_id,
        "scope": scope,
        "trigger": trigger,
        "analysis": analysis,
        "question_snapshot": snapshot,
        "state_meta": {
            "snapshot_version": state_payload.get("snapshot_version"),
            "revision": state_payload.get("revision"),
            "last_refresh_reason": state_payload.get("last_refresh_reason"),
        },
    }

    reflection = None
    reflection_error: Optional[str] = None
    try:
        reflection = reflection_service.reflect(
            subject=f"Nine Question {question_id} effectiveness reflection",
            context=context,
            reflection_type="strategy_reflection",
            trace_id=f"nine-question-reflection:{question_id}:{trigger}",
        )
    except Exception as exc:
        reflection_error = str(exc)

    upgrade_result: dict[str, Optional[Any]] = None
    if analysis.get("need_upgrade") and upgrade_execution_service is not None:
        try:
            contract = get_prompt_upgrade_contract(question_id)
            request = LLMUpgradeIntentRequest(
                reason=f"{question_id} effectiveness reflection requested auto-upgrade",
                change_signals=["nine_question_effectiveness_low"],
                upgrade_required=True,
                upgrade_request=LLMUpgradeRequest(
                    program_id=f"nine-question-{question_id}",
                    target_component=contract.target_component,
                    baseline_version="v1.0.0",
                    target_metric="effectiveness_score",
                    dataset_refs=[f"reflection:{question_id}", "nine-questions"],
                    objective_summary=str(analysis.get("upgrade_reason") or "improve question effectiveness"),
                    validation_commands=list(contract.validation_commands) or ["make test"],
                    upgrade_kind="prompt_optimization",
                    prompt_file_path=contract.prompt_file_path,
                    prompt_builder_symbol=contract.prompt_builder_symbol,
                    prompt_contract=contract.to_prompt_contract(),
                    immutable_intent=contract.immutable_intent,
                    forbidden_prompt_changes=list(contract.forbidden_prompt_changes),
                    allowed_prompt_change_scope=list(contract.allowed_prompt_change_scope),
                ),
            )
            record = upgrade_execution_service.execute_llm_upgrade(request)
            if record is not None:
                upgrade_result = {
                    "executed": True,
                    "record_id": getattr(record, "record_id", None),
                    "status": getattr(record, "current_status", None),
                }
            else:
                upgrade_result = {
                    "executed": False,
                    "reason": "upgrade_not_required",
                }
        except Exception as exc:
            upgrade_result = {
                "executed": False,
                "error": str(exc),
            }

    return {
        "question_id": question_id,
        "reflection_id": reflection.reflection_id if reflection is not None else None,
        "summary": (
            reflection.summary
            if reflection is not None
            else f"{question_id} reflection fallback: {analysis.get('upgrade_reason') or 'analysis_generated'}"
        ),
        "analysis": analysis,
        "upgrade": upgrade_result,
        "reflection_error": reflection_error,
        "created_at": (
            reflection.created_at.isoformat()
            if reflection is not None
            else datetime.now(timezone.utc).isoformat()
        ),
    }
