from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.models import CognitiveToolSpec
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CapabilityPatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_summary: str = Field(min_length=1)
    patch_updates: Dict[str, Any] = Field(default_factory=dict)


class BaseCapabilityPatchPlugin(CognitiveToolSpec):
    """
    Generic base for capability patch plugins.

    Guarantees:
    - LLM mandatory (requires a model_provider with generate_json)
    - fail-closed on any model/provider failure
    - transcript_store required for auditable replay
    """

    question_ref: str = "Abstract Question"
    source_module: str = "abstract_patch"
    invocation_phase: str = "capability_patch"
    context_update_key: Optional[str] = None

    def _require_model_provider(self, context: Dict[str, Any]) -> Any:
        provider = context.get("model_provider")
        if provider is not None and callable(getattr(provider, "generate_json", None)):
            return provider
        raise RuntimeError(
            f"LLM MANDATORY: {self.plugin_id} requires an active ModelProvider."
        )

    def _require_transcript_store(self, context: Dict[str, Any]) -> BrainTranscriptStore:
        store = context.get("transcript_store")
        if not isinstance(store, BrainTranscriptStore):
            raise RuntimeError("transcript_store is required for auditable replay")
        return store

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return context

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. Provide an additive enhancement patch for the current cognitive state.\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates."
        )

    def execute_patch_inference(self, context: Dict[str, Any], output_model: Type[T]) -> T:
        provider = self._require_model_provider(context)
        transcript_store = self._require_transcript_store(context)
        local_inputs = self._get_local_inputs(context)
        prompt = self._get_prompt()

        trace_id = str(context.get("trace_id") or f"patch:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")
        request_id = str(uuid4())

        # Local import to avoid module import cycles (model_provider_spec -> plugin_base).
        from zentex.core.model_provider_spec import ModelProviderCallerContext  # noqa: WPS433

        caller_context = ModelProviderCallerContext(
            source_module=self.source_module,
            invocation_phase=self.invocation_phase,
            question_driver_refs=[self.question_ref],
            decision_id=decision_id,
        )

        transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
            timestamp=datetime.now(timezone.utc),
            source=f"zentex.capability_patch.{self.source_module}",
            trace_id=trace_id,
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": self.question_ref,
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "context": local_inputs,
            },
        )

        try:
            raw = provider.generate_json(
                prompt=prompt,
                context=local_inputs,
                caller_context=caller_context,
            )
        except Exception as exc:
            transcript_store.write_entry(
                session_id=session_id,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_FAILED,
                timestamp=datetime.now(timezone.utc),
                source=f"zentex.capability_patch.{self.source_module}",
                trace_id=trace_id,
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": self.question_ref,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error("Capability patch LLM call failed: %s -> %s", self.plugin_id, exc)
            raise

        parsed = output_model.model_validate(raw)
        transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
            timestamp=datetime.now(timezone.utc),
            source=f"zentex.capability_patch.{self.source_module}",
            trace_id=trace_id,
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": self.question_ref,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": parsed.model_dump(mode="json"),
            },
        )
        return parsed

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        parsed = self.execute_patch_inference(context, CapabilityPatchOutput)
        context_updates: Dict[str, Any] = {
            f"{self.plugin_id}_result": parsed.model_dump(mode="json"),
        }
        if isinstance(self.context_update_key, str) and self.context_update_key.strip():
            context_updates[self.context_update_key.strip()] = parsed.model_dump(mode="json")

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=parsed.patch_summary,
            proposals=[
                {
                    "kind": "capability_patch",
                    "patch_ref": self.question_ref,
                    "patch_summary": parsed.patch_summary,
                    "patch_updates": parsed.patch_updates,
                }
            ],
            context_updates=context_updates,
            confidence=0.8,
        )

