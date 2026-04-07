from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BrainTurnResult:
    """
    ThinkLoop 单轮执行完成后的完整交接对象。

    Responsibilities:
    - 承载单轮九阶段认知产物，供 `BrainSession.advance_turn` 统一落盘。
    - 保存 turn 级总 trace 与 phase 级 trace 映射，确保后续 Transcript 回放时能
      还原“哪一个阶段触发了哪一次大模型调用”。

    Field semantics:
    - `trace_id`: 当前 turn 的总追踪标识，用于串联 `session_started`、
      `turn_started`、`turn_finished` 等 turn 级事件。
    - `phase_trace_ids`: phase 到 trace 的映射，用于把 `context_snapshot`、
      `decision` 等关键阶段与对应的大模型调用严格绑定。
    """

    session_id: str
    turn_id: str
    started_at: datetime
    finished_at: datetime
    context_snapshot: Dict[str, Any]
    working_memory: Dict[str, Any]
    temporal_agenda: Dict[str, Any]
    living_self_model: Dict[str, Any]
    metacognition: Dict[str, Any]
    conflict_snapshot: Dict[str, Any]
    counterfactual_simulation: Dict[str, Any]
    interaction_mind: Dict[str, Any]
    tool_invocations: List[Dict[str, Any]] = field(default_factory=list)
    cognitive_tool_context: Dict[str, Any] = field(default_factory=dict)
    decision_summary: Dict[str, Any] = field(default_factory=dict)
    reflection_record: Dict[str, Any] = field(default_factory=dict)
    consolidation: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    phase_trace_ids: Dict[str, str] = field(default_factory=dict)
    nine_question_state: Optional[Any] = None
