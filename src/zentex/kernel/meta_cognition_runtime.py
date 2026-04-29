from __future__ import annotations

"""Runtime orchestration for Feature 54 MetaCognitionController."""

from typing import Any, Optional

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


def decide_meta_cognition(
    kernel_service: Any,
    *,
    session_id: str,
    wm_frame: dict[str, Any],
    self_model: dict[str, Any],
    budget: dict[str, Any],
    nine_q_state: dict[str, Any],
    agenda: list[dict[str, Any]] | dict[str, Any],
    tool_registry: list[dict[str, Any]] | dict[str, Any],
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    result = state.meta_cognition.decide(
        wm_frame=wm_frame,
        self_model=self_model,
        budget=budget,
        nine_q_state=nine_q_state,
        agenda=agenda,
        tool_registry=tool_registry,
    )
    _append_entry(state, session_id=session_id, trace_id=trace_id, result=result)
    return _read_after_write(state, result)


def query_meta_cognition_decision(kernel_service: Any, *, session_id: str) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    return {
        "feature_code": "B7-54",
        "operation": "query_meta_cognition_decision",
        "query_visible": True,
        "metacognition_status": "queried",
        "decision_bundle": state.meta_cognition.last_decision_snapshot(),
    }


def invoke_planned_cognitive_tools(
    kernel_service: Any,
    *,
    session_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    decision_bundle = context.get("decision_bundle")
    if not isinstance(decision_bundle, dict):
        raise ValueError("Phase 7 requires Feature 54 decision_bundle from Phase 6")
    tool_plan = decision_bundle.get("tool_invocation_plan")
    if not isinstance(tool_plan, dict):
        raise ValueError("Phase 7 requires Feature 54 tool_invocation_plan")
    selected_tools = tool_plan.get("selected_tools") or []
    if selected_tools and kernel_service._plugins_service is None:
        raise RuntimeError("Phase 7 cannot execute planned cognitive tools: plugins_service unavailable")
    method = getattr(kernel_service._plugins_service, "invoke_cognitive_tools", None)
    if selected_tools and not callable(method):
        raise RuntimeError("Phase 7 cannot execute planned cognitive tools: plugins_service.invoke_cognitive_tools unavailable")
    enriched_context = {
        **context,
        "cognitive_tool_plan": tool_plan,
        "selected_cognitive_tool_ids": [str(item.get("tool_id")) for item in selected_tools if isinstance(item, dict)],
        "metacognition_escalation": decision_bundle.get("escalation_decision") or {},
        "reasoning_mode_decision": decision_bundle.get("reasoning_mode_decision") or {},
    }
    result = method(session_id=session_id, context=enriched_context)
    if result is None:
        raise RuntimeError("Phase 7 cognitive tool execution returned None")
    if not isinstance(result, dict):
        raise RuntimeError("Phase 7 cognitive tool execution must return a dict")
    return {
        **result,
        "feature_code": "B7-54",
        "operation": "invoke_planned_cognitive_tools",
        "metacognition_plan_consumed": True,
        "consumed_plan_id": tool_plan.get("plan_id"),
        "selected_cognitive_tool_ids": enriched_context["selected_cognitive_tool_ids"],
    }


def run_phase6_metacognition(
    kernel_service: Any,
    *,
    session_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    state = _require_state(kernel_service, session_id)
    wm_frame = context.get("working_memory_frame") or state.working_memory.frame_snapshot()
    self_model = context.get("living_self_model") or state.self_model.snapshot()
    budget = context.get("reasoning_budget") or context.get("budget") or {"remaining_ratio": 1.0}
    nine_q_state = context.get("nine_q_state") or context.get("nine_question_state") or kernel_service._nq_shared_state.to_dict()
    agenda = context.get("agenda") or context.get("cognitive_agenda") or []
    tool_registry = context.get("tool_registry") or context.get("cognitive_tool_registry")
    if tool_registry is None:
        raise ValueError("Phase 6 metacognition requires an explicit cognitive tool_registry")
    return decide_meta_cognition(
        kernel_service,
        session_id=session_id,
        wm_frame=wm_frame,
        self_model=self_model,
        budget=budget,
        nine_q_state=nine_q_state,
        agenda=agenda,
        tool_registry=tool_registry,
        trace_id=context.get("trace_id"),
    )


def _require_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    return state


def _append_entry(
    state: Any,
    *,
    session_id: str,
    trace_id: Optional[str],
    result: dict[str, Any],
) -> None:
    bundle = result["decision_bundle"]
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.metacognition_decided,
            session_id=session_id,
            turn_id=bundle["decision_bundle_id"],
            trace_id=trace_id or f"metacognition:{bundle['decision_bundle_id']}",
            source="zentex.kernel.meta_cognition_runtime",
            payload={
                "feature_code": "B7-54",
                "entry_type": "metacognition_decided",
                "operation": "decide",
                "decision_bundle_id": bundle["decision_bundle_id"],
                "thought_mode": bundle["reasoning_mode_decision"]["thought_mode"],
                "decision_type": bundle["escalation_decision"]["decision_type"],
                "selected_tool_ids": [
                    item["tool_id"] for item in bundle["tool_invocation_plan"]["selected_tools"]
                ],
                "metacognition_status": result["metacognition_status"],
            },
        )
    )


def _read_after_write(state: Any, result: dict[str, Any]) -> dict[str, Any]:
    queried = state.meta_cognition.last_decision_snapshot()
    return {
        **result,
        "read_after_write": True,
        "queried_decision_bundle": queried,
    }
