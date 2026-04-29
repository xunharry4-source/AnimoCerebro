from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.tasks.experience.extractor import ExperienceExtractor
from zentex.tasks.experience.models import TaskOutcomeType
from zentex.tasks.verification.models import VerificationStrategy, VerificationType


def _verification_contract() -> dict:
    return {
        "verification": {
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "experience_required_receipt",
                    "verifier_type": VerificationType.RULE_BASED.value,
                    "retry_on_failure": False,
                    "max_retries": 0,
                    "config": {
                        "rules": [
                            {"type": "required_field", "field": "actual_outcome"},
                            {"type": "required_field", "field": "evidence"},
                        ]
                    },
                }
            ],
        },
        "success_criteria": ["actual_outcome and evidence are present"],
        "acceptance_conditions": ["verification_result.overall_passed is true"],
    }


async def _create_verified_task(real_ci_runtime, *, suffix: str, should_pass: bool):
    payload = task_payload(suffix=suffix, title_prefix="experience-outcome")
    payload["contract"] = _verification_contract()
    created = await real_ci_runtime.task_service.create_task(payload)
    result_payload = {"actual_outcome": {"artifact": f"outcome-{suffix}"}}
    if should_pass:
        result_payload["evidence"] = [f"real evidence {suffix}"]

    completion = await real_ci_runtime.task_service.complete_task_with_verification(
        created.task_id,
        result=result_payload,
        remarks=f"experience outcome binding {suffix}",
    )
    queried_task = real_ci_runtime.task_service.get_task(created.task_id)
    persisted_outcome = real_ci_runtime.task_service.get_task_outcome(created.task_id)

    assert queried_task is not None
    assert persisted_outcome is not None, "mutation 后必须能查询到 task_outcomes"
    assert persisted_outcome["task_id"] == created.task_id
    assert persisted_outcome["actual_outcome"] == {"artifact": f"outcome-{suffix}"}
    if should_pass:
        assert completion["success"] is True
        assert queried_task.status.value == "done"
        assert persisted_outcome["overall_passed"] is True
    else:
        assert completion["success"] is False
        assert queried_task.status.value == "failed"
        assert persisted_outcome["overall_passed"] is False
        assert persisted_outcome["deviation_report"]["failed_verifiers"] == ["experience_required_receipt"]
    return created


@pytest.mark.asyncio
async def test_experience_extractor_reads_success_from_real_task_outcome_not_keywords(real_ci_runtime) -> None:
    """查询链路：真实 memory 查询后，必须按 task_outcomes 判定成功，不能被失败关键词误导。"""
    suffix = unique_suffix()
    task = await _create_verified_task(real_ci_runtime, suffix=suffix, should_pass=True)
    memory = real_ci_runtime.memory_service.remember(
        title=f"structured outcome extraction success {suffix}",
        summary=f"structured outcome extraction success {suffix}",
        content=f"structured outcome extraction success {suffix} failed error timeout misleading text",
        source="tests",
        target_id=task.task_id,
        tags=["experience-outcome", suffix],
    )
    queried_memory = real_ci_runtime.memory_service.get_record(memory.memory_id)
    assert queried_memory is not None, "remember 后必须能按 memory_id 查询到记录"
    assert queried_memory.target_id == task.task_id

    extractor = ExperienceExtractor(
        memory_service=real_ci_runtime.memory_service,
        task_service=real_ci_runtime.task_service,
        similarity_threshold=0.1,
    )
    context = await extractor.extract_experience_context(
        task_title=f"structured outcome extraction success {suffix}",
        task_type="system_action",
    )

    matched = [item for item in context.similar_experiences if item.memory_id == memory.memory_id]
    assert matched, "真实 memory 查询结果必须包含刚写入的记录"
    assert matched[0].outcome == TaskOutcomeType.SUCCESS
    assert matched[0].executor_id == task.task_id
    assert all("300s" not in lesson.content for lesson in context.extracted_lessons)


@pytest.mark.asyncio
async def test_experience_extractor_reads_failure_from_real_task_outcome_not_keywords(real_ci_runtime) -> None:
    """查询链路：真实 memory 查询后，必须按 task_outcomes 判定失败，不能被成功关键词误导。"""
    suffix = unique_suffix()
    task = await _create_verified_task(real_ci_runtime, suffix=suffix, should_pass=False)
    memory = real_ci_runtime.memory_service.remember(
        title=f"structured outcome extraction failure {suffix}",
        summary=f"structured outcome extraction failure {suffix}",
        content=f"structured outcome extraction failure {suffix} success completed done misleading text",
        source="tests",
        target_id=task.task_id,
        tags=["experience-outcome", suffix],
    )
    assert real_ci_runtime.memory_service.get_record(memory.memory_id) is not None

    extractor = ExperienceExtractor(
        memory_service=real_ci_runtime.memory_service,
        task_service=real_ci_runtime.task_service,
        similarity_threshold=0.1,
    )
    context = await extractor.extract_experience_context(
        task_title=f"structured outcome extraction failure {suffix}",
        task_type="system_action",
    )

    matched = [item for item in context.similar_experiences if item.memory_id == memory.memory_id]
    assert matched, "真实 memory 查询结果必须包含刚写入的记录"
    assert matched[0].outcome == TaskOutcomeType.FAILURE
    assert matched[0].failure_reason is None
    assert context.executor_competency_map[task.task_id].failed_attempts == 1


def test_experience_extractor_refuses_legacy_keyword_inference_even_with_old_flag() -> None:
    """异常链路：没有结构化 outcome 时，关键词和旧兼容 flag 都不能判定成败。"""
    extractor = ExperienceExtractor()
    record = {
        "content": "success completed done failed error timeout",
        "summary": "ambiguous keyword-only record",
    }

    assert extractor._infer_outcome(record) == TaskOutcomeType.UNKNOWN
    assert extractor._infer_outcome({**record, "allow_legacy_keyword_outcome": True}) == TaskOutcomeType.UNKNOWN
