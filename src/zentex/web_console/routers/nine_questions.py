from __future__ import annotations

import copy
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import platform
import tempfile
from time import perf_counter
from uuid import uuid4

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.params import Depends # Added missing Depends
from pydantic import BaseModel

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.nine_questions.executor import NineQuestionExecutor
from zentex.runtime.nine_questions.router import build_event
from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from zentex.runtime.nine_questions.state import NineQuestionState
from zentex.core.capability_patch_base import BaseCapabilityPatchPlugin
from zentex.web_console.contracts.llm_trace import LLMTokenUsagePayload, LLMTracePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.contracts.nine_questions import (
    MountedPluginInfo,
    NineQuestionReportItem,
    NineQuestionSandboxRequest,
    NineQuestionSandboxResponse,
    NineQuestionsRunRequest,
    NineQuestionsRunResponse,
    NineQuestionsReportPayload,
    Q1CandidateGroupDetail,
    Q1LLMUpgradeView,
    Q1LongTextEvidence,
    Q1PreprocessedEvidence,
    Q1PhysicalAndEnvironmentEvidence,
    Q1RiskFileDetail,
    Q1StructureTreeRow,
    Q1WorkspaceContentSamplingEvidence,
    Q1WorkspaceSampleSummary,
    Q1WorkspaceStructureEvidence,
    Q2PreprocessedEvidence,
    Q2WhoAmIInferenceView,
    Q2Q1Summary,
    Q2IdentityKernel,
    Q2ManualIntervention,
    Q2RoleView,
    Q2MissionBoundaryView,
    Q3PreprocessedEvidence,
    Q3WhatDoIHaveInferenceView,
    Q3AssetRow,
    Q3AgentRow,
    Q3WorkspaceAndPermission,
    Q3ToolsAndAgents,
    Q3MemoryAndStrategy,
    Q3ResourceSufficiencyView,
    Q4PreprocessedEvidence,
    Q4WhatCanIDoInferenceView,
    Q5PreprocessedEvidence,
    Q5WhatAmIAllowedToDoInferenceView,
    Q6ForbiddenZoneInferenceView,
    Q6PreprocessedEvidence,
    Q7AlternativeStrategyInferenceView,
    Q7PreprocessedEvidence,
    Q8AgendaItem,
    Q8AggregatedContextEvidence,
    Q8AutonomousTaskQueueView,
    Q8ObjectiveProfileView,
    Q8PersistentTaskItem,
    Q8PreprocessedEvidence,
    Q8RuntimeStateEvidence,
    Q8WhatShouldIDoNowInferenceView,
    Q9ActionPostureInferenceView,
    Q9CognitiveSnapshotEvidence,
    Q9PreprocessedEvidence,
    Q9ReasoningBudgetEvidence,
    Q9RecentWeaknessView,
    Q9SelfModelEvidence,
    WorkspaceDomainInferenceView,
)
from zentex.web_console.contracts.transcript import TranscriptEventPayload
from zentex.web_console.contracts.plugins import PluginFeatureCatalogItem
from zentex.web_console.dependencies import get_cognitive_tool_registry, get_runtime, get_transcript_store


router = APIRouter()
logger = logging.getLogger(__name__)

QUESTION_TITLES = {
    "q1": "我在哪",
    "q2": "我是谁",
    "q3": "我有什么",
    "q4": "我能做什么",
    "q5": "我被允许做什么",
    "q6": "我即使能做也不该做什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}


def _humanize_plugin_token(value: str) -> str:
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
    catalog_by_feature: dict[str, PluginFeatureCatalogItem],
) -> str:
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
        "nine_questions.q1": "负责判断当前系统所处环境、工作区结构和外部态势，回答“我在哪”。",
        "nine_questions.q2": "负责结合 Q1 态势与身份约束，判断当前系统扮演的角色与使命边界，回答“我是谁”。",
        "nine_questions.q3": "负责盘点当前可用工具、Agent、工作区与权限资产，回答“我有什么”。",
        "nine_questions.q4": "负责基于真实资产与执行域，判断系统当前真正具备的行动能力，回答“我能做什么”。",
        "nine_questions.q5": "负责基于授权与合规边界，对可行动作做减法裁剪，回答“我被允许做什么”。",
        "nine_questions.q6": "负责识别即使物理上可行也绝对不能触碰的红线与禁区，回答“我即使能做也不该做什么”。",
        "nine_questions.q7": "负责在主路径受阻时生成备选策略、降级路径和协作切换方案，回答“我还可以做什么”。",
        "nine_questions.q8": "负责汇总 Q1-Q7 的约束与能力，生成当前最优主目标和任务队列，回答“我现在应该做什么”。",
        "nine_questions.q9": "负责根据 Q1-Q8 的状态确定行动姿态、节奏和确认策略，回答“我应该如何行动”。",
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


def _get_mounted_plugins_for_question(
    runtime: BrainRuntime,
    q_id: str,
    plugin_feature_catalog: list[PluginFeatureCatalogItem] | None = None,
) -> list[MountedPluginInfo]:
    """
    Expose the truth of capability patch mountings for the frontend.
    """
    registry: CognitiveToolRegistry = (
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

            source_kind = "patch" if isinstance(reg.spec, BaseCapabilityPatchPlugin) else "base"
            if source_kind == "base" and ("patch" in reg.plugin_id.lower() or "enhancement" in reg.plugin_id.lower()):
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
            display_name = _derive_plugin_display_name(
                plugin_id=plugin_id,
                feature_code=feature_code,
                plugin=plugin,
                catalog_by_feature=catalog_by_feature,
            )
            function_description = _derive_plugin_function_description(
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


def _functional_feature_codes_for_question(q_id: str) -> set[str]:
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


def _build_runtime_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: CognitiveToolRegistry,
    execution_registry: object | None,
    task_service: object | None,
    host_telemetry_plugin: object | None = None,
) -> dict[str, object]:
    return build_runtime_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
        task_service=task_service,
        environment_summary="frontend requested a full nine-question refresh",
        host_telemetry_plugin=host_telemetry_plugin,
    )


def _run_full_nine_questions(
    *,
    request: Request,
    runtime: BrainRuntime,
    session: BrainSession,
    state: NineQuestionState,
    registry: CognitiveToolRegistry,
    refresh_reason: str,
) -> NineQuestionsRunResponse:
    workspace_root = str(getattr(runtime, "default_workspace", ".") or os.getcwd())
    startup_context = _build_runtime_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=registry,
        execution_registry=getattr(request.app.state, "execution_registry", None),
        task_service=getattr(request.app.state, "task_service", None),
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
    executor = NineQuestionExecutor(
        registry=registry,
        transcript_store=runtime.transcript_store,
    )
    for queued_event in runtime.nine_question_router.drain():
        executor.run_questions(
            runtime=runtime,
            session=session,
            state=state,
            question_ids=queued_event.dirty_questions,
            trace_id=queued_event.trace_id,
            refresh_reason=queued_event.reason,
            driver_refs=["frontend:nine-questions", queued_event.event_type],
            turn_id=f"turn-{refresh_reason}",
        )
    return NineQuestionsRunResponse(
        started=True,
        trace_id=trace_id,
        refresh_reason=refresh_reason,
        snapshot_version=state.snapshot_version,
        revision=state.revision,
    )


def _normalize_health_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"healthy", "ok", "online", "low", "normal"}:
        return "healthy"
    if normalized in {"degraded", "degrade", "medium", "warn", "warning"}:
        return "degrade"
    if normalized:
        return normalized
    return "unknown"


def _serialize_contract_payload(value: object) -> dict[str, object] | None:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _build_directory_tree_rows(structure_dict: dict[str, object], top_level_dirs: list[str]) -> list[Q1StructureTreeRow]:
    raw_nodes = structure_dict.get("directory_tree") or structure_dict.get("directory_hierarchy") or structure_dict.get("directories")
    rows: list[Q1StructureTreeRow] = []

    if isinstance(raw_nodes, list):
        for index, node in enumerate(raw_nodes):
            if not isinstance(node, dict):
                continue
            path = str(node.get("path") or node.get("name") or node.get("label") or "").strip()
            if not path:
                continue
            label = str(node.get("label") or Path(path).name or path)
            depth = node.get("depth")
            if not isinstance(depth, int):
                depth = max(path.count("/") - 1, 0)
            file_count = node.get("file_count")
            rows.append(
                Q1StructureTreeRow(
                    row_id=f"dir-{index}",
                    path=path,
                    label=label,
                    depth=depth,
                    kind=str(node.get("kind") or "directory"),
                    file_count=file_count if isinstance(file_count, int) else None,
                    summary=str(node.get("summary")).strip() if node.get("summary") else None,
                )
            )

    if rows:
        return rows

    return [
        Q1StructureTreeRow(
            row_id=f"dir-top-{index}",
            path=directory,
            label=directory,
            depth=0,
            kind="directory",
        )
        for index, directory in enumerate(top_level_dirs)
    ]


def _build_candidate_group_details(structure_dict: dict[str, object], candidate_groups: list[str]) -> list[Q1CandidateGroupDetail]:
    raw_groups = structure_dict.get("candidate_group_details") or structure_dict.get("candidate_groups_detailed")
    details: list[Q1CandidateGroupDetail] = []

    if isinstance(raw_groups, list):
        for index, group in enumerate(raw_groups):
            if isinstance(group, dict):
                label = str(group.get("label") or group.get("name") or "").strip()
                if not label:
                    continue
                file_count = group.get("file_count")
                details.append(
                    Q1CandidateGroupDetail(
                        group_id=f"group-{index}",
                        label=label,
                        file_count=file_count if isinstance(file_count, int) else None,
                        summary=str(group.get("summary")).strip() if group.get("summary") else None,
                    )
                )
            elif str(group).strip():
                details.append(Q1CandidateGroupDetail(group_id=f"group-{index}", label=str(group).strip()))

    if details:
        return details

    return [
        Q1CandidateGroupDetail(group_id=f"group-fallback-{index}", label=group)
        for index, group in enumerate(candidate_groups)
    ]


def _build_risk_file_details(structure_dict: dict[str, object], obvious_risk_files: list[str]) -> list[Q1RiskFileDetail]:
    raw_risks = structure_dict.get("obvious_risk_file_details") or structure_dict.get("risk_file_details")
    details: list[Q1RiskFileDetail] = []

    if isinstance(raw_risks, list):
        for risk in raw_risks:
            if isinstance(risk, dict):
                path = str(risk.get("path") or risk.get("file") or "").strip()
                if not path:
                    continue
                details.append(
                    Q1RiskFileDetail(
                        path=path,
                        severity=str(risk.get("severity")).strip() if risk.get("severity") else None,
                        reason=str(risk.get("reason")).strip() if risk.get("reason") else None,
                    )
                )
            elif str(risk).strip():
                details.append(Q1RiskFileDetail(path=str(risk).strip()))

    if details:
        return details

    return [Q1RiskFileDetail(path=path) for path in obvious_risk_files]


def _build_long_text_evidence(
    sampled_items: list[dict[str, object]],
    anomalies: list[str],
) -> list[Q1LongTextEvidence]:
    blocks: list[Q1LongTextEvidence] = []
    sample_text_keys = [
        ("title", "标题"),
        ("header", "表头"),
        ("summary", "摘要"),
        ("snippet", "样本行"),
        ("excerpt", "文档前段"),
        ("first_lines", "文件前段"),
    ]

    for sample_index, sample in enumerate(sampled_items):
        sample_path = str(sample.get("path") or sample.get("file") or "").strip() or None
        base_label = sample_path or f"sample-{sample_index + 1}"
        for field_name, field_label in sample_text_keys:
            text = sample.get(field_name)
            if not isinstance(text, str) or not text.strip():
                continue
            blocks.append(
                Q1LongTextEvidence(
                    evidence_id=f"sample-{sample_index}-{field_name}",
                    label=f"{base_label} · {field_label}",
                    kind=field_name,
                    source="workspace_content_sampler",
                    path=sample_path,
                    text=text.strip(),
                )
            )

    for index, snippet in enumerate(anomalies):
        if not isinstance(snippet, str) or not snippet.strip():
            continue
        blocks.append(
            Q1LongTextEvidence(
                evidence_id=f"anomaly-{index}",
                label=f"日志异常片段 #{index + 1}",
                kind="log_anomaly",
                source="workspace_content_sampler",
                text=snippet.strip(),
            )
        )

    return blocks


def _build_q1_preprocessed_evidence(context_snapshot: dict[str, object]) -> Q1PreprocessedEvidence:
    structure = context_snapshot.get("workspace_structure_analysis", {})
    samples = context_snapshot.get("workspace_content_samples", {})
    environment_event = context_snapshot.get("environment_event", {})
    physical_host_state = context_snapshot.get("physical_host_state", {})

    structure_dict = structure if isinstance(structure, dict) else {}
    samples_dict = samples if isinstance(samples, dict) else {}
    environment_dict = environment_event if isinstance(environment_event, dict) else {}
    host_dict = physical_host_state if isinstance(physical_host_state, dict) else {}

    sampled_items_raw = samples_dict.get("sampled_file_summaries") or samples_dict.get("file_samples") or []
    sampled_items: list[dict[str, object]] = []
    if isinstance(sampled_items_raw, list):
        sampled_items = [item for item in sampled_items_raw if isinstance(item, dict)]

    anomalies = samples_dict.get("log_anomaly_snippets") or samples_dict.get("anomalies") or []
    anomaly_list = [str(item).strip() for item in anomalies if isinstance(item, str) and item.strip()] if isinstance(anomalies, list) else []

    top_level_dirs = _coerce_string_list(structure_dict.get("top_level_dirs"))
    candidate_groups = _coerce_string_list(structure_dict.get("candidate_groups"))
    obvious_risk_files = _coerce_string_list(structure_dict.get("obvious_risk_files") or structure_dict.get("risk_files"))
    suffix_distribution = structure_dict.get("suffix_distribution") or structure_dict.get("extension_distribution") or {}
    keyword_distribution = (
        structure_dict.get("high_frequency_filename_keywords") or structure_dict.get("keyword_frequencies") or {}
    )
    file_total_count = structure_dict.get("file_total_count") or structure_dict.get("file_count")

    environment_summary = []
    for key in ("cwd", "hostname", "platform", "python_version"):
        value = host_dict.get(key)
        if value:
            environment_summary.append(f"{key}={value}")
    for key in ("kind", "summary"):
        value = environment_dict.get(key)
        if value:
            environment_summary.append(f"environment_{key}={value}")

    sampled_summaries = [Q1WorkspaceSampleSummary.model_validate(sample) for sample in sampled_items]
    long_text_evidence = _build_long_text_evidence(sampled_items, anomaly_list)

    return Q1PreprocessedEvidence(
        physical_and_environment=Q1PhysicalAndEnvironmentEvidence(
            environment_event=environment_dict,
            physical_host_state=host_dict,
            memory_pressure=str(host_dict.get("memory_pressure")) if host_dict.get("memory_pressure") is not None else None,
            network_health=str(host_dict.get("network_health")) if host_dict.get("network_health") is not None else None,
            memory_pressure_status=_normalize_health_status(host_dict.get("memory_pressure")),
            network_health_status=_normalize_health_status(host_dict.get("network_health")),
            environment_summary=environment_summary,
        ),
        workspace_structure=Q1WorkspaceStructureEvidence(
            directory_hierarchy_summary=str(structure_dict.get("directory_hierarchy_summary")).strip()
            if structure_dict.get("directory_hierarchy_summary")
            else None,
            top_level_dirs=top_level_dirs,
            file_total_count=file_total_count if isinstance(file_total_count, int) else None,
            suffix_distribution={
                str(key): int(value)
                for key, value in suffix_distribution.items()
                if str(key).strip() and isinstance(value, int)
            }
            if isinstance(suffix_distribution, dict)
            else {},
            high_frequency_filename_keywords={
                str(key): int(value)
                for key, value in keyword_distribution.items()
                if str(key).strip() and isinstance(value, int)
            }
            if isinstance(keyword_distribution, dict)
            else {},
            candidate_groups=candidate_groups,
            obvious_risk_files=obvious_risk_files,
            directory_tree_rows=_build_directory_tree_rows(structure_dict, top_level_dirs),
            candidate_group_details=_build_candidate_group_details(structure_dict, candidate_groups),
            obvious_risk_file_details=_build_risk_file_details(structure_dict, obvious_risk_files),
            analyzer_snapshot=structure_dict,
        ),
        workspace_content_sampling=Q1WorkspaceContentSamplingEvidence(
            sampled_file_summaries=sampled_summaries,
            log_anomaly_snippets=anomaly_list,
            long_text_evidence=long_text_evidence,
            sample_count=len(sampled_summaries),
            anomaly_count=len(anomaly_list),
            sampler_snapshot=samples_dict,
        ),
    )


def _extract_q1_inference_result(result_payload: object) -> WorkspaceDomainInferenceView | None:
    if not isinstance(result_payload, dict):
        return None

    ordered_keys = [
        "primary_domain",
        "secondary_domains",
        "confidence",
        "reasoning_summary",
        "uncertainties",
        "suggested_first_step",
    ]
    if not set(ordered_keys).issubset(result_payload.keys()):
        return None

    return WorkspaceDomainInferenceView.model_validate({key: result_payload.get(key) for key in ordered_keys})


def _extract_q1_llm_upgrade(context_payload: object) -> Q1LLMUpgradeView | None:
    if not isinstance(context_payload, dict):
        return None
    upgrade_payload = context_payload.get("q1_llm_upgrade")
    if not isinstance(upgrade_payload, dict):
        return None
    return Q1LLMUpgradeView.model_validate(upgrade_payload)


def _extract_q1_preprocessed_evidence(context_payload: object) -> Q1PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("workspace_structure_analysis", "workspace_content_samples", "environment_event", "physical_host_state")
    ):
        return None
    return _build_q1_preprocessed_evidence(context_payload)


def _build_q2_preprocessed_evidence(context_payload: dict[str, Any]) -> Q2PreprocessedEvidence | None:
    q1_inference = context_payload.get("workspace_domain_inference", {})
    q1_scene_model = context_payload.get("q1_scene_model", {})
    q1_uncertainty_profile = context_payload.get("q1_uncertainty_profile", {})
    if not isinstance(q1_inference, dict):
        q1_inference = {}
    if not isinstance(q1_scene_model, dict):
        q1_scene_model = {}
    if not isinstance(q1_uncertainty_profile, dict):
        q1_uncertainty_profile = {}

    q1_summary = Q2Q1Summary(
        primary_domain=str(
            q1_inference.get("primary_domain")
            or q1_scene_model.get("primary_domain")
            or "unknown"
        ),
        secondary_domains=(
            _coerce_string_list(q1_inference.get("secondary_domains"))
            or _coerce_string_list(q1_scene_model.get("secondary_domains"))
        ),
        uncertainties=(
            _coerce_string_list(q1_inference.get("uncertainties"))
            or _coerce_string_list(q1_uncertainty_profile.get("risk_sources"))
        ),
        risk_summary=(
            str(q1_inference.get("reasoning_summary") or "").strip()
            or str(q1_uncertainty_profile.get("risk_summary") or "").strip()
            or ", ".join(_coerce_string_list(q1_uncertainty_profile.get("risk_sources")))
            or None
        ),
    )

    identity_kernel_raw = (
        context_payload.get("identity_core")
        or context_payload.get("identity_kernel_snapshot")
        or {}
    )
    if not isinstance(identity_kernel_raw, dict):
        identity_kernel_raw = {}

    meta_motivation = identity_kernel_raw.get("meta_motivation")
    if not meta_motivation:
        meta_motivation = " / ".join(_coerce_string_list(identity_kernel_raw.get("meta_drives")))
    values_prohibition = identity_kernel_raw.get("values_prohibition")
    if not values_prohibition:
        values_prohibition = " / ".join(_coerce_string_list(identity_kernel_raw.get("value_vetoes")))

    identity_kernel = Q2IdentityKernel(
        meta_motivation=str(meta_motivation or "No meta-motivation defined."),
        values_prohibition=str(values_prohibition or "No value prohibitions defined."),
        non_bypassable_constraints=[
            text
            for item in _coerce_string_list(identity_kernel_raw.get("non_bypassable_constraints"))
            if (text := _humanize_constraint_text(item))
        ],
    )

    manual_raw = context_payload.get("manual_role_intervention") or context_payload.get("manual_role_overrides") or {}
    manual_intervention = None
    if isinstance(manual_raw, dict) and manual_raw:
        latest_manual = (
            manual_raw.get("reason")
            or manual_raw.get("role_update")
            or manual_raw.get("active_role_override")
            or "manual override"
        )
        applied_at = manual_raw.get("timestamp") or manual_raw.get("applied_at")
        manual_intervention = Q2ManualIntervention(
            latest_manual_role_modification=str(latest_manual),
            applied_at=str(applied_at) if applied_at else None,
        )

    return Q2PreprocessedEvidence(
        q1_summary=q1_summary,
        identity_kernel=identity_kernel,
        manual_intervention=manual_intervention,
    )


def _extract_q2_preprocessed_evidence(context_payload: object) -> Q2PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in (
            "identity_core",
            "identity_kernel_snapshot",
            "workspace_domain_inference",
            "q1_scene_model",
            "q1_uncertainty_profile",
            "manual_role_intervention",
            "manual_role_overrides",
        )
    ):
        return None
    return _build_q2_preprocessed_evidence(context_payload)


def _humanize_constraint_text(value: object) -> str | None:
    labels = {
        "NO_FAKE_RUNTIME_STATE": "禁止伪造运行态事实或虚构系统状态",
        "NO_SKIP_AUDIT": "禁止跳过审计记录、证据链和可追溯性要求",
        "NO_UNAUTHORIZED_WRITE_ACTION": "禁止未授权写入、修改或执行会产生副作用的动作",
    }
    text = str(value or "").strip()
    if not text:
        return None
    return labels.get(text, text)


def _merge_context_payloads(*payloads: object) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key not in merged:
                merged[key] = value
                continue
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                combined = dict(existing)
                for child_key, child_value in value.items():
                    if child_key not in combined or combined.get(child_key) in (None, "", [], {}):
                        combined[child_key] = child_value
                merged[key] = combined
            elif existing in (None, "", [], {}):
                merged[key] = value
    return merged


def _has_material_q2_q1_summary(evidence: object) -> bool:
    if not isinstance(evidence, dict):
        return False
    q1_summary = evidence.get("q1_summary")
    if not isinstance(q1_summary, dict):
        return False
    primary_domain = str(q1_summary.get("primary_domain") or "").strip().lower()
    secondary_domains = _coerce_string_list(q1_summary.get("secondary_domains"))
    uncertainties = _coerce_string_list(q1_summary.get("uncertainties"))
    risk_summary = str(q1_summary.get("risk_summary") or "").strip()
    return bool(
        (primary_domain and primary_domain != "unknown")
        or secondary_domains
        or uncertainties
        or risk_summary
    )


def _build_question_preprocessed_evidence(
    *,
    question_id: str,
    state_context: dict[str, Any],
    trace_context: object | None,
    trace_evidence: object | None,
):
    extractor_map = {
        "q1": _extract_q1_preprocessed_evidence,
        "q2": _extract_q2_preprocessed_evidence,
        "q3": _extract_q3_preprocessed_evidence,
        "q4": _extract_q4_preprocessed_evidence,
        "q5": _extract_q5_preprocessed_evidence,
        "q6": _extract_q6_preprocessed_evidence,
        "q7": _extract_q7_preprocessed_evidence,
        "q8": _extract_q8_preprocessed_evidence,
        "q9": _extract_q9_preprocessed_evidence,
    }
    extractor = extractor_map[question_id]
    merged_context = _merge_context_payloads(state_context, trace_context)
    merged_evidence = extractor(merged_context)
    if question_id == "q2":
        if _has_material_q2_q1_summary(merged_evidence):
            return merged_evidence
        if _has_material_q2_q1_summary(trace_evidence):
            return trace_evidence
        return merged_evidence
    return merged_evidence or trace_evidence


def _extract_q2_inference_result(result_payload: object) -> Q2WhoAmIInferenceView | None:
    if not isinstance(result_payload, dict):
        return None

    role_profile_raw = result_payload.get("role_profile")
    mission_boundary_raw = result_payload.get("mission_boundary")

    if not isinstance(role_profile_raw, dict) or not isinstance(mission_boundary_raw, dict):
        return None

    return Q2WhoAmIInferenceView(
        role_profile=Q2RoleView(
            identity_role=str(role_profile_raw.get("identity_role") or ""),
            active_role=str(role_profile_raw.get("active_role") or ""),
            task_role=str(role_profile_raw.get("task_role") or ""),
        ),
        mission_boundary=Q2MissionBoundaryView(
            current_mission=str(mission_boundary_raw.get("current_mission") or ""),
            priority_duties=_coerce_string_list(mission_boundary_raw.get("priority_duties")),
            continuity_boundaries=_coerce_string_list(mission_boundary_raw.get("continuity_boundaries")),
        ),
    )


def _build_q3_preprocessed_evidence(context_payload: dict[str, Any]) -> Q3PreprocessedEvidence | None:
    unified_inventory = context_payload.get("q3_unified_asset_inventory", {})
    if not isinstance(unified_inventory, dict):
        unified_inventory = {}

    permissions_raw = context_payload.get("permissions", {})
    workspace_assets_raw = context_payload.get("workspace_assets", {})
    active_tools_raw = context_payload.get("active_tools", {})
    loaded_memories_raw = context_payload.get("loaded_memories", {})

    # 1. Workspaces & Permissions
    wp_raw = context_payload.get("workspaces_and_permissions", {})
    if not isinstance(wp_raw, dict):
        wp_raw = {}
    wp = Q3WorkspaceAndPermission(
        workspaces=(
            _coerce_string_list(unified_inventory.get("accessible_workspace_zones"))
            or _coerce_string_list((permissions_raw or {}).get("accessible_workspace_zones"))
            or _coerce_string_list((workspace_assets_raw or {}).get("accessible_workspace_zones"))
            or _coerce_string_list(wp_raw.get("available_workspaces"))
        ),
        tenant_permissions=(
            _coerce_string_list((permissions_raw or {}).get("tenant_scope"))
            or _coerce_string_list(wp_raw.get("tenant_permissions"))
        ),
        execution_tokens=(
            _coerce_string_list((permissions_raw or {}).get("brain_scope"))
            or _coerce_string_list((permissions_raw or {}).get("execution_tokens"))
            or _coerce_string_list(wp_raw.get("execution_tokens"))
        ),
    )

    # 2. Tools & Agents
    ta_raw = context_payload.get("tool_inventory", {})
    if not isinstance(ta_raw, dict):
        ta_raw = {}
    connected_agents_raw = (
        unified_inventory.get("connected_agents")
        or ta_raw.get("connected_agents")
        or context_payload.get("connected_agents")
        or []
    )
    filtered_connected_agents = []
    if isinstance(connected_agents_raw, list):
        for agent in connected_agents_raw:
            if not isinstance(agent, dict):
                continue
            if str(agent.get("status") or "").lower() == "offline":
                continue
            filtered_connected_agents.append(agent)

    def _humanize_q3_asset_row(raw_id: object) -> Q3AssetRow:
        raw_text = str(raw_id or "").strip()
        name = " ".join(chunk.capitalize() for chunk in raw_text.replace(":", " ").replace(".", " ").replace("-", " ").replace("_", " ").split()) or "未知工具"
        return Q3AssetRow(
            id=raw_text,
            name=name,
            introduction=f"{name} 是当前运行态中可调用的一项工具资产。",
            function_description=f"{name} 用于提供与 {raw_text} 对应的认知或执行能力。",
        )

    def _humanize_q3_agent_row(agent: dict[str, Any]) -> Q3AgentRow:
        agent_id = str(agent.get("agent_id") or agent.get("id") or agent.get("name") or "").strip()
        name = str(agent.get("name") or "").strip() or (
            " ".join(chunk.capitalize() for chunk in agent_id.replace("-", " ").replace("_", " ").split()) if agent_id else "未知 Agent"
        )
        introduction = str(agent.get("summary") or agent.get("description") or "").strip() or f"{name} 是当前已连接的协作 Agent。"
        function_description = (
            f"{name} 负责 {agent.get('role') or agent.get('scope') or agent.get('status')} 相关的协作支持。"
            if (agent.get("role") or agent.get("scope") or agent.get("status"))
            else f"{name} 用于承接需要多 Agent 协同的任务。"
        )
        return Q3AgentRow(
            id=agent_id or name,
            name=name,
            introduction=introduction,
            function_description=function_description,
            status=str(agent.get("status") or "").strip() or None,
        )

    humanized_inventory = context_payload.get("q3_humanized_asset_inventory", {})
    if not isinstance(humanized_inventory, dict):
        humanized_inventory = {}
    cognitive_tool_rows = [
        Q3AssetRow.model_validate(item)
        for item in (humanized_inventory.get("cognitive_tool_rows") or [])
        if isinstance(item, dict)
    ]
    if not cognitive_tool_rows:
        cognitive_tool_rows = [
            _humanize_q3_asset_row(item)
            for item in (
                _coerce_string_list(unified_inventory.get("available_cognitive_tools"))
                or _coerce_string_list((active_tools_raw or {}).get("available_cognitive_tools"))
                or _coerce_string_list(ta_raw.get("cognitive_tools"))
            )
        ]
    execution_tool_rows = [
        Q3AssetRow.model_validate(item)
        for item in (humanized_inventory.get("execution_tool_rows") or [])
        if isinstance(item, dict)
    ]
    if not execution_tool_rows:
        execution_tool_rows = [
            _humanize_q3_asset_row(item)
            for item in (
                _coerce_string_list(unified_inventory.get("available_execution_tools"))
                or _coerce_string_list((active_tools_raw or {}).get("available_execution_tools"))
                or _coerce_string_list(ta_raw.get("execution_tools"))
            )
        ]
    connected_agent_rows = [
        Q3AgentRow.model_validate(item)
        for item in (humanized_inventory.get("connected_agent_rows") or [])
        if isinstance(item, dict)
    ]
    if not connected_agent_rows:
        connected_agent_rows = [_humanize_q3_agent_row(item) for item in filtered_connected_agents]
    ta = Q3ToolsAndAgents(
        cognitive_tools=(
            _coerce_string_list(unified_inventory.get("available_cognitive_tools"))
            or _coerce_string_list((active_tools_raw or {}).get("available_cognitive_tools"))
            or _coerce_string_list(ta_raw.get("cognitive_tools"))
        ),
        execution_tools=(
            _coerce_string_list(unified_inventory.get("available_execution_tools"))
            or _coerce_string_list((active_tools_raw or {}).get("available_execution_tools"))
            or _coerce_string_list(ta_raw.get("execution_tools"))
        ),
        connected_agents=filtered_connected_agents,
        cognitive_tool_rows=cognitive_tool_rows,
        execution_tool_rows=execution_tool_rows,
        connected_agent_rows=connected_agent_rows,
    )

    # 3. Memory & Strategy
    ms_raw = context_payload.get("memory_and_strategy", {})
    if not isinstance(ms_raw, dict):
        ms_raw = {}
    ms = Q3MemoryAndStrategy(
        experience_logs=(
            _coerce_string_list((loaded_memories_raw or {}).get("experience_logs"))
            or _coerce_string_list(ms_raw.get("experience_logs"))
        ),
        strategy_patches=(
            _coerce_string_list(unified_inventory.get("activated_strategy_patches"))
            or _coerce_string_list((loaded_memories_raw or {}).get("activated_strategy_patches"))
            or _coerce_string_list(ms_raw.get("strategy_patches"))
        ),
    )

    if not wp.workspaces and not ta.cognitive_tools and not ta.execution_tools and not ms.strategy_patches and not ms.experience_logs:
        return None

    return Q3PreprocessedEvidence(
        workspace_permission=wp,
        tools_agents=ta,
        memory_strategy=ms,
    )


def _extract_q3_preprocessed_evidence(context_payload: object) -> Q3PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        k in context_payload
        for k in (
            "workspaces_and_permissions",
            "tool_inventory",
            "memory_and_strategy",
            "q3_unified_asset_inventory",
            "permissions",
            "workspace_assets",
            "active_tools",
            "loaded_memories",
            "connected_agents",
        )
    ):
        return None
    return _build_q3_preprocessed_evidence(context_payload)


def _extract_q3_inference_result(result_payload: object) -> Q3WhatDoIHaveInferenceView | None:
    if not isinstance(result_payload, dict):
        return None

    sufficiency_raw = (
        result_payload.get("sufficiency_assessment")
        or result_payload.get("resource_evaluation")
        or result_payload.get("q3_resource_evaluation")
    )
    if not isinstance(sufficiency_raw, dict):
        return None

    resource_status = str(sufficiency_raw.get("resource_status") or "unknown")
    status_label_map = {
        "sufficient": "资源充沛",
        "degraded": "资源降级",
        "critically_lacking": "关键资源匮乏",
    }
    status_explanation_map = {
        "sufficient": "当前关键工具、执行能力与协同代理基本齐备，可以支撑正常推演与执行。",
        "degraded": "当前具备部分关键资源，但存在明显短板或瓶颈，需要保守决策与补足关键能力。",
        "critically_lacking": "当前缺少关键资源，无法安全完成核心任务，应先补足基础资产再继续执行。",
    }
    return Q3WhatDoIHaveInferenceView(
        sufficiency_assessment=Q3ResourceSufficiencyView(
            resource_status=resource_status,
            resource_status_label=str(sufficiency_raw.get("resource_status_label") or "")
            if sufficiency_raw.get("resource_status_label")
            else status_label_map.get(resource_status),
            resource_status_explanation=str(sufficiency_raw.get("resource_status_explanation") or "")
            if sufficiency_raw.get("resource_status_explanation")
            else status_explanation_map.get(resource_status),
            missing_critical_assets=_coerce_string_list(sufficiency_raw.get("missing_critical_assets")),
            bottleneck_node=sufficiency_raw.get("bottleneck_node"),
            reasoning_summary=sufficiency_raw.get("reasoning_summary"),
        )
    )


def _extract_q4_preprocessed_evidence(context_payload: object) -> Q4PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    q1_context = {
        "scene_model": context_payload.get("q1_scene_model") if isinstance(context_payload.get("q1_scene_model"), dict) else {},
        "uncertainty_profile": context_payload.get("q1_uncertainty_profile")
        if isinstance(context_payload.get("q1_uncertainty_profile"), dict)
        else {},
    }
    q2_context = {
        "role_profile": context_payload.get("q2_role_profile") if isinstance(context_payload.get("q2_role_profile"), dict) else {},
        "mission_boundary": context_payload.get("q2_mission_boundary")
        if isinstance(context_payload.get("q2_mission_boundary"), dict)
        else {},
    }
    q3_inventory = {
        "available_cognitive_tools": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("available_cognitive_tools")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "available_execution_tools": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("available_execution_tools")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "connected_agents": (
            (context_payload.get("q3_unified_asset_inventory") or {}).get("connected_agents")
            if isinstance((context_payload.get("q3_unified_asset_inventory") or {}).get("connected_agents"), list)
            else []
        ),
        "activated_strategy_patches": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("activated_strategy_patches")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "accessible_workspace_zones": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("accessible_workspace_zones")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "resource_evaluation": context_payload.get("q3_resource_evaluation")
        if isinstance(context_payload.get("q3_resource_evaluation"), dict)
        else {},
    }
    if not any(
        (
            q1_context["scene_model"],
            q1_context["uncertainty_profile"],
            q2_context["role_profile"],
            q2_context["mission_boundary"],
            q3_inventory["available_cognitive_tools"],
            q3_inventory["available_execution_tools"],
            q3_inventory["connected_agents"],
            q3_inventory["activated_strategy_patches"],
            q3_inventory["accessible_workspace_zones"],
            q3_inventory["resource_evaluation"],
        )
    ):
        return None
    return Q4PreprocessedEvidence(q1_context=q1_context, q2_context=q2_context, q3_inventory=q3_inventory)


def _extract_q4_inference_result(result_payload: object) -> Q4WhatCanIDoInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    payload = (
        result_payload.get("capability_boundary_profile")
        if isinstance(result_payload.get("capability_boundary_profile"), dict)
        else result_payload.get("q4_capability_boundary_profile")
        if isinstance(result_payload.get("q4_capability_boundary_profile"), dict)
        else result_payload
    )
    if not isinstance(payload, dict) or not any(
        key in payload for key in ("capability_upper_limits", "actionable_space", "executable_strategies")
    ):
        return None
    return Q4WhatCanIDoInferenceView(
        capability_upper_limits=_coerce_string_list(payload.get("capability_upper_limits")),
        actionable_space=_coerce_string_list(payload.get("actionable_space")),
        executable_strategies=_coerce_string_list(payload.get("executable_strategies")),
    )


def _extract_q5_preprocessed_evidence(context_payload: object) -> Q5PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None

    def _flatten_policy_lines(value: object) -> list[str]:
        if isinstance(value, dict):
            lines: list[str] = []
            for key, raw in value.items():
                if raw is None:
                    continue
                if isinstance(raw, list):
                    rendered = ", ".join(str(item) for item in raw)
                elif isinstance(raw, bool):
                    rendered = str(raw).lower()
                else:
                    rendered = str(raw)
                lines.append(f"{key}={rendered}")
            return lines
        return _coerce_string_list(value)

    q4_profile = context_payload.get("q4_capability_boundary_profile")
    action_space = _coerce_string_list(context_payload.get("actionable_space"))
    if not action_space and isinstance(q4_profile, dict):
        action_space = _coerce_string_list(q4_profile.get("actionable_space"))

    boundaries = _coerce_string_list(context_payload.get("tenant_boundaries"))
    if not boundaries:
        boundaries = _flatten_policy_lines(context_payload.get("tenant_scope"))

    contact_policy = _flatten_policy_lines(context_payload.get("contact_policy"))

    trust = context_payload.get("agent_trust_status") or {}
    if not isinstance(trust, dict):
        trust = {}
    if not trust and isinstance(context_payload.get("q3_connected_agents"), list):
        derived_trust: dict[str, str] = {}
        for raw_agent in context_payload.get("q3_connected_agents", []):
            if not isinstance(raw_agent, dict):
                continue
            agent_id = raw_agent.get("agent_id") or raw_agent.get("id") or raw_agent.get("name")
            agent_status = raw_agent.get("trust_level") or raw_agent.get("status") or raw_agent.get("scope")
            if agent_id and agent_status:
                derived_trust[str(agent_id)] = str(agent_status)
        trust = derived_trust

    if not action_space and not boundaries and not contact_policy and not trust:
        return None
    return Q5PreprocessedEvidence(
        actionable_space=action_space,
        contact_policy=contact_policy,
        tenant_boundaries=boundaries,
        agent_trust_status={str(k): str(v) for k, v in trust.items()} if isinstance(trust, dict) else {},
    )


def _extract_q5_inference_result(result_payload: object) -> Q5WhatAmIAllowedToDoInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    profile = result_payload.get("authorization_boundary_profile") if isinstance(result_payload.get("authorization_boundary_profile"), dict) else result_payload
    if not isinstance(profile, dict):
        return None

    contact_boundaries = profile.get("contact_and_org_boundaries")
    if not isinstance(contact_boundaries, dict):
        contact_boundaries = {}

    forbidden_payload = profile.get("forbidden_action_space")
    forbidden_actions: list[str] = []
    compliance_risks = _coerce_string_list(profile.get("compliance_risks"))
    if isinstance(forbidden_payload, list):
        for raw_item in forbidden_payload:
            if isinstance(raw_item, dict):
                action = str(raw_item.get("action") or "").strip()
                reason = str(raw_item.get("reason") or "").strip()
                if action and reason:
                    forbidden_actions.append(f"{action}: {reason}")
                    compliance_risks.append(reason)
                elif action:
                    forbidden_actions.append(action)
            elif raw_item is not None:
                forbidden_actions.append(str(raw_item))

    forbidden_actions.extend(_coerce_string_list(profile.get("explicitly_forbidden_actions")))
    seen_forbidden: set[str] = set()
    forbidden_actions = [item for item in forbidden_actions if item and not (item in seen_forbidden or seen_forbidden.add(item))]

    compliance_risks.extend(_coerce_string_list(profile.get("requires_escalation_actions")))
    seen_risks: set[str] = set()
    compliance_risks = [item for item in compliance_risks if item and not (item in seen_risks or seen_risks.add(item))]

    allowed_targets = _coerce_string_list(profile.get("allowed_delegation_targets"))
    if not allowed_targets:
        allowed_targets = _coerce_string_list(contact_boundaries.get("allowed_delegation_targets"))

    execution_tier = str(profile.get("execution_tier") or contact_boundaries.get("execution_tier") or "unknown")
    interaction_scope = str(profile.get("interaction_scope") or contact_boundaries.get("interaction_scope") or "unknown")
    requires_human_confirmation = bool(
        profile.get("requires_human_confirmation")
        if "requires_human_confirmation" in profile
        else contact_boundaries.get("requires_human_confirmation")
    )
    requires_cloud_audit = bool(
        profile.get("requires_cloud_audit")
        if "requires_cloud_audit" in profile
        else contact_boundaries.get("requires_cloud_audit")
    )

    if not any(
        (
            execution_tier != "unknown",
            interaction_scope != "unknown",
            requires_human_confirmation,
            requires_cloud_audit,
            bool(forbidden_actions),
            bool(compliance_risks),
            bool(allowed_targets),
        )
    ):
        return None

    return Q5WhatAmIAllowedToDoInferenceView(
        execution_tier=execution_tier,
        interaction_scope=interaction_scope,
        requires_human_confirmation=requires_human_confirmation,
        requires_cloud_audit=requires_cloud_audit,
        explicitly_forbidden_actions=forbidden_actions,
        compliance_risks=compliance_risks,
        allowed_delegation_targets=allowed_targets,
    )


def _extract_q6_preprocessed_evidence(context_payload: object) -> Q6PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("actionable_space", "authorization_boundaries", "non_bypassable_constraints", "historical_strategy_patches")
    ):
        return None
    return Q6PreprocessedEvidence(
        actionable_space=_coerce_string_list(context_payload.get("actionable_space")),
        authorization_boundaries=_coerce_string_list(context_payload.get("authorization_boundaries")),
        non_bypassable_constraints=_coerce_string_list(context_payload.get("non_bypassable_constraints")),
        historical_strategy_patches=_coerce_string_list(context_payload.get("historical_strategy_patches")),
    )


def _extract_q6_inference_result(result_payload: object) -> Q6ForbiddenZoneInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    if not any(
        key in result_payload
        for key in ("absolute_red_lines", "performance_tradeoff_bans", "prohibited_strategies", "contamination_risks")
    ):
        return None
    return Q6ForbiddenZoneInferenceView(
        absolute_red_lines=_coerce_string_list(result_payload.get("absolute_red_lines")),
        performance_tradeoff_bans=_coerce_string_list(result_payload.get("performance_tradeoff_bans")),
        prohibited_strategies=_coerce_string_list(result_payload.get("prohibited_strategies")),
        contamination_risks=_coerce_string_list(result_payload.get("contamination_risks")),
    )


def _extract_q7_preprocessed_evidence(context_payload: object) -> Q7PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("resource_bottlenecks", "capability_limits", "permission_boundaries", "absolute_red_lines", "historical_failure_patches")
    ):
        return None
    return Q7PreprocessedEvidence(
        resource_bottlenecks=_coerce_string_list(context_payload.get("resource_bottlenecks")),
        capability_limits=_coerce_string_list(context_payload.get("capability_limits")),
        permission_boundaries=_coerce_string_list(context_payload.get("permission_boundaries")),
        absolute_red_lines=_coerce_string_list(context_payload.get("absolute_red_lines")),
        historical_failure_patches=_coerce_string_list(context_payload.get("historical_failure_patches")),
    )


def _extract_q7_inference_result(result_payload: object) -> Q7AlternativeStrategyInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    if not any(
        key in result_payload
        for key in ("fallback_plans", "degradation_strategies", "collaboration_switches", "exploratory_actions")
    ):
        return None
    return Q7AlternativeStrategyInferenceView(
        fallback_plans=_coerce_string_list(result_payload.get("fallback_plans")),
        degradation_strategies=_coerce_string_list(result_payload.get("degradation_strategies")),
        collaboration_switches=_coerce_string_list(result_payload.get("collaboration_switches")),
        exploratory_actions=_coerce_string_list(result_payload.get("exploratory_actions")),
    )


def _extract_q8_snapshot_dict(context_payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = context_payload.get("q1_q7_snapshot") or context_payload.get("nine_questions") or {}
    if isinstance(snapshot, dict):
        return {str(k): v for k, v in snapshot.items() if str(k).strip()}
    return {}


def _count_q8_redlines(snapshot: dict[str, Any]) -> int:
    q6 = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    q5 = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    return len(
        _coerce_string_list(q6.get("absolute_red_lines"))
        + _coerce_string_list(q6.get("non_bypassable_constraints"))
        + _coerce_string_list(q5.get("explicitly_forbidden_actions"))
    )


def _count_q8_capability_ceilings(snapshot: dict[str, Any]) -> int:
    q4 = snapshot.get("q4") if isinstance(snapshot.get("q4"), dict) else {}
    q7 = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    return len(
        _coerce_string_list(q4.get("capability_upper_limits"))
        + _coerce_string_list(q4.get("actionable_space"))
        + _coerce_string_list(q7.get("capability_limits"))
    )


def _coerce_q8_persistent_items(raw: object) -> list[Q8PersistentTaskItem]:
    if not isinstance(raw, dict):
        return []

    items: list[Q8PersistentTaskItem] = []
    for status_key, value in raw.items():
        if isinstance(value, list):
            for index, entry in enumerate(value):
                if isinstance(entry, dict):
                    title = str(entry.get("title") or entry.get("task") or entry.get("id") or f"{status_key}-{index}")
                    items.append(
                        Q8PersistentTaskItem(
                            item_id=str(entry.get("id") or f"{status_key}-{index}"),
                            title=title,
                            status=str(entry.get("status") or status_key),
                            priority=entry.get("priority") if isinstance(entry.get("priority"), int) else None,
                            blocker_reason=str(entry.get("blocker_reason") or entry.get("reason") or "")
                            or None,
                        )
                    )
                else:
                    items.append(
                        Q8PersistentTaskItem(
                            item_id=f"{status_key}-{index}",
                            title=str(entry),
                            status=str(status_key),
                        )
                    )
    return items


def _coerce_q8_agenda_items(raw: object) -> list[Q8AgendaItem]:
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []

    agenda_items: list[Q8AgendaItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        agenda_items.append(
            Q8AgendaItem(
                item_id=str(item.get("item_id") or item.get("id") or f"agenda-{index}"),
                title=str(item.get("title") or item.get("item_id") or item.get("id") or f"agenda-{index}"),
                status=str(item.get("status") or "open"),
                priority=item.get("priority") if isinstance(item.get("priority"), int) else None,
                next_review_condition=str(item.get("next_review_condition") or "") or None,
                delay_risk_score=float(item.get("delay_risk_score"))
                if isinstance(item.get("delay_risk_score"), (int, float))
                else None,
            )
        )
    return agenda_items


def _build_q8_preprocessed_evidence(context_payload: dict[str, Any]) -> Q8PreprocessedEvidence | None:
    snapshot = _extract_q8_snapshot_dict(context_payload)
    task_state = _coerce_q8_persistent_items(context_payload.get("persistent_task_state"))
    agenda_items = _coerce_q8_agenda_items(context_payload.get("cognitive_agenda"))
    if not snapshot and not task_state and not agenda_items:
        return None

    return Q8PreprocessedEvidence(
        aggregated_context=Q8AggregatedContextEvidence(
            q1_to_q7_snapshot=snapshot,
            absolute_red_line_count=_count_q8_redlines(snapshot),
            capability_ceiling_count=_count_q8_capability_ceilings(snapshot),
        ),
        runtime_state=Q8RuntimeStateEvidence(
            persistent_task_state=task_state,
            cognitive_agenda=agenda_items,
        ),
    )


def _extract_q8_preprocessed_evidence(context_payload: object) -> Q8PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(key in context_payload for key in ("q1_q7_snapshot", "nine_questions", "persistent_task_state", "cognitive_agenda")):
        return None
    return _build_q8_preprocessed_evidence(context_payload)


def _extract_q8_inference_result(result_payload: object) -> Q8WhatShouldIDoNowInferenceView | None:
    if not isinstance(result_payload, dict):
        return None

    aggregate_raw = result_payload.get("q8_objective_and_queue") or {}
    objective_raw = (
        result_payload.get("objective_profile")
        or result_payload.get("objective")
        or result_payload.get("q8_objective_profile")
        or (aggregate_raw.get("objective") if isinstance(aggregate_raw, dict) else None)
    )
    queue_raw = (
        result_payload.get("task_queue")
        or result_payload.get("q8_task_queue")
        or (aggregate_raw.get("task_queue") if isinstance(aggregate_raw, dict) else None)
    )
    if not isinstance(objective_raw, dict) or not isinstance(queue_raw, dict):
        return None

    return Q8WhatShouldIDoNowInferenceView(
        objective_profile=Q8ObjectiveProfileView(
            current_primary_objective=str(objective_raw.get("current_primary_objective") or ""),
            current_phase_tasks=_coerce_string_list(objective_raw.get("current_phase_tasks")),
            priority_order=_coerce_string_list(objective_raw.get("priority_order")),
        ),
        task_queue=Q8AutonomousTaskQueueView(
            next_self_tasks=queue_raw.get("next_self_tasks") or [],
            blocked_self_tasks=queue_raw.get("blocked_self_tasks") or [],
            proactive_actions=queue_raw.get("proactive_actions") or [],
        ),
    )


def _extract_q9_snapshot_dict(context_payload: dict[str, Any]) -> dict[str, Any]:
    raw = context_payload.get("q1_q8") or context_payload.get("q1_q8_snapshot") or {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if str(k).strip()}
    return {}


def _count_q9_uncertainties(snapshot: dict[str, Any]) -> int:
    q1 = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    return len(_coerce_string_list(q1.get("uncertainties")))


def _count_q9_redlines(snapshot: dict[str, Any]) -> int:
    q5 = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q6 = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    return len(
        _coerce_string_list(q5.get("explicitly_forbidden_actions"))
        + _coerce_string_list(q6.get("absolute_red_lines"))
    )


def _normalize_ratio(value: object) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return 0.0


def _build_q9_preprocessed_evidence(context_payload: dict[str, Any]) -> Q9PreprocessedEvidence | None:
    snapshot = _extract_q9_snapshot_dict(context_payload)
    self_model_raw = context_payload.get("living_self_model") or context_payload.get("self_model") or {}
    budget_raw = context_payload.get("reasoning_budget") or context_payload.get("budget") or {}
    drift_raw = context_payload.get("confidence_drift_indicator") or {}
    if not isinstance(self_model_raw, dict):
        self_model_raw = {}
    if not isinstance(budget_raw, dict):
        budget_raw = {}
    if not isinstance(drift_raw, dict):
        drift_raw = {}

    recent_weaknesses_raw = self_model_raw.get("recent_weaknesses") or []
    recent_weaknesses: list[Q9RecentWeaknessView] = []
    if isinstance(recent_weaknesses_raw, list):
        for item in recent_weaknesses_raw:
            if not isinstance(item, dict):
                continue
            recent_weaknesses.append(
                Q9RecentWeaknessView(
                    pattern_id=str(item.get("pattern_id")) if item.get("pattern_id") else None,
                    pattern_type=str(item.get("pattern_type") or "unknown"),
                    frequency=int(item.get("frequency")) if isinstance(item.get("frequency"), int) else None,
                    severity=str(item.get("severity")) if item.get("severity") else None,
                )
            )

    if not snapshot and not self_model_raw and not budget_raw:
        return None

    return Q9PreprocessedEvidence(
        cognitive_snapshot=Q9CognitiveSnapshotEvidence(
            q1_to_q8_snapshot=snapshot,
            uncertainty_count=_count_q9_uncertainties(snapshot),
            absolute_red_line_count=_count_q9_redlines(snapshot),
        ),
        self_model=Q9SelfModelEvidence(
            cognitive_load=str(
                self_model_raw.get("current_cognitive_load")
                or self_model_raw.get("cognitive_load")
                or "unknown"
            ),
            stability_level=str(
                (self_model_raw.get("current_state") or {}).get("stability_level")
            )
            if isinstance(self_model_raw.get("current_state"), dict)
            and (self_model_raw.get("current_state") or {}).get("stability_level")
            else None,
            confidence_drift=float(drift_raw.get("drift_score"))
            if isinstance(drift_raw.get("drift_score"), (int, float))
            else None,
            recent_weaknesses=recent_weaknesses,
        ),
        reasoning_budget=Q9ReasoningBudgetEvidence(
            compute_remaining_ratio=_normalize_ratio(
                budget_raw.get("compute_remaining_ratio")
                or budget_raw.get("remaining")
                or budget_raw.get("compute_remaining")
            ),
            token_remaining_ratio=_normalize_ratio(
                budget_raw.get("token_remaining_ratio")
                or budget_raw.get("token_remaining")
            ),
            time_remaining_ratio=_normalize_ratio(
                budget_raw.get("time_remaining_ratio")
                or budget_raw.get("time_remaining")
            ),
            budget_pressure=str(budget_raw.get("budget_pressure")) if budget_raw.get("budget_pressure") else None,
        ),
    )


def _extract_q9_preprocessed_evidence(context_payload: object) -> Q9PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(key in context_payload for key in ("q1_q8", "q1_q8_snapshot", "living_self_model", "self_model", "reasoning_budget", "budget")):
        return None
    return _build_q9_preprocessed_evidence(context_payload)


def _extract_q9_inference_result(result_payload: object) -> Q9ActionPostureInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    payload = result_payload.get("q9_action_posture_profile") if isinstance(result_payload.get("q9_action_posture_profile"), dict) else result_payload
    required = {"evaluation_style", "risk_tolerance", "action_rhythm", "confirmation_strategy", "evolution_direction"}
    if not isinstance(payload, dict) or not required.issubset(payload.keys()):
        return None
    return Q9ActionPostureInferenceView(
        evaluation_style=str(payload.get("evaluation_style") or ""),
        risk_tolerance=str(payload.get("risk_tolerance") or ""),
        action_rhythm=str(payload.get("action_rhythm") or ""),
        confirmation_strategy=str(payload.get("confirmation_strategy") or ""),
        evolution_direction=str(payload.get("evolution_direction") or ""),
    )


def _resolve_active_model_provider(runtime: BrainRuntime, request: Request) -> ModelProviderSpec:
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


def _resolve_active_nine_question_tool(registry: CognitiveToolRegistry, question_id: str):
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
    return candidates[0].spec


def _provider_name_for_trace(store: BrainTranscriptStore, trace_id: str) -> str | None:
    if not trace_id:
        return None
    entries = store.search_entries(trace_id=trace_id)
    invoked_event = next(
        (entry for entry in entries if entry.entry_type == BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED),
        None,
    )
    if not invoked_event or not isinstance(invoked_event.payload, dict):
        return None
    provider_name = invoked_event.payload.get("provider_plugin_id")
    return str(provider_name) if provider_name else None


def _question_id_from_source_module(source_module: object) -> str | None:
    if not source_module:
        return None
    text = str(source_module).lower()
    for q_id in QUESTION_TITLES:
        if q_id in text:
            return q_id
    return None


def _build_trace_detail(store: BrainTranscriptStore, trace_id: str) -> ModelProviderTraceItem:
    entries = store.search_entries(trace_id=trace_id)
    if not entries:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    invoked_event = next(
        (e for e in entries if e.entry_type == BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED),
        None,
    )
    completed_event = next(
        (e for e in entries if e.entry_type == BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED),
        None,
    )
    failed_event = next(
        (e for e in entries if e.entry_type == BrainTranscriptEntryType.MODEL_PROVIDER_FAILED),
        None,
    )

    if not invoked_event:
        raise HTTPException(status_code=404, detail="Trace contains no LLM invocation data")

    i_payload = invoked_event.payload or {}
    caller_i = i_payload.get("caller_context") or {}

    c_payload = (completed_event.payload or {}) if completed_event else {}
    f_payload = (failed_event.payload or {}) if failed_event else {}

    related_events: list[TranscriptEventPayload] = []
    for event in entries:
        related_events.append(
            TranscriptEventPayload(
                entry_id=event.entry_id,
                session_id=event.session_id,
                turn_id=event.turn_id,
                entry_type=event.entry_type.value,
                timestamp=event.timestamp.isoformat(),
                source=event.source,
                trace_id=event.trace_id,
                context_info={},
                payload=event.payload,
            )
        )

    trace_context = i_payload.get("context") or {}
    llm_trace_payload = LLMTracePayload(
        request_id=i_payload.get("request_id"),
        decision_id=i_payload.get("decision_id"),
        provider_name=i_payload.get("provider_plugin_id"),
        model=c_payload.get("model"),
        system_prompt=i_payload.get("system_prompt"),
        prompt=i_payload.get("prompt") or i_payload.get("system_prompt"),
        source_module=caller_i.get("source_module"),
        invocation_phase=caller_i.get("invocation_phase"),
        question_driver_refs=caller_i.get("question_driver_refs") or [],
        context_data=trace_context if isinstance(trace_context, dict) else {},
        raw_response=c_payload.get("raw_response") if isinstance(c_payload.get("raw_response"), dict) else None,
        token_usage=LLMTokenUsagePayload.model_validate(c_payload.get("token_usage") or {}),
        elapsed_ms=c_payload.get("elapsed_ms") if isinstance(c_payload.get("elapsed_ms"), int) else None,
        error_type=f_payload.get("error_type"),
        error_message=f_payload.get("error_message"),
    )
    trace_question_id = _question_id_from_source_module(caller_i.get("source_module"))
    evidence_extractors = {
        "q1": _extract_q1_preprocessed_evidence,
        "q2": _extract_q2_preprocessed_evidence,
        "q3": _extract_q3_preprocessed_evidence,
        "q4": _extract_q4_preprocessed_evidence,
        "q5": _extract_q5_preprocessed_evidence,
        "q6": _extract_q6_preprocessed_evidence,
        "q7": _extract_q7_preprocessed_evidence,
        "q8": _extract_q8_preprocessed_evidence,
        "q9": _extract_q9_preprocessed_evidence,
    }
    inference_extractors = {
        "q1": _extract_q1_inference_result,
        "q2": _extract_q2_inference_result,
        "q3": _extract_q3_inference_result,
        "q4": _extract_q4_inference_result,
        "q5": _extract_q5_inference_result,
        "q6": _extract_q6_inference_result,
        "q7": _extract_q7_inference_result,
        "q8": _extract_q8_inference_result,
        "q9": _extract_q9_inference_result,
    }
    extracted_evidence = (
        evidence_extractors[trace_question_id](trace_context)
        if trace_question_id in evidence_extractors
        else (
            _extract_q1_preprocessed_evidence(trace_context)
            or _extract_q2_preprocessed_evidence(trace_context)
            or _extract_q3_preprocessed_evidence(trace_context)
            or _extract_q4_preprocessed_evidence(trace_context)
            or _extract_q5_preprocessed_evidence(trace_context)
            or _extract_q6_preprocessed_evidence(trace_context)
            or _extract_q7_preprocessed_evidence(trace_context)
            or _extract_q8_preprocessed_evidence(trace_context)
            or _extract_q9_preprocessed_evidence(trace_context)
        )
    )
    extracted_inference = (
        inference_extractors[trace_question_id](c_payload.get("result"))
        if trace_question_id in inference_extractors
        else (
            _extract_q1_inference_result(c_payload.get("result"))
            or _extract_q2_inference_result(c_payload.get("result"))
            or _extract_q3_inference_result(c_payload.get("result"))
            or _extract_q4_inference_result(c_payload.get("result"))
            or _extract_q5_inference_result(c_payload.get("result"))
            or _extract_q6_inference_result(c_payload.get("result"))
            or _extract_q7_inference_result(c_payload.get("result"))
            or _extract_q8_inference_result(c_payload.get("result"))
            or _extract_q9_inference_result(c_payload.get("result"))
        )
    )
    extracted_q1_llm_upgrade = (
        _extract_q1_llm_upgrade(trace_context)
        if trace_question_id == "q1"
        else None
    )
    return ModelProviderTraceItem(
        trace_id=trace_id,
        request_id=i_payload.get("request_id") or "unknown",
        decision_id=i_payload.get("decision_id") or "unknown",
        phase_name=caller_i.get("invocation_phase") or "unknown",
        session_id=invoked_event.session_id,
        turn_id=invoked_event.turn_id,
        provider_plugin_id=i_payload.get("provider_plugin_id") or "unknown",
        provider_name=i_payload.get("provider_plugin_id"),
        source_module=caller_i.get("source_module"),
        invocation_phase=caller_i.get("invocation_phase"),
        question_driver_refs=caller_i.get("question_driver_refs") or [],
        invoked_at=invoked_event.timestamp.isoformat(),
        completed_at=completed_event.timestamp.isoformat() if completed_event else None,
        failed_at=failed_event.timestamp.isoformat() if failed_event else None,
        prompt=i_payload.get("prompt") or i_payload.get("system_prompt"),
        context=trace_context,
        result=c_payload.get("result"),
        error_type=f_payload.get("error_type"),
        error_message=f_payload.get("error_message"),
        related_events=related_events,
        preprocessed_evidence=_serialize_contract_payload(extracted_evidence),
        inference_result=_serialize_contract_payload(extracted_inference),
        q1_llm_upgrade=_serialize_contract_payload(extracted_q1_llm_upgrade),
        llm_trace_payload=llm_trace_payload,
    )


@router.get("/nine-questions/objectives")
async def get_evolution_objectives(request: Request):
    runtime: BrainRuntime = get_runtime(request)
    session: BrainSession | None = runtime.active_session
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    return getattr(session, "active_evolution_result", {})


@router.get("/nine-questions/latest-report", response_model=NineQuestionsReportPayload)
async def get_latest_nine_questions_report(request: Request):
    runtime: BrainRuntime = get_runtime(request)
    store: BrainTranscriptStore = get_transcript_store(request)
    plugin_feature_catalog = getattr(request.app.state, "plugin_feature_catalog", None)
    session: BrainSession | None = runtime.active_session
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    state = getattr(session, "current_nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        state = getattr(runtime, "nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        raise HTTPException(status_code=503, detail="NineQuestionState is not attached to the runtime.")


    final_questions: list[NineQuestionReportItem] = []
    for i in range(1, 10):
        q_id = f"q{i}"
        snapshot = state.question_snapshots.get(q_id)
        if not isinstance(snapshot, dict):
            continue

        context_updates = snapshot.get("context_updates")
        context_payload = dict(context_updates) if isinstance(context_updates, dict) else {}
        trace_id = str(snapshot.get("trace_id") or "")
        trace_detail = _build_trace_detail(store, trace_id) if trace_id else None
        final_questions.append(
            NineQuestionReportItem(
                question_id=q_id,
                title=QUESTION_TITLES[q_id],
                tool_id=str(snapshot.get("tool_id") or ""),
                summary=str(snapshot.get("summary") or ""),
                confidence=float(snapshot.get("confidence") or 0.0),
                result=context_payload,
                context_updates=context_payload,
                trace_id=trace_id,
                timestamp=str(snapshot.get("updated_at") or state.refreshed_at.isoformat()),
                cache_status="已失效" if state.is_dirty(q_id) else "已就绪",
                provider_name=_provider_name_for_trace(store, trace_id),
                mounted_plugins=_get_mounted_plugins_for_question(runtime, q_id, plugin_feature_catalog),
                preprocessed_evidence=_build_question_preprocessed_evidence(
                    question_id=q_id,
                    state_context=state.current_context,
                    trace_context=trace_detail.context if trace_detail else None,
                    trace_evidence=trace_detail.preprocessed_evidence if trace_detail else None,
                ),
                inference_result=(
                    trace_detail.inference_result
                    if trace_detail
                    else (
                        _extract_q1_inference_result(context_payload)
                        if q_id == "q1"
                        else _extract_q2_inference_result(context_payload)
                        if q_id == "q2"
                        else _extract_q3_inference_result(context_payload)
                        if q_id == "q3"
                        else _extract_q4_inference_result(context_payload)
                        if q_id == "q4"
                        else _extract_q5_inference_result(context_payload)
                        if q_id == "q5"
                        else _extract_q6_inference_result(context_payload)
                        if q_id == "q6"
                        else _extract_q7_inference_result(context_payload)
                        if q_id == "q7"
                        else _extract_q8_inference_result(context_payload)
                        if q_id == "q8"
                        else _extract_q9_inference_result(context_payload)
                        if q_id == "q9"
                        else None
                    )
                ),
                q1_llm_upgrade=(
                    _extract_q1_llm_upgrade(context_payload)
                    if q_id == "q1"
                    else None
                ),
                llm_trace_payload=trace_detail.llm_trace_payload if trace_detail else None,
            )
        )

    bootstrap = (
        runtime.get_nine_question_bootstrap_status()
        if hasattr(runtime, "get_nine_question_bootstrap_status")
        else {"status": "ready", "error": None}
    )
    status = "ready"
    status_message = None
    if not final_questions and bootstrap.get("status") == "initializing":
        status = "initializing"
        status_message = "大脑冷启动中：正在执行全量九问推演..."
    elif bootstrap.get("status") == "failed":
        status = "failed"
        status_message = str(bootstrap.get("error") or "九问冷启动失败")

    return NineQuestionsReportPayload(
        session_id=session.session_id,
        status=status,
        status_message=status_message,
        last_turn_id=str(getattr(session, "last_turn_id", "0") or "0"),
        snapshot_version=state.snapshot_version,
        revision=state.revision,
        refreshed_at=state.refreshed_at.isoformat(),
        last_refresh_reason=state.last_refresh_reason,
        question_driver_refs=list(state.question_driver_refs),
        questions=final_questions,
    )


@router.get("/nine-questions/{question_id}", response_model=NineQuestionReportItem)
async def get_nine_question_detail(
    request: Request,
    question_id: str,
    trace_id: str | None = None,
):
    """
    Get a single NineQuestion item by question_id.
    - If trace_id is provided, reconstruct the item from the transcript store.
    - Otherwise, return the latest snapshot from the live NineQuestionState.
    This is the proper isolated endpoint for frontend detail pages (Q1-Q9).
    Prevents frontend from being forced to pull all 9 questions just to display one.
    """
    if question_id not in QUESTION_TITLES:
        raise HTTPException(status_code=404, detail=f"Unknown nine question id: {question_id}")

    runtime: BrainRuntime = get_runtime(request)
    store: BrainTranscriptStore = get_transcript_store(request)
    plugin_feature_catalog = getattr(request.app.state, "plugin_feature_catalog", None)
    session: BrainSession | None = runtime.active_session

    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    state = getattr(session, "current_nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        state = getattr(runtime, "nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        raise HTTPException(status_code=503, detail="NineQuestionState is not attached to the runtime.")

    # If trace_id is given, try to reconstruct from transcript history
    effective_trace_id = trace_id
    snapshot = state.question_snapshots.get(question_id)

    # Fall back to snapshot's known trace_id if not explicitly provided
    if not effective_trace_id and isinstance(snapshot, dict):
        effective_trace_id = str(snapshot.get("trace_id") or "")

    trace_detail = _build_trace_detail(store, effective_trace_id) if effective_trace_id else None

    # Build context payload from state snapshot
    context_updates: dict[str, object] = {}
    if isinstance(snapshot, dict):
        raw_updates = snapshot.get("context_updates")
        context_updates = dict(raw_updates) if isinstance(raw_updates, dict) else {}

    # Extract structured evidence using per-question extractors
    _inference_extractors = {
        "q1": _extract_q1_inference_result,
        "q2": _extract_q2_inference_result,
        "q3": _extract_q3_inference_result,
        "q4": _extract_q4_inference_result,
        "q5": _extract_q5_inference_result,
        "q6": _extract_q6_inference_result,
        "q7": _extract_q7_inference_result,
        "q8": _extract_q8_inference_result,
        "q9": _extract_q9_inference_result,
    }

    preprocessed_evidence = _build_question_preprocessed_evidence(
        question_id=question_id,
        state_context=state.current_context,
        trace_context=trace_detail.context if trace_detail else None,
        trace_evidence=trace_detail.preprocessed_evidence if trace_detail else None,
    )
    inference_result = (
        trace_detail.inference_result
        if trace_detail
        else _inference_extractors[question_id](context_updates)
    )
    llm_trace_payload = trace_detail.llm_trace_payload if trace_detail else None

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"{question_id} 尚无快照记录。请先运行一次完整的九问推演流程。"
        )

    return NineQuestionReportItem(
        question_id=question_id,
        title=QUESTION_TITLES[question_id],
        tool_id=str(snapshot.get("tool_id") or ""),
        summary=str(snapshot.get("summary") or ""),
        confidence=float(snapshot.get("confidence") or 0.0),
        result=context_updates,
        context_updates=context_updates,
        trace_id=effective_trace_id or "",
        timestamp=str(snapshot.get("updated_at") or state.refreshed_at.isoformat()),
        cache_status="已失效" if state.is_dirty(question_id) else "已就绪",
        provider_name=_provider_name_for_trace(store, effective_trace_id or ""),
        mounted_plugins=_get_mounted_plugins_for_question(runtime, question_id, plugin_feature_catalog),
        preprocessed_evidence=preprocessed_evidence,
        inference_result=inference_result,
        q1_llm_upgrade=_extract_q1_llm_upgrade(context_updates) if question_id == "q1" else None,
        llm_trace_payload=llm_trace_payload,
    )


@router.get("/nine-questions/traces/{trace_id}", response_model=ModelProviderTraceItem)
async def get_nine_question_trace_detail(request: Request, trace_id: str):
    store: BrainTranscriptStore = get_transcript_store(request)
    return _build_trace_detail(store, trace_id)


@router.post("/nine-questions/{question_id}/test", response_model=NineQuestionSandboxResponse)
async def run_nine_question_sandbox_test(
    request: Request,
    question_id: str,
    payload: NineQuestionSandboxRequest,
):
    runtime: BrainRuntime = get_runtime(request)
    registry: CognitiveToolRegistry = get_cognitive_tool_registry(request)
    plugin_feature_catalog = getattr(request.app.state, "plugin_feature_catalog", None)
    session: BrainSession | None = runtime.active_session
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    if question_id not in QUESTION_TITLES:
        raise HTTPException(status_code=404, detail=f"Unknown nine question id: {question_id}")

    production_state = getattr(session, "current_nine_question_state", None)
    if not isinstance(production_state, NineQuestionState):
        production_state = getattr(runtime, "nine_question_state", None)
    if not isinstance(production_state, NineQuestionState):
        raise HTTPException(status_code=503, detail="NineQuestionState is not attached to the runtime.")

    try:
        provider = _resolve_active_model_provider(runtime, request)
        tool = _resolve_active_nine_question_tool(registry, question_id)
    except PluginNotBoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    base_context = copy.deepcopy(production_state.current_context)
    base_context.update(copy.deepcopy(payload.mock_context))

    sandbox_state = NineQuestionState(
        snapshot_version=production_state.snapshot_version,
        revision=production_state.revision,
        last_refresh_reason="sandbox_test",
        refreshed_at=datetime.now(timezone.utc),
        question_driver_refs=list(production_state.question_driver_refs),
        current_role_hypothesis=production_state.current_role_hypothesis,
        current_context=base_context,
        active_constraints=copy.deepcopy(production_state.active_constraints),
        operator_patch=copy.deepcopy(production_state.operator_patch),
        dirty_questions=copy.deepcopy(production_state.dirty_questions),
        question_snapshots=copy.deepcopy(production_state.question_snapshots),
        environment_fingerprint=production_state.environment_fingerprint,
        agent_signature=production_state.agent_signature,
    )

    trace_id = f"sandbox:{question_id}:{uuid4().hex}"
    turn_id = f"sandbox-test-{question_id}-{uuid4().hex[:8]}"
    started = perf_counter()

    with tempfile.TemporaryDirectory(prefix=f"nineq-{question_id}-") as sandbox_dir:
        sandbox_store = BrainTranscriptStore(Path(sandbox_dir) / "sandbox_transcript.jsonl")
        result = tool.run_tool(
            {
                "session_id": f"{session.session_id}:sandbox",
                "turn_id": turn_id,
                "trace_id": trace_id,
                "decision_id": f"{turn_id}:{question_id}",
                "inspection": True,
                "context_snapshot": base_context,
                "plugin_registry": registry if question_id in {"q8", "q9"} else None,
                "managed_plugin_records": getattr(runtime, "managed_plugin_records", None),
                "cognitive_tool_registry_runtime": registry,
                "nine_questions": (base_context.get("q1_q7_snapshot") or base_context.get("nine_questions") or {})
                if question_id == "q8"
                else {},
                "persistent_task_state": base_context.get("persistent_task_state") or {}
                if question_id == "q8"
                else {},
                "cognitive_agenda": base_context.get("cognitive_agenda") or {}
                if question_id == "q8"
                else {},
                "nine_question_state": (base_context.get("q1_q8") or base_context.get("q1_q8_snapshot") or {})
                if question_id == "q9"
                else {},
                "model_provider": provider,
                "transcript_store": sandbox_store,
                "question_driver_refs": [f"sandbox test {question_id}"],
            }
        )

        if not isinstance(result, CognitiveToolResult):
            raise HTTPException(status_code=500, detail="Nine-question tool returned an invalid result type")

        sandbox_state.apply_question_result(
            question_id=question_id,  # type: ignore[arg-type]
            tool_id=str(result.tool_id),
            summary=str(result.summary),
            confidence=float(result.confidence),
            context_updates=dict(result.context_updates or {}),
            trace_id=trace_id,
            refreshed_at=datetime.now(timezone.utc),
            refresh_reason="sandbox_test",
            driver_refs=[f"sandbox test {question_id}"],
        )
        trace_detail = _build_trace_detail(sandbox_store, trace_id)

    elapsed_ms = int((perf_counter() - started) * 1000)
    preprocessed_evidence = (
        _extract_q1_preprocessed_evidence(base_context)
        if question_id == "q1"
        else _extract_q2_preprocessed_evidence(base_context)
        if question_id == "q2"
        else _extract_q3_preprocessed_evidence(base_context)
        if question_id == "q3"
        else _extract_q4_preprocessed_evidence(base_context)
        if question_id == "q4"
        else _extract_q5_preprocessed_evidence(base_context)
        if question_id == "q5"
        else _extract_q6_preprocessed_evidence(base_context)
        if question_id == "q6"
        else _extract_q7_preprocessed_evidence(base_context)
        if question_id == "q7"
        else _extract_q8_preprocessed_evidence(base_context)
        if question_id == "q8"
        else _extract_q9_preprocessed_evidence(base_context)
        if question_id == "q9"
        else None
    )
    inference_result = (
        _extract_q1_inference_result(trace_detail.result)
        if question_id == "q1"
        else _extract_q2_inference_result(trace_detail.result)
        if question_id == "q2"
        else _extract_q3_inference_result(trace_detail.result)
        if question_id == "q3"
        else _extract_q4_inference_result(trace_detail.result)
        if question_id == "q4"
        else _extract_q5_inference_result(trace_detail.result)
        if question_id == "q5"
        else _extract_q6_inference_result(trace_detail.result)
        if question_id == "q6"
        else _extract_q7_inference_result(trace_detail.result)
        if question_id == "q7"
        else _extract_q8_inference_result(trace_detail.result)
        if question_id == "q8"
        else _extract_q9_inference_result(trace_detail.result)
        if question_id == "q9"
        else None
    )
    return NineQuestionSandboxResponse(
        question_id=question_id,
        title=QUESTION_TITLES[question_id],
        tool_id=str(result.tool_id),
        summary=str(result.summary),
        confidence=float(result.confidence),
        trace_id=trace_id,
        elapsed_ms=elapsed_ms,
        provider_name=str(getattr(provider, "plugin_id", None) or trace_detail.provider_plugin_id),
        prompt=trace_detail.prompt,
        context=trace_detail.context,
        result=trace_detail.result,
        context_updates=dict(result.context_updates or {}),
        mounted_plugins=_get_mounted_plugins_for_question(runtime, question_id, plugin_feature_catalog),
        preprocessed_evidence=preprocessed_evidence,
        inference_result=inference_result,
        q1_llm_upgrade=_extract_q1_llm_upgrade(result.context_updates) if question_id == "q1" else None,
        llm_trace_payload=trace_detail.llm_trace_payload,
    )


@router.post("/nine-questions/run-all", response_model=NineQuestionsRunResponse)
async def run_all_nine_questions(
    request: Request,
    payload: NineQuestionsRunRequest | None = None,
):
    runtime: BrainRuntime = get_runtime(request)
    registry: CognitiveToolRegistry = get_cognitive_tool_registry(request)
    session: BrainSession | None = runtime.active_session
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    state = getattr(session, "current_nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        state = getattr(runtime, "nine_question_state", None)
    if not isinstance(state, NineQuestionState):
        raise HTTPException(status_code=503, detail="NineQuestionState is not attached to the runtime.")

    refresh_reason = "frontend_force_run_all" if (payload is None or payload.force_refresh) else "frontend_run_all"
    try:
        return _run_full_nine_questions(
            request=request,
            runtime=runtime,
            session=session,
            state=state,
            registry=registry,
            refresh_reason=refresh_reason,
        )
    except PluginNotBoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("run-all nine-questions failed")
        raise HTTPException(status_code=500, detail=f"run-all failed: {exc}") from exc
