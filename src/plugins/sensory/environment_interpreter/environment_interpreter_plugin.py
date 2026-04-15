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

    def interpret_signal(self, signal) -> EnvironmentEvent:
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

        return EnvironmentEvent(
            event_type="environment.observed",
            source_plugin_id=self.plugin_id,
            summary=f"Observed external signal: {normalized.sanitized_text or '[EMPTY]'}",
            structured_payload={
                "text": normalized.sanitized_text,
                "raw_fingerprint": normalized.raw_fingerprint,
            },
            risk_flags=["sanitized_signal"] if normalized.sanitized_text else [],
            audit_evidence=list(normalized.redaction_evidence),
        )


def build_default_environment_interpreter_plugin() -> BasicEnvironmentInterpreter:
    return BasicEnvironmentInterpreter()
