from __future__ import annotations
"""
Temporal Engine
----------------
Provides a lightweight snapshot‑at‑time view over memory records.
It is used by the HybridRetrievalEngine when a query is classified as
`QueryType.TEMPORAL` and an `as_of_time` is supplied.
"""


import logging
from datetime import datetime, timezone
from typing import Iterable, List, Dict, Any

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Simple result model compatible with HybridRetrievalEngine expectations
# ---------------------------------------------------------------------------

class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    score: float = 1.0
    source: str = "temporal"
    memory_layer: str = ""
    source_kind: str = ""
    title: str = ""
    summary: str = ""
    trace_id: str = ""
    tags: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    explanation: str = ""

# ---------------------------------------------------------------------------
# Engine implementation
# ---------------------------------------------------------------------------

class TemporalEngine:
    """Builds an in‑memory index of records keyed by creation timestamp.

    The engine is deliberately simple – it stores the full record dicts and
    filters them on demand. This satisfies the requirement of sub‑millisecond
    query latency for the typical < 100 K record workloads.
    """

    def __init__(self, records: Iterable[dict]) -> None:
        # Store records sorted by creation time for efficient slicing
        self._records: List[dict] = sorted(
            records,
            key=lambda r: self._parse_ts(r.get("created_at")),
        )

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
        except Exception:
            # POLICY[no-silent-except]: log unparseable timestamp; fall back to now().
            logger.debug("Could not parse timestamp value %r — using current time", value, exc_info=True)
            return datetime.now(timezone.utc)

    def snapshot_at(self, as_of: datetime, limit: int = 10) -> List[RetrievalResult]:
        """Return up to ``limit`` records that existed at ``as_of``.

        Records with ``created_at`` <= ``as_of`` are considered present. The
        result list is ordered by most‑recent creation time (descending).
        """
        as_of = self._parse_ts(as_of)
        # Find the cutoff index using binary search for efficiency
        lo, hi = 0, len(self._records)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._records[mid]["created_at"] <= as_of:
                lo = mid + 1
            else:
                hi = mid
        # ``lo`` is the count of records with created_at <= as_of
        eligible = self._records[:lo]
        # Return most recent ``limit`` entries (reverse order)
        selected = list(reversed(eligible))[:limit]
        results: List[RetrievalResult] = []
        for rec in selected:
            results.append(
                RetrievalResult(
                    memory_id=str(rec.get("memory_id", "")),
                    score=1.0,
                    source="temporal",
                    memory_layer=str(rec.get("memory_layer", "")),
                    source_kind=str(rec.get("source_kind", "")),
                    title=str(rec.get("title", "")),
                    summary=str(rec.get("summary", "")),
                    trace_id=str(rec.get("trace_id", "")),
                    tags=list(rec.get("tags", [])),
                    source_refs=list(rec.get("source_refs", [])),
                    explanation=f"Snapshot as of {as_of.isoformat()}",
                )
            )
        return results

# ---------------------------------------------------------------------------
# Builder helper used by the retrieval router
# ---------------------------------------------------------------------------

def build_temporal_engine(service: Any) -> TemporalEngine:
    """Create a TemporalEngine from an ``EnhancedMemoryService``.

    The service is expected to provide ``list_all_records()`` returning an
    iterable of dict‑like memory records.
    """
    records = service.list_all_records()
    return TemporalEngine(records)
