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
from zentex.foundation.service import get_service as get_foundation_service
from zentex.environment.service import get_service as get_environment_service
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

@pytest.mark.asyncio
async def test_q2_clinical_authenticity():
    """
    Q2 临床验收测试：验证认知真实性与服务层完整性。
    
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
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()
    
    # 权威查询服务
    nq_query_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager(),
    )
    
    # 2. 依赖注入与系统引导 (模拟真实启动链路)
    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        foundation_service=foundation_service,
        environment_service=environment_service,
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
    q = next(q for q in DEFAULT_NINE_QUESTIONS if q.question_id == "q2")
    trace_id = "ci-acceptance-trace-q2"

    # 3.1 严格门禁：只允许读取已存在的上游最新合格快照，不在 Q2 测试中补跑上游题目
    try:
        await nq_query_service.assert_latest_qualified_upstreams("q2")
    except Exception as exc:
        raise AssertionError(
            f"Q2 prerequisite gate failed. Upstream must already be latest-qualified snapshot. {exc}"
        ) from exc

    print(f"\n[Clinical] Executing {q.question_id} via SystemPluginService...")
    
    # 4. 执行插件 (真实调用)
    # 这将触发真实的推理链，如果环境中 Ollama 宕机，此处应显式报错
    response = plugin_service.execute_plugin_once_sync(
        plugin_id=q.plugin_id,
        task_id="ci-acceptance:q2",
        parameters={
            "question_id": q.question_id,
            "question_text": q.text
        },
        trace_id=trace_id,
        originator_id="clinical-test"
    )
    
    assert getattr(response, "status", None) in ("completed", "done"), f"Execution failed: {getattr(response, 'error', 'unknown error')} - Remarks: {getattr(response, 'remarks', 'no remarks')}"
    
    # 5. 通过权威 Service 查询持久化状态
    print(f"[Clinical] Querying {q.question_id} via NineQuestionService...")
    state_mgr = facade.get_nine_question_state_manager()
    db_state = await state_mgr.get_state("nq-baseline")
    assert q.question_id in db_state.question_snapshots, f"{q.question_id} not persisted in authoritative database snapshots"
    assert_question_history_version_exists(db_state, q.question_id)
    persisted_snapshot = db_state.question_snapshots[q.question_id]
    assert str(persisted_snapshot.get("trace_id") or "").strip() == trace_id, (
        f"{q.question_id} persisted trace_id mismatch: {persisted_snapshot.get('trace_id')}"
    )

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
    print(f"[Clinical] Q2 Authenticity Status: {authenticity}")
    
    # 预期状态：已实现的问题为 'completed'，其他为 'ready' 或 'partial'
    # 关键在于绝不能是 'fake' 或 'mocked'
    assert authenticity == "completed", f"Unexpected authenticity status for {q.question_id}: {authenticity}"

    # 7. 内部模块运行检查（module_runs + modules 持久化视图）
    module_runs = diagnosis.get("module_runs", {}) if isinstance(diagnosis, dict) else {}
    if isinstance(module_runs, dict):
        module_runs = list(module_runs.values())
    assert isinstance(module_runs, list) and len(module_runs) > 0, "No module_runs found in q2 execution diagnosis"

    required_modules = {
        "q2_q1_dependency_validation",
        "q2_identity_kernel_validation",
        "q2_functional_identity_chain",
        "q2_role_reasoning_projection",
    }

    executed_module_ids = {
        str(item.get("module_id") or "").strip()
        for item in module_runs
        if isinstance(item, dict)
    }
    missing_runs = required_modules - executed_module_ids
    assert not missing_runs, f"Missing required q2 module runs: {sorted(missing_runs)}"

    modules_payload = await nq_query_service.get_question_modules(q.question_id)
    module_map = modules_payload.get("modules", {})
    assert isinstance(module_map, dict) and module_map, "No persisted module payload for q2"

    for module_id in required_modules:
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

    # 8. 记忆写入检查
    memory_records = memory_service.query_managed_records(trace_id=trace_id, limit=100)
    assert isinstance(memory_records, list), "memory_service.query_managed_records must return list"
    assert any(
        str(getattr(item, "trace_id", "") or "") == trace_id
        and (
            "q2" in str(getattr(item, "title", "")).lower()
            or "q2" in str(getattr(item, "summary", "")).lower()
            or "q2" in " ".join(getattr(item, "tags", []) or []).lower()
        )
        for item in memory_records
    ), "No Q2-related memory record found for trace_id"

    # 9. 反思写入检查
    reflection_records = reflection_service.list_reflections({"trace_id": trace_id})
    assert isinstance(reflection_records, list), "reflection_service.list_reflections must return list"
    assert any(
        str(getattr(item, "trace_id", "") or "") == trace_id
        and (
            "q2" in str(getattr(item, "subject", "")).lower()
            or "q2" in str((getattr(item, "context", {}) or {}).get("question_id", "")).lower()
        )
        for item in reflection_records
    ), "No Q2-related reflection record found for trace_id"

    # 10. 审计写入检查
    audit_flows = audit_service.query_flows(flow_type="nine_questions", limit=200)
    assert isinstance(audit_flows, list), "audit_service.query_flows must return list"
    assert any(
        "q2" in str(item).lower() or trace_id in str(item)
        for item in audit_flows
    ), "No Q2-related audit flow found"

    # 11. 学习写入检查
    learning_entries = learning_service.list_history_entries(limit=200)
    assert isinstance(learning_entries, list), "learning_service.list_history_entries must return list"
    learning_found = any(
        "q2" in str(item).lower() or trace_id in str(item)
        for item in learning_entries
    )
    if not learning_found:
        learning_module = module_map.get("q2_learning_integration", {}) if isinstance(module_map, dict) else {}
        learning_data = learning_module.get("data", {}) if isinstance(learning_module, dict) else {}
        learning_trace_id = str(learning_data.get("learning_trace_id") or "").strip() if isinstance(learning_data, dict) else ""
        assert learning_trace_id, "No Q2-related learning entry found"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q2_clinical_authenticity())


@pytest.mark.asyncio
async def test_q2_rejects_non_latest_or_unqualified_upstream_snapshot():
    """
    严格门禁：Q2 只能读取上游最新合格快照。
    当 Q1 被标记 dirty（非最新合格）时，Q2 必须被真实执行链路拒绝。
    """
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()

    llm_service = get_llm_service()
    plugin_service = get_plugin_service()
    audit_service = get_audit_service()
    learning_service = get_learning_service()
    memory_service = get_memory_service()
    reflection_service = get_reflection_service()
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()

    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        foundation_service=foundation_service,
        environment_service=environment_service,
        audit_service=audit_service,
        learning_service=learning_service,
        memory_service=memory_service,
        reflection_service=reflection_service,
    )
    plugin_service.attach_cognitive_services(
        llm_service=llm_service,
        audit_service=audit_service,
        learning_service=learning_service,
        memory_service=memory_service,
        reflection_service=reflection_service,
    )
    plugin_service.register_discovered_plugins()
    plugin_service.rehydrate_registered_plugins()

    nq_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager(),
    )

    # 先确认当前上游处于最新合格状态，再将 Q1 标记 dirty 验证硬门禁拒绝。
    await nq_service.assert_latest_qualified_upstreams("q2")
    await nq_service.mark_question_dirty("q1", reason="ci_strict_upstream_snapshot_gate")

    q2 = next(q for q in DEFAULT_NINE_QUESTIONS if q.question_id == "q2")
    response = plugin_service.execute_plugin_once_sync(
        plugin_id=q2.plugin_id,
        task_id="ci-acceptance:q2:reject-unqualified-upstream",
        parameters={
            "question_id": q2.question_id,
            "question_text": q2.text,
        },
        trace_id="ci-acceptance-trace-q2-upstream-gate",
        originator_id="clinical-test",
    )

    assert getattr(response, "status", None) == "failed", (
        "Q2 must fail when upstream snapshot is dirty/non-latest."
    )
    remarks = str(getattr(response, "remarks", "") or "")
    error = str(getattr(response, "error", "") or "")
    assert (
        "Upstream latest qualified snapshot gate failed" in remarks
        or "Upstream latest qualified snapshot gate failed" in error
    ), f"Unexpected failure reason: status={getattr(response, 'status', None)} error={error} remarks={remarks}"

    # 避免污染后续测试。
    await nq_service.clear_question_dirty("q1", reason="ci_strict_upstream_snapshot_gate_cleanup")
