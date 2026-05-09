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
async def test_q4_clinical_authenticity():
    """
    Q4 临床验收测试：验证认知真实性与服务层完整性。
    
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
    # 无论 llm 是否已注入，都强制补全 memory/reflection 注入，确保侧作用可验证
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
    q = next(q for q in DEFAULT_NINE_QUESTIONS if q.question_id == "q4")
    trace_id = "ci-acceptance-trace-q4"

    # 3.1 严格门禁：只允许读取已存在的上游最新合格快照，不在 Q4 测试中补跑上游题目
    try:
        await nq_query_service.assert_latest_qualified_upstreams("q4")
    except Exception as exc:
        raise AssertionError(
            f"Q4 prerequisite gate failed. Upstreams must already be latest-qualified snapshots. {exc}"
        ) from exc
    
    print(f"\n[Clinical] Executing {q.question_id} via SystemPluginService...")
    
    # 4. 执行插件 (真实调用)
    # 这将触发真实的推理链，如果环境中 Ollama 宕机，此处应显式报错
    response = plugin_service.execute_plugin_once_sync(
        plugin_id=q.plugin_id,
        task_id="ci-acceptance:q4",
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
    print(f"[Clinical] Q4 Authenticity Status: {authenticity}")
    
    # 预期状态：已实现的问题为 'completed'，其他为 'ready' 或 'partial'
    # 关键在于绝不能是 'fake' 或 'mocked'
    assert authenticity == "completed", f"Unexpected authenticity status for {q.question_id}: {authenticity}"

    # 7. 内部模块运行检查（module_runs + modules 持久化视图）
    module_runs = diagnosis.get("module_runs", {}) if isinstance(diagnosis, dict) else {}
    if isinstance(module_runs, dict):
        module_runs = list(module_runs.values())
    assert isinstance(module_runs, list) and len(module_runs) > 0, "No module_runs found in q4 execution diagnosis"

    required_run_modules = {
        "q4_inventory_validation",
        "q4_permission_validation",
        "q4_execution_capability_verification",
        "q4_actionability_projection",
    }
    executed_module_ids = {
        str(item.get("module_id") or "").strip()
        for item in module_runs
        if isinstance(item, dict)
    }
    missing_run_modules = required_run_modules - executed_module_ids
    assert not missing_run_modules, f"Missing required q4 module runs: {sorted(missing_run_modules)}"
    assert "q4_anti_hallucination_guard" in executed_module_ids, "Missing q4_anti_hallucination_guard module run"

    modules_payload = await nq_query_service.get_question_modules(q.question_id)
    module_map = modules_payload.get("modules", {})
    assert isinstance(module_map, dict) and module_map, "No persisted module payload for q4"

    required_persisted_modules = {
        "q4_inventory_validation",
        "q4_permission_validation",
        "q4_execution_capability_verification",
        "q4_actionability_projection",
        "q4_memory_integration",
        "q4_reflection_integration",
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

    # 8. 记忆写入检查（以模块产物 memory_id 为主键做真实查询）
    memory_module = module_map.get("q4_memory_integration", {}) if isinstance(module_map, dict) else {}
    memory_data = memory_module.get("data", {}) if isinstance(memory_module, dict) else {}
    memory_id = str(memory_data.get("memory_id") or "").strip() if isinstance(memory_data, dict) else ""
    assert memory_id, "Q4 memory integration did not return memory_id"
    memory_record = memory_service.get_record(memory_id)
    assert memory_record is not None, f"Q4 memory_id not queryable: {memory_id}"
    assert str(getattr(memory_record, "trace_id", "") or "") == trace_id, "Q4 memory trace_id mismatch"
    memory_records = memory_service.query_managed_records(trace_id=trace_id, limit=100)
    assert isinstance(memory_records, list), "memory_service.query_managed_records must return list"
    assert any(str(getattr(item, "memory_id", "") or "") == memory_id for item in memory_records), (
        "Q4 memory_id not queryable by trace_id"
    )

    # 9. 反思写入检查（优先使用模块产物 reflection_id 回查）
    reflection_module = module_map.get("q4_reflection_integration", {}) if isinstance(module_map, dict) else {}
    reflection_data = reflection_module.get("data", {}) if isinstance(reflection_module, dict) else {}
    reflection_id = str(reflection_data.get("reflection_id") or "").strip() if isinstance(reflection_data, dict) else ""
    assert reflection_id, "Q4 reflection integration did not return reflection_id"
    reflection_record = reflection_service.get_reflection(reflection_id)
    assert reflection_record is not None, f"Q4 reflection_id not queryable: {reflection_id}"
    assert str(getattr(reflection_record, "trace_id", "") or "") == trace_id, "Q4 reflection trace_id mismatch"

    # 10. 审计写入检查（必须可查询到 q4/trace_id 相关审计流）
    audit_flows = audit_service.query_flows(flow_type="nine_questions", limit=200)
    assert isinstance(audit_flows, list), "audit_service.query_flows must return list"
    assert any("q4" in str(item).lower() or trace_id in str(item) for item in audit_flows), (
        "No Q4-related audit flow found"
    )

    # 11. 学习写入检查（必须可查询到 q4/trace_id 相关学习记录）
    learning_entries = learning_service.list_history_entries(limit=200)
    assert isinstance(learning_entries, list), "learning_service.list_history_entries must return list"
    learning_found = any("q4" in str(item).lower() or trace_id in str(item) for item in learning_entries)
    if not learning_found:
        learning_module = module_map.get("q4_learning_integration", {}) if isinstance(module_map, dict) else {}
        learning_data = learning_module.get("data", {}) if isinstance(learning_module, dict) else {}
        learning_trace_id = str(learning_data.get("learning_trace_id") or "").strip() if isinstance(learning_data, dict) else ""
        assert learning_trace_id, "No Q4-related learning entry found"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q4_clinical_authenticity())
