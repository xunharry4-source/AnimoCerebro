from __future__ import annotations

"""
BrainSession / 会话容器

EN:
BrainSession is the pure in-memory state container and snapshot manager. It is
responsible for replaying the transcript tape and restoring session state.

The continuity-facing identity kernel used by a session is intended to be
pluginized through Identity Package Plugins. Role packs, prohibition packs, and
domain experience packs may be loaded or switched independently while session
replay remains the stable continuity mechanism. Every package switch must
support rollback so subject continuity can recover from contamination or a bad
upgrade.

ZH:
BrainSession（会话容器）：纯内存的状态容器与快照管理器，负责录像带的重放与
状态恢复。

会话连续性所依赖的身份内核会进一步插件化为 Identity Package Plugins（身份与
经验包插件家族）。角色包、禁令包、行业经验包都可以独立加载、卸载与切换，而
transcript 回放机制继续作为主体连续性的稳定底座。所有身份包切换都必须支持回
退，以便在污染或错误升级时恢复主体连续性。
"""

from dataclasses import dataclass
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from zentex.runtime.transcript import (
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
    BrainTranscriptStore,
    JSONValue,
)
from zentex.runtime.nine_questions.state import NineQuestionState

EventSpec = Tuple[str, BrainTranscriptEntryType, str]


@dataclass(frozen=True)
class BrainSessionSnapshot:
    """会话快照，供 ThinkLoop 在下一轮推理时读取稳定上下文。"""

    session_id: str
    turn_count: int
    active_goal_titles: List[str]
    current_focus_summary: Optional[str]
    overdue_items: List[str]
    current_reasoning_mode: Optional[str]
    degraded_flags: List[str]
    last_turn_at: Optional[datetime]


class BrainSession:
    """
    Stateful session container for continuous thinking.

    Responsibilities:
    - hold session-local continuity state in memory
    - restore state by replaying transcript entries
    - persist turn-level runtime events through BrainTranscriptStore

    Explicitly out of scope:
    - global dependency bootstrapping
    - component assembly
    - nine-question reasoning
    - model invocation
    - tool orchestration

    Pluginization boundary:
    - session continuity may be informed by Identity Package Plugins
    - identity packs may carry role, prohibition, and domain experience layers
    - session restore still relies on transcript replay rather than plugin
      side effects
    - every identity package upgrade or switch must support rollback
    - package load failures must stay isolated from core session restore
    - rejection, revocation, degrade, and rollback reasons must remain auditable
    """

    def __init__(
        self,
        session_id: str,
        store: BrainTranscriptStore,
        runtime: Any = None,
    ) -> None:
        self.session_id = session_id
        self.store = store
        self.runtime = runtime

        self.created_at: Optional[datetime] = None
        self.turn_counter = 0
        self.current_workspace: Any = None
        self.active_goal_frame: Any = None
        self.last_context_snapshot: Any = None
        self.last_working_memory: Any = None
        self.last_temporal_agenda: Any = None
        self.last_living_self_model: Any = None
        self.last_metacognition: Any = None
        self.last_conflict_snapshot: Any = None
        self.last_counterfactual_simulation: Any = None
        self.last_interaction_mind: Any = None
        self.last_decision_summary: Any = None
        self.last_consolidation: Any = None
        self.last_reflection: Any = None
        self.last_turn_at: Optional[datetime] = None

        # Session-local nine-question snapshot cache (hot-path readable, no inference here).
        self.current_nine_question_state: NineQuestionState = NineQuestionState()
        self.active_evolution_result: Optional[Dict[str, Any]] = None

    def restore_from_transcript(self) -> "BrainSession":
        """通过 Transcript 回放恢复当前会话的内存态。"""
        self._reset_runtime_state()
        entries = list(self.store.read_by_session_id(self.session_id))
        if not entries:
            return self
            
        # Optimization: Process entries in bulk if possible, or at least avoid re-scanning
        for entry in entries:
            self._apply_entry(entry)
        return self

    def advance_turn(self, turn_result: Any) -> str:
        """
        Persist a single ThinkLoop turn into the append-only transcript.

        Args:
            turn_result: ThinkLoop 返回的单轮产物，允许为 `dict`、dataclass
                或暴露 `__dict__` 的对象。

        Returns:
            str: 实际写盘使用的 `turn_id`。

        Raises:
            TypeError: 当 `turn_result` 不是可转换的 dict-like 对象时抛出。
        """
        result = self._coerce_turn_result(turn_result)
        turn_id = str(result.get("turn_id") or uuid4())
        trace_id = str(result.get("trace_id") or turn_id)
        phase_trace_ids_raw = result.get("phase_trace_ids")
        phase_trace_ids = (
            {
                str(key): str(value)
                for key, value in phase_trace_ids_raw.items()
                if value is not None
            }
            if isinstance(phase_trace_ids_raw, dict)
            else {}
        )
        timestamp = self._coerce_timestamp(result.get("timestamp"))

        self._ensure_session_started(timestamp=timestamp, trace_id=trace_id, result=result)

        self.turn_counter += 1
        self.last_turn_at = timestamp

        self.store.write_entry(
            session_id=self.session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.TURN_STARTED,
            timestamp=timestamp,
            payload={
                "turn_index": self.turn_counter,
                "workspace": self._json_safe(result.get("current_workspace")),
            },
            source="brain_session",
            trace_id=trace_id,
        )

        if "current_workspace" in result:
            self.current_workspace = result["current_workspace"]
        if "active_goal_frame" in result:
            self.active_goal_frame = result["active_goal_frame"]

        event_specs: List[EventSpec] = [
            ("context_snapshot", BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN, "think_loop"),
            ("nine_question_state", BrainTranscriptEntryType.NINE_QUESTION_STATE_UPDATED, "think_loop"),
            ("working_memory", BrainTranscriptEntryType.WORKING_MEMORY_UPDATED, "think_loop"),
            ("temporal_agenda", BrainTranscriptEntryType.TEMPORAL_AGENDA_UPDATED, "think_loop"),
            ("living_self_model", BrainTranscriptEntryType.LIVING_SELF_MODEL_UPDATED, "think_loop"),
            ("conflict_snapshot", BrainTranscriptEntryType.CONFLICT_SNAPSHOT_WRITTEN, "think_loop"),
            ("counterfactual_simulation", BrainTranscriptEntryType.COUNTERFACTUAL_COMPLETED, "think_loop"),
            ("interaction_mind", BrainTranscriptEntryType.INTERACTION_MIND_UPDATED, "think_loop"),
            ("metacognition", BrainTranscriptEntryType.METACOGNITION_DECIDED, "think_loop"),
            ("decision", BrainTranscriptEntryType.DECISION_SYNTHESIZED, "think_loop"),
            ("reflection", BrainTranscriptEntryType.REFLECTION_PERSISTED, "think_loop"),
            ("consolidation", BrainTranscriptEntryType.CONSOLIDATION_COMPLETED, "think_loop"),
            ("evolution_result", BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN, "think_loop"),
            ("human_intervention", BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED, "human_supervisor"),
        ]
        for key, entry_type, source in event_specs:
            if key not in result:
                continue
            payload = result[key]
            if (
                entry_type == BrainTranscriptEntryType.NINE_QUESTION_STATE_UPDATED
                and isinstance(payload, NineQuestionState)
            ):
                payload = payload.to_payload()
            self._update_state_from_event_type(entry_type, payload)
            entry_trace_id = phase_trace_ids.get(key, trace_id)
            # 为什么这里不能统一使用 turn trace：只有保留 phase 级 trace，审计页才能把
            # “上下文构建/决策合成”这类具体阶段与对应的大模型调用精准绑死。
            self.store.write_entry(
                session_id=self.session_id,
                turn_id=turn_id,
                entry_type=entry_type,
                timestamp=timestamp,
                payload=self._json_safe(payload),
                source=source,
                trace_id=entry_trace_id,
            )

        self.store.write_entry(
            session_id=self.session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.TURN_FINISHED,
            timestamp=timestamp,
            payload={
                "turn_index": self.turn_counter,
                "status": str(result.get("status", "completed")),
            },
            source="brain_session",
            trace_id=trace_id,
        )
        return turn_id

    def get_snapshot(self) -> BrainSessionSnapshot:
        """提取当前会话的稳定快照，供 ThinkLoop 读取。"""
        active_goal_titles = self._extract_goal_titles(self.active_goal_frame)
        current_focus_summary = self._extract_current_focus_summary()
        overdue_items = self._extract_overdue_items(self.last_temporal_agenda)
        current_reasoning_mode = self._extract_reasoning_mode(self.last_metacognition)
        degraded_flags = self._extract_degraded_flags(
            self.last_metacognition,
            self.last_living_self_model,
        )
        return BrainSessionSnapshot(
            session_id=self.session_id,
            turn_count=self.turn_counter,
            active_goal_titles=active_goal_titles,
            current_focus_summary=current_focus_summary,
            overdue_items=overdue_items,
            current_reasoning_mode=current_reasoning_mode,
            degraded_flags=degraded_flags,
            last_turn_at=self.last_turn_at,
        )

    def _reset_runtime_state(self) -> None:
        """清空内存状态，确保 Transcript 回放从干净基线开始。"""
        self.created_at = None
        self.turn_counter = 0
        self.current_workspace = None
        self.active_goal_frame = None
        self.last_context_snapshot = None
        self.last_working_memory = None
        self.last_temporal_agenda = None
        self.last_living_self_model = None
        self.last_metacognition = None
        self.last_conflict_snapshot = None
        self.last_counterfactual_simulation = None
        self.last_interaction_mind = None
        self.last_decision_summary = None
        self.last_consolidation = None
        self.last_reflection = None
        self.last_turn_at = None
        self.current_nine_question_state = NineQuestionState()

    def _ensure_session_started(
        self,
        *,
        timestamp: datetime,
        trace_id: str,
        result: Dict[str, Any],
    ) -> None:
        """在首次落盘前补写 `session_started` 事件。"""
        if self.created_at is not None:
            return
        self.created_at = timestamp
        self.store.write_entry(
            session_id=self.session_id,
            turn_id=str(result.get("turn_id") or "session-bootstrap"),
            entry_type=BrainTranscriptEntryType.SESSION_STARTED,
            timestamp=timestamp,
            payload={
                "created_at": timestamp.isoformat(),
                "workspace": self._json_safe(result.get("current_workspace")),
                "active_goal_frame": self._json_safe(result.get("active_goal_frame")),
            },
            source="brain_session",
            trace_id=trace_id,
        )

    def _apply_entry(self, entry: BrainTranscriptEntry) -> None:
        """将单条 Transcript 事件回放到会话内存态。"""
        if self.created_at is None:
            self.created_at = entry.timestamp
        self.last_turn_at = entry.timestamp

        if entry.entry_type == BrainTranscriptEntryType.SESSION_STARTED:
            self.created_at = entry.timestamp
            if isinstance(entry.payload, dict):
                if "workspace" in entry.payload:
                    self.current_workspace = entry.payload.get("workspace")
                if "active_goal_frame" in entry.payload:
                    self.active_goal_frame = entry.payload.get("active_goal_frame")
            return

        if entry.entry_type == BrainTranscriptEntryType.TURN_STARTED:
            self.turn_counter += 1
            if isinstance(entry.payload, dict) and "workspace" in entry.payload:
                self.current_workspace = entry.payload.get("workspace")
            return

        self._update_state_from_event_type(entry.entry_type, entry.payload)

    def _update_state_from_event_type(
        self,
        entry_type: BrainTranscriptEntryType,
        payload: Any,
    ) -> None:
        """根据事件类型把 payload 写回对应的内存槽位。"""
        if entry_type == BrainTranscriptEntryType.WORKING_MEMORY_UPDATED:
            self.last_working_memory = payload
            return
        if entry_type == BrainTranscriptEntryType.TEMPORAL_AGENDA_UPDATED:
            self.last_temporal_agenda = payload
            return
        if entry_type == BrainTranscriptEntryType.LIVING_SELF_MODEL_UPDATED:
            self.last_living_self_model = payload
            return
        if entry_type == BrainTranscriptEntryType.CONFLICT_SNAPSHOT_WRITTEN:
            self.last_conflict_snapshot = payload
            return
        if entry_type == BrainTranscriptEntryType.COUNTERFACTUAL_COMPLETED:
            self.last_counterfactual_simulation = payload
            return
        if entry_type == BrainTranscriptEntryType.INTERACTION_MIND_UPDATED:
            self.last_interaction_mind = payload
            return
        if entry_type == BrainTranscriptEntryType.METACOGNITION_DECIDED:
            self.last_metacognition = payload
            return
        if entry_type == BrainTranscriptEntryType.CONSOLIDATION_COMPLETED:
            self.last_consolidation = payload
            return
        if entry_type == BrainTranscriptEntryType.REFLECTION_PERSISTED:
            self.last_reflection = payload
            return
        if entry_type == BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN:
            self.last_context_snapshot = payload
            if isinstance(payload, dict):
                if "active_goal_frame" in payload:
                    self.active_goal_frame = payload["active_goal_frame"]
                if "workspace" in payload:
                    self.current_workspace = payload["workspace"]
            return
        if entry_type == BrainTranscriptEntryType.DECISION_SYNTHESIZED:
            self.last_decision_summary = payload
            return
        if entry_type == BrainTranscriptEntryType.NINE_QUESTION_STATE_UPDATED:
            if isinstance(payload, dict):
                # Best-effort restore: writers are strict; replay is permissive.
                state = NineQuestionState()
                try:
                    state.snapshot_version = int(payload.get("snapshot_version") or 0)
                except Exception:
                    state.snapshot_version = 0
                try:
                    state.revision = int(payload.get("revision") or 0)
                except Exception:
                    state.revision = 0
                state.last_refresh_reason = str(payload.get("last_refresh_reason") or "replay")
                refreshed_at = payload.get("refreshed_at")
                if isinstance(refreshed_at, str):
                    try:
                        state.refreshed_at = datetime.fromisoformat(refreshed_at)
                    except Exception:
                        state.refreshed_at = datetime.now(timezone.utc)
                state.question_driver_refs = list(payload.get("question_driver_refs") or [])
                state.current_role_hypothesis = payload.get("current_role_hypothesis")
                state.current_context = dict(payload.get("current_context") or {})
                state.active_constraints = list(payload.get("active_constraints") or [])
                state.operator_patch = dict(payload.get("operator_patch") or {})
                dirty = payload.get("dirty_questions")
                if isinstance(dirty, dict):
                    state.dirty_questions = dict(dirty)
                snapshots = payload.get("question_snapshots")
                if isinstance(snapshots, dict):
                    state.question_snapshots = dict(snapshots)
                    # Log restoration for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"[Nine Questions Restore] Restored {len(state.question_snapshots)}/9 snapshots: "
                        f"{sorted(state.question_snapshots.keys())}"
                    )
                state.environment_fingerprint = payload.get("environment_fingerprint")
                state.agent_signature = payload.get("agent_signature")
                self.current_nine_question_state = state
            return

    def _coerce_turn_result(self, turn_result: Any) -> Dict[str, Any]:
        """把外部 turn 结果统一规整为 dict。"""
        if isinstance(turn_result, dict):
            return turn_result
        if is_dataclass(turn_result):
            return asdict(turn_result)
        if hasattr(turn_result, "__dict__"):
            return dict(vars(turn_result))
        raise TypeError("turn_result must be a dict-like object or expose __dict__")

    def _coerce_timestamp(self, value: Any) -> datetime:
        """把时间值统一规整成带时区的 UTC `datetime`。"""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return datetime.now(timezone.utc)

    def _extract_goal_titles(self, goal_frame: Any) -> List[str]:
        """从目标框架中提取标题列表，兼容多种落盘结构。"""
        if not isinstance(goal_frame, dict):
            return []
        goals = goal_frame.get("goals")
        if isinstance(goals, list):
            titles = []
            for goal in goals:
                if isinstance(goal, dict) and goal.get("title"):
                    titles.append(str(goal["title"]))
            if titles:
                return titles
        titles = goal_frame.get("active_goal_titles")
        if isinstance(titles, list):
            return [str(item) for item in titles]
        return []

    def _extract_current_focus_summary(self) -> Optional[str]:
        """从工作记忆或目标框架中提取当前聚焦摘要。"""
        for candidate in (self.last_working_memory, self.active_goal_frame):
            if isinstance(candidate, dict):
                for key in ("current_focus_summary", "focus_summary", "summary"):
                    value = candidate.get(key)
                    if value:
                        return str(value)
        return None

    def _extract_overdue_items(self, temporal_agenda: Any) -> List[str]:
        """提取当前已逾期事项列表。"""
        if not isinstance(temporal_agenda, dict):
            return []
        overdue_items = temporal_agenda.get("overdue_items")
        if not isinstance(overdue_items, list):
            return []
        return [str(item) for item in overdue_items]

    def _extract_reasoning_mode(self, metacognition: Any) -> Optional[str]:
        """提取当前元认知推理模式。"""
        if not isinstance(metacognition, dict):
            return None
        mode = metacognition.get("current_reasoning_mode") or metacognition.get("reasoning_mode")
        if mode is None:
            return None
        return str(mode)

    def _extract_degraded_flags(
        self,
        metacognition: Any,
        living_self_model: Any,
    ) -> List[str]:
        """汇总当前降级标记，优先使用最近一轮显式写入的数据。"""
        for candidate in (metacognition, living_self_model):
            if not isinstance(candidate, dict):
                continue
            flags = candidate.get("degraded_flags")
            if isinstance(flags, list):
                return [str(item) for item in flags]
        return []

    def _json_safe(self, value: Any) -> JSONValue:
        """把运行时对象安全转换为 Transcript 可落盘的 JSON 值。"""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        return str(value)
