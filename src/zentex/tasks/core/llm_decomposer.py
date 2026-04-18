"""
LLM Task Decomposer — zentex.tasks.core.llm_decomposer

RESPONSIBILITY:
  Orchestrates LLM calls for mission decomposition.  Prompt construction and
  content preprocessing are fully delegated to zentex.tasks.core.llm_prompt —
  this module MUST NOT build or inline any prompt string sent to the LLM.

DOES NOT:
  - Build prompt strings (see llm_prompt.py).
  - Preprocess or truncate mission content (see llm_prompt.py).
  - Own service lifecycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import ModelProviderCallerContext, ModelProviderSpec
from zentex.kernel import BrainTranscriptEntryType
from zentex.llm.service import LLMService
from zentex.tasks.models import CoordinationMode, TaskType, DecompositionContext
from zentex.tasks.core.llm_prompt import (
    build_decomposition_prompt,
    build_decomposition_context_dict,
)

logger = logging.getLogger(__name__)


class LLMDecomposedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    task_type: TaskType
    content: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    requirements: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    coordination_mode: CoordinationMode = CoordinationMode.PARALLEL


class LLMMissionDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: List[LLMDecomposedTask] = Field(default_factory=list)


class LLMTaskDecomposerPlugin:
    """
    LLM-backed mission decomposer for TaskManagementService.

    Contract: returns a List[dict] compatible with TaskManagementService.decompose_and_dispatch_mission().
    Fail-closed: if model_provider/transcript_store are missing or the model output is invalid, raise.
    """

    def __init__(
        self,
        *,
        llm_service: LLMService | None = None,
        model_provider: ModelProviderSpec | None = None,
        model_provider_key: str | None = None,
        transcript_store: Optional[Any] = None,
        session_id: str = "task-management",
    ) -> None:
        self._llm_service = llm_service
        self._model_provider = model_provider
        self._model_provider_key = model_provider_key
        self._transcript_store = transcript_store
        self._session_id = session_id

    def decompose_mission(
        self,
        mission_title: str,
        mission_content: str,
        context: Optional[DecompositionContext] = None,
    ) -> List[Dict[str, Any]]:
        """
        LLM-backed mission decomposer with unified context support.
        
        Phase A1: Accepts DecompositionContext for memory-informed decomposition.
        """
        if self._transcript_store is None:
            raise RuntimeError("transcript_store is required for auditable replay")
        if self._llm_service is None and (
            self._model_provider is None or not hasattr(self._model_provider, "generate_json")
        ):
            raise RuntimeError("LLM MANDATORY: missing active llm_service and ModelProvider fallback")

        trace_id = f"task_decompose:{uuid4().hex}"
        turn_id = str(uuid4())
        decision_id = f"{turn_id}:task_decompose"
        caller_context = ModelProviderCallerContext(
            source_module="zentex.tasks.llm_decomposer",
            invocation_phase="task_decompose_mission",
            question_driver_refs=["mission_decomposition"],
            decision_id=decision_id,
            trace_id=trace_id,
        )

        # Phase A1: All prompt construction and content preprocessing is
        # delegated to llm_prompt.py — never build prompts inline here.
        memory_text = context.memory_text if context else None
        prompt = build_decomposition_prompt(
            mission_title=mission_title,
            mission_content=mission_content,
            memory_text=memory_text,
        )
        ctx_dict: Dict[str, Any] = build_decomposition_context_dict(
            mission_title=mission_title,
            mission_content=mission_content,
        )

        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
            timestamp=datetime.now(timezone.utc),
            source="zentex.tasks.llm_decomposer",
            trace_id=trace_id,
            payload={
                "decision_id": decision_id,
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "context": ctx_dict,
            },
        )

        try:
            if self._llm_service is not None:
                raw = self._llm_service.generate_json(
                    prompt=prompt,
                    context=ctx_dict,
                    caller_context=caller_context,
                    source_module=caller_context.source_module,
                    invocation_phase=caller_context.invocation_phase,
                    decision_id=caller_context.decision_id,
                    model_provider=self._model_provider_key,
                    metadata={
                        "trace_id": caller_context.trace_id,
                        "question_driver_refs": caller_context.question_driver_refs,
                    },
                ).output
            else:
                raw = self._model_provider.generate_json(
                    prompt=prompt,
                    context=ctx_dict,
                    caller_context=caller_context,
                )
            parsed = LLMMissionDecomposition.model_validate(raw)
        except Exception as exc:
            self._transcript_store.write_entry(
                session_id=self._session_id,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_FAILED,
                timestamp=datetime.now(timezone.utc),
                source="zentex.tasks.llm_decomposer",
                trace_id=trace_id,
                payload={
                    "decision_id": decision_id,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
            timestamp=datetime.now(timezone.utc),
            source="zentex.tasks.llm_decomposer",
            trace_id=trace_id,
            payload={
                "decision_id": decision_id,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": parsed.model_dump(mode="json"),
            },
        )

        return [task.model_dump(mode="json") for task in parsed.subtasks]
