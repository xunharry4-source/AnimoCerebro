from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from zentex.kernel import AuditEventType
from zentex.llm.providers.config import get_default_provider_key, load_provider_tool_configs, resolve_env_value
from zentex.tasks.models import CoordinationMode, DecompositionContext, TaskStatus, TaskType
from zentex.tasks.decomposition.reviewer import PydanticAIAtomicSubtaskReviewer

logger = logging.getLogger(__name__)


class PydanticAIAtomicSubtask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    local_id: str = Field(min_length=1, description="Stable local dependency id, e.g. step-1")
    title: str = Field(min_length=1, max_length=120)
    task_type: Literal["cognitive_step", "agent_delegation", "system_action", "intervention"]
    content: str = Field(min_length=1, max_length=320)
    objective: str = Field(min_length=1, max_length=220)
    acceptance_criteria: List[str] = Field(min_length=1, max_length=5)
    required_resources: List[str] = Field(default_factory=list, max_length=6)
    depends_on: List[str] = Field(default_factory=list, max_length=8)
    coordination_mode: Literal["parallel", "bundle", "sequential"] = "sequential"

    @field_validator("local_id")
    @classmethod
    def _local_id_must_be_step(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("step-"):
            raise ValueError("local_id must use the step-N form")
        return text

    @field_validator("acceptance_criteria", "required_resources", "depends_on")
    @classmethod
    def _string_lists_must_be_clean(cls, value: List[str]) -> List[str]:
        cleaned = [str(item or "").strip() for item in value if str(item or "").strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("list values must not contain duplicates")
        return cleaned


class PydanticAIAtomicTaskBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decomposition_goal: str = Field(min_length=1)
    granularity_policy: str = Field(min_length=1)
    subtasks: List[PydanticAIAtomicSubtask] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _validate_dependency_graph(self) -> "PydanticAIAtomicTaskBreakdown":
        local_ids = [item.local_id for item in self.subtasks]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("subtask local_id values must be unique")
        seen: set[str] = set()
        for item in self.subtasks:
            unknown = [dep for dep in item.depends_on if dep not in local_ids]
            if unknown:
                raise ValueError(f"unknown dependencies for {item.local_id}: {unknown}")
            forward = [dep for dep in item.depends_on if dep not in seen]
            if forward:
                raise ValueError(f"dependencies must point to earlier subtasks only: {item.local_id} -> {forward}")
            seen.add(item.local_id)
        return self


class PydanticAIQ9SubtaskAlignmentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    objective_alignment_score: float = Field(ge=0.0, le=1.0)
    prohibition_compliance_score: float = Field(ge=0.0, le=1.0)
    requirement_coverage_score: float = Field(ge=0.0, le=1.0)
    review_findings: List[str] = Field(default_factory=list)
    rejected_subtask_local_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_low_scores(self) -> "PydanticAIQ9SubtaskAlignmentReview":
        if (
            self.objective_alignment_score < 0.9
            or self.prohibition_compliance_score < 1.0
            or self.requirement_coverage_score < 0.85
        ):
            self.accepted = False
        if not self.accepted and not self.review_findings:
            raise ValueError("rejected alignment review must include review_findings")
        return self


class PydanticAITaskDecomposerPlugin:
    """
    PydanticAI-backed mission decomposer for G31A.

    This component owns only the cognitive split into validated atomic records.
    It does not bind executors and never falls back to rule-generated subtasks.
    """

    def __init__(
        self,
        *,
        transcript_store: Any,
        session_id: str = "task-management",
        model_provider_key: Optional[str] = None,
        model_name: Optional[str] = None,
        api_base: Optional[str] = None,
        request_timeout_seconds: Optional[float] = None,
    ) -> None:
        if transcript_store is None:
            raise RuntimeError("transcript_store is required for PydanticAI task decomposition")
        self._transcript_store = transcript_store
        self._session_id = session_id
        self._model_provider_key = model_provider_key
        self._model_name = model_name
        self._api_base = api_base
        self._request_timeout_seconds = request_timeout_seconds
        self._reviewer = PydanticAIAtomicSubtaskReviewer()

    async def decompose_mission(
        self,
        mission_title: str,
        mission_content: str,
        context: Optional[DecompositionContext] = None,
    ) -> List[Dict[str, Any]]:
        trace_id = f"task_pydantic_ai_decompose:{uuid4().hex}"
        turn_id = str(uuid4())
        prompt = self._build_user_prompt(
            mission_title=mission_title,
            mission_content=mission_content,
            context=context,
        )
        model, provider_key, model_name, api_base, timeout_seconds = self._build_model()

        self._write_transcript(
            turn_id=turn_id,
            entry_type=AuditEventType.MODEL_PROVIDER_INVOKED,
            trace_id=trace_id,
            payload={
                "provider": provider_key,
                "model": model_name,
                "api_base": api_base,
                "prompt": prompt,
                "output_type": "PydanticAIAtomicTaskBreakdown",
                "granularity_policy": "single_atomic_operation_per_subtask",
            },
        )

        try:
            from pydantic_ai import Agent, ModelSettings, PromptedOutput

            agent = Agent(
                model,
                output_type=PromptedOutput(
                    PydanticAIAtomicTaskBreakdown,
                    name="PydanticAIAtomicTaskBreakdown",
                    description="Return a minimum-granularity task breakdown as JSON.",
                ),
                system_prompt=_SYSTEM_PROMPT,
                retries=0,
                output_retries=3,
                model_settings=ModelSettings(
                    temperature=0.0,
                    timeout=timeout_seconds,
                    max_tokens=1800,
                ),
            )
            result = await agent.run(prompt)
            parsed = PydanticAIAtomicTaskBreakdown.model_validate(result.output)
            self._reviewer.review_generated_subtasks(parsed.subtasks).raise_if_rejected()
            alignment = await self._review_q9_alignment(
                model=model,
                provider_key=provider_key,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
                trace_id=trace_id,
                turn_id=turn_id,
                mission_title=mission_title,
                mission_content=mission_content,
                context=context,
                breakdown=parsed,
            )
            subtasks = [self._to_task_payload(item, trace_id=trace_id) for item in parsed.subtasks]
            self._write_transcript(
                turn_id=turn_id,
                entry_type=AuditEventType.MODEL_PROVIDER_COMPLETED,
                trace_id=trace_id,
                payload={
                    "provider": provider_key,
                    "model": model_name,
                    "result": parsed.model_dump(mode="json"),
                    "q9_alignment_review": alignment.model_dump(mode="json"),
                    "usage": _usage_payload(result),
                    "subtask_count": len(subtasks),
                },
            )
            return subtasks
        except Exception as exc:
            self._write_transcript(
                turn_id=turn_id,
                entry_type=AuditEventType.MODEL_PROVIDER_FAILED,
                trace_id=trace_id,
                payload={
                    "provider": provider_key,
                    "model": model_name,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error(
                "PydanticAI task decomposition failed | trace_id=%s provider=%s model=%s error=%s",
                trace_id,
                provider_key,
                model_name,
                exc,
                exc_info=True,
            )
            raise RuntimeError(f"PydanticAI task decomposition failed: {exc}") from exc

    async def _review_q9_alignment(
        self,
        *,
        model: Any,
        provider_key: str,
        model_name: str,
        timeout_seconds: float,
        trace_id: str,
        turn_id: str,
        mission_title: str,
        mission_content: str,
        context: Optional[DecompositionContext],
        breakdown: PydanticAIAtomicTaskBreakdown,
    ) -> PydanticAIQ9SubtaskAlignmentReview:
        from pydantic_ai import Agent, ModelSettings, PromptedOutput

        q9_contract = self._q9_contract_from_context(context)
        prompt = "\n".join(
            [
                "审核 PydanticAI 生成的子任务是否严格继承 Q9 输出。",
                "必须检查：任务目标一致、要求完整覆盖、禁止事项没有被触碰或绕开。",
                "只要任何子任务扩大目标、遗漏验收要求、触碰禁止项，accepted 必须为 false。",
                f"mission_title: {mission_title}",
                f"mission_content: {mission_content}",
                f"q9_contract: {q9_contract}",
                f"generated_breakdown: {breakdown.model_dump(mode='json')}",
            ]
        )
        self._write_transcript(
            turn_id=turn_id,
            entry_type=AuditEventType.MODEL_PROVIDER_INVOKED,
            trace_id=f"{trace_id}:q9_alignment_review",
            payload={
                "provider": provider_key,
                "model": model_name,
                "prompt": prompt,
                "output_type": "PydanticAIQ9SubtaskAlignmentReview",
                "review_type": "q9_objective_requirement_prohibition_alignment",
            },
        )
        agent = Agent(
            model,
            output_type=PromptedOutput(
                PydanticAIQ9SubtaskAlignmentReview,
                name="PydanticAIQ9SubtaskAlignmentReview",
                description="Review whether generated subtasks obey Q9 objective, requirements, and prohibitions.",
            ),
            system_prompt=_Q9_ALIGNMENT_REVIEW_PROMPT,
            retries=0,
            output_retries=3,
            model_settings=ModelSettings(
                temperature=0.0,
                timeout=timeout_seconds,
                max_tokens=1200,
            ),
        )
        result = await agent.run(prompt)
        review = PydanticAIQ9SubtaskAlignmentReview.model_validate(result.output)
        self._write_transcript(
            turn_id=turn_id,
            entry_type=AuditEventType.MODEL_PROVIDER_COMPLETED,
            trace_id=f"{trace_id}:q9_alignment_review",
            payload={
                "provider": provider_key,
                "model": model_name,
                "result": review.model_dump(mode="json"),
                "usage": _usage_payload(result),
            },
        )
        if not review.accepted:
            raise RuntimeError(f"Q9 alignment LLM review rejected subtasks: {review.model_dump(mode='json')}")
        return review

    @staticmethod
    def _q9_contract_from_context(context: Optional[DecompositionContext]) -> Dict[str, Any]:
        if context is None:
            return {}
        raw = getattr(context, "metadata", None)
        if isinstance(raw, dict):
            for key in ("q9_contract", "q9_action_blueprint", "q9_task_profile", "q9_constraints"):
                value = raw.get(key)
                if isinstance(value, dict):
                    return value
        return {}

    def validate_breakdown(self, payload: Dict[str, Any]) -> PydanticAIAtomicTaskBreakdown:
        try:
            return PydanticAIAtomicTaskBreakdown.model_validate(payload)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid PydanticAI atomic task breakdown: {exc}") from exc

    def _build_model(self) -> tuple[Any, str, str, str, float]:
        try:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.ollama import OllamaProvider
            from pydantic_ai.providers.openai import OpenAIProvider
        except ModuleNotFoundError as exc:
            raise RuntimeError("pydantic-ai is not installed; install requirements.txt before task decomposition") from exc

        provider_key = str(
            self._model_provider_key
            or os.getenv("ZENTEX_TASK_PYDANTIC_AI_PROVIDER")
            or get_default_provider_key()
        ).strip()
        configs = load_provider_tool_configs()
        config = configs.get(provider_key)
        if config is None:
            raise RuntimeError(f"PydanticAI provider config not found: {provider_key}")

        model_name = str(
            self._model_name
            or os.getenv("ZENTEX_TASK_PYDANTIC_AI_MODEL")
            or config.default_model
        ).strip()
        api_base = str(self._api_base or os.getenv("ZENTEX_TASK_PYDANTIC_AI_API_BASE") or config.api_base).strip()
        timeout_seconds = float(
            self._request_timeout_seconds
            or os.getenv("ZENTEX_TASK_PYDANTIC_AI_TIMEOUT_SECONDS")
            or config.timeout_seconds
        )

        if provider_key == "ollama":
            base_url = api_base.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            return OpenAIChatModel(model_name, provider=OllamaProvider(base_url=base_url)), provider_key, model_name, base_url, timeout_seconds

        api_key = resolve_env_value(str(config.api_key_env or "")) or str(config.api_key_env or "")
        if not api_key:
            raise RuntimeError(f"PydanticAI provider {provider_key} requires api_key_env")
        return OpenAIChatModel(model_name, provider=OpenAIProvider(base_url=api_base, api_key=api_key)), provider_key, model_name, api_base, timeout_seconds

    def _build_user_prompt(
        self,
        *,
        mission_title: str,
        mission_content: str,
        context: Optional[DecompositionContext],
    ) -> str:
        memory_text = str(context.memory_text or "").strip() if context else ""
        parts = [
            "将下面 mission 拆成任务中心可落库执行的最小颗粒度子任务。",
            "每个子任务必须只包含一个不可再拆的动作；不能把“分析并执行并验证”合并在一个子任务里。",
            "每个子任务必须带验收条件 acceptance_criteria；如果需要资源，写入 required_resources。",
            "task_type 只能使用 cognitive_step、agent_delegation、system_action、intervention。",
            "coordination_mode 只能使用 sequential、parallel、bundle。",
            f"mission_title: {str(mission_title or '').strip()}",
            f"mission_content: {str(mission_content or '').strip()}",
            "输出示例：",
            '{"decomposition_goal":"检查 CSV 表头","granularity_policy":"single_atomic_operation_per_subtask","subtasks":[{"local_id":"step-1","title":"检查文件存在","task_type":"system_action","content":"确认目标 CSV 文件路径存在。","objective":"获得文件存在性的证据。","acceptance_criteria":["公开查询或执行回执证明文件存在"],"required_resources":["local_file_read"],"depends_on":[],"coordination_mode":"sequential"},{"local_id":"step-2","title":"读取表头","task_type":"system_action","content":"读取 CSV 文件第一行表头。","objective":"获得字段名列表。","acceptance_criteria":["执行回执包含表头字段列表"],"required_resources":["local_file_read"],"depends_on":["step-1"],"coordination_mode":"sequential"}]}',
        ]
        if memory_text:
            parts.append(f"memory_context: {memory_text[-1500:]}")
        return "\n".join(parts)

    def _to_task_payload(self, item: PydanticAIAtomicSubtask, *, trace_id: str) -> Dict[str, Any]:
        required_resources = list(item.required_resources)
        acceptance_criteria = list(item.acceptance_criteria)
        return {
            "local_id": item.local_id,
            "title": item.title,
            "task_type": item.task_type,
            "status": TaskStatus.ASSIGNMENT_PENDING,
            "content": item.content,
            "remarks": item.content,
            "objective": item.objective,
            "requirements": required_resources,
            "depends_on": list(item.depends_on),
            "coordination_mode": CoordinationMode(item.coordination_mode),
            "metadata": {
                "source": "G31A.PydanticAI.TaskSplitter",
                "source_module": "tasks.g31a.pydantic_ai",
                "minimum_granularity": "atomic_subtask",
                "pydantic_ai_trace_id": trace_id,
                "objective": item.objective,
                "acceptance_criteria": acceptance_criteria,
                "required_resources": required_resources,
                "assignment_status": "assignment_pending",
                "worker_dispatch_enabled": False,
            },
        }

    def _write_transcript(
        self,
        *,
        turn_id: str,
        entry_type: Any,
        trace_id: str,
        payload: Dict[str, Any],
    ) -> None:
        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=turn_id,
            entry_type=entry_type,
            timestamp=datetime.now(timezone.utc),
            source="zentex.tasks.pydantic_ai_decomposer",
            trace_id=trace_id,
            payload=payload,
        )


def _usage_payload(result: Any) -> Dict[str, Any]:
    usage = result.usage() if callable(getattr(result, "usage", None)) else getattr(result, "usage", None)
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    if isinstance(usage, dict):
        return usage
    return {}


_SYSTEM_PROMPT = """
你是 Zentex G31A 任务中心的最小颗粒度任务拆分器。
你的唯一职责是把 mission 拆成可落库、可追踪、可分配执行方的原子子任务。

硬性规则：
1. 每个子任务只能包含一个不可再拆的动作。
2. 禁止把分析、执行、验证合并成一个子任务。
3. 禁止自行执行任务、调用工具或编造执行结果。
4. 禁止跳过验收条件；每个子任务必须包含可查询、可验证的 acceptance_criteria。
5. required_resources 只能描述能力或资源需求，不得编造已经存在的执行方实例。
6. depends_on 只能引用前面已经出现的 local_id，避免依赖环。
7. 如果 mission 只需要一个动作，只输出一个子任务，不要为了凑数扩展。
""".strip()


_Q9_ALIGNMENT_REVIEW_PROMPT = """
你是 Zentex G31A 的 Q9 一致性审核器。
你必须独立审核 PydanticAI 生成的子任务列表是否严格遵守 Q9 输出。

审核规则：
1. 子任务目标必须继承 Q9 的 plan_objective / intent_objective，禁止扩大范围。
2. 子任务必须覆盖 Q9 的 requirements / success_criteria / verification_method。
3. 子任务不得触碰 Q9 prohibited_actions_acknowledged / task_prohibitions / redlines。
4. 如果 Q9 contract 缺失，则只能基于 mission_title 和 mission_content 审核，且 requirement_coverage_score 不得高于 0.85。
5. 任一子任务违反禁止项，prohibition_compliance_score 必须小于 1.0，accepted 必须为 false。
6. 输出必须是结构化审核结论，不得执行任务。
""".strip()
