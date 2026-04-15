"""
Plugin utilities for nine questions router.

Contains functions for handling plugin information, display names,
and feature code mappings.
"""

from typing import Any

from zentex.plugins.service import (
    query_all_plugins_by_operational_status,
    query_cognitive_plugin_functionals_by_operational_status,
)
from zentex.web_console.contracts.nine_questions import MountedPluginInfo
from zentex.plugins.contracts import PluginLifecycleStatus


# Feature code explanations for plugin function descriptions
FEATURE_EXPLANATIONS = {
    "core.model_provider": "负责将九问的结构化提示发送给大模型,并返回严格 JSON 结果。",
    "host.telemetry": "负责采集宿主机内存压力、网络健康度和运行环境状态,供 Q1 使用。",
    "sensory.ingest": "负责接收外部输入或环境信号,形成九问推演的原始证据。",
    "sensory.sanitize": "负责清洗输入信号,降低提示注入和脏数据污染风险。",
    "sensory.interpret": "负责把原始信号解释为结构化环境语义,供九问使用。",
    "nine_questions.q1": "负责判断当前系统所处环境、工作区结构和外部态势,回答'我在哪'。",
    "nine_questions.q2": "负责结合 Q1 态势与身份约束,判断当前系统扮演的角色与使命边界,回答'我是谁'。",
    "nine_questions.q3": "负责盘点当前可用工具、Agent、工作区与权限资产,回答'我有什么'。",
    "nine_questions.q4": "负责基于真实资产与执行域,判断系统当前真正具备的行动能力,回答'我能做什么'。",
    "nine_questions.q5": "负责基于授权与合规边界,对可行动作做减法裁剪,回答'我被允许做什么'。",
    "nine_questions.q6": "负责识别即使物理上可行也绝对不能触碰的红线与禁区,回答'我即使能做也不该做什么'。",
    "nine_questions.q7": "负责在主路径受阻时生成备选策略、降级路径和协作切换方案,回答'我还可以做什么'。",
    "nine_questions.q8": "负责汇总 Q1-Q7 的约束与能力,生成当前最优主目标和任务队列,回答'我现在应该做什么'。",
    "nine_questions.q9": "负责根据 Q1-Q8 的状态确定行动姿态、节奏和确认策略,回答'我应该如何行动'。",
    "weights:subjective_preferences": "负责提供风险偏好与主观权重,用于调节推演倾向。",
    "identity:package_loader": "负责加载身份角色包、约束包和经验包,帮助 Q2 构建身份内核。",
    "execution.system": "负责系统级执行域能力,用于评估本地系统相关动作。",
    "execution.browser": "负责浏览器执行域能力,用于评估网页访问和页面交互动作。",
    "redline.core": "负责提供全局红线与禁区规则,约束高风险动作。",
    "alternative.core": "负责提供主路径受阻时的备选策略、降级路径和协作切换建议。",
    "objective.core": "负责提供主目标编排与任务队列重排能力,支撑 Q8 的决策聚合。",
    "posture.core": "负责提供行动姿态、节奏和确认策略建议,支撑 Q9 的风格控制。",
}


def _humanize_plugin_token(value: str) -> str:
    """Convert plugin token to human-readable name."""
    text = str(value or "").strip()
    if not text:
        return "未命名插件"
    normalized = text.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ")
    return " ".join(chunk.capitalize() for chunk in normalized.split()) or text


def _derive_plugin_display_name(
    *,
    plugin_id: str,
    feature_code: str | None,
    plugin: object | None,
    catalog_by_feature: dict[str, Any],
) -> str:
    """Derive display name for a plugin from multiple sources."""
    display_name = str(getattr(plugin, "display_name", "") or "").strip()
    if display_name:
        return display_name
    if feature_code and feature_code in catalog_by_feature:
        return catalog_by_feature[feature_code].display_name
    return _humanize_plugin_token(plugin_id)


def _derive_plugin_function_description(
    *,
    plugin_id: str,
    feature_code: str | None,
    plugin: object | None,
    raw_description: str | None,
    source_kind: str,
    display_name: str,
) -> str:
    """Derive function description for a plugin."""
    description = str(raw_description or "").strip()
    purpose = str(getattr(plugin, "purpose", "") or "").strip()
    for candidate in (description, purpose):
        if candidate and candidate != plugin_id and candidate.lower() != plugin_id.lower():
            return candidate

    if feature_code and feature_code in FEATURE_EXPLANATIONS:
        return FEATURE_EXPLANATIONS[feature_code]
    if source_kind == "functional":
        return f"{display_name} 负责为当前九问提供底层能力支撑。"
    if source_kind == "patch":
        return f"{display_name} 负责在主算子之上补充增强推理能力。"
    return f"{display_name} 是当前问题的主认知算子。"


def _get_mounted_plugins_for_question(
    runtime: Any,
    q_id: str,
    plugin_feature_catalog: list[Any] | None = None,
) -> list[MountedPluginInfo]:
    """
    Expose the truth of capability patch mountings for the frontend.
    """
    registry: Any = (
        getattr(runtime, "cognitive_tool_registry", None)
        or getattr(runtime, "tool_registry", None)
    )
    catalog_by_feature = {
        item.feature_code: item
        for item in (plugin_feature_catalog or [])
        if isinstance(item, dict)
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
            display_name = _derive_plugin_display_name(
                plugin_id=reg.plugin_id,
                feature_code=getattr(reg.spec, "feature_code", None),
                plugin=reg.spec,
                catalog_by_feature=catalog_by_feature,
            )
            function_description = _derive_plugin_function_description(
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

    dependency_feature_codes = _functional_feature_codes_for_question(q_id)
    plugin_service: Any = getattr(runtime, "plugin_service", None)
    if plugin_service is not None:
        try:
            service_plugins = {
                str(item.get("plugin_id") or ""): item
                for item in query_all_plugins_by_operational_status(
                    plugin_service,
                    category="functional",
                    operational_status="enabled",
                    limit=500,
                )
                if str(item.get("plugin_id") or "").strip()
            }
        except Exception:
            service_plugins = {}

        cognitive_candidates: list[str] = []
        if registry is not None:
            feature_code = f"nine_questions.{q_id}"
            for reg in registry.list_registrations():
                if reg.spec.feature_code == feature_code or reg.spec.behavior_key == q_id:
                    cognitive_candidates.append(reg.plugin_id)

        for cognitive_plugin_id in cognitive_candidates:
            try:
                relations = list(
                    query_cognitive_plugin_functionals_by_operational_status(
                        plugin_service,
                        cognitive_plugin_id,
                        operational_status="enabled",
                        limit=200,
                    )
                    or []
                )
            except Exception:
                continue

            for relation in relations:
                functional_id = str(
                    relation.get("plugin_id")
                    or relation.get("functional_plugin_id")
                    or ""
                ).strip()
                if not functional_id or functional_id in seen_plugin_ids:
                    continue

                plugin_row = service_plugins.get(functional_id, {})
                if not isinstance(plugin_row, dict):
                    plugin_row = {}
                feature_code = str(plugin_row.get("feature_code") or "").strip() or None
                if feature_code and feature_code not in dependency_feature_codes:
                    continue

                raw_description = str(
                    plugin_row.get("description")
                    or plugin_row.get("purpose")
                    or relation.get("description")
                    or functional_id
                )
                display_name = _derive_plugin_display_name(
                    plugin_id=functional_id,
                    feature_code=feature_code,
                    plugin=None,
                    catalog_by_feature=catalog_by_feature,
                )
                function_description = _derive_plugin_function_description(
                    plugin_id=functional_id,
                    feature_code=feature_code,
                    plugin=None,
                    raw_description=raw_description,
                    source_kind="functional",
                    display_name=display_name,
                )
                mounted.append(
                    MountedPluginInfo(
                        plugin_id=functional_id,
                        display_name=display_name,
                        source_kind="functional",
                        version=str(plugin_row.get("version", "") or "unknown"),
                        description=raw_description,
                        function_description=function_description,
                        status=str(plugin_row.get("status", "") or "unknown"),
                    )
                )
                seen_plugin_ids.add(functional_id)

    # Ensure stable ordering: base first, then alphabetically by plugin_id
    source_order = {"base": 0, "patch": 1, "functional": 2}
    return sorted(mounted, key=lambda x: (source_order.get(x.source_kind, 9), x.plugin_id))


def _functional_feature_codes_for_question(q_id: str) -> set[str]:
    """Get the set of functional feature codes required for a question."""
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
