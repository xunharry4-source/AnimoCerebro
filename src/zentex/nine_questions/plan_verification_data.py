from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from zentex.kernel.prompt_contracts import build_contract_summary
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


class PlanVerificationDataError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Plan verification data generation failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot(session_id: str, sample_count: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index in range(sample_count):
        rows.append(
            {
                "task_id": f"plan-verification-{index:03d}",
                "title": f"Plan generated verification sample #{index:03d}",
                "priority": "high" if index % 3 == 0 else "medium",
                "reason": "generated local verification data for fail-closed plan gates",
                "expected_outcome": {
                    "session_id": session_id,
                    "sample_index": index,
                    "verification_scope": ["meta_value_loop", "prompt_engineering", "prompt_contracts", "self_evolution"],
                },
                "success_criteria": [
                    "task is persisted through real TaskService",
                    "verification outcome is queryable after completion",
                    "metadata is written and read back exactly",
                ],
                "acceptance_conditions": [
                    "generated data is explicitly marked generated_verification",
                    "production_history_claimed is false",
                    "prompt contract count is nine",
                    "Phase D evidence is marked as engineering rehearsal only",
                ],
                "verification_method": "rule_based_outcome_contract",
                "risk_assessment": {
                    "risk_level": "medium",
                    "fake_completion_guard": "do_not_claim_production_history",
                },
            }
        )
    return {
        "q8": {
            "trace_id": f"trace-plan-verification-{session_id}",
            "summary": "Plan generated verification data writer",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": "Generate queryable local verification data without claiming production completion",
                    "primary_objectives": [
                        "persist verification samples in the real TaskService database",
                        "preserve fail-closed production evidence gates",
                    ],
                    "secondary_objectives": [
                        "cover prompt contract registry evidence",
                        "cover Phase D governance rehearsal evidence",
                    ],
                    "completion_conditions": [
                        "all generated samples have task_outcomes",
                        "all generated samples have exact metadata readback",
                    ],
                    "pause_conditions": ["real production export or natural-week observation is missing"],
                    "escalation_conditions": ["generated data is used as production evidence"],
                },
                "q8_task_queue": {
                    "next_self_tasks": rows,
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


def _verification_metadata(*, task: Any, index: int, generated_at: str) -> dict[str, Any]:
    contract_summary = build_contract_summary()
    return {
        "plan_verification_evidence": {
            "source": "generated_verification",
            "environment": "local_acceptance_db",
            "generated_at": generated_at,
            "sample_index": index,
            "phase_a_lens_evidence": True,
            "prompt_gate_evidence": True,
            "contract_registry_version": "initial",
            "phase_d_governance_rehearsal": True,
            "question_contract_count": contract_summary["question_count"],
            "cross_q_consistency_errors": contract_summary["consistency_errors"],
            "production_history_claimed": False,
            "natural_week_observation_claimed": False,
            "phase_d_real_activation_claimed": False,
        },
        "q8_prompt_v2_metrics": {
            "source": "generated_verification",
            "environment": "local_acceptance_db",
            "sample_id": f"generated-plan-{task.task_id}",
            "q8_trace_id": task.metadata.get("trace_id"),
            "evidence_uri": f"task-service://generated-verification/{task.task_id}",
            "baseline_prompt_chars": 12000,
            "current_prompt_chars": 3900,
            "baseline_llm_calls": 3,
            "current_llm_calls": 1,
            "baseline_latency_ms": 10000,
            "current_latency_ms": 5500,
            "baseline_token_cost": 6000,
            "current_token_cost": 2400,
            "baseline_quality_score": 0.82,
            "current_quality_score": 0.84,
        },
        "phase_d_verification": {
            "source": "generated_verification",
            "environment": "local_acceptance_db",
            "d0_prompt_registry": "engineering_rehearsal",
            "d1_q8_pilot": "engineering_rehearsal",
            "d2_q1_q2_extension": "engineering_rehearsal",
            "d3_q5_q7_extension": "engineering_rehearsal",
            "d4_q3_q4_q6_q9_extension": "engineering_rehearsal",
            "real_shadow_canary_activation_claimed": False,
            "real_rollback_drill_claimed": False,
        },
    }


async def generate_plan_verification_data(
    *,
    task_service: Any,
    session_id: str,
    sample_count: int = 100,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if task_service is None or not callable(getattr(task_service, "list_tasks", None)):
        failures.append({"reason": "task_service_list_missing"})
    if task_service is None or not callable(getattr(task_service, "update_task_metadata", None)):
        failures.append({"reason": "task_service_update_metadata_missing"})
    if task_service is None or not callable(getattr(task_service, "complete_task_with_verification", None)):
        failures.append({"reason": "task_service_verification_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if sample_count <= 0:
        failures.append({"reason": "sample_count_must_be_positive", "sample_count": sample_count})
    contract_summary = build_contract_summary()
    if contract_summary["consistency_errors"]:
        failures.append(
            {
                "reason": "prompt_contract_consistency_failed",
                "consistency_errors": contract_summary["consistency_errors"],
            }
        )
    if failures:
        raise PlanVerificationDataError(failures)

    await sync_q8_tasks_to_task_service(
        task_service=task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, sample_count),
    )
    tasks = list(task_service.list_tasks(metadata_filters={"session_id": session_id}) or [])
    tasks = [
        task
        for task in tasks
        if getattr(task, "metadata", {}).get("source") == "nine_questions.q8"
        and str(getattr(task, "metadata", {}).get("trace_id") or "").startswith("trace-plan-verification-")
    ]
    tasks.sort(key=lambda item: item.title)
    if len(tasks) != sample_count:
        raise PlanVerificationDataError(
            [
                {
                    "reason": "generated_task_count_mismatch",
                    "expected": sample_count,
                    "actual": len(tasks),
                }
            ]
        )

    generated_at = _now_iso()
    receipts: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        completed = await task_service.complete_task_with_verification(
            task.task_id,
            result={
                "actual_outcome": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "session_id": session_id,
                    "sample_index": index,
                    "source": "generated_verification",
                    "production_history_claimed": False,
                },
                "evidence": [
                    f"real TaskService task persisted: {task.task_id}",
                    f"real TaskService outcome query required for sample {index}",
                ],
            },
            remarks="Plan generated verification outcome",
        )
        if completed.get("success") is not True:
            raise PlanVerificationDataError(
                [
                    {
                        "reason": "verification_completion_failed",
                        "task_id": task.task_id,
                        "result": completed,
                    }
                ]
            )
        outcome = task_service.get_task_outcome(task.task_id)
        if not outcome or outcome.get("overall_passed") is not True:
            raise PlanVerificationDataError(
                [
                    {
                        "reason": "task_outcome_readback_failed",
                        "task_id": task.task_id,
                        "outcome": outcome,
                    }
                ]
            )

        metadata = _verification_metadata(task=task, index=index, generated_at=generated_at)
        await task_service.update_task_metadata(
            task.task_id,
            metadata,
            remarks="Plan generated verification metadata recorded",
        )
        refreshed = task_service.get_task(task.task_id)
        refreshed_metadata = getattr(refreshed, "metadata", {}) if refreshed is not None else {}
        for key, expected_value in metadata.items():
            if refreshed_metadata.get(key) != expected_value:
                raise PlanVerificationDataError(
                    [
                        {
                            "reason": "metadata_readback_mismatch",
                            "task_id": task.task_id,
                            "metadata_key": key,
                        }
                    ]
                )
        receipts.append(
            {
                "task_id": task.task_id,
                "title": task.title,
                "source": metadata["plan_verification_evidence"]["source"],
                "production_history_claimed": False,
                "outcome_passed": outcome["overall_passed"],
                "sample_index": index,
            }
        )

    refreshed_tasks = task_service.list_tasks(metadata_filters={"session_id": session_id})
    generated = [
        task
        for task in refreshed_tasks
        if getattr(task, "metadata", {}).get("plan_verification_evidence", {}).get("source") == "generated_verification"
    ]
    return {
        "verification_data_status": "generated",
        "session_id": session_id,
        "sample_count": sample_count,
        "persisted_task_count": len(tasks),
        "persisted_outcome_count": sum(1 for task in tasks if task_service.get_task_outcome(task.task_id)),
        "metadata_verified_count": len(generated),
        "real_database": True,
        "source": "generated_verification",
        "production_history_claimed": False,
        "full_plan_completion_claimed": False,
        "contract_summary": contract_summary,
        "receipts": receipts,
    }
