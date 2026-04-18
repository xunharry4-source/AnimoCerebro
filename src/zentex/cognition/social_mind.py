from __future__ import annotations

"""
Interaction mind engine / 社会心智模型引擎。

该模块负责维护“系统如何理解当前交互对象”的内部状态，包括意图假设、
知识边界、表达适配和误解风险。它只允许影响脑内理解策略，绝对不允许
直接触发任何执行层动作。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import (
    ModelProviderCallerContext,
    ModelProviderSpec,
)
from zentex.llm.service import LLMService
from zentex.cognition.llm_prompt import build_interaction_mind_prompt


class StaleWriteError(RuntimeError):
    """在集群或共享状态下，拒绝落后快照版本写入。"""


class KnowledgeGapEstimate(BaseModel):
    """描述交互对象在当前话题上的知识边界。"""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    known_topics: List[str] = Field(default_factory=list)
    uncertain_topics: List[str] = Field(default_factory=list)
    likely_missing_topics: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class CommunicationFitProfile(BaseModel):
    """描述当前最适合的表达方式。"""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    preferred_style: Literal["brief", "structured", "evidence_first", "conclusion_first"]
    detail_level: Literal["low", "medium", "high"]
    clarification_bias: float = Field(ge=0.0, le=1.0)
    risk_of_misunderstanding: float = Field(ge=0.0, le=1.0)


class MisunderstandingSignal(BaseModel):
    """捕捉当前交互中的误解风险信号。"""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str = Field(min_length=1)
    signal_type: Literal[
        "correction",
        "frustration",
        "topic_shift",
        "contradiction",
        "silence_after_complexity",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InteractionMindModel(BaseModel):
    """综合表示系统对一个交互对象的动态理解。"""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    role_hint: str = Field(min_length=1)
    current_goal_hypothesis: str = Field(min_length=1)
    knowledge_depth: Literal["low", "medium", "high"]
    tolerance_for_detail: Literal["low", "medium", "high"]
    current_engagement_state: Literal["low", "medium", "high", "uncertain"]
    trust_estimate: float = Field(ge=0.0, le=1.0)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InteractionMindState(BaseModel):
    """交互对象的完整社会心智状态快照。"""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    brain_scope: str = Field(min_length=1)
    snapshot_version: int = Field(ge=0)
    clarification_mode: bool = False
    model: InteractionMindModel
    knowledge_gap: KnowledgeGapEstimate
    communication_fit: CommunicationFitProfile
    misunderstanding_signals: List[MisunderstandingSignal] = Field(default_factory=list)


class InteractionMindEngine:
    """
    对交互对象进行意图理解与误解风险建模的引擎。

    红线：
    - 只允许更新内部认知状态
    - 不允许调用执行域、外发消息或其他具备副作用的适配器
    - 所有状态写入都必须带 snapshot_version 做乐观并发控制
    """

    def __init__(
        self,
        *,
        llm_service: LLMService | None = None,
        model_provider: ModelProviderSpec | None = None,
        model_provider_key: str | None = None,
        brain_scope: str = "zentex.runtime",
        initial_states: Dict[str, InteractionMindState] | None = None,
    ) -> None:
        """
        初始化社会心智模型引擎。

        Args:
            llm_service: 统一 LLM 服务入口。
            model_provider: 兼容旧调用链的回退 provider。
            brain_scope: 当前集群/运行域的作用域标识。
            initial_states: 可选的初始快照，用于开发态或测试态种子。
        """
        self._llm_service = llm_service
        self._model_provider: ModelProviderSpec | None = model_provider
        self._model_provider_key = model_provider_key
        self._brain_scope: str = brain_scope
        self._states: Dict[str, InteractionMindState] = dict(initial_states or {})

    @property
    def brain_scope(self) -> str:
        """返回当前引擎所属的共享状态作用域。"""
        return self._brain_scope

    def get_state(self, entity_id: str) -> Optional[InteractionMindState]:
        """读取指定交互对象的最新心智状态。"""
        return self._states.get(entity_id)

    def seed_state(self, state: InteractionMindState) -> None:
        """注入开发态或测试态的已知状态。"""
        self._states[state.entity_id] = state

    def infer_interaction_mind(
        self,
        *,
        entity_id: str,
        snapshot_version: int,
        context: Dict[str, Any],
    ) -> InteractionMindState:
        """
        使用 live ModelProvider 推断交互对象的社会心智状态。

        Args:
            entity_id: 交互对象标识。
            snapshot_version: 当前主脑快照版本。
            context: 当前对话与行为上下文。

        Returns:
            InteractionMindState: 更新后的社会心智状态。

        Raises:
            StaleWriteError: 当前写入版本落后于已存状态时抛出。
            Exception: 透传底层 LLM 调用异常；失败时不得写入任何伪造心智状态。
        """
        current_state: Optional[InteractionMindState] = self._states.get(entity_id)
        self._assert_fresh_snapshot(
            entity_id=entity_id,
            snapshot_version=snapshot_version,
            current_state=current_state,
        )

        caller_context = ModelProviderCallerContext(
            source_module="Interaction mind engine",
            invocation_phase="inferring user intent and misunderstanding risk",
            question_driver_refs=["对方想要什么", "对方理解到了什么", "我该如何表达更容易被理解"],
            decision_id=f"interaction-mind:{entity_id}",
        )

        try:
            prompt = build_interaction_mind_prompt()["prompt"]
            translated_context = self._translate_context(context)
            if self._llm_service is not None:
                payload = self._llm_service.generate_json(
                    prompt=prompt,
                    context=translated_context,
                    caller_context=caller_context,
                    source_module=caller_context.source_module,
                    invocation_phase=caller_context.invocation_phase,
                    decision_id=caller_context.decision_id,
                    model_provider=self._model_provider_key,
                    metadata={"question_driver_refs": caller_context.question_driver_refs},
                ).output
            elif self._model_provider is not None:
                payload = self._model_provider.generate_json(
                    prompt=prompt,
                    context=translated_context,
                    caller_context=caller_context,
                )
            else:
                raise RuntimeError("LLM MANDATORY: missing llm_service and model_provider fallback")
        except Exception:
            raise

        inferred_state = InteractionMindState(
            entity_id=entity_id,
            brain_scope=self._brain_scope,
            snapshot_version=snapshot_version + 1,
            clarification_mode=False,
            model=InteractionMindModel.model_validate(
                {
                    "entity_id": entity_id,
                    **dict(payload.get("model") or {}),
                    "last_updated_at": datetime.now(timezone.utc),
                }
            ),
            knowledge_gap=KnowledgeGapEstimate.model_validate(
                {"entity_id": entity_id, **dict(payload.get("knowledge_gap") or {})}
            ),
            communication_fit=CommunicationFitProfile.model_validate(
                {"entity_id": entity_id, **dict(payload.get("communication_fit") or {})}
            ),
            misunderstanding_signals=[
                MisunderstandingSignal.model_validate(
                    {"entity_id": entity_id, **dict(signal)}
                )
                for signal in list(payload.get("misunderstanding_signals") or [])
            ],
        )
        self._states[entity_id] = inferred_state
        return inferred_state

    def record_user_correction(
        self,
        *,
        entity_id: str,
        corrected_goal_hypothesis: str,
        snapshot_version: int,
    ) -> InteractionMindState:
        """
        记录对方的明确纠正行为，并更新内部意图假设。

        Raises:
            KeyError: 目标实体尚无可更新状态。
            StaleWriteError: 当前写入版本落后于已存状态。
        """
        current_state: Optional[InteractionMindState] = self._states.get(entity_id)
        if current_state is None:
            raise KeyError(f"Unknown interaction entity: {entity_id}")
        self._assert_fresh_snapshot(
            entity_id=entity_id,
            snapshot_version=snapshot_version,
            current_state=current_state,
        )

        updated_signals: List[MisunderstandingSignal] = [
            *current_state.misunderstanding_signals,
            MisunderstandingSignal(
                entity_id=entity_id,
                signal_type="correction",
                severity="medium",
            ),
        ]
        updated_state = current_state.model_copy(
            update={
                "snapshot_version": snapshot_version + 1,
                "clarification_mode": False,
                "model": current_state.model.model_copy(
                    update={
                        "current_goal_hypothesis": corrected_goal_hypothesis,
                        "last_updated_at": datetime.now(timezone.utc),
                    }
                ),
                "communication_fit": current_state.communication_fit.model_copy(
                    update={
                        "clarification_bias": max(
                            0.2,
                            current_state.communication_fit.clarification_bias - 0.2,
                        ),
                        "risk_of_misunderstanding": max(
                            0.0,
                            current_state.communication_fit.risk_of_misunderstanding - 0.25,
                        ),
                    }
                ),
                "misunderstanding_signals": updated_signals,
            }
        )
        self._states[entity_id] = updated_state
        return updated_state

    def _assert_fresh_snapshot(
        self,
        *,
        entity_id: str,
        snapshot_version: int,
        current_state: Optional[InteractionMindState],
    ) -> None:
        """校验写入请求使用的是当前最新快照版本。"""
        if current_state is None:
            return
        if current_state.brain_scope != self._brain_scope:
            raise StaleWriteError(
                f"Interaction mind scope mismatch for {entity_id}: "
                f"expected {self._brain_scope}, got {current_state.brain_scope}"
            )
        if snapshot_version != current_state.snapshot_version:
            raise StaleWriteError(
                f"Stale interaction-mind write for {entity_id}: "
                f"expected snapshot_version {current_state.snapshot_version}, got {snapshot_version}"
            )

    def _build_clarification_state(
        self,
        *,
        entity_id: str,
        snapshot_version: int,
        context: Dict[str, Any],
        previous_state: Optional[InteractionMindState],
    ) -> InteractionMindState:
        """构造最保守的澄清模式状态，用于 LLM 失败后的安全回退。"""
        role_hint_source: Optional[str] = context.get("role_hint")
        if role_hint_source is None and previous_state is not None:
            role_hint_source = previous_state.model.role_hint
        role_hint: str = str(role_hint_source or "unknown partner")
        current_goal_hypothesis: str = "需要先澄清对方的真实意图，再继续推理"
        return InteractionMindState(
            entity_id=entity_id,
            brain_scope=self._brain_scope,
            snapshot_version=snapshot_version,
            clarification_mode=True,
            model=InteractionMindModel(
                entity_id=entity_id,
                role_hint=role_hint,
                current_goal_hypothesis=current_goal_hypothesis,
                knowledge_depth=previous_state.model.knowledge_depth if previous_state else "medium",
                tolerance_for_detail=previous_state.model.tolerance_for_detail if previous_state else "medium",
                current_engagement_state=previous_state.model.current_engagement_state if previous_state else "uncertain",
                trust_estimate=previous_state.model.trust_estimate if previous_state else 0.5,
            ),
            knowledge_gap=KnowledgeGapEstimate(
                entity_id=entity_id,
                known_topics=list(previous_state.knowledge_gap.known_topics) if previous_state else [],
                uncertain_topics=["当前意图", "关键约束"],
                likely_missing_topics=list(previous_state.knowledge_gap.likely_missing_topics) if previous_state else [],
                confidence=0.2,
            ),
            communication_fit=CommunicationFitProfile(
                entity_id=entity_id,
                preferred_style="structured",
                detail_level="low",
                clarification_bias=1.0,
                risk_of_misunderstanding=1.0,
            ),
            misunderstanding_signals=[
                *(list(previous_state.misunderstanding_signals) if previous_state else []),
                MisunderstandingSignal(
                    entity_id=entity_id,
                    signal_type="contradiction",
                    severity="high",
                ),
            ],
        )

    def _translate_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """把内部上下文翻译成更适合模型理解的自然语义键。"""
        key_map: Dict[str, str] = {
            "role_hint": "observed_role_hint",
            "latest_message": "latest_user_message",
            "conversation_summary": "conversation_summary",
            "user_feedback": "recent_user_feedback",
            "system_goal": "current_system_goal",
        }
        return {
            key_map.get(key, key.replace("_", " ")): value
            for key, value in context.items()
            if not callable(value)
        }


__all__ = [
    "CommunicationFitProfile",
    "InteractionMindEngine",
    "InteractionMindModel",
    "InteractionMindState",
    "KnowledgeGapEstimate",
    "MisunderstandingSignal",
    "StaleWriteError",
]
