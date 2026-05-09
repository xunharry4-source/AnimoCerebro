from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from zentex.common.plugin_ids import COGNITIVE_SEMANTIC_CONFLICT
from zentex.common.nine_questions_shared import resolve_model_provider_key
from zentex.common.prompt_template_files import render_prompt_template
from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals
from zentex.safety.conflict_engine import CognitiveConflictReport


class SemanticConflictPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = COGNITIVE_SEMANTIC_CONFLICT
    version: str = "1.0.0"
    feature_code: str = "cognitive.semantic_conflict"
    display_name: str = "Semantic Conflict"
    description: str = "Detect conflicts between goals and identity constraints."
    behavior_key: str = "cognitive_conflict_detection"
    lifecycle_status: str = "active"
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def detect_conflict(
        self,
        *,
        context: dict[str, Any],
        model_provider: Any,
        llm_service: Any = None,
    ) -> Optional[CognitiveConflictReport]:
        plugin_service = context.get("plugin_service")
        functional_inputs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "semantic-conflict"),
                originator_id=str(context.get("session_id") or "semantic-conflict"),
                caller_plugin_id=self.plugin_id,
            )
        prompt = render_prompt_template(
            Path(__file__).resolve().with_name("prompt_templates"),
            "semantic_conflict.md",
            {},
            error_prefix="semantic_conflict",
        )
        llm_context = {
            **dict(context),
            "functional_inputs": functional_inputs,
        }
        caller_context = ModelProviderCallerContext(
            source_module="CognitiveConflictEngine",
            invocation_phase="semantic_conflict_detection",
            decision_id=str(context.get("decision_id") or "semantic-conflict"),
            trace_id=str(context.get("trace_id") or "semantic-conflict"),
        )
        if llm_service is not None and hasattr(llm_service, "generate_json"):
            payload = llm_service.generate_json(
                prompt=prompt,
                context=llm_context,
                caller_context=caller_context,
                source_module=caller_context.source_module,
                invocation_phase=caller_context.invocation_phase,
                decision_id=caller_context.decision_id,
                model_provider=resolve_model_provider_key(context),
                metadata={"trace_id": caller_context.trace_id},
            ).output
        else:
            payload = model_provider.generate_json(
                prompt=prompt,
                context=llm_context,
                caller_context=caller_context,
            )
        if not payload.get("has_conflict"):
            return None
        return CognitiveConflictReport(
            conflict_type="semantic_identity_conflict",
            severity=str(payload.get("severity") or "high"),
            suggested_resolution=str(
                payload.get("suggested_resolution") or "pause_and_review_identity_alignment"
            ),
            source_plugin_id=self.plugin_id,
            details={
                "rationale": payload.get("rationale"),
                "goal": context.get("goal"),
                "identity_constraints": context.get("identity_constraints"),
                "functional_inputs": functional_inputs,
            },
        )


def build_semantic_conflict_plugin() -> SemanticConflictPlugin:
    return SemanticConflictPlugin()
