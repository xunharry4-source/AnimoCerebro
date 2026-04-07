from __future__ import annotations

from typing import Any, Dict

from zentex.core.model_provider_spec import ModelProviderCallerContext
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult


class MemoryExtractorPlugin(CognitiveToolSpec):
    """
    LLM-backed memory extraction plugin.

    Fail-closed rule:
    - If LLM is unavailable or missing from context, raise immediately.
    - Do not fabricate memory candidates via rules.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = context.get("model_provider")
        if provider is None or not hasattr(provider, "generate_json"):
            raise RuntimeError(
                "LLM MANDATORY: missing active ModelProvider in context['model_provider']"
            )

        model_context: Dict[str, Any] = {
            key: value
            for key, value in context.items()
            if key not in {"model_provider", "transcript_store"}
        }
        response = provider.generate_json(
            prompt=(
                "You are Zentex. Extract durable memory candidates from the provided turn context. "
                "Return JSON with keys: summary, promotion_candidates, forget_candidates, tags, confidence."
            ),
            context=model_context,
            caller_context=ModelProviderCallerContext(
                source_module="memory.memory_extractor",
                invocation_phase="memory_extraction",
                question_driver_refs=["什么值得长期记住"],
                decision_id=str(model_context.get("decision_id") or "memory:extract"),
            ),
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
                }
            },
            confidence=confidence,
        )


def build_memory_extractor_plugin(
    *,
    plugin_id: str = "memory-extractor-llm",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> MemoryExtractorPlugin:
    return MemoryExtractorPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="memory.extract",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["memory_extraction_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="memory_extractor",
        purpose="Extract durable memory candidates using the active LLM provider.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["summary"]},
        required_context=[],
        trigger_conditions=["inspection"],
        behavior_key="memory",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "unsafe_external_action"],
    )
