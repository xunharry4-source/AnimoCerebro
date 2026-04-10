"""Plugin-related utility functions for nine questions implementation.

This module handles:
- Plugin token humanization and display name derivation
- Mounted plugin discovery and listing
- Feature code mapping for questions
- Model provider resolution
- Runtime workspace snapshots

Functions should be imported and used by route_handlers.py via proper interfaces.
"""

from __future__ import annotations

from uuid import uuid4
from typing import Any
from pydantic import BaseModel

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.nine_questions.router import build_event
from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot
from zentex.web_console.contracts.nine_questions import (
    MountedPluginInfo,
    NineQuestionsRunResponse,
)
from zentex.web_console.contracts.plugins import PluginFeatureCatalogItem


def humanize_plugin_token(value: str) -> str:
    """Convert plugin token to human-readable display name."""
    text = str(value or "").strip()
    if not text:
        return "未命名插件"
    normalized = text.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ")
    return " ".join(chunk.capitalize() for chunk in normalized.split()) or text


def derive_plugin_display_name(
    *,
    plugin_id: str,
    feature_code: str | None,
    plugin: object | None,
    catalog_by_feature: dict[str, PluginFeatureCatalogItem],
) -> str:
    """Derive plugin display name from multiple sources."""
    display_name = str(getattr(plugin, "display_name", "") or "").strip()
    if display_name:
        return display_name
    if feature_code and feature_code in catalog_by_feature:
        return catalog_by_feature[feature_code].display_name
    return humanize_plugin_token(plugin_id)


def derive_plugin_function_description(
    *,
    plugin_id: str,
    feature_code: str | None,
    plugin: object | None,
    raw_description: str | None,
    source_kind: str,
    display_name: str,
) -> str:
    """Derive plugin function description from multiple sources."""
    description = str(raw_description or "").strip()
    purpose = str(getattr(plugin, "purpose", "") or "").strip()
    for candidate in (description, purpose):
        if candidate and candidate != plugin_id and candidate.lower() != plugin_id.lower():
            return candidate

    feature_explanations = {
        "core.model_provider": "负责将九问的结构化提示发送给大模型，并返回严格 JSON 结果。",
        "host.telemetry": "负责采集宿主机内存压力、网络健康度和运行环境状态，供 Q1 使用。",
        "sensory.ingest": "负责接收外部输入或环境信号，形成九问推演的原始证据。",
        "sensory.sanitize": "负责清洗输入信号，降低提示注入和脏数据污染风险。",
        "sensory.interpret": "负责把原始信号解释为结构化环境语义，供九问使用。",
        "nine_questions.q1": "负责判断当前系统所处环境、工作区结构和外部态势，回答我在哪。",
        "nine_questions.q2": "负责结合 Q1 态势与身份约束，判断当前系统扮演的角色与使命边界，回答我是谁。",
        "nine_questions.q3": "负责盘点当前可用工具、Agent、工作区与权限资产，回答我有什么。",
        "nine_questions.q4": "负责基于真实资产与执行域，判断系统当前真正具备的行动能力，回答我能做什么。",
        "nine_questions.q5": "负责基于授权与合规边界，对可行动作做减法裁剪，回答我被允许做什么。",
        "nine_questions.q6": "负责识别即使物理上可行也绝对不能触碰的红线与禁区，回答我即使能做也不该做什么。",
        "nine_questions.q7": "负责在主路径受阻时生成备选策略、降级路径和协作切换方案，回答我还可以做什么。",
        "nine_questions.q8": "负责汇总 Q1-Q7 的约束与能力，生成当前最优主目标和任务队列，回答我现在应该做什么。",
        "nine_questions.q9": "负责根据 Q1-Q8 的状态确定行动姿态、节奏和确认策略，回答我应该如何行动。",
        "weights:subjective_preferences": "负责提供风险偏好与主观权重，用于调节推演倾向。",
        "identity:package_loader": "负责加载身份角色包、约束包和经验包，帮助 Q2 构建身份内核。",
        "execution.system": "负责系统级执行域能力，用于评估本地系统相关动作。",
        "execution.browser": "负责浏览器执行域能力，用于评估网页访问和页面交互动作。",
        "redline.core": "负责提供全局红线与禁区规则，约束高风险动作。",
        "alternative.core": "负责提供主路径受阻时的备选策略、降级路径和协作切换建议。",
        "objective.core": "负责提供主目标编排与任务队列重排能力，支撑 Q8 的决策聚合。",
        "posture.core": "负责提供行动姿态、节奏和确认策略建议，支撑 Q9 的风格控制。",
    }
    if feature_code and feature_code in feature_explanations:
        return feature_explanations[feature_code]
    if source_kind == "functional":
        return f"{display_name} 负责为当前九问提供底层能力支撑。"
    if source_kind == "patch":
        return f"{display_name} 负责在主算子之上补充增强推理能力。"
    return f"{display_name} 是当前问题的主认知算子。"


def get_mounted_plugins_for_question(
    runtime: Any,
    q_id: str,
    plugin_feature_catalog: list[PluginFeatureCatalogItem] | None = None,
) -> list[MountedPluginInfo]:
    """
    Expose the truth of capability patch mountings for the frontend.
    """
    registry: Any = (
        getattr(runtime, "cognitive_tool_registry", None)
        or getattr(runtime, "tool_registry", None)
    )
    managed_records = getattr(runtime, "managed_plugin_records", {}) or {}
    catalog_by_feature = {
        item.feature_code: item
        for item in (plugin_feature_catalog or [])
        if isinstance(item, PluginFeatureCatalogItem)
    }

    mounted: list[MountedPluginInfo] = []
    seen_plugin_ids: set[str] = set()

    if registry is not None:
        feature_code = f"nine_questions.{q_id}"
        for reg in registry.list_registrations():
            if reg.spec.feature_code != feature_code and reg.spec.behavior_key != q_id:
                continue

            # Using attribute check to avoid direct import coupling
            source_kind = "base"
            if hasattr(reg.spec, "is_capability_patch") and reg.spec.is_capability_patch:
                source_kind = "patch"
            elif "patch" in reg.plugin_id.lower() or "enhancement" in reg.plugin_id.lower():
                source_kind = "patch"
            raw_description = reg.description or reg.spec.purpose
            display_name = derive_plugin_display_name(
                plugin_id=reg.plugin_id,
                feature_code=getattr(reg.spec, "feature_code", None),
                plugin=reg.spec,
                catalog_by_feature=catalog_by_feature,
            )
            function_description = derive_plugin_function_description(
                plugin_id=reg.plugin_id,
                feature_code=getattr(reg.spec, "feature_code", None),
                plugin=reg.spec,
                raw_description=raw_description,
                source_kind=source_kind,
                display_name=display_name,
            )

            mounted.append(
                MountedPluginInfo(
                    plugin_id=reg.plugin_id,
                    display_name=display_name,
                    source_kind=source_kind,
                    version=reg.spec.version,
                    description=raw_description,
                    function_description=function_description,
                    status=reg.spec.status.value if hasattr(reg.spec.status, "value") else str(reg.spec.status),
                )
            )
            seen_plugin_ids.add(reg.plugin_id)

    dependency_feature_codes = functional_feature_codes_for_question(q_id)
    if isinstance(managed_records, dict):
        for record in managed_records.values():
            feature_code = getattr(record, "feature_code", None)
            plugin = getattr(record, "plugin", None)
            if feature_code not in dependency_feature_codes or plugin is None:
                continue
            plugin_id = str(getattr(plugin, "plugin_id", "") or "")
            if not plugin_id or plugin_id in seen_plugin_ids:
                continue
            raw_description = str(getattr(record, "description", None) or getattr(plugin, "purpose", None) or plugin_id)
            display_name = derive_plugin_display_name(
                plugin_id=plugin_id,
                feature_code=feature_code,
                plugin=plugin,
                catalog_by_feature=catalog_by_feature,
            )
            function_description = derive_plugin_function_description(
                plugin_id=plugin_id,
                feature_code=feature_code,
                plugin=plugin,
                raw_description=raw_description,
                source_kind="functional",
                display_name=display_name,
            )
            mounted.append(
                MountedPluginInfo(
                    plugin_id=plugin_id,
                    display_name=display_name,
                    source_kind="functional",
                    version=str(getattr(plugin, "version", "") or "unknown"),
                    description=raw_description,
                    function_description=function_description,
                    status=(
                        getattr(getattr(plugin, "status", None), "value", None)
                        or str(getattr(plugin, "status", "unknown"))
                    ),
                )
            )
            seen_plugin_ids.add(plugin_id)

    # Ensure stable ordering: base first, then alphabetically by plugin_id
    source_order = {"base": 0, "patch": 1, "functional": 2}
    return sorted(mounted, key=lambda x: (source_order.get(x.source_kind, 9), x.plugin_id))


def functional_feature_codes_for_question(q_id: str) -> set[str]:
    """Get feature codes required for a question."""
    feature_codes: set[str] = {"core.model_provider"}
    if q_id == "q1":
        feature_codes.update({"host.telemetry", "sensory.ingest", "sensory.sanitize", "sensory.interpret"})
    elif q_id == "q2":
        feature_codes.update({"identity.role", "identity.constraint", "weights:subjective_preferences"})
    elif q_id == "q3":
        feature_codes.update({"execution.system", "execution.browser"})
    elif q_id == "q4":
        feature_codes.update({"execution.system", "execution.browser"})
    elif q_id == "q6":
        feature_codes.update({"identity.constraint", "redline.core"})
    elif q_id == "q7":
        feature_codes.update({"alternative.core"})
    elif q_id == "q8":
        feature_codes.update({"objective.core"})
    elif q_id == "q9":
        feature_codes.update({"posture.core"})
    return feature_codes


def build_runtime_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: Any,
    execution_registry: object | None,
    task_service: object | None,
    plugin_service: Any | None = None,
    host_telemetry_plugin: object | None = None,
) -> dict[str, object]:
    """Build runtime workspace snapshot for nine questions."""
    return build_runtime_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
        task_service=task_service,
        plugin_service=plugin_service,
        environment_summary="frontend requested a full nine-question refresh",
        host_telemetry_plugin=host_telemetry_plugin,
    )


def resolve_active_model_provider(runtime: Any, request: Any) -> ModelProviderSpec:
    """Resolve the active model provider from available records."""
    records = getattr(request.app.state, "managed_plugin_records", None)
    if not isinstance(records, dict):
        records = getattr(runtime, "managed_plugin_records", None)
    if not isinstance(records, dict):
        raise PluginNotBoundError("Managed plugin records are not attached to the runtime")

    candidates: list[ModelProviderSpec] = []
    for record in records.values():
        plugin = getattr(record, "plugin", None)
        if isinstance(plugin, ModelProviderSpec) and plugin.status == PluginLifecycleStatus.ACTIVE:
            candidates.append(plugin)

    if not candidates:
        raise PluginNotBoundError("No active model provider is available for sandbox execution")

    candidates.sort(key=lambda plugin: (plugin.version, plugin.plugin_id), reverse=True)
    return candidates[0]


def resolve_active_nine_question_tool(registry: Any, question_id: str):
    """
    标准规范：返回完整的registration对象（包含plugin_id），而不是仅返回spec。
    
    调用者可以从registration获取plugin_id并通过标准框架获取插件实例。
    """
    feature_code = f"nine_questions.{question_id}"
    candidates = [
        registration
        for registration in registry.list_registrations()
        if registration.status == PluginLifecycleStatus.ACTIVE
        and getattr(registration.spec, "feature_code", None) == feature_code
    ]
    if not candidates:
        raise PluginNotBoundError(f"No active nine-question tool is bound for {feature_code}")
    candidates.sort(key=lambda registration: (registration.spec.version, registration.plugin_id), reverse=True)
    return candidates[0]


def run_full_nine_questions(
    *,
    request: Any,
    runtime: Any,
    session: Any,
    state: Any,
    registry: Any,
    refresh_reason: str,
) -> NineQuestionsRunResponse:
    """Execute full nine questions refresh from frontend request."""
    import os
    
    workspace_root = str(getattr(runtime, "default_workspace", ".") or os.getcwd())
    startup_context = build_runtime_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=registry,
        execution_registry=getattr(request.app.state, "execution_registry", None),
        task_service=getattr(request.app.state, "task_service", None),
        plugin_service=getattr(runtime, "plugin_service", None),
        host_telemetry_plugin=next(
            (
                getattr(record, "plugin", None)
                for record in getattr(request.app.state, "managed_plugin_records", {}).values()
                if getattr(record, "feature_code", None) == "host.telemetry"
                and getattr(getattr(record, "plugin", None), "status", None)
                == PluginLifecycleStatus.ACTIVE
            ),
            None,
        ),
    )
    session.last_context_snapshot = dict(startup_context)
    trace_id = f"manual-nine-questions:{uuid4().hex}"
    event = build_event(
        event_type="cold_start",
        reason=refresh_reason,
        trace_id=trace_id,
        dirty_questions=runtime.nine_question_router.derive_dirty_questions_for_event("cold_start"),
        payload={"workspace_root": workspace_root},
    )
    runtime.nine_question_router.publish(state, event)
    runtime.refresh_nine_question_state(
        question_driver_refs=["frontend:nine-questions", refresh_reason],
        refresh_reason=refresh_reason,
        context_snapshot=startup_context,
        active_constraints=[],
    )
    if not getattr(runtime, "managed_plugin_records", None):
        managed_records = getattr(request.app.state, "managed_plugin_records", None)
        if isinstance(managed_records, dict):
            runtime.managed_plugin_records = managed_records
    from zentex.runtime.service import get_runtime_service
    runtime_service = get_runtime_service()
    
    runtime.process_nine_question_events(
        session=session,
        turn_id=f"turn-{refresh_reason}",
    )
    return NineQuestionsRunResponse(
        started=True,
        trace_id=trace_id,
        refresh_reason=refresh_reason,
        snapshot_version=state.snapshot_version,
        revision=state.revision,
    )
