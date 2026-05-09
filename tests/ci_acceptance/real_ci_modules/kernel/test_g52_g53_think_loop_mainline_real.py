from __future__ import annotations

from zentex.foundation.contracts import TurnRequest, TurnStatus
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.kernel.flow_domain.turn_protocol import TurnProtocol
from zentex.kernel.session_domain import KernelSession
from zentex.kernel.state_domain import (
    CognitiveTemporalEngine,
    SelfModelEngine,
    TranscriptEntryType,
    TranscriptStore,
    WorkingMemoryController,
)


class DeterministicMainlineBridge:
    def observe_environment(self, session_id: str, turn_id: str) -> dict:
        return {"observed_at": "2026-04-29T00:00:00+00:00", "physical_state": {"status": "ok"}}

    def evaluate_drive(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"drive": {"priority": "maintain_attention_integrity"}}

    def evaluate_cognition(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"framed_goal": {"goal_id": f"goal-{turn_id}", "summary": "keep current request grounded"}}

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        return {
            "conflict_reports": [
                {
                    "report_id": f"conflict-{context['turn_id']}",
                    "conflict_type": "high_risk_attention_shift",
                    "severity": "high",
                    "evidence_refs": [f"risk-evidence-{context['turn_id']}"],
                    "summary": "high risk signal must interrupt the current low-priority focus",
                }
            ],
            "high_risk_attention_items": [
                {
                    "focus_id": f"risk-focus-{context['turn_id']}",
                    "focus_type": "risk",
                    "title": "High risk mainline signal",
                    "summary": "A high risk signal requires immediate working-memory attention.",
                    "source_ref": f"risk:{context['turn_id']}",
                    "priority": 10,
                    "urgency": 10,
                    "uncertainty": 1,
                    "resume_hint": "Resume previous turn focus after risk review.",
                }
            ],
        }

    def run_simulation(self, session_id: str, context: dict) -> dict:
        return {"simulation": {"branches": ["continue_after_risk_review"]}}

    def run_metacognition(self, session_id: str, context: dict) -> dict:
        return {"metacognition": {"decision": "continue_with_conservative_attention"}}

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        return {"tool_results": [{"tool_id": "internal.attention_review", "status": "success"}]}

    def synthesize_decision(self, session_id: str, context: dict) -> dict:
        return {"response": "mainline risk was handled through working memory"}

    def consolidate_memory(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"memory_writeback": {"status": "recorded", "turn_id": turn_id}}


def test_g52_g53_think_loop_mainline_interrupts_updates_self_model_and_writes_transcript_real(tmp_path) -> None:
    session_id = "g52-g53-mainline-session"
    turn_id = "g52-g53-mainline-turn"
    session = KernelSession(session_id=session_id, user_id="g52-g53-mainline")
    transcript = TranscriptStore(session_id=session_id, db_dir=str(tmp_path))
    working_memory = WorkingMemoryController()
    self_model = SelfModelEngine(session_id=session_id)
    temporal = CognitiveTemporalEngine(session_id=session_id)
    bridge = DeterministicMainlineBridge()
    protocol = TurnProtocol(bridge=bridge, think_loop=ThinkLoop(bridge=bridge))

    result = protocol.execute(
        request=TurnRequest(
            turn_id=turn_id,
            session_id=session_id,
            user_input="Keep the current task grounded, but interrupt on high risk.",
            context={
                "attention_budget": {
                    "max_active_focus": 1,
                    "max_suspended_focus": 3,
                    "max_revisit_refs": 5,
                    "overflow_policy": "suspend_noncritical",
                }
            },
        ),
        session=session,
        transcript=transcript,
        working_memory=working_memory,
        self_model=self_model,
        temporal=temporal,
    )

    assert result.status == TurnStatus.completed
    assert result.response == "mainline risk was handled through working memory"
    cognitive_risks = next(phase for phase in result.phase_results if phase.phase_name == "cognitive_risks")
    assert len(cognitive_risks.output["cognitive_risk_interrupts_applied"]) == 1
    interrupt_result = cognitive_risks.output["cognitive_risk_interrupts_applied"][0]
    assert interrupt_result["attention_shift_events"][0]["shift_reason"] == "high_risk_interrupt"

    frame = working_memory.frame_snapshot()
    assert frame["active_focus_ids"] == [f"risk-focus-{turn_id}"]
    assert frame["suspended_focus_ids"] == [f"turn-focus-{turn_id}"]
    suspended = frame["suspended_items"][0]
    assert suspended["resume_hint"]
    assert "Current turn request" in frame["context_summary"]

    living_model = self_model.living_model_snapshot()
    assert living_model["current_state"]["load_level"] == "high"
    assert living_model["current_state"]["reasoning_posture"] == "conservative"
    assert living_model["current_risk_tolerance"] == "low"
    assert any(source["source_type"] == "turn_result" and source["source_ref"] == turn_id for source in living_model["update_sources"])
    assert any(signal["signal_type"] == "alert" for signal in living_model["emotion_like_signals"])

    entries = transcript.read_entries(session_id=session_id)
    wm_payloads = [entry.payload for entry in entries if entry.entry_type == TranscriptEntryType.working_memory_updated]
    self_payloads = [entry.payload for entry in entries if entry.entry_type == TranscriptEntryType.living_self_model_updated]
    assert any(payload["entry_type"] == "working_memory_updated" and payload["operation"] == "think_loop_working_state" for payload in wm_payloads)
    assert any(payload["entry_type"] == "attention_shift_event" and payload["shift_reason"] == "high_risk_interrupt" for payload in wm_payloads)
    assert any(payload["operation"] == "phase9_update_from_turn_result" for payload in self_payloads)
