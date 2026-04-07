from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional

from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.transcript import BrainTranscriptEntryType
from zentex.web_console.contracts.replay import (
    TranscriptReplayPayload,
    TurnReplayPayload,
    TurnReplayTraceGroup,
)
from zentex.web_console.transcript_serialization import serialize_transcript_entry


def build_replay_payload(
    runtime: BrainRuntime,
    event_id: str,
    *,
    include_payload: bool = True,
) -> TranscriptReplayPayload:
    """
    Build a replay payload from a trace id or transcript entry id.

    Why:
    - 前端调试是从“某次事件”跳进来，但底层 replay 需要回放整条 trace。
    - 因此这里允许 event_id 同时匹配 entry_id 和 trace_id，再统一展开全链路。
    """
    entries = runtime.transcript_store.get_entries_snapshot()
    matched_entry = next((entry for entry in entries if entry.entry_id == event_id), None)
    trace_id = matched_entry.trace_id if matched_entry is not None else event_id
    related_entries = runtime.transcript_store.read_by_trace_id(trace_id)
    if not related_entries:
        raise KeyError(f"Unknown replay event_id or trace_id: {event_id}")

    related_entries.sort(key=lambda item: item.timestamp.astimezone(timezone.utc).isoformat())
    source_module: Optional[str] = None
    invocation_phase: Optional[str] = None
    question_driver_refs: List[str] = []
    summary = "调用链路回放"

    for entry in related_entries:
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        caller_context = payload.get("caller_context") if isinstance(payload, dict) else None
        trace_chain = payload.get("trace_chain") if isinstance(payload, dict) else None
        if isinstance(caller_context, dict):
            source_module = str(caller_context.get("source_module") or source_module or "")
            invocation_phase = str(caller_context.get("invocation_phase") or invocation_phase or "")
            refs = caller_context.get("question_driver_refs")
            if isinstance(refs, list) and refs:
                question_driver_refs = [str(item) for item in refs]
        if isinstance(trace_chain, dict):
            source_module = str(trace_chain.get("source_module") or source_module or "")
            invocation_phase = str(trace_chain.get("phase_name") or invocation_phase or "")
        if entry.entry_type == BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED:
            action = str(payload.get("action") or "manual_action")
            reason = str(payload.get("reason") or "human intervention")
            question_driver_refs = [
                str(item)
                for item in payload.get("question_driver_refs", [])
                if isinstance(item, str)
            ]
            source_module = source_module or "Human Supervisor"
            invocation_phase = invocation_phase or str(payload.get("phase_name") or "phase_2_frame")
            summary = f"因为您的干预（{action} / {reason}），系统触发了九问重校验与状态回写。"
            continue
        if (
            entry.entry_type == BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN
            and isinstance(payload.get("nine_question_state"), dict)
        ):
            nine_question_state = payload["nine_question_state"]
            refresh_reason = str(nine_question_state.get("last_refresh_reason") or "")
            if refresh_reason.startswith("manual_intervention:"):
                source_module = source_module or "ThinkLoop"
                invocation_phase = invocation_phase or str(payload.get("target_phase") or "phase_2_frame")
                if not question_driver_refs:
                    refs = nine_question_state.get("question_driver_refs")
                    if isinstance(refs, list):
                        question_driver_refs = [str(item) for item in refs]
                summary = "因为您的干预，系统触发了九问重校验并刷新了目标框架。"
        if entry.entry_type == BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED:
            summary = f"{source_module or '主脑回路'} 在 {invocation_phase or '关键推理阶段'} 发起了一次模型调用。"
            break

    return TranscriptReplayPayload(
        event_id=event_id,
        trace_id=trace_id,
        summary=summary,
        source_module=(source_module or None),
        invocation_phase=(invocation_phase or None),
        question_driver_refs=question_driver_refs,
        events=[
            serialize_transcript_entry(entry, include_payload=include_payload)
            for entry in related_entries
        ],
    )


def build_turn_replay_payload(
    runtime: BrainRuntime,
    *,
    turn_id: str,
    session_id: Optional[str] = None,
    include_payload: bool = True,
) -> TurnReplayPayload:
    turn_entries = runtime.transcript_store.read_by_turn_id(turn_id)
    if session_id is not None:
        turn_entries = [entry for entry in turn_entries if entry.session_id == session_id]
    if not turn_entries:
        raise KeyError(f"Unknown replay turn_id: {turn_id}")

    turn_entries.sort(key=lambda item: item.timestamp.astimezone(timezone.utc).isoformat())
    first = turn_entries[0]
    trace_id = next(
        (
            entry.trace_id
            for entry in turn_entries
            if entry.entry_type == BrainTranscriptEntryType.TURN_STARTED
        ),
        first.trace_id,
    )

    counts_by_trace: Dict[str, int] = {}
    for entry in turn_entries:
        counts_by_trace[entry.trace_id] = counts_by_trace.get(entry.trace_id, 0) + 1

    def label_for_trace(candidate_trace_id: str) -> str:
        if candidate_trace_id.endswith(":phase_2_frame"):
            return "phase_2_frame"
        if candidate_trace_id.endswith(":phase_8_synthesize_decision"):
            return "phase_8_synthesize_decision"
        if candidate_trace_id.startswith("tool:") or candidate_trace_id.count("-") >= 2:
            return "cognitive_tool"
        if candidate_trace_id == trace_id:
            return "turn"
        return "trace"

    trace_groups = [
        TurnReplayTraceGroup(
            trace_id=trace_key,
            label=label_for_trace(trace_key),
            entry_count=count,
        )
        for trace_key, count in counts_by_trace.items()
    ]
    trace_groups.sort(key=lambda item: (item.label, item.trace_id))
    summary = f"Turn replay: {turn_id}"
    return TurnReplayPayload(
        session_id=first.session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        summary=summary,
        trace_groups=trace_groups,
        events=[
            serialize_transcript_entry(entry, include_payload=include_payload)
            for entry in turn_entries
        ],
    )
