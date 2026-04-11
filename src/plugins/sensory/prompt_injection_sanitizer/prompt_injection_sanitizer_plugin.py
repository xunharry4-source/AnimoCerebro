from __future__ import annotations

import hashlib
import re

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.sensory_spec import SanitizedSignal, SignalSanitizePlugin


INJECTION_PATTERNS = (
    "ignore all previous instructions",
    "execute this",
    "system prompt",
    "developer message",
)


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


def build_default_prompt_injection_sanitizer_plugin(
    *,
    plugin_id: str = "sensory-sanitize-basic",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> BasicPromptInjectionSanitizer:
    return BasicPromptInjectionSanitizer(
        plugin_id=plugin_id,
        version=version,
        feature_code="sensory.sanitize",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sanitize_false_negative_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )