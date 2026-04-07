from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.plugin_base import PluginLifecycleStatus  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.session import BrainSessionSnapshot  # noqa: E402
from zentex.runtime.think_loop import ThinkLoop  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402


@dataclass
class ManagedRecord:
    plugin: object
    feature_key: str


class FakePlugin:
    def __init__(self, *, plugin_id: str, kind: str, status: PluginLifecycleStatus, **attrs: object) -> None:
        self.plugin_id = plugin_id
        self.version = "9.9.9"
        self.status = status
        self._kind = kind
        for k, v in attrs.items():
            setattr(self, k, v)

    def plugin_kind(self) -> str:
        return self._kind


def _build_session(runtime: BrainRuntime):
    session = mock.Mock()
    session.session_id = "session-gating"
    session.turn_counter = 0
    session.current_workspace = {"cwd": "/workspace/zentex"}
    session.active_goal_frame = {"goals": [{"title": "Keep stable"}]}
    session.last_working_memory = {}
    session.last_metacognition = {}
    session.last_conflict_snapshot = {}
    session.runtime = runtime
    session.current_nine_question_state = runtime.nine_question_state
    session.get_snapshot.return_value = BrainSessionSnapshot(
        session_id=session.session_id,
        turn_count=0,
        active_goal_titles=["Keep stable"],
        current_focus_summary=None,
        overdue_items=[],
        current_reasoning_mode=None,
        degraded_flags=[],
        last_turn_at=datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
    )
    return session


def test_phase_2_framing_uses_cache_when_environment_unchanged() -> None:
    transcript_path = PROJECT_ROOT / "tmp_test_nine_question_gating.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()
    runtime = BrainRuntime(transcript_store=BrainTranscriptStore(transcript_path))

    ingest_plugin = FakePlugin(
        plugin_id="sensory-ingest-webhook",
        kind="signal_ingest",
        status=PluginLifecycleStatus.ACTIVE,
        ingest_signal=mock.Mock(return_value="system telemetry"),
    )
    sanitize_plugin = FakePlugin(
        plugin_id="sensory-sanitize-basic",
        kind="signal_sanitize",
        status=PluginLifecycleStatus.ACTIVE,
        sanitize_signal=mock.Mock(
            return_value=mock.Mock(
                sanitized_text="system telemetry",
                raw_fingerprint="fp-1",
                injection_risk=False,
                redaction_evidence=[],
            )
        ),
    )
    interpret_plugin = FakePlugin(
        plugin_id="sensory-interpret-generic",
        kind="signal_interpret",
        status=PluginLifecycleStatus.ACTIVE,
        interpret_signal=mock.Mock(
            return_value=mock.Mock(
                model_dump=mock.Mock(
                    return_value={
                        "event_type": "environment.observed",
                        "summary": "Observed external signal",
                        "structured_payload": {"raw_fingerprint": "fp-1"},
                    }
                )
            )
        ),
    )

    model_provider = FakePlugin(
        plugin_id="model-provider-fake",
        kind="model_provider",
        status=PluginLifecycleStatus.ACTIVE,
        generate_json=mock.Mock(
            return_value={
                "role_hypothesis": "operator",
                "nine_question_frame": {"q1": "cached", "q2": "cached", "q3": "cached"},
                "constraints": [],
                "immediate_priorities": [],
            }
        ),
    )

    runtime.managed_plugin_records = {
        "sensory-ingest-webhook": ManagedRecord(plugin=ingest_plugin, feature_key="sensory_ingest:webhook"),
        "sensory-sanitize-basic": ManagedRecord(plugin=sanitize_plugin, feature_key="sensory_sanitize:basic_prompt_injection_sanitizer"),
        "sensory-interpret-generic": ManagedRecord(plugin=interpret_plugin, feature_key="sensory_interpret:generic_environment"),
        "model-provider-fake": ManagedRecord(plugin=model_provider, feature_key="model_provider:fake"),
    }

    session = _build_session(runtime)
    think_loop = ThinkLoop()

    observed = think_loop._phase_1_observe(session=session, turn_id="t-1", started_at=datetime.now(timezone.utc))

    # 1st call: cold start -> should call model provider.
    think_loop._phase_2_frame(session=session, turn_id="t-1", observed=observed, phase_trace_id="t-1:phase_2_frame")
    assert model_provider.generate_json.call_count == 1

    # 2nd-5th calls: unchanged fingerprint -> should reuse cache and not call provider again.
    for idx in range(2, 6):
        think_loop._phase_2_frame(
            session=session,
            turn_id=f"t-{idx}",
            observed=observed,
            phase_trace_id=f"t-{idx}:phase_2_frame",
        )
    assert model_provider.generate_json.call_count == 1
