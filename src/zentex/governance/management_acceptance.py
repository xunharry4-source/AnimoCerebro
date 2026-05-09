from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


ManagementModuleName = Literal["plugin", "task", "agent", "cli", "mcp"]
TestCategory = Literal["unit", "integration", "main_chain", "failure_path", "degraded_path", "rollback_path", "real_environment"]
FaultCategory = Literal["timeout", "disconnect", "permission_denied", "version_conflict", "bad_structure", "fake_health", "audit_chain_missing"]
CompletionTier = Literal["structural", "main_chain", "real"]


class ManagementTestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TestCategory
    name: str = Field(min_length=1)
    command: str = Field(min_length=1)
    passed: bool
    used_real_service: bool
    used_requests: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    checked_business_result: bool = False
    checked_persisted_state: bool = False
    checked_audit_chain: bool = False


class ManagementFaultEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FaultCategory
    name: str = Field(min_length=1)
    injected: bool
    observed_expected_result: bool
    error_code: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ManagementCompletionClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structural_complete: bool = False
    main_chain_complete: bool = False
    real_complete: bool = False


class ManagementModuleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_name: ManagementModuleName
    diagnostic_report: dict[str, Any] = Field(default_factory=dict)
    fault_injection_report: dict[str, Any] = Field(default_factory=dict)
    test_evidence: list[ManagementTestEvidence] = Field(default_factory=list)
    fault_evidence: list[ManagementFaultEvidence] = Field(default_factory=list)
    completion_claim: ManagementCompletionClaim = Field(default_factory=ManagementCompletionClaim)
    source_refs: list[str] = Field(default_factory=list)


class ManagementAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"mgmt-acceptance:{uuid4().hex}")
    release_candidate: str = Field(min_length=1)
    modules: list[ManagementModuleEvidence] = Field(min_length=1)
    operator: str = Field(default="system", min_length=1)


class ManagementAcceptanceModuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_name: ManagementModuleName
    structural_complete: bool
    main_chain_complete: bool
    real_complete: bool
    blocking: bool
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    passed_requirements: list[str] = Field(default_factory=list)


class ManagementAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    request_id: str
    release_candidate: str
    evaluated_at: str
    release_decision: Literal["allowed", "blocked"]
    module_results: list[ManagementAcceptanceModuleResult]
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    completion_summary: dict[str, Any] = Field(default_factory=dict)


REQUIRED_MODULES: tuple[ManagementModuleName, ...] = ("plugin", "task", "agent", "cli", "mcp")
REQUIRED_TEST_CATEGORIES: tuple[TestCategory, ...] = (
    "unit",
    "integration",
    "main_chain",
    "failure_path",
    "degraded_path",
    "rollback_path",
    "real_environment",
)
REQUIRED_FAULT_CATEGORIES: tuple[FaultCategory, ...] = (
    "timeout",
    "disconnect",
    "permission_denied",
    "version_conflict",
    "bad_structure",
    "fake_health",
    "audit_chain_missing",
)
REQUIRED_DIAGNOSTIC_CHECK_KEYWORDS = ("health", "status", "permission", "audit")


def management_acceptance_matrix() -> dict[str, Any]:
    return {
        "modules": list(REQUIRED_MODULES),
        "required_test_categories": list(REQUIRED_TEST_CATEGORIES),
        "required_fault_categories": list(REQUIRED_FAULT_CATEGORIES),
        "completion_tiers": ["structural", "main_chain", "real"],
        "rules": [
            "Every management module must provide diagnostics, tests, fault injection, and real evidence.",
            "Real completion requires real service execution, failure-path evidence, persisted-state or business-result checks, and audit evidence.",
            "A release is blocked when any of plugin/task/agent/cli/mcp is missing or fails real completion.",
        ],
    }


def evaluate_management_acceptance(request: ManagementAcceptanceRequest) -> ManagementAcceptanceReport:
    module_by_name = {module.module_name: module for module in request.modules}
    module_results: list[ManagementAcceptanceModuleResult] = []
    blockers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for module_name in REQUIRED_MODULES:
        evidence = module_by_name.get(module_name)
        if evidence is None:
            gap = _gap(module_name, "module_missing", "required management module evidence is missing", blocking=True)
            blockers.append(gap)
            gaps.append(gap)
            module_results.append(
                ManagementAcceptanceModuleResult(
                    module_name=module_name,
                    structural_complete=False,
                    main_chain_complete=False,
                    real_complete=False,
                    blocking=True,
                    gaps=[gap],
                )
            )
            continue

        result = _evaluate_module(evidence)
        module_results.append(result)
        gaps.extend(result.gaps)
        blockers.extend(gap for gap in result.gaps if gap.get("blocking") is True)

    structural_count = sum(1 for result in module_results if result.structural_complete)
    main_chain_count = sum(1 for result in module_results if result.main_chain_complete)
    real_count = sum(1 for result in module_results if result.real_complete)
    release_decision = "allowed" if not blockers and real_count == len(REQUIRED_MODULES) else "blocked"

    return ManagementAcceptanceReport(
        evaluation_id=f"mgmt-acceptance-eval:{uuid4().hex}",
        request_id=request.request_id,
        release_candidate=request.release_candidate,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        release_decision=release_decision,
        module_results=module_results,
        blockers=blockers,
        gaps=gaps,
        completion_summary={
            "required_module_count": len(REQUIRED_MODULES),
            "submitted_module_count": len(module_by_name),
            "structural_complete_count": structural_count,
            "main_chain_complete_count": main_chain_count,
            "real_complete_count": real_count,
        },
    )


def _evaluate_module(evidence: ManagementModuleEvidence) -> ManagementAcceptanceModuleResult:
    gaps: list[dict[str, Any]] = []
    passed: list[str] = []

    diagnostic_checks = _diagnostic_checks(evidence.diagnostic_report)
    for keyword in REQUIRED_DIAGNOSTIC_CHECK_KEYWORDS:
        if any(keyword in check for check in diagnostic_checks):
            passed.append(f"diagnostic:{keyword}")
        else:
            gaps.append(_gap(evidence.module_name, f"diagnostic_{keyword}_missing", f"diagnostic report lacks {keyword} check", blocking=True))

    if not evidence.diagnostic_report:
        gaps.append(_gap(evidence.module_name, "diagnostic_report_missing", "diagnostic report is empty", blocking=True))
    if evidence.fault_injection_report.get("passed") is not True:
        gaps.append(_gap(evidence.module_name, "fault_matrix_not_passed", "fault injection report did not pass", blocking=True))
    else:
        passed.append("fault_matrix:passed")

    tests_by_category = {item.category: item for item in evidence.test_evidence}
    for category in REQUIRED_TEST_CATEGORIES:
        item = tests_by_category.get(category)
        if item is None:
            gaps.append(_gap(evidence.module_name, f"test_{category}_missing", f"{category} test evidence missing", blocking=True))
            continue
        if not item.passed:
            gaps.append(_gap(evidence.module_name, f"test_{category}_failed", f"{category} test did not pass", blocking=True))
            continue
        if not item.used_real_service:
            gaps.append(_gap(evidence.module_name, f"test_{category}_not_real", f"{category} test did not use a real service", blocking=True))
            continue
        if category == "real_environment" and not item.used_requests:
            gaps.append(_gap(evidence.module_name, "real_environment_requests_missing", "real API acceptance must use requests", blocking=True))
            continue
        passed.append(f"test:{category}")

    faults_by_category = {item.category: item for item in evidence.fault_evidence}
    for category in REQUIRED_FAULT_CATEGORIES:
        item = faults_by_category.get(category)
        if item is None:
            gaps.append(_gap(evidence.module_name, f"fault_{category}_missing", f"{category} fault evidence missing", blocking=True))
            continue
        if not item.injected or not item.observed_expected_result:
            gaps.append(_gap(evidence.module_name, f"fault_{category}_not_observed", f"{category} fault did not show expected behavior", blocking=True))
            continue
        passed.append(f"fault:{category}")

    if not any(item.checked_business_result or item.checked_persisted_state for item in evidence.test_evidence):
        gaps.append(_gap(evidence.module_name, "business_or_state_check_missing", "tests must verify business result or persisted state", blocking=True))
    else:
        passed.append("verification:business_or_state")

    if not any(item.checked_audit_chain for item in evidence.test_evidence):
        gaps.append(_gap(evidence.module_name, "audit_chain_test_missing", "tests must verify audit chain", blocking=True))
    else:
        passed.append("verification:audit")

    structural_complete = (
        evidence.completion_claim.structural_complete
        and bool(evidence.diagnostic_report)
        and not any(gap["code"].startswith("diagnostic_") for gap in gaps)
    )
    main_chain_complete = structural_complete and evidence.completion_claim.main_chain_complete and all(
        category in tests_by_category and tests_by_category[category].passed
        for category in ("integration", "main_chain")
    )
    real_complete = (
        main_chain_complete
        and evidence.completion_claim.real_complete
        and not gaps
        and all(category in faults_by_category for category in REQUIRED_FAULT_CATEGORIES)
    )

    return ManagementAcceptanceModuleResult(
        module_name=evidence.module_name,
        structural_complete=structural_complete,
        main_chain_complete=main_chain_complete,
        real_complete=real_complete,
        blocking=not real_complete,
        gaps=gaps,
        passed_requirements=sorted(set(passed)),
    )


def _diagnostic_checks(report: dict[str, Any]) -> set[str]:
    checks = report.get("checks") if isinstance(report, dict) else None
    if not isinstance(checks, list):
        return set()
    names: set[str] = set()
    for item in checks:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and item.get("passed") is True:
                names.add(name.lower())
    return names


def _gap(module_name: str, code: str, detail: str, *, blocking: bool) -> dict[str, Any]:
    return {"module_name": module_name, "code": code, "detail": detail, "blocking": blocking}
