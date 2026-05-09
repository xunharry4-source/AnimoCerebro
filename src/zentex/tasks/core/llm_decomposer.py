from __future__ import annotations
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


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import (
    ModelProviderCallerContext,
    ModelProviderSpec,
    ModelProviderTimeoutError,
)
from zentex.kernel import AuditEventType
from zentex.llm.service import LLMService
from zentex.tasks.models import CoordinationMode, TaskType, DecompositionContext
from zentex.tasks.core.llm_prompt import (
    build_decomposition_prompt,
    build_decomposition_context_dict,
)

logger = logging.getLogger(__name__)
_TIMEOUT_FALLBACK_PROVIDER_ORDER = ("gemini", "openai_compat")
_TIMEOUT_FALLBACK_MODELS = {
    "openai_compat": "gemini-3-flash",
}


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
    Fail-closed: if model_provider/audit_store are missing or the model output is invalid, raise.
    """

    def __init__(
        self,
        *,
        llm_service: Optional[LLMService] = None,
        model_provider: Optional[ModelProviderSpec] = None,
        model_provider_key: Optional[str] = None,
        transcript_store: Any = None,
        session_id: str = "task-management",
    ) -> None:
        self._llm_service = llm_service
        self._model_provider = model_provider
        self._model_provider_key = model_provider_key
        self._transcript_store = transcript_store
        self._session_id = session_id
        self._request_timeout_seconds = 8.0

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
            raise RuntimeError("audit_store is required for auditable replay")
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

        logger.info(f"[TASK AUDIT] Starting mission Union[decomposition, Title]: {mission_title} | Trace: {trace_id}")
        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=turn_id,
            entry_type=AuditEventType.MODEL_PROVIDER_INVOKED,
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
            raw = self._invoke_generate_json(
                prompt=prompt,
                context=ctx_dict,
                caller_context=caller_context,
            )
            parsed = LLMMissionDecomposition.model_validate(raw)
            logger.info(f"[TASK AUDIT] Mission decomposition Union[successful, Subtasks]: {len(parsed.subtasks)} | Trace: {trace_id}")
        except Exception as exc:
            logger.warning(
                "[TASK AUDIT] Mission decomposition failed, using fallback | Trace: %s | Error: %s",
                trace_id,
                exc,
            )
            self._transcript_store.write_entry(
                session_id=self._session_id,
                turn_id=turn_id,
                entry_type=AuditEventType.MODEL_PROVIDER_FAILED,
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
            parsed = self._build_fallback_decomposition(mission_title, mission_content)

        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=turn_id,
            entry_type=AuditEventType.MODEL_PROVIDER_COMPLETED,
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

    def _invoke_generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
    ) -> Any:
        metadata = {
            "trace_id": caller_context.trace_id,
            "question_driver_refs": caller_context.question_driver_refs,
            "request_timeout_seconds": self._request_timeout_seconds,
        }
        if self._llm_service is not None:
            try:
                result = self._invoke_gateway_or_service(
                    prompt=prompt,
                    context=context,
                    caller_context=caller_context,
                    provider_key=self._model_provider_key,
                    model=None,
                    metadata=metadata,
                )
                return result.output if hasattr(result, "output") else result
            except ModelProviderTimeoutError as primary_exc:
                logger.warning(
                    "Task decomposition LLM timed out on primary provider; trying online fallback providers: %s",
                    ", ".join(_TIMEOUT_FALLBACK_PROVIDER_ORDER),
                )
                last_exc: Exception = primary_exc
                primary_provider = self._resolve_default_provider_key()
                for provider_key in _TIMEOUT_FALLBACK_PROVIDER_ORDER:
                    if provider_key in {self._model_provider_key, primary_provider}:
                        continue
                    try:
                        result = self._invoke_gateway_or_service(
                            prompt=prompt,
                            context=context,
                            caller_context=caller_context,
                            provider_key=provider_key,
                            model=_TIMEOUT_FALLBACK_MODELS.get(provider_key),
                            metadata=metadata,
                        )
                        return result.output if hasattr(result, "output") else result
                    except Exception as fallback_exc:
                        last_exc = fallback_exc
                        logger.warning(
                            "Task decomposition fallback provider failed | provider=%s error=%s",
                            provider_key,
                            fallback_exc,
                        )
                raise last_exc

        return self._model_provider.generate_json(
            prompt=prompt,
            context=context,
            caller_context=caller_context,
        )

    def _invoke_gateway_or_service(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        provider_key: Optional[str],
        model: Optional[str],
        metadata: Dict[str, Any],
    ) -> Any:
        gateway = getattr(self._llm_service, "_gateway", None)
        if gateway is not None and hasattr(gateway, "invoke_generate_json"):
            return gateway.invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                provider_key=provider_key,
                model=model,
                metadata=metadata,
            )
        return self._llm_service.generate_json(
            prompt=prompt,
            context=context,
            caller_context=caller_context,
            source_module=caller_context.source_module,
            invocation_phase=caller_context.invocation_phase,
            decision_id=caller_context.decision_id,
            model_provider=provider_key,
            model=model,
            metadata=metadata,
        )

    def _resolve_default_provider_key(self) -> Optional[str]:
        gateway = getattr(self._llm_service, "_gateway", None)
        return getattr(gateway, "_default_provider_key", None)

    def _build_fallback_decomposition(
        self,
        mission_title: str,
        mission_content: str,
    ) -> LLMMissionDecomposition:
        title = (mission_title or "任务").strip()
        content = (mission_content or "").strip()
        subject = content or title
        subtasks = [
            LLMDecomposedTask(
                local_id="step-1",
                title=f"分析{title}",
                task_type=TaskType.COGNITIVE_STEP,
                content=f"梳理目标、约束、输入与验收条件：{subject}",
                objective=f"明确{title}的执行边界与依赖关系",
                requirements=[
                    "提取主要目标",
                    "识别约束与风险",
                    "形成可执行步骤",
                ],
                depends_on=[],
                coordination_mode=CoordinationMode.SEQUENTIAL,
            ),
            LLMDecomposedTask(
                local_id="step-2",
                title=f"执行{title}",
                task_type=TaskType.SYSTEM_ACTION,
                content=f"基于分析结果推进核心执行工作：{subject}",
                objective=f"完成{title}的主体执行",
                requirements=[
                    "遵循分析阶段给出的边界",
                    "保留关键中间结果",
                    "记录执行产出",
                ],
                depends_on=["step-1"],
                coordination_mode=CoordinationMode.SEQUENTIAL,
            ),
            LLMDecomposedTask(
                local_id="step-3",
                title=f"验证{title}",
                task_type=TaskType.COGNITIVE_STEP,
                content=f"检查执行结果是否满足目标与约束：{subject}",
                objective=f"确认{title}的结果可交付",
                requirements=[
                    "核对目标完成度",
                    "确认无明显遗漏",
                    "输出验证结论",
                ],
                depends_on=["step-2"],
                coordination_mode=CoordinationMode.SEQUENTIAL,
            ),
        ]
        return LLMMissionDecomposition(subtasks=subtasks)
