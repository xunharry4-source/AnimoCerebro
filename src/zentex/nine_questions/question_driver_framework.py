from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zentex.common.nine_questions_contracts import MountedPluginInfo


@dataclass(frozen=True)
class NineQuestionDriverSpec:
    question_id: str
    question_text: str
    core_capability: str
    production_api: str
    sandbox_api: str


QUESTION_DRIVER_SPECS: dict[str, NineQuestionDriverSpec] = {
    "q1": NineQuestionDriverSpec(
        question_id="q1",
        question_text="我在那",
        core_capability="环境态势感知 + 工作区领域归类",
        production_api="/api/web/nine-questions/q1",
        sandbox_api="/api/web/nine-questions/q1/test",
    ),
    "q2": NineQuestionDriverSpec(
        question_id="q2",
        question_text="我有什么",
        core_capability="统一资产盘点（记忆/工具/权限/Agent/策略补丁）",
        production_api="/api/web/nine-questions/q2",
        sandbox_api="/api/web/nine-questions/q2/test",
    ),
    "q3": NineQuestionDriverSpec(
        question_id="q3",
        question_text="我是谁",
        core_capability="角色推演 + 身份内核装配",
        production_api="/api/web/nine-questions/q3",
        sandbox_api="/api/web/nine-questions/q3/test",
    ),
    "q4": NineQuestionDriverSpec(
        question_id="q4",
        question_text="我能干什么",
        core_capability="能力评估（声明/分析/验证三层，不可混淆）",
        production_api="/api/web/nine-questions/q4",
        sandbox_api="/api/web/nine-questions/q4/test",
    ),
    "q5": NineQuestionDriverSpec(
        question_id="q5",
        question_text="我不能干什么",
        core_capability="禁止边界 + 未授权动作 + 需升级审批动作判断",
        production_api="/api/web/nine-questions/q5",
        sandbox_api="/api/web/nine-questions/q5/test",
    ),
    "q6": NineQuestionDriverSpec(
        question_id="q6",
        question_text="What if I do it / 代价与后果是什么",
        core_capability="直接后果 + 传导后果 + 代价 + 可逆性 + 缓解/停止条件",
        production_api="/api/web/nine-questions/q6",
        sandbox_api="/api/web/nine-questions/q6/test",
    ),
    "q7": NineQuestionDriverSpec(
        question_id="q7",
        question_text="我的红线与约束是什么",
        core_capability="红线与约束评估（RedLineAssessment）",
        production_api="/api/web/nine-questions/q7",
        sandbox_api="/api/web/nine-questions/q7/test",
    ),
    "q8": NineQuestionDriverSpec(
        question_id="q8",
        question_text="我应该干什么",
        core_capability="任务优先级与目标生成（ObjectiveProfile）",
        production_api="/api/web/nine-questions/q8",
        sandbox_api="/api/web/nine-questions/q8/test",
    ),
    "q9": NineQuestionDriverSpec(
        question_id="q9",
        question_text="我应该怎么做",
        core_capability="行动计划与方法选择（ActionPlan）",
        production_api="/api/web/nine-questions/q9",
        sandbox_api="/api/web/nine-questions/q9/test",
    ),
}


def get_question_driver_spec(question_id: str) -> NineQuestionDriverSpec:
    try:
        return QUESTION_DRIVER_SPECS[question_id]
    except KeyError as exc:
        raise ValueError(f"Unknown nine-question driver: {question_id}") from exc


def question_driver_refs(question_id: str) -> list[str]:
    return [get_question_driver_spec(question_id).question_text]


def built_in_mounted_plugin(question_id: str) -> MountedPluginInfo:
    spec = get_question_driver_spec(question_id)
    return MountedPluginInfo(
        plugin_id=f"nine_questions.{question_id}.driver",
        display_name=f"{question_id.upper()} {spec.question_text}",
        source_kind="base",
        version="1.0.0",
        description=spec.core_capability,
        function_description=f"内置九问驱动器，负责回答“{spec.question_text}”并输出可追溯证据。",
        status="active",
    )


def ensure_mounted_plugins(question_id: str, mounted_plugins: list[Any] | None) -> list[Any]:
    plugins = list(mounted_plugins or [])
    if plugins:
        return plugins
    return [built_in_mounted_plugin(question_id)]


def ensure_question_driver_trace(
    question_id: str,
    payload: dict[str, Any] | None,
    *,
    context_data: dict[str, Any] | None = None,
    raw_response: dict[str, Any] | None = None,
    sandbox: bool = False,
) -> dict[str, Any]:
    spec = get_question_driver_spec(question_id)
    trace = dict(payload or {})
    invocations = trace.get("invocations")
    had_material_trace = (
        isinstance(invocations, list)
        and any(
            isinstance(item, dict)
            and any(item.get(key) not in (None, "", [], {}) for key in ("provider_name", "model", "raw_response", "prompt"))
            for item in invocations
        )
    ) or any(
        trace.get(key) not in (None, "", [], {})
        for key in ("provider_name", "model", "raw_response")
    )
    refs = [str(item) for item in trace.get("question_driver_refs") or [] if str(item).strip()]
    if spec.question_text not in refs:
        refs.append(spec.question_text)
    trace["question_driver_refs"] = refs
    if context_data is not None and not isinstance(trace.get("context_data"), dict):
        trace["context_data"] = context_data
    if sandbox and raw_response is not None and not isinstance(trace.get("raw_response"), dict):
        trace["raw_response"] = raw_response
    if sandbox:
        trace.setdefault("source_module", "nine_questions.sandbox")
        trace.setdefault("invocation_phase", f"{question_id}_sandbox_isolated_projection")
        trace.setdefault("system_prompt", "Nine-question sandbox isolated driver")
        trace.setdefault("prompt", spec.question_text)
        return trace

    if not had_material_trace:
        trace.setdefault("error_type", "llm_trace_missing")
        trace.setdefault(
            "error_message",
            f"No live LLM trace payload is available for {question_id}; production answer must be refreshed.",
        )
    return trace
