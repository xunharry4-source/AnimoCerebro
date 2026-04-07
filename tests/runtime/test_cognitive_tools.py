from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.cognitive_tools import (  # noqa: E402
    CognitiveToolOrchestrator,
    CognitiveToolRegistry,
    CognitiveToolResult,
    CognitiveToolSpec,
    ToolInvocationPlan,
)


def _build_tool_specs() -> tuple[CognitiveToolSpec, CognitiveToolSpec, CognitiveToolSpec]:
    tool_a = CognitiveToolSpec(
        tool_id="tool-a",
        tool_type="analysis",
        purpose="Read-only risk comparison",
        inputs=["context_snapshot"],
        outputs=["ranked_options"],
        required_context=["context_snapshot", "memory_refs"],
        trigger_conditions=["metacognition"],
        do_not_use_when=["no_analysis"],
        is_concurrency_safe=True,
        priority=10,
    )
    tool_b = CognitiveToolSpec(
        tool_id="tool-b",
        tool_type="analysis",
        purpose="Read-only evidence ranking",
        inputs=["context_snapshot"],
        outputs=["evidence"],
        required_context=["context_snapshot", "memory_refs"],
        trigger_conditions=["metacognition"],
        do_not_use_when=["skip_tool_b"],
        is_concurrency_safe=True,
        priority=20,
    )
    tool_c = CognitiveToolSpec(
        tool_id="tool-c",
        tool_type="state_refinement",
        purpose="Refresh working memory hypotheses",
        inputs=["working_memory"],
        outputs=["working_memory"],
        required_context=["context_snapshot", "memory_refs"],
        trigger_conditions=["metacognition"],
        do_not_use_when=[],
        is_concurrency_safe=False,
        priority=30,
    )
    return tool_a, tool_b, tool_c


def _make_executor(spec: CognitiveToolSpec) -> Mock:
    return Mock(
        name=f"executor_{spec.tool_id}",
        return_value=CognitiveToolResult(
            tool_id=spec.tool_id,
            summary=f"{spec.tool_id} completed",
            proposals=[{"tool_id": spec.tool_id, "proposal": "inspect"}],
            ranked_options=[{"tool_id": spec.tool_id, "rank": 1}],
            risks=[{"tool_id": spec.tool_id, "risk": "bounded"}],
            evidence=[{"tool_id": spec.tool_id, "evidence": "trace"}],
            uncertainties=[{"tool_id": spec.tool_id, "uncertainty": "low"}],
            context_updates={"note": f"{spec.tool_id}-safe"},
            confidence=0.8,
        ),
    )


def test_registry_registration_and_resolution() -> None:
    registry = CognitiveToolRegistry()
    tool_a, tool_b, tool_c = _build_tool_specs()

    registry.register(tool_a, _make_executor(tool_a))
    registry.register(tool_b, _make_executor(tool_b))
    registry.register(tool_c, _make_executor(tool_c))

    resolved = registry.resolve_candidates(
        {
            "phase": "metacognition",
            "context_snapshot": {"goal": "assess"},
            "memory_refs": ["memory-1"],
            "state_flags": ["skip_tool_b"],
        }
    )

    assert [tool.spec.tool_id for tool in resolved] == ["tool-a", "tool-c"]
    assert registry.get("tool-a").spec is tool_a
    assert [tool.spec.tool_id for tool in registry.list()] == ["tool-a", "tool-b", "tool-c"]


def test_orchestrator_concurrency_grouping() -> None:
    registry = CognitiveToolRegistry()
    tool_a, tool_b, tool_c = _build_tool_specs()
    executor_a = _make_executor(tool_a)
    executor_b = _make_executor(tool_b)
    executor_c = _make_executor(tool_c)
    registry.register(tool_a, executor_a)
    registry.register(tool_b, executor_b)
    registry.register(tool_c, executor_c)

    orchestrator = CognitiveToolOrchestrator(registry)
    plan = ToolInvocationPlan(
        session_id="session-1",
        turn_id="turn-1",
        phase="metacognition",
        context={
            "context_snapshot": {"goal": "group-tools"},
            "memory_refs": ["memory-1"],
            "state_flags": [],
        },
        requested_tool_ids=["tool-a", "tool-b", "tool-c"],
    )

    report = orchestrator.orchestrate(plan)

    assert report.selected_tools == ["tool-a", "tool-b", "tool-c"]
    assert report.parallel_groups == [["tool-a", "tool-b"]]
    assert report.serial_groups == [["tool-c"]]
    assert [invocation.tool_id for invocation in report.invocations] == [
        "tool-a",
        "tool-b",
        "tool-c",
    ]
    assert all(invocation.session_id == "session-1" for invocation in report.invocations)
    assert all(invocation.turn_id == "turn-1" for invocation in report.invocations)
    executor_a.assert_called_once_with(plan.context)
    executor_b.assert_called_once_with(plan.context)
    executor_c.assert_called_once_with(plan.context)


def test_orchestrator_cognitive_boundary() -> None:
    registry = CognitiveToolRegistry()
    tool_a, _, _ = _build_tool_specs()
    violating_executor = Mock(
        name="violating_executor",
        return_value=CognitiveToolResult(
            tool_id="tool-a",
            summary="attempted side effect",
            proposals=[{"proposal": "ask host"}],
            ranked_options=[],
            risks=[{"risk": "unsafe"}],
            evidence=[],
            uncertainties=[],
            context_updates={
                "external_action": {"kind": "write_file", "path": "/tmp/x"},
            },
            confidence=0.2,
        ),
    )
    registry.register(tool_a, violating_executor)

    orchestrator = CognitiveToolOrchestrator(registry)
    plan = ToolInvocationPlan(
        session_id="session-boundary",
        turn_id="turn-boundary",
        phase="metacognition",
        context={
            "context_snapshot": {"goal": "boundary-check"},
            "memory_refs": ["memory-1"],
            "state_flags": [],
        },
        requested_tool_ids=["tool-a"],
    )

    with pytest.raises(ValueError, match="forbidden external action: external_action"):
        orchestrator.orchestrate(plan)

    violating_executor.assert_called_once_with(plan.context)
