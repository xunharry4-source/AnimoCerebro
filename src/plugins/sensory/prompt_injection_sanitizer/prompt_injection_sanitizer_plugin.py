from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


INJECTION_PATTERNS = (
    "ignore all previous instructions",
    "execute this",
    "system prompt",
    "developer message",
)


class SanitizedSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_fingerprint: str
    sanitized_text: str
    injection_risk: bool
    redaction_evidence: list[str] = Field(default_factory=list)


class BasicPromptInjectionSanitizer(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "sensory_injection_sanitizer"
    version: str = "1.0.0"
    feature_code: str = "sensory.sanitize"
    display_name: str = "Prompt Injection Sanitizer"
    description: str = "Sanitize raw sensory text before downstream interpretation."
    behavior_key: str = "sensory_injection_sanitizer"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def sanitize_signal(self, raw_signal: str) -> SanitizedSignal:
        normalized = (raw_signal or "").strip()
        lowered = normalized.lower()
        evidence = [pattern for pattern in INJECTION_PATTERNS if pattern in lowered]
        sanitized_text = normalized
        for pattern in evidence:
            sanitized_text = re.sub(
                re.escape(pattern),
                "[REDACTED_PROMPT_INJECTION]",
                sanitized_text,
                flags=re.IGNORECASE,
            )
        return SanitizedSignal(
            raw_fingerprint=hashlib.sha256((raw_signal or "").encode("utf-8")).hexdigest(),
            sanitized_text=sanitized_text[:160] or "[EMPTY_AFTER_SANITIZATION]",
            injection_risk=bool(evidence),
            redaction_evidence=evidence,
        )


def build_default_prompt_injection_sanitizer_plugin() -> BasicPromptInjectionSanitizer:
    return BasicPromptInjectionSanitizer()
