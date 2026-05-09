from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.learning.directions import LearningDirection


RiskLevel = Literal["low", "medium", "high", "critical"]


class CuriosityTaskStatus(str, Enum):
    PLANNED = "planned"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class EpistemicUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uncertainty_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    knowledge_gap_score: float = Field(ge=0.0, le=1.0)
    expected_learning_value: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: RiskLevel = "low"
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_compute_units: float = Field(default=0.0, ge=0.0)
    evidence_refs: list[str] = Field(default_factory=list)
    source: str = Field(default="world_model", min_length=1)


class CuriosityBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remaining_tokens: int = Field(ge=0)
    remaining_compute_units: float = Field(ge=0.0)
    max_tokens_per_task: int = Field(default=2000, ge=0)
    max_compute_units_per_task: float = Field(default=1.0, ge=0.0)


class BudgetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    status: Literal["approved", "blocked"]
    reason: str = Field(min_length=1)
    remaining_tokens: int = Field(ge=0)
    remaining_compute_units: float = Field(ge=0.0)
    estimated_tokens: int = Field(ge=0)
    estimated_compute_units: float = Field(ge=0.0)


class CuriosityTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    exploration_goal: str = Field(min_length=1)
    target_topics: list[str] = Field(min_length=1)
    uncertainty_ids: list[str] = Field(min_length=1)
    priority_score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    trigger_source: Literal["idle_heartbeat", "manual_cycle"]
    learning_direction: str = LearningDirection.CURIOSITY.value
    budget_decision: BudgetDecision
    status: CuriosityTaskStatus
    blocked_reason: str | None = None
    memory_id: str | None = None
    result_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExplorationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(min_length=1)
    findings: str = Field(min_length=1)
    confidence_delta: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    reusable_for_decisions: bool = True
    memory_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CuriosityCycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(default_factory=lambda: str(uuid4()))
    active_external_task_count: int = Field(ge=0)
    trigger_source: Literal["idle_heartbeat", "manual_cycle"]
    status: Literal["idle_not_available", "no_uncertainty", "tasks_generated"]
    reason: str = Field(min_length=1)
    uncertainties: list[EpistemicUncertainty] = Field(default_factory=list)
    generated_tasks: list[CuriosityTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CuriosityEngine:
    def __init__(self) -> None:
        self._uncertainties: dict[str, EpistemicUncertainty] = {}
        self._tasks: dict[str, CuriosityTask] = {}
        self._results: dict[str, ExplorationResult] = {}

    def run_idle_cycle(
        self,
        *,
        uncertainties: list[EpistemicUncertainty],
        budget: CuriosityBudget,
        active_external_task_count: int,
        trigger_source: Literal["idle_heartbeat", "manual_cycle"] = "idle_heartbeat",
    ) -> CuriosityCycleReport:
        if active_external_task_count < 0:
            raise ValueError("active_external_task_count cannot be negative")
        for uncertainty in uncertainties:
            self._uncertainties[uncertainty.uncertainty_id] = uncertainty

        if active_external_task_count > 0:
            return CuriosityCycleReport(
                active_external_task_count=active_external_task_count,
                trigger_source=trigger_source,
                status="idle_not_available",
                reason="external_task_active",
                uncertainties=uncertainties,
                generated_tasks=[],
            )
        ranked = self._rank_uncertainties(uncertainties)
        if not ranked:
            return CuriosityCycleReport(
                active_external_task_count=0,
                trigger_source=trigger_source,
                status="no_uncertainty",
                reason="no_uncertainty_above_trigger_threshold",
                uncertainties=uncertainties,
                generated_tasks=[],
            )

        generated: list[CuriosityTask] = []
        available_tokens = budget.remaining_tokens
        available_compute_units = budget.remaining_compute_units
        for uncertainty in ranked:
            task_budget = budget.model_copy(
                update={
                    "remaining_tokens": available_tokens,
                    "remaining_compute_units": available_compute_units,
                }
            )
            task = self._build_task(uncertainty=uncertainty, budget=task_budget, trigger_source=trigger_source)
            generated.append(task)
            if task.budget_decision.approved:
                available_tokens = max(0, available_tokens - uncertainty.estimated_tokens)
                available_compute_units = max(0.0, available_compute_units - uncertainty.estimated_compute_units)
        for task in generated:
            self._tasks[task.task_id] = task
        return CuriosityCycleReport(
            active_external_task_count=0,
            trigger_source=trigger_source,
            status="tasks_generated",
            reason="curiosity_drive_triggered_by_idle_uncertainty",
            uncertainties=uncertainties,
            generated_tasks=generated,
        )

    def complete_task(
        self,
        *,
        task_id: str,
        findings: str,
        confidence_delta: float,
        evidence_refs: list[str],
        memory_service: Any,
    ) -> ExplorationResult:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"CuriosityTask {task_id} not found")
        if task.status != CuriosityTaskStatus.PLANNED:
            raise ValueError(f"CuriosityTask {task_id} is not executable: {task.status.value}")
        if memory_service is None:
            raise ValueError("memory_service is required to consolidate curiosity exploration results")

        result = ExplorationResult(
            task_id=task_id,
            findings=findings,
            confidence_delta=confidence_delta,
            evidence_refs=evidence_refs,
        )
        memory = memory_service.remember(
            content=findings,
            title=f"G24 curiosity result: {', '.join(task.target_topics)}",
            summary=f"Curiosity exploration completed for {', '.join(task.target_topics)}",
            layer="semantic",
            source="curiosity",
            trace_id=task_id,
            target_id=task_id,
            tags=["g24", "curiosity", *task.target_topics],
            learning_direction=task.learning_direction,
            confidence_delta=confidence_delta,
            evidence_refs=evidence_refs,
        )
        memory_id = str(getattr(memory, "memory_id", ""))
        if not memory_id:
            raise RuntimeError("MemoryService returned a record without memory_id")
        verified = memory_service.get_record(memory_id)
        if verified is None:
            raise RuntimeError(f"Curiosity result memory {memory_id} was not queryable after write")

        result = result.model_copy(update={"memory_id": memory_id})
        completed = task.model_copy(
            update={
                "status": CuriosityTaskStatus.COMPLETED,
                "result_id": result.result_id,
                "memory_id": memory_id,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._tasks[task_id] = completed
        self._results[result.result_id] = result
        return result

    def get_task(self, task_id: str) -> CuriosityTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[CuriosityTask]:
        return sorted(self._tasks.values(), key=lambda item: item.created_at)

    def get_result(self, result_id: str) -> ExplorationResult | None:
        return self._results.get(result_id)

    def _rank_uncertainties(self, uncertainties: list[EpistemicUncertainty]) -> list[EpistemicUncertainty]:
        ranked = sorted(
            uncertainties,
            key=lambda item: item.knowledge_gap_score * (1.0 - item.confidence) * item.expected_learning_value,
            reverse=True,
        )
        return [
            item
            for item in ranked
            if item.knowledge_gap_score * (1.0 - item.confidence) * item.expected_learning_value >= 0.2
        ]

    def _build_task(
        self,
        *,
        uncertainty: EpistemicUncertainty,
        budget: CuriosityBudget,
        trigger_source: Literal["idle_heartbeat", "manual_cycle"],
    ) -> CuriosityTask:
        priority = round(
            min(1.0, uncertainty.knowledge_gap_score * (1.0 - uncertainty.confidence) * uncertainty.expected_learning_value),
            3,
        )
        decision = self._budget_decision(uncertainty, budget)
        status = CuriosityTaskStatus.PLANNED if decision.approved else CuriosityTaskStatus.BLOCKED
        return CuriosityTask(
            exploration_goal=f"Reduce uncertainty about {uncertainty.topic}: {uncertainty.description}",
            target_topics=[uncertainty.topic],
            uncertainty_ids=[uncertainty.uncertainty_id],
            priority_score=priority,
            risk_level=uncertainty.risk_level,
            trigger_source=trigger_source,
            budget_decision=decision,
            status=status,
            blocked_reason=None if decision.approved else decision.reason,
        )

    def _budget_decision(self, uncertainty: EpistemicUncertainty, budget: CuriosityBudget) -> BudgetDecision:
        reason = "approved_low_risk_idle_curiosity"
        approved = True
        if uncertainty.risk_level in {"high", "critical"}:
            approved = False
            reason = "blocked_high_risk_curiosity_requires_non_autonomous_review"
        elif uncertainty.estimated_tokens > budget.remaining_tokens:
            approved = False
            reason = "blocked_by_token_budget"
        elif uncertainty.estimated_compute_units > budget.remaining_compute_units:
            approved = False
            reason = "blocked_by_compute_budget"
        elif uncertainty.estimated_tokens > budget.max_tokens_per_task:
            approved = False
            reason = "blocked_by_per_task_token_limit"
        elif uncertainty.estimated_compute_units > budget.max_compute_units_per_task:
            approved = False
            reason = "blocked_by_per_task_compute_limit"
        return BudgetDecision(
            approved=approved,
            status="approved" if approved else "blocked",
            reason=reason,
            remaining_tokens=budget.remaining_tokens,
            remaining_compute_units=budget.remaining_compute_units,
            estimated_tokens=uncertainty.estimated_tokens,
            estimated_compute_units=uncertainty.estimated_compute_units,
        )


_DEFAULT_ENGINE = CuriosityEngine()


def get_curiosity_engine() -> CuriosityEngine:
    return _DEFAULT_ENGINE
