from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.models import BrainRuntimeState  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.session import BrainSession  # noqa: E402


def _build_runtime(tmp_path: Path) -> tuple[BrainRuntime, dict[str, Mock]]:
    dependencies = {
        "transcript_store": Mock(name="transcript_store"),
        "reflection_store": Mock(name="reflection_store"),
        "runtime_memory_store": Mock(name="runtime_memory_store"),
        "identity_store": Mock(name="identity_store"),
        "tool_registry": Mock(name="tool_registry"),
        "working_memory_controller": Mock(name="working_memory_controller"),
        "temporal_engine": Mock(name="temporal_engine"),
        "living_self_model_engine": Mock(name="living_self_model_engine"),
        "metacognition_controller": Mock(name="metacognition_controller"),
        "conflict_engine": Mock(name="conflict_engine"),
        "counterfactual_engine": Mock(name="counterfactual_engine"),
        "interaction_mind_engine": Mock(name="interaction_mind_engine"),
        "consolidation_engine": Mock(name="consolidation_engine"),
    }
    runtime = BrainRuntime(
        runtime_id="runtime-test",
        default_workspace=str(tmp_path),
        transcript_store=dependencies["transcript_store"],
        reflection_store=dependencies["reflection_store"],
        runtime_memory_store=dependencies["runtime_memory_store"],
        identity_store=dependencies["identity_store"],
        tool_registry=dependencies["tool_registry"],
        identity_kernel_ref="identity-kernel:v1",
        tool_registry_version="tools:v3",
        working_memory_controller=dependencies["working_memory_controller"],
        temporal_engine=dependencies["temporal_engine"],
        living_self_model_engine=dependencies["living_self_model_engine"],
        metacognition_controller=dependencies["metacognition_controller"],
        conflict_engine=dependencies["conflict_engine"],
        counterfactual_engine=dependencies["counterfactual_engine"],
        interaction_mind_engine=dependencies["interaction_mind_engine"],
        consolidation_engine=dependencies["consolidation_engine"],
    )
    return runtime, dependencies


def _assert_runtime_has_no_session_process_state(runtime: BrainRuntime) -> None:
    assert not hasattr(runtime, "last_working_memory")
    assert not hasattr(runtime, "last_temporal_agenda")
    assert not hasattr(runtime, "last_living_self_model")
    assert not hasattr(runtime, "last_metacognition")
    assert not hasattr(runtime, "last_conflict_snapshot")
    assert not hasattr(runtime, "last_counterfactual_simulation")
    assert not hasattr(runtime, "last_interaction_mind")
    assert not hasattr(runtime, "last_consolidation")
    assert not hasattr(runtime, "last_reflection")


def test_runtime_initialization(tmp_path: Path) -> None:
    runtime, dependencies = _build_runtime(tmp_path)

    assert runtime.transcript_store is dependencies["transcript_store"]
    assert runtime.reflection_store is dependencies["reflection_store"]
    assert runtime.runtime_memory_store is dependencies["runtime_memory_store"]
    assert runtime.identity_store is dependencies["identity_store"]
    assert runtime.tool_registry is dependencies["tool_registry"]
    assert runtime.working_memory_controller is dependencies["working_memory_controller"]
    assert runtime.temporal_engine is dependencies["temporal_engine"]
    assert runtime.living_self_model_engine is dependencies["living_self_model_engine"]
    assert runtime.metacognition_controller is dependencies["metacognition_controller"]
    assert runtime.conflict_engine is dependencies["conflict_engine"]
    assert runtime.counterfactual_engine is dependencies["counterfactual_engine"]
    assert runtime.interaction_mind_engine is dependencies["interaction_mind_engine"]
    assert runtime.consolidation_engine is dependencies["consolidation_engine"]
    assert runtime._sessions == {}

    _assert_runtime_has_no_session_process_state(runtime)


def test_create_and_get_session(tmp_path: Path) -> None:
    runtime, dependencies = _build_runtime(tmp_path)

    session = runtime.create_session("session-test-1")

    assert isinstance(session, BrainSession)
    assert session.session_id == "session-test-1"
    assert session.store is dependencies["transcript_store"]

    same_session = runtime.get_session("session-test-1")
    assert same_session is session

    with pytest.raises(KeyError, match="Unknown session_id: missing-session"):
        runtime.get_session("missing-session")

    _assert_runtime_has_no_session_process_state(runtime)


def test_get_runtime_state(tmp_path: Path) -> None:
    runtime, _ = _build_runtime(tmp_path)
    runtime.create_session("session-b")
    runtime.create_session("session-a")

    state = runtime.get_runtime_state()

    assert isinstance(state, BrainRuntimeState)
    assert state.runtime_id == "runtime-test"
    assert isinstance(state.started_at, datetime)
    assert state.active_session_ids == ["session-a", "session-b"]
    assert state.default_workspace == str(tmp_path)
    assert state.identity_kernel_ref == "identity-kernel:v1"
    assert state.tool_registry_version == "tools:v3"
    assert state.transcript_store_status == "ready"
    assert state.memory_store_status == "ready"
    assert state.read_only_mode is False
    assert state.degraded_mode is False
    assert state.manual_confirmation_required is False
    assert isinstance(state.last_runtime_snapshot_at, datetime)
    assert runtime.last_runtime_snapshot_at == state.last_runtime_snapshot_at

    _assert_runtime_has_no_session_process_state(runtime)
