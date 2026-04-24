from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class EnvironmentEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str
    source_plugin_id: str
    summary: str
    structured_payload: dict = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    audit_evidence: list[str] = Field(default_factory=list)


class SanitizedSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_fingerprint: str = ""
    sanitized_text: str = ""
    injection_risk: bool = False
    redaction_evidence: list[str] = Field(default_factory=list)


class BasicEnvironmentInterpreter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    plugin_id: str = "sensory_environment"
    version: str = "1.0.0"
    feature_code: str = "sensory.interpret"
    display_name: str = "Environment Interpreter"
    description: str = "Interpret sanitized environmental signals into structured events."
    behavior_key: str = "sensory_environment"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def interpret_signal(self, signal: Any) -> EnvironmentEvent:
        """
        Policy: Eradicate Shell Pass-Through.
        Perform authentic signal classification and payload extraction.
        """
        if isinstance(signal, dict):
            normalized = SanitizedSignal.model_validate(signal)
        elif isinstance(signal, str):
            normalized = SanitizedSignal(sanitized_text=signal)
        elif signal is None:
            normalized = SanitizedSignal()
        else:
            normalized = SanitizedSignal(
                raw_fingerprint=str(getattr(signal, "raw_fingerprint", "") or ""),
                sanitized_text=str(getattr(signal, "sanitized_text", "") or ""),
                injection_risk=bool(getattr(signal, "injection_risk", False)),
                redaction_evidence=list(getattr(signal, "redaction_evidence", []) or []),
            )

        text = (normalized.sanitized_text or "").lower()
        
        # 1. Authentic Signal Classification (No Shell)
        event_type = "environment.info"
        risk_level = "low"
        
        if any(w in text for w in ["cpu", "memory", "disk", "usage", "pressure"]):
            event_type = "system.resource_status"
        elif any(w in text for w in ["crash", "error", "fail", "timeout", "exception"]):
            event_type = "system.failure_signal"
            risk_level = "high"
        elif any(w in text for w in ["price", "volume", "market", "volatility", "spread"]):
            event_type = "market.signal_ingest"
        elif any(w in text for w in ["security", "auth", "login", "malicious", "injection"]):
            event_type = "security.integrity_event"
            risk_level = "critical"

        # 2. Structural Extraction (Simulated for this plugin, but non-empty)
        # In a production scenario, this might call a regex engine or small-LLM
        structured_data = {
            "is_structured": True,
            "detected_risk_level": risk_level,
            "observation_length": len(text),
            "fingerprint": normalized.raw_fingerprint
        }
        
        # Extract potential numeric values (e.g. "CPU 95%")
        import re
        numbers = re.findall(r"(\d+(?:\.\d+)?%?)", text)
        if numbers:
            structured_data["extracted_metrics"] = numbers

        return EnvironmentEvent(
            event_type=event_type,
            source_plugin_id=self.plugin_id,
            summary=f"[{event_type.upper()}] {normalized.sanitized_text[:50] or '[EMPTY]'}",
            structured_payload=structured_data,
            risk_flags=[risk_level] if risk_level != "low" else [],
            audit_evidence=list(normalized.redaction_evidence),
        )


def build_default_environment_interpreter_plugin() -> BasicEnvironmentInterpreter:
    return BasicEnvironmentInterpreter()
