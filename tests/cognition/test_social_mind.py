from __future__ import annotations

from pathlib import Path
import sys
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.model_provider_spec import ModelProviderRateLimitError  # noqa: E402
from zentex.cognition.social_mind import (  # noqa: E402
    CommunicationFitProfile,
    InteractionMindEngine,
    InteractionMindModel,
    InteractionMindState,
    KnowledgeGapEstimate,
    MisunderstandingSignal,
    StaleWriteError,
)


def _build_seed_state(entity_id: str = "operator-1") -> InteractionMindState:
    """构造一条稳定的社会心智状态，用于并发和纠正测试。"""
    return InteractionMindState(
        entity_id=entity_id,
        brain_scope="cluster-a",
        snapshot_version=1,
        clarification_mode=False,
        model=InteractionMindModel(
            entity_id=entity_id,
            role_hint="operator",
            current_goal_hypothesis="想继续推进当前方案",
            knowledge_depth="medium",
            tolerance_for_detail="medium",
            current_engagement_state="high",
            trust_estimate=0.8,
        ),
        knowledge_gap=KnowledgeGapEstimate(
            entity_id=entity_id,
            known_topics=["插件状态"],
            uncertain_topics=["风险边界"],
            likely_missing_topics=["误解来源"],
            confidence=0.7,
        ),
        communication_fit=CommunicationFitProfile(
            entity_id=entity_id,
            preferred_style="evidence_first",
            detail_level="medium",
            clarification_bias=0.5,
            risk_of_misunderstanding=0.35,
        ),
        misunderstanding_signals=[
            MisunderstandingSignal(
                entity_id=entity_id,
                signal_type="topic_shift",
                severity="medium",
            ),
        ],
    )


def test_interaction_mind_engine_does_not_write_fallback_state_when_llm_is_rate_limited() -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.side_effect = ModelProviderRateLimitError("rate limited")
    dangerous_callback = mock.Mock(name="dangerous_execution_callback")
    engine = InteractionMindEngine(
        model_provider=model_provider,
        brain_scope="cluster-a",
    )

    with pytest.raises(ModelProviderRateLimitError, match="rate limited"):
        engine.infer_interaction_mind(
            entity_id="operator-1",
            snapshot_version=0,
            context={
                "role_hint": "operator",
                "latest_message": "为什么你总是给我内部字段？",
                "execution_adapter": dangerous_callback,
            },
        )

    state = engine.get_state("operator-1")
    # Fail-closed: do not mutate interaction mind state when the model provider fails.
    assert state is None
    assert dangerous_callback.call_count == 0


def test_interaction_mind_engine_updates_goal_hypothesis_after_user_correction() -> None:
    model_provider = mock.Mock()
    engine = InteractionMindEngine(
        model_provider=model_provider,
        brain_scope="cluster-a",
        initial_states={"operator-1": _build_seed_state()},
    )

    updated = engine.record_user_correction(
        entity_id="operator-1",
        corrected_goal_hypothesis="先修复回放链路，再评估是否扩展",
        snapshot_version=1,
    )

    assert updated.model.current_goal_hypothesis == "先修复回放链路，再评估是否扩展"
    assert updated.snapshot_version == 2
    assert any(signal.signal_type == "correction" for signal in updated.misunderstanding_signals)


def test_interaction_mind_engine_rejects_stale_snapshot_writes() -> None:
    model_provider = mock.Mock()
    engine = InteractionMindEngine(
        model_provider=model_provider,
        brain_scope="cluster-a",
        initial_states={"operator-1": _build_seed_state()},
    )

    with pytest.raises(StaleWriteError, match="Stale interaction-mind write"):
        engine.record_user_correction(
            entity_id="operator-1",
            corrected_goal_hypothesis="这是落后写入",
            snapshot_version=0,
        )
