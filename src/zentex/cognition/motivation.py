from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol

from pydantic import BaseModel, Field


class IdentityKernel(Protocol):
    identity_id: str
    mission_baseline: str
    meta_motivation: str


class DataDeprivationError(RuntimeError):
    """Raised when motivation cannot be derived due to missing cognitive inputs."""
    pass


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
        
        Fail-Closed Policy: 
        1. If identity mission is missing, raises RuntimeError.
        2. If required NQ data (e.g., confidence) is missing, raises DataDeprivationError.
        """
        if not getattr(identity, "mission_baseline", None):
            raise RuntimeError("MotivationEngine: Identity mission baseline is missing. Cannot derive authentic drivers.")
            
        motivations: List[Motivation] = []
        
        # 1. Base motivation from identity mission (Q8 link)
        # Policy: No default confidence. Must be provided by the cognition layer.
        q1_certainty = getattr(nine_q_state, "q1_confidence", None)
        if q1_certainty is None:
            raise DataDeprivationError("MotivationEngine: q1_confidence is missing. Cannot evaluate mission strength.")
            
        # Strength is a non-linear function of certainty
        mission_strength = 0.5 + (0.5 * q1_certainty)
        
        motivations.append(Motivation(
            id=f"mission-{identity.identity_id}",
            title="Core Mission Pursuit",
            strength=mission_strength,
            source_identity_ref=identity.identity_id,
            source_nine_q_ref=["Q8", "Q1"],
            description=f"Driven by core mission: {identity.mission_baseline}"
        ))
        
        # 2. Situational Curiosity (Proactive bias)
        if self.drive_config.proactive_bias > 0.0:
            knowledge_gap = 1.0 - q1_certainty
            curiosity_strength = self.drive_config.proactive_bias * (knowledge_gap ** 2) # Penalize low gaps
            
            if curiosity_strength > 0.1:
                motivations.append(Motivation(
                    id="proactive-exploration",
                    title="Proactive Exploration",
                    strength=min(0.95, curiosity_strength),
                    source_identity_ref=identity.identity_id,
                    source_nine_q_ref=["Q4", "Q1"],
                    description="Proactively seeking to expand situational knowledge based on observed gaps."
                ))
                
        # 3. Defensive Bias (Safety drive)
        risk_level = getattr(nine_q_state, "risk_level", None)
        if risk_level is None:
             raise DataDeprivationError("MotivationEngine: risk_level is missing. Cannot evaluate safety drive.")

        if risk_level > self.drive_config.safety_threshold:
            motivations.append(Motivation(
                id="safety-preservation",
                title="Safety Preservation",
                strength=risk_level,
                source_identity_ref=identity.identity_id,
                source_nine_q_ref=["Q5", "Q6"],
                description=f"High risk detected ({risk_level:.2f}); prioritizing safety over efficiency."
            ))

        # 4. Filter or Adjust based on Vetoes
        veto_active = getattr(nine_q_state, "q6_veto_active", False)
        if veto_active:
            veto_reason = getattr(nine_q_state, "q6_veto_reason", "Ethics/Safety Veto")
            logger.warning(f"Cognitive Veto active: {veto_reason}. Filtering conflicting drives.")
            # Policy: Only safety preservation is allowed to persist during an active veto
            motivations = [m for m in motivations if m.id == "safety-preservation"]
            if not motivations:
                # If no safety-preservation exists but veto is active, create an emergency drive
                motivations.append(Motivation(
                    id="emergency-halt",
                    title="Cognitive Halt",
                    strength=1.0,
                    source_identity_ref=identity.identity_id,
                    source_nine_q_ref=["Q6"],
                    description=f"Emergency halt triggered by veto: {veto_reason}"
                ))

        logger.info(f"MotivationEngine generated {len(motivations)} authentic active drivers.")
        return motivations
