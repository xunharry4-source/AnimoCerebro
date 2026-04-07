from __future__ import annotations

import hashlib
import re

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.sensory_spec import (
    EnvironmentEvent,
    SanitizedSignal,
    SensorySecurityError,
    SignalIngestPlugin,
    SignalInterpretPlugin,
    SignalSanitizePlugin,
)


INJECTION_PATTERNS = (
    "ignore all previous instructions",
    "execute this",
    "system prompt",
    "developer message",
)


class BasicWebhookIngestPlugin(SignalIngestPlugin):
    source_kind: str = "webhook"
    _payload: str

    def __init__(self, payload: str, **data: object) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_payload", payload)

    def ingest_signal(self) -> str:
        return self._payload


class BasicPromptInjectionSanitizer(SignalSanitizePlugin):
    sanitizer_name: str = "basic_prompt_injection_sanitizer"

    def sanitize_signal(self, raw_signal: str) -> SanitizedSignal:
        normalized = raw_signal.strip()
        lowered = normalized.lower()
        evidence = [pattern for pattern in INJECTION_PATTERNS if pattern in lowered]
        injection_risk = bool(evidence)

        sanitized_text = normalized
        if injection_risk:
            sanitized_text = normalized
            for pattern in evidence:
                sanitized_text = re.sub(
                    re.escape(pattern),
                    "[REDACTED_PROMPT_INJECTION]",
                    sanitized_text,
                    flags=re.IGNORECASE,
                )
            sanitized_text = sanitized_text[:160]

        fingerprint = hashlib.sha256(raw_signal.encode("utf-8")).hexdigest()
        return SanitizedSignal(
            raw_fingerprint=fingerprint,
            sanitized_text=sanitized_text or "[EMPTY_AFTER_SANITIZATION]",
            injection_risk=injection_risk,
            redaction_evidence=evidence,
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


def build_default_sensory_chain(payload: str) -> SensoryChainOrchestrator:
    ingest = BasicWebhookIngestPlugin(
        payload=payload,
        plugin_id="sensory-ingest-webhook",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["webhook_parse_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    sanitize = BasicPromptInjectionSanitizer(
        plugin_id="sensory-sanitize-basic",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sanitize_false_negative_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    interpret = BasicEnvironmentInterpreter(
        plugin_id="sensory-interpret-generic",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["interpretation_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    return SensoryChainOrchestrator(
        ingest_plugin=ingest,
        sanitize_plugin=sanitize,
        interpret_plugin=interpret,
    )
