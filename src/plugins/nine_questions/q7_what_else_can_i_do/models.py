from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, ConfigDict


class AlternativeStrategyProfile(BaseModel):
    """
    Q7 Result: Alternative Strategies and Fallback Plans.
    Ensures the brain can safely degrade or seek help when primary paths are blocked.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    fallback_plans: List[str] = Field(..., description="Safe alternative actions within current bounds.")
    degradation_strategies: List[str] = Field(..., description="Strategies to reduce functionality for safety.")
    collaboration_switches: List[str] = Field(..., description="Methods to request human or agent help. Explicitly identify targets like 'professional devops agents'.")
    exploratory_actions: List[str] = Field(..., description="Low-risk information gathering actions.")


class Q7InferenceResult(BaseModel):
    """
    Strict LLM output contract for Q7.
    """
    model_config = ConfigDict(extra="forbid")

    alternative_strategy_profile: AlternativeStrategyProfile
