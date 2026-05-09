from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _record_id(record: Any, *names: str) -> str:
    for name in names:
        value = getattr(record, name, None)
        if value:
            return str(value)
    payload = _as_dict(record)
    for name in names:
        value = payload.get(name)
        if value:
            return str(value)
    return ""


def _record_detail(record: Any) -> dict[str, Any]:
    detail = getattr(record, "detail", None)
    if isinstance(detail, dict):
        return detail
    payload = _as_dict(record)
    return payload.get("detail") if isinstance(payload.get("detail"), dict) else payload


def _reflection_context(record: Any) -> dict[str, Any]:
    context = getattr(record, "context", None)
    if isinstance(context, dict):
        return context
    payload = _as_dict(record)
    return payload.get("context") if isinstance(payload.get("context"), dict) else payload


def _matches_dataset(detail: dict[str, Any], *, dataset_id: str, dataset_fingerprint: str, source_trace_id: str) -> bool:
    trigger = detail.get("trigger_condition") if isinstance(detail.get("trigger_condition"), dict) else {}
    if dataset_id and detail.get("dataset_id") != dataset_id:
        return False
    if source_trace_id and str(detail.get("source_trace_id") or "") != source_trace_id:
        return False
    if dataset_fingerprint and str(trigger.get("dataset_fingerprint") or "") != dataset_fingerprint:
        return False
    return bool(detail.get("best_practice") or detail.get("avoid_pattern"))


def _learning_records(learning_service: Any, *, dataset_id: str, dataset_fingerprint: str, source_trace_id: str) -> list[tuple[Any, dict[str, Any]]]:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise RuntimeError("learning_service.query_overall_records is required for evolution context loading")
    rows = list(learning_service.query_overall_records(limit=200) or [])
    matches: list[tuple[Any, dict[str, Any]]] = []
    for row in rows:
        detail = _record_detail(row)
        if _matches_dataset(detail, dataset_id=dataset_id, dataset_fingerprint=dataset_fingerprint, source_trace_id=source_trace_id):
            matches.append((row, detail))
    return matches


def _reflection_records(reflection_service: Any, *, dataset_id: str, source_trace_id: str) -> list[tuple[Any, dict[str, Any]]]:
    if reflection_service is None or not callable(getattr(reflection_service, "list_reflections", None)):
        raise RuntimeError("reflection_service.list_reflections is required for evolution context loading")
    rows = list(reflection_service.list_reflections({"trace_id": source_trace_id}) or [])
    matches: list[tuple[Any, dict[str, Any]]] = []
    for row in rows:
        context = _reflection_context(row)
        if dataset_id and str(context.get("dataset_id") or "") not in {"", dataset_id}:
            continue
        adjustment = context.get("actionable_adjustment")
        if context.get("root_cause") and isinstance(adjustment, dict) and adjustment:
            matches.append((row, context))
    return matches


def build_turn2_learning_evolution_context(
    *,
    learning_service: Any,
    reflection_service: Any,
    dataset_id: str,
    dataset_fingerprint: str,
    previous_trace_id: str,
    current_trace_id: str,
) -> dict[str, Any]:
    learning_matches = _learning_records(
        learning_service,
        dataset_id=dataset_id,
        dataset_fingerprint=dataset_fingerprint,
        source_trace_id=previous_trace_id,
    )
    reflection_matches = _reflection_records(
        reflection_service,
        dataset_id=dataset_id,
        source_trace_id=previous_trace_id,
    )
    if not learning_matches:
        raise RuntimeError(f"No reusable Learning records found for {dataset_id}/{previous_trace_id}")
    if not reflection_matches:
        raise RuntimeError(f"No reusable Reflection records found for {dataset_id}/{previous_trace_id}")

    learning_row, learning_detail = learning_matches[-1]
    reflection_row, reflection_context = reflection_matches[-1]
    learning_trace_id = _record_id(learning_row, "trace_id")
    reflection_id = _record_id(reflection_row, "reflection_id")
    adjustment = reflection_context.get("actionable_adjustment")
    adjustment = adjustment if isinstance(adjustment, dict) else {}
    posture_hint = str(adjustment.get("q9_posture_hint") or "cautious_slow")
    precheck_action = str(adjustment.get("q4_add_action") or "precheck_risk_signal")

    learned_rule = {
        "dataset_id": dataset_id,
        "source_trace_id": previous_trace_id,
        "learning_trace_id": learning_trace_id,
        "reflection_id": reflection_id,
        "best_practice": learning_detail.get("best_practice"),
        "avoid_pattern": learning_detail.get("avoid_pattern"),
        "trigger_condition": learning_detail.get("trigger_condition"),
        "root_cause": reflection_context.get("root_cause"),
        "system_limitation": reflection_context.get("system_limitation"),
        "actionable_adjustment": adjustment,
    }
    # Q2/Q3 swap (commit 712af9ee)：learned rules / strategy patches 是资产维度，
    # 放入 Q2 asset_inventory.activated_strategy_patches。无兼容别名，调用方必须用 q2。
    q2 = {
        "dataset_id": dataset_id,
        "source_signal": "turn1_learning|turn1_reflection",
        "loaded_learning_ids": [learning_trace_id],
        "loaded_reflection_ids": [reflection_id],
        "learned_rules": [learned_rule],
        "activated_strategy_patches": [learned_rule],
    }
    trigger_condition = learning_detail.get("trigger_condition") if isinstance(learning_detail.get("trigger_condition"), dict) else {}
    risk_signal = str(trigger_condition.get("risk_signal") or reflection_context.get("risk_signal") or "prior_failure_risk")
    q4 = {
        "action_candidates": [
            {
                "action": precheck_action,
                "source_signal": "turn1_learning|turn1_reflection",
                "source_learning_trace_id": learning_trace_id,
                "source_reflection_id": reflection_id,
                "risk_signal": risk_signal,
            }
        ]
    }
    q8_task = {
        "task_id": "turn2-learned-precheck",
        "title": "Run learned risk precheck before full analysis",
        "task_scope": "internal",
        "target_id": "internal:task_constraint_checker",
        "metadata": {
            "dataset_id": dataset_id,
            "learned_rules_applied": [learned_rule],
            "source_learning_trace_id": learning_trace_id,
            "source_reflection_id": reflection_id,
            "source_signal": "turn1_learning|turn1_reflection",
        },
    }
    proactive_action = {
        "task_id": "turn2-known-risk-guard",
        "title": "Guard known risk before full analysis",
        "task_scope": "internal",
        "metadata": {
            "dataset_id": dataset_id,
            "source_signal": "turn1_learning|turn1_reflection",
            "source_learning_trace_id": learning_trace_id,
            "source_reflection_id": reflection_id,
            "suggestion": f"known risk signal requires precheck before full report: {risk_signal}",
        },
    }
    q9_profile = {
        "action_rhythm_hint": posture_hint,
        "conservative_mode_triggered": True,
        "posture_source": "turn1_reflection",
        "source_reflection_id": reflection_id,
    }
    return {
        "status": "succeeded",
        "dataset_id": dataset_id,
        "dataset_fingerprint": dataset_fingerprint,
        "previous_trace_id": previous_trace_id,
        "current_trace_id": current_trace_id,
        "learning_trace_id": learning_trace_id,
        "reflection_id": reflection_id,
        "learned_rule": learned_rule,
        # 返回结构：q2 = asset inventory（含 strategy patches）。
        # 不再返回 q3 字段；调用方必须迁移到 q2。
        "q2": q2,
        "q4": q4,
        "q8_next_tasks": [q8_task],
        "q8_proactive_actions": [proactive_action],
        "q9_evaluation_profile_overrides": q9_profile,
        "q9_result_overrides": {
            "action_rhythm_hint": posture_hint,
            "conservative_mode_triggered": True,
            "posture_source": "turn1_reflection",
            "source_reflection_id": reflection_id,
        },
    }
