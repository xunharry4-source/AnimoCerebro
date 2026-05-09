from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


TraceStage = Literal[
    "perception",
    "nine_questions",
    "dispatch",
    "tool_call",
    "safety_review",
    "execution",
    "receipt",
    "reflection",
    "memory_writeback",
]
TraceStatus = Literal["success", "failed", "degraded", "blocked", "skipped"]
TraceActor = Literal["zentex", "plugin", "agent", "cli", "mcp_server", "human_supervisor", "cloud_audit"]


class TraceResourceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_percent: float | None = Field(default=None, ge=0)
    memory_mb: float | None = Field(default=None, ge=0)
    budget_units: float | None = Field(default=None, ge=0)


class TraceSpanEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)
    parent_span_id: str | None = None
    stage: TraceStage
    actor: TraceActor
    module: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    input_summary: str = Field(min_length=1)
    output_summary: str = Field(min_length=1)
    status: TraceStatus
    duration_ms: float = Field(ge=0)
    occurred_at: str
    error_code: str | None = None
    error_stage: TraceStage | None = None
    resource_usage_snapshot: TraceResourceUsage = Field(default_factory=TraceResourceUsage)
    evidence_refs: list[str] = Field(default_factory=list)
    request_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    decision_id: str | None = None
    retry_count: int = Field(default=0, ge=0)


class TraceObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"trace-observation:{uuid4().hex}")
    trace_id: str = Field(min_length=1)
    source: str = Field(default="web_console", min_length=1)
    spans: list[TraceSpanEvidence] = Field(min_length=1)


class TraceObservationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    request_id: str
    trace_id: str
    observed_at: str
    observability_status: Literal["healthy", "degraded", "broken"]
    span_count: int
    stage_coverage: dict[str, bool]
    call_tree: list[dict[str, Any]]
    metrics: dict[str, Any]
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    passed_requirements: list[str] = Field(default_factory=list)
    searchable_refs: dict[str, list[str]] = Field(default_factory=dict)
    source_spans: list[dict[str, Any]] = Field(default_factory=list)


REQUIRED_TRACE_STAGES: tuple[TraceStage, ...] = (
    "perception",
    "nine_questions",
    "dispatch",
    "tool_call",
    "safety_review",
    "execution",
    "receipt",
    "reflection",
    "memory_writeback",
)
EXTERNAL_ACTORS: set[TraceActor] = {"plugin", "agent", "cli", "mcp_server", "cloud_audit"}
HIGH_RISK_STAGES: set[TraceStage] = {"tool_call", "safety_review", "execution", "receipt", "memory_writeback"}
SUMMARY_MIN_LENGTH = 8
CLOCK_DRIFT_SECONDS = 300
SLOW_CALL_MS = 1000
RETRY_STORM_THRESHOLD = 3


def trace_observability_requirements() -> dict[str, Any]:
    return {
        "required_stages": list(REQUIRED_TRACE_STAGES),
        "required_span_fields": [
            "trace_id",
            "span_id",
            "parent_span_id",
            "stage",
            "actor",
            "module",
            "operation",
            "input_summary",
            "output_summary",
            "status",
            "duration_ms",
            "resource_usage_snapshot",
            "evidence_refs",
        ],
        "cross_protocol_actors": sorted(EXTERNAL_ACTORS),
        "anomaly_checks": [
            "trace_id_mismatch",
            "parent_span_missing",
            "duplicate_span_id",
            "clock_drift",
            "summary_insufficient",
            "audit_ref_missing",
            "failed_or_blocked_span",
            "slow_call",
            "retry_storm",
        ],
    }


def evaluate_trace_observability(request: TraceObservationRequest) -> TraceObservationReport:
    anomalies: list[dict[str, Any]] = []
    passed: list[str] = []
    spans = list(request.spans)
    span_by_id: dict[str, TraceSpanEvidence] = {}
    children_by_parent: dict[str | None, list[TraceSpanEvidence]] = defaultdict(list)

    for span in spans:
        if span.trace_id != request.trace_id:
            anomalies.append(
                _anomaly(
                    "trace_id_mismatch",
                    "span trace_id does not match the observation trace_id",
                    span=span,
                    severity="critical",
                )
            )
        if span.span_id in span_by_id:
            anomalies.append(
                _anomaly("duplicate_span_id", "span_id is duplicated within the trace", span=span, severity="critical")
            )
        else:
            span_by_id[span.span_id] = span
        children_by_parent[span.parent_span_id].append(span)

    for span in spans:
        if span.parent_span_id and span.parent_span_id not in span_by_id:
            anomalies.append(
                _anomaly("parent_span_missing", "parent_span_id cannot be resolved", span=span, severity="critical")
            )
        if _summary_is_insufficient(span.input_summary) or _summary_is_insufficient(span.output_summary):
            anomalies.append(
                _anomaly("summary_insufficient", "input/output summary is too weak for troubleshooting", span=span)
            )
        if span.actor in EXTERNAL_ACTORS and not _has_cross_context_ref(span):
            anomalies.append(
                _anomaly("cross_context_ref_missing", "external actor span lacks request/task/agent/decision binding", span=span)
            )
        if span.stage in HIGH_RISK_STAGES and not span.evidence_refs:
            anomalies.append(_anomaly("audit_ref_missing", "high risk span has no evidence_refs", span=span))
        if span.status in {"failed", "blocked"}:
            anomalies.append(
                _anomaly(
                    "failed_or_blocked_span",
                    "span completed with failed or blocked status",
                    span=span,
                    severity="critical",
                )
            )
        if span.status == "degraded":
            anomalies.append(_anomaly("degraded_span", "span completed through degraded path", span=span))
        if span.duration_ms > SLOW_CALL_MS:
            anomalies.append(_anomaly("slow_call", "span duration exceeded slow-call threshold", span=span))
        if span.retry_count >= RETRY_STORM_THRESHOLD:
            anomalies.append(_anomaly("retry_storm", "span retry_count reached retry-storm threshold", span=span))

    _check_clock_drift(spans, anomalies)
    stage_coverage = {stage: any(span.stage == stage for span in spans) for stage in REQUIRED_TRACE_STAGES}
    for stage, covered in stage_coverage.items():
        if covered:
            passed.append(f"stage:{stage}")
        else:
            anomalies.append(
                {
                    "code": "required_stage_missing",
                    "severity": "critical",
                    "stage": stage,
                    "message": f"required trace stage missing: {stage}",
                }
            )

    if not any(span.parent_span_id is None for span in spans):
        anomalies.append(
            {
                "code": "root_span_missing",
                "severity": "critical",
                "message": "trace has no root span",
            }
        )
    else:
        passed.append("trace:root_span")
    if not any(span.evidence_refs for span in spans):
        anomalies.append(
            {
                "code": "evidence_chain_missing",
                "severity": "critical",
                "message": "trace has no evidence references",
            }
        )
    else:
        passed.append("trace:evidence_refs")

    metrics = _build_metrics(spans, stage_coverage, anomalies)
    call_tree = _build_call_tree(children_by_parent, root_parent=None)
    critical_count = sum(1 for item in anomalies if item.get("severity") == "critical")
    if critical_count:
        status: Literal["healthy", "degraded", "broken"] = "broken"
    elif anomalies:
        status = "degraded"
    else:
        status = "healthy"

    return TraceObservationReport(
        observation_id=f"trace-observation:{uuid4().hex}",
        request_id=request.request_id,
        trace_id=request.trace_id,
        observed_at=datetime.now(timezone.utc).isoformat(),
        observability_status=status,
        span_count=len(spans),
        stage_coverage=stage_coverage,
        call_tree=call_tree,
        metrics=metrics,
        anomalies=anomalies,
        passed_requirements=passed,
        searchable_refs=_searchable_refs(spans),
        source_spans=[span.model_dump(mode="json") for span in sorted(spans, key=lambda item: item.occurred_at)],
    )


def _build_metrics(
    spans: list[TraceSpanEvidence],
    stage_coverage: dict[str, bool],
    anomalies: list[dict[str, Any]],
) -> dict[str, Any]:
    latency_by_module: dict[str, float] = defaultdict(float)
    calls_by_module: Counter[str] = Counter()
    failures_by_module: Counter[str] = Counter()
    retry_total = 0
    timeout_count = 0
    degraded_count = 0
    replay_ready_count = 0

    for span in spans:
        latency_by_module[span.module] += span.duration_ms
        calls_by_module[span.module] += 1
        retry_total += span.retry_count
        if span.status in {"failed", "blocked"}:
            failures_by_module[span.module] += 1
        if span.error_code and "timeout" in span.error_code.lower():
            timeout_count += 1
        if span.status == "degraded":
            degraded_count += 1
        if any(ref.startswith("replay:") for ref in span.evidence_refs):
            replay_ready_count += 1

    latency_metrics = {
        module: round(total / calls_by_module[module], 3)
        for module, total in sorted(latency_by_module.items())
    }
    error_rate_metrics = {
        module: round(failures_by_module[module] / calls_by_module[module], 3)
        for module in sorted(calls_by_module)
    }
    coverage_count = sum(1 for covered in stage_coverage.values() if covered)
    critical_count = sum(1 for item in anomalies if item.get("severity") == "critical")

    return {
        "latency_metrics": latency_metrics,
        "error_rate_metrics": error_rate_metrics,
        "retry_metrics": {"total_retry_count": retry_total},
        "timeout_metrics": {"timeout_count": timeout_count},
        "degraded_metrics": {"degraded_count": degraded_count},
        "replay_coverage_metrics": {
            "replay_ready_span_count": replay_ready_count,
            "replay_ready_ratio": round(replay_ready_count / len(spans), 3) if spans else 0.0,
        },
        "trace_integrity_metrics": {
            "required_stage_count": len(REQUIRED_TRACE_STAGES),
            "covered_stage_count": coverage_count,
            "critical_anomaly_count": critical_count,
            "integrity_score": round((coverage_count / len(REQUIRED_TRACE_STAGES)) if not critical_count else 0.0, 3),
        },
    }


def _build_call_tree(
    children_by_parent: dict[str | None, list[TraceSpanEvidence]],
    *,
    root_parent: str | None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for span in sorted(children_by_parent.get(root_parent, []), key=lambda item: item.occurred_at):
        nodes.append(
            {
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "stage": span.stage,
                "actor": span.actor,
                "module": span.module,
                "operation": span.operation,
                "status": span.status,
                "children": _build_call_tree(children_by_parent, root_parent=span.span_id),
            }
        )
    return nodes


def _searchable_refs(spans: list[TraceSpanEvidence]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {
        "request_ids": set(),
        "task_ids": set(),
        "agent_ids": set(),
        "decision_ids": set(),
    }
    for span in spans:
        if span.request_id:
            result["request_ids"].add(span.request_id)
        if span.task_id:
            result["task_ids"].add(span.task_id)
        if span.agent_id:
            result["agent_ids"].add(span.agent_id)
        if span.decision_id:
            result["decision_ids"].add(span.decision_id)
    return {key: sorted(values) for key, values in result.items()}


def _has_cross_context_ref(span: TraceSpanEvidence) -> bool:
    return bool(span.request_id or span.task_id or span.agent_id or span.decision_id)


def _summary_is_insufficient(summary: str) -> bool:
    value = summary.strip().lower()
    return len(value) < SUMMARY_MIN_LENGTH or value in {"ok", "success", "done", "failed", "n/a"}


def _check_clock_drift(spans: list[TraceSpanEvidence], anomalies: list[dict[str, Any]]) -> None:
    parsed: list[tuple[TraceSpanEvidence, datetime]] = []
    for span in spans:
        try:
            value = datetime.fromisoformat(span.occurred_at)
        except ValueError:
            anomalies.append(_anomaly("timestamp_invalid", "occurred_at is not ISO-8601", span=span, severity="critical"))
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        parsed.append((span, value))
    if len(parsed) < 2:
        return
    earliest = min(value for _, value in parsed)
    latest = max(value for _, value in parsed)
    if (latest - earliest).total_seconds() > CLOCK_DRIFT_SECONDS:
        anomalies.append(
            {
                "code": "clock_drift",
                "severity": "warning",
                "message": "trace span timestamps exceed allowed drift window",
                "drift_seconds": round((latest - earliest).total_seconds(), 3),
            }
        )


def _anomaly(
    code: str,
    message: str,
    *,
    span: TraceSpanEvidence,
    severity: Literal["warning", "critical"] = "warning",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "stage": span.stage,
        "module": span.module,
        "operation": span.operation,
        "message": message,
    }
