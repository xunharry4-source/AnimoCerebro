from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StaleWriteError(RuntimeError):
    """Raised when a reconciliation plan targets an outdated snapshot version."""


class ConflictSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str = Field(min_length=1)
    reference_id: str


class SelfCorrectionTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_id: str
    action: str
    priority: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CognitiveConflictReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_type: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    suggested_resolution: str = Field(min_length=1)
    source_plugin_id: str = Field(min_length=1)
    status: Literal["unresolved", "reconciling", "resolved"] = "unresolved"
    details: Dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReconciliationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_ids: List[str] = Field(default_factory=list)
    resolution_actions: List[str] = Field(default_factory=list)
    status: Literal["proposed", "applied", "discarded"] = "proposed"
    brain_scope: str = Field(min_length=1)
    snapshot_version: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConflictSharedState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_scope: str
    snapshot_version: int = 0
    unresolved_conflicts: List[CognitiveConflictReport] = Field(default_factory=list)
    applied_plan_ids: List[str] = Field(default_factory=list)


class CognitiveConflictEngine:
    """
    Deterministic conflict aggregation and optimistic reconciliation control.

    Hard redline:
    - this engine coordinates cognitive state only
    - it does not call execution adapters or external notification channels
    """

    def __init__(
        self,
        *,
        brain_scope: str = "zentex.runtime",
        shared_state: Optional[ConflictSharedState] = None,
    ) -> None:
        self._shared_state = shared_state or ConflictSharedState(brain_scope=brain_scope)

    @property
    def brain_scope(self) -> str:
        return self._shared_state.brain_scope

    @property
    def snapshot_version(self) -> int:
        return self._shared_state.snapshot_version

    def ingest_reports(self, reports: List[CognitiveConflictReport]) -> List[CognitiveConflictReport]:
        merged: Dict[str, CognitiveConflictReport] = {
            report.conflict_id: report for report in self._shared_state.unresolved_conflicts
        }
        for report in reports:
            if report.status == "resolved":
                continue
            merged[report.conflict_id] = report
        self._shared_state = self._shared_state.model_copy(
            update={
                "unresolved_conflicts": sorted(
                    merged.values(),
                    key=lambda report: (
                        self._severity_rank(report.severity),
                        report.detected_at,
                    ),
                    reverse=True,
                ),
            }
        )
        return self._shared_state.unresolved_conflicts

    def list_unresolved_conflicts(self) -> List[CognitiveConflictReport]:
        return list(self._shared_state.unresolved_conflicts)

    def detect(self, working_memory: Any, self_model: Any, agenda: Any) -> List[CognitiveConflictReport]:
        """
        Scan for Goal, Evidence, Memory, Budget, and Confidence conflicts.
        """
        detected: List[CognitiveConflictReport] = []
        
        wm_dict = working_memory if isinstance(working_memory, dict) else getattr(working_memory, "__dict__", {})
        sm_dict = self_model if isinstance(self_model, dict) else getattr(self_model, "__dict__", {})
        
        # Confidence conflict via ConfidenceDriftIndicator
        weaknesses = sm_dict.get("recent_weaknesses", [])
        if isinstance(weaknesses, list) and any(getattr(w, "pattern_type", "") == "overconfidence" or (isinstance(w, dict) and w.get("pattern_type") == "overconfidence") for w in weaknesses):
            detected.append(
                CognitiveConflictReport(
                    conflict_type="confidence",
                    severity="high",
                    suggested_resolution="downgrade_confidence",
                    source_plugin_id="core.self_model",
                )
            )
            
        # Basic structural evaluation hooks
        if wm_dict.get("goal_conflict"):
            detected.append(CognitiveConflictReport(conflict_type="goal", severity="high", suggested_resolution="reconcile_goals", source_plugin_id="core.working_memory"))
        if wm_dict.get("evidence_conflict"):
            detected.append(CognitiveConflictReport(conflict_type="evidence", severity="medium", suggested_resolution="review_evidence", source_plugin_id="core.working_memory"))
        if wm_dict.get("memory_conflict"):
            detected.append(CognitiveConflictReport(conflict_type="memory", severity="high", suggested_resolution="reconcile_memory", source_plugin_id="core.working_memory"))
        if wm_dict.get("budget_conflict"):
            detected.append(CognitiveConflictReport(conflict_type="budget", severity="medium", suggested_resolution="downgrade_reasoning_depth", source_plugin_id="core.metacognition"))
            
        if detected:
            self.ingest_reports(detected)
            
        return detected

    def generate_triggers(self) -> List[SelfCorrectionTrigger]:
        """
        Create SelfCorrectionTrigger objects from unresolved conflicts.
        Consumed by B7 MetaCognitionController.
        """
        triggers = []
        for conflict in self._shared_state.unresolved_conflicts:
            triggers.append(
                SelfCorrectionTrigger(
                    conflict_id=conflict.conflict_id,
                    action="pause_and_evaluate",
                    priority=self._severity_rank(conflict.severity)
                )
            )
        return triggers

    def detect_cognitive_risks_phase4(self, signals: Any) -> List[CognitiveConflictReport]:
        """Integration boundary for ThinkLoop Phase 4."""
        return self.detect(
            signals.get("working_memory"),
            signals.get("self_model"),
            signals.get("agenda")
        ) if isinstance(signals, dict) else []

    def consume_triggers_b7(self, metacognition_controller: Any) -> None:
        """Integration boundary for B7 MetaCognitionController."""
        triggers = self.generate_triggers()
        if hasattr(metacognition_controller, "receive_triggers"):
            metacognition_controller.receive_triggers(triggers)

    def build_reconciliation_plan(self, conflict_ids: List[str]) -> ReconciliationPlan:
        return ReconciliationPlan(
            conflict_ids=conflict_ids,
            resolution_actions=["pause_expansion_reasoning", "prefer_conservative_branch"],
            brain_scope=self.brain_scope,
            snapshot_version=self.snapshot_version,
        )

    def apply_reconciliation_plan(self, plan: ReconciliationPlan) -> ConflictSharedState:
        if plan.brain_scope != self.brain_scope:
            raise StaleWriteError(
                f"Reconciliation plan scope mismatch: expected {self.brain_scope}, got {plan.brain_scope}"
            )
        if plan.snapshot_version != self.snapshot_version:
            raise StaleWriteError(
                f"Stale reconciliation plan: expected snapshot_version {self.snapshot_version}, got {plan.snapshot_version}"
            )

        unresolved = [
            report.model_copy(update={"status": "resolved"})
            if report.conflict_id in set(plan.conflict_ids)
            else report
            for report in self._shared_state.unresolved_conflicts
        ]
        self._shared_state = self._shared_state.model_copy(
            update={
                "snapshot_version": self.snapshot_version + 1,
                "unresolved_conflicts": [
                    report for report in unresolved if report.status != "resolved"
                ],
                "applied_plan_ids": [*self._shared_state.applied_plan_ids, plan.plan_id],
            }
        )
        return self._shared_state

    def snapshot(self) -> ConflictSharedState:
        return self._shared_state

    def _severity_rank(self, severity: str) -> int:
        ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return ranks.get(severity, 0)
