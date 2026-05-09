from __future__ import annotations

"""
Standard-library statistics pipeline for memory consolidation scoring.

RESPONSIBILITY:
  - Convert input memory refs into normalized row dictionaries.
  - Compute real pattern stability scores based on time span, reuse, and failures.

DOES NOT:
  - Perform semantic clustering
  - Call any LLM
  - Persist governance state
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from zentex.common.data_pipeline import exponential_decay
from zentex.memory.consolidation.consolidation import PatternStabilityScore


def refs_to_dataframe(input_refs: list[dict], *, now_ts: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in input_refs:
        created_at_ts = ref.get("created_at_ts")
        try:
            created_ts_value = float(created_at_ts) if created_at_ts is not None else None
        except (TypeError, ValueError):
            created_ts_value = None
        age_days = (
            max(0.0, (float(now_ts) - created_ts_value) / 86400.0)
            if created_ts_value is not None
            else None
        )
        try:
            reuse_value = float(ref.get("reuse_value", 0.0) or 0.0)
        except (TypeError, ValueError):
            reuse_value = 0.0
        decay = exponential_decay(age_days, half_life_days=30.0) if age_days is not None else 0.0
        rows.append(
            {
                "ref_id": str(ref.get("ref_id") or ref.get("id") or ""),
                "created_at_ts": created_ts_value,
                "age_days": age_days,
                "reuse_value": max(0.0, min(1.0, reuse_value)),
                "decayed_reuse": max(0.0, min(1.0, reuse_value * decay)),
                "tags": [str(tag).strip() for tag in list(ref.get("tags", []) or []) if str(tag).strip()],
                "outcome_type": str(ref.get("outcome_type") or "").strip().lower(),
                "is_failure": str(ref.get("outcome_type") or "").strip().lower() == "failure",
            }
        )
    return rows


def compute_pattern_scores(df: list[dict[str, Any]]) -> List[PatternStabilityScore]:
    scores: list[PatternStabilityScore] = []
    if not df:
        return scores

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in df:
        for tag in list(row.get("tags") or []):
            tag_text = str(tag).strip()
            if tag_text:
                grouped.setdefault(tag_text, []).append(row)

    for tag, group in grouped.items():
        frequency = len(group)
        if frequency < 2:
            continue
        created_values = [
            float(row["created_at_ts"])
            for row in group
            if row.get("created_at_ts") is not None
        ]
        if not created_values:
            time_span_seconds = 0
        else:
            time_span_seconds = int(max(0.0, max(created_values) - min(created_values)))
        cross_context_reuse = sum(float(row.get("decayed_reuse") or 0.0) for row in group) / float(frequency)
        failure_count = sum(1 for row in group if bool(row.get("is_failure")))
        stability_score = max(0.0, min(1.0, cross_context_reuse - failure_count * 0.15))
        scores.append(
            PatternStabilityScore(
                pattern_id=f"tag:{tag}",
                frequency=frequency,
                time_span_seconds=time_span_seconds,
                cross_context_reuse=cross_context_reuse,
                conflict_count=0,
                failure_count=failure_count,
                stability_score=stability_score,
            )
        )
    return sorted(scores, key=lambda item: (-item.stability_score, -item.frequency, item.pattern_id))


def compute_tier_pressure(df: list[dict[str, Any]]) -> Dict[str, float]:
    if not df:
        return {
            "record_count": 0.0,
            "failure_ratio": 0.0,
            "low_reuse_ratio": 0.0,
        }
    record_count = float(len(df))
    failure_ratio = float(sum(1 for row in df if bool(row.get("is_failure")))) / record_count
    low_reuse_ratio = float(sum(1 for row in df if float(row.get("decayed_reuse") or 0.0) < 0.3)) / record_count
    return {
        "record_count": record_count,
        "failure_ratio": failure_ratio,
        "low_reuse_ratio": low_reuse_ratio,
    }
