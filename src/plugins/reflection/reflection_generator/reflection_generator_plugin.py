from __future__ import annotations

from typing import Any, Dict

from zentex.core.model_provider_spec import ModelProviderCallerContext
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult


class ReflectionGeneratorPlugin(CognitiveToolSpec):
    """
    LLM-backed reflection generator plugin.

    Fail-closed rule:
    - If LLM is unavailable or missing from context, raise immediately.
    - No local rules are allowed to pretend a reflection exists.
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
                "You are Zentex. Generate an auditable reflection for the current turn. "
                "Return JSON with keys: summary, lessons, risks, next_improvements, confidence."
            ),
            context=model_context,
            caller_context=ModelProviderCallerContext(
                source_module="reflection.reflection_generator",
                invocation_phase="reflection_generation",
                question_driver_refs=["我学到了什么", "下次如何做得更好"],
                decision_id=str(model_context.get("decision_id") or "reflection:generate"),
            ),
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
                }
            },
            confidence=confidence,
        )


def build_reflection_generator_plugin(
    *,
    plugin_id: str = "reflection-generator-llm",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> ReflectionGeneratorPlugin:
    return ReflectionGeneratorPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="reflection.generate",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["reflection_generation_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="reflection_generator",
        purpose="Generate an auditable reflection using the active LLM provider.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["summary"]},
        required_context=[],
        trigger_conditions=["inspection"],
        behavior_key="reflection",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "unsafe_external_action"],
    )
