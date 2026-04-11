from __future__ import annotations

from datetime import datetime, timezone
import itertools
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, Request

from zentex.common.plugin_registry import AbstractPluginRegistry, PluginNotBoundError
from zentex.core.plugin_base import BasePluginSpec, PluginLifecycleStatus
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from typing import Literal

from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    ForceEnablePluginResponse,
    FunctionalPluginDetailResponse,
    ManagedForceEnableResult,
    ManagedPluginRecord,
    ManagedPluginTestSandbox,
    PluginFeatureCatalogItem,
    PluginFeatureGroupItem,
    PluginRelationshipItem,
    PluginVersionHistoryItem,
    PluginTestResponse,
    FEATURE_GUIDE_PATHS,
    PLUGIN_FAMILY_GUIDE_PATHS,
)


logger = logging.getLogger(__name__)
_MANAGED_PLUGIN_INTERNAL_REVISION = itertools.count(1)


def _humanize_plugin_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "未命名插件"
    normalized = text.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ")
    return " ".join(chunk.capitalize() for chunk in normalized.split()) or text


def _derive_plugin_description(
    *,
    plugin_id: str,
    feature_code: str | None,
    purpose: str | None,
    raw_description: str | None,
    plugin_kind: str,
) -> str:
    feature_explanations = {
        "core.model_provider": "负责将结构化提示发送给大模型，并返回严格 JSON 结果。",
        "host.telemetry": "负责采集宿主机内存压力、网络健康度和运行环境状态，供环境判断使用。",
        "sensory.ingest": "负责接收外部输入或环境信号，形成可供推理使用的原始证据。",
        "sensory.sanitize": "负责清洗输入信号，降低提示注入和脏数据污染风险。",
        "sensory.interpret": "负责把原始信号解释为结构化环境语义，供认知插件使用。",
        "nine_questions.q1": "负责判断当前系统所处环境、工作区结构和外部态势，回答“我在哪”。",
        "nine_questions.q2": "负责结合环境态势与身份约束，判断当前系统扮演的角色与使命边界，回答“我是谁”。",
        "nine_questions.q3": "负责盘点当前可用工具、Agent、工作区与权限资产，回答“我有什么”。",
        "nine_questions.q4": "负责基于真实资产与执行域，判断系统当前真正具备的行动能力，回答“我能做什么”。",
        "nine_questions.q5": "负责基于授权与合规边界，对可行动作做减法裁剪，回答“我被允许做什么”。",
        "nine_questions.q6": "负责识别即使物理上可行也绝对不能触碰的红线与禁区，回答“我即使能做也不该做什么”。",
        "nine_questions.q7": "负责在主路径受阻时生成备选策略、降级路径和协作切换方案，回答“我还可以做什么”。",
        "nine_questions.q8": "负责汇总 Q1-Q7 的约束与能力，生成当前最优主目标和任务队列，回答“我现在应该做什么”。",
        "nine_questions.q9": "负责根据 Q1-Q8 的状态确定行动姿态、节奏和确认策略，回答“我应该如何行动”。",
        "weights:subjective_preferences": "负责提供风险偏好与主观权重，用于调节推演倾向。",
        "identity:package_loader": "负责加载身份角色包、约束包和经验包，帮助构建身份内核。",
        "execution.system": "负责系统级执行域能力，用于评估本地系统相关动作。",
        "execution.browser": "负责浏览器执行域能力，用于评估网页访问和页面交互动作。",
    }
    if feature_code and feature_code in feature_explanations:
        return feature_explanations[feature_code]

    for candidate in (str(raw_description or "").strip(), str(purpose or "").strip()):
        if candidate and candidate != plugin_id and candidate.lower() != plugin_id.lower():
            return candidate

    display_name = _humanize_plugin_token(plugin_id)
    if plugin_kind == "cognitive_tool":
        return f"{display_name} 是当前问题的主认知算子。"
    return f"{display_name} 负责为当前认知链路提供底层能力支撑。"


def _normalize_runtime_status(status: object, *, is_instantiated: bool) -> str:
    status_text = str(getattr(status, "value", status) or "").strip().lower()
    if is_instantiated and status_text in {"", "candidate", "sandbox_verified", "unknown"}:
        return PluginLifecycleStatus.ACTIVE.value
    if not status_text:
        return "unknown"
    return status_text


def build_plugin_payloads(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord] | None = None,
) -> List[CognitivePluginStatusItem]:
    items: Dict[str, CognitivePluginStatusItem] = {}
    protected_plugin_ids = cognitive_registry.protected_plugin_ids
    for registration in cognitive_registry.list_registrations():
        description = _derive_plugin_description(
            plugin_id=registration.spec.plugin_id,
            feature_code=registration.spec.feature_code,
            purpose=registration.spec.purpose,
            raw_description=registration.spec.purpose,
            plugin_kind=registration.spec.plugin_kind(),
        )
        items[registration.spec.plugin_id] = CognitivePluginStatusItem(
            tool_id=registration.spec.plugin_id,
            feature_code=registration.spec.feature_code,
            supports_multiple_plugins=registration.spec.supports_multiple_plugins,
            plugin_kind=registration.spec.plugin_kind(),
            version=registration.spec.version,
            status=_normalize_runtime_status(
                registration.spec.status.value,
                is_instantiated=True,
            ),
            health_status=registration.spec.health_status.value if registration.spec.health_status is not None else None,
            purpose=registration.spec.purpose,
            description=description,
            used_in=list(registration.spec.trigger_conditions),
            is_default=registration.spec.plugin_id in protected_plugin_ids,
            is_official_release=registration.spec.is_official_release,
            can_force_enable=registration.spec.plugin_id not in protected_plugin_ids,
            can_force_disable=cognitive_registry.can_force_disable_plugin(registration.spec.plugin_id),
            can_delete=registration.spec.plugin_id not in protected_plugin_ids,
            usage_count=registration.usage_count,
            failure_count=registration.failure_count,
            rollback_conditions=list(getattr(registration.spec, "rollback_conditions", []) or []),
            trigger_conditions=list(registration.spec.trigger_conditions),
            required_context=list(getattr(registration.spec, "required_context", []) or []),
            created_at=registration.created_at,
            updated_at=registration.updated_at,
            started_at=registration.started_at,
            stopped_at=registration.stopped_at,
            last_used_at=registration.last_used_at,
        )

    if managed_records is None:
        managed_records = {}

    for record in managed_records.values():
        plugin = record.plugin
        is_instantiated = plugin.plugin_id in getattr(plugin_registry, "_plugins", {}) if plugin_registry is not None else False
        description = _derive_plugin_description(
            plugin_id=plugin.plugin_id,
            feature_code=record.feature_code,
            purpose=str(getattr(plugin, "purpose", "") or ""),
            raw_description=record.description,
            plugin_kind=plugin.plugin_kind(),
        )
        items[plugin.plugin_id] = CognitivePluginStatusItem(
            tool_id=plugin.plugin_id,
            feature_code=record.feature_code,
            supports_multiple_plugins=record.supports_multiple_plugins,
            plugin_kind=plugin.plugin_kind(),
            version=str(getattr(plugin, "version", "1.0.0")),
            status=_normalize_runtime_status(
                getattr(plugin, "status", None),
                is_instantiated=is_instantiated,
            ),
            health_status=getattr(plugin, "health_status", None).value if getattr(plugin, "health_status", None) else None,
            purpose=str(getattr(plugin, "purpose", "") or ""),
            description=description,
            used_in=list(getattr(plugin, "used_in", []) or []),
            is_default=record.is_default,
            is_official_release=record.is_official_release,
            can_force_enable=plugin.plugin_id not in cognitive_registry.protected_plugin_ids,
            can_force_disable=can_force_disable_managed_plugin(record, managed_records),
            can_delete=plugin.plugin_id not in cognitive_registry.protected_plugin_ids,
            usage_count=0,
            failure_count=0,
            rollback_conditions=list(getattr(plugin, "rollback_conditions", []) or []),
            trigger_conditions=list(getattr(plugin, "trigger_conditions", []) or []),
            required_context=list(getattr(plugin, "required_context", []) or []),
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            stopped_at=record.stopped_at,
            last_used_at=None,
        )

    result = list(items.values())
    result.sort(key=lambda item: (item.plugin_kind, item.feature_code, item.tool_id))
    return result


def derive_feature_code(plugin: BasePluginSpec) -> str:
    feature_code = getattr(plugin, "feature_code", None)
    if feature_code:
        return str(feature_code)
    behavior_key = getattr(plugin, "behavior_key", None)
    if behavior_key:
        return str(behavior_key)
    return plugin.plugin_id


def derive_supports_multiple_plugins(plugin: BasePluginSpec) -> bool:
    return bool(getattr(plugin, "supports_multiple_plugins", False))


def build_managed_plugin_record(
    plugin: BasePluginSpec,
    *,
    feature_code: Optional[str] = None,
    supports_multiple_plugins: Optional[bool] = None,
    is_default: bool = False,
    is_official_release: bool = True,
    source_kind: Literal["builtin", "user", "test_stub"] = "builtin",
    description: Optional[str] = None,
) -> ManagedPluginRecord:
    timestamp = datetime.now(timezone.utc)
    return ManagedPluginRecord(
        plugin=plugin,
        internal_revision_id=next(_MANAGED_PLUGIN_INTERNAL_REVISION),
        source_kind=source_kind,
        description=(description or getattr(plugin, "purpose", "") or "").strip() or plugin.plugin_id,
        feature_code=feature_code or derive_feature_code(plugin),
        supports_multiple_plugins=(
            derive_supports_multiple_plugins(plugin)
            if supports_multiple_plugins is None
            else supports_multiple_plugins
        ),
        is_default=is_default,
        is_official_release=is_official_release,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp if plugin.status == PluginLifecycleStatus.ACTIVE else None,
        stopped_at=timestamp if plugin.status == PluginLifecycleStatus.REVOKED else None,
    )


def managed_behavior_records(managed_records: Dict[str, ManagedPluginRecord]) -> Dict[str, List[ManagedPluginRecord]]:
    behavior_records: Dict[str, List[ManagedPluginRecord]] = {}
    for record in managed_records.values():
        behavior_key = str(getattr(record.plugin, "behavior_key", "") or record.feature_code)
        behavior_records.setdefault(behavior_key, []).append(record)
    return behavior_records


def resolve_managed_bound_plugins(
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
) -> Set[str]:
    if plugin_registry is None:
        return set()
    bound: Set[str] = set()
    for record in managed_records.values():
        try:
            plugin_registry.resolve_bound_plugin(record.feature_code)
        except PluginNotBoundError:
            continue
        except Exception:
            continue
        bound.add(record.plugin.plugin_id)
    return bound


def create_managed_plugin_test_sandbox(
    request: Request,
    managed_records: Dict[str, ManagedPluginRecord],
) -> ManagedPluginTestSandbox:
    sandbox = ManagedPluginTestSandbox(records=dict(managed_records))
    request.app.state.managed_plugin_test_sandbox = sandbox
    return sandbox


def version_key(version: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for chunk in version.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def resolve_managed_disable_replacement(
    disabled: ManagedPluginRecord,
    behavior_registrations: List[ManagedPluginRecord],
) -> Optional[ManagedPluginRecord]:
    previous_official = [
        record
        for record in behavior_registrations
        if record.plugin.plugin_id != disabled.plugin.plugin_id
        and record.is_official_release
        and record.plugin.status != PluginLifecycleStatus.REVOKED
        and version_key(str(getattr(record.plugin, "version", "0")))
        < version_key(str(getattr(disabled.plugin, "version", "0")))
    ]
    if previous_official:
        return max(
            previous_official,
            key=lambda record: version_key(str(getattr(record.plugin, "version", "0"))),
        )

    official = [
        record
        for record in behavior_registrations
        if record.plugin.plugin_id != disabled.plugin.plugin_id
        and record.is_official_release
        and record.plugin.status != PluginLifecycleStatus.REVOKED
    ]
    if official:
        return max(official, key=lambda record: version_key(str(getattr(record.plugin, "version", "0"))))

    defaults = [
        record
        for record in behavior_registrations
        if record.plugin.plugin_id != disabled.plugin.plugin_id
        and record.is_default
        and record.plugin.status != PluginLifecycleStatus.REVOKED
    ]
    if defaults:
        return max(defaults, key=lambda record: version_key(str(getattr(record.plugin, "version", "0"))))
    return None


def can_force_disable_managed_plugin(
    record: ManagedPluginRecord,
    managed_records: Dict[str, ManagedPluginRecord],
) -> bool:
    if record.is_default:
        return False
    behavior_key = str(getattr(record.plugin, "behavior_key", "") or record.feature_code)
    behavior_registrations = managed_behavior_records(managed_records).get(behavior_key, [])
    replacement = resolve_managed_disable_replacement(record, behavior_registrations)
    return replacement is not None


def update_managed_record_status(
    managed_records: Dict[str, ManagedPluginRecord],
    *,
    plugin_id: str,
    status: PluginLifecycleStatus,
    audit_reason: str,
    recorded_at: Optional[datetime] = None,
) -> ManagedPluginRecord:
    if plugin_id not in managed_records:
        raise KeyError(f"Unknown managed plugin: {plugin_id}")
    record = managed_records[plugin_id]
    plugin = record.plugin
    plugin.status = status
    now = recorded_at or datetime.now(timezone.utc)
    updated = record.model_copy(update={"updated_at": now})
    if status == PluginLifecycleStatus.ACTIVE:
        updated = updated.model_copy(update={"started_at": now, "stopped_at": None})
    elif status in {PluginLifecycleStatus.REVOKED, PluginLifecycleStatus.DEGRADED}:
        updated = updated.model_copy(update={"stopped_at": now})
    managed_records[plugin_id] = updated
    logger.info("managed plugin state changed: %s -> %s (%s)", plugin_id, status.value, audit_reason)
    return updated


def force_enable_managed_plugin(
    request: Request,
    plugin_id: str,
    audit_reason: str,
    *,
    allow_overwrite_active: bool = False,
) -> ManagedForceEnableResult:
    records = getattr(request.app.state, "managed_plugin_records", None)
    if not isinstance(records, dict):
        raise HTTPException(status_code=503, detail="managed_plugin_records is not attached")
    managed_records: Dict[str, ManagedPluginRecord] = records
    if plugin_id not in managed_records:
        raise KeyError(f"Unknown managed plugin: {plugin_id}")

    target = managed_records[plugin_id]
    feature_code = target.feature_code
    auto_disabled: List[str] = []
    for other in managed_records.values():
        if other.plugin.plugin_id == plugin_id:
            continue
        if other.feature_code != feature_code:
            continue
        if other.plugin.status != PluginLifecycleStatus.ACTIVE:
            continue
        if not allow_overwrite_active:
            raise ValueError(f"Feature {feature_code} already has active plugin {other.plugin.plugin_id}")
        update_managed_record_status(
            managed_records,
            plugin_id=other.plugin.plugin_id,
            status=PluginLifecycleStatus.CANDIDATE,
            audit_reason=f"{audit_reason}: auto_deactivated_conflict",
        )
        auto_disabled.append(other.plugin.plugin_id)

    update_managed_record_status(
        managed_records,
        plugin_id=plugin_id,
        status=PluginLifecycleStatus.ACTIVE,
        audit_reason=audit_reason,
    )
    return ManagedForceEnableResult(plugin_id=plugin_id, auto_disabled_plugin_ids=auto_disabled)


def force_disable_managed_plugin(
    request: Request,
    plugin_id: str,
    audit_reason: str,
) -> ManagedPluginRecord:
    records = getattr(request.app.state, "managed_plugin_records", None)
    if not isinstance(records, dict):
        raise HTTPException(status_code=503, detail="managed_plugin_records is not attached")
    managed_records: Dict[str, ManagedPluginRecord] = records
    if plugin_id not in managed_records:
        raise KeyError(f"Unknown managed plugin: {plugin_id}")

    record = managed_records[plugin_id]
    if record.is_default:
        raise ValueError("Default plugins cannot be disabled.")

    behavior_key = str(getattr(record.plugin, "behavior_key", "") or record.feature_code)
    behavior_registrations = managed_behavior_records(managed_records).get(behavior_key, [])
    replacement = resolve_managed_disable_replacement(record, behavior_registrations)
    update_managed_record_status(
        managed_records,
        plugin_id=plugin_id,
        status=PluginLifecycleStatus.CANDIDATE,
        audit_reason=audit_reason,
    )
    if replacement is not None:
        update_managed_record_status(
            managed_records,
            plugin_id=replacement.plugin.plugin_id,
            status=PluginLifecycleStatus.ACTIVE,
            audit_reason=f"{audit_reason}: fallback_activated",
        )
        return managed_records[replacement.plugin.plugin_id]
    return managed_records[plugin_id]


def build_plugin_feature_groups(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_plugins: Dict[str, ManagedPluginRecord],
    catalog: List[PluginFeatureCatalogItem],
) -> List[PluginFeatureGroupItem]:
    plugin_items = build_plugin_payloads(cognitive_registry, plugin_registry, managed_plugins)
    items_by_feature: Dict[str, List[CognitivePluginStatusItem]] = {}
    for item in plugin_items:
        items_by_feature.setdefault(item.feature_code, []).append(item)

    catalog_by_feature_code = {item.feature_code: item for item in catalog}
    result: List[PluginFeatureGroupItem] = []
    for f_code, items in sorted(items_by_feature.items(), key=lambda row: row[0]):
        catalog_item = catalog_by_feature_code.get(f_code)
        plugin_ids = [item.tool_id for item in items]
        active_ids = [item.tool_id for item in items if item.status == PluginLifecycleStatus.ACTIVE.value]
        binding_status = "unbound"
        if active_ids:
            binding_status = "bound_active"
        elif plugin_ids:
            binding_status = "bound_inactive"

        result.append(
            PluginFeatureGroupItem(
                feature_code=f_code,
                display_name=catalog_item.display_name if catalog_item is not None else f_code,
                plugin_kind=catalog_item.plugin_kind if catalog_item is not None else (items[0].plugin_kind if items else "unknown"),
                feature_guide_path=catalog_item.feature_guide_path if catalog_item is not None and catalog_item.feature_guide_path is not None else FEATURE_GUIDE_PATHS.get(f_code),
                family_guide_path=catalog_item.family_guide_path if catalog_item is not None and catalog_item.family_guide_path is not None else PLUGIN_FAMILY_GUIDE_PATHS.get(catalog_item.plugin_kind if catalog_item is not None else (items[0].plugin_kind if items else "unknown")),
                supports_multiple_plugins=catalog_item.supports_multiple_plugins if catalog_item is not None else (items[0].supports_multiple_plugins if items else False),
                binding_status=binding_status,
                active_plugin_ids=active_ids,
                plugins=items,
            )
        )
    return result


def build_cognitive_plugin_list(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
) -> List[CognitivePluginStatusItem]:
    return [
        item
        for item in build_plugin_payloads(cognitive_registry, plugin_registry, managed_records)
        if item.plugin_kind == "cognitive_tool"
    ]


def build_functional_plugin_list(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
) -> List[CognitivePluginStatusItem]:
    return [
        item
        for item in build_plugin_payloads(cognitive_registry, plugin_registry, managed_records)
        if item.plugin_kind != "cognitive_tool"
    ]


def _history_items_for_plugin(plugin_service: Any, plugin_id: str) -> List[PluginVersionHistoryItem]:
    history_items: List[PluginVersionHistoryItem] = []
    history_records = []
    if plugin_service is not None and hasattr(plugin_service, "get_upgrade_history"):
        try:
            history_records = list(plugin_service.get_upgrade_history(plugin_id) or [])
        except Exception:
            history_records = []
    for record in history_records:
        history_items.append(
            PluginVersionHistoryItem(
                plugin_id=getattr(record, "plugin_id", plugin_id),
                version=str(getattr(record, "version", "")),
                status=str(getattr(record, "status", "")),
                started_at=getattr(record, "started_at", None),
                completed_at=getattr(record, "completed_at", None),
                error_message=getattr(record, "error_message", None),
                previous_version=getattr(record, "previous_version", None),
            )
        )
    return history_items


def build_cognitive_plugin_detail(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
    plugin_service: Any,
    plugin_id: str,
) -> CognitivePluginDetailResponse:
    payloads = build_plugin_payloads(cognitive_registry, plugin_registry, managed_records)
    payload_by_id = {item.tool_id: item for item in payloads}
    plugin = payload_by_id.get(plugin_id)
    if plugin is None:
        raise KeyError(f"Unknown plugin: {plugin_id}")

    relations = []
    if plugin_service is not None and hasattr(plugin_service, "query_cognitive_functionals"):
        relations = list(plugin_service.query_cognitive_functionals(plugin_id) or [])

    functional_plugins: List[PluginRelationshipItem] = []
    for relation in relations:
        functional_id = relation.get("plugin_id") or relation.get("functional_plugin_id")
        if not functional_id:
            continue
        functional = payload_by_id.get(functional_id)
        if functional is None:
            continue
        functional_status = _normalize_runtime_status(
            relation.get("status", functional.status),
            is_instantiated=bool(relation.get("is_instantiated")),
        )
        functional_description = _derive_plugin_description(
            plugin_id=functional.tool_id,
            feature_code=functional.feature_code,
            purpose=functional.purpose,
            raw_description=functional.description,
            plugin_kind=functional.plugin_kind,
        )
        functional_plugins.append(
            PluginRelationshipItem(
                plugin=functional.model_copy(
                    update={
                        "status": functional_status,
                        "description": functional_description,
                    }
                ),
                role=str(relation.get("role", "primary")),
                priority=int(relation.get("priority", 1)),
                fallback_id=relation.get("fallback_id"),
                relationship_created_at=relation.get("created_at"),
                relationship_updated_at=relation.get("updated_at"),
            )
        )

    return CognitivePluginDetailResponse(
        plugin=plugin,
        functional_plugins=functional_plugins,
        history=_history_items_for_plugin(plugin_service, plugin_id),
    )


def build_functional_plugin_detail(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
    plugin_service: Any,
    plugin_id: str,
) -> FunctionalPluginDetailResponse:
    payloads = build_plugin_payloads(cognitive_registry, plugin_registry, managed_records)
    payload_by_id = {item.tool_id: item for item in payloads}
    plugin = payload_by_id.get(plugin_id)
    if plugin is None:
        raise KeyError(f"Unknown plugin: {plugin_id}")

    relations = []
    if plugin_service is not None and hasattr(plugin_service, "query_functional_cognitives"):
        relations = list(plugin_service.query_functional_cognitives(plugin_id) or [])

    cognitive_plugins: List[PluginRelationshipItem] = []
    for relation in relations:
        cognitive_id = relation.get("cognitive_plugin_id") or relation.get("plugin_id")
        if not cognitive_id:
            continue
        cognitive = payload_by_id.get(cognitive_id)
        if cognitive is None:
            continue
        cognitive_description = _derive_plugin_description(
            plugin_id=cognitive.tool_id,
            feature_code=cognitive.feature_code,
            purpose=cognitive.purpose,
            raw_description=cognitive.description,
            plugin_kind=cognitive.plugin_kind,
        )
        cognitive_plugins.append(
            PluginRelationshipItem(
                plugin=cognitive.model_copy(update={"description": cognitive_description}),
                role=str(relation.get("role", "primary")),
                priority=int(relation.get("priority", 1)),
                fallback_id=relation.get("fallback_id"),
                relationship_created_at=relation.get("created_at"),
                relationship_updated_at=relation.get("updated_at"),
            )
        )

    return FunctionalPluginDetailResponse(
        plugin=plugin,
        cognitive_plugins=cognitive_plugins,
        history=_history_items_for_plugin(plugin_service, plugin_id),
    )


def build_force_enable_response(
    cognitive_registry: CognitiveToolRegistry,
    plugin_registry: AbstractPluginRegistry[Any] | None,
    managed_records: Dict[str, ManagedPluginRecord],
    *,
    enabled_plugin_id: str,
    auto_disabled_plugin_ids: List[str],
    requires_override_warning: bool,
    message: str,
) -> ForceEnablePluginResponse:
    item = next(
        item
        for item in build_plugin_payloads(cognitive_registry, plugin_registry, managed_records)
        if item.tool_id == enabled_plugin_id
    )
    return ForceEnablePluginResponse(
        plugin=item,
        auto_disabled_plugin_ids=auto_disabled_plugin_ids,
        requires_override_warning=requires_override_warning,
        message=message,
    )


def run_managed_plugin_test(
    request: Request,
    *,
    plugin_id: str,
    audit_reason: str,
    idempotency_key: str,
) -> PluginTestResponse:
    sandbox = getattr(request.app.state, "managed_plugin_test_sandbox", None)
    if not isinstance(sandbox, ManagedPluginTestSandbox):
        records = getattr(request.app.state, "managed_plugin_records", None)
        sandbox = create_managed_plugin_test_sandbox(request, records if isinstance(records, dict) else {})
    record = sandbox.resolve_plugin_for_test(plugin_id)
    details = {
        "plugin_id": record.plugin.plugin_id,
        "status": record.plugin.status.value,
        "feature_code": record.feature_code,
        "idempotency_key": idempotency_key,
        "audit_reason": audit_reason,
    }
    return PluginTestResponse(plugin_id=plugin_id, ok=True, details=details)
