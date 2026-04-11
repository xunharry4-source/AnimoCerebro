from __future__ import annotations

"""Sensory signal processing chain.

Framework-level orchestrator that enforces the mandatory
ingest → sanitize → interpret pipeline for all sensory signals.
"""

from zentex.core.sensory_spec import (
    EnvironmentEvent,
    SanitizedSignal,
    SensorySecurityError,
    SignalIngestPlugin,
    SignalInterpretPlugin,
    SignalSanitizePlugin,
)


class SensoryChainOrchestrator:
    """
    Mandatory ingest -> sanitize -> interpret chain.

    Hard redlines:
    - raw ingest output never reaches the interpreter directly
    - risky sanitized signals are downgraded into quarantine warning events
    """

    def __init__(
        self,
        *,
        ingest_plugin: SignalIngestPlugin,
        sanitize_plugin: SignalSanitizePlugin,
        interpret_plugin: SignalInterpretPlugin,
    ) -> None:
        self.ingest_plugin = ingest_plugin
        self.sanitize_plugin = sanitize_plugin
        self.interpret_plugin = interpret_plugin

    def process_signal(self) -> EnvironmentEvent:
        raw_signal = self.ingest_plugin.ingest_signal()
        sanitized = self.sanitize_plugin.sanitize_signal(raw_signal)
        return self.interpret_sanitized_signal(sanitized)

    def interpret_sanitized_signal(self, signal: SanitizedSignal) -> EnvironmentEvent:
        if not isinstance(signal, SanitizedSignal):
            raise SensorySecurityError(
                "Only SanitizedSignal may enter the interpretation stage"
            )

        if signal.injection_risk:
            return self._build_security_warning_event(signal)

        return self.interpret_plugin.interpret_signal(signal)

    def _build_security_warning_event(self, signal: SanitizedSignal) -> EnvironmentEvent:
        return EnvironmentEvent(
            event_type="security.sensory_injection_blocked",
            source_plugin_id=self.sanitize_plugin.plugin_id,
            summary=(
                "Dangerous external signal quarantined before interpretation. "
                f"Fingerprint={signal.raw_fingerprint[:16]}"
            ),
            structured_payload={
                "raw_fingerprint": signal.raw_fingerprint,
                "sanitized_excerpt": signal.sanitized_text[:80],
                "quarantine_reason": "prompt_injection_risk",
            },
            risk_flags=["prompt_injection_detected", "interpretation_blocked"],
            audit_evidence=list(signal.redaction_evidence),
        )
