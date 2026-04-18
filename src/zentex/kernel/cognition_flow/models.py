"""Cognition-flow models — nine-question data types and bootstrap state."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from zentex.common.plugin_ids import (
    NINE_QUESTION_Q1,
    NINE_QUESTION_Q2,
    NINE_QUESTION_Q3,
    NINE_QUESTION_Q4,
    NINE_QUESTION_Q5,
    NINE_QUESTION_Q6,
    NINE_QUESTION_Q7,
    NINE_QUESTION_Q8,
    NINE_QUESTION_Q9,
)
from zentex.foundation.meta import FeatureFamily


class NineQuestionExecutionPhase(StrEnum):
    """Ordered phases within the execution of a single nine-question cycle."""

    context_gathering = "context_gathering"
    llm_inference = "llm_inference"
    state_write = "state_write"
    audit = "audit"


class BootstrapStatus(StrEnum):
    """Overall status of the nine-question bootstrap process."""

    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


@dataclass
class NineQuestion:
    """A single question in the nine-question cognitive bootstrap protocol."""

    question_id: str   # stable external id: q1 .. q9
    plugin_id: str     # canonical cognitive plugin id from zentex.common.plugin_ids
    text: str
    family: FeatureFamily
    priority: int      # lower number = higher priority


@dataclass
class NineQuestionResponse:
    """The answer produced for a single NineQuestion."""

    question_id: str
    answer: str
    confidence: float = 0.0
    duration_ms: float = 0.0
    error: str = ""
    tool_id: str = ""
    trace_id: str = ""
    timestamp: str = ""
    result_payload: dict[str, Any] = field(default_factory=dict)
    context_updates: dict[str, Any] = field(default_factory=dict)
    execution_context: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    llm_trace_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NineQuestionState:
    """Per-session state for the nine-question bootstrap cycle."""

    session_id: str
    responses: dict[str, NineQuestionResponse] = field(default_factory=dict)
    bootstrap_status: BootstrapStatus = BootstrapStatus.not_started
    last_updated_at: str = ""   # ISO 8601 timestamp


# ---------------------------------------------------------------------------
# Default question catalogue
# ---------------------------------------------------------------------------

DEFAULT_NINE_QUESTIONS: list[NineQuestion] = [
    NineQuestion(
        question_id="q1",
        plugin_id=NINE_QUESTION_Q1,
        text="环境/场景识别、工作域推断",
        family=FeatureFamily.cognition,
        priority=1,
    ),
    NineQuestion(
        question_id="q2",
        plugin_id=NINE_QUESTION_Q2,
        text="角色、身份、使命边界识别",
        family=FeatureFamily.cognition,
        priority=2,
    ),
    NineQuestion(
        question_id="q3",
        plugin_id=NINE_QUESTION_Q3,
        text="资产、工具、执行域盘点",
        family=FeatureFamily.execution,
        priority=3,
    ),
    NineQuestion(
        question_id="q4",
        plugin_id=NINE_QUESTION_Q4,
        text="能力边界推导",
        family=FeatureFamily.execution,
        priority=4,
    ),
    NineQuestion(
        question_id="q5",
        plugin_id=NINE_QUESTION_Q5,
        text="授权、合规、许可边界",
        family=FeatureFamily.safety,
        priority=5,
    ),
    NineQuestion(
        question_id="q6",
        plugin_id=NINE_QUESTION_Q6,
        text="红线、禁区、禁止动作",
        family=FeatureFamily.safety,
        priority=6,
    ),
    NineQuestion(
        question_id="q7",
        plugin_id=NINE_QUESTION_Q7,
        text="备选策略与替代动作",
        family=FeatureFamily.cognition,
        priority=7,
    ),
    NineQuestion(
        question_id="q8",
        plugin_id=NINE_QUESTION_Q8,
        text="当前目标排序与任务队列",
        family=FeatureFamily.cognition,
        priority=8,
    ),
    NineQuestion(
        question_id="q9",
        plugin_id=NINE_QUESTION_Q9,
        text="姿态、节奏、升级/降级策略",
        family=FeatureFamily.reflection,
        priority=9,
    ),
]
