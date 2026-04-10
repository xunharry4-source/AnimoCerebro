from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExpectedOutcome(BaseModel):
    """
    Registry for expected results before an action is taken.
    """
    expectation_id: str = Field(default_factory=lambda: f"exp-{uuid4().hex[:8]}")
    target_state: str
    success_criteria: List[str]
    predicted_impact: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_level: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RealOutcome(BaseModel):
    """
    Collected real outcome after action execution.
    """
    result_id: str = Field(default_factory=lambda: f"res-{uuid4().hex[:8]}")
    expectation_id: str
    actual_state: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutcomeDeviation(BaseModel):
    """
    The delta between expected and real outcomes.
    """
    deviation_id: str = Field(default_factory=lambda: f"dev-{uuid4().hex[:8]}")
    expectation_id: str
    result_id: str
    deviation_score: float = Field(ge=0.0, le=1.0)
    unforeseen_elements: List[str] = Field(default_factory=list)
    impact_delta: float
    analysis: str


class OutcomeBinding:
    """
    Engine to manage the lifecycle of outcome registration, collection, and comparison.
    """
    def __init__(self):
        self._expectations: Dict[str, ExpectedOutcome] = {}
        self._results: Dict[str, RealOutcome] = {}

    def register_expectation(self, target_state: str, success_criteria: List[str], confidence: float = 0.5) -> ExpectedOutcome:
        expectation = ExpectedOutcome(
            target_state=target_state,
            success_criteria=success_criteria,
            confidence_level=confidence
        )
        self._expectations[expectation.expectation_id] = expectation
        logger.info(f"Registered expectation: {expectation.expectation_id} for {target_state}")
        return expectation

    def collect_result(self, expectation_id: str, actual_state: str, metrics: Optional[Dict[str, Any]] = None) -> RealOutcome:
        if expectation_id not in self._expectations:
            logger.warning(f"Collecting result for unknown expectation: {expectation_id}")
        
        result = RealOutcome(
            expectation_id=expectation_id,
            actual_state=actual_state,
            metrics=metrics or {}
        )
        self._results[result.result_id] = result
        logger.info(f"Collected result: {result.result_id} for expectation {expectation_id}")
        return result

    def compare(self, result: RealOutcome) -> OutcomeDeviation:
        expectation = self._expectations.get(result.expectation_id)
        if not expectation:
             return OutcomeDeviation(
                expectation_id=result.expectation_id,
                result_id=result.result_id,
                deviation_score=1.0,
                impact_delta=0.0,
                analysis="No core expectation found to compare against."
            )

        # Simple semantic/heuristic comparison for now
        # In full implementation, this could involve LLM calls or metric checks
        score = 0.0
        if result.actual_state != expectation.target_state:
            score = 0.5 # Partial deviation
        
        # Calculate impact delta
        actual_impact = result.metrics.get("impact", 0.5)
        impact_delta = float(actual_impact) - expectation.predicted_impact

        deviation = OutcomeDeviation(
            expectation_id=expectation.expectation_id,
            result_id=result.result_id,
            deviation_score=score,
            impact_delta=impact_delta,
            analysis=f"Deviation analysis completed. Measured score: {score}"
        )
        return deviation
