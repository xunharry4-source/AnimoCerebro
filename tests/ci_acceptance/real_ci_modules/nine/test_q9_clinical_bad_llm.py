from __future__ import annotations

import asyncio
import pytest
import os
import sys
import logging
from pathlib import Path

# 确保 src/ 目录在路径中，以便手动执行
repo_root = Path(__file__).resolve().parents[4]
if str(repo_root / "src") not in sys.path:
    sys.path.append(str(repo_root / "src"))

from zentex.plugins.service import get_service as get_plugin_service
from zentex.llm.service import get_service as get_llm_service
from zentex.audit.service import get_service as get_audit_service
from zentex.learning.service import get_service as get_learning_service
from zentex.memory.service import get_service as get_memory_service
from zentex.reflection.service import get_service as get_reflection_service
from zentex.nine_questions.service import NineQuestionService
from zentex.kernel.cognition_flow import DEFAULT_NINE_QUESTIONS
from zentex.web_console.di_container import WebConsoleContainer
from tests.ci_acceptance.llm_output_assertions import (
    assert_llm_output_integrity,
    assert_no_snapshot_fallback,
)
from tests.ci_acceptance.nine_question_history_assertions import (
    assert_question_history_version_exists,
)

CI_ACCEPTANCE_OLLAMA_MODEL = os.getenv(
    "CI_ACCEPTANCE_OLLAMA_MODEL",
    "gemma4:latest",
).strip()
CI_ACCEPTANCE_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("CI_ACCEPTANCE_REQUEST_TIMEOUT_SECONDS", "90").strip()
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


def _extract_blocked_upstreams(error_text: str, ordered_upstreams: tuple[str, ...]) -> list[str]:
    text = (error_text or "").lower()
    blocked = [qid for qid in ordered_upstreams if f"{qid}:" in text]
    return blocked or list(ordered_upstreams)


async def _stabilize_prerequisites(
    *,
    plugin_service,
    nq_service: NineQuestionService,
    target_question_id: str,
    ordered_upstreams: tuple[str, ...],
    max_rounds: int = 3,
) -> None:
    last_error = ""
    for _ in range(max_rounds):
        try:
            await nq_service.assert_latest_qualified_upstreams(target_question_id)
            return
        except Exception as exc:
            last_error = str(exc)

        blocked_upstreams = _extract_blocked_upstreams(last_error, ordered_upstreams)
        for upstream_id in blocked_upstreams:
            upstream_q = next(item for item in DEFAULT_NINE_QUESTIONS if item.question_id == upstream_id)
            upstream_response = _execute_with_retry(
                plugin_service=plugin_service,
                plugin_id=upstream_q.plugin_id,
                task_id=f"ci-acceptance:{upstream_id}:for-{target_question_id}",
                parameters=_build_question_parameters(upstream_q.question_id, upstream_q.text),
                trace_id=f"ci-acceptance-trace-{upstream_id}-for-{target_question_id}",
                originator_id="clinical-test",
                max_attempts=1,
            )
            assert _is_completed_status(getattr(upstream_response, "status", None)), (
                f"{upstream_id.upper()} prerequisite execution failed: {getattr(upstream_response, 'error', '')} "
                f"{getattr(upstream_response, 'remarks', '')}"
            )
            await nq_service.clear_question_dirty(
                upstream_id,
                reason=f"{target_question_id}_clinical_prerequisite",
            )

    raise AssertionError(
        f"{target_question_id.upper()} prerequisite cannot reach latest-qualified state: {last_error}"
    )


@pytest.mark.asyncio
async def test_q9_clinical_authenticity():
    """
    Q9 临床验收测试：验证认知真实性与服务层完整性。
    
    本测试严格遵循“临床级验证”原则，核心检查点包括：
    1. **服务真实性**：必须通过官方 Service 接口（zentex.plugins.service）执行，严禁 Mock 核心逻辑。
    2. **依赖注入完整性**：验证 LLM 服务和插件运行时是否已正确绑定并注入执行上下文。
    3. **物理状态一致性**：必须通过权威查询接口（zentex.nine_questions.service）验证数据库中的持久化状态。
    4. **真实性判定 (Authenticity)**：检查执行诊断中的 `authenticity_status`，确保输出源自真实推理而非硬编码或伪造数据。
    
    验证要求：
    - 必须物理执行，产生真实审计日志。
    - 严禁绕过服务层直接操作数据库。
    """
    
    # 1. 初始化真实系统服务 (拒绝 Mock)
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()
    llm_service = get_llm_service()
    plugin_service = get_plugin_service()
    audit_service = get_audit_service()
    learning_service = get_learning_service()
    memory_service = get_memory_service()
    reflection_service = get_reflection_service()
    
    # 权威查询服务
    nq_query_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager(),
    )
    
    # 2. 依赖注入与系统引导 (模拟真实启动链路)
    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        audit_service=audit_service,
        learning_service=learning_service,
        memory_service=memory_service,
        reflection_service=reflection_service,
    )
    
    # 物理验证注入状态，确保执行上下文包含 LLM
    if plugin_service._execution_service._llm_service is None:
        print("[Clinical] CRITICAL: llm_service injection failed!")
    plugin_service.attach_cognitive_services(
        llm_service=llm_service,
        audit_service=audit_service,
        learning_service=learning_service,
        memory_service=memory_service,
        reflection_service=reflection_service,
    )
    
    assert plugin_service._execution_service._llm_service is not None, "LLM Service not injected into ExecutionService"
    
    # 物理注册并重构插件实例
    plugin_service.register_discovered_plugins()
    plugin_service.rehydrate_registered_plugins()
    
    # 3. 获取问题定义
    q = next(q for q in DEFAULT_NINE_QUESTIONS if q.question_id == "q9")
    trace_id = "ci-acceptance-trace-q9"
    print(f"\n[Clinical] Executing {q.question_id} via SystemPluginService...")
    
    # 4. 执行插件 (真实调用)
    # 这将触发真实的推理链，如果环境中 Ollama 宕机，此处应显式报错
    response = _execute_with_retry(
        plugin_service=plugin_service,
        plugin_id=q.plugin_id,
        task_id="ci-acceptance:q9",
        parameters=_build_question_parameters(q.question_id, q.text),
        trace_id=trace_id,
        originator_id="clinical-test",
        max_attempts=3,
    )
    
    assert _is_completed_status(getattr(response, "status", None)), f"Execution failed: {getattr(response, 'error', 'unknown error')} - Remarks: {getattr(response, 'remarks', 'no remarks')}"
    
    # 5. 通过权威 Service 查询持久化状态
    print(f"[Clinical] Querying {q.question_id} via NineQuestionService...")
    state_mgr = facade.get_nine_question_state_manager()
    db_state = await state_mgr.get_state("nq-baseline")
    assert q.question_id in db_state.question_snapshots, f"{q.question_id} not persisted in authoritative database snapshots"
    assert_question_history_version_exists(db_state, q.question_id)

    record = await nq_query_service.get_question_record(q.question_id)
    
    assert record is not None, f"No authoritative record found for {q.question_id}"
    assert record.get("status", {}).get("status") == "completed", f"Authoritative record for {q.question_id} not marked completed"
    
    composed = record.get("composed", {})
    summary = composed.get("summary", {})
    assert str(summary.get("answer") or summary.get("summary") or "").strip(), (
        f"No usable summary text found for {q.question_id}"
    )
    
    # 6. 真实性验证 (Authenticity Validation)
    raw = composed.get("raw", {})
    context_updates = raw.get("context_updates", {})
    diagnosis = context_updates.get(f"{q.question_id}_execution_diagnosis", {})
    assert isinstance(diagnosis, dict) and diagnosis, f"Missing diagnosis payload for {q.question_id}"
    assert_no_snapshot_fallback(diagnosis, q.question_id)
    
    authenticity = diagnosis.get("authenticity_status")
    print(f"[Clinical] Q9 Authenticity Status: {authenticity}")
    
    # 预期状态：已实现的问题为 'completed'，其他为 'ready' 或 'partial'
    # 关键在于绝不能是 'fake' 或 'mocked'
    assert authenticity == "completed", f"Unexpected authenticity status for {q.question_id}: {authenticity}"

    # 7. 内部模块运行检查（module_runs + modules 持久化视图）
    module_runs = diagnosis.get("module_runs", {}) if isinstance(diagnosis, dict) else {}
    if isinstance(module_runs, dict):
        module_runs = list(module_runs.values())
    assert isinstance(module_runs, list) and len(module_runs) > 0, "No module_runs found in q9 execution diagnosis"

    required_run_modules = {
        "q9_functional_posture_chain",
        "q9_q1_q8_validation",
        "q9_self_model_source_validation",
        "q9_reasoning_budget_source_validation",
        "q9_posture_control_projection",
    }
    executed_module_ids = {
        str(item.get("module_id") or "").strip()
        for item in module_runs
        if isinstance(item, dict)
    }
    missing_run_modules = required_run_modules - executed_module_ids
    assert not missing_run_modules, f"Missing required q9 module runs: {sorted(missing_run_modules)}"

    modules_payload = await nq_query_service.get_question_modules(q.question_id)
    module_map = modules_payload.get("modules", {})
    assert isinstance(module_map, dict) and module_map, "No persisted module payload for q9"

    required_persisted_modules = {
        "q9_q1_q8_validation",
        "q9_self_model_source_validation",
        "q9_reasoning_budget_source_validation",
        "q9_posture_baseline_projection",
        "q9_posture_control_projection",
        "q9_memory_integration",
        "q9_reflection_integration",
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
        question_id=q.question_id,
        composed=composed,
        context_updates=context_updates,
    )

    # 8. 记忆写入检查（必须可查询到 trace_id 对应记录）
    memory_records = memory_service.query_managed_records(trace_id=trace_id, limit=100)
    assert isinstance(memory_records, list), "memory_service.query_managed_records must return list"
    assert any(
        "q9" in str(getattr(item, "title", "")).lower()
        or "q9" in str(getattr(item, "summary", "")).lower()
        or "q9" in " ".join(getattr(item, "tags", []) or []).lower()
        for item in memory_records
    ), "No Q9-related memory record found for trace_id"

    # 9. 反思写入检查（必须可查询到 trace_id 对应反思）
    reflection_records = reflection_service.list_reflections({"trace_id": trace_id})
    assert isinstance(reflection_records, list), "reflection_service.list_reflections must return list"
    assert any(
        str(getattr(item, "trace_id", "") or "") == trace_id
        or "q9" in str(getattr(item, "subject", "")).lower()
        or "q9" in str((getattr(item, "context", {}) or {}).get("question_id", "")).lower()
        for item in reflection_records
    ), "No Q9-related reflection record found for trace_id"

    # 10. 审计写入检查
    audit_flows = audit_service.query_flows(flow_type="nine_questions", limit=200)
    assert isinstance(audit_flows, list), "audit_service.query_flows must return list"
    assert any("q9" in str(item).lower() or trace_id in str(item) for item in audit_flows), (
        "No Q9-related audit flow found"
    )

    # 11. 学习写入检查
    learning_entries = learning_service.list_history_entries(limit=200)
    assert isinstance(learning_entries, list), "learning_service.list_history_entries must return list"
    assert any("q9" in str(item).lower() or trace_id in str(item) for item in learning_entries), (
        "No Q9-related learning entry found"
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q9_clinical_authenticity())
