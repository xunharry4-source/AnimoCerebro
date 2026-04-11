from __future__ import annotations

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.sensory_spec import (
    EnvironmentEvent,
    SanitizedSignal,
    SensorySecurityError,
    SignalInterpretPlugin,
)


class BasicEnvironmentInterpreter(SignalInterpretPlugin):
    interpreter_domain: str = "generic_environment"

    def interpret_signal(self, signal: SanitizedSignal) -> EnvironmentEvent:
        if not isinstance(signal, SanitizedSignal):
            raise SensorySecurityError(
                "SignalInterpretPlugin requires SanitizedSignal input; raw signal bypass blocked"
            )

        return EnvironmentEvent(
            event_type="environment.observed",
            source_plugin_id=self.plugin_id,
            summary=f"Observed external signal: {signal.sanitized_text}",
            structured_payload={
                "text": signal.sanitized_text,
                "raw_fingerprint": signal.raw_fingerprint,
            },
            risk_flags=["sanitized_signal"],
            audit_evidence=list(signal.redaction_evidence),
        )


def build_default_environment_interpreter_plugin(
    *,
    plugin_id: str = "sensory-interpret-generic",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> BasicEnvironmentInterpreter:
    return BasicEnvironmentInterpreter(
        plugin_id=plugin_id,
        version=version,
        feature_code="sensory.interpret",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["interpretation_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )