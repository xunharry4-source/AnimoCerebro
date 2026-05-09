from __future__ import annotations

import pytest

from plugins.nine_questions.q8_what_should_i_do_now.external_tasks import build_external_task_plan
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.context_builder import build_external_task_context
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.validator import (
    Q8ExternalTaskIsolationError,
    validate_external_task_plan,
)
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks import build_internal_task_plan
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks.context_builder import build_internal_task_context
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks.validator import (
    Q8InternalTaskIsolationError,
    validate_internal_task_plan,
)


def _snapshot() -> dict:
    return {
        "q3": {
            "available_cognitive_tools": ["reflection", "learning", "memory"],
            "available_execution_tools": ["cli:gemini", "mcp:notion"],
            "cli_tools": [{"tool_name": "gemini", "description": "file edit CLI"}],
            "mcp_servers": [{"server_id": "notion", "description": "task database"}],
        },
        "q4": {
            "actionable_space": ["write learning entry", "summarize audit chain"],
            "executable_strategies": ["self reflection improvement"],
            "capability_upper_limits": ["external calls require registered authenticated tool"],
        },
        "q5": {"allowed_action_space": ["internal learning", "registered external tool calls"]},
        "q6": {"absolute_red_lines": ["do not leak secrets"]},
        "q7": {"fallback_plans": ["create internal follow-up after external task evidence"]},
    }


def test_q8_internal_and_external_contexts_are_physically_isolated_real() -> None:
    snapshot = _snapshot()
    internal_context = build_internal_task_context(
        question_snapshot=snapshot,
        normalized_task_state={"todo": [{"title": "review previous task outcome"}]},
        priority_baseline={"immediate_tasks": ["write reflection summary"]},
        functional_objectives=[{"plugin_id": "internal.reflection"}],
    )
    external_context = build_external_task_context(question_snapshot=snapshot)

    internal_text = str(internal_context).lower()
    external_text = str(external_context).lower()
    assert "available_execution_tools" not in internal_text
    assert "cli_tools" not in internal_text
    assert "mcp_servers" not in internal_text
    assert "external_connectors" not in internal_text
    assert "available_cognitive_tools" not in external_text
    assert "functional_objectives" not in external_text
    assert "reflection_strategy" not in external_text
    assert "learning_strategy" not in external_text


def test_q8_internal_and_external_planners_split_and_validate_real_tasks() -> None:
    snapshot = _snapshot()
    raw_queue = {
        "next_self_tasks": [
            {
                "task_id": "internal-reflection",
                "title": "write internal reflection from audit evidence",
            },
            {
                "task_id": "external-gemini-file",
                "title": "use Gemini CLI to inspect a file",
                "task_scope": "external",
                "executor_type": "cli",
                "target_id": "cli:gemini",
                "metadata": {"executor_type": "cli", "target_id": "cli:gemini"},
            },
        ],
        "blocked_self_tasks": [],
        "proactive_actions": [],
    }

    internal_plan = build_internal_task_plan(
        question_snapshot=snapshot,
        normalized_task_state={},
        priority_baseline={},
        functional_objectives=[],
        raw_task_queue=raw_queue,
    )
    external_plan = build_external_task_plan(
        question_snapshot=snapshot,
        raw_task_queue=raw_queue,
    )

    assert internal_plan["generated"] == 1
    assert internal_plan["tasks"][0]["task_scope"] == "internal"
    assert internal_plan["tasks"][0]["metadata"]["source_chain"] == "internal_q8"
    assert external_plan["generated"] == 1
    assert external_plan["tasks"][0]["task_scope"] == "external"
    assert external_plan["tasks"][0]["executor_type"] == "cli"
    assert external_plan["tasks"][0]["metadata"]["source_chain"] == "external_q8"

    with pytest.raises(Q8InternalTaskIsolationError) as internal_error:
        validate_internal_task_plan({"tasks": [external_plan["tasks"][0]]})
    assert Q8InternalTaskIsolationError.error_code in str(internal_error.value)

    with pytest.raises(Q8ExternalTaskIsolationError) as external_error:
        validate_external_task_plan({"tasks": [internal_plan["tasks"][0]]})
    assert Q8ExternalTaskIsolationError.error_code in str(external_error.value)
