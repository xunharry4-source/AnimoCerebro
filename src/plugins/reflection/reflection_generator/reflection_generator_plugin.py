from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import REFLECTION_GENERATOR
from zentex.common.nine_questions_shared import resolve_model_provider_key
from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


class CognitiveToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    summary: str
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    context_updates: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class ReflectionGeneratorPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = REFLECTION_GENERATOR
    version: str = "1.0.0"
    feature_code: str = "reflection.generate"
    display_name: str = "Reflection Generator"
    description: str = "Generate an auditable reflection using the active model provider."
    behavior_key: str = "reflection"
    lifecycle_status: str = "active"
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        llm_service = context.get("llm_service")
        provider = context.get("model_provider")
        if llm_service is None and (provider is None or not hasattr(provider, "generate_json")):
            raise RuntimeError(
                "LLM MANDATORY: missing active llm_service and ModelProvider fallback"
            )

        model_context: dict[str, Any] = {
            key: value
            for key, value in context.items()
            if key not in {"llm_service", "model_provider", "transcript_store"}
        }
        plugin_service = context.get("plugin_service")
        functional_reflection_signals: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_reflection_signals = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=model_context,
                trace_id=str(context.get("trace_id") or "reflection-generation"),
                originator_id=str(context.get("session_id") or "reflection-generator"),
                caller_plugin_id=self.plugin_id,
        )
        model_context["functional_reflection_signals"] = functional_reflection_signals
        caller_context = ModelProviderCallerContext(
            source_module="reflection.reflection_generator",
            invocation_phase="reflection_generation",
            decision_id=str(model_context.get("decision_id") or "reflection:generate"),
            trace_id=str(context.get("trace_id") or "reflection:generate"),
        )
        prompt = (
            "You are Zentex. Generate an auditable reflection for the current turn. "
            "Return JSON with keys: summary, lessons, risks, next_improvements, confidence."
        )
        if llm_service is not None and hasattr(llm_service, "generate_json"):
            gateway_call = llm_service.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
                source_module=caller_context.source_module,
                invocation_phase=caller_context.invocation_phase,
                decision_id=caller_context.decision_id,
                model_provider=resolve_model_provider_key(context),
                metadata={
                    "trace_id": caller_context.trace_id,
                },
            )
            response = gateway_call.output
        else:
            response = provider.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
            )
        summary = str(response.get("summary") or "").strip()
        lessons = response.get("lessons") or []
        risks = response.get("risks") or []
        improvements = response.get("next_improvements") or []
        confidence = float(response.get("confidence") or 0.5)
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary or "LLM returned empty reflection summary",
            proposals=[
                {
                    "kind": "reflection",
                    "summary": summary,
                    "lessons": lessons,
                    "next_improvements": improvements,
                }
            ],
            risks=[{"kind": "reflection_risks", "items": risks}],
            context_updates={
                "reflection": {
                    "summary": summary,
                    "lessons": lessons,
                    "risks": risks,
                    "next_improvements": improvements,
                    "functional_inputs": functional_reflection_signals,
                }
            },
            confidence=confidence,
        )


def build_reflection_generator_plugin() -> ReflectionGeneratorPlugin:
    return ReflectionGeneratorPlugin()
