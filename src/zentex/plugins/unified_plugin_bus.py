from __future__ import annotations

"""Unified plugin bus for feature 43."""

from datetime import datetime, timezone
from enum import Enum
import re
import time
from typing import Any
from uuid import uuid4

import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus


UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PluginFamily(str, Enum):
    LLM = "llm"
    SENSORY = "sensory"
    SIMULATOR = "simulator"
    EXECUTION_DOMAIN = "execution_domain"
    IDENTITY_PACK = "identity_pack"
    COGNITIVE_TOOL = "cognitive_tool"


class UnifiedPluginAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: f"plugin-audit-{uuid4().hex[:12]}")
    plugin_id: str
    action: str
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class UnifiedPluginSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    plugin_id: str = Field(min_length=1)
    family: PluginFamily
    version: str = Field(min_length=1)
    feature_code: str = Field(min_length=1)
    health_probe_endpoint: str = Field(min_length=1)
    invocation_endpoint: str | None = None
    is_concurrency_safe: bool
    rollback_conditions: list[str] = Field(default_factory=list)
    revocation_reasons: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    read_only_isolation: bool = True
    execution_permissions: list[str] = Field(default_factory=list)
    max_response_ms: float = Field(default=5000.0, gt=0)
    max_memory_growth_units: float = Field(default=1000.0, ge=0)
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN

    @model_validator(mode="after")
    def validate_unified_contract(self) -> "UnifiedPluginSpec":
        if not self.rollback_conditions:
            raise ValueError("plugins must declare rollback_conditions")
        if not self.trigger_conditions:
            raise ValueError("plugins must declare trigger_conditions")
        if not self.read_only_isolation:
            raise ValueError("plugin runtime must use read_only_isolation")
        if self.execution_permissions and self.family == PluginFamily.COGNITIVE_TOOL:
            raise ValueError("cognitive tools cannot own execution permissions")
        if self.lifecycle_status in {PluginLifecycleStatus.DEGRADED, PluginLifecycleStatus.REVOKED} and not self.revocation_reasons:
            raise ValueError("degraded or revoked plugins must declare revocation_reasons")
        return self


class UnifiedPluginRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_id: str = Field(default_factory=lambda: f"plugin-reg-{uuid4().hex[:12]}")
    spec: UnifiedPluginSpec
    registered_at: datetime = Field(default_factory=_utc_now)
    audit_event_id: str


class PluginSelectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(default_factory=lambda: f"plugin-selection-{uuid4().hex[:12]}")
    selected_plugin_ids: list[str]
    blocked_reasons: dict[str, str]
    context: dict[str, Any]
    created_at: datetime = Field(default_factory=_utc_now)


class PluginInvocationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(default_factory=lambda: f"plugin-plan-{uuid4().hex[:12]}")
    selected_plugin_ids: list[str]
    serial_steps: list[str]
    parallel_groups: list[list[str]]
    read_only_isolation: bool
    created_at: datetime = Field(default_factory=_utc_now)


class PluginInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str = Field(default_factory=lambda: f"plugin-invoke-{uuid4().hex[:12]}")
    plugin_id: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    degraded_plugin: bool = False
    created_at: datetime = Field(default_factory=_utc_now)


class PluginBusDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"plugin-diagnostic-{uuid4().hex[:12]}")
    checks: dict[str, bool]
    metrics: dict[str, Any]
    failures: list[dict[str, Any]] = Field(default_factory=list)
    degraded_plugin_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class PluginFaultInjectionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"plugin-fault-{uuid4().hex[:12]}")
    cases: list[dict[str, Any]]
    passed: bool
    created_at: datetime = Field(default_factory=_utc_now)


class PluginCompletionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"plugin-completion-{uuid4().hex[:12]}")
    structure_complete: bool
    main_chain_complete: bool
    real_complete: bool
    missing_evidence: list[str] = Field(default_factory=list)
    diagnostic_report: PluginBusDiagnosticReport
    created_at: datetime = Field(default_factory=_utc_now)


class UnifiedPluginBus:
    """Feature 43 registry, selector, orchestrator, runtime, and governance."""

    required_families = {family.value for family in PluginFamily}
    allowed_lifecycle_transitions = {
        PluginLifecycleStatus.CANDIDATE.value: {PluginLifecycleStatus.SANDBOX_VERIFIED.value, PluginLifecycleStatus.DEGRADED.value, PluginLifecycleStatus.REVOKED.value},
        PluginLifecycleStatus.SANDBOX_VERIFIED.value: {PluginLifecycleStatus.ACTIVE.value, PluginLifecycleStatus.DEGRADED.value, PluginLifecycleStatus.REVOKED.value},
        PluginLifecycleStatus.ACTIVE.value: {PluginLifecycleStatus.DEGRADED.value, PluginLifecycleStatus.REVOKED.value, PluginLifecycleStatus.SANDBOX_VERIFIED.value},
        PluginLifecycleStatus.DEGRADED.value: {PluginLifecycleStatus.SANDBOX_VERIFIED.value, PluginLifecycleStatus.REVOKED.value},
        PluginLifecycleStatus.REVOKED.value: set(),
    }

    def __init__(self) -> None:
        self._plugins: dict[str, UnifiedPluginRegistration] = {}
        self._audit: list[UnifiedPluginAuditEvent] = []
        self._runtime_stats: dict[str, dict[str, Any]] = {}

    def register_plugin(self, spec: UnifiedPluginSpec) -> UnifiedPluginRegistration:
        if spec.plugin_id in self._plugins:
            raise ValueError(f"plugin already registered: {spec.plugin_id}")
        event = self._audit_event(spec.plugin_id, "plugin_registered", "candidate plugin registered", {
            "family": spec.family.value,
            "version": spec.version,
        })
        registration = UnifiedPluginRegistration(spec=spec, audit_event_id=event.event_id)
        self._plugins[spec.plugin_id] = registration
        return registration

    def get_plugin(self, plugin_id: str) -> UnifiedPluginRegistration:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(plugin_id) from exc

    def list_plugins(self, *, family: PluginFamily | None = None, status: PluginLifecycleStatus | None = None) -> list[UnifiedPluginRegistration]:
        rows = list(self._plugins.values())
        if family is not None:
            rows = [row for row in rows if row.spec.family == family]
        if status is not None:
            rows = [row for row in rows if row.spec.lifecycle_status == status]
        return rows

    def verify_sandbox(self, plugin_id: str) -> UnifiedPluginRegistration:
        registration = self.get_plugin(plugin_id)
        try:
            response = requests.get(registration.spec.health_probe_endpoint, timeout=5)
        except requests.RequestException as exc:
            updated = self._transition(plugin_id, PluginLifecycleStatus.DEGRADED, f"health probe transport failed: {exc}")
            raise RuntimeError(f"plugin health probe transport failed for {plugin_id}: {exc}; status={updated.spec.lifecycle_status.value}") from exc
        if response.status_code != 200:
            updated = self._transition(plugin_id, PluginLifecycleStatus.DEGRADED, f"health probe failed: {response.status_code}")
            raise RuntimeError(f"plugin health probe failed for {plugin_id}: {response.status_code}; status={updated.spec.lifecycle_status.value}")
        try:
            payload = response.json()
        except ValueError as exc:
            updated = self._transition(plugin_id, PluginLifecycleStatus.DEGRADED, f"health probe invalid json: {exc}")
            raise RuntimeError(f"plugin health probe invalid json for {plugin_id}: {exc}; status={updated.spec.lifecycle_status.value}") from exc
        if payload.get("status") != "healthy":
            updated = self._transition(plugin_id, PluginLifecycleStatus.DEGRADED, f"health probe unhealthy: {payload}")
            raise RuntimeError(f"plugin health probe unhealthy for {plugin_id}: {payload}; status={updated.spec.lifecycle_status.value}")
        return self._transition(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, "sandbox health probe passed")

    def promote_plugin(self, plugin_id: str, target_status: PluginLifecycleStatus, *, reason: str) -> UnifiedPluginRegistration:
        current = self.get_plugin(plugin_id).spec.lifecycle_status
        if target_status == PluginLifecycleStatus.ACTIVE and current != PluginLifecycleStatus.SANDBOX_VERIFIED:
            raise ValueError("plugins must pass sandbox_verified before active promotion")
        if target_status == PluginLifecycleStatus.SANDBOX_VERIFIED and current != PluginLifecycleStatus.CANDIDATE:
            raise ValueError("sandbox verification can only start from candidate")
        return self._transition(plugin_id, target_status, reason)

    def select_plugins(self, context: dict[str, Any]) -> PluginSelectionDecision:
        available = {str(item) for item in context.get("available_conditions", [])}
        blocked = {str(item) for item in context.get("blocked_conditions", [])}
        family_filter = {str(item) for item in context.get("families", [])}
        selected: list[str] = []
        blocked_reasons: dict[str, str] = {}
        for plugin_id, registration in self._plugins.items():
            spec = registration.spec
            if family_filter and spec.family.value not in family_filter:
                blocked_reasons[plugin_id] = f"family {spec.family.value} not requested"
                continue
            if spec.lifecycle_status != PluginLifecycleStatus.ACTIVE:
                blocked_reasons[plugin_id] = f"lifecycle_status={spec.lifecycle_status.value}"
                continue
            matched_block = [condition for condition in spec.do_not_use_when if condition in blocked]
            if matched_block:
                blocked_reasons[plugin_id] = f"do_not_use_when matched: {', '.join(matched_block)}"
                continue
            matched_trigger = [condition for condition in spec.trigger_conditions if condition in available]
            if not matched_trigger:
                blocked_reasons[plugin_id] = "no trigger condition matched"
                continue
            selected.append(plugin_id)
        self._audit_event("*", "plugins_selected", "plugin selector evaluated context", {
            "selected_plugin_ids": selected,
            "blocked_reasons": blocked_reasons,
        })
        return PluginSelectionDecision(selected_plugin_ids=selected, blocked_reasons=blocked_reasons, context=context)

    def build_invocation_plan(self, plugin_ids: list[str]) -> PluginInvocationPlan:
        serial_steps: list[str] = []
        parallel_group: list[str] = []
        for plugin_id in plugin_ids:
            spec = self.get_plugin(plugin_id).spec
            if spec.lifecycle_status != PluginLifecycleStatus.ACTIVE:
                raise ValueError(f"plugin {plugin_id} is not active")
            if spec.is_concurrency_safe:
                parallel_group.append(plugin_id)
            else:
                serial_steps.append(plugin_id)
        plan = PluginInvocationPlan(
            selected_plugin_ids=plugin_ids,
            serial_steps=serial_steps,
            parallel_groups=[parallel_group] if parallel_group else [],
            read_only_isolation=True,
        )
        self._audit_event("*", "plugin_plan_built", "plugin invocation plan built", plan.model_dump(mode="json"))
        return plan

    def invoke_plugin(self, plugin_id: str, payload: dict[str, Any]) -> PluginInvocationResult:
        registration = self.get_plugin(plugin_id)
        spec = registration.spec
        if spec.lifecycle_status != PluginLifecycleStatus.ACTIVE:
            raise ValueError(f"plugin {plugin_id} is not active")
        if not spec.invocation_endpoint:
            raise ValueError(f"plugin {plugin_id} has no invocation_endpoint")
        request_payload = {"readonly": True, "input": payload}
        started = time.perf_counter()
        try:
            response = requests.post(spec.invocation_endpoint, json=request_payload, timeout=5)
        except requests.RequestException as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=f"transport_error: {exc}")
            self.degrade_plugin(plugin_id, reason=f"invocation transport failed: {exc}")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=f"transport_error: {exc}",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation transport failed and plugin degraded", result.model_dump(mode="json"))
            return result
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        if response.status_code != 200:
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=f"HTTP {response.status_code}")
            self.degrade_plugin(plugin_id, reason=f"invocation failed: {response.status_code}")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=f"HTTP {response.status_code}: {response.text}",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation failed and plugin degraded", result.model_dump(mode="json"))
            return result
        try:
            output = response.json()
        except ValueError as exc:
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=f"invalid_json: {exc}")
            self.degrade_plugin(plugin_id, reason=f"invocation returned invalid json: {exc}")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=f"invalid_json: {exc}",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation returned invalid json and plugin degraded", result.model_dump(mode="json"))
            return result
        if not isinstance(output, dict):
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error="output_not_object")
            self.degrade_plugin(plugin_id, reason="invocation returned non-object output")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error="bad_output_structure: output must be a JSON object",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation returned non-object output and plugin degraded", result.model_dump(mode="json"))
            return result
        output_errors = self._validate_output_contract(spec, output)
        if output_errors:
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=f"bad_output_structure: {output_errors}")
            self.degrade_plugin(plugin_id, reason=f"invocation output schema violation: {output_errors}")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=f"bad_output_structure: {'; '.join(output_errors)}",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation output failed schema validation and plugin degraded", result.model_dump(mode="json"))
            return result
        if elapsed_ms > spec.max_response_ms:
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=f"long_tail_latency_ms={elapsed_ms}")
            self.degrade_plugin(plugin_id, reason=f"invocation latency exceeded {spec.max_response_ms}ms: {elapsed_ms}ms")
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=f"long_tail_timeout: elapsed_ms={elapsed_ms}, max_response_ms={spec.max_response_ms}",
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin invocation exceeded latency budget and plugin degraded", result.model_dump(mode="json"))
            return result
        leak_error = self._detect_resource_leak(spec, output)
        if leak_error is not None:
            self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=False, error=leak_error)
            self.degrade_plugin(plugin_id, reason=leak_error)
            result = PluginInvocationResult(
                plugin_id=plugin_id,
                success=False,
                error=leak_error,
                degraded_plugin=True,
            )
            self._audit_event(plugin_id, "plugin_invocation_failed", "plugin resource leak trend detected and plugin degraded", result.model_dump(mode="json"))
            return result
        self._record_runtime_sample(plugin_id, elapsed_ms=elapsed_ms, success=True)
        result = PluginInvocationResult(plugin_id=plugin_id, success=True, output=output)
        self._audit_event(plugin_id, "plugin_invoked", "plugin invoked in read-only isolation", result.model_dump(mode="json"))
        return result

    def degrade_plugin(self, plugin_id: str, *, reason: str) -> UnifiedPluginRegistration:
        return self._transition(plugin_id, PluginLifecycleStatus.DEGRADED, reason, revocation_reason=reason)

    def revoke_plugin(self, plugin_id: str, *, reason: str) -> UnifiedPluginRegistration:
        return self._transition(plugin_id, PluginLifecycleStatus.REVOKED, reason, revocation_reason=reason)

    def rollback_plugin(self, plugin_id: str, *, reason: str) -> UnifiedPluginRegistration:
        current = self.get_plugin(plugin_id).spec.lifecycle_status
        if current not in {PluginLifecycleStatus.ACTIVE, PluginLifecycleStatus.DEGRADED}:
            raise ValueError("rollback requires active or degraded plugin state")
        return self._transition(
            plugin_id,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
            reason,
            action="plugin_rollback",
        )

    def diagnose_acceptance_closure(self, *, run_health_probes: bool = True) -> PluginBusDiagnosticReport:
        failures: list[dict[str, Any]] = []
        degraded_plugin_ids: list[str] = []
        metrics: dict[str, Any] = {
            "plugin_count": len(self._plugins),
            "audit_event_count": len(self._audit),
            "health_probe_results": {},
            "lifecycle_states": {},
            "runtime_stats": self._runtime_stats,
        }

        for plugin_id, registration in list(self._plugins.items()):
            spec = registration.spec
            metrics["lifecycle_states"][plugin_id] = spec.lifecycle_status.value
            self._validate_manifest_contract(spec, failures)
            self._validate_version_contract(spec, failures)
            self._validate_permission_boundary(spec, failures)

            if run_health_probes and spec.lifecycle_status != PluginLifecycleStatus.REVOKED:
                started = time.perf_counter()
                try:
                    response = requests.get(spec.health_probe_endpoint, timeout=5)
                    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                    result: dict[str, Any] = {
                        "status_code": response.status_code,
                        "elapsed_ms": elapsed_ms,
                    }
                    if response.status_code != 200:
                        result["healthy"] = False
                        failures.append({"plugin_id": plugin_id, "check": "health_probe", "reason": f"http_{response.status_code}"})
                        degraded_plugin_ids.append(plugin_id)
                        self.degrade_plugin(plugin_id, reason=f"diagnostic health_probe failed: {response.status_code}")
                    else:
                        payload = response.json()
                        result["payload"] = payload
                        result["healthy"] = payload.get("status") == "healthy"
                        if not result["healthy"]:
                            failures.append({"plugin_id": plugin_id, "check": "health_probe", "reason": "unhealthy_payload", "payload": payload})
                            degraded_plugin_ids.append(plugin_id)
                            self.degrade_plugin(plugin_id, reason=f"diagnostic health_probe unhealthy: {payload}")
                    metrics["health_probe_results"][plugin_id] = result
                except Exception as exc:
                    failures.append({"plugin_id": plugin_id, "check": "health_probe", "reason": str(exc)})
                    degraded_plugin_ids.append(plugin_id)
                    self.degrade_plugin(plugin_id, reason=f"diagnostic health_probe exception: {exc}")

            if not any(event.event_id == registration.audit_event_id for event in self._audit):
                failures.append({"plugin_id": plugin_id, "check": "audit_chain", "reason": "registration_audit_event_missing"})

        self._validate_lifecycle_audit_transitions(failures)
        actions = {event.action for event in self._audit}
        checks = {
            "manifest_validation": not any(item["check"] == "manifest" for item in failures),
            "health_probe": not any(item["check"] == "health_probe" for item in failures),
            "state_transition_consistency": not any(item["check"] == "state_transition" for item in failures),
            "version_compatibility": not any(item["check"] == "version" for item in failures),
            "permission_boundary": not any(item["check"] == "permission_boundary" for item in failures),
            "audit_chain_integrity": not any(item["check"] == "audit_chain" for item in failures),
            "runtime_metrics_recorded": any(stats.get("invocation_count", 0) > 0 for stats in self._runtime_stats.values()),
            "failure_path_evidence": bool(actions & {"plugin_invocation_failed", "plugin_degraded", "plugin_revoked", "plugin_rollback"}),
        }
        report = PluginBusDiagnosticReport(
            checks=checks,
            metrics=metrics,
            failures=failures,
            degraded_plugin_ids=sorted(set(degraded_plugin_ids)),
        )
        self._audit_event("*", "plugin_diagnostic_reported", "plugin acceptance closure diagnostics executed", report.model_dump(mode="json"))
        return report

    def run_fault_injection_matrix(self) -> PluginFaultInjectionReport:
        cases: list[dict[str, Any]] = []

        def record(name: str, passed: bool, details: dict[str, Any]) -> None:
            cases.append({"name": name, "passed": passed, "details": details})

        try:
            UnifiedPluginSpec(
                plugin_id="fault-missing-rollback",
                family=PluginFamily.COGNITIVE_TOOL,
                version="1.0.0",
                feature_code="fault",
                health_probe_endpoint="http://127.0.0.1/health",
                is_concurrency_safe=True,
                rollback_conditions=[],
                trigger_conditions=["runtime_ready"],
                read_only_isolation=True,
            )
            record("manifest_missing_required_evidence", False, {"error": "invalid manifest accepted"})
        except ValueError as exc:
            record("manifest_missing_required_evidence", True, {"error": str(exc)})

        version_failures: list[dict[str, Any]] = []
        version_conflict_spec = self._fault_spec(
            "version-conflict",
            base_spec=None,
            version="v1",
            health_probe_endpoint="http://127.0.0.1/health",
            invocation_endpoint="http://127.0.0.1/invoke/success",
        )
        self._validate_version_contract(version_conflict_spec, version_failures)
        record(
            "version_conflict_rejected",
            any(item.get("check") == "version" for item in version_failures),
            {"failures": version_failures},
        )

        try:
            UnifiedPluginSpec(
                plugin_id="fault-permission-overreach",
                family=PluginFamily.COGNITIVE_TOOL,
                version="1.0.0",
                feature_code="fault",
                health_probe_endpoint="http://127.0.0.1/health",
                is_concurrency_safe=True,
                rollback_conditions=["rollback"],
                trigger_conditions=["runtime_ready"],
                read_only_isolation=True,
                execution_permissions=["write_files"],
            )
            record("permission_overreach", False, {"error": "overreaching cognitive tool accepted"})
        except ValueError as exc:
            record("permission_overreach", True, {"error": str(exc)})

        active_ids = [
            plugin_id
            for plugin_id, registration in self._plugins.items()
            if registration.spec.lifecycle_status == PluginLifecycleStatus.ACTIVE
        ]
        if active_ids:
            plugin_id = active_ids[0]
            base_spec = self.get_plugin(plugin_id).spec
            self._run_clone_invocation_fault(
                record,
                base_spec,
                "load_failure_degrades_candidate",
                health_probe_endpoint="http://127.0.0.1:1/zentex-fault-health",
                invocation_endpoint=base_spec.invocation_endpoint,
                expect_verify_failure=True,
            )
            self._run_clone_invocation_fault(
                record,
                base_spec,
                "false_health_detected_by_real_invocation",
                invocation_endpoint=self._sibling_invocation_endpoint(base_spec.invocation_endpoint, "fail"),
                expected_error="HTTP 500",
            )
            self._run_clone_invocation_fault(
                record,
                base_spec,
                "bad_output_structure_rejected",
                invocation_endpoint=self._sibling_invocation_endpoint(base_spec.invocation_endpoint, "bad-structure"),
                output_schema={"type": "object", "required": ["required_result"]},
                expected_error="bad_output_structure",
            )
            self._run_clone_invocation_fault(
                record,
                base_spec,
                "long_tail_timeout_degrades_plugin",
                invocation_endpoint=self._sibling_invocation_endpoint(base_spec.invocation_endpoint, "slow"),
                max_response_ms=50.0,
                expected_error="long_tail_timeout",
            )
            self._run_clone_invocation_fault(
                record,
                base_spec,
                "resource_leak_trend_degrades_plugin",
                invocation_endpoint=self._sibling_invocation_endpoint(base_spec.invocation_endpoint, "leak"),
                max_memory_growth_units=10.0,
                expected_error="resource_leak",
            )
            original_endpoint = self.get_plugin(plugin_id).spec.invocation_endpoint
            broken_spec = self.get_plugin(plugin_id).spec.model_copy(update={"invocation_endpoint": "http://127.0.0.1:1/zentex-fault"})
            original = self.get_plugin(plugin_id)
            self._plugins[plugin_id] = original.model_copy(update={"spec": broken_spec})
            result = self.invoke_plugin(plugin_id, {"fault": "timeout_or_connection_refused"})
            record(
                "runtime_invocation_failure_degrades_plugin",
                result.success is False and result.degraded_plugin is True and self.get_plugin(plugin_id).spec.lifecycle_status == PluginLifecycleStatus.DEGRADED,
                {"plugin_id": plugin_id, "error": result.error, "original_endpoint": original_endpoint},
            )
        else:
            record("runtime_invocation_failure_degrades_plugin", False, {"error": "no active plugin available"})

        passed = all(item["passed"] for item in cases)
        report = PluginFaultInjectionReport(cases=cases, passed=passed)
        self._audit_event("*", "plugin_fault_matrix_executed", "plugin fault injection matrix executed", report.model_dump(mode="json"))
        return report

    def completion_report(self, *, run_health_probes: bool = True) -> PluginCompletionReport:
        diagnostic = self.diagnose_acceptance_closure(run_health_probes=run_health_probes)
        actions = {event.action for event in self._audit}
        missing: list[str] = []
        required_structure = {
            "manifest_validation",
            "state_transition_consistency",
            "version_compatibility",
            "permission_boundary",
            "audit_chain_integrity",
        }
        for check in sorted(required_structure):
            if not diagnostic.checks.get(check, False):
                missing.append(check)
        structure_complete = not missing and bool(self._plugins)

        main_chain_requirements = {
            "plugin_registered",
            "plugin_sandbox_verified",
            "plugin_active",
            "plugins_selected",
            "plugin_plan_built",
            "plugin_invoked",
        }
        for action in sorted(main_chain_requirements - actions):
            missing.append(action)
        main_chain_complete = not (main_chain_requirements - actions)

        real_requirements = {
            "plugin_invocation_failed",
            "plugin_degraded",
            "plugin_rollback",
            "plugin_revoked",
        }
        for action in sorted(real_requirements - actions):
            missing.append(action)
        real_complete = structure_complete and main_chain_complete and not (real_requirements - actions)

        report = PluginCompletionReport(
            structure_complete=structure_complete,
            main_chain_complete=main_chain_complete,
            real_complete=real_complete,
            missing_evidence=sorted(set(missing)),
            diagnostic_report=diagnostic,
        )
        self._audit_event("*", "plugin_completion_reported", "plugin acceptance completion report built", report.model_dump(mode="json"))
        return report

    def family_coverage(self) -> dict[str, Any]:
        observed = {row.spec.family.value for row in self._plugins.values()}
        missing = sorted(self.required_families - observed)
        return {
            "required_families": sorted(self.required_families),
            "observed_families": sorted(observed),
            "missing_families": missing,
            "complete": not missing,
        }

    def list_audit_events(self) -> list[UnifiedPluginAuditEvent]:
        return list(self._audit)

    def _transition(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        reason: str,
        *,
        revocation_reason: str | None = None,
        action: str | None = None,
    ) -> UnifiedPluginRegistration:
        registration = self.get_plugin(plugin_id)
        spec = registration.spec
        revocation_reasons = list(spec.revocation_reasons)
        if revocation_reason and revocation_reason not in revocation_reasons:
            revocation_reasons.append(revocation_reason)
        health_status = spec.health_status
        if target_status in {PluginLifecycleStatus.CANDIDATE, PluginLifecycleStatus.SANDBOX_VERIFIED, PluginLifecycleStatus.ACTIVE}:
            health_status = PluginHealthStatus.HEALTHY
        if target_status == PluginLifecycleStatus.DEGRADED:
            health_status = PluginHealthStatus.DEGRADED
        if target_status == PluginLifecycleStatus.REVOKED:
            health_status = PluginHealthStatus.UNHEALTHY
        updated_spec = spec.model_copy(
            update={
                "lifecycle_status": target_status,
                "health_status": health_status,
                "revocation_reasons": revocation_reasons,
            }
        )
        event = self._audit_event(plugin_id, action or f"plugin_{target_status.value}", reason, {
            "previous_status": spec.lifecycle_status.value,
            "current_status": target_status.value,
            "health_status": health_status.value,
        })
        updated = registration.model_copy(update={"spec": updated_spec, "audit_event_id": event.event_id})
        self._plugins[plugin_id] = updated
        return updated

    def _audit_event(self, plugin_id: str, action: str, reason: str, details: dict[str, Any]) -> UnifiedPluginAuditEvent:
        event = UnifiedPluginAuditEvent(plugin_id=plugin_id, action=action, reason=reason, details=details)
        self._audit.append(event)
        return event

    def _record_runtime_sample(self, plugin_id: str, *, elapsed_ms: float, success: bool, error: str | None = None) -> None:
        stats = self._runtime_stats.setdefault(
            plugin_id,
            {
                "invocation_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "latency_samples_ms": [],
                "max_latency_ms": 0.0,
                "last_error": None,
            },
        )
        stats["invocation_count"] += 1
        stats["latency_samples_ms"].append(elapsed_ms)
        stats["max_latency_ms"] = max(float(stats["max_latency_ms"]), elapsed_ms)
        if success:
            stats["success_count"] += 1
            stats["last_error"] = None
        else:
            stats["failure_count"] += 1
            stats["last_error"] = error
        stats["failure_rate"] = stats["failure_count"] / stats["invocation_count"]

    def _validate_output_contract(self, spec: UnifiedPluginSpec, output: dict[str, Any]) -> list[str]:
        schema = spec.output_schema or {}
        errors: list[str] = []
        if schema.get("type") == "object" and not isinstance(output, dict):
            errors.append("output_schema.type=object requires JSON object")
        required = schema.get("required", [])
        if isinstance(required, list):
            for field_name in required:
                if isinstance(field_name, str) and field_name not in output:
                    errors.append(f"missing_required_output_field:{field_name}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            expected_types = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "object": dict,
                "array": list,
            }
            for field_name, field_schema in properties.items():
                if field_name not in output or not isinstance(field_schema, dict):
                    continue
                expected = field_schema.get("type")
                expected_type = expected_types.get(expected)
                if expected_type is not None and not isinstance(output[field_name], expected_type):
                    errors.append(f"output_field_type_mismatch:{field_name}:{expected}")
        return errors

    def _detect_resource_leak(self, spec: UnifiedPluginSpec, output: dict[str, Any]) -> str | None:
        usage = output.get("resource_usage")
        if not isinstance(usage, dict):
            return None
        start = usage.get("memory_units_start")
        end = usage.get("memory_units_end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return "resource_leak_payload_invalid: memory_units_start and memory_units_end must be numeric"
        growth = float(end) - float(start)
        if growth > spec.max_memory_growth_units:
            return f"resource_leak_trend: growth_units={growth}, max_memory_growth_units={spec.max_memory_growth_units}"
        return None

    def _fault_spec(
        self,
        label: str,
        *,
        base_spec: UnifiedPluginSpec | None,
        health_probe_endpoint: str,
        invocation_endpoint: str | None,
        version: str | None = None,
        output_schema: dict[str, Any] | None = None,
        max_response_ms: float | None = None,
        max_memory_growth_units: float | None = None,
    ) -> UnifiedPluginSpec:
        if base_spec is None:
            return UnifiedPluginSpec(
                plugin_id=f"fault-{label}-{uuid4().hex[:8]}",
                family=PluginFamily.COGNITIVE_TOOL,
                version=version or "1.0.0",
                feature_code="fault",
                health_probe_endpoint=health_probe_endpoint,
                invocation_endpoint=invocation_endpoint,
                is_concurrency_safe=True,
                rollback_conditions=["fault_rollback"],
                trigger_conditions=["runtime_ready"],
                input_schema={"type": "object"},
                output_schema=output_schema or {"type": "object"},
                read_only_isolation=True,
                max_response_ms=max_response_ms or 5000.0,
                max_memory_growth_units=max_memory_growth_units if max_memory_growth_units is not None else 1000.0,
            )
        return base_spec.model_copy(
            update={
                "plugin_id": f"fault-{label}-{uuid4().hex[:8]}",
                "version": version or base_spec.version,
                "health_probe_endpoint": health_probe_endpoint,
                "invocation_endpoint": invocation_endpoint,
                "output_schema": output_schema or base_spec.output_schema,
                "max_response_ms": max_response_ms or base_spec.max_response_ms,
                "max_memory_growth_units": max_memory_growth_units if max_memory_growth_units is not None else base_spec.max_memory_growth_units,
                "lifecycle_status": PluginLifecycleStatus.CANDIDATE,
                "health_status": PluginHealthStatus.UNKNOWN,
                "revocation_reasons": [],
            }
        )

    def _run_clone_invocation_fault(
        self,
        record: Any,
        base_spec: UnifiedPluginSpec,
        name: str,
        *,
        invocation_endpoint: str | None,
        health_probe_endpoint: str | None = None,
        output_schema: dict[str, Any] | None = None,
        max_response_ms: float | None = None,
        max_memory_growth_units: float | None = None,
        expected_error: str | None = None,
        expect_verify_failure: bool = False,
    ) -> None:
        spec = self._fault_spec(
            name,
            base_spec=base_spec,
            health_probe_endpoint=health_probe_endpoint or base_spec.health_probe_endpoint,
            invocation_endpoint=invocation_endpoint,
            output_schema=output_schema,
            max_response_ms=max_response_ms,
            max_memory_growth_units=max_memory_growth_units,
        )
        self.register_plugin(spec)
        if expect_verify_failure:
            try:
                self.verify_sandbox(spec.plugin_id)
            except RuntimeError as exc:
                record(
                    name,
                    self.get_plugin(spec.plugin_id).spec.lifecycle_status == PluginLifecycleStatus.DEGRADED,
                    {"plugin_id": spec.plugin_id, "error": str(exc)},
                )
                return
            record(name, False, {"plugin_id": spec.plugin_id, "error": "sandbox verification unexpectedly passed"})
            return
        try:
            self.verify_sandbox(spec.plugin_id)
            self.promote_plugin(spec.plugin_id, PluginLifecycleStatus.ACTIVE, reason=f"fault injection activation: {name}")
            result = self.invoke_plugin(spec.plugin_id, {"fault": name})
            passed = (
                result.success is False
                and result.degraded_plugin is True
                and self.get_plugin(spec.plugin_id).spec.lifecycle_status == PluginLifecycleStatus.DEGRADED
                and (expected_error is None or expected_error in str(result.error))
            )
            record(name, passed, {"plugin_id": spec.plugin_id, "error": result.error})
        except Exception as exc:
            record(name, False, {"plugin_id": spec.plugin_id, "error": str(exc)})

    def _sibling_invocation_endpoint(self, endpoint: str | None, leaf: str) -> str | None:
        if not endpoint:
            return None
        prefix, separator, _ = endpoint.rpartition("/")
        if not separator:
            return endpoint
        return f"{prefix}/{leaf}"

    def _validate_manifest_contract(self, spec: UnifiedPluginSpec, failures: list[dict[str, Any]]) -> None:
        required_fields = {
            "plugin_id": spec.plugin_id,
            "version": spec.version,
            "feature_code": spec.feature_code,
            "health_probe_endpoint": spec.health_probe_endpoint,
            "rollback_conditions": spec.rollback_conditions,
            "trigger_conditions": spec.trigger_conditions,
        }
        for field_name, value in required_fields.items():
            if value in ("", [], None):
                failures.append({"plugin_id": spec.plugin_id, "check": "manifest", "field": field_name, "reason": "missing_or_empty"})
        if not isinstance(spec.input_schema, dict) or not isinstance(spec.output_schema, dict):
            failures.append({"plugin_id": spec.plugin_id, "check": "manifest", "reason": "schema_must_be_object"})

    def _validate_version_contract(self, spec: UnifiedPluginSpec, failures: list[dict[str, Any]]) -> None:
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?", spec.version):
            failures.append({"plugin_id": spec.plugin_id, "check": "version", "version": spec.version, "reason": "non_semver"})

    def _validate_permission_boundary(self, spec: UnifiedPluginSpec, failures: list[dict[str, Any]]) -> None:
        if not spec.read_only_isolation:
            failures.append({"plugin_id": spec.plugin_id, "check": "permission_boundary", "reason": "read_only_isolation_disabled"})
        if spec.family == PluginFamily.COGNITIVE_TOOL and spec.execution_permissions:
            failures.append({"plugin_id": spec.plugin_id, "check": "permission_boundary", "reason": "cognitive_tool_execution_permissions"})

    def _validate_lifecycle_audit_transitions(self, failures: list[dict[str, Any]]) -> None:
        for event in self._audit:
            previous_status = event.details.get("previous_status")
            current_status = event.details.get("current_status")
            if not previous_status or not current_status:
                continue
            allowed = self.allowed_lifecycle_transitions.get(str(previous_status), set())
            if str(current_status) not in allowed and previous_status != current_status:
                failures.append(
                    {
                        "plugin_id": event.plugin_id,
                        "check": "state_transition",
                        "previous_status": previous_status,
                        "current_status": current_status,
                        "event_id": event.event_id,
                    }
                )
