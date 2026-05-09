from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import MEMORY_EXTRACTOR
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


class MemoryExtractorPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = MEMORY_EXTRACTOR
    version: str = "1.0.0"
    feature_code: str = "memory.extract"
    display_name: str = "Memory Extractor"
    description: str = "Extract durable memory candidates using the active model provider."
    behavior_key: str = "memory"
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
        functional_memory_signals: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_memory_signals = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=model_context,
                trace_id=str(context.get("trace_id") or "memory-extraction"),
                originator_id=str(context.get("session_id") or "memory-extractor"),
                caller_plugin_id=self.plugin_id,
            )
        model_context["functional_memory_signals"] = functional_memory_signals
        prompt = (
            "You are Zentex. Extract durable memory candidates from the provided turn context. "
            "Return JSON with keys: summary, promotion_candidates, forget_candidates, tags, confidence."
        )
        caller_context = ModelProviderCallerContext(
            source_module="memory.memory_extractor",
            invocation_phase="memory_extraction",
            decision_id=str(model_context.get("decision_id") or "memory:extract"),
            trace_id=str(context.get("trace_id") or "memory:extract"),
        )
        if llm_service is not None and hasattr(llm_service, "generate_json"):
            response = llm_service.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
                source_module=caller_context.source_module,
                invocation_phase=caller_context.invocation_phase,
                decision_id=caller_context.decision_id,
                model_provider=resolve_model_provider_key(context),
                metadata={"trace_id": caller_context.trace_id},
            ).output
        else:
            response = provider.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
            )
        summary = str(response.get("summary") or "").strip()
        promotions = response.get("promotion_candidates") or []
        forgets = response.get("forget_candidates") or []
        tags = response.get("tags") or []
        confidence = float(response.get("confidence") or 0.5)
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary or "LLM returned empty memory summary",
            proposals=[
                {
                    "kind": "memory_promotion_candidates",
                    "candidates": promotions,
                    "tags": tags,
                }
            ],
            risks=[{"kind": "memory_forget_candidates", "items": forgets}],
            context_updates={
                "memory_extraction": {
                    "promotion_candidates": promotions,
                    "forget_candidates": forgets,
                    "tags": tags,
                    "functional_inputs": functional_memory_signals,
                }
            },
            confidence=confidence,
        )


def build_memory_extractor_plugin() -> MemoryExtractorPlugin:
    return MemoryExtractorPlugin()
