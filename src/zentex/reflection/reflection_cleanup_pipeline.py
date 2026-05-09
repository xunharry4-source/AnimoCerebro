from __future__ import annotations

"""
Pandas pipeline for reflection cleanup candidate extraction.

RESPONSIBILITY:
  - Normalize reflection rows used in cleanup maintenance.
  - Extract deletion candidates using deterministic rules.

DOES NOT:
  - Delete records
  - Mark suspect
  - Perform semantic duplicate detection in this phase
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pandas is required for zentex.reflection.reflection_cleanup_pipeline. "
        "Add pandas>=2.0,<3.0 to requirements.txt and reinstall."
    ) from exc

from zentex.common.data_pipeline import exponential_decay
from zentex.reflection.models import GovernanceStatus, ReflectionQuality, ReflectionRecord


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def reflections_to_dataframe(records: list[ReflectionRecord], *, now: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        created_at = record.created_at if record.created_at.tzinfo else record.created_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        signature_seed = f"{str(record.subject or '').strip().lower()}::{str(record.summary or '').strip().lower()}"
        rows.append(
            {
                "reflection_id": record.reflection_id,
                "subject": str(record.subject or ""),
                "summary": str(record.summary or ""),
                "quality": _enum_value(record.quality),
                "confidence": float(record.confidence),
                "actionability": float(record.actionability),
                "age_days": age_days,
                "decayed_confidence": float(record.confidence) * exponential_decay(age_days, half_life_days=60.0),
                "source": str((record.metadata or {}).get("source") or ""),
                "governance_status": _enum_value(record.governance_status),
                "signature": hashlib.sha1(signature_seed.encode("utf-8")).hexdigest(),
            }
        )
    return pd.DataFrame(rows)


def extract_deletion_candidates(
    df: pd.DataFrame,
    *,
    confidence_threshold: float = 0.35,
    min_age_days: float = 7.0,
) -> list[str]:
    if df.empty:
        return []

    candidate_ids: list[str] = []
    retired_mask = df["governance_status"].isin(
        {
            GovernanceStatus.ARCHIVED.value,
            GovernanceStatus.DEPRECATED.value,
            GovernanceStatus.HIDDEN.value,
        }
    ) & (df["age_days"] > 1.0 / 24.0)

    poor_mask = (
        (df["quality"] == ReflectionQuality.POOR.value)
        & (df["decayed_confidence"] < confidence_threshold)
        & (df["actionability"] < 0.25)
        & (df["age_days"] > min_age_days)
    )

    duplicate_mask = pd.Series([False] * len(df), index=df.index)
    maintenance_df = df[df["source"] == "memory_aware_maintenance"].sort_values("age_days", ascending=True)
    if not maintenance_df.empty:
        duplicate_mask.loc[maintenance_df.duplicated(subset=["signature"], keep="first").index] = maintenance_df.duplicated(
            subset=["signature"], keep="first"
        )
        duplicate_mask &= df["age_days"] > 1.0 / 24.0

    combined = retired_mask | poor_mask | duplicate_mask
    candidate_ids.extend([str(item) for item in df.loc[combined, "reflection_id"].tolist() if str(item)])
    return candidate_ids
