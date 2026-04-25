from __future__ import annotations

"""
Pandas pipeline for learning maintenance cross-module summaries.

RESPONSIBILITY:
  - Merge memory and reflection records into a normalized dataframe.
  - Compute weighted tags and cross-module pressure for learning maintenance.

DOES NOT:
  - Call any LLM
  - Persist records
  - Route learning directions
"""

from datetime import datetime, timezone
from typing import Any, Dict

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pandas is required for zentex.learning.stats_pipeline. "
        "Add pandas>=2.0,<3.0 to requirements.txt and reinstall."
    ) from exc

from zentex.common.data_pipeline import compute_weighted_tag_counts, exponential_decay


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def merge_cross_module_records(
    memory_records: list[Any],
    reflection_records: list[Any],
    *,
    now: datetime,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in memory_records:
        created_at = getattr(record, "created_at", None)
        age_days = 0.0
        if isinstance(created_at, datetime):
            created_at = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        rows.append(
            {
                "record_id": str(getattr(record, "memory_id", "") or ""),
                "tags": [str(tag).strip() for tag in list(getattr(record, "tags", []) or []) if str(tag).strip()],
                "age_days": age_days,
                "decayed_weight": exponential_decay(age_days, half_life_days=30.0),
                "source_module": "memory",
                "focus_topic": "",
                "layer": str(getattr(record, "memory_layer", "unknown") or "unknown"),
                "memory_verified": str(getattr(record, "trust_level", "") or "") in {"verified", "trusted"},
                "reflection_low_quality": False,
            }
        )
    for record in reflection_records:
        created_at = getattr(record, "created_at", None)
        age_days = 0.0
        if isinstance(created_at, datetime):
            created_at = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        quality = _enum_value(getattr(record, "quality", "")).lower()
        rows.append(
            {
                "record_id": str(getattr(record, "reflection_id", "") or ""),
                "tags": [str(tag).strip() for tag in list(getattr(record, "tags", []) or []) if str(tag).strip()],
                "age_days": age_days,
                "decayed_weight": exponential_decay(age_days, half_life_days=45.0),
                "source_module": "reflection",
                "focus_topic": str(getattr(record, "subject", "") or "").strip(),
                "layer": "",
                "memory_verified": True,
                "reflection_low_quality": quality in {"poor", "fair"},
            }
        )
    return pd.DataFrame(rows)


def compute_weighted_cross_summary(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "summary": "Learning maintenance: no reusable memory or reflection context.",
            "top_weighted_tags": [],
            "focus_topics": [],
            "focus_topic_distribution": {},
            "cross_module_pressure": {
                "memory_unverified_ratio": 0.0,
                "reflection_low_quality_ratio": 0.0,
            },
            "layer_distribution": {},
            "memory_ids": [],
        }

    weighted_tags = compute_weighted_tag_counts(df["tags"].tolist(), df["decayed_weight"].tolist())
    top_weighted_tags = list(weighted_tags.keys())[:5]

    focus_df = df[(df["source_module"] == "reflection") & df["focus_topic"].astype(str).str.strip().ne("")]
    focus_topic_distribution = {str(k): int(v) for k, v in focus_df["focus_topic"].value_counts().to_dict().items()}
    focus_topics = list(focus_topic_distribution.keys())[:5]

    memory_df = df[df["source_module"] == "memory"]
    reflection_df = df[df["source_module"] == "reflection"]
    layer_distribution = {str(k): int(v) for k, v in memory_df["layer"].value_counts().to_dict().items() if str(k)}

    memory_unverified_ratio = (
        float((~memory_df["memory_verified"]).sum()) / float(len(memory_df))
        if not memory_df.empty
        else 0.0
    )
    reflection_low_quality_ratio = (
        float(reflection_df["reflection_low_quality"].sum()) / float(len(reflection_df))
        if not reflection_df.empty
        else 0.0
    )
    cross_module_pressure = {
        "memory_unverified_ratio": memory_unverified_ratio,
        "reflection_low_quality_ratio": reflection_low_quality_ratio,
    }
    summary_parts: list[str] = []
    if layer_distribution:
        summary_parts.append(
            "memory layers=" + ", ".join(f"{layer}:{count}" for layer, count in layer_distribution.items())
        )
    if top_weighted_tags:
        summary_parts.append("top weighted tags=" + ", ".join(top_weighted_tags[:3]))
    if focus_topics:
        summary_parts.append("reflection focus=" + "; ".join(focus_topics[:2]))
    summary_parts.append(
        "cross pressure=" + ", ".join(f"{k}:{v:.2f}" for k, v in cross_module_pressure.items())
    )

    return {
        "summary": "Learning maintenance: " + "; ".join(summary_parts),
        "top_weighted_tags": top_weighted_tags,
        "focus_topics": focus_topics,
        "focus_topic_distribution": focus_topic_distribution,
        "cross_module_pressure": cross_module_pressure,
        "layer_distribution": layer_distribution,
        "memory_ids": [str(rid) for rid in memory_df["record_id"].tolist() if str(rid)][:10],
    }
