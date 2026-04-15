from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol

from pydantic import BaseModel, Field


class IdentityKernel(Protocol):
    identity_id: str
    mission_baseline: str
    meta_motivation: str


class NineQuestionStateLike(Protocol):
    def __getattr__(self, name: str) -> Any: ...

logger = logging.getLogger(__name__)


class MetaDrive(BaseModel):
    """
    Configuration for the proactive nature of the AI.
    """
    primary_drive: str = Field(..., description="The dominant behavioral bias (e.g., 'efficiency', 'safety', 'exploration').")
    curiosity_level: float = Field(default=0.5, ge=0.0, le=1.0)
    safety_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    proactive_bias: float = Field(default=0.3, ge=0.0, le=1.0)


class Motivation(BaseModel):
    """
    A specific, situational driver for action.
    """
    id: str
    title: str
    strength: float = Field(ge=0.0, le=1.0)
    source_identity_ref: str
    source_nine_q_ref: List[str]
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MotivationEngine:
    """
    Translates static identity and situational awareness into active motivations.
    """
    def __init__(self, drive_config: Optional[MetaDrive] = None):
        self.drive_config = drive_config or MetaDrive(primary_drive="balanced")

    def generate_motivations(
        self, 
        identity: IdentityKernel, 
        nine_q_state: NineQuestionStateLike
    ) -> List[Motivation]:
        """
        Derives situational motivations from the identity kernel and nine questions.
        """
        motivations: List[Motivation] = []
        
        # 1. Base motivation from identity mission (Q8 link)
        motivations.append(Motivation(
            id=f"mission-{identity.identity_id}",
            title="Core Mission Pursuit",
            strength=0.9,
            source_identity_ref=identity.identity_id,
            source_nine_q_ref=["Q8"],
            description=f"Driven by core mission: {identity.mission_baseline}"
        ))

        # 2. Meta-motivation (Evolution/Drive)
        motivations.append(Motivation(
            id=f"meta-{identity.identity_id}",
            title="Sovereign Drive",
            strength=0.7,
            source_identity_ref=identity.identity_id,
            source_nine_q_ref=[],
            description=f"Internal driver: {identity.meta_motivation}"
        ))

        # 3. Situational Curiosity (Proactive bias)
        # If Q4 (Ability) or Q3 (Assets) shows uncertainty, curiosity might trigger evidence gathering.
        if self.drive_config.proactive_bias > 0.5:
             motivations.append(Motivation(
                id="proactive-exploration",
                title="Proactive Exploration",
                strength=self.drive_config.proactive_bias,
                source_identity_ref=identity.identity_id,
                source_nine_q_ref=["Q4"],
                description="Proactively seeking to expand situational knowledge."
            ))

        # 4. Filter or Adjust based on Vetoes
        # (Implementation of veto checking logic would go here)

        logger.info(f"MotivationEngine generated {len(motivations)} active drivers.")
        return motivations
