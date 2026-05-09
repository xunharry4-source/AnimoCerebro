from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


ReplayMode = Literal["read_only", "sandbox", "diff", "teaching"]


class TraceReplayBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    mode: ReplayMode = "read_only"
    compare_trace_id: str | None = None
    sandbox_confirmation: bool = False


class TraceReplayReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_id: str
    trace_id: str
    source_observation_id: str
    mode: ReplayMode
    replayed_at: str
    executable_actions_enabled: bool = False
    production_side_effects_enabled: bool = False
    reconstruction_status: Literal["complete", "incomplete"]
    timeline: list[dict[str, Any]]
    call_tree: list[dict[str, Any]]
    state_machine: list[dict[str, Any]]
    error_distribution: dict[str, Any]
    evidence_bundle: dict[str, Any]
    key_decision_points: list[dict[str, Any]]
    postmortem_report: dict[str, Any]
    diff_report: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    searchable_refs: dict[str, list[str]] = Field(default_factory=dict)


def trace_replay_capabilities() -> dict[str, Any]:
    return {
        "lookup_keys": ["trace_id", "task_id", "request_id", "decision_id", "agent_id"],
        "views": ["call_tree", "timeline", "state_machine", "error_distribution", "evidence"],
        "modes": ["read_only", "sandbox", "diff", "teaching"],
        "safety_rules": [
            "read_only is the default mode",
            "sandbox replay requires explicit sandbox_confirmation",
            "production side effects are never enabled by replay APIs",
            "incomplete evidence must return reconstruction_status=incomplete",
        ],
    }


def build_trace_replay_report(
    observation_report: dict[str, Any],
    request: TraceReplayBuildRequest,
    *,
    compare_observation_report: dict[str, Any] | None = None,
) -> TraceReplayReport:
    if observation_report.get("trace_id") != request.trace_id:
        raise ValueError("trace_id does not match the observation report")
    if request.mode == "sandbox" and not request.sandbox_confirmation:
        raise ValueError("sandbox replay requires sandbox_confirmation=true")
    if request.mode == "diff" and not compare_observation_report:
        raise ValueError("diff replay requires compare_trace_id with an existing replay source")

    source_spans = list(observation_report.get("source_spans") or [])
    warnings = _evidence_warnings(observation_report, source_spans)
    timeline = _build_timeline(source_spans)
    state_machine = _build_state_machine(timeline)
    error_distribution = _build_error_distribution(timeline, observation_report)
    evidence_bundle = _build_evidence_bundle(timeline, observation_report)
    key_decision_points = _build_key_decision_points(timeline, observation_report)
    postmortem_report = _build_postmortem_report(timeline, observation_report, warnings)
    diff_report = (
        _build_diff_report(observation_report, compare_observation_report)
        if compare_observation_report is not None
        else None
    )
    reconstruction_status: Literal["complete", "incomplete"] = "incomplete" if warnings else "complete"

    return TraceReplayReport(
        replay_id=f"trace-replay:{uuid4().hex}",
        trace_id=request.trace_id,
        source_observation_id=str(observation_report.get("observation_id") or ""),
        mode=request.mode,
        replayed_at=datetime.now(timezone.utc).isoformat(),
        reconstruction_status=reconstruction_status,
        timeline=timeline,
        call_tree=list(observation_report.get("call_tree") or []),
        state_machine=state_machine,
        error_distribution=error_distribution,
        evidence_bundle=evidence_bundle,
        key_decision_points=key_decision_points,
        postmortem_report=postmortem_report,
        diff_report=diff_report,
        warnings=warnings,
        searchable_refs=dict(observation_report.get("searchable_refs") or {}),
    )


def _build_timeline(source_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(source_spans, key=lambda item: str(item.get("occurred_at") or ""))
    timeline: list[dict[str, Any]] = []
    for index, span in enumerate(rows, start=1):
        timeline.append(
            {
                "order": index,
                "trace_id": span.get("trace_id"),
                "span_id": span.get("span_id"),
                "parent_span_id": span.get("parent_span_id"),
                "stage": span.get("stage"),
                "actor": span.get("actor"),
                "module": span.get("module"),
                "operation": span.get("operation"),
                "status": span.get("status"),
                "duration_ms": span.get("duration_ms"),
                "occurred_at": span.get("occurred_at"),
                "input_summary": span.get("input_summary"),
                "output_summary": span.get("output_summary"),
                "error_code": span.get("error_code"),
                "error_stage": span.get("error_stage"),
                "evidence_refs": list(span.get("evidence_refs") or []),
                "request_id": span.get("request_id"),
                "task_id": span.get("task_id"),
                "agent_id": span.get("agent_id"),
                "decision_id": span.get("decision_id"),
                "retry_count": span.get("retry_count", 0),
            }
        )
    return timeline


def _build_state_machine(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in timeline:
        key = str(row.get("task_id") or row.get("request_id") or row.get("trace_id"))
        grouped[key].append(row)
    machines: list[dict[str, Any]] = []
    for entity_id, rows in sorted(grouped.items()):
        transitions = [
            {
                "from": "start" if index == 0 else f"{rows[index - 1].get('stage')}:{rows[index - 1].get('status')}",
                "to": f"{row.get('stage')}:{row.get('status')}",
                "span_id": row.get("span_id"),
                "occurred_at": row.get("occurred_at"),
            }
            for index, row in enumerate(rows)
        ]
        machines.append(
            {
                "entity_id": entity_id,
                "transition_count": len(transitions),
                "initial_state": transitions[0]["from"] if transitions else "start",
                "final_state": transitions[-1]["to"] if transitions else "unknown",
                "transitions": transitions,
            }
        )
    return machines


def _build_error_distribution(timeline: list[dict[str, Any]], observation_report: dict[str, Any]) -> dict[str, Any]:
    by_stage: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    by_error_code: Counter[str] = Counter()
    failure_chain: list[dict[str, Any]] = []
    for row in timeline:
        if row.get("status") in {"failed", "blocked", "degraded"} or row.get("error_code"):
            stage = str(row.get("stage") or "unknown")
            module = str(row.get("module") or "unknown")
            error_code = str(row.get("error_code") or row.get("status") or "unknown")
            by_stage[stage] += 1
            by_module[module] += 1
            by_error_code[error_code] += 1
            failure_chain.append(
                {
                    "span_id": row.get("span_id"),
                    "stage": stage,
                    "module": module,
                    "status": row.get("status"),
                    "error_code": row.get("error_code"),
                }
            )
    for anomaly in observation_report.get("anomalies") or []:
        by_error_code[str(anomaly.get("code") or "observability_anomaly")] += 1
    return {
        "by_stage": dict(sorted(by_stage.items())),
        "by_module": dict(sorted(by_module.items())),
        "by_error_code": dict(sorted(by_error_code.items())),
        "failure_chain": failure_chain,
    }


def _build_evidence_bundle(timeline: list[dict[str, Any]], observation_report: dict[str, Any]) -> dict[str, Any]:
    refs_by_kind: dict[str, set[str]] = defaultdict(set)
    for row in timeline:
        for ref in row.get("evidence_refs") or []:
            kind = str(ref).split(":", 1)[0] if ":" in str(ref) else "other"
            refs_by_kind[kind].add(str(ref))
        for key in ("request_id", "task_id", "agent_id", "decision_id"):
            if row.get(key):
                refs_by_kind[key].add(str(row[key]))
    for key, values in (observation_report.get("searchable_refs") or {}).items():
        for value in values:
            refs_by_kind[key].add(str(value))
    return {
        "complete": bool(timeline) and all(row.get("evidence_refs") for row in timeline),
        "refs_by_kind": {key: sorted(values) for key, values in sorted(refs_by_kind.items())},
        "observation_anomalies": list(observation_report.get("anomalies") or []),
    }


def _build_key_decision_points(
    timeline: list[dict[str, Any]],
    observation_report: dict[str, Any],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in timeline:
        if row.get("decision_id") or row.get("stage") == "safety_review" or row.get("status") in {"failed", "blocked", "degraded"}:
            points.append(
                {
                    "span_id": row.get("span_id"),
                    "stage": row.get("stage"),
                    "module": row.get("module"),
                    "operation": row.get("operation"),
                    "status": row.get("status"),
                    "decision_id": row.get("decision_id"),
                    "reason": row.get("output_summary"),
                }
            )
    for anomaly in observation_report.get("anomalies") or []:
        if anomaly.get("severity") == "critical":
            points.append(
                {
                    "span_id": anomaly.get("span_id"),
                    "stage": anomaly.get("stage"),
                    "module": anomaly.get("module"),
                    "operation": anomaly.get("operation"),
                    "status": "observability_anomaly",
                    "decision_id": None,
                    "reason": anomaly.get("message"),
                }
            )
    return points


def _build_postmortem_report(
    timeline: list[dict[str, Any]],
    observation_report: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_rows = [
        row
        for row in timeline
        if row.get("status") in {"failed", "blocked", "degraded"} or row.get("error_code")
    ]
    critical_anomalies = [
        item for item in (observation_report.get("anomalies") or []) if item.get("severity") == "critical"
    ]
    if failed_rows:
        first = failed_rows[0]
        root_cause = f"{first.get('stage')}::{first.get('module')}::{first.get('error_code') or first.get('status')}"
    elif critical_anomalies:
        first_anomaly = critical_anomalies[0]
        root_cause = f"observability::{first_anomaly.get('code')}"
    else:
        root_cause = "no_failure_detected"

    modules = sorted({str(row.get("module")) for row in timeline if row.get("module")})
    missed_guardrails: list[str] = []
    stages = {row.get("stage") for row in timeline}
    if failed_rows and "safety_review" not in stages:
        missed_guardrails.append("safety_review_missing_before_failure")
    if warnings:
        missed_guardrails.append("evidence_chain_incomplete")

    return {
        "root_cause": root_cause,
        "impact_scope": {
            "trace_id": observation_report.get("trace_id"),
            "modules": modules,
            "searchable_refs": observation_report.get("searchable_refs") or {},
        },
        "failure_chain": [
            {
                "span_id": row.get("span_id"),
                "stage": row.get("stage"),
                "module": row.get("module"),
                "status": row.get("status"),
                "error_code": row.get("error_code"),
            }
            for row in failed_rows
        ],
        "missed_guardrails": missed_guardrails,
        "evidence_bundle": {
            "span_count": len(timeline),
            "warning_count": len(warnings),
            "critical_anomaly_count": len(critical_anomalies),
        },
        "remediation_actions": _remediation_actions(root_cause, warnings),
        "regression_tests_needed": _regression_tests(root_cause, failed_rows, warnings),
    }


def _build_diff_report(left: dict[str, Any], right: dict[str, Any] | None) -> dict[str, Any] | None:
    if right is None:
        return None
    left_spans = _build_timeline(list(left.get("source_spans") or []))
    right_spans = _build_timeline(list(right.get("source_spans") or []))
    left_keys = {_diff_key(row) for row in left_spans}
    right_keys = {_diff_key(row) for row in right_spans}
    left_errors = set(_build_error_distribution(left_spans, left)["by_error_code"])
    right_errors = set(_build_error_distribution(right_spans, right)["by_error_code"])
    return {
        "left_trace_id": left.get("trace_id"),
        "right_trace_id": right.get("trace_id"),
        "added_steps": sorted(right_keys - left_keys),
        "missing_steps": sorted(left_keys - right_keys),
        "left_only_errors": sorted(left_errors - right_errors),
        "right_only_errors": sorted(right_errors - left_errors),
        "status_changed": (left.get("observability_status") != right.get("observability_status")),
    }


def _diff_key(row: dict[str, Any]) -> str:
    return f"{row.get('stage')}::{row.get('module')}::{row.get('operation')}::{row.get('status')}"


def _evidence_warnings(observation_report: dict[str, Any], source_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not source_spans:
        warnings.append({"code": "source_spans_missing", "message": "replay source has no persisted source_spans"})
    if not observation_report.get("call_tree"):
        warnings.append({"code": "call_tree_missing", "message": "replay source has no call_tree"})
    missing_evidence = [
        str(span.get("span_id"))
        for span in source_spans
        if not span.get("evidence_refs")
    ]
    if missing_evidence:
        warnings.append(
            {
                "code": "span_evidence_refs_missing",
                "message": "one or more spans lack evidence_refs",
                "span_ids": missing_evidence,
            }
        )
    return warnings


def _remediation_actions(root_cause: str, warnings: list[dict[str, Any]]) -> list[str]:
    actions = []
    if root_cause == "no_failure_detected":
        actions.append("keep replay evidence retention enabled for future audits")
    else:
        actions.append("inspect the first failing span and restore the upstream guardrail")
    if warnings:
        actions.append("backfill missing replay evidence before marking the trace fully replayable")
    return actions


def _regression_tests(
    root_cause: str,
    failed_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[str]:
    tests = ["requests_api_replay_read_after_write"]
    if failed_rows:
        tests.append("failure_chain_replay_regression")
    if warnings:
        tests.append("incomplete_evidence_replay_regression")
    if root_cause == "no_failure_detected":
        tests.append("healthy_trace_replay_regression")
    return tests
