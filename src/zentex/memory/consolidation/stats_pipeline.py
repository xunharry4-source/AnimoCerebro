from __future__ import annotations

"""
Pandas statistics pipeline for memory consolidation scoring.

RESPONSIBILITY:
  - Convert input memory refs into a normalized dataframe.
  - Compute real pattern stability scores based on time span, reuse, and failures.

DOES NOT:
  - Perform semantic clustering
  - Call any LLM
  - Persist governance state
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pandas is required for zentex.memory.consolidation.stats_pipeline. "
        "Add pandas>=2.0,<3.0 to requirements.txt and reinstall."
    ) from exc

from zentex.common.data_pipeline import exponential_decay
from zentex.memory.consolidation.consolidation import PatternStabilityScore


def refs_to_dataframe(input_refs: list[dict], *, now_ts: float) -> pd.DataFrame:
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
    return pd.DataFrame(rows)


def compute_pattern_scores(df: pd.DataFrame) -> List[PatternStabilityScore]:
    scores: list[PatternStabilityScore] = []
    if df.empty or "tags" not in df.columns:
        return scores

    exploded = df.explode("tags")
    exploded = exploded[exploded["tags"].notna() & (exploded["tags"].astype(str).str.strip() != "")]
    if exploded.empty:
        return scores

    for tag, group in exploded.groupby("tags", dropna=True):
        frequency = int(len(group))
        if frequency < 2:
            continue
        created_series = group["created_at_ts"].dropna()
        if created_series.empty:
            time_span_seconds = 0
        else:
            time_span_seconds = int(max(0.0, float(created_series.max()) - float(created_series.min())))
        cross_context_reuse = float(group["decayed_reuse"].fillna(0.0).mean())
        failure_count = int(group["is_failure"].fillna(False).sum())
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


def compute_tier_pressure(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {
            "record_count": 0.0,
            "failure_ratio": 0.0,
            "low_reuse_ratio": 0.0,
        }
    record_count = float(len(df))
    failure_ratio = float(df["is_failure"].fillna(False).sum()) / record_count
    low_reuse_ratio = float((df["decayed_reuse"].fillna(0.0) < 0.3).sum()) / record_count
    return {
        "record_count": record_count,
        "failure_ratio": failure_ratio,
        "low_reuse_ratio": low_reuse_ratio,
    }

