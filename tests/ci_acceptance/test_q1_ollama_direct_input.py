from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root / "src") not in sys.path:
    sys.path.append(str(repo_root / "src"))

from zentex.plugins.service import get_service as get_plugin_service
from zentex.llm.service import get_service as get_llm_service
from zentex.nine_questions.service import NineQuestionService
from zentex.web_console.di_container import WebConsoleContainer
from zentex.foundation.service import get_service as get_foundation_service
from zentex.environment.service import get_service as get_environment_service
from zentex.audit.service import get_service as get_audit_service
from zentex.learning.service import get_service as get_learning_service
from zentex.memory.service import get_memory_service
from zentex.reflection.service import get_service as get_reflection_service
from zentex.kernel.cognition_flow import DEFAULT_NINE_QUESTIONS

from plugins.nine_questions.q1_where_am_i.llm_prompt import build_q1_llm_request
from zentex.common.nine_questions_shared import build_caller_context


@pytest.mark.asyncio
async def test_q1_ollama_direct_call_with_real_input_payload():
    """使用 Q1 真实输入结构，单独直连 ollama 验证 LLM 调用链路。"""
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()

    llm_service = get_llm_service()
    plugin_service = get_plugin_service()
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()
    audit_service = get_audit_service()
    learning_service = get_learning_service()
    memory_service = get_memory_service()
    reflection_service = get_reflection_service()

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

    q1 = next(q for q in DEFAULT_NINE_QUESTIONS if q.question_id == "q1")
    q1_response = plugin_service.execute_plugin_once_sync(
        plugin_id=q1.plugin_id,
        task_id="ci-acceptance:q1:build-real-llm-input",
        parameters={
            "question_id": q1.question_id,
            "question_text": q1.text,
        },
        trace_id="ci-acceptance-trace-q1-ollama-direct",
        originator_id="clinical-test",
    )
    assert getattr(q1_response, "status", None) in {"done", "completed"}, (
        f"Q1 pre-run failed: error={getattr(q1_response, 'error', '')} "
        f"remarks={getattr(q1_response, 'remarks', '')}"
    )

    nq_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager(),
    )
    q1_raw = await nq_service.get_question_raw("q1")
    context_updates = q1_raw.get("context_updates", {}) if isinstance(q1_raw, dict) else {}

    compressed = context_updates.get("q1_compression_snapshot", {}) if isinstance(context_updates, dict) else {}
    if not isinstance(compressed, dict):
        compressed = {}
    environment_event = context_updates.get("environment_event", {}) if isinstance(context_updates, dict) else {}
    if not isinstance(environment_event, dict):
        environment_event = {}
    physical_host_state = context_updates.get("physical_host_state", {}) if isinstance(context_updates, dict) else {}
    if not isinstance(physical_host_state, dict):
        physical_host_state = {}
    sensory_audit = context_updates.get("q1_sensory_audit", {}) if isinstance(context_updates, dict) else {}
    if not isinstance(sensory_audit, dict):
        sensory_audit = {}
    structure_snapshot = context_updates.get("workspace_structure_analysis", {}) if isinstance(context_updates, dict) else {}
    if not isinstance(structure_snapshot, dict):
        structure_snapshot = {}

    llm_request = build_q1_llm_request(
        compressed=compressed,
        environment_event=environment_event,
        physical_host_state=physical_host_state,
        interpretation_markers=sensory_audit.get("interpretation_markers"),
        risk_markers=sensory_audit.get("risk_markers"),
        suffix_distribution=structure_snapshot.get("suffix_distribution"),
    )
    system_prompt = llm_request["system_prompt"]
    prompt = llm_request["prompt"]
    model_context = llm_request["model_context"]

    caller_context = build_caller_context(
        source_module="q1_ollama_direct_input_test",
        invocation_phase="ci_acceptance_q1_ollama_direct_input",
        question_ref="我在哪",
        question_driver_refs=["我在哪"],
        decision_id="ci:q1:ollama:direct",
        trace_id="ci-acceptance-trace-q1-ollama-direct-input",
    )

    try:
        call = llm_service.generate_json(
            prompt=f"{system_prompt}\n\n{prompt}",
            context=model_context,
            caller_context=caller_context,
            source_module="q1_ollama_direct_input_test",
            invocation_phase="ci_acceptance_q1_ollama_direct_input",
            decision_id="ci:q1:ollama:direct",
            model_provider="ollama",
            model="gemma4:latest",
            metadata={
                "trace_id": "ci-acceptance-trace-q1-ollama-direct-input",
                "question_driver_refs": ["我在哪"],
                "request_timeout_seconds": 120,
            },
        )
    except Exception as exc:
        pytest.fail(
            "Direct ollama call with Q1 real input failed: "
            f"{exc.__class__.__name__}: {exc}"
        )

    output = call.output if isinstance(call.output, dict) else {}
    assert output, "Direct ollama call returned empty output"
    assert str(output.get("primary_domain") or "").strip(), "Missing primary_domain in ollama output"
    assert str(output.get("reasoning_summary") or "").strip(), "Missing reasoning_summary in ollama output"
    assert isinstance(output.get("secondary_domains"), list), "secondary_domains must be list"
    assert isinstance(output.get("uncertainties"), list) and output.get("uncertainties"), "uncertainties must be non-empty list"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_q1_ollama_direct_call_with_real_input_payload())
