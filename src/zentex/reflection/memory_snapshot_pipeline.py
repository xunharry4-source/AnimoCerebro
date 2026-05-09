from __future__ import annotations

"""
Pandas pipeline for reflection maintenance snapshots built from memory records.

RESPONSIBILITY:
  - Convert memory-service records into a normalized dataframe.
  - Build weighted memory snapshots for reflection maintenance.

DOES NOT:
  - Call any LLM
  - Persist reflection data
  - Delete or mutate records
"""

from datetime import datetime, timezone
from typing import Any, Dict

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pandas is required for zentex.reflection.memory_snapshot_pipeline. "
        "Add pandas>=2.0,<3.0 to requirements.txt and reinstall."
    ) from exc

from zentex.common.data_pipeline import compute_weighted_tag_counts, exponential_decay


def memory_records_to_dataframe(records: list[Any], *, now: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        created_at = getattr(record, "created_at", None)
        age_days = 0.0
        if isinstance(created_at, datetime):
            created_at = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        weight = exponential_decay(age_days, half_life_days=30.0)
        trust_level = str(getattr(record, "trust_level", "unknown") or "unknown")
        rows.append(
            {
                "memory_id": str(getattr(record, "memory_id", "") or ""),
                "layer": str(getattr(record, "memory_layer", "unknown") or "unknown"),
                "trust_level": trust_level,
                "trust_verified": trust_level in {"verified", "trusted"},
                "title": str(getattr(record, "title", "") or "").strip(),
                "tags": [str(tag).strip() for tag in list(getattr(record, "tags", []) or []) if str(tag).strip()],
                "age_days": age_days,
                "decayed_weight": weight,
            }
        )
    return pd.DataFrame(rows)


def build_memory_snapshot(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "summary": "Reflection maintenance: no active memory records were available.",
            "insights": [],
            "lessons": [],
            "risks": ["No recent active memory records were available to organize."],
            "improvements": [],
            "top_tags": [],
            "layer_distribution": {},
            "memory_ids": [],
            "titles": [],
            "unverified_count": 0,
            "tier_pressure": {
                "hot_ratio": 0.0,
                "unverified_ratio": 0.0,
                "low_weight_ratio": 0.0,
            },
        }

    weighted_tags = compute_weighted_tag_counts(df["tags"].tolist(), df["decayed_weight"].tolist())
    top_tags = list(weighted_tags.keys())[:5]
    layer_distribution = {str(k): int(v) for k, v in df["layer"].value_counts().to_dict().items()}
    titles = [title for title in df["title"].tolist() if title][:10]
    unverified_count = int((~df["trust_verified"]).sum())
    total = float(len(df))
    tier_pressure = {
        "hot_ratio": float((df["layer"] == "hot").sum()) / total,
        "unverified_ratio": float((~df["trust_verified"]).sum()) / total,
        "low_weight_ratio": float((df["decayed_weight"] < 0.3).sum()) / total,
    }
    insights: list[str] = []
    lessons: list[str] = []
    risks: list[str] = []
    improvements: list[str] = []
    if layer_distribution:
        insights.append(
            "Recent memory is concentrated in "
            + ", ".join(f"{layer}:{count}" for layer, count in layer_distribution.items())
            + "."
        )
    if top_tags:
        lessons.append("Recurring memory themes: " + ", ".join(top_tags[:3]) + ".")
        improvements.append("Prioritize reflection follow-up on: " + ", ".join(top_tags[:3]) + ".")
    if titles:
        insights.append("Representative memory titles: " + "; ".join(titles[:3]) + ".")
    if unverified_count:
        risks.append(f"{unverified_count} recent memory records are not yet verified.")
    if tier_pressure["low_weight_ratio"] > 0.4:
        improvements.append("Review stale low-weight memories before they crowd newer records.")

    summary_parts: list[str] = []
    if layer_distribution:
        summary_parts.append(
            "memory layers=" + ", ".join(f"{layer}:{count}" for layer, count in layer_distribution.items())
        )
    if top_tags:
        summary_parts.append("top tags=" + ", ".join(top_tags[:3]))
    if unverified_count:
        summary_parts.append(f"unverified={unverified_count}")
    summary_parts.append(
        "tier pressure="
        + ", ".join(f"{key}:{value:.2f}" for key, value in tier_pressure.items())
    )

    return {
        "summary": "Reflection maintenance: " + "; ".join(summary_parts),
        "insights": insights,
        "lessons": lessons,
        "risks": risks,
        "improvements": improvements,
        "top_tags": top_tags,
        "layer_distribution": layer_distribution,
        "memory_ids": [memory_id for memory_id in df["memory_id"].tolist() if memory_id][:10],
        "titles": titles,
        "unverified_count": unverified_count,
        "tier_pressure": tier_pressure,
    }

