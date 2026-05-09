from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from zentex.common.nine_questions_shared import build_caller_context

Q4ObjectiveLane = Literal["internal", "external"]
Q4SemanticType = Literal[
    "objective",
    "execution_step",
    "tool_call",
    "analysis",
    "constraint",
    "task_record",
    "placeholder_or_noise",
    "other_non_objective",
]
Q4_SEMANTIC_GUARD_MAX_ATTEMPTS = 3


class Q4ObjectiveSemanticAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_index: int = Field(..., ge=0)
    candidate_description: str
    semantic_type: Q4SemanticType
    is_objective: bool
    lane_boundary_ok: bool
    rejection_reason: str

    @field_validator("candidate_description", "rejection_reason")
    @classmethod
    def _text(cls, value: str) -> str:
        return str(value or "").strip()


class Q4ObjectiveSemanticGuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Q4ObjectiveSemanticGuardResult"]
    lane: Q4ObjectiveLane
    assessments: list[Q4ObjectiveSemanticAssessment] = Field(..., min_length=1)


class Q4ObjectiveSemanticGuardRejected(RuntimeError):
    def __init__(self, *, lane: Q4ObjectiveLane, rejected: list[dict[str, Any]]) -> None:
        self.lane = lane
        self.rejected = rejected
        super().__init__(
            f"q4_{lane}_objective_semantic_guard_rejected:"
            f"{json.dumps(rejected, ensure_ascii=False, separators=(',', ':'))}"
        )


class Q4ObjectiveSemanticGuardReviewFailed(RuntimeError):
    def __init__(self, *, lane: Q4ObjectiveLane, reason: str) -> None:
        self.lane = lane
        self.reason = reason
        super().__init__(f"q4_{lane}_objective_semantic_guard_review_failed:{reason}")


def build_q4_objective_semantic_guard_prompt(
    *,
    lane: Q4ObjectiveLane,
    candidate_set: dict[str, Any],
) -> str:
    lane_text = "内部认知轨" if lane == "internal" else "外部执行轨"
    objective_rule = (
        "内部认知轨的合格目标必须是记忆治理、反思质量、学习、策略补丁、价值提示、影子测试或自我进化等脑内维护/演化结果。"
        if lane == "internal"
        else "外部执行轨的合格目标必须是宏观业务结果、外部信息获取结果、文件/浏览器/SaaS/CLI/MCP/Connector/Agent 能力组合后的业务成果。"
    )
    lane_rule = (
        "如果候选描述真实要求外部 Agent、CLI、MCP、Connector、浏览器、文件或物理外部副作用，则 lane_boundary_ok 必须为 false。"
        if lane == "internal"
        else "如果候选描述真实要求内部记忆治理、反思、自我进化、价值提示或纯脑内维护，则 lane_boundary_ok 必须为 false。"
    )
    candidates_json = json.dumps(candidate_set, ensure_ascii=False, indent=2, default=str)
    return f"""### Zentex Q4 目标候选语义守门 LLM

你是 Q4 的语义拦截器，只判断候选描述是否真的是“目标”，而不是步骤、工具调用、分析、约束、任务记录或噪音。
必须直接输出 JSON，禁止输出解释性自然语言。

【当前轨道】
{lane_text}

【合格目标定义】
{objective_rule}

【必须拦截的非目标】
- 底层执行步骤，例如“加载 CSV”“打开网页”“写入数据库”“执行脚本”。
- 纯工具调用，例如“调用 Gemini”“请求 Agent”“通过 MCP 读取数据”。
- 分析/评估/检查/判断过程本身，而不是要达成的结果。
- 纯约束句，例如“确保附带证据”“必须遵守规范”“不要越权”。
- task_id、subtask_id、工单、资源锁、真实任务创建语义。
- 占位变量、字段名复述、无业务/无认知意义的噪音。

【轨道边界】
{lane_rule}

【待审查候选集合】
```json
{candidates_json}
```

【强制输出 JSON Schema】
第一层必须包含 `"type"` 和 `"lane"`，禁止只输出 assessments。

```json
{{
  "type": "Q4ObjectiveSemanticGuardResult",
  "lane": "{lane}",
  "assessments": [
    {{
      "candidate_index": 0,
      "candidate_description": "原样复制被审查的 candidate_description",
      "semantic_type": "enum: [objective, execution_step, tool_call, analysis, constraint, task_record, placeholder_or_noise, other_non_objective]",
      "is_objective": true,
      "lane_boundary_ok": true,
      "rejection_reason": "通过时为空字符串；拦截时说明为什么不是目标或为什么越过轨道边界"
    }}
  ]
}}
```
"""


def validate_q4_objective_semantic_guard_result(
    raw_output: dict[str, Any],
    *,
    lane: Q4ObjectiveLane,
    candidate_set: dict[str, Any],
) -> dict[str, Any]:
    try:
        validated = Q4ObjectiveSemanticGuardResult.model_validate(raw_output)
    except ValidationError as exc:
        raise Q4ObjectiveSemanticGuardReviewFailed(
            lane=lane,
            reason=f"validation_failed:{exc}",
        ) from exc
    payload = validated.model_dump(mode="json")
    if payload["lane"] != lane:
        raise Q4ObjectiveSemanticGuardReviewFailed(
            lane=lane,
            reason=f"lane_mismatch:{payload['lane']}",
        )

    candidates = candidate_set.get("objective_candidates") if isinstance(candidate_set, dict) else []
    if not isinstance(candidates, list) or not candidates:
        raise Q4ObjectiveSemanticGuardReviewFailed(lane=lane, reason="candidates_missing")

    expected = {
        index: str(item.get("candidate_description") or "").strip()
        for index, item in enumerate(candidates)
        if isinstance(item, dict)
    }
    actual: dict[int, str] = {}
    for item in payload["assessments"]:
        index = int(item["candidate_index"])
        if index in actual:
            raise RuntimeError(f"q4_{lane}_objective_semantic_guard_duplicate_index:{index}")
        actual[index] = str(item.get("candidate_description") or "").strip()
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise Q4ObjectiveSemanticGuardReviewFailed(
            lane=lane,
            reason=f"index_mismatch:missing={missing}:extra={extra}",
        )
    mismatched = [
        index
        for index, description in expected.items()
        if actual.get(index) != description
    ]
    if mismatched:
        raise Q4ObjectiveSemanticGuardReviewFailed(
            lane=lane,
            reason=f"description_mismatch:{mismatched}",
        )
    return payload


def run_q4_objective_semantic_guard(
    *,
    provider: Any,
    lane: Q4ObjectiveLane,
    candidate_set: dict[str, Any],
    trace_id: str,
    question_driver_refs: Any = None,
) -> dict[str, Any]:
    prompt = build_q4_objective_semantic_guard_prompt(lane=lane, candidate_set=candidate_set)
    from plugins.nine_questions.q4_what_can_i_do.semantic_guard_instructor_contract import (
        generate_q4_objective_semantic_guard_result_with_instructor_contract,
    )

    guard = generate_q4_objective_semantic_guard_result_with_instructor_contract(
        provider,
        prompt=prompt,
        context={},
        caller_context=build_caller_context(
            source_module=__name__,
            invocation_phase=f"nine_question_q4_{lane}_objective_semantic_guard",
            question_ref=f"q4:{lane}:semantic_guard",
            question_driver_refs=question_driver_refs,
            decision_id=f"q4-{lane}-semantic-guard:{uuid4().hex}",
            trace_id=f"{trace_id}:semantic-guard",
        ),
        metadata={
            "question_id": "q4",
            "scope": f"{lane}_semantic_guard",
            "output_schema": "Q4ObjectiveSemanticGuardResult",
            "max_json_repair_attempts": 0,
            "output_truncation_forbidden": True,
        },
        lane=lane,
        candidate_set=candidate_set,
    )
    rejected = [
        item
        for item in guard["assessments"]
        if not item.get("is_objective") or not item.get("lane_boundary_ok")
    ]
    if rejected:
        compact = [
            {
                "candidate_index": item.get("candidate_index"),
                "semantic_type": item.get("semantic_type"),
                "rejection_reason": item.get("rejection_reason"),
            }
            for item in rejected
        ]
        raise Q4ObjectiveSemanticGuardRejected(lane=lane, rejected=compact)
    return guard


def _prompt_with_semantic_retry_feedback(
    *,
    base_prompt: str,
    failures: list[dict[str, Any]],
) -> str:
    if not failures:
        return base_prompt
    feedback = json.dumps(failures, ensure_ascii=False, indent=2, default=str)
    return f"""{base_prompt}

--------------------------------------------------------------------------------
【上一轮 Q4 生成失败反馈】
下面候选或原始 JSON 未通过 Schema / Instructor / 语义审查。本轮必须重新生成完整 JSON，修正这些问题，并仍然满足原 Schema、数量、编号与目标语义要求。

```json
{feedback}
```
"""


def run_q4_objective_generation_with_semantic_guard(
    *,
    provider: Any,
    lane: Q4ObjectiveLane,
    prompt: str,
    generate_candidate_set: Callable[..., dict[str, Any]],
    trace_id: str,
    source_module: str,
    invocation_phase: str,
    question_ref: str,
    decision_id_prefix: str,
    metadata: dict[str, Any],
    question_driver_refs: Any = None,
    max_attempts: int = Q4_SEMANTIC_GUARD_MAX_ATTEMPTS,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        attempt_prompt = _prompt_with_semantic_retry_feedback(base_prompt=prompt, failures=failures)
        caller_context = build_caller_context(
            source_module=source_module,
            invocation_phase=invocation_phase,
            question_ref=question_ref,
            question_driver_refs=question_driver_refs,
            decision_id=f"{decision_id_prefix}:attempt-{attempt}:{uuid4().hex}",
            trace_id=f"{trace_id}:attempt-{attempt}",
        )
        try:
            candidate_set = generate_candidate_set(
                provider,
                prompt=attempt_prompt,
                context={},
                caller_context=caller_context,
                metadata={
                    **metadata,
                    "semantic_guard_attempt": attempt,
                    "semantic_guard_max_attempts": max_attempts,
                },
            )
        except RuntimeError as exc:
            if "_instructor_validation_failed:" not in str(exc):
                raise
            last_error = exc
            failures.append(
                {
                    "attempt": attempt,
                    "error": str(exc),
                    "reason": "validation_failed",
                    "required_fix": (
                        "Regenerate the full candidate set with at least 5 valid objective_candidates, "
                        "stable objective_number values, and all required fields."
                    ),
                }
            )
            if attempt >= max_attempts:
                raise
            continue
        if not candidate_set:
            raise RuntimeError(f"q4_{lane}_llm_output_empty")
        try:
            guard_result = run_q4_objective_semantic_guard(
                provider=provider,
                lane=lane,
                candidate_set=candidate_set,
                trace_id=trace_id,
                question_driver_refs=question_driver_refs,
            )
        except (Q4ObjectiveSemanticGuardRejected, Q4ObjectiveSemanticGuardReviewFailed) as exc:
            last_error = exc
            rejected = getattr(exc, "rejected", [])
            reason = getattr(exc, "reason", str(exc))
            failures.append(
                {
                    "attempt": attempt,
                    "error": str(exc),
                    "rejected": rejected,
                    "reason": reason,
                }
            )
            if attempt >= max_attempts:
                raise
            continue
        return {
            "candidate_set": candidate_set,
            "semantic_guard": guard_result,
            "attempt_count": attempt,
            "prompt": attempt_prompt,
        }
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"q4_{lane}_semantic_guard_retry_exhausted")
