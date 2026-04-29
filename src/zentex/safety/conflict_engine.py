from __future__ import annotations

"""Feature 56 CognitiveConflictEngine.

Lightweight deterministic conflict detection for ThinkLoop Phase 4. The engine
does not call an LLM and does not execute external actions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

UTC = timezone.utc
Severity = Literal["low", "medium", "high", "critical"]


class StaleWriteError(RuntimeError):
    """Raised when a reconciliation plan targets an outdated snapshot version."""


class ConflictSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: str = Field(default="unknown", min_length=1)
    source_ref: str = ""
    conflict_note: str = ""
    # Compatibility with older callers.
    source_type: str = ""
    reference_id: str = ""

    @model_validator(mode="after")
    def _sync_legacy_fields(self) -> "ConflictSource":
        if not self.source_type:
            self.source_type = self.source_kind
        if not self.reference_id:
            self.reference_id = self.source_ref
        if not self.source_ref:
            self.source_ref = self.reference_id
        if not self.source_kind:
            self.source_kind = self.source_type
        return self


class ReconciliationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    report_id: str = ""
    conflict_ids: List[str] = Field(default_factory=list)
    resolution_type: str = "revisit"
    resolution_actions: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    blocking: bool = False
    status: Literal["proposed", "applied", "discarded"] = "proposed"
    brain_scope: str = Field(default="zentex.runtime", min_length=1)
    snapshot_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _sync_actions(self) -> "ReconciliationPlan":
        if not self.conflict_ids and self.report_id:
            self.conflict_ids = [self.report_id]
        if not self.report_id and self.conflict_ids:
            self.report_id = self.conflict_ids[0]
        if not self.steps and self.resolution_actions:
            self.steps = list(self.resolution_actions)
        if not self.resolution_actions and self.steps:
            self.resolution_actions = list(self.steps)
        if not self.resolution_actions:
            self.resolution_actions = [_resolution_action(self.resolution_type)]
            self.steps = list(self.resolution_actions)
        return self


class SelfCorrectionTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    report_id: str = ""
    conflict_id: str = ""
    trigger_reason: str = ""
    recommended_phase: str = "metacognition"
    must_pause_current_path: bool = False
    # Compatibility with older callers.
    action: str = "pause_and_evaluate"
    priority: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _sync_fields(self) -> "SelfCorrectionTrigger":
        if not self.conflict_id and self.report_id:
            self.conflict_id = self.report_id
        if not self.report_id and self.conflict_id:
            self.report_id = self.conflict_id
        if not self.trigger_reason:
            self.trigger_reason = self.action
        if self.priority <= 0:
            self.priority = 3 if self.must_pause_current_path else 1
        return self


class CognitiveConflictReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_id: str = ""
    conflict_type: str = Field(min_length=1)
    severity: Severity
    summary: str = ""
    source_refs: List[str] = Field(default_factory=list)
    conflict_sources: List[ConflictSource] = Field(default_factory=list)
    suggested_resolution: str = Field(min_length=1)
    reconciliation_plan: Optional[ReconciliationPlan] = None
    source_plugin_id: str = Field(default="core.cognitive_conflict_engine", min_length=1)
    status: Literal["unresolved", "reconciling", "resolved"] = "unresolved"
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _sync_fields(self) -> "CognitiveConflictReport":
        if not self.conflict_id:
            self.conflict_id = self.report_id
        if not self.report_id:
            self.report_id = self.conflict_id
        if not self.summary:
            self.summary = f"{self.conflict_type} conflict detected"
        if not self.source_refs and self.conflict_sources:
            self.source_refs = [item.source_ref or item.reference_id for item in self.conflict_sources if item.source_ref or item.reference_id]
        if not self.conflict_sources and self.source_refs:
            self.conflict_sources = [
                ConflictSource(source_kind="unknown", source_ref=source_ref, conflict_note=self.summary)
                for source_ref in self.source_refs
            ]
        if self.reconciliation_plan is None:
            self.reconciliation_plan = ReconciliationPlan(
                report_id=self.report_id,
                conflict_ids=[self.conflict_id],
                resolution_type=_resolution_type(self.suggested_resolution),
                steps=[_resolution_action(self.suggested_resolution)],
                blocking=self.severity in {"high", "critical"},
            )
        return self


class ConflictSharedState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_scope: str
    snapshot_version: int = 0
    unresolved_conflicts: List[CognitiveConflictReport] = Field(default_factory=list)
    applied_plan_ids: List[str] = Field(default_factory=list)


class CognitiveConflictEngine:
    """Deterministic conflict aggregation and optimistic reconciliation control."""

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
                    key=lambda report: (self._severity_rank(report.severity), report.detected_at),
                    reverse=True,
                ),
            }
        )
        return self._shared_state.unresolved_conflicts

    def list_unresolved_conflicts(self) -> List[CognitiveConflictReport]:
        return list(self._shared_state.unresolved_conflicts)

    def detect(
        self,
        working_memory: Any,
        goals: Any = None,
        nine_q_state: Any = None,
        memory_recalls: Any = None,
        budget: Any = None,
        *,
        self_model: Any = None,
        agenda: Any = None,
    ) -> List[CognitiveConflictReport]:
        """Scan for goal, evidence, memory, budget, boundary, and confidence conflicts."""
        wm = _as_dict(working_memory)
        goals_list = _as_list(goals if goals is not None and not _looks_like_self_model(goals) else wm.get("goals"))
        if self_model is None and _looks_like_self_model(goals):
            self_model = goals
        nq = _as_dict(nine_q_state)
        recalls = _as_list(memory_recalls if memory_recalls is not None else wm.get("memory_recalls"))
        budget_dict = _as_dict(budget if budget is not None else wm.get("budget"))
        self_model_dict = _as_dict(self_model)
        agenda_items = _as_list(agenda if agenda is not None else wm.get("agenda"))

        detected: List[CognitiveConflictReport] = []
        detected.extend(self._detect_goal_conflicts(goals_list))
        detected.extend(self._detect_evidence_conflicts(wm))
        detected.extend(self._detect_memory_conflicts(recalls))
        detected.extend(self._detect_confidence_conflicts(self_model_dict))
        detected.extend(self._detect_budget_conflicts(budget_dict, agenda_items))
        detected.extend(self._detect_boundary_conflicts(nq))

        if detected:
            self.ingest_reports(detected)
        return detected

    def generate_triggers(
        self,
        reports: Optional[List[CognitiveConflictReport]] = None,
    ) -> List[SelfCorrectionTrigger]:
        source_reports = reports if reports is not None else self._shared_state.unresolved_conflicts
        triggers: List[SelfCorrectionTrigger] = []
        for conflict in source_reports:
            rank = self._severity_rank(conflict.severity)
            triggers.append(
                SelfCorrectionTrigger(
                    report_id=conflict.report_id,
                    conflict_id=conflict.conflict_id,
                    trigger_reason=f"{conflict.conflict_type}:{conflict.suggested_resolution}",
                    recommended_phase="metacognition",
                    must_pause_current_path=conflict.severity in {"high", "critical"},
                    action="pause_and_evaluate" if conflict.severity in {"high", "critical"} else "review",
                    priority=rank,
                )
            )
        return triggers

    def detect_cognitive_risks_phase4(self, signals: Any) -> List[CognitiveConflictReport]:
        if not isinstance(signals, dict):
            return []
        return self.detect(
            working_memory=signals.get("working_memory") or signals,
            goals=signals.get("goals"),
            nine_q_state=signals.get("nine_q_state") or signals.get("nine_question_state"),
            memory_recalls=signals.get("memory_recalls"),
            budget=signals.get("budget") or signals.get("reasoning_budget"),
            self_model=signals.get("self_model") or signals.get("living_self_model"),
            agenda=signals.get("agenda") or signals.get("cognitive_agenda"),
        )

    def consume_triggers_b7(self, metacognition_controller: Any) -> None:
        triggers = self.generate_triggers()
        if hasattr(metacognition_controller, "receive_triggers"):
            metacognition_controller.receive_triggers(triggers)

    def build_reconciliation_plan(self, conflict_ids: List[str]) -> ReconciliationPlan:
        return ReconciliationPlan(
            conflict_ids=conflict_ids,
            report_id=conflict_ids[0] if conflict_ids else "",
            resolution_type="revisit",
            resolution_actions=["pause_expansion_reasoning", "prefer_conservative_branch"],
            steps=["pause_expansion_reasoning", "prefer_conservative_branch"],
            blocking=True,
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
            if report.conflict_id in set(plan.conflict_ids) or report.report_id in set(plan.conflict_ids)
            else report
            for report in self._shared_state.unresolved_conflicts
        ]
        self._shared_state = self._shared_state.model_copy(
            update={
                "snapshot_version": self.snapshot_version + 1,
                "unresolved_conflicts": [report for report in unresolved if report.status != "resolved"],
                "applied_plan_ids": [*self._shared_state.applied_plan_ids, plan.plan_id],
            }
        )
        return self._shared_state

    def snapshot(self) -> ConflictSharedState:
        return self._shared_state

    def _detect_goal_conflicts(self, goals: list[dict[str, Any]]) -> list[CognitiveConflictReport]:
        reports: list[CognitiveConflictReport] = []
        by_id = {str(goal.get("goal_id") or goal.get("id") or idx): goal for idx, goal in enumerate(goals)}
        for goal_id, goal in by_id.items():
            for conflict_ref in _as_list(goal.get("conflicts_with")):
                if str(conflict_ref) in by_id:
                    reports.append(
                        _report(
                            conflict_type="goal_conflict",
                            severity="high",
                            suggested_resolution="revisit_goals",
                            summary=f"Goal {goal_id} conflicts with {conflict_ref}",
                            sources=[
                                ConflictSource(source_kind="goal", source_ref=goal_id, conflict_note="declares conflicts_with"),
                                ConflictSource(source_kind="goal", source_ref=str(conflict_ref), conflict_note="referenced conflicting goal"),
                            ],
                        )
                    )
        return reports

    def _detect_evidence_conflicts(self, working_memory: dict[str, Any]) -> list[CognitiveConflictReport]:
        items = _as_list(working_memory.get("active_items") or working_memory.get("items") or working_memory.get("evidence_items"))
        grouped: dict[str, dict[str, Any]] = {}
        for item in items:
            key = str(item.get("claim_key") or item.get("statement_id") or "")
            polarity = str(item.get("polarity") or item.get("stance") or "").lower()
            if not key or polarity not in {"supports", "support", "true", "opposes", "oppose", "false", "contradicts"}:
                continue
            bucket = grouped.setdefault(key, {"positive": [], "negative": []})
            target = "positive" if polarity in {"supports", "support", "true"} else "negative"
            bucket[target].append(item)
        reports: list[CognitiveConflictReport] = []
        for key, bucket in grouped.items():
            if bucket["positive"] and bucket["negative"]:
                refs = [_item_ref(item) for item in bucket["positive"] + bucket["negative"]]
                reports.append(
                    _report(
                        conflict_type="evidence_conflict",
                        severity="medium",
                        suggested_resolution="review_evidence",
                        summary=f"Evidence for {key} contains supporting and opposing claims",
                        sources=[ConflictSource(source_kind="evidence", source_ref=ref, conflict_note=key) for ref in refs],
                    )
                )
        return reports

    def _detect_memory_conflicts(self, recalls: list[dict[str, Any]]) -> list[CognitiveConflictReport]:
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for recall in recalls:
            key = str(recall.get("memory_key") or recall.get("claim_key") or "")
            conclusion = str(recall.get("conclusion") or recall.get("polarity") or "").lower()
            if not key or conclusion not in {"true", "false", "supports", "opposes"}:
                continue
            target = "positive" if conclusion in {"true", "supports"} else "negative"
            grouped.setdefault(key, {"positive": [], "negative": []})[target].append(recall)
        reports: list[CognitiveConflictReport] = []
        for key, bucket in grouped.items():
            if bucket["positive"] and bucket["negative"]:
                refs = [_item_ref(item) for item in bucket["positive"] + bucket["negative"]]
                reports.append(
                    _report(
                        conflict_type="memory_conflict",
                        severity="high",
                        suggested_resolution="reconcile_memory",
                        summary=f"Memory recalls for {key} disagree",
                        sources=[ConflictSource(source_kind="memory", source_ref=ref, conflict_note=key) for ref in refs],
                    )
                )
        return reports

    def _detect_confidence_conflicts(self, self_model: dict[str, Any]) -> list[CognitiveConflictReport]:
        living = self_model.get("living_self_model") if isinstance(self_model.get("living_self_model"), dict) else self_model
        indicators = _as_list(living.get("confidence_drift_indicators"))
        reports: list[CognitiveConflictReport] = []
        for indicator in indicators:
            if bool(indicator.get("triggered_alert")):
                refs = _as_list(indicator.get("evidence_refs")) or [str(indicator.get("indicator_id") or "confidence_drift")]
                reports.append(
                    _report(
                        conflict_type="confidence_conflict",
                        severity="high",
                        suggested_resolution="downgrade_confidence",
                        summary="Statement confidence exceeds evidence support",
                        sources=[ConflictSource(source_kind="self_model", source_ref=str(ref), conflict_note="confidence drift") for ref in refs],
                    )
                )
        return reports

    def _detect_budget_conflicts(
        self,
        budget: dict[str, Any],
        agenda_items: list[dict[str, Any]],
    ) -> list[CognitiveConflictReport]:
        if not budget:
            return []
        remaining_ratio = _remaining_ratio(budget)
        planned_count = int(budget.get("planned_steps") or budget.get("planned_tool_count") or len(agenda_items) or 0)
        if remaining_ratio < 0.2 and planned_count >= 3:
            return [
                _report(
                    conflict_type="budget_conflict",
                    severity="medium",
                    suggested_resolution="downgrade_reasoning_depth",
                    summary="Reasoning budget is too low for the planned work",
                    sources=[
                        ConflictSource(
                            source_kind="budget",
                            source_ref=str(budget.get("budget_id") or "reasoning_budget"),
                            conflict_note=f"remaining_ratio={remaining_ratio}",
                        )
                    ],
                )
            ]
        return []

    def _detect_boundary_conflicts(self, nine_q_state: dict[str, Any]) -> list[CognitiveConflictReport]:
        violations = _as_list(nine_q_state.get("boundary_violations") or nine_q_state.get("constraint_violations"))
        if not violations:
            return []
        return [
            _report(
                conflict_type="boundary_conflict",
                severity="critical",
                suggested_resolution="request_help",
                summary="Nine-question boundary violation is present",
                sources=[
                    ConflictSource(source_kind="nine_q_state", source_ref=str(item), conflict_note="boundary violation")
                    for item in violations
                ],
            )
        ]

    def _severity_rank(self, severity: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity, 1)


def _report(
    *,
    conflict_type: str,
    severity: Severity,
    suggested_resolution: str,
    summary: str,
    sources: list[ConflictSource],
) -> CognitiveConflictReport:
    return CognitiveConflictReport(
        conflict_type=conflict_type,
        severity=severity,
        suggested_resolution=suggested_resolution,
        summary=summary,
        source_refs=[source.source_ref for source in sources],
        conflict_sources=sources,
        source_plugin_id="core.cognitive_conflict_engine",
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return getattr(value, "__dict__", {}) if hasattr(value, "__dict__") else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _item_ref(item: dict[str, Any]) -> str:
    return str(item.get("source_ref") or item.get("memory_id") or item.get("item_id") or item.get("id") or uuid4())


def _looks_like_self_model(value: Any) -> bool:
    data = _as_dict(value)
    return bool(
        "living_self_model" in data
        or "confidence_drift_indicators" in data
        or "recent_weaknesses" in data
    )


def _remaining_ratio(budget: dict[str, Any]) -> float:
    if budget.get("remaining_ratio") is not None:
        return _clamp01(float(budget["remaining_ratio"]))
    remaining = float(budget.get("remaining") or budget.get("remaining_tokens") or budget.get("remaining_steps") or 0.0)
    total = float(budget.get("total") or budget.get("total_tokens") or budget.get("max_steps") or 0.0)
    if total <= 0:
        return 1.0
    return _clamp01(remaining / total)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _resolution_type(resolution: str) -> str:
    lowered = resolution.lower()
    if "confidence" in lowered:
        return "lower_confidence"
    if "memory" in lowered:
        return "reconcile_memory"
    if "goal" in lowered:
        return "revisit"
    if "help" in lowered:
        return "request_help"
    if "budget" in lowered or "depth" in lowered:
        return "prune"
    return "clarify"


def _resolution_action(resolution: str) -> str:
    mapping = {
        "lower_confidence": "downgrade_confidence_before_answer",
        "reconcile_memory": "compare_memory_sources_before_continuing",
        "revisit": "revisit_conflicting_goal_or_assumption",
        "request_help": "pause_and_request_supervisory_review",
        "prune": "trim_plan_to_budget_before_tool_execution",
        "clarify": "ask_for_or_collect_clarifying_evidence",
    }
    return mapping.get(_resolution_type(resolution), "review_conflict_before_continuing")
