from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import time

import requests
from fastapi import FastAPI, HTTPException

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.plugins.contracts import PluginLifecycleStatus
from zentex.plugins.unified_plugin_bus import PluginFamily, UnifiedPluginBus, UnifiedPluginSpec


@contextmanager
def _plugin_runtime_server() -> Iterator[str]:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/invoke/success")
    def invoke_success(payload: dict) -> dict:
        return {
            "readonly_received": payload["readonly"],
            "echo": payload["input"],
            "side_effect_committed": False,
        }

    @app.post("/invoke/fail")
    def invoke_fail(payload: dict) -> dict[str, str]:
        raise HTTPException(status_code=500, detail={"error": "real plugin failure"})

    @app.post("/invoke/bad-structure")
    def invoke_bad_structure(payload: dict) -> dict[str, str]:
        return {"unexpected_field": "schema violation"}

    @app.post("/invoke/slow")
    def invoke_slow(payload: dict) -> dict:
        time.sleep(0.12)
        return {
            "readonly_received": payload["readonly"],
            "echo": payload["input"],
            "side_effect_committed": False,
        }

    @app.post("/invoke/leak")
    def invoke_leak(payload: dict) -> dict:
        return {
            "readonly_received": payload["readonly"],
            "echo": payload["input"],
            "side_effect_committed": False,
            "resource_usage": {
                "memory_units_start": 100,
                "memory_units_end": 140,
            },
        }

    with live_http_server(app) as base_url:
        yield base_url


def _spec(
    suffix: str,
    family: PluginFamily,
    base_url: str,
    *,
    plugin_id: str | None = None,
    concurrency_safe: bool = True,
    blocked: bool = False,
    failing: bool = False,
) -> UnifiedPluginSpec:
    return UnifiedPluginSpec(
        plugin_id=plugin_id or f"{family.value}-{suffix}",
        family=family,
        version="1.0.0",
        feature_code=f"feature-{family.value}",
        health_probe_endpoint=f"{base_url}/health",
        invocation_endpoint=f"{base_url}/invoke/{'fail' if failing else 'success'}",
        is_concurrency_safe=concurrency_safe,
        rollback_conditions=["rollback_on_failure"],
        revocation_reasons=[],
        trigger_conditions=["runtime_ready"],
        do_not_use_when=["blocked_by_policy"] if blocked else [],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        read_only_isolation=True,
        execution_permissions=[],
    )


def _activate(bus: UnifiedPluginBus, spec: UnifiedPluginSpec) -> None:
    bus.register_plugin(spec)
    verified = bus.verify_sandbox(spec.plugin_id)
    assert verified.spec.lifecycle_status == PluginLifecycleStatus.SANDBOX_VERIFIED
    active = bus.promote_plugin(spec.plugin_id, PluginLifecycleStatus.ACTIVE, reason="ci activation")
    assert active.spec.lifecycle_status == PluginLifecycleStatus.ACTIVE


def test_unified_plugin_bus_business_covers_six_families_selection_runtime_and_governance() -> None:
    suffix = unique_suffix()
    bus = UnifiedPluginBus()

    with _plugin_runtime_server() as base_url:
        specs = [
            _spec(suffix, PluginFamily.LLM, base_url),
            _spec(suffix, PluginFamily.SENSORY, base_url),
            _spec(suffix, PluginFamily.SIMULATOR, base_url),
            _spec(suffix, PluginFamily.EXECUTION_DOMAIN, base_url, concurrency_safe=False),
            _spec(suffix, PluginFamily.IDENTITY_PACK, base_url),
            _spec(suffix, PluginFamily.COGNITIVE_TOOL, base_url),
        ]
        for spec in specs:
            _activate(bus, spec)

        coverage = bus.family_coverage()
        assert coverage["complete"] is True
        assert coverage["observed_families"] == coverage["required_families"]
        assert len(bus.list_plugins(status=PluginLifecycleStatus.ACTIVE)) == 6

        blocked_spec = _spec(suffix, PluginFamily.COGNITIVE_TOOL, base_url, plugin_id=f"blocked-{suffix}", blocked=True)
        _activate(bus, blocked_spec)
        decision = bus.select_plugins(
            {
                "available_conditions": ["runtime_ready"],
                "blocked_conditions": ["blocked_by_policy"],
                "families": ["cognitive_tool", "execution_domain"],
            }
        )
        assert specs[3].plugin_id in decision.selected_plugin_ids
        assert specs[5].plugin_id in decision.selected_plugin_ids
        assert blocked_spec.plugin_id in decision.blocked_reasons
        assert "do_not_use_when" in decision.blocked_reasons[blocked_spec.plugin_id]

        plan = bus.build_invocation_plan([specs[3].plugin_id, specs[5].plugin_id])
        assert plan.serial_steps == [specs[3].plugin_id]
        assert plan.parallel_groups == [[specs[5].plugin_id]]
        assert plan.read_only_isolation is True

        result = bus.invoke_plugin(specs[5].plugin_id, {"task": f"read-only-{suffix}"})
        assert result.success is True
        assert result.output["readonly_received"] is True
        assert result.output["side_effect_committed"] is False
        assert result.output["echo"]["task"] == f"read-only-{suffix}"
        runtime_diagnostics = bus.diagnose_acceptance_closure(run_health_probes=False)
        assert runtime_diagnostics.checks["runtime_metrics_recorded"] is True
        assert runtime_diagnostics.metrics["runtime_stats"][specs[5].plugin_id]["invocation_count"] == 1
        assert runtime_diagnostics.metrics["runtime_stats"][specs[5].plugin_id]["failure_count"] == 0

        failing_spec = _spec(suffix, PluginFamily.COGNITIVE_TOOL, base_url, plugin_id=f"failing-{suffix}", failing=True)
        _activate(bus, failing_spec)
        failure = bus.invoke_plugin(failing_spec.plugin_id, {"task": "must degrade visibly"})
        assert failure.success is False
        assert failure.degraded_plugin is True
        assert "HTTP 500" in str(failure.error)
        assert bus.get_plugin(failing_spec.plugin_id).spec.lifecycle_status == PluginLifecycleStatus.DEGRADED
        assert bus.get_plugin(failing_spec.plugin_id).spec.health_status.value == "degraded"
        rollback = bus.rollback_plugin(failing_spec.plugin_id, reason="ci rollback after injected failure")
        assert rollback.spec.lifecycle_status == PluginLifecycleStatus.SANDBOX_VERIFIED
        assert bus.get_plugin(failing_spec.plugin_id).spec.lifecycle_status == PluginLifecycleStatus.SANDBOX_VERIFIED

        revoked = bus.revoke_plugin(specs[0].plugin_id, reason="ci revoke")
        assert revoked.spec.lifecycle_status == PluginLifecycleStatus.REVOKED
        assert specs[0].plugin_id not in bus.select_plugins({"available_conditions": ["runtime_ready"]}).selected_plugin_ids
        diagnostics = bus.diagnose_acceptance_closure(run_health_probes=False)
        assert diagnostics.checks["manifest_validation"] is True
        assert diagnostics.checks["state_transition_consistency"] is True
        assert diagnostics.checks["audit_chain_integrity"] is True
        assert diagnostics.checks["runtime_metrics_recorded"] is True
        completion = bus.completion_report(run_health_probes=False)
        assert completion.structure_complete is True
        assert completion.main_chain_complete is True
        assert completion.real_complete is True
        assert completion.missing_evidence == []
        audit_actions = {event.action for event in bus.list_audit_events()}
        assert {
            "plugin_registered",
            "plugin_active",
            "plugins_selected",
            "plugin_invoked",
            "plugin_invocation_failed",
            "plugin_rollback",
            "plugin_revoked",
            "plugin_completion_reported",
        } <= audit_actions


def test_unified_plugin_bus_api_uses_requests_and_read_after_write_checks(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.unified_plugin_bus = UnifiedPluginBus()

    with _plugin_runtime_server() as plugin_base_url:
        with live_http_server(acceptance_app) as base_url:
            plugin_payload = _spec(
                suffix,
                PluginFamily.COGNITIVE_TOOL,
                plugin_base_url,
                plugin_id=f"api-plugin-{suffix}",
            ).model_dump(mode="json")
            register = requests.post(f"{base_url}/api/web/plugin-bus/g43/plugins", json=plugin_payload, timeout=10)
            assert register.status_code == 200, register.text
            assert register.json()["spec"]["lifecycle_status"] == "candidate"

            get_candidate = requests.get(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}",
                timeout=10,
            )
            assert get_candidate.status_code == 200
            assert get_candidate.json()["spec"]["plugin_id"] == plugin_payload["plugin_id"]

            verify = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}/sandbox-verify",
                timeout=10,
            )
            assert verify.status_code == 200, verify.text
            assert verify.json()["spec"]["lifecycle_status"] == "sandbox_verified"

            promote = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}/promote",
                json={"target_status": "active", "reason": "api activation"},
                timeout=10,
            )
            assert promote.status_code == 200, promote.text
            assert promote.json()["spec"]["lifecycle_status"] == "active"

            active_query = requests.get(
                f"{base_url}/api/web/plugin-bus/g43/plugins",
                params={"status": "active"},
                timeout=10,
            )
            assert [row["spec"]["plugin_id"] for row in active_query.json()] == [plugin_payload["plugin_id"]]

            selection = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/selection",
                json={"context": {"available_conditions": ["runtime_ready"], "families": ["cognitive_tool"]}},
                timeout=10,
            )
            assert selection.status_code == 200
            assert selection.json()["selected_plugin_ids"] == [plugin_payload["plugin_id"]]

            plan = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plans",
                json={"plugin_ids": [plugin_payload["plugin_id"]]},
                timeout=10,
            )
            assert plan.status_code == 200
            assert plan.json()["parallel_groups"] == [[plugin_payload["plugin_id"]]]
            assert plan.json()["read_only_isolation"] is True

            invoke = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}/invoke",
                json={"payload": {"api_task": suffix}},
                timeout=10,
            )
            assert invoke.status_code == 200, invoke.text
            invoke_payload = invoke.json()
            assert invoke_payload["success"] is True
            assert invoke_payload["output"]["readonly_received"] is True
            assert invoke_payload["output"]["side_effect_committed"] is False
            assert invoke_payload["output"]["echo"]["api_task"] == suffix

            diagnostics = requests.get(
                f"{base_url}/api/web/plugin-bus/g43/closure/diagnostics",
                params={"run_health_probes": "false"},
                timeout=10,
            )
            assert diagnostics.status_code == 200, diagnostics.text
            diagnostics_payload = diagnostics.json()
            assert diagnostics_payload["checks"]["manifest_validation"] is True
            assert diagnostics_payload["checks"]["state_transition_consistency"] is True
            assert diagnostics_payload["checks"]["permission_boundary"] is True
            assert diagnostics_payload["metrics"]["plugin_count"] == 1

            fault = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/closure/fault-injection",
                timeout=10,
            )
            assert fault.status_code == 200, fault.text
            fault_payload = fault.json()
            assert fault_payload["passed"] is True
            fault_cases = {case["name"]: case for case in fault_payload["cases"]}
            assert set(fault_cases) >= {
                "manifest_missing_required_evidence",
                "version_conflict_rejected",
                "permission_overreach",
                "load_failure_degrades_candidate",
                "false_health_detected_by_real_invocation",
                "bad_output_structure_rejected",
                "long_tail_timeout_degrades_plugin",
                "resource_leak_trend_degrades_plugin",
                "runtime_invocation_failure_degrades_plugin",
            }
            assert fault_cases["bad_output_structure_rejected"]["details"]["error"].startswith("bad_output_structure")
            assert "long_tail_timeout" in fault_cases["long_tail_timeout_degrades_plugin"]["details"]["error"]
            assert "resource_leak_trend" in fault_cases["resource_leak_trend_degrades_plugin"]["details"]["error"]
            degraded_query = requests.get(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}",
                timeout=10,
            )
            assert degraded_query.json()["spec"]["lifecycle_status"] == "degraded"

            rollback = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}/rollback",
                json={"reason": "api rollback after injected failure"},
                timeout=10,
            )
            assert rollback.status_code == 200, rollback.text
            assert rollback.json()["spec"]["lifecycle_status"] == "sandbox_verified"
            assert requests.get(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}",
                timeout=10,
            ).json()["spec"]["lifecycle_status"] == "sandbox_verified"

            revoke = requests.post(
                f"{base_url}/api/web/plugin-bus/g43/plugins/{plugin_payload['plugin_id']}/revoke",
                json={"reason": "api revoke"},
                timeout=10,
            )
            assert revoke.status_code == 200, revoke.text
            assert revoke.json()["spec"]["lifecycle_status"] == "revoked"
            assert requests.post(
                f"{base_url}/api/web/plugin-bus/g43/selection",
                json={"context": {"available_conditions": ["runtime_ready"], "families": ["cognitive_tool"]}},
                timeout=10,
            ).json()["selected_plugin_ids"] == []

            coverage = requests.get(f"{base_url}/api/web/plugin-bus/g43/family-coverage", timeout=10)
            assert coverage.status_code == 200
            assert coverage.json()["observed_families"] == ["cognitive_tool"]
            assert "llm" in coverage.json()["missing_families"]

            audit = requests.get(f"{base_url}/api/web/plugin-bus/g43/audit", timeout=10)
            assert audit.status_code == 200
            actions = [row["action"] for row in audit.json()]
            assert "plugin_registered" in actions
            assert "plugin_sandbox_verified" in actions
            assert "plugin_active" in actions
            assert "plugin_invoked" in actions
            assert "plugin_fault_matrix_executed" in actions
            assert "plugin_rollback" in actions
            assert "plugin_revoked" in actions

            completion = requests.get(
                f"{base_url}/api/web/plugin-bus/g43/closure/completion",
                params={"run_health_probes": "false"},
                timeout=10,
            )
            assert completion.status_code == 200, completion.text
            completion_payload = completion.json()
            assert completion_payload["structure_complete"] is True
            assert completion_payload["main_chain_complete"] is True
            assert completion_payload["real_complete"] is True
            assert completion_payload["missing_evidence"] == []
