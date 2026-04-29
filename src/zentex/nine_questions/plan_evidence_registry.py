from __future__ import annotations

from typing import Any


class PlanEvidenceRegistryError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Plan evidence registry failed")


COMPLETION_EVIDENCE_KINDS = {
    "real_production_history",
    "natural_week_observation",
    "online_q8_prompt_baseline",
    "prompt_audit_report_set",
    "phase_d_shadow_canary_rollback",
    "llm_reflection_quality",
}
NON_COMPLETION_EVIDENCE_KINDS = {"generated_verification"}
ALL_EVIDENCE_KINDS = COMPLETION_EVIDENCE_KINDS | NON_COMPLETION_EVIDENCE_KINDS
REAL_EXTERNAL_URI_PREFIXES = (
    "production-export://",
    "database://",
    "internal-api://",
    "observability://",
    "audit://",
    "object-store://",
    "phase-d://",
    "llm-provider://",
)
GENERATED_URI_PREFIXES = ("generated://", "task-service://generated-verification/")
EVIDENCE_REQUIREMENTS = {
    "real_production_history": {
        "allowed_prefixes": ("production-export://", "database://", "internal-api://", "object-store://"),
        "minimum_evidence_count": 100,
        "required_fields": ("task_id", "task_outcome", "q8_trace_id", "manual_review"),
    },
    "natural_week_observation": {
        "allowed_prefixes": ("observability://", "internal-api://", "object-store://"),
        "minimum_evidence_count": 7,
        "required_fields": ("observation_day", "false_kill_rate", "drift_rate"),
    },
    "online_q8_prompt_baseline": {
        "allowed_prefixes": ("observability://", "production-export://", "database://", "internal-api://"),
        "minimum_evidence_count": 100,
        "required_fields": (
            "baseline_prompt_tokens",
            "current_prompt_tokens",
            "llm_call_count",
            "latency_ms",
            "quality_score",
            "replay_count",
        ),
    },
    "prompt_audit_report_set": {
        "allowed_prefixes": ("audit://", "object-store://"),
        "minimum_evidence_count": 27,
        "required_fields": ("audit_id", "question_id", "report_uri", "reviewer"),
    },
    "phase_d_shadow_canary_rollback": {
        "allowed_prefixes": ("phase-d://", "observability://", "internal-api://", "object-store://"),
        "minimum_evidence_count": 5,
        "required_fields": (
            "replay_run_id",
            "gold_standard_id",
            "shadow_run_id",
            "canary_run_id",
            "rollback_run_id",
            "approval_id",
        ),
    },
    "llm_reflection_quality": {
        "allowed_prefixes": ("llm-provider://", "observability://", "internal-api://", "object-store://"),
        "minimum_evidence_count": 1,
        "required_fields": ("provider_key", "model", "quality_score", "reviewer", "evidence_trace_id"),
    },
}


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _validate_manifest(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    source_kind = _as_str(manifest.get("source_kind"))
    source_uri = _as_str(manifest.get("source_uri"))
    environment = _as_str(manifest.get("environment"))
    checksum = _as_str(manifest.get("checksum"))
    captured_at = _as_str(manifest.get("captured_at"))
    owner = _as_str(manifest.get("owner"))
    evidence_count = manifest.get("evidence_count")
    evidence_fields = manifest.get("evidence_fields")

    if source_kind not in ALL_EVIDENCE_KINDS:
        failures.append({"reason": "evidence_source_kind_invalid", "source_kind": source_kind})
    if not source_uri:
        failures.append({"reason": "evidence_source_uri_missing"})
    if not environment:
        failures.append({"reason": "evidence_environment_missing"})
    if not checksum:
        failures.append({"reason": "evidence_checksum_missing"})
    if not captured_at:
        failures.append({"reason": "evidence_captured_at_missing"})
    if not owner:
        failures.append({"reason": "evidence_owner_missing"})
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        failures.append({"reason": "evidence_count_must_be_positive", "evidence_count": evidence_count})
    if not isinstance(evidence_fields, list) or not evidence_fields or not all(_as_str(item) for item in evidence_fields):
        failures.append({"reason": "evidence_fields_missing"})

    counts_toward_completion = False
    if source_kind in COMPLETION_EVIDENCE_KINDS:
        requirements = EVIDENCE_REQUIREMENTS[source_kind]
        allowed_prefixes = requirements["allowed_prefixes"]
        if not source_uri.startswith(REAL_EXTERNAL_URI_PREFIXES):
            failures.append(
                {
                    "reason": "completion_evidence_source_uri_not_real_external",
                    "source_kind": source_kind,
                    "source_uri": source_uri,
                    "allowed_prefixes": list(REAL_EXTERNAL_URI_PREFIXES),
                }
            )
        if source_uri and not source_uri.startswith(allowed_prefixes):
            failures.append(
                {
                    "reason": "completion_evidence_source_uri_kind_mismatch",
                    "source_kind": source_kind,
                    "source_uri": source_uri,
                    "allowed_prefixes": list(allowed_prefixes),
                }
            )
        environment_lower = environment.lower()
        if source_uri.startswith(GENERATED_URI_PREFIXES) or any(
            marker in environment_lower for marker in ("local", "test", "generated", "fixture", "mock")
        ):
            failures.append(
                {
                    "reason": "generated_or_test_evidence_cannot_satisfy_completion_gate",
                    "source_kind": source_kind,
                    "environment": environment,
                }
            )
        minimum_count = int(requirements["minimum_evidence_count"])
        if isinstance(evidence_count, int) and evidence_count < minimum_count:
            failures.append(
                {
                    "reason": "completion_evidence_count_below_required",
                    "source_kind": source_kind,
                    "minimum_evidence_count": minimum_count,
                    "actual_evidence_count": evidence_count,
                }
            )
        if isinstance(evidence_fields, list):
            present_fields = {_as_str(item) for item in evidence_fields}
            missing_fields = sorted(set(requirements["required_fields"]) - present_fields)
            if missing_fields:
                failures.append(
                    {
                        "reason": "completion_evidence_required_fields_missing",
                        "source_kind": source_kind,
                        "missing_fields": missing_fields,
                    }
                )
        counts_toward_completion = not failures
    elif source_kind == "generated_verification":
        counts_toward_completion = False

    normalized = {
        "source_kind": source_kind,
        "source_uri": source_uri,
        "environment": environment,
        "checksum": checksum,
        "captured_at": captured_at,
        "owner": owner,
        "evidence_count": evidence_count,
        "evidence_fields": [_as_str(item) for item in evidence_fields] if isinstance(evidence_fields, list) else [],
        "counts_toward_completion": counts_toward_completion,
        "requirements": EVIDENCE_REQUIREMENTS.get(source_kind),
    }
    return failures, normalized


def register_plan_evidence_manifest(
    *,
    learning_service: Any,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        failures.append({"reason": "learning_service_record_missing"})
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if not isinstance(manifest, dict):
        failures.append({"reason": "evidence_manifest_must_be_object"})
        manifest = {}
    manifest_failures, normalized = _validate_manifest(manifest)
    failures.extend(manifest_failures)
    if failures:
        raise PlanEvidenceRegistryError(failures)

    trace_id = f"plan-evidence:{normalized['source_kind']}:{normalized['checksum']}"
    record = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="plan_evidence_manifest",
        trace_id=trace_id,
        detail={
            "source": "plan_evidence_registry",
            "manifest": normalized,
            "source_kind": normalized["source_kind"],
            "source_uri": normalized["source_uri"],
            "checksum": normalized["checksum"],
            "counts_toward_completion": normalized["counts_toward_completion"],
        },
    )
    learning_trace_id = _as_str(getattr(record, "trace_id", "") or trace_id)
    rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matches = [
        row
        for row in rows
        if row.detail.get("learning_kind") == "plan_evidence_manifest"
        and row.detail.get("checksum") == normalized["checksum"]
        and row.detail.get("source_kind") == normalized["source_kind"]
    ]
    if len(matches) != 1:
        raise PlanEvidenceRegistryError(
            [
                {
                    "reason": "evidence_manifest_query_mismatch",
                    "source_kind": normalized["source_kind"],
                    "checksum": normalized["checksum"],
                    "match_count": len(matches),
                }
            ]
        )
    return {
        "evidence_manifest_status": "registered",
        "learning_trace_id": learning_trace_id,
        "manifest": matches[0].detail["manifest"],
        "counts_toward_completion": matches[0].detail["counts_toward_completion"],
    }


def build_plan_evidence_summary(
    *,
    learning_service: Any,
    limit: int = 500,
) -> dict[str, Any]:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise PlanEvidenceRegistryError([{"reason": "learning_service_query_missing"}])
    rows = learning_service.query_overall_records(limit=limit)
    manifests: list[dict[str, Any]] = []
    completion_kinds: set[str] = set()
    generated_count = 0
    for row in rows:
        detail = dict(row.detail or {})
        if detail.get("learning_kind") != "plan_evidence_manifest":
            continue
        manifest = dict(detail.get("manifest") or {})
        item = {
            "learning_trace_id": row.trace_id,
            "source_kind": manifest.get("source_kind"),
            "source_uri": manifest.get("source_uri"),
            "environment": manifest.get("environment"),
            "checksum": manifest.get("checksum"),
            "evidence_count": manifest.get("evidence_count"),
            "counts_toward_completion": bool(manifest.get("counts_toward_completion")),
            "requirements": manifest.get("requirements"),
        }
        manifests.append(item)
        if item["counts_toward_completion"] and item["source_kind"] in COMPLETION_EVIDENCE_KINDS:
            completion_kinds.add(str(item["source_kind"]))
        if item["source_kind"] == "generated_verification":
            generated_count += 1
    missing_completion_kinds = sorted(COMPLETION_EVIDENCE_KINDS - completion_kinds)
    return {
        "evidence_summary_status": "complete" if not missing_completion_kinds else "incomplete",
        "manifest_count": len(manifests),
        "generated_manifest_count": generated_count,
        "completion_evidence_kinds": sorted(completion_kinds),
        "missing_completion_evidence_kinds": missing_completion_kinds,
        "completion_evidence_requirements": EVIDENCE_REQUIREMENTS,
        "manifests": manifests,
    }
