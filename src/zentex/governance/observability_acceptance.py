from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


AcceptanceTestCategory = Literal[
    "unit",
    "integration",
    "main_chain",
    "replay",
    "error_response",
    "real_acceptance",
]
AcceptanceFaultCategory = Literal[
    "trace_break",
    "span_missing",
    "clock_drift",
    "error_code_missing",
    "error_stage_wrong",
    "replay_data_missing",
    "audit_ref_lost",
    "fake_success_internal_failure",
]


class ObservabilityAcceptanceTestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: AcceptanceTestCategory
    name: str = Field(min_length=1)
    command: str = Field(min_length=1)
    passed: bool
    used_real_service: bool
    used_requests: bool = False
    checked_business_result: bool = False
    checked_persisted_state: bool = False
    checked_audit_chain: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class ObservabilityAcceptanceFaultEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: AcceptanceFaultCategory
    name: str = Field(min_length=1)
    injected: bool
    observed_expected_result: bool
    evidence_refs: list[str] = Field(default_factory=list)


class ObservabilityAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"obs-acceptance:{uuid4().hex}")
    release_candidate: str = Field(min_length=1)
    observation_ids: list[str] = Field(min_length=1)
    replay_ids: list[str] = Field(min_length=1)
    unified_error_ids: list[str] = Field(min_length=1)
    test_evidence: list[ObservabilityAcceptanceTestEvidence] = Field(min_length=1)
    fault_evidence: list[ObservabilityAcceptanceFaultEvidence] = Field(min_length=1)
    operator: str = Field(default="system", min_length=1)


class ObservabilityAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    request_id: str
    release_candidate: str
    evaluated_at: str
    release_decision: Literal["allowed", "blocked"]
    observability_complete: bool
    replay_complete: bool
    error_response_complete: bool
    real_complete: bool
    completion_summary: dict[str, Any]
    passed_checks: list[str] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)


REQUIRED_TEST_CATEGORIES: tuple[AcceptanceTestCategory, ...] = (
    "unit",
    "integration",
    "main_chain",
    "replay",
    "error_response",
    "real_acceptance",
)
REQUIRED_FAULT_CATEGORIES: tuple[AcceptanceFaultCategory, ...] = (
    "trace_break",
    "span_missing",
    "clock_drift",
    "error_code_missing",
    "error_stage_wrong",
    "replay_data_missing",
    "audit_ref_lost",
    "fake_success_internal_failure",
)
REQUIRED_TRACE_STAGES = (
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
REQUIRED_ERROR_ENVELOPE_FIELDS = (
    "error_code",
    "error_category",
    "error_stage",
    "severity",
    "retryable",
    "message",
    "recovery_hint",
)
REQUIRED_AUDIT_EVENTS = (
    "trace_observability_evaluated",
    "trace_replay_built",
    "unified_error_mapped",
)


def observability_acceptance_matrix() -> dict[str, Any]:
    return {
        "required_test_categories": list(REQUIRED_TEST_CATEGORIES),
        "required_fault_categories": list(REQUIRED_FAULT_CATEGORIES),
        "required_trace_stages": list(REQUIRED_TRACE_STAGES),
        "required_error_envelope_fields": list(REQUIRED_ERROR_ENVELOPE_FIELDS),
        "required_audit_events": list(REQUIRED_AUDIT_EVENTS),
        "completion_dimensions": [
            "observability_complete",
            "replay_complete",
            "error_response_complete",
            "real_complete",
        ],
    }


def evaluate_observability_acceptance(
    request: ObservabilityAcceptanceRequest,
    *,
    observation_reports: list[dict[str, Any]],
    replay_reports: list[dict[str, Any]],
    unified_error_reports: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
) -> ObservabilityAcceptanceReport:
    gaps: list[dict[str, Any]] = []
    passed: list[str] = []

    observation_by_id = {str(item.get("observation_id")): item for item in observation_reports}
    replay_by_id = {str(item.get("replay_id")): item for item in replay_reports}
    error_by_id = {str(item.get("unified_error", {}).get("error_id")): item for item in unified_error_reports}

    selected_observations = _select(request.observation_ids, observation_by_id, "observation", gaps)
    selected_replays = _select(request.replay_ids, replay_by_id, "replay", gaps)
    selected_errors = _select(request.unified_error_ids, error_by_id, "unified_error", gaps)

    observability_complete = _check_observability(selected_observations, gaps, passed)
    replay_complete = _check_replay(selected_replays, gaps, passed)
    error_response_complete = _check_errors(selected_errors, gaps, passed)
    tests_complete = _check_tests(request.test_evidence, gaps, passed)
    faults_complete = _check_faults(request.fault_evidence, gaps, passed)
    audit_complete = _check_audit(audit_events, gaps, passed)
    real_complete = all(
        [
            observability_complete,
            replay_complete,
            error_response_complete,
            tests_complete,
            faults_complete,
            audit_complete,
        ]
    )
    blockers = [gap for gap in gaps if gap.get("blocking") is True]
    release_decision = "allowed" if real_complete and not blockers else "blocked"

    return ObservabilityAcceptanceReport(
        evaluation_id=f"obs-acceptance-eval:{uuid4().hex}",
        request_id=request.request_id,
        release_candidate=request.release_candidate,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        release_decision=release_decision,
        observability_complete=observability_complete,
        replay_complete=replay_complete,
        error_response_complete=error_response_complete,
        real_complete=real_complete,
        completion_summary={
            "submitted_observation_count": len(selected_observations),
            "submitted_replay_count": len(selected_replays),
            "submitted_unified_error_count": len(selected_errors),
            "required_test_category_count": len(REQUIRED_TEST_CATEGORIES),
            "required_fault_category_count": len(REQUIRED_FAULT_CATEGORIES),
            "audit_event_count": len(audit_events),
        },
        passed_checks=passed,
        blockers=blockers,
        gaps=gaps,
    )


def _select(
    ids: list[str],
    by_id: dict[str, dict[str, Any]],
    label: str,
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item_id in ids:
        item = by_id.get(item_id)
        if item is None:
            gaps.append(_gap(f"{label}_missing", f"{label} report not found: {item_id}"))
        else:
            selected.append(item)
    return selected


def _check_observability(
    reports: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    passed: list[str],
) -> bool:
    healthy = [item for item in reports if item.get("observability_status") == "healthy"]
    broken = [item for item in reports if item.get("observability_status") == "broken"]
    if not healthy:
        gaps.append(_gap("healthy_observation_missing", "no healthy trace observability report was submitted"))
    else:
        report = healthy[0]
        coverage = report.get("stage_coverage") or {}
        missing = [stage for stage in REQUIRED_TRACE_STAGES if coverage.get(stage) is not True]
        if missing:
            gaps.append(_gap("trace_stage_coverage_incomplete", "healthy observation lacks required stages", {"missing": missing}))
        else:
            passed.append("observability:stage_coverage")
        integrity = (report.get("metrics") or {}).get("trace_integrity_metrics") or {}
        if integrity.get("integrity_score") != 1.0:
            gaps.append(_gap("trace_integrity_score_not_complete", "healthy observation integrity_score is not 1.0"))
        else:
            passed.append("observability:integrity_score")
        replay = (report.get("metrics") or {}).get("replay_coverage_metrics") or {}
        if replay.get("replay_ready_ratio") != 1.0:
            gaps.append(_gap("replay_ready_ratio_not_complete", "healthy observation replay_ready_ratio is not 1.0"))
        else:
            passed.append("observability:replay_ready_ratio")
        if not report.get("source_spans"):
            gaps.append(_gap("source_spans_missing", "healthy observation has no persisted source_spans"))
        else:
            passed.append("observability:source_spans")
    if not broken:
        gaps.append(_gap("broken_observation_missing", "no broken observation report submitted for fault detection evidence"))
    else:
        codes = {
            anomaly.get("code")
            for report in broken
            for anomaly in (report.get("anomalies") or [])
        }
        if not {"parent_span_missing", "required_stage_missing"} <= codes:
            gaps.append(_gap("trace_fault_detection_incomplete", "broken observation did not prove trace/span fault detection"))
        else:
            passed.append("observability:fault_detection")
    return not any(gap["code"].startswith(("healthy_observation", "trace_", "replay_ready", "source_spans", "broken_observation")) for gap in gaps)


def _check_replay(reports: list[dict[str, Any]], gaps: list[dict[str, Any]], passed: list[str]) -> bool:
    complete = [item for item in reports if item.get("reconstruction_status") == "complete"]
    if not complete:
        gaps.append(_gap("complete_replay_missing", "no complete replay report submitted"))
        return False
    read_only = [item for item in complete if item.get("mode") == "read_only"]
    diff = [item for item in complete if item.get("mode") == "diff" and item.get("diff_report")]
    failure = [item for item in complete if (item.get("postmortem_report") or {}).get("root_cause") != "no_failure_detected"]
    if not read_only:
        gaps.append(_gap("read_only_replay_missing", "read_only replay report missing"))
    elif any(item.get("production_side_effects_enabled") for item in read_only):
        gaps.append(_gap("replay_side_effects_enabled", "replay enabled production side effects"))
    else:
        passed.append("replay:read_only_safe")
    if not any(item.get("timeline") and item.get("call_tree") and item.get("state_machine") for item in complete):
        gaps.append(_gap("replay_views_incomplete", "replay lacks timeline/call_tree/state_machine"))
    else:
        passed.append("replay:views")
    if not diff:
        gaps.append(_gap("diff_replay_missing", "diff replay report missing"))
    else:
        passed.append("replay:diff")
    if not failure:
        gaps.append(_gap("incident_postmortem_missing", "no replay postmortem with a failure root_cause submitted"))
    else:
        passed.append("replay:postmortem")
    return not any(gap["code"].startswith(("complete_replay", "read_only_replay", "replay_", "diff_replay", "incident_postmortem")) for gap in gaps)


def _check_errors(reports: list[dict[str, Any]], gaps: list[dict[str, Any]], passed: list[str]) -> bool:
    if not reports:
        gaps.append(_gap("unified_errors_missing", "no unified error reports submitted"))
        return False
    categories = set()
    actions = set()
    modules = set()
    for report in reports:
        error = report.get("unified_error") or {}
        envelope = (report.get("api_envelope") or {}).get("error") or {}
        missing = [field for field in REQUIRED_ERROR_ENVELOPE_FIELDS if field not in envelope]
        if missing:
            gaps.append(_gap("error_envelope_field_missing", "api envelope lacks required fields", {"error_id": error.get("error_id"), "missing": missing}))
        if not error.get("trace_id") or not error.get("error_code") or not error.get("error_stage"):
            gaps.append(_gap("unified_error_identity_incomplete", "unified error lacks error_code/error_stage/trace_id"))
        if str(error.get("raw_error_type") or "") in str(error.get("user_visible_message") or ""):
            gaps.append(_gap("raw_error_leaked_to_user", "raw error type leaked to user_visible_message"))
        categories.add(error.get("error_category"))
        actions.add((report.get("disposition") or {}).get("action"))
        modules.add(error.get("source_module"))
    if len(categories - {None}) < 3:
        gaps.append(_gap("error_category_coverage_insufficient", "unified error evidence covers fewer than 3 categories"))
    else:
        passed.append("errors:category_coverage")
    if not {"retry", "block", "escalate"} <= actions:
        gaps.append(_gap("disposition_coverage_insufficient", "disposition evidence lacks retry/block/escalate"))
    else:
        passed.append("errors:disposition_coverage")
    if len(modules - {None}) < 5:
        gaps.append(_gap("error_module_coverage_insufficient", "unified error evidence covers fewer than 5 modules"))
    else:
        passed.append("errors:module_coverage")
    if not any(report.get("audit_payload", {}).get("operator_message") for report in reports):
        gaps.append(_gap("error_audit_payload_missing", "unified errors lack operator audit payload"))
    else:
        passed.append("errors:audit_payload")
    return not any(gap["code"].startswith(("unified_errors", "error_", "raw_error", "disposition")) for gap in gaps)


def _check_tests(
    evidence: list[ObservabilityAcceptanceTestEvidence],
    gaps: list[dict[str, Any]],
    passed: list[str],
) -> bool:
    by_category = {item.category: item for item in evidence}
    for category in REQUIRED_TEST_CATEGORIES:
        item = by_category.get(category)
        if item is None:
            gaps.append(_gap(f"test_{category}_missing", f"{category} test evidence missing"))
            continue
        if not item.passed:
            gaps.append(_gap(f"test_{category}_failed", f"{category} test did not pass"))
            continue
        if not item.used_real_service:
            gaps.append(_gap(f"test_{category}_not_real", f"{category} test did not use a real service"))
            continue
        if category == "real_acceptance" and not item.used_requests:
            gaps.append(_gap("real_acceptance_requests_missing", "real acceptance must use requests"))
            continue
        passed.append(f"test:{category}")
    if not any(item.checked_business_result or item.checked_persisted_state for item in evidence):
        gaps.append(_gap("test_business_or_state_check_missing", "tests lack business-result or persisted-state assertions"))
    else:
        passed.append("test:business_or_state")
    if not any(item.checked_audit_chain for item in evidence):
        gaps.append(_gap("test_audit_chain_check_missing", "tests lack audit-chain assertions"))
    else:
        passed.append("test:audit_chain")
    return not any(gap["code"].startswith(("test_", "real_acceptance")) for gap in gaps)


def _check_faults(
    evidence: list[ObservabilityAcceptanceFaultEvidence],
    gaps: list[dict[str, Any]],
    passed: list[str],
) -> bool:
    by_category = {item.category: item for item in evidence}
    for category in REQUIRED_FAULT_CATEGORIES:
        item = by_category.get(category)
        if item is None:
            gaps.append(_gap(f"fault_{category}_missing", f"{category} fault injection evidence missing"))
            continue
        if not item.injected or not item.observed_expected_result:
            gaps.append(_gap(f"fault_{category}_not_proven", f"{category} fault injection did not prove expected behavior"))
            continue
        passed.append(f"fault:{category}")
    return not any(gap["code"].startswith("fault_") for gap in gaps)


def _check_audit(audit_events: list[dict[str, Any]], gaps: list[dict[str, Any]], passed: list[str]) -> bool:
    events = {str(item.get("event")) for item in audit_events if item.get("event")}
    missing = [event for event in REQUIRED_AUDIT_EVENTS if event not in events]
    if missing:
        gaps.append(_gap("audit_events_missing", "required audit event types missing", {"missing": missing}))
        return False
    passed.append("audit:required_events")
    return True


def _gap(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "blocking": True,
        "details": details or {},
    }
