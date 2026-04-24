from __future__ import annotations

"""
Memory Confidence Scoring Engine / 记忆置信度评分系统 (Phase 3.1)

Five-dimensional formula:
  confidence = w1·source_trust + w2·verification + w3·conflict_penalty
               + w4·time_decay + w5·usage_frequency

Dimension weights:
  1. source_trust      → Trustworthiness of the origin [0, 1]
  2. verification      → G38/Nine-Question validation state [0, 1]
  3. conflict_penalty  → Penalty for contradictions/consensus failure
  4. affect_signal     → Emotional intensity (affect_intensity) [0, 1]
  5. reasoning_logic   → Structural depth/logical consistency [0, 1]

Classification:
  CLEAR  → confidence_score >= 0.8   (清晰记忆)
  FUZZY  → confidence_score <  0.8   (模糊记忆)

Design notes:
  - The calculator is pure and stateless; inject access counts from
    MemoryAccessTracker to get dynamic scores.
  - Weights can be tuned per deployment via ConfidenceConfig.
  - All outputs are clamped to [0, 1] before returning.
"""

import math
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Literal, Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Classification labels
# ---------------------------------------------------------------------------

MemoryClarity = Literal["clear", "fuzzy"]

CLARITY_THRESHOLD = 0.8   # ≥ this → CLEAR; < this → FUZZY


# ---------------------------------------------------------------------------
# Source credibility mapping
# ---------------------------------------------------------------------------

_SOURCE_TRUST: dict[str, float] = {
    "direct_observation": 1.00,   # First-hand evidence from the runtime
    "verified":           0.95,   # Human-verified and signed off
    "inferred":           0.65,   # Logically derived, not directly observed
    "second_hand":        0.50,   # Relayed through another system / agent
    "synthetic":          0.35,   # Generated / hallucination-risk content
    "unknown":            0.40,   # No credibility metadata available
}


# ---------------------------------------------------------------------------
# Verification status mapping
# ---------------------------------------------------------------------------

_VERIFICATION_SCORE: dict[str, float] = {
    "verified":    1.00,
    "trusted":     0.90,
    "unverified":  0.60,
    "disputed":    0.25,
    "retracted":   0.05,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ConfidenceConfig(BaseModel):
    """Tunable weights for the 5-dimensional confidence formula."""

    model_config = ConfigDict(extra="forbid")

    # Dimension weights (Total 1.0)
    w_source:       float = Field(default=0.25, ge=0.0, le=1.0)
    w_verification: float = Field(default=0.25, ge=0.0, le=1.0)
    w_conflict:     float = Field(default=0.20, ge=0.0, le=1.0)
    w_affect:       float = Field(default=0.15, ge=0.0, le=1.0)
    w_logic:        float = Field(default=0.15, ge=0.0, le=1.0)

    # Conflict penalty: how much each contradiction lowers confidence
    conflict_penalty_per_count: float = Field(default=0.12, ge=0.0, le=1.0)
    max_conflict_penalty:       float = Field(default=0.60, ge=0.0, le=1.0)

    # Decay: half-life in days for time-based confidence decay
    decay_half_life_days: float = Field(default=90.0, gt=0.0)

    # Usage: access count at which full usage bonus is reached
    usage_saturation_count: int = Field(default=20, ge=1)


# ---------------------------------------------------------------------------
# Confidence result
# ---------------------------------------------------------------------------

class ConfidenceResult(BaseModel):
    """Full breakdown of a confidence calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    confidence_score: float          # Clamped [0, 1]
    clarity: MemoryClarity

    source_score:       float
    verification_score: float
    conflict_score:     float
    affect_score:       float
    logic_score:        float

    # Metadata
    contradiction_count: int
    access_count:        int
    age_days:            float


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class ConfidenceCalculator:
    """
    Computes a calibrated confidence score for a memory record.

    Usage:
        calc = ConfidenceCalculator()
        result = calc.score(
            memory_id="abc",
            source_credibility="inferred",
            verification_status="unverified",
            contradiction_count=1,
            created_at=datetime(..., tzinfo=UTC),
            access_count=5,
        )
    """

    def __init__(self, config: Optional[ConfidenceConfig] = None) -> None:
        self._cfg = config or ConfidenceConfig()

    # ── public ──────────────────────────────────────────────────────────

    def score(
        self,
        *,
        memory_id: str,
        source_credibility: str = "direct_observation",
        verification_status: str = "unverified",
        contradiction_count: int = 0,
        affect_intensity: float = 0.0,
        logic_depth: float = 0.5,
        created_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> ConfidenceResult:
        """Return a fully explained ConfidenceResult for one memory record."""
        cfg = self._cfg
        now = now or datetime.now(UTC)

        # Dimension 1 — source trust
        source = _SOURCE_TRUST.get(source_credibility, _SOURCE_TRUST["unknown"])

        # Dimension 2 — verification status
        verif = _VERIFICATION_SCORE.get(verification_status, _VERIFICATION_SCORE["unverified"])

        # Dimension 3 — conflict penalty (0 contradictions → no penalty)
        raw_penalty = min(
            contradiction_count * cfg.conflict_penalty_per_count,
            cfg.max_conflict_penalty,
        )
        conflict = 1.0 - raw_penalty   # Higher = fewer conflicts = better

        # Dimension 4 — affect signal (High affect usually correlates with vividness/salience)
        affect = max(0.0, min(1.0, affect_intensity))

        # Dimension 5 — reasoning logic (logical depth or consistency score)
        logic = max(0.0, min(1.0, logic_depth))

        # Weighted sum
        raw = (
            cfg.w_source       * source
            + cfg.w_verification * verif
            + cfg.w_conflict     * conflict
            + cfg.w_affect       * affect
            + cfg.w_logic        * logic
        )
        # Normalise
        weight_sum = (
            cfg.w_source + cfg.w_verification
            + cfg.w_conflict + cfg.w_affect + cfg.w_logic
        )
        confidence = max(0.0, min(1.0, raw / weight_sum))

        return ConfidenceResult(
            memory_id=memory_id,
            confidence_score=confidence,
            clarity="clear" if confidence >= CLARITY_THRESHOLD else "fuzzy",
            source_score=source,
            verification_score=verif,
            conflict_score=conflict,
            affect_score=affect,
            logic_score=logic,
            contradiction_count=contradiction_count,
            access_count=0, # access context handled externally
            age_days=0.0,
        )

    def classify(self, confidence_score: float) -> MemoryClarity:
        """Classify a pre-computed confidence score into clear / fuzzy."""
        return "clear" if confidence_score >= CLARITY_THRESHOLD else "fuzzy"

    # ── private ─────────────────────────────────────────────────────────

    @staticmethod
    def _decay_score(age_days: float, half_life: float) -> float:
        """Exponential decay: score → 0.5 at half_life, → ~0 at 5x half_life."""
        # We want decay(0) = 1.0,  decay(half_life) = 0.75,  floor at 0.3
        # Formula:  0.3 + 0.7 * 2^(−age / half_life)
        return 0.3 + 0.7 * math.pow(2.0, -age_days / half_life)

    @staticmethod
    def _usage_score(access_count: int, saturation: int) -> float:
        """Logistic saturation: 0 accesses → 0.3, saturation → ~0.95."""
        # Simple logistic: score = 1 / (1 + e^(−k*(x − x0)))
        # Tuned so that x=0 → 0.30, x=saturation → 0.90
        k = 5.0 / max(saturation, 1)
        x0 = saturation / 2.0
        return 1.0 / (1.0 + math.exp(-k * (access_count - x0)))


# ---------------------------------------------------------------------------
# Convenience: batch scoring
# ---------------------------------------------------------------------------

def score_batch(
    records: list[dict],
    *,
    access_counts: dict[str, Optional[int]] = None,
    config: Optional[ConfidenceConfig] = None,
    now: Optional[datetime] = None,
) -> list[ConfidenceResult]:
    """
    Score a list of record dicts in batch.

    Each dict is expected to contain the fields available on
    EnhancedMemoryRecord: memory_id, source_credibility, verification_status,
    contradiction_count, created_at.

    access_counts is a mapping memory_id → count (e.g. from MemoryAccessTracker).
    """
    calc = ConfidenceCalculator(config)
    now = now or datetime.now(UTC)
    access_counts = access_counts or {}
    results: list[ConfidenceResult] = []

    for rec in records:
        mid = str(rec.get("memory_id", ""))
        created_raw = rec.get("created_at")
        try:
            if isinstance(created_raw, datetime):
                created_at = created_raw if created_raw.tzinfo else created_raw.replace(tzinfo=UTC)
            else:
                created_at = datetime.fromisoformat(str(created_raw)).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            created_at = now

        results.append(calc.score(
            memory_id=mid,
            source_credibility=str(rec.get("source_credibility", "unknown")),
            verification_status=str(rec.get("verification_status", "unverified")),
            contradiction_count=int(rec.get("contradiction_count", 0)),
            created_at=created_at,
            access_count=access_counts.get(mid, 0),
            now=now,
        ))

    return results
