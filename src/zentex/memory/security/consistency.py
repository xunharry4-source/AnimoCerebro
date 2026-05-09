from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""
Cross-layer memory consistency checker.

职责:
  - 检测 semantic、procedural、episodic 三层记忆之间的内容矛盾。
  - 检测 profile 记忆与 collection 记忆之间的隐式冲突。
  - 定期输出一致性审计报告，供人工或 AI 复查。
  - 为矛盾记忆打标（contradiction_count 递增），驱动置信度更新。

不负责:
  - 语义层面的矛盾判断（依赖 LLM；本模块只做规则/启发式检测）。
  - 物理修改记忆内容（所有矛盾标记都通过 governance 状态流转实现）。
  - 触发 consolidation 流程（由调用方决定）。

设计原则:
  - Fail-Closed：检测失败时抛出异常，不返回假阴性。
  - 所有检测结果必须附 trace_id 和 reason，便于审计。
"""

import logging
import re
from datetime import datetime, timezone
UTC = timezone.utc
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Violation model
# ---------------------------------------------------------------------------

class ViolationType(str):
    PROFILE_SUPERSESSION_CONFLICT = "profile_supersession_conflict"
    TITLE_COLLISION = "title_collision"
    CROSS_LAYER_CONTRADICTION = "cross_layer_contradiction"
    CONFIDENCE_INCONSISTENCY = "confidence_inconsistency"
    TEMPORAL_INVERSION = "temporal_inversion"


class ConsistencyViolation(BaseModel):
    """Describes one detected inconsistency between two memory records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    violation_id: str = Field(default_factory=lambda: str(uuid4()))
    violation_type: str
    memory_id_a: str
    memory_id_b: str
    layer_a: str
    layer_b: str
    reason: str
    severity: str = Field(default="medium")  # "low" | "medium" | "high" | "critical"
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolution_hint: str = Field(default="")


class ConsistencyAuditReport(BaseModel):
    """Result of a full consistency check run."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    records_scanned: int = 0
    violations: list[ConsistencyViolation] = Field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "critical")

    def summary(self) -> str:
        return (
            f"Scanned {self.records_scanned} records; "
            f"{self.violation_count} violations "
            f"({self.critical_count} critical)"
        )


# ---------------------------------------------------------------------------
# Heuristic text comparison helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation for loose comparison."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def _title_overlap(title_a: str, title_b: str) -> float:
    """Return word-level Jaccard similarity between two titles."""
    words_a = set(_normalize(title_a).split())
    words_b = set(_normalize(title_b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(Union[words_a, words_b])


def _content_contradiction_heuristic(content_a: str, content_b: str) -> bool:
    """
    Very lightweight heuristic: detect obvious negation patterns.

    "X is Y" vs "X is not Y" or "X is Z".
    This is intentionally conservative — LLM-based contradiction detection
    should be used for high-confidence decisions.
    """
    a = _normalize(content_a)
    b = _normalize(content_b)
    # Simple check: same subject, one negates the other.
    negation_pairs = [
        ("is not", "is"),
        ("never", "always"),
        ("cannot", "can"),
        ("failed", "succeeded"),
        ("inactive", "active"),
        ("disabled", "enabled"),
    ]
    for neg, pos in negation_pairs:
        # Check if one has negation and the other has positive form
        # The key insight: if A has "is not X" and B has "is X", that's a contradiction
        if neg in a and pos in b:
            # Make sure it's not the same phrase (e.g., both have "is not")
            if neg not in b:
                return True
        if neg in b and pos in a:
            if neg not in a:
                return True
    return False


# ---------------------------------------------------------------------------
# Consistency checker
# ---------------------------------------------------------------------------

class CrossLayerConsistencyChecker:
    """
    Detects contradictions and inconsistencies across memory layers.

    Operates on lists of record dicts (not EnhancedMemoryRecord objects) so it
    can be used without importing the full memory stack.

    Expected dict keys per record:
      memory_id, memory_layer, source_kind, title, summary, content,
      memory_kind, content_hash, confidence_score (optional),
      created_at (ISO string), trust_level (optional)
    """

    def __init__(
        self,
        *,
        title_overlap_threshold: float = 0.8,
        enable_content_heuristics: bool = True,
    ) -> None:
        self._title_overlap_threshold = title_overlap_threshold
        self._enable_content_heuristics = enable_content_heuristics

    # ── public entry point ────────────────────────────────────────────────

    def check(
        self,
        records: list[dict],
        *,
        active_only: bool = True,
    ) -> ConsistencyAuditReport:
        """
        Run all consistency checks over the provided record list.

        Args:
            records: List of memory record dicts.
            active_only: If True, skip records with status != "active" / "trusted".

        Returns:
            ConsistencyAuditReport with all detected violations.
        """
        started = datetime.now(UTC)
        if active_only:
            records = [
                r for r in records
                if r.get("status", "active") not in ("deprecated", "archived", "rejected")
            ]

        violations: list[ConsistencyViolation] = []

        # Run all detectors.
        violations.extend(self._detect_profile_conflicts(records))
        violations.extend(self._detect_title_collisions(records))
        if self._enable_content_heuristics:
            violations.extend(self._detect_cross_layer_contradictions(records))
        violations.extend(self._detect_temporal_inversions(records))
        violations.extend(self._detect_confidence_inconsistencies(records))

        return ConsistencyAuditReport(
            started_at=started,
            records_scanned=len(records),
            violations=violations,
        )

    # ── detectors ────────────────────────────────────────────────────────

    def _detect_profile_conflicts(
        self, records: list[dict]
    ) -> list[ConsistencyViolation]:
        """
        Two active profile records with the same (memory_layer, title, source_kind)
        is a governance violation — the supersession mechanism should have deprecated one.
        """
        violations = []
        profile_index: dict[tuple, list[dict]] = {}
        for rec in records:
            if rec.get("memory_kind") != "profile":
                continue
            key = (rec.get("memory_layer", ""), rec.get("title", ""), rec.get("source_kind", ""))
            profile_index.setdefault(key, []).append(rec)

        for key, group in profile_index.items():
            if len(group) < 2:
                continue
            # Sort by created_at; newest should be the one that's active.
            group_sorted = sorted(group, key=lambda r: r.get("created_at", ""), reverse=True)
            for older in group_sorted[1:]:
                violations.append(ConsistencyViolation(
                    violation_type=ViolationType.PROFILE_SUPERSESSION_CONFLICT,
                    memory_id_a=group_sorted[0].get("memory_id", ""),
                    memory_id_b=older.get("memory_id", ""),
                    layer_a=str(key[0]),
                    layer_b=str(key[0]),
                    reason=(
                        f"Two active profile records share key {key}. "
                        f"Older record {older.get('memory_id')} should have been deprecated."
                    ),
                    severity="high",
                    resolution_hint="Deprecate the older profile via update_management_state().",
                ))
        return violations

    def _detect_title_collisions(
        self, records: list[dict]
    ) -> list[ConsistencyViolation]:
        """
        Two collection records in the same layer with near-identical titles but
        different content_hashes may be unintentional duplicates.
        """
        violations = []
        collection_records = [r for r in records if r.get("memory_kind", "collection") == "collection"]

        for i, a in enumerate(collection_records):
            for b in collection_records[i + 1:]:
                if a.get("memory_layer") != b.get("memory_layer"):
                    continue
                if a.get("content_hash") == b.get("content_hash"):
                    continue  # True duplicates handled by dedup, not a violation.
                overlap = _title_overlap(str(a.get("title", "")), str(b.get("title", "")))
                if overlap >= self._title_overlap_threshold:
                    violations.append(ConsistencyViolation(
                        violation_type=ViolationType.TITLE_COLLISION,
                        memory_id_a=a.get("memory_id", ""),
                        memory_id_b=b.get("memory_id", ""),
                        layer_a=str(a.get("memory_layer", "")),
                        layer_b=str(b.get("memory_layer", "")),
                        reason=(
                            f"Near-duplicate titles (overlap={overlap:.2f}): "
                            f"'{a.get('title')}' vs '{b.get('title')}'"
                        ),
                        severity="medium",
                        resolution_hint="Consider merging or deprecating the older record.",
                    ))
        return violations

    def _detect_cross_layer_contradictions(
        self, records: list[dict]
    ) -> list[ConsistencyViolation]:
        """
        Check for semantic-procedural or semantic-episodic contradictions using
        the lightweight negation heuristic.
        """
        violations = []
        layer_groups: dict[str, list[dict]] = {}
        for rec in records:
            layer_groups.setdefault(str(rec.get("memory_layer", "")), []).append(rec)

        layers = list(layer_groups.keys())
        for i, layer_a in enumerate(layers):
            for layer_b in layers[i + 1:]:
                for a in layer_groups[layer_a]:
                    for b in layer_groups[layer_b]:
                        if _content_contradiction_heuristic(
                            str(a.get("content", "")),
                            str(b.get("content", "")),
                        ):
                            violations.append(ConsistencyViolation(
                                violation_type=ViolationType.CROSS_LAYER_CONTRADICTION,
                                memory_id_a=a.get("memory_id", ""),
                                memory_id_b=b.get("memory_id", ""),
                                layer_a=layer_a,
                                layer_b=layer_b,
                                reason=(
                                    f"Heuristic contradiction detected between "
                                    f"'{a.get('title')}' ({layer_a}) and "
                                    f"'{b.get('title')}' ({layer_b})."
                                ),
                                severity="medium",
                                resolution_hint=(
                                    "Verify with LLM-based comparison; deprecate the outdated record."
                                ),
                            ))
        return violations

    def _detect_temporal_inversions(
        self, records: list[dict]
    ) -> list[ConsistencyViolation]:
        """
        An episodic record whose event_time is AFTER its ingest_time is suspect
        (could indicate clock skew or manual data injection).
        """
        violations = []
        for rec in records:
            event_time_raw = rec.get("event_time")
            ingest_time_raw = rec.get("created_at")
            if not event_time_raw or not ingest_time_raw:
                continue
            try:
                event_time = datetime.fromisoformat(str(event_time_raw))
                ingest_time = datetime.fromisoformat(str(ingest_time_raw))
                # Normalise to UTC
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=UTC)
                if ingest_time.tzinfo is None:
                    ingest_time = ingest_time.replace(tzinfo=UTC)
                # Allow up to 1 second clock skew.
                if (event_time - ingest_time).total_seconds() > 1:
                    violations.append(ConsistencyViolation(
                        violation_type=ViolationType.TEMPORAL_INVERSION,
                        memory_id_a=rec.get("memory_id", ""),
                        memory_id_b="",
                        layer_a=str(rec.get("memory_layer", "")),
                        layer_b="",
                        reason=(
                            f"event_time ({event_time.isoformat()}) "
                            f"is after ingest_time ({ingest_time.isoformat()}) "
                            f"by {(event_time - ingest_time).total_seconds():.0f}s."
                        ),
                        severity="low",
                        resolution_hint="Check source clock; may be intentional back-dating.",
                    ))
            except (ValueError, TypeError):
                pass
        return violations

    def _detect_confidence_inconsistencies(
        self, records: list[dict]
    ) -> list[ConsistencyViolation]:
        """
        A 'verified' record with confidence_score < 0.5 is inconsistent.
        A 'disputed' record with confidence_score > 0.8 is inconsistent.
        """
        violations = []
        for rec in records:
            vs = rec.get("verification_status", "unverified")
            cs = float(rec.get("confidence_score", 0.5))
            mid = rec.get("memory_id", "")
            layer = str(rec.get("memory_layer", ""))

            if vs == "verified" and cs < 0.5:
                violations.append(ConsistencyViolation(
                    violation_type=ViolationType.CONFIDENCE_INCONSISTENCY,
                    memory_id_a=mid, memory_id_b="",
                    layer_a=layer, layer_b="",
                    reason=f"Record is 'verified' but confidence_score={cs:.2f} < 0.5.",
                    severity="medium",
                    resolution_hint="Update confidence_score or re-verify the record.",
                ))
            elif vs == "disputed" and cs > 0.8:
                violations.append(ConsistencyViolation(
                    violation_type=ViolationType.CONFIDENCE_INCONSISTENCY,
                    memory_id_a=mid, memory_id_b="",
                    layer_a=layer, layer_b="",
                    reason=f"Record is 'disputed' but confidence_score={cs:.2f} > 0.8.",
                    severity="medium",
                    resolution_hint="Resolve dispute or lower confidence_score.",
                ))
        return violations
