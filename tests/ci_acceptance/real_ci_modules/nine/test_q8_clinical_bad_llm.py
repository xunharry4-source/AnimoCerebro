from __future__ import annotations

import asyncio
import os
import pytest
import sys
import logging
from pathlib import Path

# 确保路径
repo_root = Path(__file__).resolve().parents[4]
if str(repo_root / "src") not in sys.path:
    sys.path.append(str(repo_root / "src"))
if str(repo_root / "tests/ci_acceptance") not in sys.path:
    sys.path.append(str(repo_root / "tests/ci_acceptance"))

from zentex.plugins.service import get_service as get_plugin_service
from zentex.llm.service import get_service as get_llm_service
from zentex.nine_questions.service import NineQuestionService
from zentex.kernel.cognition_flow import DEFAULT_NINE_QUESTIONS
from zentex.web_console.di_container import WebConsoleContainer

# Core Services
from zentex.foundation.service import get_service as get_foundation_service
from zentex.environment.service import get_service as get_environment_service
from zentex.audit.service import get_service as get_audit_service
from zentex.learning.service import get_service as get_learning_service
from zentex.memory.service import get_memory_service
from zentex.reflection.service import get_service as get_reflection_service
from zentex.tasks.service import get_service as get_task_service
from llm_output_assertions import assert_llm_output_integrity, assert_no_snapshot_fallback
from nine_question_history_assertions import assert_question_history_version_exists

CI_ACCEPTANCE_OLLAMA_MODEL = os.getenv(
    "CI_ACCEPTANCE_OLLAMA_MODEL",
    "gemma4:latest",
).strip()
CI_ACCEPTANCE_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("CI_ACCEPTANCE_REQUEST_TIMEOUT_SECONDS", "240").strip()
)


def _build_question_parameters(question_id: str, question_text: str) -> dict:
    return {
        "question_id": question_id,
        "question_text": question_text,
        "model_provider": "__bad_llm_provider__",
        "llm_model": "__bad_llm_model__",
        "model": "__bad_llm_model__",
        "request_timeout_seconds": 5,
    }


def _is_completed_status(status: object) -> bool:
    text = str(status or "").strip().lower()
    return text in {"done", "completed", "taskstatus.done", "taskstatus.completed"}


def _execute_with_retry(
    *,
    plugin_service,
    plugin_id: str,
    task_id: str,
    parameters: dict,
    trace_id: str,
    originator_id: str,
    max_attempts: int = 3,
):
    last_response = None
    for attempt in range(1, max_attempts + 1):
        response = plugin_service.execute_plugin_once_sync(
            plugin_id=plugin_id,
            task_id=task_id,
            parameters=parameters,
            trace_id=trace_id,
            originator_id=originator_id,
        )
        last_response = response
        if _is_completed_status(getattr(response, "status", None)):
            return response
        if attempt < max_attempts:
            continue
    return last_response


@pytest.mark.asyncio
async def test_q8_clinical_comprehensive():
    """
    Q8 临床验收测试：验证认知决策及任务同步到任务模块。
    """
    print("\n" + "="*60)
    print("STARTING Q8 CLINICAL ACCEPTANCE TEST")
    print("="*60)

    # 1. 初始化系统环境（真实业务路径，不清理历史数据）
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()
    
    # 2. 准备服务并注入真实依赖
    llm_service = get_llm_service()
    
    plugin_service = get_plugin_service()
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()
    audit_svc = get_audit_service()
    learning_svc = get_learning_service()
    memory_svc = get_memory_service()
    reflection_svc = get_reflection_service()
    task_svc = get_task_service()
    
    # 3. 注入依赖到内核
    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        foundation_service=foundation_service,
        environment_service=environment_service,
        audit_service=audit_svc,
        learning_service=learning_svc,
        memory_service=memory_svc,
        reflection_service=reflection_svc,
        agent_service=task_svc # 通常任务模块注入为 agent_service
    )
    plugin_service.attach_cognitive_services(
        llm_service=llm_service,
        memory_service=memory_svc,
        reflection_service=reflection_svc,
    )
    plugin_service.register_discovered_plugins()
    plugin_service.rehydrate_registered_plugins()
    
    # 4. 执行 Q8（只读取已存在的上游最新合格快照，不补跑上游题目）
    nq_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager()
    )

    q_id = "q8"
    q = next(item for item in DEFAULT_NINE_QUESTIONS if item.question_id == q_id)
    trace_id = "ci-acceptance-trace-q8"

    try:
        await nq_service.assert_latest_qualified_upstreams(q_id)
    except Exception as exc:
        raise AssertionError(
            f"Q8 prerequisite gate failed. Upstreams must already be latest-qualified snapshots. {exc}"
        ) from exc

    print(f"[Clinical] Executing {q_id}...")
    response = _execute_with_retry(
        plugin_service=plugin_service,
        plugin_id=q.plugin_id,
        task_id="ci-acceptance:q8",
        parameters=_build_question_parameters(q.question_id, q.text),
        trace_id=trace_id,
        originator_id="clinical-test",
        max_attempts=1,
    )
    assert _is_completed_status(getattr(response, "status", None)), (
        f"Execution failed: {getattr(response, 'error', 'unknown error')} - "
        f"Remarks: {getattr(response, 'remarks', 'no remarks')}"
    )
    
    # 5. 验证数据库与权威状态 (Q8)
    state_mgr = facade.get_nine_question_state_manager()
    db_state = await state_mgr.get_state("nq-baseline")
    assert q_id in db_state.question_snapshots, "Q8 not persisted"
    assert_question_history_version_exists(db_state, q_id)
    
    record = await nq_service.get_question_record(q_id)
    composed = record.get("composed", {})
    assert record.get("status", {}).get("status") == "completed", "Authoritative record for q8 not marked completed"
    summary = composed.get("summary", {})
    assert str(summary.get("answer") or summary.get("summary") or "").strip(), "No usable summary text found for q8"

    # 6. 内部模块运行检查（module_runs + modules 持久化）
    raw = composed.get("raw", {})
    context_updates = raw.get("context_updates", {})
    diagnosis = context_updates.get("q8_execution_diagnosis", {})
    assert isinstance(diagnosis, dict) and diagnosis, "Missing diagnosis payload for q8"
    assert_no_snapshot_fallback(diagnosis, q_id)
    authenticity = diagnosis.get("authenticity_status")
    assert authenticity == "completed", f"Unexpected authenticity status for q8: {authenticity}"
    module_runs = diagnosis.get("module_runs", {}) if isinstance(diagnosis, dict) else {}
    if isinstance(module_runs, dict):
        module_runs = list(module_runs.values())
    assert isinstance(module_runs, list) and module_runs, "No module_runs found in q8 execution diagnosis"

    required_run_modules = {
        "q8_snapshot_validation",
        "q8_task_state_load",
        "q8_functional_objective_chain",
        "q8_priority_derivation",
        "q8_decision_projection",
        "q8_task_persistence",
    }
    executed_module_ids = {
        str(item.get("module_id") or "").strip()
        for item in module_runs
        if isinstance(item, dict)
    }
    missing_run_modules = required_run_modules - executed_module_ids
    assert not missing_run_modules, f"Missing required q8 module runs: {sorted(missing_run_modules)}"

    modules_payload = await nq_service.get_question_modules(q_id)
    module_map = modules_payload.get("modules", {})
    assert isinstance(module_map, dict) and module_map, "No persisted module payload for q8"

    required_persisted_modules = {
        "q8_snapshot_validation",
        "q8_task_state_load",
        "q8_functional_objective_chain",
        "q8_priority_derivation",
        "q8_decision_projection",
        "q8_task_persistence",
        "q8_memory_integration",
        "q8_reflection_integration",
    }
    for module_id in required_persisted_modules:
        assert module_id in module_map, f"Module {module_id} missing in persisted module map"
        module_entry = module_map[module_id]
        assert isinstance(module_entry, dict), f"Module {module_id} entry must be dict"
        module_status = str(module_entry.get("status") or "").strip()
        assert module_status in {"completed", "ready"}, (
            f"Module {module_id} is not fully completed: {module_status}"
        )

    assert_llm_output_integrity(
        question_id=q_id,
        composed=composed,
        context_updates=context_updates,
    )

    # 7. 验证任务模块同步 (核心要求)
    print("[Clinical] Verifying Task Module Synchronization...")
    tasks = task_svc.list_tasks()
    # 检查是否有任务是由 Q8 产生的
    # Q8 插件通常会在任务描述或元数据中包含 q8 标识
    q8_tasks = [t for t in tasks if "Q8" in str(t.description) or "q8" in str(t.metadata)]
    
    # 严格真实链路：任务同步必须来自 Q8 实际执行结果，禁止 stub/fake 放行。
    assert len(q8_tasks) > 0, "Task Module: No tasks synchronized from Q8"
    print(f"[Clinical] ✓ Task Module: {len(q8_tasks)} tasks found in registry")

    # 8. 记忆写入检查（必须存在 q8 相关记录）
    memory_records = memory_svc.query_managed_records(limit=100)
    assert isinstance(memory_records, list), "memory_service.query_managed_records must return list"
    assert any(
        "q8" in str(getattr(item, "title", "")).lower()
        or "q8" in str(getattr(item, "summary", "")).lower()
        or "q8" in " ".join(getattr(item, "tags", []) or []).lower()
        for item in memory_records
    ), "No Q8-related memory record found"

    # 9. 反思写入检查（必须存在 q8 相关反思）
    reflection_records = reflection_svc.list_reflections({})
    assert isinstance(reflection_records, list), "reflection_service.list_reflections must return list"
    assert any(
        "q8" in str(getattr(item, "subject", "")).lower()
        or "q8" in str((getattr(item, "context", {}) or {}).get("question_id", "")).lower()
        for item in reflection_records
    ), "No Q8-related reflection record found"

    # 10. 审计写入检查（必须存在 q8 相关审计流）
    audit_flows = audit_svc.query_flows(flow_type="nine_questions", limit=200)
    assert isinstance(audit_flows, list), "audit_service.query_flows must return list"
    assert any("q8" in str(item).lower() for item in audit_flows), "No Q8-related audit flow found"

    # 11. 学习写入检查（必须存在 q8 相关学习记录）
    learning_entries = learning_svc.list_history_entries(limit=200)
    assert isinstance(learning_entries, list), "learning_service.list_history_entries must return list"
    assert any("q8" in str(item).lower() for item in learning_entries), "No Q8-related learning entry found"

    print(f"\n[Clinical] {q_id.upper()} CLINICAL ACCEPTANCE PASSED.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q8_clinical_comprehensive())
