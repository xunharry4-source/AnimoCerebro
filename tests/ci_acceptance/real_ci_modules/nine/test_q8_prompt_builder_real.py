from __future__ import annotations

import json

from plugins.nine_questions.q8_what_should_i_do_now.llm_prompt import (
    build_q8_llm_request,
    build_q8_prompt_snapshot,
)


def _build_request(snapshot: dict) -> dict:
    return build_q8_llm_request(
        system_prompt="Q8 real prompt builder test",
        nine_questions_summary="RAW_SECRET_SUMMARY must not be used",
        task_state_summary="RAW_TASK_STATE_SUMMARY must not be used",
        objective_catalog="objective catalog",
        priority_baseline={"immediate_tasks": ["ship real prompt preprocessing"]},
        q1_q7_snapshot=snapshot,
        nine_questions=snapshot,
        persistent_task_state={"todo": [{"title": "real task", "raw_output": "TASK_RAW_SECRET"}]},
        active_objectives=["real objective"],
        functional_objectives=[{"plugin_id": "real-plugin", "result": {"objective": "structured value"}}],
    )


def test_q8_prompt_builder_drops_raw_debug_and_unmapped_fields_real() -> None:
    """真实 prompt builder：raw/debug/token 字段不得进入 prompt 或 model_context。"""
    snapshot = {
        "q1": {
            "status": "completed",
            "environment_summary": "workspace ready",
            "raw_output": "RAW_SECRET_Q1",
            "reasoning_trace": "TRACE_SECRET_Q1",
            "token_count": 999,
        },
        "q4": {
            "status": "completed",
            "actionable_space": ["edit code"],
            "permission_profile": {"mode": "workspace-write", "debug": "DEBUG_SECRET_Q4"},
            "unmapped_field": "UNMAPPED_SECRET_Q4",
        },
        "q5": {
            "status": "completed",
            "authorized_actions": ["write tests"],
            "forbidden_action_space": ["hide errors"],
            "latency_ms": 1234,
        },
        "q6": {
            "status": "completed",
            "absolute_red_lines": ["no fake tests"],
            "prohibited_strategies": ["silent fallback"],
            "chain_of_thought": "COT_SECRET_Q6",
        },
    }

    request = _build_request(snapshot)
    rendered = json.dumps(request, ensure_ascii=False, sort_keys=True)
    report = request["model_context"]["q8_prompt_preprocessing_report"]

    assert "workspace ready" in request["prompt"]
    assert "hide errors" in request["prompt"]
    for forbidden in (
        "RAW_SECRET_Q1",
        "TRACE_SECRET_Q1",
        "DEBUG_SECRET_Q4",
        "UNMAPPED_SECRET_Q4",
        "COT_SECRET_Q6",
        "RAW_SECRET_SUMMARY",
        "RAW_TASK_STATE_SUMMARY",
        "TASK_RAW_SECRET",
    ):
        assert forbidden not in rendered
    assert "q1.raw_output" in report["dropped_raw_fields"]
    assert "q1.reasoning_trace" in report["dropped_raw_fields"]
    assert "q4.unmapped_field" in report["dropped_unmapped_fields"]
    assert report["missing_required_questions"] == []


def test_q8_prompt_builder_reports_missing_required_upstreams_real() -> None:
    """异常链路：缺 Q4/Q5/Q6 不能静默正常，必须进入预处理报告。"""
    compact, report = build_q8_prompt_snapshot({"q1": {"status": "completed"}})

    assert compact["q1"]["status"] == "completed"
    assert set(report["missing_required_questions"]) == {"q4", "q5", "q6"}
    assert report["used_field_intent_map"] is True


def test_q8_prompt_builder_truncates_with_evidence_and_caps_context_real() -> None:
    """边界链路：超长字段必须裁剪并留下 evidence，不能把全量噪声塞回 prompt。"""
    long_text = "x" * 1200
    snapshot = {
        "q4": {"status": "completed", "actionable_space": [long_text for _ in range(12)]},
        "q5": {"status": "completed", "forbidden_action_space": [long_text for _ in range(12)]},
        "q6": {"status": "completed", "absolute_red_lines": [long_text for _ in range(12)]},
        "q7": {"status": "completed", "fallback_plans": [long_text for _ in range(12)]},
    }

    compact, report = build_q8_prompt_snapshot(snapshot)

    assert report["context_chars"] <= report["max_context_chars"]
    assert report["truncated_fields"], "Prompt preprocessing must expose truncation evidence"
    assert any(item["path"].startswith("q6.absolute_red_lines") for item in report["truncated_fields"])
    assert len(compact["q6"]["absolute_red_lines"]) <= 10
    assert all(len(item) <= 200 for item in compact["q6"]["absolute_red_lines"])


def test_q8_prompt_builder_keeps_only_business_intent_fields_for_q1_to_q7_real() -> None:
    """查询链路：Q1-Q7 只允许进入明确业务意图字段，不允许把未映射字段混入 prompt。"""
    snapshot = {
        "q1": {
            "status": "completed",
            "environment_summary": "prod workspace",
            "primary_domain": "engineering",
            "secondary_domains": ["qa", "ops", "security", "runtime", "extra-domain"],
            "suggested_first_step": "check real evidence",
            "unused_environment_blob": "Q1_UNUSED_SECRET",
        },
        "q2": {
            "status": "completed",
            "role_profile": {"identity_role": "operator", "active_role": "developer", "task_role": "verifier"},
            "mission": {"current_mission": "finish V2", "priority_duties": ["test"], "continuity_boundaries": ["no mock"]},
            "non_bypassable_constraints": ["fail closed"],
            "audit_rules": ["real requests"],
        },
        "q3": {
            "status": "completed",
            "resource_status": "ready",
            "bottleneck_node": "production evidence",
            "missing_critical_assets": ["external production export"],
            "available_cognitive_tools": ["prompt builder"],
            "available_execution_tools": ["pytest"],
            "accessible_workspace_zones": ["workspace"],
        },
        "q4": {
            "status": "completed",
            "actionable_space": ["add gate"],
            "executable_strategies": ["query after write"],
            "capability_upper_limits": ["no fake completion"],
            "permission_profile": {"mode": "workspace-write", "is_read_only": False},
        },
        "q5": {
            "status": "completed",
            "allowed_action_space": ["edit q8 domain"],
            "forbidden_action_space": ["hide errors"],
            "requires_escalation_actions": ["network provider"],
            "authorized_actions": ["write tests"],
            "unauthorized_actions": ["mock llm"],
            "conditional_actions": ["browser e2e only if UI changes"],
        },
        "q6": {
            "status": "completed",
            "absolute_red_lines": ["no mock"],
            "performance_tradeoff_bans": ["silent fallback"],
            "prohibited_strategies": ["fake green"],
            "contamination_risks": ["fixture as production"],
            "audit_rules": ["write then query"],
        },
        "q7": {
            "status": "completed",
            "fallback_plans": ["keep V2 incomplete if real source missing"],
            "degradation_strategies": ["explicit 409 only"],
            "collaboration_switches": ["ask only for real source"],
            "exploratory_actions": ["inspect trace"],
            "capability_limits": ["4000 chars"],
            "permission_boundaries": ["service thin only"],
            "resource_bottlenecks": ["production export absent"],
        },
    }

    compact, report = build_q8_prompt_snapshot(snapshot)
    rendered = json.dumps(compact, ensure_ascii=False, sort_keys=True)

    assert compact["q1"]["environment_summary"] == "prod workspace"
    assert compact["q2"]["mission"]["current_mission"] == "finish V2"
    assert compact["q4"]["permission_profile"]["mode"] == "workspace-write"
    assert compact["q5"]["forbidden_action_space"] == ["hide errors"]
    assert compact["q6"]["absolute_red_lines"] == ["no mock"]
    assert compact["q7"]["capability_limits"] == ["4000 chars"]
    assert "Q1_UNUSED_SECRET" not in rendered
    assert "q1.unused_environment_blob" in report["dropped_unmapped_fields"]
    assert any(item["path"] == "q1.secondary_domains" for item in report["truncated_fields"])
    assert report["missing_required_questions"] == []


def test_q8_prompt_builder_caps_task_state_and_records_exact_truncation_real() -> None:
    """边界链路：任务状态列表必须按数量和字段白名单裁剪，并留下可查询 evidence。"""
    snapshot = {
        "q4": {"status": "completed", "actionable_space": ["edit"]},
        "q5": {"status": "completed", "forbidden_action_space": ["fake"]},
        "q6": {"status": "completed", "absolute_red_lines": ["no mock"]},
    }
    request = build_q8_llm_request(
        system_prompt="Q8 task state cap test",
        nine_questions_summary="unused raw summary",
        task_state_summary="unused task summary",
        objective_catalog="objective catalog",
        priority_baseline={},
        q1_q7_snapshot=snapshot,
        nine_questions=snapshot,
        persistent_task_state={
            "todo": [
                {"title": f"task {index}", "status": "todo", "debug": f"DEBUG_{index}", "owner": "unmapped"}
                for index in range(8)
            ]
        },
        active_objectives=[],
        functional_objectives=[],
    )

    task_state = request["model_context"]["persistent_task_state"]
    report = request["model_context"]["q8_prompt_preprocessing_report"]
    rendered = json.dumps(request, ensure_ascii=False, sort_keys=True)

    assert len(task_state["todo"]) == 6
    assert task_state["todo"][0] == {"title": "task 0", "status": "todo"}
    assert all("debug" not in item and "owner" not in item for item in task_state["todo"])
    assert "DEBUG_0" not in rendered
    assert {"path": "task_state.todo", "from": 8, "to": 6} in report["truncated_fields"]
    assert "task_state.todo[0].debug" in report["dropped_raw_fields"]
    assert "task_state.todo[0].owner" in report["dropped_unmapped_fields"]


def test_q8_prompt_builder_caps_active_and_functional_objectives_real() -> None:
    """边界链路：目标输入必须受数量和长度上限控制，不能线性膨胀 prompt。"""
    snapshot = {
        "q4": {"status": "completed", "actionable_space": ["edit"]},
        "q5": {"status": "completed", "forbidden_action_space": ["fake"]},
        "q6": {"status": "completed", "absolute_red_lines": ["no mock"]},
    }
    request = build_q8_llm_request(
        system_prompt="Q8 objective cap test",
        nine_questions_summary="unused raw summary",
        task_state_summary="unused task summary",
        objective_catalog="objective catalog",
        priority_baseline={},
        q1_q7_snapshot=snapshot,
        nine_questions=snapshot,
        persistent_task_state=[],
        active_objectives=[f"active objective {index}" for index in range(14)],
        functional_objectives=[
            {"plugin_id": f"plugin-{index}", "objective": "x" * 900, "secret": "UNMAPPED_OBJECTIVE_SECRET"}
            for index in range(14)
        ],
    )

    context = request["model_context"]
    report = context["q8_prompt_preprocessing_report"]
    rendered = json.dumps(request, ensure_ascii=False, sort_keys=True)

    assert len(context["active_objectives"]) == 12
    assert len(context["functional_objectives"]) == 12
    assert all(len(item["objective"]) == 800 for item in context["functional_objectives"])
    assert "UNMAPPED_OBJECTIVE_SECRET" not in rendered
    assert {"path": "active_objectives", "from": 14, "to": 12} in report["truncated_fields"]
    assert {"path": "functional_objectives", "from": 14, "to": 12} in report["truncated_fields"]
    assert any(item["path"] == "functional_objectives[0].objective" for item in report["truncated_fields"])
