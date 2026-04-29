from __future__ import annotations

from typing import Any

from zentex.kernel.prompt_contracts import build_contract_summary
from zentex.nine_questions.plan_evidence_registry import build_plan_evidence_summary
from zentex.nine_questions.plan_execution_evidence import (
    EXECUTION_EVIDENCE_KINDS,
    build_plan_execution_evidence_summary,
)


class PlanCompletionGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]], report: dict[str, Any] | None = None) -> None:
        self.failures = failures
        self.report = report or {}
        super().__init__("Plan completion gate failed")


def build_plan_completion_gate_report(
    *,
    task_service: Any,
    session_id: str,
    learning_service: Any = None,
    expected_generated_count: int = 1,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if task_service is None or not callable(getattr(task_service, "list_tasks", None)):
        failures.append({"reason": "task_service_list_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_generated_count <= 0:
        failures.append({"reason": "expected_generated_count_must_be_positive", "expected": expected_generated_count})

    contract_summary = build_contract_summary()
    if contract_summary["consistency_errors"]:
        failures.append(
            {
                "reason": "prompt_contract_consistency_failed",
                "consistency_errors": contract_summary["consistency_errors"],
            }
        )

    generated_tasks: list[Any] = []
    receipts: list[dict[str, Any]] = []
    if not failures:
        generated_tasks = [
            task
            for task in task_service.list_tasks(metadata_filters={"session_id": session_id})
            if getattr(task, "metadata", {}).get("plan_verification_evidence", {}).get("source") == "generated_verification"
        ]
        generated_tasks.sort(key=lambda item: item.title)
        if len(generated_tasks) < expected_generated_count:
            failures.append(
                {
                    "reason": "generated_verification_count_below_required",
                    "required": expected_generated_count,
                    "actual": len(generated_tasks),
                }
            )
        for task in generated_tasks:
            metadata = getattr(task, "metadata", {})
            evidence = metadata.get("plan_verification_evidence") or {}
            outcome = task_service.get_task_outcome(task.task_id) if callable(getattr(task_service, "get_task_outcome", None)) else None
            if outcome is None:
                failures.append({"reason": "generated_task_outcome_missing", "task_id": task.task_id})
                outcome_passed = False
            else:
                outcome_passed = outcome.get("overall_passed") is True
                if not outcome_passed:
                    failures.append({"reason": "generated_task_outcome_failed", "task_id": task.task_id})
            receipts.append(
                {
                    "task_id": task.task_id,
                    "source": evidence.get("source"),
                    "production_history_claimed": evidence.get("production_history_claimed"),
                    "natural_week_observation_claimed": evidence.get("natural_week_observation_claimed"),
                    "phase_d_real_activation_claimed": evidence.get("phase_d_real_activation_claimed"),
                    "outcome_passed": outcome_passed,
                }
            )

    evidence_summary = None
    completion_kinds: set[str] = set()
    execution_summary = None
    execution_kinds: set[str] = set()
    if learning_service is not None:
        evidence_summary = build_plan_evidence_summary(learning_service=learning_service)
        completion_kinds = set(evidence_summary["completion_evidence_kinds"])
        execution_summary = build_plan_execution_evidence_summary(learning_service=learning_service)
        execution_kinds = set(execution_summary["completed_execution_evidence_kinds"])

    blocker_specs = [
        (
            "real_production_history",
            "real_production_history_source_missing",
            "真实生产导出文件、生产数据库或内部 API 历史任务来源",
        ),
        (
            "natural_week_observation",
            "natural_week_observation_missing",
            "连续自然周线上观测数据与误杀率/漂移率统计",
        ),
        (
            "online_q8_prompt_baseline",
            "online_q8_prompt_baseline_missing",
            "真实线上 Q8 baseline/current prompt、调用次数、延迟、token、质量记录",
        ),
        (
            "prompt_audit_report_set",
            "prompt_audit_reports_missing",
            "docs/q_audit/q1_audit.md 到 q9_audit.md 的 27 项真实 audit 归档",
        ),
        (
            "phase_d_shadow_canary_rollback",
            "phase_d_real_shadow_canary_rollback_missing",
            "Phase D0-D4 真实 replay/gold/shadow/canary/activation/rollback 演练证据",
        ),
        (
            "llm_reflection_quality",
            "llm_reflection_quality_evidence_missing",
            "真实 LLM provider 驱动的语义反思质量指标与审查证据",
        ),
    ]
    hard_blockers = [
        {
            "reason": reason,
            "required_evidence": required_evidence,
        }
        for source_kind, reason, required_evidence in blocker_specs
        if source_kind not in completion_kinds
    ]
    execution_blockers = [
        {
            "reason": "real_execution_evidence_missing",
            "required_evidence_kind": evidence_kind,
        }
        for evidence_kind in sorted(EXECUTION_EVIDENCE_KINDS - execution_kinds)
    ]
    failures.extend(hard_blockers)
    failures.extend(execution_blockers)
    report = {
        "gate_status": "failed" if failures else "passed",
        "phase": "plan_completion_gate",
        "session_id": session_id,
        "expected_generated_count": expected_generated_count,
        "generated_verification_count": len(generated_tasks),
        "contract_summary": contract_summary,
        "receipts": receipts,
        "blockers": hard_blockers,
        "execution_blockers": execution_blockers,
        "evidence_summary": evidence_summary,
        "execution_evidence_summary": execution_summary,
        "production_history_claimed": False,
        "full_plan_completion_claimed": False,
    }
    if failures:
        raise PlanCompletionGateError(failures, report)
    return report
