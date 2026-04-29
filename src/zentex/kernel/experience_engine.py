from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
IDENTITY_FORBIDDEN_KEYS = {
    "identity_override",
    "identity_overrides",
    "hard_constraints_override",
    "disable_identity_kernel",
    "remove_safety_constraint",
}


def register_experience_expectation(
    kernel: Any,
    *,
    session_id: str,
    task_id: str,
    expected_outcome: dict[str, Any],
    success_criteria: list[str],
    risk_assessment: Optional[dict[str, Any]] = None,
    source: str = "runtime",
) -> dict[str, Any]:
    if not session_id or not task_id:
        raise ValueError("session_id and task_id are required")
    if not expected_outcome:
        raise ValueError("expected_outcome is required")
    if not success_criteria:
        raise ValueError("success_criteria is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    task_service = _require_service(kernel, "_task_service", "task service")
    task = task_service.get_task(task_id)
    if task is None:
        raise KeyError(f"Task not found for G11 expectation: {task_id}")

    expectation_id = f"g11-expectation-{uuid4().hex}"
    record = {
        "feature_code": "G11",
        "expectation_id": expectation_id,
        "session_id": session_id,
        "task_id": task_id,
        "task_title": task.title,
        "expected_outcome": expected_outcome,
        "success_criteria": list(success_criteria),
        "risk_assessment": dict(risk_assessment or {}),
        "source": source,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _remember(kernel, record, kind="expectation")
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_experience_expectations", expectation_id, record)
    _append_transcript(state, record, "g11_experience_expectation_registered")
    return record


def bind_experience_outcome(
    kernel: Any,
    *,
    session_id: str,
    expectation_id: str,
    actual_outcome: dict[str, Any],
    benefits: Optional[list[str]] = None,
    losses: Optional[list[str]] = None,
    source_reliability: float = 0.8,
    strategy_patch: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id or not expectation_id:
        raise ValueError("session_id and expectation_id are required")
    if actual_outcome is None:
        raise ValueError("actual_outcome is required")
    if source_reliability < 0 or source_reliability > 1:
        raise ValueError("source_reliability must be within [0, 1]")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    expectation = getattr(kernel, "_experience_expectations", {}).get(expectation_id)
    if not expectation or expectation["session_id"] != session_id:
        raise KeyError(f"G11 expectation not found: {expectation_id}")

    task_service = _require_service(kernel, "_task_service", "task service")
    task_id = expectation["task_id"]
    task_outcome = task_service.get_task_outcome(task_id)
    deviation = _compare_outcome(expectation, actual_outcome, task_outcome)
    patch = _build_strategy_patch(
        expectation=expectation,
        deviation=deviation,
        source_reliability=source_reliability,
        requested_patch=strategy_patch or {},
    )
    if patch["identity_constraint_protected"] is False:
        raise ValueError("G11 strategy patch attempted to override IdentityKernel hard constraints")

    binding_id = f"g11-binding-{uuid4().hex}"
    record = {
        "feature_code": "G11",
        "binding_id": binding_id,
        "expectation_id": expectation_id,
        "session_id": session_id,
        "task_id": task_id,
        "expected_outcome": expectation["expected_outcome"],
        "success_criteria": expectation["success_criteria"],
        "actual_outcome": actual_outcome,
        "task_outcome": task_outcome,
        "deviation_report": deviation,
        "benefits": list(benefits or []),
        "losses": list(losses or []),
        "source_reliability": source_reliability,
        "strategy_patch": patch,
        "identity_kernel_constraints_preserved": True,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _remember(kernel, record, kind="outcome_binding")
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    reflection_id = _write_reflection(kernel, record)
    if reflection_id:
        record["evidence_refs"].append({"type": "reflection", "reflection_id": reflection_id})
    learning_trace_id = _write_learning(kernel, record)
    if learning_trace_id:
        record["evidence_refs"].append({"type": "learning", "trace_id": learning_trace_id})
    _cache_record(kernel, "_experience_bindings", binding_id, record)
    _cache_strategy_patch(kernel, patch, binding_id)
    _append_transcript(state, record, "g11_experience_outcome_bound")
    return record


def query_experience_binding(kernel: Any, *, session_id: str, binding_id: str) -> dict[str, Any]:
    if not session_id or not binding_id:
        raise ValueError("session_id and binding_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    record = getattr(kernel, "_experience_bindings", {}).get(binding_id)
    if not record or record["session_id"] != session_id:
        raise KeyError(f"G11 experience binding not found: {binding_id}")
    _append_transcript(state, record, "g11_experience_binding_queried")
    return {**record, "query_visible": True}


def rank_goals_with_experience(
    kernel: Any,
    *,
    session_id: str,
    candidate_goals: list[dict[str, Any]],
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not candidate_goals:
        raise ValueError("candidate_goals is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    patches = [
        patch
        for patch in getattr(kernel, "_strategy_patches", {}).values()
        if patch.get("session_id") == session_id
    ]
    ranked = []
    for goal in candidate_goals:
        goal_id = str(goal.get("goal_id") or uuid4().hex)
        goal_tags = {str(tag).lower() for tag in list(goal.get("tags") or [])}
        text = " ".join(
            str(goal.get(field) or "")
            for field in ("title", "summary", "description", "task_type")
        ).lower()
        score = float(goal.get("base_score", 0.5))
        cited: list[dict[str, Any]] = []
        for patch in patches:
            patch_tags = {str(tag).lower() for tag in patch.get("applies_to_tags", [])}
            applies = bool(goal_tags & patch_tags) if goal_tags else any(tag in text for tag in patch_tags)
            if not applies:
                continue
            adjustment = float(patch["score_delta"])
            score += adjustment
            cited.append(
                {
                    "binding_id": patch["binding_id"],
                    "patch_id": patch["patch_id"],
                    "score_delta": adjustment,
                    "lesson": patch["lesson"],
                }
            )
        ranked.append({**goal, "goal_id": goal_id, "experience_adjusted_score": round(score, 4), "experience_refs": cited})
    ranked.sort(key=lambda item: item["experience_adjusted_score"], reverse=True)
    report = {
        "feature_code": "G11",
        "session_id": session_id,
        "ranking_id": f"g11-ranking-{uuid4().hex}",
        "ranked_goals": ranked,
        "context": dict(context or {}),
        "created_at": datetime.now(UTC).isoformat(),
    }
    _append_transcript(state, report, "g11_experience_goals_ranked")
    return report


def _compare_outcome(expectation: dict[str, Any], actual_outcome: dict[str, Any], task_outcome: dict[str, Any] | None) -> dict[str, Any]:
    expected = expectation["expected_outcome"]
    matched_keys = [key for key, value in expected.items() if actual_outcome.get(key) == value]
    mismatched = [
        {"field": key, "expected": value, "actual": actual_outcome.get(key)}
        for key, value in expected.items()
        if actual_outcome.get(key) != value
    ]
    task_passed = None if task_outcome is None else bool(task_outcome.get("overall_passed"))
    passed = not mismatched and task_passed is not False
    return {
        "expected_fields": expected,
        "matched_fields": matched_keys,
        "mismatched_fields": mismatched,
        "task_outcome_overall_passed": task_passed,
        "passed": passed,
        "deviation_score": round(len(mismatched) / max(1, len(expected)), 4),
    }


def _build_strategy_patch(
    *,
    expectation: dict[str, Any],
    deviation: dict[str, Any],
    source_reliability: float,
    requested_patch: dict[str, Any],
) -> dict[str, Any]:
    if any(key in requested_patch for key in IDENTITY_FORBIDDEN_KEYS):
        return {"identity_constraint_protected": False}
    passed = bool(deviation["passed"])
    task_text = f"{expectation.get('task_title', '')} {expectation.get('task_id', '')}".lower()
    applies = list(dict.fromkeys([part for part in task_text.replace("-", " ").split() if len(part) > 3]))[:8]
    confidence = round((0.55 if passed else 0.72) * source_reliability, 4)
    return {
        "patch_id": f"g11-strategy-patch-{uuid4().hex}",
        "patch_type": "promote_strategy" if passed else "avoid_or_replan_strategy",
        "lesson": requested_patch.get("lesson") or ("repeat_success_pattern" if passed else "avoid_failed_pattern_and_generate_alternative"),
        "applies_to_tags": requested_patch.get("applies_to_tags") or applies,
        "score_delta": round((0.12 if passed else -0.25) * source_reliability, 4),
        "confidence": confidence,
        "source_reliability": source_reliability,
        "identity_constraint_protected": True,
        "structured": True,
    }


def _write_reflection(kernel: Any, record: dict[str, Any]) -> str | None:
    reflection_service = getattr(kernel, "_reflection_service", None)
    if reflection_service is None or not callable(getattr(reflection_service, "record_nine_question_reflection", None)):
        return None
    from zentex.reflection.models import ReflectionType

    reflection = reflection_service.record_nine_question_reflection(
        subject=f"G11 outcome binding: {record['task_id']}",
        reflection_type=ReflectionType.OUTCOME_REFLECTION,
        trace_id=record["binding_id"],
        context={"source": "g11_experience_engine", **record},
    )
    reflection_id = str(getattr(reflection, "reflection_id", "") or "")
    if reflection_id and getattr(reflection_service.get_reflection(reflection_id), "reflection_id", None) != reflection_id:
        raise RuntimeError(f"G11 reflection writeback query verification failed: {reflection_id}")
    return reflection_id or None


def _write_learning(kernel: Any, record: dict[str, Any]) -> str | None:
    learning_service = getattr(kernel, "_learning_service", None)
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        return None
    learning = learning_service.record_nine_question_learning(
        question_id="G11",
        learning_kind="experience_outcome_binding",
        trace_id=record["binding_id"],
        detail={"source": "g11_experience_engine", **record},
    )
    trace_id = str(getattr(learning, "trace_id", "") or "")
    if trace_id:
        records = learning_service.query_overall_records(limit=20, trace_id=trace_id)
        if not any(item.detail.get("binding_id") == record["binding_id"] for item in records):
            raise RuntimeError(f"G11 learning writeback query verification failed: {trace_id}")
    return trace_id or None


def _remember(kernel: Any, record: dict[str, Any], *, kind: str) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    identifier = record.get("binding_id") or record.get("expectation_id")
    memory = memory_service.remember(
        title=f"G11 {kind} {identifier}",
        summary=f"G11 {kind} task={record['task_id']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g11_experience_engine",
        trace_id=str(identifier),
        target_id=record["task_id"],
        tags=["G11", "experience", kind],
        experience_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if memory_id and getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G11 memory writeback query verification failed: {memory_id}")
    return memory_id or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _cache_strategy_patch(kernel: Any, patch: dict[str, Any], binding_id: str) -> None:
    if not hasattr(kernel, "_strategy_patches"):
        setattr(kernel, "_strategy_patches", {})
    binding = getattr(kernel, "_experience_bindings", {}).get(binding_id, {})
    kernel._strategy_patches[patch["patch_id"]] = {
        **patch,
        "binding_id": binding_id,
        "session_id": binding.get("session_id"),
    }


def _require_service(kernel: Any, attr: str, label: str) -> Any:
    service = getattr(kernel, attr, None)
    if service is None:
        raise RuntimeError(f"G11 requires {label}")
    return service


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G11", "entry_type": entry_type, **record},
        )
    )
