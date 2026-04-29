from __future__ import annotations

from pathlib import Path
from typing import Any


class PlanExecutionEvidenceError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Plan execution evidence failed")


EXECUTION_EVIDENCE_KINDS = {
    "browser_e2e_validation",
    "frontend_build_validation",
    "full_pytest_regression",
}

EXECUTION_EVIDENCE_REQUIREMENTS = {
    "browser_e2e_validation": {
        "required_fields": (
            "url",
            "assertions",
            "screenshot_or_trace_uri",
            "command",
            "exit_code",
            "output_log_uri",
        ),
        "minimum_assertion_count": 3,
        "required_assertions": (
            "phase_b_gate_visible",
            "phase_m_gate_visible",
            "waiting_evidence_not_marked_complete",
        ),
    },
    "frontend_build_validation": {
        "required_fields": (
            "command",
            "exit_code",
            "checked_files",
            "artifact_uri",
            "output_log_uri",
        ),
        "required_command_fragment": "npm run build",
        "minimum_checked_file_count": 1,
    },
    "full_pytest_regression": {
        "required_fields": (
            "command",
            "exit_code",
            "test_count",
            "failure_count",
            "duration_seconds",
            "output_log_uri",
        ),
        "required_command_fragment": "pytest",
        "minimum_test_count": 1,
    },
}


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_str(item) for item in value if _as_str(item)]


def _local_path_exists(uri: str) -> bool | None:
    if not uri:
        return None
    path_text = uri[7:] if uri.startswith("file://") else uri
    if not path_text.startswith("/"):
        return None
    return Path(path_text).exists()


def _validate_execution_evidence(evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    evidence_kind = _as_str(evidence.get("evidence_kind"))
    environment = _as_str(evidence.get("environment"))
    captured_at = _as_str(evidence.get("captured_at"))
    owner = _as_str(evidence.get("owner"))
    command = _as_str(evidence.get("command"))
    exit_code = evidence.get("exit_code")
    output_digest = _as_str(evidence.get("output_digest"))
    output_log_uri = _as_str(evidence.get("output_log_uri"))

    if evidence_kind not in EXECUTION_EVIDENCE_KINDS:
        failures.append({"reason": "execution_evidence_kind_invalid", "evidence_kind": evidence_kind})
        requirements: dict[str, Any] = {}
    else:
        requirements = EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]

    if not environment:
        failures.append({"reason": "execution_environment_missing"})
    if not captured_at:
        failures.append({"reason": "execution_captured_at_missing"})
    if not owner:
        failures.append({"reason": "execution_owner_missing"})
    if not command:
        failures.append({"reason": "execution_command_missing"})
    if not output_digest:
        failures.append({"reason": "execution_output_digest_missing"})
    if not output_log_uri:
        failures.append({"reason": "execution_output_log_uri_missing"})
    elif _local_path_exists(output_log_uri) is False:
        failures.append({"reason": "execution_output_log_file_missing", "output_log_uri": output_log_uri})
    if not isinstance(exit_code, int):
        failures.append({"reason": "execution_exit_code_must_be_integer", "exit_code": exit_code})
    elif exit_code != 0:
        failures.append({"reason": "execution_exit_code_not_zero", "exit_code": exit_code})

    if requirements:
        missing_fields = [
            field
            for field in requirements["required_fields"]
            if evidence.get(field) in (None, "", [], {})
        ]
        if missing_fields:
            failures.append(
                {
                    "reason": "execution_evidence_required_fields_missing",
                    "evidence_kind": evidence_kind,
                    "missing_fields": missing_fields,
                }
            )

    if evidence_kind == "browser_e2e_validation":
        assertions = _as_string_list(evidence.get("assertions"))
        required_assertions = set(EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["required_assertions"])
        missing_assertions = sorted(required_assertions - set(assertions))
        screenshot_or_trace_uri = _as_str(evidence.get("screenshot_or_trace_uri"))
        if _local_path_exists(screenshot_or_trace_uri) is False:
            failures.append(
                {
                    "reason": "browser_e2e_screenshot_or_trace_file_missing",
                    "screenshot_or_trace_uri": screenshot_or_trace_uri,
                }
            )
        if len(assertions) < int(EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_assertion_count"]):
            failures.append(
                {
                    "reason": "browser_e2e_assertion_count_below_required",
                    "minimum_assertion_count": EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_assertion_count"],
                    "actual_assertion_count": len(assertions),
                }
            )
        if missing_assertions:
            failures.append(
                {
                    "reason": "browser_e2e_required_assertions_missing",
                    "missing_assertions": missing_assertions,
                }
            )

    if evidence_kind == "frontend_build_validation":
        if command and EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["required_command_fragment"] not in command:
            failures.append(
                {
                    "reason": "frontend_build_command_mismatch",
                    "required_command_fragment": EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["required_command_fragment"],
                    "command": command,
                }
            )
        checked_files = _as_string_list(evidence.get("checked_files"))
        artifact_uri = _as_str(evidence.get("artifact_uri"))
        if _local_path_exists(artifact_uri) is False:
            failures.append(
                {
                    "reason": "frontend_build_artifact_file_missing",
                    "artifact_uri": artifact_uri,
                }
            )
        if len(checked_files) < int(EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_checked_file_count"]):
            failures.append(
                {
                    "reason": "frontend_build_checked_files_missing",
                    "minimum_checked_file_count": EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_checked_file_count"],
                    "actual_checked_file_count": len(checked_files),
                }
            )

    if evidence_kind == "full_pytest_regression":
        if command and EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["required_command_fragment"] not in command:
            failures.append(
                {
                    "reason": "full_pytest_command_mismatch",
                    "required_command_fragment": EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["required_command_fragment"],
                    "command": command,
                }
            )
        test_count = evidence.get("test_count")
        failure_count = evidence.get("failure_count")
        if not isinstance(test_count, int) or test_count < int(EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_test_count"]):
            failures.append(
                {
                    "reason": "full_pytest_test_count_below_required",
                    "minimum_test_count": EXECUTION_EVIDENCE_REQUIREMENTS[evidence_kind]["minimum_test_count"],
                    "actual_test_count": test_count,
                }
            )
        if failure_count != 0:
            failures.append(
                {
                    "reason": "full_pytest_failure_count_not_zero",
                    "failure_count": failure_count,
                }
            )

    normalized = {
        "evidence_kind": evidence_kind,
        "environment": environment,
        "captured_at": captured_at,
        "owner": owner,
        "command": command,
        "exit_code": exit_code,
        "output_digest": output_digest,
        "output_log_uri": output_log_uri,
        "url": _as_str(evidence.get("url")),
        "assertions": _as_string_list(evidence.get("assertions")),
        "screenshot_or_trace_uri": _as_str(evidence.get("screenshot_or_trace_uri")),
        "checked_files": _as_string_list(evidence.get("checked_files")),
        "artifact_uri": _as_str(evidence.get("artifact_uri")),
        "test_count": evidence.get("test_count"),
        "failure_count": evidence.get("failure_count"),
        "duration_seconds": evidence.get("duration_seconds"),
        "requirements": EXECUTION_EVIDENCE_REQUIREMENTS.get(evidence_kind),
    }
    return failures, normalized


def register_plan_execution_evidence(
    *,
    learning_service: Any,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        failures.append({"reason": "learning_service_record_missing"})
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if not isinstance(evidence, dict):
        failures.append({"reason": "execution_evidence_must_be_object"})
        evidence = {}
    evidence_failures, normalized = _validate_execution_evidence(evidence)
    failures.extend(evidence_failures)
    if failures:
        raise PlanExecutionEvidenceError(failures)

    trace_id = f"plan-execution:{normalized['evidence_kind']}:{normalized['output_digest']}"
    record = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="plan_execution_evidence",
        trace_id=trace_id,
        detail={
            "source": "plan_execution_evidence",
            "evidence": normalized,
            "evidence_kind": normalized["evidence_kind"],
            "output_digest": normalized["output_digest"],
        },
    )
    learning_trace_id = _as_str(getattr(record, "trace_id", "") or trace_id)
    rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matches = [
        row
        for row in rows
        if row.detail.get("learning_kind") == "plan_execution_evidence"
        and row.detail.get("output_digest") == normalized["output_digest"]
        and row.detail.get("evidence_kind") == normalized["evidence_kind"]
    ]
    if len(matches) != 1:
        raise PlanExecutionEvidenceError(
            [
                {
                    "reason": "execution_evidence_query_mismatch",
                    "evidence_kind": normalized["evidence_kind"],
                    "output_digest": normalized["output_digest"],
                    "match_count": len(matches),
                }
            ]
        )
    return {
        "execution_evidence_status": "registered",
        "learning_trace_id": learning_trace_id,
        "evidence": matches[0].detail["evidence"],
    }


def build_plan_execution_evidence_summary(
    *,
    learning_service: Any,
    limit: int = 500,
) -> dict[str, Any]:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise PlanExecutionEvidenceError([{"reason": "learning_service_query_missing"}])
    rows = learning_service.query_overall_records(limit=limit)
    evidence_items: list[dict[str, Any]] = []
    completed_kinds: set[str] = set()
    for row in rows:
        detail = dict(row.detail or {})
        if detail.get("learning_kind") != "plan_execution_evidence":
            continue
        evidence = dict(detail.get("evidence") or {})
        item = {
            "learning_trace_id": row.trace_id,
            "evidence_kind": evidence.get("evidence_kind"),
            "environment": evidence.get("environment"),
            "command": evidence.get("command"),
            "exit_code": evidence.get("exit_code"),
            "output_digest": evidence.get("output_digest"),
            "requirements": evidence.get("requirements"),
        }
        evidence_items.append(item)
        if item["evidence_kind"] in EXECUTION_EVIDENCE_KINDS and item["exit_code"] == 0:
            completed_kinds.add(str(item["evidence_kind"]))
    missing_execution_kinds = sorted(EXECUTION_EVIDENCE_KINDS - completed_kinds)
    return {
        "execution_evidence_summary_status": "complete" if not missing_execution_kinds else "incomplete",
        "execution_evidence_count": len(evidence_items),
        "completed_execution_evidence_kinds": sorted(completed_kinds),
        "missing_execution_evidence_kinds": missing_execution_kinds,
        "execution_evidence_requirements": EXECUTION_EVIDENCE_REQUIREMENTS,
        "evidence": evidence_items,
    }
