from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

from plugins.nine_questions.q3_what_do_i_have.models import Q3WhatDoIHaveInference
# Decoupled: Assets are discovered via the plugin registry
from zentex.core.plugin_family import ExecutionPluginSpec


QUESTION_REF = "我有什么"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _humanize_identifier(identifier: str) -> str:
    text = identifier.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ").strip()
    if not text:
        return "未知资产"
    return " ".join(chunk.capitalize() for chunk in text.split())


def _describe_tool(tool_id: object, *, registry_rows: list[dict[str, str]] | None = None) -> dict[str, str]:
    tool_text = _normalize_text(tool_id)
    matched = next((row for row in (registry_rows or []) if row.get("id") == tool_text), None)
    name = matched.get("name") if matched else ""
    introduction = matched.get("introduction") if matched else ""
    function_description = matched.get("function_description") if matched else ""
    if not name:
        name = _humanize_identifier(tool_text)
    if not introduction:
        introduction = f"{name} 是当前运行态可直接调度的一项能力资产。"
    if not function_description:
        function_description = f"{name} 用于在当前工作流中提供 {tool_text} 对应的能力支持。"
    return {
        "id": tool_text,
        "name": name,
        "introduction": introduction,
        "function_description": function_description,
    }


def _describe_agent(agent: dict[str, Any]) -> dict[str, str]:
    agent_id = _normalize_text(agent.get("agent_id") or agent.get("id") or agent.get("name"))
    name = _normalize_text(agent.get("name")) or _humanize_identifier(agent_id)
    role = _normalize_text(agent.get("role") or agent.get("scope") or agent.get("status"))
    summary = _normalize_text(agent.get("summary") or agent.get("description"))
    introduction = summary or f"{name} 是当前已连接的协同 Agent。"
    function_description = (
        f"{name} 负责 {role} 相关的协作、分析或执行支持。"
        if role
        else f"{name} 用于承接需要多 Agent 协同的任务。"
    )
    return {
        "id": agent_id or name,
        "name": name,
        "introduction": introduction,
        "function_description": function_description,
        "status": _normalize_text(agent.get("status")) or "unknown",
    }


def _resource_status_label(status: str) -> str:
    mapping = {
        "sufficient": "资源充沛",
        "degraded": "资源降级",
        "critically_lacking": "关键资源匮乏",
    }
    return mapping.get(status, status or "未知")


def _resource_status_explanation(status: str) -> str:
    mapping = {
        "sufficient": "当前关键工具、执行能力与协同代理基本齐备，可以支撑正常推演与执行。",
        "degraded": "当前具备部分关键资源，但存在明显短板或瓶颈，需要保守决策与补足关键能力。",
        "critically_lacking": "当前缺少关键资源，无法安全完成核心任务，应先补足基础资产再继续执行。",
    }
    return mapping.get(status, "当前资源状态尚未形成可解释结论，需要进一步核查。")


def _safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    return None


def _catalog_rows_from_runtime_context(context: dict[str, Any], *, plugin_ids: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    managed_records = context.get("managed_plugin_records")
    if isinstance(managed_records, dict):
        for record in managed_records.values():
            plugin = getattr(record, "plugin", None)
            plugin_id = _normalize_text(getattr(plugin, "plugin_id", None))
            if not plugin_id or plugin_id not in plugin_ids or plugin_id in seen:
                continue
            rows.append(
                {
                    "id": plugin_id,
                    "name": _humanize_identifier(plugin_id),
                    "introduction": _normalize_text(getattr(record, "description", None))
                    or _normalize_text(getattr(plugin, "purpose", None))
                    or f"{_humanize_identifier(plugin_id)} 是当前运行态中的可用插件资产。",
                    "function_description": _normalize_text(getattr(plugin, "purpose", None))
                    or _normalize_text(getattr(record, "description", None))
                    or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的运行能力。",
                }
            )
            seen.add(plugin_id)

    cognitive_registry = context.get("cognitive_tool_registry_runtime")
    if cognitive_registry is not None and hasattr(cognitive_registry, "list_registrations"):
        try:
            registrations = cognitive_registry.list_registrations()
        except Exception:
            registrations = []
        for registration in registrations:
            spec = getattr(registration, "spec", None)
            plugin_id = _normalize_text(getattr(spec, "plugin_id", None) or getattr(registration, "plugin_id", None))
            if not plugin_id or plugin_id not in plugin_ids or plugin_id in seen:
                continue
            purpose = _normalize_text(getattr(spec, "purpose", None))
            rows.append(
                {
                    "id": plugin_id,
                    "name": _humanize_identifier(plugin_id),
                    "introduction": purpose or f"{_humanize_identifier(plugin_id)} 是当前启用的认知插件资产。",
                    "function_description": purpose or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的认知支持能力。",
                }
            )
            seen.add(plugin_id)

    return rows


class Q3WhatDoIHavePlugin(LogicalCognitiveToolSpec):
    """
    Q3: 我有什么 (unified asset inventory + resource evaluation)

    Red lines:
    - Must use Live LLM (fail-closed).
    - Must not scan full repo or read raw bodies; only lightweight metadata.
    - Must write prompt/context/response into BrainTranscriptStore with trace_id.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        active_tools = snapshot.get("active_tools", {}) or {}
        cog_tools = list(active_tools.get("available_cognitive_tools", []) or [])
        exec_domains = list(active_tools.get("available_execution_tools", []) or [])
        connected_agents = [
            agent
            for agent in (snapshot.get("connected_agents", []) or [])
            if isinstance(agent, dict) and agent.get("status") != "offline"
        ]
        activated_strategy_patches = list(
            (snapshot.get("loaded_memories", {}) or {}).get("activated_strategy_patches", [])
            or []
        )
        accessible_workspace_zones = list(
            (snapshot.get("permissions", {}) or {}).get(
                "accessible_workspace_zones",
                (snapshot.get("workspace_assets", {}) or {}).get("accessible_workspace_zones", []),
            )
            or []
        )
        runtime_cognitive_rows = _catalog_rows_from_runtime_context(context, plugin_ids=cog_tools)
        runtime_execution_rows = _catalog_rows_from_runtime_context(context, plugin_ids=exec_domains)
        cognitive_tool_registry = [
            _describe_tool(item, registry_rows=runtime_cognitive_rows)
            for item in cog_tools
        ]
        execution_domain_registry = [
            _describe_tool(item, registry_rows=runtime_execution_rows)
            for item in exec_domains
        ]
        connected_agent_catalog = [
            _describe_agent(agent)
            for agent in connected_agents
        ]

        system_prompt = (
            "你现在是 Zentex 外部大脑的资产评估中枢。请严格阅读提供的资源清单及活跃插件家族。\n"
            "你的任务是完成大脑资产盘点：插件绝对禁止捏造外部资产，必须基于活跃的 Execution Domains 和 Cognitive Tools 进行能力声明。\n"
            "你必须输出 UnifiedAssetInventory（统一资产盘点对象），作为后续任务分发的物理基础。"
        )

        prompt = (
            f"{system_prompt}\n\n"
            "你必须返回严格 JSON，且必须满足以下结构（少字段直接失败）：\n"
            "- unified_asset_inventory: { available_cognitive_tools, available_execution_tools, connected_agents, activated_strategy_patches, accessible_workspace_zones }\n"
            "- resource_evaluation: { resource_status, missing_critical_assets, bottleneck_node, reasoning_summary }\n"
            "- 禁止输出任何额外字段，尤其禁止输出 `physical_assets`。\n"
            "- `resource_status` 只能是这三个枚举之一: `sufficient`, `degraded`, `critically_lacking`。\n"
            "- `available_execution_tools` 必须是执行域名称列表，不要输出嵌套对象。\n"
            "- `connected_agents` 必须保留为对象数组。\n\n"
            "请基于以下人类可读资产目录完成盘点，不要复述内部代码或 Python/JSON 字面量：\n"
            f"1) 认知工具目录:\n{json.dumps(cognitive_tool_registry, ensure_ascii=False, indent=2)}\n\n"
            f"2) 执行工具目录:\n{json.dumps(execution_domain_registry, ensure_ascii=False, indent=2)}\n\n"
            f"3) 已连接 Agent 目录:\n{json.dumps(connected_agent_catalog, ensure_ascii=False, indent=2)}\n\n"
            "输出示例:\n"
            "{\n"
            '  "unified_asset_inventory": {\n'
            f'    "available_cognitive_tools": {cog_tools},\n'
            f'    "available_execution_tools": {exec_domains},\n'
            f'    "connected_agents": {connected_agents},\n'
            f'    "activated_strategy_patches": {activated_strategy_patches},\n'
            f'    "accessible_workspace_zones": {accessible_workspace_zones}\n'
            "  },\n"
            '  "resource_evaluation": {\n'
            '    "resource_status": "degraded",\n'
            '    "missing_critical_assets": [],\n'
            '    "bottleneck_node": "execution.system",\n'
            '    "reasoning_summary": "当前具备基础认知与执行资源，但执行域仍是主要瓶颈。"\n'
            "  }\n"
            "}\n"
        )

        model_context = {
            "cognitive_tool_registry": cognitive_tool_registry,
            "execution_domain_registry": execution_domain_registry,
            "connected_agents": connected_agent_catalog,
            "activated_strategy_patches": activated_strategy_patches,
            "accessible_workspace_zones": accessible_workspace_zones,
            "workspace_assets": snapshot.get("workspace_assets", {}),
            "permissions": snapshot.get("permissions", {}),
        }

        trace_id = str(context.get("trace_id") or f"q3-what-do-i-have:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q3_what_do_i_have")

        caller_context = build_caller_context(
            source_module="q3_what_do_i_have_plugin",
            invocation_phase="nine_question_q3_what_do_i_have",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": _safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        try:
            started = perf_counter()
            raw = provider.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q3_what_do_i_have",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        inference = Q3WhatDoIHaveInference.model_validate(raw)

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": _json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": _json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": _json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": elapsed_ms,
            },
        )

        summary = (
            f"resource_status={inference.resource_evaluation.resource_status.value}; "
            f"bottleneck={inference.resource_evaluation.bottleneck_node}"
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "unified_asset_inventory",
                    **inference.unified_asset_inventory.model_dump(mode="json"),
                },
                {
                    "kind": "resource_evaluation",
                    **inference.resource_evaluation.model_dump(mode="json"),
                },
            ],
            risks=[
                {
                    "kind": "missing_critical_assets",
                    "items": inference.resource_evaluation.missing_critical_assets,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.resource_evaluation.resource_status.value},
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
                "q3_humanized_asset_inventory": {
                    "cognitive_tool_rows": cognitive_tool_registry,
                    "execution_tool_rows": execution_domain_registry,
                    "connected_agent_rows": connected_agent_catalog,
                },
                "q3_resource_status_humanized": {
                    "label": _resource_status_label(inference.resource_evaluation.resource_status.value),
                    "explanation": _resource_status_explanation(inference.resource_evaluation.resource_status.value),
                },
            },
            confidence=0.7,
        )


def build_q3_what_do_i_have_plugin(
    *,
    plugin_id: str = "nine-question-q3-what-do-i-have",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3WhatDoIHavePlugin:
    return Q3WhatDoIHavePlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q3",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["q3_asset_inventory_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="nine_question",
        purpose="LLM-backed nine-question Q3: 我有什么 (asset inventory + resource evaluation).",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["unified_asset_inventory", "resource_evaluation"],
        },
        required_context=["context_snapshot", "model_provider", "transcript_store"],
        trigger_conditions=["inspection"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "unsafe_external_action"],
    )
