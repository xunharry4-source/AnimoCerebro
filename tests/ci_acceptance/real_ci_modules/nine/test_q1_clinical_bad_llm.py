from __future__ import annotations

import asyncio
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
from llm_output_assertions import assert_llm_output_integrity, assert_no_snapshot_fallback
from nine_question_history_assertions import assert_question_history_version_exists

@pytest.mark.asyncio
async def test_q1_clinical_comprehensive():
    """
    Q1 临床验收测试 (V4)：验证认知真实性、数据库持久化、模块节点完整性及全链路侧作用。
    """
    print("\n" + "="*60)
    print("STARTING Q1 CLINICAL ACCEPTANCE TEST")
    print("="*60)

    # 1. 初始化系统环境（真实业务路径，不清理历史数据）
    # 走 WebConsoleContainer 默认业务初始化链路，让系统按正式配置创建/使用数据库。
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()
    
    # 2. 准备依赖（真实 LLM 链路）
    llm_service = get_llm_service()
    
    plugin_service = get_plugin_service()
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()
    audit_svc = get_audit_service()
    learning_svc = get_learning_service()
    memory_svc = get_memory_service()
    reflection_svc = get_reflection_service()
    
    # 3. 注入依赖到内核
    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        foundation_service=foundation_service,
        environment_service=environment_service,
        audit_service=audit_svc,
        learning_service=learning_svc,
        memory_service=memory_svc,
        reflection_service=reflection_svc
    )
    
    # 4. 引导插件系统
    plugin_service.register_discovered_plugins()
    plugin_service.rehydrate_registered_plugins()
    if callable(getattr(plugin_service, "attach_cognitive_services", None)):
        plugin_service.attach_cognitive_services(
            llm_service=llm_service,
            audit_service=audit_svc,
            memory_service=memory_svc,
            reflection_service=reflection_svc,
            learning_service=learning_svc,
            transcript_store=kernel_service.transcript_store
        )
    
    # 5. 物理执行 Q1（执行走正式 plugin_service，查询走 NineQuestionService）
    nq_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager()
    )
    
    q_id = "q1"
    q = next(item for item in DEFAULT_NINE_QUESTIONS if item.question_id == q_id)
    print(f"[Clinical] Executing {q_id}...")
    response = plugin_service.execute_plugin_once_sync(
        plugin_id=q.plugin_id,
        task_id="ci-acceptance:q1",
        parameters={
            "question_id": q.question_id,
            "question_text": q.text,
            "model_provider": "__bad_llm_provider__",
            "llm_model": "__bad_llm_model__",
            "model": "__bad_llm_model__",
            "request_timeout_seconds": 5,
        },
        trace_id="ci-acceptance-trace-q1",
        originator_id="clinical-test",
    )
    assert getattr(response, "status", None) in {"done", "completed"}, (
        f"Q1 execution failed: {getattr(response, 'error', '')} "
        f"{getattr(response, 'remarks', '')}"
    )
    
    # 6. 验证持久化 (检查项目 1: 数据库是否有值)
    print("[Clinical] Verifying Database Persistence...")
    # 使用 StateManager 获取物理存储的状态
    state_mgr = facade.get_nine_question_state_manager()
    db_state = await state_mgr.get_state("nq-baseline")
    assert q_id in db_state.question_snapshots, f"Q1 not found in database snapshots"
    assert_question_history_version_exists(db_state, q_id)
    q1_snapshot = db_state.question_snapshots[q_id]
    assert (
        str(q1_snapshot.get("summary") or "").strip()
        or bool(q1_snapshot.get("result"))
        or bool(q1_snapshot.get("context_updates"))
    ), "Q1 snapshot has no usable persisted payload in database"
    print(f"[Clinical] ✓ Database: Q1 persisted with revision {db_state.revision}")

    # 7. 验证模块节点 (检查项目 2: 每一问里面的模块节点都必须检查)
    print("[Clinical] Verifying Module Node Integrity...")
    record = await nq_service.get_question_record(q_id)
    composed = record.get("composed", {})
    
    required_non_empty_nodes = ["evidence", "inference", "summary", "trace", "raw"]
    for node in required_non_empty_nodes:
        assert composed.get(node), f"Missing modular node: {node}"
        print(f"[Clinical] ✓ Node: {node} is present and non-empty")
    
    # 深度检查 inference 内容
    inference = composed.get("inference", {})
    assert "reasoning_summary" in inference, "Inference reasoning_summary missing"
    print(f"[Clinical] ✓ Inference Detail: {inference['reasoning_summary'][:50]}...")

    # 7.1 验证内部模块真实运行轨迹（module_runs）
    raw = composed.get("raw", {})
    context_updates = raw.get("context_updates", {}) if isinstance(raw, dict) else {}
    diagnosis = context_updates.get("q1_execution_diagnosis", {}) if isinstance(context_updates, dict) else {}
    assert isinstance(diagnosis, dict) and diagnosis, "Missing q1_execution_diagnosis"
    assert_no_snapshot_fallback(diagnosis, q_id)
    authenticity = diagnosis.get("authenticity_status")
    assert authenticity == "completed", f"Q1 authenticity must be completed, got: {authenticity}"
    module_runs = diagnosis.get("module_runs", []) if isinstance(diagnosis, dict) else []
    assert isinstance(module_runs, list) and len(module_runs) > 0, "No q1 module_runs found in execution diagnosis"

    required_modules = {
        "dependency_check",
        "workspace_structure_scan",
        "content_sampling",
        "functional_plugin_chain",
        "environment_scan",
        "domain_inference",
        "uncertainty_projection",
        "state_write",
    }
    executed_module_ids = {
        str(item.get("module_id") or "").strip()
        for item in module_runs
        if isinstance(item, dict)
    }
    missing_runs = required_modules - executed_module_ids
    assert not missing_runs, f"Missing required q1 module runs: {sorted(missing_runs)}"
    print(f"[Clinical] ✓ Module Runs: required modules executed ({len(executed_module_ids)} total)")

    # 7.2 验证 NineQuestionService 中模块级查询结果（持久化读路径）
    module_payload = await nq_service.get_question_modules(q_id)
    module_map = module_payload.get("modules", {})
    assert isinstance(module_map, dict) and module_map, "No module payload found in NineQuestionService.get_question_modules"

    for module_id in required_modules:
        assert module_id in module_map, f"Module {module_id} missing from persisted module map"
        module_entry = module_map[module_id]
        assert isinstance(module_entry, dict), f"Module {module_id} entry must be a dict"
        module_status = str(module_entry.get("status") or "").strip()
        assert module_status in {"completed", "ready"}, (
            f"Module {module_id} is not fully completed: {module_status}"
        )
    print("[Clinical] ✓ Module Persistence: module-level query checks passed")

    assert_llm_output_integrity(
        question_id=q_id,
        composed=composed,
        context_updates=context_updates,
    )

    # 8. 验证侧作用 (Side-Effects)
    print("[Clinical] Verifying Side-Effects...")
    
    # 审计 (Audit)
    flows = audit_svc.query_flows(flow_type="nine_questions", limit=10)
    assert any(q_id in str(f) for f in flows), "Audit: No related flow found"
    print(f"[Clinical] ✓ Audit: Trace recorded")
    
    # 学习 (Learning)
    learning_entries = learning_svc.list_history_entries(limit=200)
    assert any(q_id in str(item).lower() for item in learning_entries), "Learning: No Q1-related records found"
    print("[Clinical] ✓ Learning: Record found")

    # 记忆 (Memory)
    memory_records = memory_svc.query_managed_records(limit=100)
    assert isinstance(memory_records, list), "Memory: query_managed_records must return list"
    assert any(
        "q1" in str(getattr(item, "title", "")).lower()
        or "q1" in str(getattr(item, "summary", "")).lower()
        or "q1" in " ".join(getattr(item, "tags", []) or []).lower()
        for item in memory_records
    ), "Memory: No Q1-related record found"
    print("[Clinical] ✓ Memory: Record found")

    # 反思 (Reflection)
    reflection_records = reflection_svc.list_reflections({})
    assert isinstance(reflection_records, list), "Reflection: list_reflections must return list"
    assert any(
        "q1" in str(getattr(item, "subject", "")).lower()
        or "q1" in str((getattr(item, "context", {}) or {}).get("question_id", "")).lower()
        for item in reflection_records
    ), "Reflection: No Q1-related record found"
    print("[Clinical] ✓ Reflection: Record found")

    print(f"\n[Clinical] {q_id.upper()} CLINICAL ACCEPTANCE PASSED.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q1_clinical_comprehensive())
